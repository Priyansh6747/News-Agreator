from __future__ import annotations

from datetime import timedelta

from Core.models import (
    Article,
    CredibilityScore,
    ImportanceScore,
    QueryPlan,
    StoryCluster,
    Tier,
)
from Core.registry import SourceRegistry
from Core.score import score_clusters
from Core.settings import Settings
from test.helpers import NOW, make_candidate
from tool.fixture_adapters import StaticClock


def article(candidate) -> Article:
    return Article(
        candidate=candidate,
        canonical_url=candidate.url,
        resolved_publisher=candidate.publisher,
    )


def cluster(candidates: list, cluster_id: str = "c1") -> StoryCluster:
    return StoryCluster(
        id=cluster_id,
        headline=candidates[0].title,
        members=[article(candidate) for candidate in candidates],
        importance=ImportanceScore(score=0.0),
        credibility=CredibilityScore(score=0.0),
        first_seen=NOW - timedelta(hours=2),
        last_seen=NOW - timedelta(hours=1),
    )


def plan() -> QueryPlan:
    return QueryPlan(query="gold prices", normalized="gold prices", freshness_hours=24)


def test_dual_scores_and_families(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    candidates = [
        make_candidate(
            title="Gold rises",
            url="https://www.reuters.com/a",
            publisher="Reuters",
            tier=Tier.T1,
            family="reuters",
        ),
        make_candidate(
            title="Gold climbs",
            url="https://www.bbc.com/b",
            publisher="BBC News",
            tier=Tier.T2,
            family="bbc",
        ),
    ]
    scored = score_clusters(
        [cluster(candidates)],
        plan=plan(),
        registry=registry,
        settings=settings,
        clock=StaticClock(NOW),
    )
    result = scored[0]
    assert result.families == ["bbc", "reuters"]
    assert 0.0 < result.importance.corroboration < 1.0
    assert result.importance.score > 0.0
    assert 0.0 < result.credibility.score < 100.0
    assert result.credibility.capped is False


def test_google_carried_article_keeps_publisher_identity(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    candidate = make_candidate(
        title="Gold rises",
        url="https://news.google.com/rss/articles/abc",
        publisher="Reuters",
        tier=Tier.T1,
        family="reuters",
    )
    candidate.needs_resolution = True
    result = score_clusters(
        [cluster([candidate])],
        plan=plan(),
        registry=registry,
        settings=settings,
        clock=StaticClock(NOW),
    )[0]
    assert result.families == ["reuters"]
    assert result.credibility.propaganda_risk == 0.05


def test_publisher_lookup_wins_over_aggregator_domain(
    registry: SourceRegistry,
) -> None:
    assert registry.family_for(domain="news.google.com", publisher="Reuters") == "reuters"
    assert registry.tier_for(domain="news.google.com", publisher="Reuters") is Tier.T1
    assert registry.risk_for(domain="news.google.com", publisher="Reuters") == 0.05


def test_high_risk_credibility_is_capped(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    candidates = [
        make_candidate(
            title="Gold conspiracy",
            url="https://www.zerohedge.com/a",
            publisher="ZeroHedge",
            tier=Tier.T4,
            family="zerohedge",
        ),
        make_candidate(
            title="Gold conspiracy follow-up",
            url="https://zerohedge.com/b",
            publisher="ZeroHedge",
            tier=Tier.T4,
            family="zerohedge",
        ),
    ]
    result = score_clusters(
        [cluster(candidates)],
        plan=plan(),
        registry=registry,
        settings=settings,
        clock=StaticClock(NOW),
    )[0]
    assert result.credibility.capped is True
    assert result.credibility.score <= settings.high_risk_cap
    assert result.families == ["zerohedge"]
    assert result.importance.corroboration == 0.0
