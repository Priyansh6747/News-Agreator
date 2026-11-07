from __future__ import annotations

import hashlib

from Core.models import Article, Candidate, CredibilityScore, ImportanceScore, StoryCluster
from Core.registry import SourceRegistry
from Core.settings import Settings


def cluster_id(candidate: Candidate) -> str:
    digest = hashlib.sha1(candidate.url.encode("utf-8")).hexdigest()[:12]
    return f"c_{digest}"


def cluster_candidates(
    candidates: list[Candidate],
    *,
    registry: SourceRegistry,
    settings: Settings,
) -> list[StoryCluster]:
    clusters: list[StoryCluster] = []
    for candidate in candidates:
        article = Article(
            candidate=candidate,
            canonical_url=candidate.url,
            resolved_publisher=candidate.publisher,
        )
        clusters.append(
            StoryCluster(
                id=cluster_id(candidate),
                headline=candidate.title,
                members=[article],
                families=[candidate.family] if candidate.family else [],
                importance=ImportanceScore(score=0.0),
                credibility=CredibilityScore(score=0.0),
                first_seen=candidate.published_at,
                last_seen=candidate.published_at,
            )
        )
    return clusters
