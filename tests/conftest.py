import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.client import TickApiClient
from app.config import Settings
from app.main import create_app
from tests.factories import clean_payload, messy_payload


class FakeUpstream:
    """Scriptable stand-in for the Elanco API."""

    def __init__(self, payload):
        self.payload, self.script, self.calls = payload, [], 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, Exception):
                raise step
            if step is not None:
                return step
        if request.url.path.endswith("/stats"):
            return httpx.Response(200, json={"api_version": "1.0.0", "total_sightings": len(self.payload)})
        return httpx.Response(200, json=self.payload)


async def _nosleep(_):
    return None


def make_client(upstream: FakeUpstream, retries=3) -> TickApiClient:
    return TickApiClient("https://fake/data", max_retries=retries, transport=httpx.MockTransport(upstream.handler), sleep=_nosleep)


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "t.db"), snapshot_path=str(tmp_path / "snap.json"), uploads_dir=str(tmp_path / "up"),
                    max_retries=3, max_upload_mb=1, reports_per_minute=50)


@pytest.fixture
def upstream():
    return FakeUpstream(clean_payload())


@pytest.fixture
def api(settings, upstream):
    app = create_app(settings, client_factory=lambda: make_client(upstream))
    with TestClient(app) as c:
        c.upstream = upstream
        yield c


@pytest.fixture
def messy_api(settings):
    up = FakeUpstream(messy_payload())
    app = create_app(settings, client_factory=lambda: make_client(up))
    with TestClient(app) as c:
        c.upstream = up
        yield c
