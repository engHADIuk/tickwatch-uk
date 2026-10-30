"""The ingestion pipeline: fetch -> snapshot -> clean -> dedupe -> upsert -> audit trail."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from . import db as dbm
from .cleaning import process_batch
from .client import TickApiClient, UpstreamError
from .config import Settings
from .errors import AppError

log = logging.getLogger("tick.ingest")
DEGRADED_REJECT_RATIO = 0.25


def _save_snapshot(path: str, payload: list[Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    os.replace(tmp, p)  # atomic: a crash can never leave a half-written snapshot


def _load_snapshot(path: str) -> list[Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, list) else None
    except (OSError, ValueError):
        return None


async def run_sync(database: dbm.Database, settings: Settings, client: TickApiClient | None = None) -> dict[str, Any]:
    t0 = time.monotonic()
    own_client = client is None
    client = client or TickApiClient(
        settings.api_base_url, settings.http_timeout_s, settings.max_retries,
        settings.backoff_base_s, settings.backoff_max_s,
    )
    with database.connect() as conn:
        run_id = dbm.start_run(conn)

    source, error, reported_total = "api", None, None
    try:
        try:
            raw = await client.fetch_all_sightings()
            reported_total = await client.fetch_reported_total()
            _save_snapshot(settings.snapshot_path, raw)
        except UpstreamError as e:
            error = str(e)
            log.error("Upstream failed: %s", e)
            raw = _load_snapshot(settings.snapshot_path)
            if raw is None:
                with database.connect() as conn:
                    dbm.finish_run(conn, run_id, status="failed", source="none", error=error,
                                   duration_ms=int((time.monotonic() - t0) * 1000))
                raise AppError(502, "upstream_unavailable",
                               "Upstream API unavailable and no local snapshot exists to fall back on.",
                               {"error": error, "sync_run_id": run_id}) from e
            source = "snapshot"
            log.warning("Falling back to local snapshot (%d records)", len(raw))
    finally:
        if own_client:
            await client.aclose()

    with database.connect() as conn:
        result = process_batch(raw, known_hashes=lambda hs: dbm.existing_hashes(conn, hs))
        stats = dbm.upsert_sightings(conn, [r.to_row() for r in result.clean])
        dbm.add_quarantine(conn, run_id, ((r.reason, r.raw) for r in result.rejected))
        ratio = len(result.rejected) / len(raw) if raw else 0
        notes = []
        if source == "snapshot":
            status = "degraded"
        elif ratio > DEGRADED_REJECT_RATIO:
            status = "degraded"; notes.append(f"{ratio:.0%} of records rejected")
        else:
            status = "success"
        if reported_total is not None and reported_total != len(raw):
            notes.append(f"API reported {reported_total} sightings but returned {len(raw)}")
        if not raw:
            notes.append("upstream returned an empty list")
        dbm.finish_run(
            conn, run_id, status=status, source=source, received=len(raw), accepted=len(result.clean),
            rejected=len(result.rejected), reject_reasons=result.reject_reasons, flag_counts=result.flag_counts,
            api_reported_total=reported_total, error="; ".join(filter(None, [error, *notes])) or None,
            duration_ms=int((time.monotonic() - t0) * 1000), **stats,
        )

    report = {
        "sync_run_id": run_id, "status": status, "source": source, "received": len(raw),
        "accepted": len(result.clean), "rejected": len(result.rejected),
        "reject_reasons": result.reject_reasons, "flag_counts": result.flag_counts,
        "api_reported_total": reported_total, "notes": notes, **stats,
        "duration_ms": int((time.monotonic() - t0) * 1000),
    }
    log.info("Sync finished: %s", report)
    return report
