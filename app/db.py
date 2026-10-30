"""SQLite storage. Zero setup for the MVP; the SQL is portable to Postgres/PostGIS later."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS sightings (
    id            TEXT PRIMARY KEY,
    occurred_at   TEXT NOT NULL,
    date          TEXT NOT NULL,
    year          INTEGER NOT NULL,
    month         TEXT NOT NULL,
    iso_week      TEXT NOT NULL,
    week_start    TEXT NOT NULL,
    latin_name    TEXT,
    species       TEXT,
    location      TEXT NOT NULL,
    location_key  TEXT NOT NULL,
    region        TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    quality_flags TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_s_date     ON sightings(date);
CREATE INDEX IF NOT EXISTS ix_s_location ON sightings(location_key);
CREATE INDEX IF NOT EXISTS ix_s_region   ON sightings(region);
CREATE INDEX IF NOT EXISTS ix_s_species  ON sightings(species);
CREATE INDEX IF NOT EXISTS ix_s_month    ON sightings(month);
CREATE INDEX IF NOT EXISTS ix_s_week     ON sightings(iso_week);
CREATE INDEX IF NOT EXISTS ix_s_hash     ON sightings(content_hash);

CREATE TABLE IF NOT EXISTS sync_runs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at         TEXT NOT NULL,
    finished_at        TEXT,
    status             TEXT NOT NULL,
    source             TEXT,
    received           INTEGER DEFAULT 0,
    accepted           INTEGER DEFAULT 0,
    inserted           INTEGER DEFAULT 0,
    updated            INTEGER DEFAULT 0,
    unchanged          INTEGER DEFAULT 0,
    rejected           INTEGER DEFAULT 0,
    reject_reasons     TEXT DEFAULT '{}',
    flag_counts        TEXT DEFAULT '{}',
    api_reported_total INTEGER,
    error              TEXT,
    duration_ms        INTEGER
);

CREATE TABLE IF NOT EXISTS quarantine (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    raw_json   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_q_run ON quarantine(run_id);
"""

_COLS = (
    "id occurred_at date year month iso_week week_start latin_name species location "
    "location_key region content_hash quality_flags"
).split()
_COMPARE = ("occurred_at", "latin_name", "species", "location", "region", "content_hash", "quality_flags")
CHUNK = 500


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as c:
            c.executescript(SCHEMA)


# ---------- writes ----------
def upsert_sightings(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> dict[str, int]:
    """Idempotent batch upsert. Re-running a sync with the same data changes nothing."""
    stats = {"inserted": 0, "updated": 0, "unchanged": 0}
    now = utcnow()
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        ids = [r["id"] for r in chunk]
        marks = ",".join("?" * len(ids))
        existing = {
            r["id"]: r
            for r in conn.execute(f"SELECT * FROM sightings WHERE id IN ({marks})", ids)
        }
        to_write = []
        for r in chunk:
            old = existing.get(r["id"])
            if old is None:
                stats["inserted"] += 1
            elif any(old[k] != r[k] for k in _COMPARE):
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
                continue
            to_write.append(r)
        conn.executemany(
            f"""INSERT INTO sightings ({",".join(_COLS)}, first_seen_at, updated_at)
                VALUES ({",".join(":" + c for c in _COLS)}, :now, :now)
                ON CONFLICT(id) DO UPDATE SET
                  {",".join(f"{c}=excluded.{c}" for c in _COLS if c != "id")},
                  updated_at=excluded.updated_at""",
            [{**r, "now": now} for r in to_write],
        )
    return stats


def existing_hashes(conn: sqlite3.Connection, hashes: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(hashes), CHUNK):
        part = hashes[i : i + CHUNK]
        marks = ",".join("?" * len(part))
        for r in conn.execute(f"SELECT content_hash, id FROM sightings WHERE content_hash IN ({marks})", part):
            out[r["content_hash"]] = r["id"]
    return out


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO sync_runs (started_at, status) VALUES (?, 'running')", (utcnow(),))
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, **f: Any) -> None:
    for k in ("reject_reasons", "flag_counts"):
        if k in f:
            f[k] = json.dumps(f[k])
    sets = ",".join(f"{k}=:{k}" for k in f)
    conn.execute(f"UPDATE sync_runs SET finished_at=:fin, {sets} WHERE id=:id", {**f, "fin": utcnow(), "id": run_id})


def add_quarantine(conn: sqlite3.Connection, run_id: int, items: Iterable[tuple[str, Any]]) -> None:
    now = utcnow()
    conn.executemany(
        "INSERT INTO quarantine (run_id, reason, raw_json, created_at) VALUES (?,?,?,?)",
        [(run_id, reason, json.dumps(raw, default=str)[:2000], now) for reason, raw in items],
    )


# ---------- reads ----------
def build_where(
    start_date: str | None = None,
    end_date: str | None = None,
    location: str | None = None,
    region: str | None = None,
    species: str | None = None,
    q: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if start_date:
        clauses.append("date >= ?"); args.append(start_date)
    if end_date:
        clauses.append("date <= ?"); args.append(end_date)
    if location:
        clauses.append("location_key = ?"); args.append(location.strip().lower())
    if region:
        clauses.append("LOWER(region) = ?"); args.append(region.strip().lower())
    if species:
        clauses.append("(LOWER(species) = ? OR LOWER(latin_name) = ?)"); args += [species.strip().lower()] * 2
    if q:
        like = f"%{q.strip().lower()}%"
        clauses.append("(location_key LIKE ? OR LOWER(COALESCE(species,'')) LIKE ? OR LOWER(COALESCE(latin_name,'')) LIKE ?)")
        args += [like] * 3
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", args


def search_sightings(conn, where: str, args: list[Any], sort: str, limit: int, offset: int):
    order = "ASC" if sort == "date_asc" else "DESC"
    total = conn.execute(f"SELECT COUNT(*) FROM sightings{where}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM sightings{where} ORDER BY occurred_at {order}, id LIMIT ? OFFSET ?",
        [*args, limit, offset],
    ).fetchall()
    return total, rows
