from __future__ import annotations

import asyncio
import re

from Core.errors import FeedParseError, HttpError
from Core.models import Backend, QueryPlan, RawItem, SearchResult
from Core.ports import Clock
from Core.registry import Feed, SourceRegistry
from Core.settings import Settings
from tool.http import HttpClient
from tool.items import dedupe_items
from tool.rss import parse_feed


class PublisherRssBackend:
    name = Backend.PUBLISHER_RSS

    def __init__(
        self,
        http: HttpClient,
        registry: SourceRegistry,
        settings: Settings,
        clock: Clock,
    ):
        self._http = http
        self._registry = registry
        self._settings = settings
        self._clock = clock

    def _tokens(self, query: str) -> set[str]:
        stopwords = set(self._settings.publisher_feed_stopwords)
        return {
            word
            for word in re.findall(r"[a-z0-9]+", query.lower())
            if len(word) > 2 and word not in stopwords
        }

    async def _fetch_feed(
        self,
        feed: Feed,
        now,
        semaphore: asyncio.Semaphore,
    ) -> tuple[Feed, SearchResult | None, str | None]:
        async with semaphore:
            try:
                response = await self._http.get(feed.url)
            except Exception as error:  # noqa: BLE001
                return feed, None, f"{feed.publisher}: {type(error).__name__}"
            if response.status >= 400:
                return feed, None, f"{feed.publisher}: HTTP {response.status}"
            try:
                parsed = parse_feed(
                    response.body,
                    backend=self.name,
                    max_items=self._settings.publisher_feed_item_cap,
                    now=now,
                    future_tolerance_h=self._settings.future_date_tolerance_h,
                    default_publisher=feed.publisher,
                    publisher_domain=feed.domain,
                )
            except FeedParseError:
                return feed, None, f"{feed.publisher}: parse error"
            return feed, parsed, None

    async def search(self, plan: QueryPlan, *, limit: int) -> SearchResult:
        feeds = self._registry.feeds()
        if not feeds:
            return SearchResult()

        now = self._clock.now()
        semaphore = asyncio.Semaphore(self._settings.fetch_concurrency)
        results = await asyncio.gather(
            *(self._fetch_feed(feed, now, semaphore) for feed in feeds)
        )

        tokens = self._tokens(plan.normalized)
        items: list[RawItem] = []
        raw_count = 0
        drops: dict[str, int] = {}
        errors: list[str] = []

        for feed, parsed, error in results:
            if error is not None or parsed is None:
                errors.append(error or f"{feed.publisher}: unknown error")
                continue
            raw_count += parsed.raw_count
            for reason, count in parsed.drops.items():
                drops[reason] = drops.get(reason, 0) + count
            for item in parsed.items:
                text = f"{item.title} {item.snippet or ''}".lower()
                if tokens and not any(token in text for token in tokens):
                    drops["irrelevant"] = drops.get("irrelevant", 0) + 1
                    continue
                items.append(item)

        if not items and errors and len(errors) == len(feeds):
            raise HttpError(feeds[0].url, "all publisher feeds failed")

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
