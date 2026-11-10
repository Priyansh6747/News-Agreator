from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from time import perf_counter


async def run(query: str, backend_names: list[str] | None) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from Core.coverage import CoverageCollector
    from Core.models import Backend
    from Core.pipeline import SystemClock
    from Core.query_plan import plan_query
    from Core.rank import rank_candidates
    from Core.registry import SourceRegistry
    from Core.retrieve import retrieve_candidates
    from Core.settings import Settings
    from tool.bing_news import BingNewsBackend
    from tool.decisions_heuristic import HeuristicDecisionEngine
    from tool.gdelt import GdeltBackend
    from tool.google_news import GoogleNewsBackend
    from tool.http import HttpClient
    from tool.publisher_rss import PublisherRssBackend

    enabled = backend_names or [backend.value for backend in Backend]
    settings = Settings(app_env="dev", enabled_backends=enabled)
    registry = SourceRegistry.load()
    clock = SystemClock()
    http = HttpClient(settings)
    decisions = HeuristicDecisionEngine()

    backends = []
    if Backend.GOOGLE_NEWS.value in enabled:
        backends.append(GoogleNewsBackend(http, settings, clock))
    if Backend.BING_NEWS.value in enabled:
        backends.append(BingNewsBackend(http, settings, registry, clock))
    if Backend.GDELT.value in enabled:
        backends.append(GdeltBackend(http, settings, registry, clock))
    if Backend.PUBLISHER_RSS.value in enabled:
        backends.append(PublisherRssBackend(http, registry, settings, clock))

    plan = await plan_query(
        query,
        decisions=decisions,
        registry=registry,
        settings=settings,
    )
    coverage = CoverageCollector()
    started = perf_counter()
    candidates = await retrieve_candidates(
        plan,
        backends=backends,
        registry=registry,
        settings=settings,
        coverage=coverage,
        clock=clock,
    )
    ranked = await rank_candidates(
        candidates,
        plan=plan,
        decisions=decisions,
        settings=settings,
        coverage=coverage,
        clock=clock,
    )
    elapsed = perf_counter() - started
    report = coverage.finish()

    print(f"query: {plan.normalized}")
    print(
        f"class: {plan.query_class.value}  freshness: {plan.freshness_hours}h  "
        f"lookback: {plan.lookback}h"
    )
    print(f"candidates: {len(candidates)}  selected: {len(ranked)}  total: {elapsed:.2f}s")
    print("\nbackends:")
    for attempt in report.attempts:
        detail = f"  {attempt.detail}" if attempt.detail else ""
        print(
            f"  {attempt.backend.value:<14} {attempt.attempt.value:<20} "
            f"returned={attempt.returned:<4} {attempt.elapsed_ms}ms{detail}"
        )
    print(f"\ndrops: {report.drops}")
    print("\ntop candidates:")
    for candidate in ranked[:10]:
        score = f"{candidate.score:.3f}" if candidate.score is not None else "-"
        print(
            f"  {score}  {candidate.tier.value:<10} {candidate.backend.value:<14} "
            f"{(candidate.publisher or '-')[:24]:<24} {candidate.title[:80]}"
        )
    await http.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe the live retrieval backends.")
    parser.add_argument("query", nargs="?", default="gold prices")
    parser.add_argument(
        "--backend",
        action="append",
        choices=["google_news", "bing_news", "gdelt", "publisher_rss"],
        help="limit to one or more backends",
    )
    args = parser.parse_args()
    asyncio.run(run(args.query, args.backend))


if __name__ == "__main__":
    main()
