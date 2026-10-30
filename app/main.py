"""FastAPI application: search, reporting, insights and operational endpoints."""
import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal

from fastapi import Depends, FastAPI, Query, Request
from pydantic import BaseModel

from . import analytics
from . import db as dbm
from .config import Settings, get_settings
from .errors import AppError, install_error_handlers
from .ingest import run_sync

log = logging.getLogger("tick.api")

DESCRIPTION = """
Backend MVP for a **UK Tick Tracker**. It ingests the Elanco tick-sightings API, cleans and
de-duplicates it, stores it, and serves search, aggregate reports and explainable risk insights.

* **Search** `/sightings` - filter by date range, city, region, species, free text.
* **Reports** `/reports/*` - per region / city, weekly & monthly trends, species, seasonality.
* **Insights** `/insights/*` - explainable risk score per city and anomaly (spike) detection.
* **Operations** `/sync`, `/data-quality`, `/health` - ingestion control and observability.
"""


# ---------------------------------------------------------------- response models
class Sighting(BaseModel):
    id: str
    occurred_at: str
    date: str
    location: str
    region: str
    species: str | None = None
    latin_name: str | None = None
    quality_flags: list[str] = []


class SightingPage(BaseModel):
    total: int
    limit: int
    offset: int
    count: int
    items: list[Sighting]


def _to_sighting(row) -> Sighting:
    d = dict(row)
    d["quality_flags"] = [f for f in d["quality_flags"].split(",") if f]
    return Sighting(**{k: d[k] for k in Sighting.model_fields})


# ---------------------------------------------------------------- shared query params
class Filters:
    """Common filters shared by search and every report endpoint."""

    def __init__(
        self,
        start_date: date | None = Query(None, description="Inclusive, YYYY-MM-DD", examples=["2020-01-01"]),
        end_date: date | None = Query(None, description="Inclusive, YYYY-MM-DD", examples=["2022-12-31"]),
        location: str | None = Query(None, description="City, case-insensitive exact match", examples=["Manchester"]),
        region: str | None = Query(None, description="UK region / nation", examples=["Scotland"]),
        species: str | None = Query(None, description="Common or Latin species name"),
    ):
        if start_date and end_date and start_date > end_date:
            raise AppError(422, "validation_error", "start_date must be on or before end_date",
                           {"start_date": str(start_date), "end_date": str(end_date)})
        self.kw = {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "location": location, "region": region, "species": species,
        }


