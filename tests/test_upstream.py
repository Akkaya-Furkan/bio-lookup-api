import asyncio

import httpx
import pytest
import respx

from bio_lookup.cache import TTLCache
from bio_lookup.clients import base
from bio_lookup.clients.base import Upstream
from bio_lookup.errors import NotFoundError, UpstreamError

URL = "https://example.test/data"


@pytest.fixture
def sleeps(monkeypatch):
    """Record backoff sleeps instead of waiting for them."""
    calls = []

    async def fake_sleep(seconds):
        calls.append(seconds)
    monkeypatch.setattr(base.asyncio, "sleep", fake_sleep)
    return calls


def run(path="/data", params=None, cache=None, retries=2, interval=0.0):
    async def go():
        async with httpx.AsyncClient() as http:
            up = Upstream("Test", "https://example.test", http, interval, retries, cache)
            return await up.get_json(path, params)
    return asyncio.run(go())


def test_returns_json():
    with respx.mock() as m:
        m.get(URL).respond(json={"a": 1})
        assert run() == {"a": 1}


def test_404_is_not_found_and_not_retried():
    with respx.mock() as m:
        route = m.get(URL).respond(404)
        with pytest.raises(NotFoundError):
            run()
        assert route.call_count == 1


def test_retries_a_503_then_succeeds(sleeps):
    with respx.mock() as m:
        route = m.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})])
        assert run() == {"ok": True}
        assert route.call_count == 2 and sleeps == [1.0]


def test_retry_after_is_honoured_but_capped(sleeps):
    with respx.mock() as m:
        m.get(URL).mock(side_effect=[httpx.Response(429, headers={"Retry-After": "3"}),
                                     httpx.Response(429, headers={"Retry-After": "999"}),
                                     httpx.Response(200, json={})])
        run()
        assert sleeps == [3.0, base.MAX_RETRY_AFTER]


def test_gives_up_with_a_502_style_error(sleeps):
    with respx.mock() as m:
        route = m.get(URL).respond(503)
        with pytest.raises(UpstreamError) as e:
            run(retries=2)
        assert route.call_count == 3 and not e.value.timeout and "HTTP 503" in e.value.detail


def test_timeouts_are_flagged_for_a_504(sleeps):
    with respx.mock() as m:
        m.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(UpstreamError) as e:
            run(retries=1)
        assert e.value.timeout


def test_network_error_is_not_a_timeout(sleeps):
    with respx.mock() as m:
        m.get(URL).mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(UpstreamError) as e:
            run(retries=0)
        assert not e.value.timeout and "ConnectError" in e.value.detail


def test_unexpected_status_is_not_retried():
    with respx.mock() as m:
        route = m.get(URL).respond(400)
        with pytest.raises(UpstreamError, match="HTTP 400"):
            run()
        assert route.call_count == 1


def test_invalid_json_is_an_upstream_error():
    with respx.mock() as m:
        m.get(URL).respond(200, content=b"<html>not json</html>")
        with pytest.raises(UpstreamError, match="invalid JSON"):
            run()


def test_requests_are_spaced_by_the_minimum_interval():
    async def go():
        async with httpx.AsyncClient() as http:
            up = Upstream("Test", "https://example.test", http, 0.05)
            loop = asyncio.get_running_loop()
            start = loop.time()
            await asyncio.gather(*(up.get_json("/data") for _ in range(3)))
            return loop.time() - start
    with respx.mock() as m:
        m.get(URL).respond(json={})
        assert asyncio.run(go()) >= 0.09  # three calls, two gaps of 50 ms


def test_success_is_cached_per_url_and_params():
    cache = TTLCache(ttl=100)
    with respx.mock() as m:
        route = m.get(URL).respond(json={"v": 1})
        assert run(params={"q": "a"}, cache=cache) == run(params={"q": "a"}, cache=cache)
        assert route.call_count == 1
        run(params={"q": "b"}, cache=cache)
        assert route.call_count == 2  # different params, different entry


def test_404_is_cached_briefly_but_failures_are_not(sleeps):
    cache = TTLCache(ttl=100)
    with respx.mock() as m:
        route = m.get(URL).respond(404)
        for _ in range(2):
            with pytest.raises(NotFoundError):
                run(cache=cache)
        assert route.call_count == 1
    cache2 = TTLCache(ttl=100)
    with respx.mock() as m:
        route = m.get(URL).respond(503)
        for _ in range(2):
            with pytest.raises(UpstreamError):
                run(cache=cache2, retries=0)
        assert route.call_count == 2  # an outage must not be remembered
