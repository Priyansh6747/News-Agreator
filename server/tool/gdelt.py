from __future__ import annotations

import html
import json
from datetime import UTC, datetime, timedelta
from time import monotonic
from urllib.parse import urlencode

from Core.errors import BackendCoolingDown, BackendRateLimited, HttpError
from Core.models import Backend, QueryPlan, RawItem, SearchResult
from Core.ports import Clock
from Core.registry import SourceRegistry
from Core.settings import Settings
from Core.urls import canonical_url, domain_of
from tool.http import HttpClient
from tool.items import dedupe_items

GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
SEENDATE_FORMAT = "%Y%m%dT%H%M%SZ"


def build_query_url(
    query: str,
    *,
    max_records: int = 250,
    timespan: str = "24h",
) -> str:
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": max_records,
        "format": "json",
        "sort": "date",
        "timespan": timespan,
    }
    return f"{GDELT_DOC}?{urlencode(params)}"


def _timespan(hours: int) -> str:
    if hours <= 24:
        return "24h"
    if hours <= 72:
        return "3d"
    return "7d"


def _parse_seendate(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, SEENDATE_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


class GdeltBackend:
    name = Backend.GDELT

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
        self._cooldown_until = 0.0

    async def search(self, plan: QueryPlan, *, limit: int) -> SearchResult:
        if monotonic() < self._cooldown_until:
            raise BackendCoolingDown(self.name.value)

        query = (
            f'"{plan.normalized}" sourcelang:eng'
            if plan.language == "en"
            else plan.normalized
        )
        url = build_query_url(
            query,
            max_records=self._settings.gdelt_max_records,
            timespan=_timespan(plan.freshness_hours),
        )
        response = await self._http.get(url, timeout_s=self._settings.gdelt_timeout_s)
        if response.status == 429:
            self._cooldown_until = monotonic() + self._settings.gdelt_cooldown_s
            raise BackendRateLimited(self.name.value)
        if response.status >= 400:
            raise HttpError(url, f"HTTP {response.status}")

        try:
            payload = json.loads(response.body)
        except json.JSONDecodeError as error:
            raise HttpError(url, "invalid JSON") from error
        records = payload.get("articles", []) if isinstance(payload, dict) else []
        now = self._clock.now()
        future_limit = now + timedelta(hours=self._settings.future_date_tolerance_h)
        drops: dict[str, int] = {}
        items: list[RawItem] = []

        for record in records:
            title = html.unescape(str(record.get("title") or "")).strip()
            link = str(record.get("url") or "").strip()
            if not title:
                drops["title"] = drops.get("title", 0) + 1
                continue
            if not link:
                drops["link"] = drops.get("link", 0) + 1
                continue
            language = str(record.get("language") or "")
            if plan.language == "en" and language and not language.lower().startswith("english"):
                drops["language"] = drops.get("language", 0) + 1
                continue
            published_at = _parse_seendate(record.get("seendate"))
            if published_at is None:
                drops["undated"] = drops.get("undated", 0) + 1
                continue
            if published_at > future_limit:
                drops["future_date"] = drops.get("future_date", 0) + 1
                continue
            domain = str(record.get("domain") or domain_of(link))
            items.append(
                RawItem(
                    title=title,
                    url=canonical_url(link),
                    publisher=self._registry.publisher_for(domain) or domain or None,
                    snippet=None,
                    published_at=published_at,
                    backend=self.name,
                )
            )

        deduped, duplicates = dedupe_items(items)
        if duplicates:
            drops["duplicate"] = drops.get("duplicate", 0) + duplicates
        if len(deduped) > limit:
            drops["cap"] = drops.get("cap", 0) + (len(deduped) - limit)
            deduped = deduped[:limit]
        return SearchResult(items=deduped, raw_count=len(records), drops=drops)
