from __future__ import annotations

import pytest

from Core.errors import FetchBlocked, HttpError, HttpTimeout
from Core.registry import SourceRegistry
from Core.settings import Settings
from tool.article_fetch import HtmlArticleFetcher
from tool.http import HttpResponse


class FakeHttp:
    def __init__(self, response: HttpResponse | None = None, error: BaseException | None = None):
        self.response = response
        self.error = error
        self.calls: list[str] = []

    async def get(self, url: str, *, timeout_s: float | None = None) -> HttpResponse:
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return self.response


class FakeRobots:
    def __init__(self, allowed: bool = True):
        self._allowed = allowed

    async def allowed(self, url: str) -> bool:
        return self._allowed


def response(
    *,
    status: int = 200,
    content_type: str = "text/html; charset=utf-8",
    body: bytes = b"<html><body><article>Gold prices rose.</article></body></html>",
    url: str = "https://www.bbc.com/news/gold",
) -> HttpResponse:
    return HttpResponse(
        url=url,
        status=status,
        headers={"content-type": content_type},
        body=body,
    )


def fetcher(settings, registry, http, robots=None) -> HtmlArticleFetcher:
    return HtmlArticleFetcher(http, registry, settings, robots or FakeRobots())


async def test_fetches_html_page(settings: Settings, registry: SourceRegistry) -> None:
    http = FakeHttp(response())
    page = await fetcher(settings, registry, http).fetch(
        "https://www.bbc.com/news/gold"
    )
    assert page.status == 200
    assert "Gold prices" in page.html
    assert page.final_url == "https://www.bbc.com/news/gold"


async def test_policy_skip_does_not_fetch(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    http = FakeHttp(response())
    with pytest.raises(FetchBlocked):
        await fetcher(settings, registry, http).fetch(
            "https://www.reuters.com/markets/gold"
        )
    assert http.calls == []


async def test_robots_disallow_does_not_fetch(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    http = FakeHttp(response())
    with pytest.raises(FetchBlocked):
        await fetcher(settings, registry, http, FakeRobots(False)).fetch(
            "https://www.bbc.com/news/gold"
        )
    assert http.calls == []


async def test_403_is_blocked(settings: Settings, registry: SourceRegistry) -> None:
    http = FakeHttp(response(status=403))
    with pytest.raises(FetchBlocked):
        await fetcher(settings, registry, http).fetch("https://www.bbc.com/news/gold")


async def test_500_is_http_error(settings: Settings, registry: SourceRegistry) -> None:
    http = FakeHttp(response(status=500))
    with pytest.raises(HttpError):
        await fetcher(settings, registry, http).fetch("https://www.bbc.com/news/gold")


async def test_unsupported_content_type_is_blocked(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    http = FakeHttp(response(content_type="application/pdf"))
    with pytest.raises(FetchBlocked):
        await fetcher(settings, registry, http).fetch("https://www.bbc.com/news/gold")


async def test_timeout_propagates(settings: Settings, registry: SourceRegistry) -> None:
    http = FakeHttp(error=HttpTimeout("https://www.bbc.com/news/gold"))
    with pytest.raises(HttpTimeout):
        await fetcher(settings, registry, http).fetch("https://www.bbc.com/news/gold")
