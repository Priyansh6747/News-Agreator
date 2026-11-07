from __future__ import annotations

import asyncio
from time import perf_counter

import httpx
import pytest

from Core.errors import HttpBodyTooLarge, HttpError, HttpTimeout
from Core.settings import Settings
from tool.http import HttpClient


def settings(**overrides) -> Settings:
    defaults = {
        "app_env": "demo",
        "per_domain_min_spacing_s": 0.0,
        "query_cache_ttl_s": 300,
        "body_cap_mb": 1.0,
        "fetch_timeout_s": 1.0,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def client(handler, config: Settings) -> HttpClient:
    return HttpClient(config, transport=httpx.MockTransport(handler))


async def test_returns_body_and_serves_cache_hit() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, content=b"<rss/>")

    http = client(handler, settings())
    first = await http.get("https://example.com/feed")
    second = await http.get("https://example.com/feed")
    assert first.status == 200
    assert first.body == b"<rss/>"
    assert first.from_cache is False
    assert second.from_cache is True
    assert calls["count"] == 1
    await http.aclose()


async def test_error_status_is_returned_and_not_cached() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404, content=b"missing")

    http = client(handler, settings())
    first = await http.get("https://example.com/feed")
    second = await http.get("https://example.com/feed")
    assert first.status == 404
    assert first.from_cache is False
    assert second.from_cache is False
    assert calls["count"] == 2
    await http.aclose()


async def test_follows_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(302, headers={"location": "/b"})
        return httpx.Response(200, content=b"final")

    http = client(handler, settings())
    response = await http.get("https://example.com/a")
    assert response.url == "https://example.com/b"
    assert response.body == b"final"
    await http.aclose()


async def test_redirect_cap_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    http = client(handler, settings(http_max_redirects=2))
    with pytest.raises(HttpError):
        await http.get("https://example.com/loop")
    await http.aclose()


async def test_body_cap_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 4096)

    http = client(handler, settings(body_cap_mb=0.001))
    with pytest.raises(HttpBodyTooLarge):
        await http.get("https://example.com/big")
    await http.aclose()


async def test_timeout_maps_to_http_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    http = client(handler, settings())
    with pytest.raises(HttpTimeout):
        await http.get("https://example.com/slow")
    await http.aclose()


async def test_per_host_spacing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    http = client(
        handler,
        settings(per_domain_min_spacing_s=0.05, query_cache_ttl_s=0),
    )
    started = perf_counter()
    await http.get("https://example.com/a")
    await http.get("https://example.com/b")
    assert perf_counter() - started >= 0.04
    await http.aclose()


async def test_single_flight_deduplicates_concurrent_requests() -> None:
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        await asyncio.sleep(0.05)
        return httpx.Response(200, content=b"once")

    http = client(handler, settings())
    first, second = await asyncio.gather(
        http.get("https://example.com/feed"),
        http.get("https://example.com/feed"),
    )
    assert calls["count"] == 1
    assert first.body == second.body == b"once"
    await http.aclose()
