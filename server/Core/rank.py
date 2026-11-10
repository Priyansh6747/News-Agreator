from __future__ import annotations

import re
from datetime import timedelta

from Core.coverage import CoverageCollector
from Core.items import select_with_context
from Core.models import ArticleType, Candidate, QueryPlan
from Core.ports import Clock, DecisionEngine, ProgressCallback
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


def _final_score(
    candidate: Candidate,
    *,
    weights: dict[str, float],
    settings: Settings,
    now,
    window,
) -> float:
    article_type = candidate.article_type or ArticleType.UNKNOWN
    type_weight = settings.type_weights.get(article_type.value, 0.9)
    tier = settings.tier_scores.get(candidate.tier.value, 0.4)
    if candidate.published_at is None:
        recency = 1.0
    else:
        age = now - candidate.published_at
        recency = _clamp(1.0 - age / window) if window.total_seconds() else 0.0
    return _clamp(
        weights["relevance"] * (candidate.relevance or 0.0) * type_weight
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
    type_top: int | None = None,
    on_progress: ProgressCallback | None = None,
) -> list[Candidate]:
    step_total = 2 if type_top is not None else 1
    now = clock.now()
    window = timedelta(hours=plan.freshness_hours)
    fresh_cutoff = now - window
    future_limit = now + timedelta(hours=settings.future_date_tolerance_h)
    oldest = now - timedelta(hours=plan.lookback)

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

    relevances = await decisions.relevance(plan.normalized, kept)
    if on_progress is not None:
        await on_progress(1, step_total)
    weights = settings.rank_weights
    scored: list[Candidate] = []
    for candidate, relevance in zip(kept, relevances):
        candidate.relevance = _clamp(relevance)
        threshold = settings.min_relevance_by_tier.get(
            candidate.tier.value, settings.min_candidate_relevance
        )
        if candidate.relevance < threshold:
            coverage.add_drop("low_relevance", backend=candidate.backend)
            continue
        candidate.article_type = None
        candidate.score = _final_score(
            candidate, weights=weights, settings=settings, now=now, window=window
        )
        scored.append(candidate)

    scored.sort(
        key=lambda item: (item.score or 0.0, item.published_at or now),
        reverse=True,
    )

    if type_top is not None and scored:
        typed = scored[:type_top]
        types = await decisions.article_types(typed)
        for candidate, article_type in zip(typed, types):
            candidate.article_type = article_type
        for candidate in scored:
            candidate.score = _final_score(
                candidate, weights=weights, settings=settings, now=now, window=window
            )
        scored.sort(
            key=lambda item: (item.score or 0.0, item.published_at or now),
            reverse=True,
        )
        if on_progress is not None:
            await on_progress(2, step_total)

    fresh = [
        candidate
        for candidate in scored
        if candidate.published_at is None or candidate.published_at >= fresh_cutoff
    ]
    context = [
        candidate
        for candidate in scored
        if candidate.published_at is not None and candidate.published_at < fresh_cutoff
    ]
    fresh_take = fresh[: settings.select_top]
    context_room = (
        settings.select_top - len(fresh_take)
        if len(fresh_take) < settings.select_top
        else max(0, settings.context_top)
    )
    context_take = select_with_context(
        context,
        limit=context_room,
        now=now,
        freshness_hours=0,
        context_share=1.0,
    )
    if len(fresh) > len(fresh_take):
        coverage.add_drop("rank_cap", len(fresh) - len(fresh_take))
    if len(context) > len(context_take):
        coverage.add_drop("context_cap", len(context) - len(context_take))
    return fresh_take + context_take
