from __future__ import annotations

import asyncio

from Core.models import (
    Backend,
    CoverageStatus,
    EventState,
    QueryClass,
    SearchResult,
    Stage,
    StageEvent,
)
from Core.pipeline import Pipeline
from Core.registry import SourceRegistry
from Core.settings import Settings
from test.helpers import NOW
from tool.decisions_heuristic import HeuristicDecisionEngine
from tool.fixture_adapters import FixtureSearchBackend, StaticClock


class CollectingSink:
    def __init__(self) -> None:
        self.events: list[StageEvent] = []

    async def emit(self, event: StageEvent) -> None:
        self.events.append(event)


async def test_pipeline_end_to_end(
    settings: Settings,
    registry: SourceRegistry,
    decisions: HeuristicDecisionEngine,
) -> None:
    clock = StaticClock(NOW)
    pipeline = Pipeline(
        backends=[FixtureSearchBackend(backend, NOW) for backend in Backend],
        decisions=decisions,
        registry=registry,
        settings=settings,
        clock=clock,
    )
    sink = CollectingSink()
    brief = await pipeline.run("gold prices", sink)

    assert brief.query == "gold prices"
    assert brief.query_class is QueryClass.MARKET
    assert brief.stories
    assert brief.timeline
    assert brief.coverage.status is CoverageStatus.COMPLETE
    assert brief.coverage.drops["out_of_window"] == 2

    finished = [event.stage for event in sink.events if event.state is EventState.FINISHED]
    assert finished == [
        Stage.PLAN,
        Stage.RETRIEVE,
        Stage.RANK,
        Stage.CLUSTER,
        Stage.SCORE,
        Stage.ENRICH,
        Stage.BRIEF,
    ]
    assert set(brief.coverage.timings_ms) == set(Stage)


async def test_deadline_marks_coverage_unavailable(registry: SourceRegistry) -> None:
    class SlowDecisions(HeuristicDecisionEngine):
        async def assess(self, query, candidates):
            await asyncio.sleep(0.2)
            return await super().assess(query, candidates)

    config = Settings(app_env="demo", pipeline_deadline_s=0.01)
    pipeline = Pipeline(
        backends=[FixtureSearchBackend(backend, NOW) for backend in Backend],
        decisions=SlowDecisions(),
        registry=registry,
        settings=config,
        clock=StaticClock(NOW),
    )
    brief = await pipeline.run("gold prices")
    assert brief.coverage.status is CoverageStatus.UNAVAILABLE
    assert any("deadline" in note for note in brief.coverage.notes)


async def test_pipeline_returns_empty_brief_when_no_candidates(
    settings: Settings,
    registry: SourceRegistry,
    decisions: HeuristicDecisionEngine,
) -> None:
    class EmptyBackend:
        name = Backend.BING_NEWS

        async def search(self, plan, *, limit):
            return SearchResult(items=[], raw_count=0)

    clock = StaticClock(NOW)
    pipeline = Pipeline(
        backends=[EmptyBackend()],
        decisions=decisions,
        registry=registry,
        settings=settings,
        clock=clock,
    )
    brief = await pipeline.run("gold prices")
    assert brief.stories == []
    assert brief.coverage.status is CoverageStatus.UNAVAILABLE
    assert "No stories" in brief.answer
