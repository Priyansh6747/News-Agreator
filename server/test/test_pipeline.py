from __future__ import annotations

import asyncio
from datetime import timedelta

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
    assert "out_of_window" not in brief.coverage.drops
    assert any(
        story.last_seen is not None and story.last_seen < NOW - timedelta(hours=24)
        for story in brief.stories
    )

    finished = [event.stage for event in sink.events if event.state is EventState.FINISHED]
    assert finished == [
        Stage.PLAN,
        Stage.RETRIEVE,
        Stage.RANK,
        Stage.CLUSTER,
        Stage.SCORE,
        Stage.ENRICH,
        Stage.BRIEF,
        Stage.PRESENT,
    ]

    assert isinstance(brief.charts, list)
    assert all(chart.kind in {"bar", "line", "pie"} for chart in brief.charts)
    assert brief.map is None
    assert Stage.PRESENT in brief.coverage.timings_ms

    progress = [event for event in sink.events if event.state is EventState.PROGRESS]
    assert any(
        event.stage is Stage.RETRIEVE
        and event.counts == {"done": len(Backend), "total": len(Backend)}
        for event in progress
    )
    assert any(
        event.stage is Stage.RANK and event.counts == {"done": 1, "total": 1}
        for event in progress
    )

    assert set(brief.coverage.timings_ms) == set(Stage)


async def test_deadline_marks_coverage_unavailable(registry: SourceRegistry) -> None:
    class SlowDecisions(HeuristicDecisionEngine):
        async def relevance(self, query, candidates):
            await asyncio.sleep(0.2)
            return await super().relevance(query, candidates)

    config = Settings(_env_file=None, app_env="demo", pipeline_deadline_s=0.01)
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
