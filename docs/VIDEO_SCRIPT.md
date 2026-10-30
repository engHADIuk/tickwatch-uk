# 10-minute walkthrough script (aim for ~8 minutes)

**0:00 - Intro (30s)** "I'm Muhammad Hadi. This is a backend MVP for a UK tick tracker. The focus is how data is consumed, processed and presented."

**0:30 - The data (1m)** Show `https://dev-task.elancoapps.com/` and one record. Point out: flat list, no coordinates, city only, ~1000 rows.

**1:30 - Architecture (1m 30s)** Show the mermaid diagram in the README. Explain: ingest into SQLite instead of proxying; why (speed, resilience, no hammering the source).

**3:00 - Data quality (2m)** Run `python scripts/profile_data.py sightings.json`. Then in Swagger: `POST /sync`, `GET /data-quality`, `GET /quarantine`. Explain the policy: reject vs keep+flag vs infer; three kinds of duplicates; `/sync` twice = 0 inserted (idempotent).

**5:00 - Resilience (1m 30s)** Terminal 1: `FAIL_RATE=0.6 uvicorn scripts.mock_upstream:app --port 9000`. Terminal 2: `TICK_API_BASE_URL=http://127.0.0.1:9000/data uvicorn app.main:app`. Show retry logs. Then kill the mock and call `POST /sync` -> `degraded`, still serving from snapshot. Show the 422 and 404 error envelopes.

**6:30 - Search + reports (1m)** `/sightings` with date range + city; `/reports/regions`; `/reports/trends?interval=week`.

**7:30 - Extension (1m)** `/insights/risk` - walk through one city's components and explanation; `/insights/anomalies`. Say why it is explainable rather than a black box.

**8:30 - Tests + next steps (1m)** `pytest -q`. Mention Postgres/PostGIS, scheduled sync, write path, calibrating the risk score.
