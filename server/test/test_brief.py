from __future__ import annotations

from Core.brief import build_brief
from Core.cluster import cluster_candidates
from Core.coverage import CoverageCollector
from Core.models import Attempt, Backend, CoverageStatus, QueryPlan, Tier
from Core.registry import SourceRegistry
from Core.score import score_clusters
from Core.settings import Settings
from test.helpers import NOW, make_candidate
from tool.fixture_adapters import FixtureGenerator, StaticClock


def plan() -> QueryPlan:
    return QueryPlan(query="gold prices", normalized="gold prices", freshness_hours=24)


def scored_clusters(registry: SourceRegistry, settings: Settings, clock: StaticClock):
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
    return score_clusters(
        clusters,
        plan=plan(),
        registry=registry,
        settings=settings,
        clock=clock,
    )


def complete_coverage() -> CoverageCollector:
    coverage = CoverageCollector()
    coverage.record_attempt(Backend.PUBLISHER_RSS, Attempt.COMPLETED, returned=2)
    coverage.record_kept(Backend.PUBLISHER_RSS, 2)
    return coverage


class DraftGenerator:
    def __init__(self, cluster_id: str):
        self._cluster_id = cluster_id

    async def complete_json(self, *, schema, system, user, max_tokens):
        return schema.model_validate(
            {
                "answer": "Generated answer.",
                "key_facts": [
                    {
                        "value": "$2,400",
                        "meaning": "Spot gold price",
                        "cluster_id": self._cluster_id,
                    }
                ],
                "timeline": [],
                "disagreements": [],
                "thin_sourcing": [],
            }
        )


async def test_fallback_brief_without_generator(
    registry: SourceRegistry,
    settings: Settings,
    clock: StaticClock,
) -> None:
    clusters = scored_clusters(registry, settings, clock)
    coverage = complete_coverage()
    brief = await build_brief(
        query="gold prices",
        plan=plan(),
        clusters=clusters,
        coverage=coverage,
        generator=None,
        settings=settings,
        clock=clock,
    )
    assert brief.answer
    assert len(brief.stories) == 2
    assert brief.timeline
    assert brief.coverage.status is CoverageStatus.COMPLETE
    assert brief.generated_at == NOW
    assert any("No article text" in note for note in brief.thin_sourcing)
    for entry in brief.timeline:
        assert entry.source_url.startswith("https://")


async def test_generator_draft_maps_cluster_provenance(
    registry: SourceRegistry,
    settings: Settings,
    clock: StaticClock,
) -> None:
    clusters = scored_clusters(registry, settings, clock)
    brief = await build_brief(
        query="gold prices",
        plan=plan(),
        clusters=clusters,
        coverage=complete_coverage(),
        generator=DraftGenerator(clusters[0].id),
        settings=settings,
        clock=clock,
    )
    assert brief.answer == "Generated answer."
    assert len(brief.key_facts) == 1
    assert brief.key_facts[0].source_url in {
        member.canonical_url for member in clusters[0].members
    }


async def test_generator_with_unknown_cluster_id_is_dropped(
    registry: SourceRegistry,
    settings: Settings,
    clock: StaticClock,
) -> None:
    clusters = scored_clusters(registry, settings, clock)
    brief = await build_brief(
        query="gold prices",
        plan=plan(),
        clusters=clusters,
        coverage=complete_coverage(),
        generator=DraftGenerator("missing"),
        settings=settings,
        clock=clock,
    )
    assert brief.key_facts == []
    assert any("unknown cluster id" in note for note in brief.coverage.notes)


async def test_fixture_generator_is_used(
    registry: SourceRegistry,
    settings: Settings,
    clock: StaticClock,
) -> None:
    brief = await build_brief(
        query="gold prices",
        plan=plan(),
        clusters=scored_clusters(registry, settings, clock),
        coverage=complete_coverage(),
        generator=FixtureGenerator(),
        settings=settings,
        clock=clock,
    )
    assert brief.answer == "Fixture brief generated from fixture clusters."
