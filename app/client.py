"""Resilient HTTP client for the upstream Elanco API.

Failure handling:
  * hard timeouts on every request
  * retries with exponential backoff + jitter for timeouts, connection errors, 5xx and 429
  * honours Retry-After on 429/503
  * 4xx (other than 429) fail fast: retrying a bad request cannot help
  * malformed / truncated JSON counts as a retryable failure
  * supports both a bare JSON list (what the API returns today) and wrapped / paginated
    shapes ({"items": [...], "next": "..."}), so a future API change does not break ingestion
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Awaitable, Callable

import httpx

log = logging.getLogger("tick.client")

_LIST_KEYS = ("items", "data", "results", "sightings", "tick_sightings")
_NEXT_KEYS = ("next", "next_url", "next_page")
MAX_PAGES = 1000  # safety valve against a server that always returns a "next" link


class UpstreamError(Exception):
    """The upstream API could not give us usable data (after retries)."""


class _Retryable(Exception):
    def __init__(self, msg: str, retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


def _retry_after(resp: httpx.Response) -> float | None:
    val = resp.headers.get("retry-after")
    try:
        return max(0.0, float(val)) if val else None
    except ValueError:
        return None


class TickApiClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 20.0,
        max_retries: int = 5,
        backoff_base_s: float = 0.5,
        backoff_max_s: float = 8.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max(1, max_retries)
        self.backoff_base_s, self.backoff_max_s = backoff_base_s, backoff_max_s
        self._sleep = sleep
        self._http = httpx.AsyncClient(timeout=timeout_s, transport=transport, headers={"Accept": "application/json"})

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get_once(self, url: str) -> Any:
        try:
            resp = await self._http.get(url)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise _Retryable(f"{type(e).__name__}: {e}") from e
        if resp.status_code == 429 or resp.status_code >= 500:
            raise _Retryable(f"HTTP {resp.status_code}", _retry_after(resp))
        if resp.status_code >= 400:
            raise UpstreamError(f"HTTP {resp.status_code} from {url} (not retryable)")
        try:
            return resp.json()
        except ValueError as e:
            raise _Retryable("response was not valid JSON (possibly truncated)") from e

    async def get_json(self, url: str) -> Any:
        last: _Retryable | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return await self._get_once(url)
            except _Retryable as e:
                last = e
                if attempt == self.max_retries:
                    break
                delay = min(self.backoff_max_s, self.backoff_base_s * 2 ** (attempt - 1))
                delay = e.retry_after if e.retry_after is not None else delay * random.uniform(0.5, 1.0)
                log.warning("GET %s failed (%s) attempt %d/%d - retrying in %.2fs", url, e, attempt, self.max_retries, delay)
                await self._sleep(delay)
        raise UpstreamError(f"GET {url} failed after {self.max_retries} attempts: {last}")

    async def fetch_all_sightings(self) -> list[Any]:
        url: str | None = f"{self.base_url}/tick-sightings"
        items: list[Any] = []
        for _ in range(MAX_PAGES):
            payload = await self.get_json(url)
            nxt = None
            if isinstance(payload, list):
                items.extend(payload)
            elif isinstance(payload, dict):
                page = next((payload[k] for k in _LIST_KEYS if isinstance(payload.get(k), list)), None)
                if page is None:
                    raise UpstreamError("payload is an object without a recognisable list of sightings")
                items.extend(page)
                nxt = next((payload[k] for k in _NEXT_KEYS if payload.get(k)), None)
            else:
                raise UpstreamError(f"unexpected payload type: {type(payload).__name__}")
            if not nxt:
                return items
            url = nxt if str(nxt).startswith("http") else f"{self.base_url}{nxt}"
        raise UpstreamError("pagination did not terminate")

    async def fetch_reported_total(self) -> int | None:
        """Best effort: the API's own claim of how many sightings exist (completeness check)."""
        try:
            data = await self.get_json(f"{self.base_url}/stats")
            total = data.get("total_sightings") if isinstance(data, dict) else None
            return int(total) if total is not None else None
        except Exception:  # noqa: BLE001 - purely advisory
            return None
