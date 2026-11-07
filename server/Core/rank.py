from __future__ import annotations

import re
from datetime import timedelta

from Core.coverage import CoverageCollector
from Core.models import Candidate, QueryPlan
from Core.ports import Clock, DecisionEngine
from Core.settings import Settings


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2}


def _lexical_relevance(query: str, candidate: Candidate) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    text = f"{candidate.title} {candidate.snippet or ''}"
    return len(query_tokens & _tokens(text)) / len(query_tokens)


def _cheap_score(
    candidate: Candidate,
    *,
    query: str,
    now,
    window,
    settings: Settings,
) -> float:
    tier = settings.tier_scores.get(candidate.tier.value, 0.4)
    if candidate.published_at is None or not window.total_seconds():
        recency = 0.0
    else:
        age = now - candidate.published_at
        recency = _clamp(1.0 - age / window)
    weights = settings.pre_rank_weights
    return (
        weights["relevance"] * _lexical_relevance(query, candidate)
        + weights["tier"] * tier
        + weights["recency"] * recency
    )


async def rank_candidates(
    candidates: list[Candidate],
    *,
    plan: QueryPlan,
    decisions: DecisionEngine,
    settings: Settings,
    coverage: CoverageCollector,
    clock: Clock,
    assess_top: int | None = None,
) -> list[Candidate]:
    now = clock.now()
    window = timedelta(hours=plan.freshness_hours)
    future_limit = now + timedelta(hours=settings.future_date_tolerance_h)
    oldest = now - window

    kept: list[Candidate] = []
    for candidate in candidates:
        if candidate.published_at is None:
            if settings.drop_undated:
                coverage.add_drop("undated", backend=candidate.backend)
                continue
            kept.append(candidate)
            continue
        if candidate.published_at > future_limit:
            coverage.add_drop("future_date", backend=candidate.backend)
            continue
        if candidate.published_at < oldest:
            coverage.add_drop("out_of_window", backend=candidate.backend)
            continue
        kept.append(candidate)

    if assess_top is not None and len(kept) > assess_top:
        kept.sort(
            key=lambda item: _cheap_score(
                item,
                query=plan.normalized,
                now=now,
                window=window,
                settings=settings,
            ),
            reverse=True,
        )
        coverage.add_drop("assess_cap", len(kept) - assess_top)
        kept = kept[:assess_top]

    assessments = await decisions.assess(plan.normalized, kept)
    weights = settings.rank_weights
    scored: list[Candidate] = []
    for candidate, assessment in zip(kept, assessments):
        candidate.relevance = _clamp(assessment.relevance)
        if candidate.relevance < settings.min_candidate_relevance:
            coverage.add_drop("low_relevance", backend=candidate.backend)
            continue
        candidate.article_type = assessment.article_type
        type_weight = settings.type_weights.get(assessment.article_type.value, 0.9)
        effective_relevance = candidate.relevance * type_weight
        tier = settings.tier_scores.get(candidate.tier.value, 0.4)
        if candidate.published_at is None:
            recency = 1.0
        else:
            age = now - candidate.published_at
            recency = _clamp(1.0 - age / window) if window.total_seconds() else 0.0
        candidate.score = _clamp(
            weights["relevance"] * effective_relevance
            + weights["tier"] * tier
            + weights["recency"] * recency
        )
        scored.append(candidate)
    kept = scored

    kept.sort(key=lambda item: (item.score or 0.0, item.published_at or now), reverse=True)
    if len(kept) > settings.select_top:
        coverage.add_drop("rank_cap", len(kept) - settings.select_top)
        kept = kept[: settings.select_top]
    return kept
