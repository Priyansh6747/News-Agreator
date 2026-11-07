from __future__ import annotations

from Core.cluster import cluster_candidates
from Core.coverage import CoverageCollector
from Core.enrich import enrich_clusters
from Core.errors import ExtractionFailed, FetchBlocked, HttpTimeout
from Core.models import ExtractedText, FetchedPage, TextStatus, Tier
from Core.prompts import DraftFact, ExtractedFacts
from Core.registry import SourceRegistry
from Core.settings import Settings
from test.helpers import NOW, make_candidate
from tool.decisions_heuristic import HeuristicDecisionEngine
from tool.fixture_adapters import StaticClock


class FakeResolver:
    def __init__(self, resolved: str | None = None):
        self.resolved = resolved
        self.calls: list[str] = []

    async def resolve(self, url: str) -> str | None:
        self.calls.append(url)
        return self.resolved or url


class FakeFetcher:
    def __init__(self, page: FetchedPage | None = None, error: BaseException | None = None):
        self.page = page
        self.error = error
        self.calls: list[str] = []

    async def fetch(self, url: str) -> FetchedPage:
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return self.page


class FakeExtractor:
    def __init__(
        self,
        extracted: ExtractedText | None = None,
        error: BaseException | None = None,
    ):
        self.extracted = extracted
        self.error = error

    def extract(self, page: FetchedPage) -> ExtractedText:
        if self.error is not None:
            raise self.error
        return self.extracted


class FakeGenerator:
    def __init__(self, facts: list[DraftFact] | None = None, error: BaseException | None = None):
        self.facts = facts or [
            DraftFact(
                claim="Gold prices rose",
                value="$4,000",
                quote="Gold prices rose as the dollar weakened.",
            )
        ]
        self.error = error
        self.calls: list[tuple[type, str]] = []

    async def complete_json(self, *, schema, system, user, max_tokens):
        self.calls.append((schema, user))
        if self.error is not None:
            raise self.error
        return ExtractedFacts(facts=self.facts)


class FakeDecisions(HeuristicDecisionEngine):
    def __init__(self, risk: float = 0.0):
        self.risk = risk

    async def injection_risk(self, text: str) -> float:
        return self.risk


def page(url: str = "https://www.bbc.com/news/gold") -> FetchedPage:
    return FetchedPage(
        url=url,
        final_url=url,
        status=200,
        content_type="text/html",
        html="<html><body><article><p>Gold prices rose.</p></article></body></html>",
    )


def extracted(word_count: int = 200) -> ExtractedText:
    text = "Gold prices rose as the dollar weakened. " * 20
    return ExtractedText(
        text=text,
        title=None,
        published_at=None,
        word_count=word_count,
        quality=0.8,
    )


def cluster_for(
    registry: SourceRegistry,
    settings: Settings,
    *,
    url: str = "https://www.bbc.com/news/gold",
    publisher: str = "BBC News",
    tier: Tier = Tier.T2,
    family: str = "bbc",
    needs_resolution: bool = False,
):
    candidate = make_candidate(
        title="Gold prices climb",
        url=url,
        publisher=publisher,
        snippet=None,
        tier=tier,
        family=family,
    )
    candidate.needs_resolution = needs_resolution
    return cluster_candidates([candidate], registry=registry, settings=settings)[0]


async def run_enrichment(
    clusters,
    *,
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
    resolver=None,
    fetcher=None,
    extractor=None,
    generator=None,
    decisions=None,
    coverage=None,
):
    coverage = coverage or CoverageCollector()
    return await enrich_clusters(
        clusters,
        query="gold prices",
        resolver=resolver,
        fetcher=fetcher,
        extractor=extractor,
        generator=generator,
        decisions=decisions or FakeDecisions(),
        registry=registry,
        settings=settings,
        coverage=coverage,
        clock=clock,
    ), coverage


async def test_reads_and_extracts_facts(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
) -> None:
    cluster = cluster_for(registry, settings)
    generator = FakeGenerator()
    enriched, coverage = await run_enrichment(
        [cluster],
        settings=settings,
        registry=registry,
        clock=clock,
        fetcher=FakeFetcher(page()),
        extractor=FakeExtractor(extracted()),
        generator=generator,
    )
    member = enriched[0].members[0]
    assert member.text_status is TextStatus.OK
    assert member.word_count == 200
    assert member.fetched_at == NOW
    assert len(enriched[0].facts) == 1
    fact = enriched[0].facts[0]
    assert fact.source_url == "https://www.bbc.com/news/gold"
    assert fact.quote
    assert len(generator.calls) == 1
    assert coverage.finish().text_status[TextStatus.OK] == 1


async def test_resolves_google_link_before_fetch(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
) -> None:
    cluster = cluster_for(
        registry,
        settings,
        url="https://news.google.com/rss/articles/CBMiGold",
        publisher="BBC News",
        needs_resolution=True,
    )
    resolved = "https://www.bbc.com/news/resolved"
    resolver = FakeResolver(resolved)
    fetcher = FakeFetcher(page(resolved))
    enriched, _ = await run_enrichment(
        [cluster],
        settings=settings,
        registry=registry,
        clock=clock,
        resolver=resolver,
        fetcher=fetcher,
        extractor=FakeExtractor(extracted()),
        generator=FakeGenerator(),
    )
    assert resolver.calls == ["https://news.google.com/rss/articles/CBMiGold"]
    assert fetcher.calls == [resolved]
    assert enriched[0].members[0].canonical_url == resolved
    assert enriched[0].facts[0].source_url == resolved


