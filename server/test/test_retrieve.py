from __future__ import annotations

from datetime import timedelta

from Core.coverage import CoverageCollector
from Core.errors import BackendNotConfigured, BackendTimeout
from Core.models import Attempt, Backend, QueryPlan, RawItem, SearchResult
from Core.registry import SourceRegistry
from Core.retrieve import retrieve_candidates
from Core.settings import Settings
from test.helpers import NOW


class StubBackend:
    def __init__(
        self,
        name: Backend,
        items: list[RawItem],
        error: BaseException | None = None,
    ):
        self.name = name
        self._items = items
        self._error = error

    async def search(self, plan: QueryPlan, *, limit: int) -> SearchResult:
        if self._error is not None:
            raise self._error
        items = self._items[:limit]
        return SearchResult(items=items, raw_count=len(items))


def raw(
    *,
    title: str,
    url: str,
    backend: Backend,
    publisher: str | None = None,
    snippet: str | None = None,
    needs_resolution: bool = False,
) -> RawItem:
    return RawItem(
        title=title,
        url=url,
        publisher=publisher,
        snippet=snippet,
        published_at=NOW - timedelta(hours=1),
        backend=backend,
        needs_resolution=needs_resolution,
    )


def plan() -> QueryPlan:
    return QueryPlan(query="gold prices", normalized="gold prices")


async def test_merges_duplicate_titles_and_keeps_snippet(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    google = raw(
        title="Gold rises",
        url="https://news.google.com/rss/articles/abc",
        publisher="Reuters",
        backend=Backend.GOOGLE_NEWS,
        needs_resolution=True,
    )
    bing = raw(
        title="Gold rises",
        url="https://www.cnbc.com/gold-rises",
        backend=Backend.BING_NEWS,
        snippet="Gold rose in early trade.",
    )
    coverage = CoverageCollector()
    candidates = await retrieve_candidates(
        plan(),
        backends=[
            StubBackend(Backend.GOOGLE_NEWS, [google]),
            StubBackend(Backend.BING_NEWS, [bing]),
        ],
        registry=registry,
        settings=settings,
        coverage=coverage,
    )
    assert len(candidates) == 1
    assert candidates[0].backend is Backend.BING_NEWS
    assert candidates[0].snippet == "Gold rose in early trade."
    report = coverage.finish()
    assert report.drops["duplicate"] == 1
    assert report.status.value == "complete"


async def test_backend_failure_is_isolated(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    bing = raw(
        title="Gold rises",
        url="https://www.cnbc.com/gold-rises",
        backend=Backend.BING_NEWS,
    )
    coverage = CoverageCollector()
    candidates = await retrieve_candidates(
        plan(),
        backends=[
            StubBackend(
                Backend.GOOGLE_NEWS,
                [],
                error=BackendNotConfigured("google_news"),
            ),
            StubBackend(Backend.BING_NEWS, [bing]),
        ],
        registry=registry,
        settings=settings,
        coverage=coverage,
    )
    assert len(candidates) == 1
    report = coverage.finish()
    assert report.attempts[0].attempt is Attempt.NOT_STARTED
    assert report.attempts[1].attempt is Attempt.COMPLETED
    assert report.status.value == "partial"


async def test_timeout_attempt_and_invalid_link(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    bad = raw(
        title="Bad link",
        url="javascript:alert(1)",
        backend=Backend.GDELT,
    )
    coverage = CoverageCollector()
    candidates = await retrieve_candidates(
        plan(),
        backends=[
            StubBackend(Backend.GDELT, [bad], error=BackendTimeout("gdelt")),
        ],
        registry=registry,
        settings=settings,
        coverage=coverage,
    )
    assert candidates == []
    report = coverage.finish()
    assert report.attempts[0].attempt is Attempt.DIRECT_TIMEOUT
    assert report.status.value == "unavailable"


async def test_invalid_url_is_dropped(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    bad = raw(title="Bad link", url="ftp://example.com/x", backend=Backend.BING_NEWS)
    coverage = CoverageCollector()
    candidates = await retrieve_candidates(
        plan(),
        backends=[StubBackend(Backend.BING_NEWS, [bad])],
        registry=registry,
        settings=settings,
        coverage=coverage,
    )
    assert candidates == []
    assert coverage.finish().drops["link"] == 1


async def test_resolution_candidates_use_publisher_tier(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    google = raw(
        title="Gold rises",
        url="https://news.google.com/rss/articles/abc",
        publisher="Reuters",
        backend=Backend.GOOGLE_NEWS,
        needs_resolution=True,
    )
    coverage = CoverageCollector()
    candidates = await retrieve_candidates(
        plan(),
        backends=[StubBackend(Backend.GOOGLE_NEWS, [google])],
        registry=registry,
        settings=settings,
        coverage=coverage,
    )
    assert candidates[0].tier.value == "T1"
    assert candidates[0].family == "reuters"
    assert candidates[0].needs_resolution is True
