from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter
from pathlib import Path


async def run(query: str, backend_names: list[str] | None) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from Core.cluster import cluster_candidates, cosine, feature_vector
    from Core.coverage import CoverageCollector
    from Core.models import Backend
    from Core.pipeline import SystemClock
    from Core.query_plan import plan_query
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
        query, decisions=decisions, registry=registry, settings=settings
    )
    coverage = CoverageCollector()
    candidates = await retrieve_candidates(
        plan,
        backends=backends,
        registry=registry,
        settings=settings,
        coverage=coverage,
    )
    clusters = cluster_candidates(candidates, registry=registry, settings=settings)
    report = coverage.finish()

    sizes = Counter(len(cluster.members) for cluster in clusters)
    print(f"query: {plan.normalized}")
    print(f"candidates: {len(candidates)}  clusters: {len(clusters)}")
    print(f"cluster sizes: {dict(sorted(sizes.items()))}")
    print(f"backend drops: {report.drops}")
    print("\nmerged clusters:")
    for cluster in clusters:
        if len(cluster.members) > 1:
            print(f"  {cluster.id} n={len(cluster.members)} families={cluster.families}")
            for member in cluster.members:
                candidate = member.candidate
                print(
                    f"    - [{candidate.tier.value}/{candidate.publisher or '-'}/"
                    f"{candidate.backend.value}] {candidate.title[:90]}"
                )

    vectors = [feature_vector(candidate.title, settings=settings) for candidate in candidates]
    token_sets = [
        {token for token in re.findall(r"[a-z0-9]+", candidate.title.lower())}
        for candidate in candidates
    ]
    pairs = []
    for left in range(len(candidates)):
        for right in range(left + 1, len(candidates)):
            score = cosine(vectors[left], vectors[right])
            shared = len(token_sets[left] & token_sets[right])
            pairs.append((score, shared, candidates[left].title, candidates[right].title))
    pairs.sort(reverse=True)
    print("\nclosest pairs:")
    for score, shared, left, right in pairs[:10]:
        print(f"  {score:.3f} shared={shared}  {left[:60]}  ||  {right[:60]}")

    await http.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe real-data clustering.")
    parser.add_argument("query", nargs="?", default="gold prices")
    parser.add_argument(
        "--backend",
        action="append",
        choices=["google_news", "bing_news", "gdelt", "publisher_rss"],
    )
    args = parser.parse_args()
    asyncio.run(run(args.query, args.backend))


if __name__ == "__main__":
    main()
