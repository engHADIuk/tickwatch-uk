"""Handling of community sighting reports: validation, image checks, rate limiting, storage."""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

from . import analytics
from . import db as dbm
from .cleaning import CleanRecord, normalise_species, parse_date
from .errors import AppError
from .regions import canonical_city, region_for

MIN_YEAR = 2000
MAX_NOTES = 500
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _sniff(data: bytes) -> str | None:
    """Identify an image by its first bytes, never by the filename or declared type."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class RateLimiter:
    """Tiny in-memory sliding-window limiter (one process; use Redis behind a load balancer)."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            wait = max(1, int(60 - (now - q[0])))
            raise AppError(429, "rate_limited", "Too many reports in a short time. Please wait a moment and try again.",
                           {"retry_after_seconds": wait}, headers={"Retry-After": str(wait)})
        q.append(now)


def validate_report(conn, date: str, location: str, species: str, notes: str, image_present: bool):
    """Return (clean_fields, errors). Collects every problem so the form can show them all at once."""
    errors: list[dict] = []
    when = parse_date(date.strip()) if date and date.strip() else None
    now = datetime.utcnow()
    if not date or not date.strip():
        errors.append({"field": "date", "problem": "Please enter when you saw the tick."})
    elif when is None:
        errors.append({"field": "date", "problem": "That date is not valid. Use the date picker."})
    elif when > now + timedelta(minutes=5):
        errors.append({"field": "date", "problem": "The sighting cannot be in the future."})
    elif when.year < MIN_YEAR:
        errors.append({"field": "date", "problem": f"Sightings before {MIN_YEAR} are not accepted."})

    city = canonical_city(location.strip()) if location and location.strip() else None
    if not location or not location.strip():
        errors.append({"field": "location", "problem": "Please choose the nearest city."})
    elif city is None:
        errors.append({"field": "location", "problem": "We do not recognise that city. Please pick one from the list."})

    known = analytics.species_latin_map(conn)
    sp_clean = species.strip() if species else ""
    chosen = None
    if not sp_clean:
        errors.append({"field": "species", "problem": "Please choose a species, or 'Not sure'."})
    elif sp_clean.lower() in ("not sure", "unidentified"):
        chosen = "Unidentified"
    else:
        match = next((k for k in known if k.lower() == normalise_species(sp_clean).lower()), None)
        if match is None:
            errors.append({"field": "species", "problem": "Please pick a species from the list."})
        else:
            chosen = match

    note = " ".join((notes or "").split())
    if len(note) > MAX_NOTES:
        errors.append({"field": "notes", "problem": f"Notes must be {MAX_NOTES} characters or fewer (you have {len(note)})."})
    return when, city, chosen, known, note, errors


async def read_image(upload, max_mb: int, errors: list[dict]) -> tuple[bytes, str] | None:
    if upload is None or not getattr(upload, "filename", ""):
        return None
    data = await upload.read(max_mb * 1024 * 1024 + 1)
    if len(data) > max_mb * 1024 * 1024:
        errors.append({"field": "image", "problem": f"The photo is larger than {max_mb} MB. Please choose a smaller one."})
        return None
    if not data:
        errors.append({"field": "image", "problem": "The photo file is empty."})
        return None
    kind = _sniff(data)
    if kind is None:
        errors.append({"field": "image", "problem": "Photos must be JPEG, PNG or WebP images."})
        return None
    return data, kind


def store_report(conn, uploads_dir: str, when, city, species, known, note, image) -> dict:
    latin = known.get(species) if species != "Unidentified" else None
    rec = CleanRecord(id="usr_" + uuid.uuid4().hex[:12], occurred_at=when.replace(microsecond=0), location=city,
                      region=region_for(city), latin_name=latin, species=species,
                      flags=["community_report"] + (["missing_latin_name"] if latin is None else []))
    clash = dbm.existing_hashes(conn, [rec.content_hash]).get(rec.content_hash)
    if clash:
        raise AppError(409, "duplicate_report", "This sighting looks like one that has already been reported.", {"existing_id": clash})
    image_path = None
    if image:
        data, kind = image
        Path(uploads_dir).mkdir(parents=True, exist_ok=True)
        image_path = uuid.uuid4().hex + IMAGE_TYPES[kind]
        (Path(uploads_dir) / image_path).write_bytes(data)
    dbm.insert_user_report(conn, rec.to_row(), note or None, image_path)
    return {"id": rec.id}
