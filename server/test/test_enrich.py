from __future__ import annotations

from Core.cluster import cluster_candidates
from Core.coverage import CoverageCollector
from Core.enrich import enrich_clusters
from Core.models import TextStatus, Tier
from Core.registry import SourceRegistry
from Core.settings import Settings
from test.helpers import make_candidate
from tool.decisions_heuristic import HeuristicDecisionEngine
from tool.fixture_adapters import StaticClock


async def test_marks_policy_denied_and_unfetched(
    settings: Settings,
    registry: SourceRegistry,
    clock: StaticClock,
    decisions: HeuristicDecisionEngine,
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
    coverage = CoverageCollector()
    enriched = await enrich_clusters(
        clusters,
        resolver=None,
        fetcher=None,
        extractor=None,
        generator=None,
        decisions=decisions,
        registry=registry,
        settings=settings,
        coverage=coverage,
        clock=clock,
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
