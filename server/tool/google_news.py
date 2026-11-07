from __future__ import annotations

from urllib.parse import urlencode

from Core.errors import BackendRateLimited, FeedParseError, HttpError
from Core.models import Backend, QueryPlan, SearchResult
from Core.ports import Clock
from Core.settings import Settings
from tool.http import HttpClient
from tool.items import dedupe_items
from tool.rss import parse_feed

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


def build_query_url(
    phrase: str,
    *,
    hl: str = "en-US",
    gl: str = "US",
    ceid: str = "US:en",
) -> str:
    query = urlencode({"q": phrase, "hl": hl, "gl": gl, "ceid": ceid})
    return f"{GOOGLE_NEWS_RSS}?{query}"


class GoogleNewsBackend:
    name = Backend.GOOGLE_NEWS

    def __init__(self, http: HttpClient, settings: Settings, clock: Clock):
        self._http = http
        self._settings = settings
        self._clock = clock

    def _queries(self, plan: QueryPlan) -> list[str]:
        queries = [*plan.phrasings[:2], *plan.site_scoped[:2]]
        return queries[: self._settings.google_news_max_queries] or [plan.normalized]

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
                    max_items=self._settings.google_news_item_cap,
                    now=now,
                    future_tolerance_h=self._settings.future_date_tolerance_h,
                    needs_resolution=True,
                )
            except FeedParseError:
                failures += 1
                errors.append(f"{phrase}: parse error")
                continue
            raw_count += parsed.raw_count
            for reason, count in parsed.drops.items():
                drops[reason] = drops.get(reason, 0) + count
            for item in parsed.items:
                item.snippet = None
            items.extend(parsed.items)

        if failures == len(queries):
            if any("rate limited" in error for error in errors):
                raise BackendRateLimited(self.name.value)
            raise HttpError(GOOGLE_NEWS_RSS, "all queries failed")

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
