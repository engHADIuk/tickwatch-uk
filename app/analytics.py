"""Aggregate reports and explainable insights. Pure SQL + small, auditable maths (no black box)."""
from __future__ import annotations

import math
import sqlite3
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from .db import build_where

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ------------------------------------------------------------------ reports
def sightings_by_region(conn: sqlite3.Connection, group_by: str, **filters) -> dict[str, Any]:
    col = {"region": "region", "city": "location"}[group_by]
    where, args = build_where(**filters)
    rows = conn.execute(
        f"""SELECT {col} AS name, MIN(region) AS region, COUNT(*) AS n, MIN(date) AS first_seen, MAX(date) AS last_seen
            FROM sightings{where} GROUP BY {col} ORDER BY n DESC, name""", args).fetchall()
    top: dict[str, tuple[str, int]] = {}
    for r in conn.execute(
        f"SELECT {col} AS name, COALESCE(species,'Unknown') AS sp, COUNT(*) AS n FROM sightings{where} "
        f"GROUP BY {col}, sp ORDER BY n DESC", args):
        top.setdefault(r["name"], (r["sp"], r["n"]))
    total = sum(r["n"] for r in rows)
    return {
        "group_by": group_by,
        "total_sightings": total,
        "groups": [
            {
                "name": r["name"],
                **({"region": r["region"]} if group_by == "city" else {}),
                "sightings": r["n"],
                "share_pct": round(100 * r["n"] / total, 2) if total else 0.0,
                "first_sighting": r["first_seen"],
                "last_sighting": r["last_seen"],
                "top_species": top.get(r["name"], (None, 0))[0],
            }
            for r in rows
        ],
    }


def _month_range(a: str, b: str) -> list[str]:
    y, m = int(a[:4]), int(a[5:7])
    ey, em = int(b[:4]), int(b[5:7])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _week_range(a: str, b: str) -> list[tuple[str, str]]:
    d, end = date.fromisoformat(a), date.fromisoformat(b)
    out = []
    while d <= end:
        y, w, _ = d.isocalendar()
        out.append((f"{y}-W{w:02d}", d.isoformat()))
        d += timedelta(days=7)
    return out


def trends(conn: sqlite3.Connection, interval: str, fill_gaps: bool = True, **filters) -> dict[str, Any]:
    where, args = build_where(**filters)
    if interval == "year":
        rows = conn.execute(f"SELECT CAST(year AS TEXT) AS b, MIN(date) AS s, COUNT(*) AS n FROM sightings{where} GROUP BY year ORDER BY year", args).fetchall()
        counts = {r["b"]: r["n"] for r in rows}
        if rows and fill_gaps:
            buckets = [(str(y), f"{y}-01-01") for y in range(int(rows[0]["b"]), int(rows[-1]["b"]) + 1)]
        else:
            buckets = [(r["b"], f"{r['b']}-01-01") for r in rows]
    elif interval == "month":
        rows = conn.execute(f"SELECT month AS b, MIN(date) AS s, COUNT(*) AS n FROM sightings{where} GROUP BY month ORDER BY month", args).fetchall()
        counts = {r["b"]: r["n"] for r in rows}
        buckets = [(m, f"{m}-01") for m in _month_range(rows[0]["b"], rows[-1]["b"])] if rows and fill_gaps else [(r["b"], f"{r['b']}-01") for r in rows]
    else:
        rows = conn.execute(f"SELECT iso_week AS b, MIN(week_start) AS s, COUNT(*) AS n FROM sightings{where} GROUP BY iso_week ORDER BY iso_week", args).fetchall()
        counts = {r["b"]: r["n"] for r in rows}
        buckets = _week_range(rows[0]["s"], rows[-1]["s"]) if rows and fill_gaps else [(r["b"], r["s"]) for r in rows]
    series, prev, window = [], None, []
    for label, start in buckets:
        n = counts.get(label, 0)
        window = (window + [n])[-3:]
        series.append({
            "period": label, "period_start": start, "sightings": n,
            "change_pct": round(100 * (n - prev) / prev, 1) if prev else None,
            "moving_avg_3": round(sum(window) / len(window), 2),
        })
        prev = n
    peak = max(series, key=lambda p: p["sightings"]) if series else None
    return {"interval": interval, "total_sightings": sum(counts.values()), "periods": len(series),
            "peak": {"period": peak["period"], "sightings": peak["sightings"]} if peak else None, "series": series}


