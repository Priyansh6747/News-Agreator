from __future__ import annotations

import re
from datetime import timedelta

from Core.models import (
    CredibilityScore,
    ImportanceScore,
    QueryPlan,
    StoryCluster,
)
from Core.ports import Clock
from Core.registry import SourceRegistry
from Core.settings import Settings

HIGH_SEVERITY = {
    "war",
    "invasion",
    "killed",
    "dead",
    "missile",
    "nuclear",
    "sanctions",
    "coup",
    "crash",
    "collapse",
    "default",
    "emergency",
    "earthquake",
    "hurricane",
    "explosion",
    "shooting",
}
MEDIUM_SEVERITY = {
    "election",
    "rate",
    "inflation",
    "tariff",
    "earnings",
    "merger",
    "acquisition",
    "ruling",
    "ban",
    "strike",
    "protest",
    "layoffs",
}


def _severity(headline: str) -> float:
    tokens = set(re.findall(r"[a-z0-9]+", headline.lower()))
    if tokens & HIGH_SEVERITY:
        return 0.9
    if tokens & MEDIUM_SEVERITY:
        return 0.6
    return 0.3


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_clusters(
    clusters: list[StoryCluster],
    *,
    plan: QueryPlan,
    registry: SourceRegistry,
    settings: Settings,
    clock: Clock,
) -> list[StoryCluster]:
    now = clock.now()
    window = timedelta(hours=plan.freshness_hours)
    importance_weights = settings.importance_weights
    credibility_weights = settings.credibility_weights

    for cluster in clusters:
        domains = [member.candidate.domain for member in cluster.members]
        publishers = [member.candidate.publisher for member in cluster.members]
        families = sorted(
            {
                family
                for family in (
                    member.candidate.family
                    or registry.family_for(
                        domain=member.candidate.domain,
                        publisher=member.candidate.publisher,
                    )
                    for member in cluster.members
                )
                if family
            }
        )
        cluster.families = families

        tier_scores = [
            settings.tier_scores.get(member.candidate.tier.value, 0.4)
            for member in cluster.members
        ]
        max_tier = max(tier_scores) if tier_scores else 0.4
        mean_tier = sum(tier_scores) / len(tier_scores) if tier_scores else 0.4
        risks = [
            registry.risk_for(domain=domain, publisher=publisher)
            for domain, publisher in zip(domains, publishers)
        ]
        risk = max(risks) if risks else 0.6
        corroboration = min(1.0, len(families) / 3.0) if len(families) >= 2 else 0.0

        last_seen = cluster.last_seen or now
        age = max(now - last_seen, timedelta(0))
        recency = _clamp(1.0 - age / window) if window.total_seconds() else 0.0
        severity = max((_severity(member.candidate.title) for member in cluster.members), default=0.3)

        importance = 100.0 * (
            importance_weights["severity"] * severity
            + importance_weights["tier"] * max_tier
            + importance_weights["corroboration"] * corroboration
            + importance_weights["recency"] * recency
        )
        cluster.importance = ImportanceScore(
            score=round(_clamp(importance / 100.0) * 100.0, 2),
            severity=severity,
            tier=max_tier,
            corroboration=corroboration,
            recency=recency,
        )

        credibility = 100.0 * (
            credibility_weights["tier"] * mean_tier
            + credibility_weights["risk"] * (1.0 - risk)
            + credibility_weights["corroboration"] * corroboration
        )
        capped = risk >= settings.high_risk_threshold
        if capped:
            credibility = min(credibility, settings.high_risk_cap)
        cluster.credibility = CredibilityScore(
            score=round(_clamp(credibility / 100.0) * 100.0, 2),
            tier=mean_tier,
            propaganda_risk=risk,
            corroboration=corroboration,
            capped=capped,
        )

    return sorted(clusters, key=lambda item: item.importance.score, reverse=True)