def create_app(settings: Settings | None = None, client_factory=None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    database = dbm.Database(settings.db_path)
    sync_lock = asyncio.Lock()

    async def do_sync() -> dict:
        if sync_lock.locked():
            raise AppError(409, "sync_in_progress", "A sync is already running; try again shortly.")
        async with sync_lock:
            return await run_sync(database, settings, client=client_factory() if client_factory else None)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.init()
        with database.connect() as c:
            empty = c.execute("SELECT COUNT(*) FROM sightings").fetchone()[0] == 0
        if empty and settings.auto_sync_on_startup:
            try:
                await do_sync()
            except Exception as e:  # noqa: BLE001 - never block startup; /health will show degraded
                log.error("Initial sync failed (API will start empty, call POST /sync to retry): %s", e)
        yield

    app = FastAPI(title="UK Tick Tracker API", version="1.0.0", description=DESCRIPTION, lifespan=lifespan)
    install_error_handlers(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        log.info("%s %s -> %s (%.0f ms) rid=%s", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - t0) * 1000, request.state.request_id)
        return response

    def conn_dep():
        with database.connect() as conn:
            yield conn

    # ------------------------------------------------------------ operations
    @app.get("/", include_in_schema=False)
    def root():
        return {"service": "UK Tick Tracker API", "docs": "/docs", "health": "/health"}

    @app.get("/health", tags=["Operations"], summary="Liveness + data freshness")
    def health(conn=Depends(conn_dep)):
        n = conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
        last = conn.execute("SELECT id, status, source, finished_at FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
        status = "ok" if n and last and last["status"] == "success" else "degraded"
        return {"status": status, "stored_sightings": n, "last_sync": dict(last) if last else None}

    @app.post("/sync", tags=["Operations"], summary="Pull, clean and store the latest upstream data")
    async def sync():
        return await do_sync()

    @app.get("/sync/history", tags=["Operations"], summary="Recent ingestion runs (audit trail)")
    def sync_history(limit: int = Query(10, ge=1, le=100), conn=Depends(conn_dep)):
        rows = conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["reject_reasons"] = json.loads(d["reject_reasons"] or "{}")
            d["flag_counts"] = json.loads(d["flag_counts"] or "{}")
            out.append(d)
        return out

    @app.get("/data-quality", tags=["Operations"], summary="What was wrong with the data and what we did about it")
    def data_quality(conn=Depends(conn_dep)):
        return analytics.data_quality(conn)

    @app.get("/quarantine", tags=["Operations"], summary="Rejected records and the reason for each")
    def quarantine(reason: str | None = None, limit: int = Query(50, ge=1, le=500), conn=Depends(conn_dep)):
        sql, args = "SELECT id, run_id, reason, raw_json, created_at FROM quarantine", []
        if reason:
            sql += " WHERE reason = ?"; args.append(reason)
        rows = conn.execute(sql + " ORDER BY id DESC LIMIT ?", [*args, limit]).fetchall()
        return [{**dict(r), "raw_json": json.loads(r["raw_json"]) if r["raw_json"].startswith(("{", "[")) else r["raw_json"]} for r in rows]

    # ------------------------------------------------------------ search
    @app.get("/sightings", response_model=SightingPage, tags=["Search"], summary="Search and filter sightings")
    def list_sightings(
        f: Filters = Depends(),
        q: str | None = Query(None, description="Free text over city / species / latin name"),
        sort: Literal["date_desc", "date_asc"] = "date_desc",
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        conn=Depends(conn_dep),
    ):
        where, args = dbm.build_where(**f.kw, q=q)
        total, rows = dbm.search_sightings(conn, where, args, sort, limit, offset)
        return SightingPage(total=total, limit=limit, offset=offset, count=len(rows), items=[_to_sighting(r) for r in rows])

    @app.get("/sightings/{sighting_id}", response_model=Sighting, tags=["Search"], summary="One sighting by id")
    def get_sighting(sighting_id: str, conn=Depends(conn_dep)):
        row = conn.execute("SELECT * FROM sightings WHERE id = ?", (sighting_id,)).fetchone()
        if not row:
            raise AppError(404, "not_found", f"No sighting with id '{sighting_id}'")
        return _to_sighting(row)

    @app.get("/locations", tags=["Search"], summary="Known cities with their region and sighting count")
    def list_locations(conn=Depends(conn_dep)):
        return analytics.locations(conn)

    # ------------------------------------------------------------ reports
    @app.get("/reports/regions", tags=["Reports"], summary="Number of sightings per region (or per city)")
    def report_regions(
        group_by: Literal["region", "city"] = "region", f: Filters = Depends(), conn=Depends(conn_dep)
    ):
        return analytics.sightings_by_region(conn, group_by, **f.kw)

    @app.get("/reports/trends", tags=["Reports"], summary="Sightings over time, weekly or monthly")
    def report_trends(
        interval: Literal["week", "month"] = "month",
        fill_gaps: bool = Query(True, description="Include zero-count periods so charts have a continuous axis"),
        f: Filters = Depends(), conn=Depends(conn_dep),
    ):
        return analytics.trends(conn, interval, fill_gaps, **f.kw)

    @app.get("/reports/species", tags=["Reports"], summary="Breakdown by species")
    def report_species(f: Filters = Depends(), conn=Depends(conn_dep)):
        return analytics.species_summary(conn, **f.kw)

    @app.get("/reports/seasonality", tags=["Reports"], summary="Which months of the year are busiest")
    def report_seasonality(f: Filters = Depends(), conn=Depends(conn_dep)):
        return analytics.seasonality(conn, **f.kw)

    # ------------------------------------------------------------ insights
    @app.get("/insights/risk", tags=["Insights (extension)"], summary="Explainable tick-risk score per city")
    def insights_risk(
        as_of: date | None = Query(None, description="Score as of this date (default: latest sighting)"),
        window_days: int = Query(90, ge=7, le=365),
        limit: int | None = Query(None, ge=1, le=500),
        conn=Depends(conn_dep),
    ):
        return analytics.risk_scores(conn, as_of.isoformat() if as_of else None, window_days, limit)

    @app.get("/insights/anomalies", tags=["Insights (extension)"], summary="Unusual spikes in sightings")
    def insights_anomalies(
        scope: Literal["overall", "region", "city"] = "region",
        z_threshold: float = Query(2.0, ge=1.0, le=6.0),
        min_count: int = Query(3, ge=1),
        conn=Depends(conn_dep),
    ):
        return analytics.anomalies(conn, scope, z_threshold, min_count)

    return app


app = create_app()
