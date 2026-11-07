from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


async def run(query: str) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from Core.models import Backend
    from Core.pipeline import Pipeline, SystemClock
    from Core.registry import SourceRegistry
    from Core.settings import Settings
    from tool.decisions_heuristic import HeuristicDecisionEngine
    from tool.fixture_adapters import FixtureSearchBackend

    clock = SystemClock()
    settings = Settings(app_env="demo")
    pipeline = Pipeline(
        backends=[FixtureSearchBackend(backend, clock.now()) for backend in Backend],
        decisions=HeuristicDecisionEngine(),
        registry=SourceRegistry.load(),
        settings=settings,
        clock=clock,
    )
    brief = await pipeline.run(query)
    print(json.dumps(brief.model_dump(mode="json"), indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixture-backed pipeline.")
    parser.add_argument("query", nargs="?", default="gold prices")
    args = parser.parse_args()
    asyncio.run(run(args.query))


if __name__ == "__main__":
    main()
