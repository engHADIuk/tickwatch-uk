"""Validation, normalisation and de-duplication of raw upstream records.

Policy (documented in README):
  * A record is REJECTED (quarantined with a reason, never silently dropped) only when it
    lacks something every query depends on: id, a parseable date, or a location.
  * Missing species / latin name does NOT reject the record. We try to infer the gap from
    the rest of the batch (latin name <-> species is one-to-one in practice) and flag it.
  * Duplicates are caught three ways: same id repeated, same event under a different id,
    and an event already stored from an earlier sync.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from .regions import canonical_city, region_for

_WS = re.compile(r"\s+")
_PLACEHOLDERS = {"", "null", "none", "n/a", "na", "nan", "unknown", "-", "undefined"}
_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
)
MIN_YEAR = 1900


@dataclass
class CleanRecord:
    id: str
    occurred_at: datetime
    location: str
    region: str
    latin_name: str | None
    species: str | None
    flags: list[str] = field(default_factory=list)

    @property
    def location_key(self) -> str:
        return self.location.lower()

    @property
    def content_hash(self) -> str:
        what = (self.latin_name or self.species or "").lower()
        raw = f"{self.occurred_at.isoformat()}|{self.location_key}|{what}"
        return hashlib.sha1(raw.encode()).hexdigest()

    def to_row(self) -> dict[str, Any]:
        d = self.occurred_at
        iso_year, iso_week, iso_wd = d.isocalendar()
        return {
            "id": self.id,
            "occurred_at": d.isoformat(timespec="seconds"),
            "date": d.date().isoformat(),
            "year": d.year,
            "month": d.strftime("%Y-%m"),
            "iso_week": f"{iso_year}-W{iso_week:02d}",
            "week_start": (d.date() - timedelta(days=iso_wd - 1)).isoformat(),
            "latin_name": self.latin_name,
            "species": self.species,
            "location": self.location,
            "location_key": self.location_key,
            "region": self.region,
            "content_hash": self.content_hash,
            "quality_flags": ",".join(sorted(set(self.flags))),
        }


@dataclass
class Rejection:
    reason: str
    raw: Any


@dataclass
class BatchResult:
    clean: list[CleanRecord]
    rejected: list[Rejection]

    @property
    def reject_reasons(self) -> dict[str, int]:
        return dict(Counter(r.reason for r in self.rejected))

    @property
    def flag_counts(self) -> dict[str, int]:
        c: Counter = Counter()
        for r in self.clean:
            c.update(set(r.flags))
        return dict(c)


# ---------- field level helpers ----------
def _text(v: Any) -> str | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        v = str(v)
    if not isinstance(v, str):
        return None
    v = _WS.sub(" ", v).strip()
    return None if v.lower() in _PLACEHOLDERS else v


def parse_date(v: Any) -> datetime | None:
    """Parse the many date shapes seen in crowdsourced data into a naive UTC datetime."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        secs = v / 1000 if v > 1e11 else v
        try:
            return datetime.fromtimestamp(secs, tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    s = _text(v)
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        dt = None
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def normalise_location(raw: str) -> str:
    known = canonical_city(raw)
    if known:
        return known
    return " ".join(w.capitalize() if w.islower() or w.isupper() else w for w in raw.split(" "))


def normalise_latin(raw: str) -> str:
    parts = raw.split(" ")
    return " ".join([parts[0].capitalize()] + [p.lower() for p in parts[1:]])


def normalise_species(raw: str) -> str:
    return raw[:1].upper() + raw[1:].lower()


# ---------- record level ----------
def clean_record(raw: Any, now: datetime | None = None) -> CleanRecord | str:
    """Return a CleanRecord, or a string reason code when the record must be rejected."""
    if not isinstance(raw, dict):
        return "not_an_object"
    now = now or datetime.utcnow()

    rid = _text(raw.get("id"))
    if not rid:
        return "missing_id"
    when = parse_date(raw.get("date"))
    if raw.get("date") in (None, "") or when is None:
        return "missing_date" if _text(raw.get("date")) is None else "invalid_date"
    if when.year < MIN_YEAR:
        return "invalid_date"
    if when > now + timedelta(days=1):
        return "future_date"
    loc = _text(raw.get("location"))
    if not loc:
        return "missing_location"

    location = normalise_location(loc)
    latin = _text(raw.get("latinName") if "latinName" in raw else raw.get("latin_name"))
    species = _text(raw.get("species"))
    rec = CleanRecord(
        id=rid,
        occurred_at=when,
        location=location,
        region=region_for(location),
        latin_name=normalise_latin(latin) if latin else None,
        species=normalise_species(species) if species else None,
    )
    if rec.region == "Unknown":
        rec.flags.append("unknown_region")
    if location != loc:
        rec.flags.append("location_normalised")
    return rec


def _infer_missing(records: list[CleanRecord]) -> None:
    """Fill species / latin name gaps using the (almost always 1:1) mapping seen in the batch."""
    latin_to_sp: dict[str, Counter] = defaultdict(Counter)
    sp_to_latin: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        if r.latin_name and r.species:
            latin_to_sp[r.latin_name][r.species] += 1
            sp_to_latin[r.species][r.latin_name] += 1
    for r in records:
        if r.species is None and r.latin_name:
            options = latin_to_sp.get(r.latin_name)
            if options and len(options) == 1:
                r.species = next(iter(options))
                r.flags.append("species_inferred")
        if r.latin_name is None and r.species:
            options = sp_to_latin.get(r.species)
            if options and len(options) == 1:
                r.latin_name = next(iter(options))
                r.flags.append("latin_name_inferred")
        if r.species is None:
            r.flags.append("missing_species")
        if r.latin_name is None:
            r.flags.append("missing_latin_name")


def process_batch(
    raw_items: Iterable[Any],
    known_hashes: Callable[[list[str]], dict[str, str]] | None = None,
    now: datetime | None = None,
) -> BatchResult:
    """Clean + de-duplicate a whole payload.

    known_hashes(hashes) -> {content_hash: id} lets the caller tell us which events are
    already stored under a *different* id (cross-sync duplicates).
    """
    clean: list[CleanRecord] = []
    rejected: list[Rejection] = []
    seen_id: dict[str, tuple] = {}
    seen_hash: dict[str, str] = {}

    for raw in raw_items:
        res = clean_record(raw, now)
        if isinstance(res, str):
            rejected.append(Rejection(res, raw))
            continue
        h = res.content_hash
        fingerprint = (h, res.species, res.latin_name)  # whole record, so a changed field is a *conflict*
        if res.id in seen_id:
            reason = "duplicate_exact" if seen_id[res.id] == fingerprint else "duplicate_id_conflict"
            rejected.append(Rejection(reason, raw))
            continue
        if h in seen_hash:
            rejected.append(Rejection("duplicate_content", raw))
            continue
        seen_id[res.id] = fingerprint
        seen_hash[h] = res.id
        clean.append(res)

    if known_hashes and clean:
        existing = known_hashes([r.content_hash for r in clean])
        kept: list[CleanRecord] = []
        for r in clean:
            other = existing.get(r.content_hash)
            if other is not None and other != r.id:
                rejected.append(Rejection("duplicate_content", {"id": r.id, "duplicate_of": other}))
            else:
                kept.append(r)
        clean = kept

    _infer_missing(clean)
    return BatchResult(clean=clean, rejected=rejected)
