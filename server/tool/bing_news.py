from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit

from Core.errors import BackendRateLimited, FeedParseError, HttpError
from Core.models import Backend, QueryPlan, SearchResult
from Core.ports import Clock
from Core.registry import SourceRegistry
from Core.settings import Settings
from Core.urls import canonical_url, domain_of
from tool.http import HttpClient
from tool.items import dedupe_items
from tool.rss import parse_feed

BING_NEWS_RSS = "https://www.bing.com/news/search"


def build_query_url(query: str, *, count: int = 20) -> str:
    params = {"q": query, "format": "rss", "count": count}
    return f"{BING_NEWS_RSS}?{urlencode(params)}"


def decode_redirect(url: str) -> str | None:
    parts = urlsplit(url)
    if "bing.com" not in (parts.hostname or ""):
        return None
    target = parse_qs(parts.query).get("url")
    if not target:
        return None
    candidate = target[0]
    target_parts = urlsplit(candidate)
    if target_parts.scheme not in {"http", "https"} or not target_parts.netloc:
        return None
    return candidate


class BingNewsBackend:
    name = Backend.BING_NEWS

    def __init__(
        self,
        http: HttpClient,
        settings: Settings,
        registry: SourceRegistry,
        clock: Clock,
    ):
        self._http = http
        self._settings = settings
        self._registry = registry
        self._clock = clock

    def _queries(self, plan: QueryPlan) -> list[str]:
        queries = plan.phrasings[: self._settings.bing_news_max_queries]
        return queries or [plan.normalized]

    async def search(self, plan: QueryPlan, *, limit: int) -> SearchResult:
        queries = self._queries(plan)
        now = self._clock.now()
        items = []
        raw_count = 0
        drops: dict[str, int] = {}
        errors: list[str] = []
        failures = 0

        for phrase in queries:
            try:
                response = await self._http.get(build_query_url(phrase))
            except Exception as error:  # noqa: BLE001
                failures += 1
                errors.append(f"{phrase}: {type(error).__name__}")
                continue
            if response.status == 429:
                failures += 1
                errors.append(f"{phrase}: rate limited")
                continue
            if response.status >= 400:
                failures += 1
                errors.append(f"{phrase}: HTTP {response.status}")
                continue
            try:
                parsed = parse_feed(
                    response.body,
                    backend=self.name,
                    max_items=self._settings.bing_news_item_cap,
                    now=now,
                    future_tolerance_h=self._settings.future_date_tolerance_h,
                )
            except FeedParseError:
                failures += 1
                errors.append(f"{phrase}: parse error")
                continue
            raw_count += parsed.raw_count
            for reason, count in parsed.drops.items():
                drops[reason] = drops.get(reason, 0) + count
            for item in parsed.items:
                domain = domain_of(item.url)
                if "bing.com" in domain:
                    target = decode_redirect(item.url)
                    if target is None:
                        drops["link"] = drops.get("link", 0) + 1
                        continue
                    item.url = canonical_url(target)
                    domain = domain_of(target)
                item.publisher = item.publisher or self._registry.publisher_for(domain)
                item.needs_resolution = False
                items.append(item)

        if failures == len(queries):
            if any("rate limited" in error for error in errors):
                raise BackendRateLimited(self.name.value)
            raise HttpError(BING_NEWS_RSS, "all queries failed")

        deduped, duplicates = dedupe_items(items)
        if duplicates:
            drops["duplicate"] = drops.get("duplicate", 0) + duplicates
        if len(deduped) > limit:
            drops["cap"] = drops.get("cap", 0) + (len(deduped) - limit)
            deduped = deduped[:limit]
        return SearchResult(
            items=deduped,
            raw_count=raw_count,
            drops=drops,
            detail="; ".join(errors) or None,
        )
