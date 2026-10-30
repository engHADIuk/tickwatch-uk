import httpx

from tests.conftest import FakeUpstream, make_client
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_startup_sync_and_health(api):
    h = api.get("/health").json()
    assert h["status"] == "ok" and h["stored_sightings"] == 300


def test_sync_is_idempotent(api):
    r = api.post("/sync").json()
    assert (r["inserted"], r["updated"], r["unchanged"]) == (0, 0, 300)
    assert api.get("/health").json()["stored_sightings"] == 300


def test_search_filters_and_paging(api):
    page = api.get("/sightings", params={"location": "manchester", "limit": 5}).json()
    assert page["count"] <= 5 and all(i["location"] == "Manchester" for i in page["items"])
    rng = api.get("/sightings", params={"start_date": "2019-01-01", "end_date": "2019-12-31", "limit": 500}).json()
    assert rng["total"] > 0 and all("2019-01-01" <= i["date"] <= "2019-12-31" for i in rng["items"])
    p2 = api.get("/sightings", params={"limit": 10, "offset": 10}).json()
    p1 = api.get("/sightings", params={"limit": 10}).json()
    assert {i["id"] for i in p1["items"]}.isdisjoint({i["id"] for i in p2["items"]})
    asc = api.get("/sightings", params={"sort": "date_asc", "limit": 3}).json()["items"]
    assert [i["date"] for i in asc] == sorted(i["date"] for i in asc)
    assert api.get("/sightings", params={"region": "Scotland"}).json()["total"] > 0
    assert api.get("/sightings", params={"q": "castor"}).json()["total"] > 0


def test_validation_errors_use_envelope(api):
    r = api.get("/sightings", params={"start_date": "2022-01-01", "end_date": "2020-01-01"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = api.get("/sightings", params={"start_date": "yesterday"})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "start_date"
    assert api.get("/sightings", params={"limit": 9999}).status_code == 422
    assert api.get("/reports/trends", params={"interval": "day"}).status_code == 422


def test_not_found_envelope_and_request_id(api):
    r = api.get("/sightings/nope", headers={"x-request-id": "abc123"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert r.json()["error"]["request_id"] == "abc123" and r.headers["x-request-id"] == "abc123"
    assert api.get("/no/such/route").json()["error"]["code"] == "not_found"


def test_region_report(api):
    r = api.get("/reports/regions").json()
    assert r["total_sightings"] == 300 and sum(g["sightings"] for g in r["groups"]) == 300
    assert abs(sum(g["share_pct"] for g in r["groups"]) - 100) < 0.1
    c = api.get("/reports/regions", params={"group_by": "city"}).json()
    assert c["groups"][0]["region"]


def test_trends_monthly_weekly(api):
    m = api.get("/reports/trends", params={"interval": "month"}).json()
    assert sum(p["sightings"] for p in m["series"]) == 300 and m["periods"] >= 40
    w = api.get("/reports/trends", params={"interval": "week", "location": "London"}).json()
    assert sum(p["sightings"] for p in w["series"]) == w["total_sightings"]
    sparse = api.get("/reports/trends", params={"interval": "month", "fill_gaps": "false"}).json()
    assert sparse["periods"] <= m["periods"]
    assert api.get("/reports/trends", params={"start_date": "2100-01-01"}).json()["series"] == []


def test_species_and_seasonality(api):
    s = api.get("/reports/species").json()
    assert sum(x["sightings"] for x in s["species"]) == 300
    se = api.get("/reports/seasonality").json()
    assert len(se["months"]) == 12 and se["total_sightings"] == 300


def test_risk_scores_explainable(api):
    r = api.get("/insights/risk", params={"limit": 5}).json()
    assert r["as_of"] and len(r["cities"]) == 5
    top = r["cities"][0]
    assert 0 <= top["risk_score"] <= 100 and top["risk_level"] in {"low", "medium", "high"}
    assert set(top["components"]) == {"volume", "growth", "seasonality"} and top["explanation"]
    scores = [c["risk_score"] for c in r["cities"]]
    assert scores == sorted(scores, reverse=True)


def test_anomalies_detect_injected_spike(settings):
    from tests.factories import clean_payload
    data = clean_payload(120)
    data += [{"id": f"spike{i}", "date": f"2019-07-{10 + i:02d}T09:00:00", "latinName": "Ixodes ricinus",
              "location": "Leeds", "species": "Castor bean tick"} for i in range(15)]
    up = FakeUpstream(data)
    with TestClient(create_app(settings, client_factory=lambda: make_client(up))) as c:
        out = c.get("/insights/anomalies", params={"scope": "overall"}).json()
        assert any(a["month"] == "2019-07" for a in out["anomalies"])


def test_messy_data_is_quarantined_and_reported(messy_api):
    dq = messy_api.get("/data-quality").json()
    assert dq["last_sync"]["rejected"] == 9 and dq["last_sync"]["reject_reasons"]["duplicate_content"] == 1
    assert dq["records_with_flags"]["species_inferred"] >= 1
    q = messy_api.get("/quarantine", params={"reason": "invalid_date"}).json()
    assert len(q) == 1 and q[0]["raw_json"]["id"] == "m1"
    assert messy_api.get("/sightings/m5").json()["location"] == "London"


def test_upstream_down_falls_back_to_snapshot(settings):
    up = FakeUpstream(__import__("tests.factories", fromlist=["x"]).clean_payload(40))
    app = create_app(settings, client_factory=lambda: make_client(up, retries=2))
    with TestClient(app) as c:
        assert c.get("/health").json()["stored_sightings"] == 40
        up.script = [httpx.Response(500)] * 10
        r = c.post("/sync").json()
        assert r["status"] == "degraded" and r["source"] == "snapshot"
        assert c.get("/health").json()["status"] == "degraded"
        assert c.get("/sightings").json()["total"] == 40  # still serving data


def test_upstream_down_no_snapshot_returns_502_and_app_still_starts(settings):
    up = FakeUpstream([])
    up.script = [httpx.Response(503)] * 20
    app = create_app(settings, client_factory=lambda: make_client(up, retries=2))
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "degraded"
        up.script = [httpx.Response(503)] * 20
        r = c.post("/sync")
        assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_unavailable"
        assert c.get("/sightings").json()["total"] == 0
