"""A local fake of the Elanco API that misbehaves on purpose - handy for demoing resilience.

    uvicorn scripts.mock_upstream:app --port 9000            # healthy
    FAIL_RATE=0.6 uvicorn scripts.mock_upstream:app --port 9000   # 60% of calls return 500
Then run the tracker with:  TICK_API_BASE_URL=http://127.0.0.1:9000/data
"""
import os
import random
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.factories import messy_payload  # noqa: E402

FAIL_RATE = float(os.getenv("FAIL_RATE", "0"))
DATA = messy_payload()
app = FastAPI()


def _maybe_fail():
    if random.random() < FAIL_RATE:
        raise HTTPException(500, "simulated upstream failure")


@app.get("/data/tick-sightings")
def sightings():
    _maybe_fail()
    return DATA


@app.get("/data/stats")
def stats():
    return {"api_version": "1.0.0", "total_sightings": len(DATA)}
