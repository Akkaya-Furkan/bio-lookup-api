"""Shared HTTP plumbing: per-host rate limit, bounded retries, uniform error mapping."""
from __future__ import annotations

import asyncio
import time

import httpx

from ..cache import MISS, NOT_FOUND, TTLCache
from ..errors import NotFoundError, UpstreamError

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER = 10.0  # never sleep longer than this for a Retry-After header
NEGATIVE_TTL = 300.0  # a 404 is cached for 5 minutes at most


class Upstream:
    def __init__(self, source: str, base_url: str, client: httpx.AsyncClient,
                 min_interval: float, retries: int = 2, cache: TTLCache | None = None):
        self.source, self.base_url, self.client = source, base_url.rstrip("/"), client
        self.min_interval, self.retries, self.cache = min_interval, retries, cache
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def _wait_turn(self) -> None:
        async with self._lock:  # serialises requests so the interval holds across concurrent callers
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

    @staticmethod
    def _retry_delay(resp: httpx.Response | None, attempt: int) -> float:
        if resp is not None:
            try:
                return min(float(resp.headers["Retry-After"]), MAX_RETRY_AFTER)
            except (KeyError, ValueError):
                pass
        return float(2 ** attempt)

    async def get_json(self, path: str, params: dict | None = None):
        url = f"{self.base_url}{path}"
        key = (url, tuple(sorted((params or {}).items())))
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is NOT_FOUND:
                raise NotFoundError(self.source, f"{self.source} has no such record")
            if hit is not MISS:
                return hit
        data = await self._fetch(url, params)
        if self.cache is not None:
            self.cache.set(key, data)
        return data

    async def _fetch(self, url: str, params: dict | None):
        last_detail, timed_out = "no response", False
        for attempt in range(self.retries + 1):
            await self._wait_turn()
            resp = None
            try:
                resp = await self.client.get(url, params=params)
            except httpx.TimeoutException:
                last_detail, timed_out = "request timed out", True
            except httpx.HTTPError as e:
                last_detail, timed_out = f"network error: {type(e).__name__}", False
            else:
                if resp.status_code == 404:
                    if self.cache is not None:
                        self.cache.set((url, tuple(sorted((params or {}).items()))), NOT_FOUND, NEGATIVE_TTL)
                    raise NotFoundError(self.source, f"{self.source} has no such record")
                if resp.status_code not in RETRY_STATUS:
                    if resp.is_success:
                        try:
                            return resp.json()
                        except ValueError:
                            raise UpstreamError(self.source, "invalid JSON in response") from None
                    raise UpstreamError(self.source, f"unexpected HTTP {resp.status_code}")
                last_detail, timed_out = f"HTTP {resp.status_code}", False
            if attempt < self.retries:
                await asyncio.sleep(self._retry_delay(resp, attempt))
        raise UpstreamError(self.source, f"{last_detail} after {self.retries + 1} attempts", timed_out)
