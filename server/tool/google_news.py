from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlencode

from Core.errors import BackendRateLimited, FeedParseError, HttpError
from Core.items import select_with_context
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
    when: str | None = None,
    hl: str = "en-US",
    gl: str = "US",
    ceid: str = "US:en",
) -> str:
    scoped = f"{phrase} when:{when}" if when else phrase
    query = urlencode({"q": scoped, "hl": hl, "gl": gl, "ceid": ceid})
    return f"{GOOGLE_NEWS_RSS}?{query}"


def _when(hours: int) -> str:
    if hours <= 24:
        return "1d"
    if hours <= 48:
        return "2d"
    if hours <= 72:
        return "3d"
    if hours <= 168:
        return "7d"
    if hours <= 336:
        return "14d"
    return "30d"


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
        window = _when(plan.lookback)
        oldest = now - timedelta(hours=plan.lookback)
        items = []
        raw_count = 0
        drops: dict[str, int] = {}
        errors: list[str] = []
        failures = 0

        for phrase in queries:
            try:
                response = await self._http.get(build_query_url(phrase, when=window))
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
                    oldest=oldest,
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
        selected = select_with_context(
            deduped,
            limit=limit,
            now=now,
            freshness_hours=plan.freshness_hours,
            context_share=self._settings.context_candidate_share,
        )
        if len(selected) < len(deduped):
            drops["cap"] = drops.get("cap", 0) + (len(deduped) - len(selected))
        return SearchResult(
            items=selected,
            raw_count=raw_count,
            drops=drops,
            detail="; ".join(errors) or None,
        )