async def test_injection_risk_blocks_generator(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
) -> None:
    cluster = cluster_for(registry, settings)
    generator = FakeGenerator()
    enriched, coverage = await run_enrichment(
        [cluster],
        settings=settings,
        registry=registry,
        clock=clock,
        fetcher=FakeFetcher(page()),
        extractor=FakeExtractor(extracted()),
        generator=generator,
        decisions=FakeDecisions(risk=0.9),
    )
    assert enriched[0].members[0].text_status is TextStatus.BLOCKED
    assert enriched[0].facts == []
    assert generator.calls == []
    assert any("injection risk" in note for note in coverage.finish().notes)


async def test_fetch_timeout_marks_timeout(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
) -> None:
    cluster = cluster_for(registry, settings)
    enriched, _ = await run_enrichment(
        [cluster],
        settings=settings,
        registry=registry,
        clock=clock,
        fetcher=FakeFetcher(error=HttpTimeout("https://www.bbc.com/news/gold")),
        extractor=FakeExtractor(extracted()),
    )
    assert enriched[0].members[0].text_status is TextStatus.TIMEOUT


async def test_policy_skip_does_not_fetch(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
) -> None:
    cluster = cluster_for(
        registry,
        settings,
        url="https://www.reuters.com/markets/gold",
        publisher="Reuters",
        tier=Tier.T1,
        family="reuters",
    )
    fetcher = FakeFetcher(page())
    enriched, _ = await run_enrichment(
        [cluster],
        settings=settings,
        registry=registry,
        clock=clock,
        fetcher=fetcher,
        extractor=FakeExtractor(extracted()),
    )
    assert enriched[0].members[0].text_status is TextStatus.SKIPPED_POLICY
    assert fetcher.calls == []


async def test_thin_text_skips_generator(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
) -> None:
    cluster = cluster_for(registry, settings)
    generator = FakeGenerator()
    enriched, _ = await run_enrichment(
        [cluster],
        settings=settings,
        registry=registry,
        clock=clock,
        fetcher=FakeFetcher(page()),
        extractor=FakeExtractor(extracted(word_count=20)),
        generator=generator,
    )
    assert enriched[0].members[0].text_status is TextStatus.THIN
    assert generator.calls == []


async def test_extraction_failure_marks_thin(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
) -> None:
    cluster = cluster_for(registry, settings)
    enriched, _ = await run_enrichment(
        [cluster],
        settings=settings,
        registry=registry,
        clock=clock,
        fetcher=FakeFetcher(page()),
        extractor=FakeExtractor(error=ExtractionFailed("no text")),
    )
    assert enriched[0].members[0].text_status is TextStatus.THIN


async def test_fetch_blocked_marks_blocked(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
) -> None:
    cluster = cluster_for(registry, settings)
    enriched, _ = await run_enrichment(
        [cluster],
        settings=settings,
        registry=registry,
        clock=clock,
        fetcher=FakeFetcher(error=FetchBlocked("https://www.bbc.com/news/gold", "403")),
        extractor=FakeExtractor(extracted()),
    )
    assert enriched[0].members[0].text_status is TextStatus.BLOCKED


async def test_generator_missing_still_reads_text(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
) -> None:
    cluster = cluster_for(registry, settings)
    enriched, coverage = await run_enrichment(
        [cluster],
        settings=settings,
        registry=registry,
        clock=clock,
        fetcher=FakeFetcher(page()),
        extractor=FakeExtractor(extracted()),
        generator=None,
    )
    assert enriched[0].members[0].text_status is TextStatus.OK
    assert enriched[0].facts == []
    assert any(
        "generator not configured" in note for note in coverage.finish().notes
    )


async def test_unselected_clusters_are_not_fetched(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
) -> None:
    config = Settings(_env_file=None, app_env="demo", fetch_max_reps=1)
    first = cluster_for(registry, config, url="https://www.bbc.com/news/gold")
    second = cluster_for(
        registry,
        config,
        url="https://www.cnbc.com/gold",
        publisher="CNBC",
        family="cnbc",
    )
    enriched, coverage = await run_enrichment(
        [first, second],
        settings=config,
        registry=registry,
        clock=clock,
        fetcher=FakeFetcher(page()),
        extractor=FakeExtractor(extracted()),
        generator=FakeGenerator(),
    )
    statuses = [
        member.text_status for cluster in enriched for member in cluster.members
    ]
    assert statuses.count(TextStatus.NOT_FETCHED) == 1
    assert coverage.finish().text_status[TextStatus.NOT_FETCHED] == 1


async def test_disabled_fetch_marks_policy_and_unfetched(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
) -> None:
    candidates = [
        make_candidate(
            title="Gold rises",
            url="https://www.reuters.com/markets/gold",
            publisher="Reuters",
            tier=Tier.T1,
            family="reuters",
        ),
        make_candidate(
            title="Gold climbs",
            url="https://www.bbc.com/news/gold",
            publisher="BBC News",
            tier=Tier.T2,
            family="bbc",
        ),
    ]
    clusters = cluster_candidates(candidates, registry=registry, settings=settings)
    enriched, coverage = await run_enrichment(
        clusters,
        settings=settings,
        registry=registry,
        clock=clock,
        fetcher=None,
        extractor=None,
    )
    statuses = {
        member.candidate.domain: member.text_status
        for cluster in enriched
        for member in cluster.members
    }
    assert statuses["reuters.com"] is TextStatus.SKIPPED_POLICY
    assert statuses["bbc.com"] is TextStatus.NOT_FETCHED
    report = coverage.finish()
    assert report.text_status[TextStatus.SKIPPED_POLICY] == 1
    assert report.text_status[TextStatus.NOT_FETCHED] == 1
    assert report.notes
