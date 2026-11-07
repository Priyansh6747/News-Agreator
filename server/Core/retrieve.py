from __future__ import annotations

import asyncio
from time import perf_counter
from urllib.parse import urlsplit

from Core.coverage import CoverageCollector
from Core.errors import (
    BackendCoolingDown,
    BackendNotConfigured,
    BackendRateLimited,
    BackendTimeout,
)
from Core.models import Attempt, Backend, Candidate, QueryPlan, RawItem, SearchResult
from Core.ports import SearchBackend
from Core.registry import SourceRegistry
from Core.settings import Settings
from Core.urls import canonical_url, domain_of, normalize_title

BACKEND_PRIORITY: dict[Backend, int] = {
    Backend.PUBLISHER_RSS: 4,
    Backend.BING_NEWS: 3,
    Backend.GOOGLE_NEWS: 2,
    Backend.GDELT: 1,
}


def _attempt_for(error: BaseException) -> Attempt:
    if isinstance(error, BackendNotConfigured):
        return Attempt.NOT_STARTED
    if isinstance(error, BackendCoolingDown):
        return Attempt.NEGATIVE_CACHE
    if isinstance(error, (BackendTimeout, TimeoutError)):
        return Attempt.DIRECT_TIMEOUT
    if isinstance(error, BackendRateLimited):
        return Attempt.OTHER_FETCH_FAILURE
    return Attempt.OTHER_FETCH_FAILURE


def _attempt_for_result(result: SearchResult) -> Attempt:
    if result.items:
        return Attempt.COMPLETED
    if result.raw_count == 0:
        return Attempt.EMPTY
    if set(result.drops) == {"undated"}:
        return Attempt.ALL_UNDATED
    if "undated" in result.drops:
        return Attempt.PARTIAL_UNDATED
    return Attempt.EMPTY


def _is_http(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _quality(item: RawItem) -> tuple[int, int, int, int]:
    return (
        int(bool(item.snippet)),
        int(bool(item.publisher)),
        int(bool(item.published_at)),
        BACKEND_PRIORITY[item.backend],
    )


def _quality_for_candidate(candidate: Candidate) -> tuple[int, int, int, int]:
    return (
        int(bool(candidate.snippet)),
        int(bool(candidate.publisher)),
        int(bool(candidate.published_at)),
        BACKEND_PRIORITY[candidate.backend],
    )


def to_candidate(item: RawItem, registry: SourceRegistry) -> Candidate:
    url = canonical_url(item.url)
    domain = domain_of(url)
    if item.needs_resolution and item.publisher:
        tier = registry.tier_for(publisher=item.publisher)
        family = registry.family_for(publisher=item.publisher)
    else:
        tier = registry.tier_for(domain=domain, publisher=item.publisher)
        family = registry.family_for(domain=domain, publisher=item.publisher)
    return Candidate(
        title=item.title,
        url=url,
        publisher=item.publisher or registry.publisher_for(domain),
        domain=domain,
        snippet=item.snippet,
        published_at=item.published_at,
        backend=item.backend,
        tier=tier,
        family=family,
        needs_resolution=item.needs_resolution,
    )


async def retrieve_candidates(
    plan: QueryPlan,
    *,
    backends: list[SearchBackend],
    registry: SourceRegistry,
    settings: Settings,
    coverage: CoverageCollector,
) -> list[Candidate]:
    started = perf_counter()
    tasks = [
        asyncio.create_task(backend.search(plan, limit=settings.candidate_cap))
        for backend in backends
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    merged: dict[str, Candidate] = {}
    for backend, result in zip(backends, results):
        elapsed_ms = int((perf_counter() - started) * 1000)
        if isinstance(result, BaseException):
            coverage.record_attempt(
                backend.name,
                _attempt_for(result),
                returned=0,
                elapsed_ms=elapsed_ms,
                detail=str(result),
            )
            continue

        for reason, count in result.drops.items():
            coverage.add_drop(reason, count, backend=backend.name)

        attempt = _attempt_for_result(result)
        coverage.record_attempt(
            backend.name,
            attempt,
            returned=len(result.items),
            elapsed_ms=elapsed_ms,
            detail=result.detail,
        )
        if not result.items:
            continue

        kept = 0
        for item in result.items:
            if not _is_http(item.url):
                coverage.add_drop("link", backend=backend.name)
                continue
            candidate = to_candidate(item, registry)
            title_key = normalize_title(candidate.title)
            keys = [f"url:{canonical_url(candidate.url)}"]
            if title_key:
                keys.append(f"title:{title_key}")
            duplicate_key = next((key for key in keys if key in merged), None)
            if duplicate_key is not None:
                existing = merged[duplicate_key]
                if _quality(item) > _quality_for_candidate(existing):
                    for stale in [key for key, value in merged.items() if value is existing]:
                        del merged[stale]
                    for key in keys:
                        merged[key] = candidate
                coverage.add_drop("duplicate", backend=backend.name)
                continue
            for key in keys:
                merged[key] = candidate
            kept += 1
        coverage.record_kept(backend.name, kept)

    candidates: list[Candidate] = []
    seen: set[int] = set()
    for candidate in merged.values():
        if id(candidate) in seen:
            continue
        seen.add(id(candidate))
        candidates.append(candidate)
    if len(candidates) > settings.candidate_cap:
        coverage.add_drop("cap", len(candidates) - settings.candidate_cap)
        candidates = candidates[: settings.candidate_cap]
    return candidates
