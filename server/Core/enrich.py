from __future__ import annotations

from Core.coverage import CoverageCollector
from Core.models import StoryCluster, TextStatus
from Core.ports import ArticleFetcher, Clock, DecisionEngine, Generator, LinkResolver, TextExtractor
from Core.registry import SourceRegistry
from Core.settings import Settings


async def enrich_clusters(
    clusters: list[StoryCluster],
    *,
    resolver: LinkResolver | None,
    fetcher: ArticleFetcher | None,
    extractor: TextExtractor | None,
    generator: Generator | None,
    decisions: DecisionEngine,
    registry: SourceRegistry,
    settings: Settings,
    coverage: CoverageCollector,
    clock: Clock,
) -> list[StoryCluster]:
    for cluster in clusters:
        for member in cluster.members:
            policy = registry.fetch_policy(member.candidate.domain)
            if policy.mode != "fetch":
                member.text_status = TextStatus.SKIPPED_POLICY
            else:
                member.text_status = TextStatus.NOT_FETCHED
            coverage.record_text_status(member.text_status)
    coverage.note("article fetch and extraction are not enabled in this build")
    return clusters
