from __future__ import annotations

from tool.http import HttpResponse
from tool.robots import RobotsCache


class FakeHttp:
    def __init__(self, body: bytes = b"", status: int = 200):
        self.body = body
        self.status = status
        self.calls: list[str] = []

    async def get(self, url: str, *, cache_ttl_s: int | None = None) -> HttpResponse:
        self.calls.append(url)
        return HttpResponse(url=url, status=self.status, body=self.body)


async def test_allows_and_denies_paths(settings) -> None:
    body = b"User-agent: *\nDisallow: /private\n"
    http = FakeHttp(body=body)
    robots = RobotsCache(http, settings)
    assert await robots.allowed("https://example.com/public") is True
    assert await robots.allowed("https://example.com/private/story") is False
    assert len(http.calls) == 1


async def test_missing_robots_allows_all(settings) -> None:
    http = FakeHttp(body=b"", status=404)
    robots = RobotsCache(http, settings)
    assert await robots.allowed("https://example.com/story") is True


async def test_server_error_allows_all(settings) -> None:
    http = FakeHttp(body=b"error", status=500)
    robots = RobotsCache(http, settings)
    assert await robots.allowed("https://example.com/story") is True


async def test_invalid_url_is_denied(settings) -> None:
    http = FakeHttp()
    robots = RobotsCache(http, settings)
    assert await robots.allowed("not-a-url") is False
    assert http.calls == []
