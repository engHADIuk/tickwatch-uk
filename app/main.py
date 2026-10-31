"""FastAPI application: search, reporting, insights and operational endpoints."""
import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analytics, content
from . import db as dbm
from . import submissions
from .config import Settings, get_settings
from .errors import AppError, install_error_handlers
from .ingest import run_sync

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

log = logging.getLogger("tick.api")

DESCRIPTION = """
Backend MVP for a **UK Tick Tracker**. It ingests the Elanco tick-sightings API, cleans and
de-duplicates it, stores it, and serves search, aggregate reports and explainable risk insights.

* **Search** `/sightings` - filter by date range, city, region, species, free text.
* **Reports** `/reports/*` - per region / city, weekly & monthly trends, species, seasonality.
* **Insights** `/insights/*` - explainable risk score per city and anomaly (spike) detection.
* **Report** `POST /sightings` - community submissions with validation and optional photo.
* **Map & learn** `/map/markers`, `/education` - data for the web app.
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
    source: str = "api"
    notes: str | None = None
    image_url: str | None = None


class SightingPage(BaseModel):
    total: int
    limit: int
    offset: int
    count: int
    items: list[Sighting]


def _to_sighting(row) -> Sighting:
    d = dict(row)
    d["quality_flags"] = [f for f in d["quality_flags"].split(",") if f]
    d["image_url"] = f"/uploads/{d['image_path']}" if d.get("image_path") else None
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
    limiter = submissions.RateLimiter(settings.reports_per_minute)
    Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)

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
        response.headers["X-Content-Type-Options"] = "nosniff"  # uploaded files are never sniffed as HTML/JS
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        log.info("%s %s -> %s (%.0f ms) rid=%s", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - t0) * 1000, request.state.request_id)
        return response

    def conn_dep():
        with database.connect() as conn:
            yield conn

    # ------------------------------------------------------------ operations
    @app.get("/", include_in_schema=False)
    def root():
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
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

    @app.get("/sightings/export", tags=["Search"], summary="Download the filtered sightings as a CSV file")
    def export_sightings(f: Filters = Depends(), q: str | None = Query(None), conn=Depends(conn_dep)):
        import csv
        import io
        where, args = dbm.build_where(**f.kw, q=q)
        rows = conn.execute(f"SELECT * FROM sightings{where} ORDER BY occurred_at DESC, id LIMIT 20000", args).fetchall()

        def safe(v):  # stop spreadsheet formula injection from user-supplied text
            v = "" if v is None else str(v)
            return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "date", "time", "city", "region", "species", "latin_name", "source", "notes", "photo_url"])
        for r in rows:
            w.writerow([safe(r["id"]), r["date"], r["occurred_at"][11:19], safe(r["location"]), safe(r["region"]), safe(r["species"]),
                        safe(r["latin_name"]), r["source"], safe(r["notes"]), f"/uploads/{r['image_path']}" if r["image_path"] else ""])
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="tickwatch-sightings.csv"'})

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
        interval: Literal["week", "month", "year"] = "month",
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

    # ------------------------------------------------------------ report a sighting
    @app.post("/sightings", response_model=Sighting, status_code=201, tags=["Report"],
              summary="Submit a new community sighting (multipart form, optional photo)")
    async def create_sighting(
        request: Request,
        date: str = Form("", description="When it was seen, e.g. 2026-10-31T14:30"),
        location: str = Form("", description="Nearest UK city"),
        species: str = Form("", description="A species from /education or 'Not sure'"),
        notes: str = Form("", description="Optional, up to 500 characters"),
        image: UploadFile | None = File(None, description="Optional JPEG, PNG or WebP, max 5 MB"),
    ):
        limiter.check(request.client.host if request.client else "unknown")
        with database.connect() as conn:
            when, city, chosen, known, note, errors = submissions.validate_report(conn, date, location, species, notes, image is not None)
            img = await submissions.read_image(image, settings.max_upload_mb, errors)
            if errors:
                raise AppError(422, "validation_error", "Please fix the highlighted fields.", errors)
            made = submissions.store_report(conn, settings.uploads_dir, when, city, chosen, known, note, img)
            row = conn.execute("SELECT * FROM sightings WHERE id = ?", (made["id"],)).fetchone()
        return _to_sighting(row)

    # ------------------------------------------------------------ map + learn (for the web app)
    @app.get("/map/markers", tags=["Map & learn"], summary="One marker per city with counts, recent activity and risk level")
    def map_markers(f: Filters = Depends(), recent_days: int = Query(90, ge=7, le=365), conn=Depends(conn_dep)):
        return analytics.map_markers(conn, recent_days, **f.kw)

    @app.get("/education", tags=["Map & learn"], summary="Species guide, prevention tips and removal steps")
    def education(conn=Depends(conn_dep)):
        counts = {r["species"]: r["n"] for r in conn.execute("SELECT species, COUNT(*) n FROM sightings GROUP BY species")}
        species = [{**sp, "sightings": counts.get(sp["species"], 0)} for sp in content.SPECIES_GUIDE]
        return {"species": species, "prevention_tips": content.PREVENTION_TIPS, "removal_steps": content.REMOVAL_STEPS,
                "see_a_professional": content.SEE_A_PROFESSIONAL, "disclaimer": content.DISCLAIMER}

    @app.get("/options", tags=["Map & learn"], summary="Values for the filter and form dropdowns")
    def options(conn=Depends(conn_dep)):
        regions = [r[0] for r in conn.execute("SELECT DISTINCT region FROM sightings ORDER BY region")]
        species = list(analytics.species_latin_map(conn).keys())
        rng = conn.execute("SELECT MIN(date), MAX(date) FROM sightings").fetchone()
        from .geo import CITY_COORDS
        from .regions import region_for
        cities = [{"city": c, "region": region_for(c), "lat": xy[0], "lng": xy[1]} for c, xy in sorted(CITY_COORDS.items())]
        return {"regions": regions, "species": species, "cities": cities, "date_min": rng[0], "date_max": rng[1]}

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

    for mount, folder in (("/assets", FRONTEND_DIR / "assets"), ("/vendor", FRONTEND_DIR / "vendor")):
        if folder.exists():
            app.mount(mount, StaticFiles(directory=folder), name=mount.strip("/"))
    app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")
    return app


app = create_app()