def species_summary(conn: sqlite3.Connection, **filters) -> dict[str, Any]:
    where, args = build_where(**filters)
    rows = conn.execute(
        f"""SELECT COALESCE(species,'Unknown') AS species, MIN(latin_name) AS latin_name, COUNT(*) AS n,
                   COUNT(DISTINCT location) AS cities, MIN(date) AS first_seen, MAX(date) AS last_seen
            FROM sightings{where} GROUP BY COALESCE(species,'Unknown') ORDER BY n DESC""", args).fetchall()
    total = sum(r["n"] for r in rows)
    return {"total_sightings": total, "species": [
        {"species": r["species"], "latin_name": r["latin_name"], "sightings": r["n"],
         "share_pct": round(100 * r["n"] / total, 2) if total else 0.0, "cities": r["cities"],
         "first_sighting": r["first_seen"], "last_sighting": r["last_seen"]} for r in rows]}


def seasonality(conn: sqlite3.Connection, **filters) -> dict[str, Any]:
    where, args = build_where(**filters)
    rows = conn.execute(f"SELECT CAST(strftime('%m', date) AS INTEGER) AS m, COUNT(*) AS n FROM sightings{where} GROUP BY m", args).fetchall()
    counts = {r["m"]: r["n"] for r in rows}
    total = sum(counts.values())
    avg = total / 12 if total else 0
    months = [{"month": MONTH_NAMES[m - 1], "month_number": m, "sightings": counts.get(m, 0),
               "seasonal_index": round(counts.get(m, 0) / avg, 2) if avg else None} for m in range(1, 13)]
    peak = max(months, key=lambda x: x["sightings"]) if total else None
    return {"total_sightings": total, "peak_month": peak["month"] if peak else None, "months": months,
            "note": "seasonal_index 1.0 = average month; >1 means busier than average."}


def locations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT location, region, COUNT(*) AS sightings FROM sightings GROUP BY location, region ORDER BY sightings DESC")]


