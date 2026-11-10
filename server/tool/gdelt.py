from __future__ import annotations

import html
import json
from datetime import UTC, datetime, timedelta
from time import monotonic
from urllib.parse import urlencode

from Core.errors import BackendCoolingDown, BackendRateLimited, HttpError
from Core.items import select_with_context
from Core.models import Backend, QueryPlan, RawItem, SearchResult
from Core.ports import Clock
from Core.registry import SourceRegistry
from Core.settings import Settings
from Core.urls import canonical_url, domain_of
from tool.http import HttpClient
from tool.items import dedupe_items

GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
SEENDATE_FORMAT = "%Y%m%dT%H%M%SZ"
QUERY_DATETIME_FORMAT = "%Y%m%d%H%M%S"


def build_query_url(
    query: str,
    *,
    max_records: int = 250,
    start: datetime,
    end: datetime,
) -> str:
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": max_records,
        "format": "json",
        "sort": "date",
        "startdatetime": start.strftime(QUERY_DATETIME_FORMAT),
        "enddatetime": end.strftime(QUERY_DATETIME_FORMAT),
    }
    return f"{GDELT_DOC}?{urlencode(params)}"


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
        now = self._clock.now()
        oldest = now - timedelta(hours=plan.lookback)
        window = timedelta(days=max(1, self._settings.gdelt_window_days))
        future_limit = now + timedelta(hours=self._settings.future_date_tolerance_h)
        drops: dict[str, int] = {}
        items: list[RawItem] = []
        errors: list[str] = []
        raw_count = 0

        end = now
        for _ in range(max(1, self._settings.gdelt_max_requests)):
            start = max(oldest, end - window)
            if start >= end:
                break
            url = build_query_url(
                query,
                max_records=self._settings.gdelt_max_records,
                start=start,
                end=end,
            )
            try:
                response = await self._http.get(
                    url, timeout_s=self._settings.gdelt_timeout_s
                )
            except Exception as error:
                if not items:
                    raise
                errors.append(type(error).__name__)
                break
            if response.status == 429:
                self._cooldown_until = monotonic() + self._settings.gdelt_cooldown_s
                if not items:
                    raise BackendRateLimited(self.name.value)
                errors.append("rate limited")
                break
            if response.status >= 400:
                if not items:
                    raise HttpError(url, f"HTTP {response.status}")
                errors.append(f"HTTP {response.status}")
                break
            try:
                payload = json.loads(response.body)
            except json.JSONDecodeError as error:
                if not items:
                    raise HttpError(url, "invalid JSON") from error
                errors.append("invalid JSON")
                break
            records = payload.get("articles", []) if isinstance(payload, dict) else []
            raw_count += len(records)

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
                if (
                    plan.language == "en"
                    and language
                    and not language.lower().startswith("english")
                ):
                    drops["language"] = drops.get("language", 0) + 1
                    continue
                published_at = _parse_seendate(record.get("seendate"))
                if published_at is None:
                    drops["undated"] = drops.get("undated", 0) + 1
                    continue
                if published_at > future_limit:
                    drops["future_date"] = drops.get("future_date", 0) + 1
                    continue
                if published_at < oldest:
                    drops["too_old"] = drops.get("too_old", 0) + 1
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
            end = start

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
