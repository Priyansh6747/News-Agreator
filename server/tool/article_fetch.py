from __future__ import annotations

from Core.errors import FetchBlocked, HttpError
from Core.models import FetchedPage
from Core.registry import SourceRegistry
from Core.settings import Settings
from Core.urls import domain_of
from tool.http import HttpClient
from tool.robots import RobotsCache


class HtmlArticleFetcher:
    def __init__(
        self,
        http: HttpClient,
        registry: SourceRegistry,
        settings: Settings,
        robots: RobotsCache | None = None,
    ):
        self._http = http
        self._registry = registry
        self._settings = settings
        self._robots = robots or RobotsCache(http, settings)

    async def fetch(self, url: str) -> FetchedPage:
        domain = domain_of(url)
        policy = self._registry.fetch_policy(domain)
        if policy.mode != "fetch":
            raise FetchBlocked(url, policy.reason or policy.mode)
        if not await self._robots.allowed(url):
            raise FetchBlocked(url, "robots.txt disallows this path")

        response = await self._http.get(url, timeout_s=self._settings.fetch_timeout_s)
        if response.status in {401, 403, 451, 429}:
            raise FetchBlocked(url, f"HTTP {response.status}")
        if response.status >= 400:
            raise HttpError(url, f"HTTP {response.status}")
        if not response.body:
            raise FetchBlocked(url, "empty response body")

        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and not content_type.startswith("text/"):
            raise FetchBlocked(url, f"unsupported content-type {content_type or 'unknown'}")

        return FetchedPage(
            url=url,
            final_url=response.url,
            status=response.status,
            content_type=content_type,
            html=response.body.decode("utf-8", errors="ignore"),
            elapsed_ms=response.elapsed_ms,
        )
