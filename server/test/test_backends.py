from __future__ import annotations

import json

import httpx
import pytest

from Core.errors import BackendCoolingDown, BackendRateLimited, HttpError
from Core.models import QueryPlan
from Core.registry import Feed, SourceRegistry
from Core.settings import Settings
from test.helpers import NOW
from tool.bing_news import BingNewsBackend
from tool.fixture_adapters import StaticClock
from tool.gdelt import GdeltBackend
from tool.google_news import GoogleNewsBackend
from tool.http import HttpClient
from tool.publisher_rss import PublisherRssBackend


def settings(**overrides) -> Settings:
    defaults = {
        "app_env": "dev",
        "per_domain_min_spacing_s": 0.0,
        "query_cache_ttl_s": 0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def http(handler, config: Settings) -> HttpClient:
    return HttpClient(config, transport=httpx.MockTransport(handler))


def fixture(name: str) -> bytes:
    from pathlib import Path

    return (Path(__file__).resolve().parent / "fixtures" / name).read_bytes()


def plan(**overrides) -> QueryPlan:
    defaults = {
        "query": "gold prices",
        "normalized": "gold prices",
        "freshness_hours": 24,
        "phrasings": ["gold prices", "gold prices price today", "gold prices market analysis"],
        "site_scoped": [
            "gold prices site:reuters.com",
            "gold prices site:apnews.com",
            "gold prices site:afp.com",
        ],
    }
    defaults.update(overrides)
    return QueryPlan(**defaults)


async def test_google_news_queries_and_text_policy() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, content=fixture("google_news.xml"))

    config = settings(google_news_max_queries=4)
    client = http(handler, config)
    backend = GoogleNewsBackend(client, config, StaticClock(NOW))
    result = await backend.search(plan(), limit=20)
    assert calls["count"] == 4
    assert len(result.items) == 2
    assert {item.publisher for item in result.items} == {"Reuters", "BBC News"}
    assert all(item.snippet is None for item in result.items)
    assert all(item.needs_resolution for item in result.items)
    await client.aclose()


async def test_bing_decodes_redirects_and_keeps_snippets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture("bing_news.xml"))

    config = settings(bing_news_max_queries=2)
    client = http(handler, config)
    backend = BingNewsBackend(client, config, SourceRegistry.load(), StaticClock(NOW))
    result = await backend.search(plan(), limit=20)
    assert len(result.items) == 1
    item = result.items[0]
    assert item.url == "https://cnbc.com/2026/11/06/gold-price-forecast.html"
    assert item.publisher == "CNBC"
    assert item.snippet
    assert item.needs_resolution is False
    assert result.drops["duplicate"] == 1
    await client.aclose()


def gdelt_payload() -> bytes:
    return json.dumps(
        {
            "articles": [
                {
                    "title": "Gold rises to a two-week high",
                    "url": "https://www.cnbc.com/2026/11/06/gold-rises.html",
                    "seendate": "20261106T090000Z",
                    "domain": "cnbc.com",
                    "language": "English",
                },
                {
                    "title": "Oro sube tras caida del dollar",
                    "url": "https://www.elpais.com/economia/oro.html",
                    "seendate": "20261106T080000Z",
                    "domain": "elpais.com",
                    "language": "Spanish",
                },
                {
                    "title": "Gold record without a date",
                    "url": "https://www.bbc.com/news/gold",
                    "domain": "bbc.com",
                    "language": "English",
                },
            ]
        }
    ).encode()


async def test_gdelt_filters_language_and_undated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=gdelt_payload())

    config = settings()
    client = http(handler, config)
    backend = GdeltBackend(client, config, SourceRegistry.load(), StaticClock(NOW))
    result = await backend.search(plan(), limit=20)
    assert len(result.items) == 1
    assert result.items[0].publisher == "CNBC"
    assert result.items[0].snippet is None
    assert result.drops == {"language": 1, "undated": 1}
    await client.aclose()


async def test_gdelt_429_sets_cooldown() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(429, content=b"slow down")

    config = settings(gdelt_cooldown_s=60)
    client = http(handler, config)
    backend = GdeltBackend(client, config, SourceRegistry.load(), StaticClock(NOW))
    with pytest.raises(BackendRateLimited):
        await backend.search(plan(), limit=20)
    with pytest.raises(BackendCoolingDown):
        await backend.search(plan(), limit=20)
    assert calls["count"] == 1
    await client.aclose()


def single_feed_registry() -> SourceRegistry:
    return SourceRegistry(
        sources=[],
        families=[],
        feeds=[
            Feed(
                publisher="BBC News",
                domain="bbc.com",
                url="https://feeds.bbci.co.uk/news/world/rss.xml",
                section="world",
            )
        ],
        denylist=[],
    )


async def test_publisher_rss_filters_by_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture("rss_basic.xml"))

    config = settings()
    client = http(handler, config)
    backend = PublisherRssBackend(
        client, single_feed_registry(), config, StaticClock(NOW)
    )
    result = await backend.search(plan(), limit=20)
    assert [item.title for item in result.items] == ["Gold rises & dollar slips"]
    assert result.items[0].publisher == "BBC News"
    assert result.drops["irrelevant"] == 1
    await client.aclose()


async def test_publisher_rss_all_feeds_failed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"error")

    config = settings()
    client = http(handler, config)
    backend = PublisherRssBackend(
        client, single_feed_registry(), config, StaticClock(NOW)
    )
    with pytest.raises(HttpError):
        await backend.search(plan(), limit=20)
    await client.aclose()
