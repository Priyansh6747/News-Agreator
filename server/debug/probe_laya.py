from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from time import perf_counter


async def run(query: str, title: str, snippet: str) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from Core.models import Backend, Candidate
    from Core.settings import Settings
    from tool.decisions_heuristic import HeuristicDecisionEngine
    from tool.decisions_laya import LayaDecisionEngine

    settings = Settings(app_env="dev")
    decisions = LayaDecisionEngine(
        fallback=HeuristicDecisionEngine(),
        preload=settings.laya_preload,
        device=settings.laya_device,
        default=settings.laya_default_model,
        max_loaded=settings.laya_max_loaded,
        batch_size=settings.laya_batch_size,
    )
    candidate = Candidate(
        title=title,
        url="https://example.com/story",
        publisher="Example",
        snippet=snippet,
        backend=Backend.PUBLISHER_RSS,
    )

    started = perf_counter()
    query_class = await decisions.classify_query(query)
    class_ms = int((perf_counter() - started) * 1000)

    started = perf_counter()
    assessment = (await decisions.assess(query, [candidate]))[0]
    assess_ms = int((perf_counter() - started) * 1000)

    started = perf_counter()
    injection = await decisions.injection_risk(snippet)
    injection_ms = int((perf_counter() - started) * 1000)

    print(f"query: {query}")
    print(f"class: {query_class.value}  ({class_ms} ms)")
    print(
        f"relevance: {assessment.relevance:.3f}  "
        f"type: {assessment.article_type.value}  "
        f"confidence: {assessment.confidence}  ({assess_ms} ms)"
    )
    print(f"injection_risk: {injection:.3f}  ({injection_ms} ms)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Laya decision set.")
    parser.add_argument("query", nargs="?", default="gold prices")
    parser.add_argument(
        "title",
        nargs="?",
        default="Gold climbs as dollar softens ahead of Fed decision",
    )
    parser.add_argument(
        "snippet",
        nargs="?",
        default="Gold prices rose as the dollar eased and traders weighed the rate path.",
    )
    args = parser.parse_args()
    asyncio.run(run(args.query, args.title, args.snippet))


if __name__ == "__main__":
    main()
