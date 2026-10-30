import httpx
import pytest

from app.client import UpstreamError
from tests.conftest import FakeUpstream, make_client


async def test_retries_then_succeeds():
    up = FakeUpstream([{"id": "1"}])
    up.script = [httpx.Response(500), httpx.ConnectError("boom"), httpx.Response(503)]
    data = await make_client(up, retries=5).fetch_all_sightings()
    assert data == [{"id": "1"}] and up.calls == 4


async def test_rate_limit_honours_retry_after():
    waits = []

    async def rec(s):
        waits.append(s)

    up = FakeUpstream([{"id": "1"}])
    up.script = [httpx.Response(429, headers={"retry-after": "3"})]
    c = make_client(up)
    c._sleep = rec
    await c.fetch_all_sightings()
    assert waits == [3.0]


async def test_client_errors_fail_fast():
    up = FakeUpstream([])
    up.script = [httpx.Response(404)]
    with pytest.raises(UpstreamError, match="not retryable"):
        await make_client(up).fetch_all_sightings()
    assert up.calls == 1


async def test_truncated_json_is_retried():
    up = FakeUpstream([{"id": "1"}])
    up.script = [httpx.Response(200, content=b'[{"id": "1"')]
    assert await make_client(up).fetch_all_sightings() == [{"id": "1"}]


async def test_gives_up_after_max_retries():
    up = FakeUpstream([])
    up.script = [httpx.Response(500)] * 10
    with pytest.raises(UpstreamError, match="failed after 3 attempts"):
        await make_client(up, retries=3).fetch_all_sightings()
    assert up.calls == 3


async def test_wrapped_and_paginated_payload():
    pages = {"https://fake/data/tick-sightings": {"items": [{"id": "1"}], "next": "https://fake/data/p2"},
             "https://fake/data/p2": {"items": [{"id": "2"}], "next": None}}
    c = make_client(FakeUpstream([]))
    c._http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=pages[str(r.url)])))
    assert await c.fetch_all_sightings() == [{"id": "1"}, {"id": "2"}]


async def test_unrecognised_object_payload_rejected():
    c = make_client(FakeUpstream({"hello": "world"}))
    with pytest.raises(UpstreamError):
        await c.fetch_all_sightings()
