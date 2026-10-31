import sqlite3
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from tests.conftest import FakeUpstream, make_client
from tests.factories import clean_payload

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def yesterday():
    return (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")


def good(**over):
    base = {"date": yesterday(), "location": "Leeds", "species": "Marsh tick", "notes": "Found on my dog after a walk"}
    base.update(over)
    return base


def problems(resp):
    return {d["field"]: d["problem"] for d in resp.json()["error"]["details"]}


def test_submit_report_appears_in_search_and_reports(api):
    r = api.post("/sightings", data=good())
    assert r.status_code == 201
    body = r.json()
    assert body["id"].startswith("usr_") and body["source"] == "user" and body["region"] == "Yorkshire and The Humber"
    assert "community_report" in body["quality_flags"] and body["notes"].startswith("Found on")
    assert api.get(f"/sightings/{body['id']}").json()["location"] == "Leeds"
    assert api.get("/sightings", params={"q": "marsh"}).json()["total"] >= 1
    assert api.get("/data-quality").json()["community_reports"] == 1


def test_submit_with_photo_is_served_back(api):
    r = api.post("/sightings", data=good(), files={"image": ("tick.png", PNG, "image/png")})
    assert r.status_code == 201
    url = r.json()["image_url"]
    assert url.startswith("/uploads/") and url.endswith(".png")
    assert api.get(url).content == PNG


def test_photo_is_checked_by_content_not_filename(api):
    r = api.post("/sightings", data=good(), files={"image": ("virus.png", b"MZ not an image at all", "image/png")})
    assert r.status_code == 422 and "JPEG, PNG or WebP" in problems(r)["image"]
    ok = api.post("/sightings", data=good(date=yesterday()[:-1] + "1"), files={"image": ("a.jpeg", JPG, "image/jpeg")})
    assert ok.status_code == 201


def test_photo_too_large_rejected(api):
    big = PNG + b"\x00" * (1024 * 1024 + 10)
    r = api.post("/sightings", data=good(), files={"image": ("big.png", big, "image/png")})
    assert r.status_code == 422 and "larger than 1 MB" in problems(r)["image"]


def test_all_validation_errors_returned_together(api):
    future = (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    r = api.post("/sightings", data={"date": future, "location": "Atlantis", "species": "Dragon tick", "notes": "x" * 600})
    assert r.status_code == 422
    p = problems(r)
    assert set(p) == {"date", "location", "species", "notes"}
    assert "future" in p["date"]


def test_required_fields(api):
    r = api.post("/sightings", data={})
    assert r.status_code == 422 and set(problems(r)) == {"date", "location", "species"}
    assert api.post("/sightings", data=good(date="not-a-date")).status_code == 422


def test_not_sure_species_is_stored_as_unidentified(api):
    r = api.post("/sightings", data=good(species="Not sure"))
    assert r.status_code == 201 and r.json()["species"] == "Unidentified"


def test_duplicate_report_conflict(api):
    d = good()
    assert api.post("/sightings", data=d).status_code == 201
    again = api.post("/sightings", data=d)
    assert again.status_code == 409 and again.json()["error"]["code"] == "duplicate_report"


def test_rate_limit_with_retry_after(settings):
    settings.reports_per_minute = 2
    up = FakeUpstream(clean_payload(30))
    with TestClient(create_app(settings, client_factory=lambda: make_client(up))) as c:
        for i in range(2):
            assert c.post("/sightings", data=good(date=f"2026-01-0{i + 1}T10:00")).status_code == 201
        r = c.post("/sightings", data=good(date="2026-01-09T10:00"))
        assert r.status_code == 429 and r.headers["retry-after"].isdigit()
        assert r.json()["error"]["code"] == "rate_limited"


def test_user_reports_survive_a_resync(api):
    rid = api.post("/sightings", data=good()).json()["id"]
    api.post("/sync")
    assert api.get(f"/sightings/{rid}").status_code == 200


def test_map_markers(api):
    m = api.get("/map/markers").json()
    assert m["total_sightings"] == 300 and len(m["markers"]) == 10
    first = m["markers"][0]
    assert {"city", "lat", "lng", "sightings", "recent_sightings", "risk_level", "top_species"} <= set(first)
    assert 49 < first["lat"] < 60 and -9 < first["lng"] < 2
    one = api.get("/map/markers", params={"species": "Marsh tick"}).json()
    assert 0 < one["total_sightings"] < 300
    assert api.get("/map/markers", params={"start_date": "2100-01-01"}).json()["markers"] == []


def test_education_and_options(api):
    e = api.get("/education").json()
    assert len(e["species"]) >= 5 and e["prevention_tips"] and e["removal_steps"] and e["disclaimer"]
    assert any(s["in_dataset"] and s["sightings"] > 0 for s in e["species"])
    o = api.get("/options").json()
    assert "Marsh tick" in o["species"] and any(c["city"] == "Leeds" for c in o["cities"]) and o["date_min"]


def test_yearly_trend(api):
    y = api.get("/reports/trends", params={"interval": "year"}).json()
    assert sum(p["sightings"] for p in y["series"]) == 300 and y["periods"] >= 4


def test_old_database_is_migrated(tmp_path):
    path = str(tmp_path / "old.db")
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE sightings (id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL, date TEXT NOT NULL,
        year INTEGER NOT NULL, month TEXT NOT NULL, iso_week TEXT NOT NULL, week_start TEXT NOT NULL, latin_name TEXT,
        species TEXT, location TEXT NOT NULL, location_key TEXT NOT NULL, region TEXT NOT NULL, content_hash TEXT NOT NULL,
        quality_flags TEXT NOT NULL DEFAULT '', first_seen_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        INSERT INTO sightings VALUES ('a','2020-01-01T00:00:00','2020-01-01',2020,'2020-01','2020-W01','2019-12-30',
        'L','S','London','london','London','h','', 'x','x');""")
    con.commit(); con.close()
    Database(path).init()
    row = sqlite3.connect(path).execute("SELECT id, source, notes, image_path FROM sightings").fetchone()
    assert row == ("a", "api", None, None)


def test_many_concurrent_requests_do_not_crash(api):
    """Regression: the web app fires several requests at once; the DB layer must be thread-safe."""
    from concurrent.futures import ThreadPoolExecutor
    paths = ["/health", "/options", "/map/markers", "/education", "/reports/regions", "/reports/species",
             "/reports/seasonality", "/reports/trends?interval=year", "/sightings?limit=5", "/insights/risk?limit=3"]
    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(lambda p: api.get(p).status_code, paths * 8))
    assert set(codes) == {200}


def test_homepage_serves_the_web_app(api):
    r = api.get("/")
    assert r.status_code == 200 and "TickWatch UK" in r.text
    assert api.get("/assets/styles.css").status_code == 200 and api.get("/vendor/chart.umd.js").status_code == 200


def test_csv_export_respects_filters_and_blocks_formula_injection(api):
    api.post("/sightings", data=good(notes="=HYPERLINK(\"http://evil\")"))
    r = api.get("/sightings/export", params={"location": "Leeds"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("id,date,time,city,region,species") and len(lines) >= 2
    assert all(",Leeds," in ln for ln in lines[1:])
    assert "'=HYPERLINK" in r.text and ",=HYPERLINK" not in r.text
    everything = api.get("/sightings/export").text.strip().splitlines()
    assert len(everything) == 300 + 1 + 1  # header + 300 api rows + the report above