# ------------------------------------------------------------------ insights (extension)
def risk_scores(conn: sqlite3.Connection, as_of: str | None = None, window_days: int = 90, limit: int | None = None) -> dict[str, Any]:
    """Explainable per-city risk score, 0-100.

        score = 100 * (0.50*volume + 0.25*growth + 0.25*seasonality)

    volume       sightings in the last `window_days` relative to the busiest city
    growth       last window vs the window before it (-100% -> 0, flat -> 0.33, +200% -> 1)
    seasonality  how busy this calendar month historically is for the city (2x average -> 1)

    `as_of` defaults to the latest sighting in the dataset, so the model works on historical data.
    """
    latest = conn.execute("SELECT MAX(date) FROM sightings").fetchone()[0]
    if not latest:
        return {"as_of": None, "window_days": window_days, "cities": []}
    ref = date.fromisoformat(as_of or latest)
    w1_start, w2_start = ref - timedelta(days=window_days), ref - timedelta(days=2 * window_days)

    def counts(lo: date, hi: date, lo_incl: bool) -> dict[str, int]:
        op = ">=" if lo_incl else ">"
        return {r["location"]: r["n"] for r in conn.execute(
            f"SELECT location, COUNT(*) n FROM sightings WHERE date {op} ? AND date <= ? GROUP BY location",
            (lo.isoformat(), hi.isoformat()))}

    recent = counts(w1_start, ref, False)
    previous = counts(w2_start, w1_start, False)
    info = {r["location"]: (r["region"], r["n"]) for r in conn.execute("SELECT location, MIN(region) region, COUNT(*) n FROM sightings GROUP BY location")}
    by_month: dict[str, dict[int, int]] = defaultdict(dict)
    for r in conn.execute("SELECT location, CAST(strftime('%m', date) AS INTEGER) m, COUNT(*) n FROM sightings GROUP BY location, m"):
        by_month[r["location"]][r["m"]] = r["n"]

    max_recent = max(recent.values(), default=0)
    out = []
    for city, (region, total) in info.items():
        r, p = recent.get(city, 0), previous.get(city, 0)
        volume = r / max_recent if max_recent else 0.0
        ratio = (r - p) / max(p, 1)
        growth = _clamp((ratio + 1) / 3)
        idx = by_month[city].get(ref.month, 0) / (total / 12) if total else 0.0
        season = _clamp(idx / 2)
        score = round(100 * (0.5 * volume + 0.25 * growth + 0.25 * season), 1)
        level = "high" if score >= 66 else "medium" if score >= 33 else "low"
        out.append({
            "city": city, "region": region, "risk_score": score, "risk_level": level,
            "confidence": "low" if total < 10 else "ok",
            "components": {"volume": round(volume, 3), "growth": round(growth, 3), "seasonality": round(season, 3)},
            "evidence": {"recent_sightings": r, "previous_sightings": p, "growth_pct": round(100 * ratio, 1),
                         "seasonal_index_for_month": round(idx, 2), "total_sightings": total},
            "explanation": (f"{r} sightings in the last {window_days} days (previous window: {p}); "
                            f"{MONTH_NAMES[ref.month - 1]} is {idx:.1f}x an average month for this city."),
        })
    out.sort(key=lambda c: (-c["risk_score"], c["city"]))
    return {"as_of": ref.isoformat(), "window_days": window_days,
            "method": "100*(0.5*volume + 0.25*growth + 0.25*seasonality); see README", "cities": out[:limit] if limit else out}


def anomalies(conn: sqlite3.Connection, scope: str = "region", z_threshold: float = 2.0, min_count: int = 3) -> dict[str, Any]:
    """Flag months whose sighting count is a statistical outlier for their own series (z-score)."""
    if scope == "overall":
        rows = conn.execute("SELECT 'All UK' AS k, month, COUNT(*) n FROM sightings GROUP BY month").fetchall()
    else:
        col = {"region": "region", "city": "location"}[scope]
        rows = conn.execute(f"SELECT {col} AS k, month, COUNT(*) n FROM sightings GROUP BY {col}, month").fetchall()
    if not rows:
        return {"scope": scope, "z_threshold": z_threshold, "anomalies": []}
    all_months = _month_range(min(r["month"] for r in rows), max(r["month"] for r in rows))
    series: dict[str, dict[str, int]] = defaultdict(dict)
    for r in rows:
        series[r["k"]][r["month"]] = r["n"]
    found = []
    for key, data in series.items():
        vals = [data.get(m, 0) for m in all_months]
        if len(vals) < 3:
            continue
        mean, sd = statistics.fmean(vals), statistics.pstdev(vals)
        if sd == 0:
            continue
        for m, v in zip(all_months, vals):
            z = (v - mean) / sd
            if z >= z_threshold and v >= min_count:
                found.append({"scope_key": key, "month": m, "sightings": v, "expected": round(mean, 2),
                              "z_score": round(z, 2), "severity": "high" if z >= 3 else "moderate"})
    found.sort(key=lambda a: -a["z_score"])
    return {"scope": scope, "z_threshold": z_threshold, "min_count": min_count, "count": len(found), "anomalies": found,
            "method": "z = (monthly count - series mean) / series std-dev; flagged when z >= threshold and count >= min_count"}


