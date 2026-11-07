from __future__ import annotations

from datetime import timedelta

from Core.coverage import CoverageCollector
from Core.models import ArticleType, CandidateAssessment, QueryPlan, Tier
from Core.rank import rank_candidates
from Core.registry import SourceRegistry
from Core.settings import Settings
from test.helpers import NOW, make_candidate
from tool.decisions_heuristic import HeuristicDecisionEngine
from tool.fixture_adapters import StaticClock


def plan(hours: int = 24) -> QueryPlan:
    return QueryPlan(query="gold prices", normalized="gold prices", freshness_hours=hours)


async def test_drops_out_of_window_undated_and_future(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    candidates = [
        make_candidate(title="Gold recent", url="https://www.reuters.com/a"),
        make_candidate(
            title="Gold old",
            url="https://www.reuters.com/b",
            published_at=NOW - timedelta(hours=48),
        ),
        make_candidate(title="Gold undated", url="https://www.reuters.com/c", published_at=None),
        make_candidate(
            title="Gold future",
            url="https://www.reuters.com/d",
            published_at=NOW + timedelta(hours=2),
        ),
    ]
    coverage = CoverageCollector()
    ranked = await rank_candidates(
        candidates,
        plan=plan(),
        decisions=HeuristicDecisionEngine(),
        settings=settings,
        coverage=coverage,
        clock=StaticClock(NOW),
    )
    assert [candidate.title for candidate in ranked] == ["Gold recent"]
    assert coverage.finish().drops == {
        "future_date": 1,
        "out_of_window": 1,
        "undated": 1,
    }


async def test_orders_by_tier_when_relevance_is_equal(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    candidates = [
        make_candidate(
            title="Gold falls",
            url="https://www.bbc.com/news/gold-falls",
            publisher="BBC News",
            tier=Tier.T2,
            family="bbc",
        ),
        make_candidate(
            title="Gold rises",
            url="https://www.reuters.com/markets/gold-rises",
            publisher="Reuters",
            tier=Tier.T1,
            family="reuters",
        ),
    ]
    ranked = await rank_candidates(
        candidates,
        plan=plan(),
        decisions=HeuristicDecisionEngine(),
        settings=settings,
        coverage=CoverageCollector(),
        clock=StaticClock(NOW),
    )
    assert ranked[0].tier is Tier.T1
    assert ranked[0].score > ranked[1].score


class FixedDecisions(HeuristicDecisionEngine):
    def __init__(self, relevance: float):
        self.relevance = relevance

    async def assess(self, query, candidates):
        return [
            CandidateAssessment(
                relevance=self.relevance,
                article_type=ArticleType.REPORT,
            )
            for _ in candidates
        ]


async def test_tier_aware_relevance_floor(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    candidates = [
        make_candidate(
            title="Gold rises",
            url="https://www.bbc.com/news/gold",
            publisher="BBC News",
            tier=Tier.T2,
            family="bbc",
        ),
        make_candidate(
            title="Gold climbs",
            url="https://www.example.com/gold",
            publisher="Example",
            tier=Tier.UNREVIEWED,
            family=None,
        ),
    ]
    coverage = CoverageCollector()
    ranked = await rank_candidates(
        candidates,
        plan=plan(),
        decisions=FixedDecisions(0.32),
        settings=settings,
        coverage=coverage,
        clock=StaticClock(NOW),
    )
    assert [candidate.tier for candidate in ranked] == [Tier.T2]
    assert coverage.finish().drops["low_relevance"] == 1


async def test_relevance_floor_drops_off_topic(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    candidates = [
        make_candidate(
            title="Gold prices rise",
            url="https://www.reuters.com/on",
            snippet="Gold prices rose on Thursday.",
        ),
        make_candidate(
            title="Oil slides on demand",
            url="https://www.reuters.com/off",
            snippet="Crude oil fell as demand weakened.",
        ),
    ]
    coverage = CoverageCollector()
    ranked = await rank_candidates(
        candidates,
        plan=plan(),
        decisions=HeuristicDecisionEngine(),
        settings=settings,
        coverage=coverage,
        clock=StaticClock(NOW),
    )
    assert [candidate.title for candidate in ranked] == ["Gold prices rise"]
    assert coverage.finish().drops["low_relevance"] == 1


async def test_pre_rank_prefers_lexical_match(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    class SpyDecisions(HeuristicDecisionEngine):
        def __init__(self) -> None:
            self.assessed: list[str] = []

        async def assess(self, query, candidates):
            self.assessed = [candidate.title for candidate in candidates]
            return await super().assess(query, candidates)

    spy = SpyDecisions()
    gold = make_candidate(
        title="Gold prices climb",
        url="https://www.example.com/gold",
        snippet="Gold prices rose on Thursday.",
        tier=Tier.T4,
        published_at=NOW - timedelta(hours=20),
    )
    oil = make_candidate(
        title="Oil slides",
        url="https://www.example.com/oil",
        snippet="Crude oil fell as demand weakened.",
        tier=Tier.T1,
        published_at=NOW - timedelta(hours=1),
    )
    await rank_candidates(
        [gold, oil],
        plan=plan(),
        decisions=spy,
        settings=settings,
        coverage=CoverageCollector(),
        clock=StaticClock(NOW),
        assess_top=1,
    )
    assert spy.assessed == ["Gold prices climb"]


async def test_assess_cap_limits_expensive_engine_calls(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    candidates = [
        make_candidate(
            title=f"Gold story {index}",
            url=f"https://www.reuters.com/cap-{index}",
        )
        for index in range(8)
    ]
    coverage = CoverageCollector()
    ranked = await rank_candidates(
        candidates,
        plan=plan(),
        decisions=HeuristicDecisionEngine(),
        settings=settings,
        coverage=coverage,
        clock=StaticClock(NOW),
        assess_top=3,
    )
    assert len(ranked) == 3
    assert coverage.finish().drops["assess_cap"] == 5


async def test_caps_at_select_top(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    candidates = [
        make_candidate(
            title=f"Gold story {index}",
            url=f"https://www.reuters.com/story-{index}",
        )
        for index in range(settings.select_top + 5)
    ]
    coverage = CoverageCollector()
    ranked = await rank_candidates(
        candidates,
        plan=plan(),
        decisions=HeuristicDecisionEngine(),
        settings=settings,
        coverage=coverage,
        clock=StaticClock(NOW),
    )
    assert len(ranked) == settings.select_top
    assert coverage.finish().drops["rank_cap"] == 5
