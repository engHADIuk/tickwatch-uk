# Video script (target 8-9 minutes, hard limit 10)

**0:00-0:30 Intro.** Say your full name. "TickWatch UK: a full-stack tick tracker. A FastAPI backend cleans and serves the data; a web app lets people explore, learn and report."

**0:30-1:30 Home page.** Scroll the home page: live numbers, the sightings network (hover, click a city), "Check your area" (change city and activity), this month's outlook. Click the three colour swatches to show Forest, Midnight and Heather, and say the theme is remembered.

**1:30-2:00 The problem and the data.** Show the Elanco docs page and one raw record. Flat list, about 1000 rows, city names only, no coordinates. This shapes the map (city level) and the design.

**2:00-3:00 The map.** Show the bubbles: size = sightings, colour = relative activity, rings as a non-colour cue. Use the date chips, species and region filters. Switch to List view and say why (accessibility). Click Nottingham.

**3:00-4:15 Sighting details.** Walk the panel: KPIs, the recent-activity score and its explanation, yearly/monthly timeline toggle, species bars, seasonal pattern, latest sightings. Click Share (link copied), then Get directions (new tab, close it).

**4:15-5:30 Report a sighting.** Submit empty: show the summary and inline errors. Pick an old date: show the amber warning. Try a text file as a photo: show the rejection. Then submit properly with a photo: success card, "See Leeds on the map", show the Community report badge and the photo.

**5:30-6:15 Insights and Learn.** (Mention the CSV download and the tick-check checklist.) Insights: regions, trend toggle, seasonality, ranking with explanations. Learn: species guide, seasonal chart for London, prevention and removal steps.

**6:15-7:45 Behind the scenes.** Terminal 1: `FAIL_RATE=0.6 uvicorn scripts.mock_upstream:app --port 9000`. Terminal 2: start the app against it and show retry logs. In /docs: GET /data-quality and /quarantine (nine reasons), POST /sync twice (0 inserted). Stop the fake API, POST /sync: degraded, snapshot, and the header pill says Offline mode.

**7:45-8:30 Quality.** `pytest -q` (42 passed). Mention the bug the browser test found (a thread-safety issue) and the regression test. README architecture diagram.

**8:30-9:00 Close.** Limitations (city-level, unmoderated reports, SQLite) and next steps (PostGIS, auth and moderation, calibrated model). Restate your name. Stop.