def data_quality(conn: sqlite3.Connection) -> dict[str, Any]:
    import json
    last = conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
    total = conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
    flags: dict[str, int] = defaultdict(int)
    for r in conn.execute("SELECT quality_flags f, COUNT(*) n FROM sightings WHERE quality_flags != '' GROUP BY f"):
        for fl in r["f"].split(","):
            flags[fl] += r["n"]
    q = {r["reason"]: r["n"] for r in conn.execute("SELECT reason, COUNT(*) n FROM quarantine GROUP BY reason")}
    user_reports = conn.execute("SELECT COUNT(*) FROM sightings WHERE source = 'user'").fetchone()[0]
    conflicts = [dict(r) for r in conn.execute(
        "SELECT latin_name, GROUP_CONCAT(DISTINCT species) species_names, COUNT(DISTINCT species) k FROM sightings "
        "WHERE latin_name IS NOT NULL AND species IS NOT NULL GROUP BY latin_name HAVING k > 1")]
    rng = conn.execute("SELECT MIN(date), MAX(date) FROM sightings").fetchone()
    return {
        "stored_sightings": total, "community_reports": user_reports, "date_range": {"from": rng[0], "to": rng[1]},
        "records_with_flags": dict(flags),
        "quarantined_all_time": q,
        "latin_name_with_multiple_species": conflicts,
        "last_sync": None if not last else {
            **{k: last[k] for k in ("id", "status", "source", "received", "accepted", "inserted", "updated", "unchanged",
                                    "rejected", "api_reported_total", "error", "started_at", "duration_ms")},
            "reject_reasons": json.loads(last["reject_reasons"] or "{}"),
            "flag_counts": json.loads(last["flag_counts"] or "{}"),
        },
    }


def map_markers(conn: sqlite3.Connection, recent_days: int = 90, **filters) -> dict[str, Any]:
    """One marker per city for the interactive map, with counts, recent activity and risk level."""
    from datetime import date as _d
    from .geo import coords_for

    where, args = build_where(**filters)
    latest = conn.execute("SELECT MAX(date) FROM sightings").fetchone()[0]
    if not latest:
        return {"as_of": None, "recent_days": recent_days, "total_sightings": 0, "markers": []}
    ref = _d.fromisoformat(latest)
    recent_from = (ref - timedelta(days=recent_days)).isoformat()
    rows = conn.execute(
        f"""SELECT location, MIN(region) AS region, COUNT(*) AS n, MAX(date) AS last_seen,
                   SUM(CASE WHEN date > ? THEN 1 ELSE 0 END) AS recent
            FROM sightings{where} GROUP BY location ORDER BY n DESC""", [recent_from, *args]).fetchall()
    top: dict[str, str] = {}
    for r in conn.execute(f"SELECT location, COALESCE(species,'Unidentified') sp, COUNT(*) n FROM sightings{where} GROUP BY location, sp ORDER BY n DESC", args):
        top.setdefault(r["location"], r["sp"])
    risk = {c["city"]: c for c in risk_scores(conn, as_of=None, window_days=recent_days)["cities"]}
    markers = []
    for r in rows:
        xy = coords_for(r["location"])
        if not xy:
            continue
        k = risk.get(r["location"], {})
        markers.append({"city": r["location"], "region": r["region"], "lat": xy[0], "lng": xy[1],
                        "sightings": r["n"], "recent_sightings": r["recent"], "last_sighting": r["last_seen"],
                        "top_species": top.get(r["location"]), "risk_score": k.get("risk_score"),
                        "risk_level": k.get("risk_level", "low"), "explanation": k.get("explanation")})
    return {"as_of": latest, "recent_days": recent_days, "total_sightings": sum(m["sightings"] for m in markers),
            "markers": markers}


def species_latin_map(conn: sqlite3.Connection) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for r in conn.execute("SELECT species, latin_name, COUNT(*) n FROM sightings WHERE species IS NOT NULL AND species != 'Unidentified' GROUP BY species, latin_name ORDER BY n DESC"):
        out.setdefault(r["species"], r["latin_name"])
    return out
