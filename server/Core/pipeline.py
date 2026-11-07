from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import perf_counter

from Core.brief import build_brief
from Core.cluster import cluster_candidates
from Core.coverage import CoverageCollector
from Core.enrich import enrich_clusters
from Core.models import Brief, CoverageStatus, EventState, Stage, StageEvent
from Core.ports import (
    ArticleFetcher,
    Clock,
    DecisionEngine,
    Generator,
    LinkResolver,
    ProgressSink,
    SearchBackend,
    TextExtractor,
)
from Core.query_plan import plan_query
from Core.rank import rank_candidates
from Core.registry import SourceRegistry
from Core.retrieve import retrieve_candidates
from Core.score import score_clusters
from Core.settings import Settings


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class NullSink:
    async def emit(self, event: StageEvent) -> None:
        return None


class Pipeline:
    def __init__(
        self,
        *,
        backends: list[SearchBackend],
        decisions: DecisionEngine,
        registry: SourceRegistry,
        settings: Settings,
        clock: Clock | None = None,
        resolver: LinkResolver | None = None,
        fetcher: ArticleFetcher | None = None,
        extractor: TextExtractor | None = None,
        generator: Generator | None = None,
        assess_top: int | None = None,
    ):
        self.backends = backends
        self.decisions = decisions
        self.registry = registry
        self.settings = settings
        self.clock = clock or SystemClock()
        self.resolver = resolver
        self.fetcher = fetcher
        self.extractor = extractor
        self.generator = generator
        self.assess_top = assess_top

    async def _emit(
        self,
        sink: ProgressSink,
        stage: Stage,
        state: EventState,
        *,
        counts: dict[str, int] | None = None,
        message: str | None = None,
        elapsed_ms: int | None = None,
    ) -> None:
        await sink.emit(
            StageEvent(
                stage=stage,
                state=state,
                counts=counts or {},
                message=message,
                elapsed_ms=elapsed_ms,
                at=self.clock.now(),
            )
        )

    def _record(self, coverage: CoverageCollector, stage: Stage, started: float) -> int:
        elapsed = int((perf_counter() - started) * 1000)
        coverage.record_timing(stage, elapsed)
        return elapsed

    async def run(self, query: str, sink: ProgressSink | None = None) -> Brief:
        sink = sink or NullSink()
        coverage = CoverageCollector()

        await self._emit(sink, Stage.PLAN, EventState.STARTED)
        started = perf_counter()
        plan = await plan_query(
            query,
            decisions=self.decisions,
            registry=self.registry,
            settings=self.settings,
        )
        elapsed = self._record(coverage, Stage.PLAN, started)
        await self._emit(
            sink,
            Stage.PLAN,
            EventState.FINISHED,
            counts={
                "phrasings": len(plan.phrasings),
                "site_scoped": len(plan.site_scoped),
                "freshness_hours": plan.freshness_hours,
            },
            elapsed_ms=elapsed,
        )

        clusters = []
        try:
            async with asyncio.timeout(self.settings.pipeline_deadline_s):
                await self._emit(sink, Stage.RETRIEVE, EventState.STARTED)
                started = perf_counter()
                candidates = await retrieve_candidates(
                    plan,
                    backends=self.backends,
                    registry=self.registry,
                    settings=self.settings,
                    coverage=coverage,
                )
                elapsed = self._record(coverage, Stage.RETRIEVE, started)
                await self._emit(
                    sink,
                    Stage.RETRIEVE,
                    EventState.FINISHED,
                    counts={"candidates": len(candidates)},
                    elapsed_ms=elapsed,
                )

                await self._emit(sink, Stage.RANK, EventState.STARTED)
                started = perf_counter()
                selected = await rank_candidates(
                    candidates,
                    plan=plan,
                    decisions=self.decisions,
                    settings=self.settings,
                    coverage=coverage,
                    clock=self.clock,
                    assess_top=self.assess_top,
                )
                elapsed = self._record(coverage, Stage.RANK, started)
                await self._emit(
                    sink,
                    Stage.RANK,
                    EventState.FINISHED,
                    counts={"selected": len(selected)},
                    elapsed_ms=elapsed,
                )

                await self._emit(sink, Stage.CLUSTER, EventState.STARTED)
                started = perf_counter()
                clusters = cluster_candidates(
                    selected,
                    registry=self.registry,
                    settings=self.settings,
                )
                elapsed = self._record(coverage, Stage.CLUSTER, started)
                await self._emit(
                    sink,
                    Stage.CLUSTER,
                    EventState.FINISHED,
                    counts={"clusters": len(clusters)},
                    elapsed_ms=elapsed,
                )

                await self._emit(sink, Stage.SCORE, EventState.STARTED)
                started = perf_counter()
                clusters = score_clusters(
                    clusters,
                    plan=plan,
                    registry=self.registry,
                    settings=self.settings,
                    clock=self.clock,
                )
                elapsed = self._record(coverage, Stage.SCORE, started)
                await self._emit(
                    sink,
                    Stage.SCORE,
                    EventState.FINISHED,
                    counts={"clusters": len(clusters)},
                    elapsed_ms=elapsed,
                )

                await self._emit(sink, Stage.ENRICH, EventState.STARTED)
                started = perf_counter()
                clusters = await enrich_clusters(
                    clusters,
                    query=query,
                    resolver=self.resolver,
                    fetcher=self.fetcher,
                    extractor=self.extractor,
                    generator=self.generator,
                    decisions=self.decisions,
                    registry=self.registry,
                    settings=self.settings,
                    coverage=coverage,
                    clock=self.clock,
                )
                elapsed = self._record(coverage, Stage.ENRICH, started)
                await self._emit(
                    sink,
                    Stage.ENRICH,
                    EventState.FINISHED,
                    counts={
                        "clusters": len(clusters),
                        "facts": sum(len(cluster.facts) for cluster in clusters),
                    },
                    elapsed_ms=elapsed,
                )
        except TimeoutError:
            coverage.note("pipeline deadline exceeded; partial results only")
            coverage.force_status(
                CoverageStatus.PARTIAL if clusters else CoverageStatus.UNAVAILABLE
            )

        await self._emit(sink, Stage.BRIEF, EventState.STARTED)
        started = perf_counter()
        brief = await build_brief(
            query=query,
            plan=plan,
            clusters=clusters,
            coverage=coverage,
            generator=self.generator,
            settings=self.settings,
            clock=self.clock,
        )
        elapsed = self._record(coverage, Stage.BRIEF, started)
        brief.coverage.timings_ms[Stage.BRIEF] = elapsed
        await self._emit(
            sink,
            Stage.BRIEF,
            EventState.FINISHED,
            counts={
                "stories": len(brief.stories),
                "facts": len(brief.key_facts),
                "timeline": len(brief.timeline),
            },
            elapsed_ms=elapsed,
        )
        return brief
