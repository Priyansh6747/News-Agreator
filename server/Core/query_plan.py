from __future__ import annotations

from Core.models import QueryClass, QueryPlan
from Core.ports import DecisionEngine
from Core.registry import SourceRegistry
from Core.settings import Settings

EXTRAS: dict[QueryClass, tuple[str, ...]] = {
    QueryClass.MARKET: ("price today", "market analysis"),
    QueryClass.EVENT: ("latest news", "timeline"),
    QueryClass.GEOPOLITICS: ("latest", "analysis"),
    QueryClass.COMPANY: ("earnings", "stock news"),
    QueryClass.COMPARISON: ("comparison", "analysis"),
    QueryClass.OTHER: ("news", "latest"),
}


def _dedupe(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def expand_phrasings(query: str, query_class: QueryClass, limit: int) -> list[str]:
    candidates = [query, *(f"{query} {extra}" for extra in EXTRAS[query_class]), f'"{query}"']
    return _dedupe(candidates)[: max(limit, 1)]


async def plan_query(
    query: str,
    *,
    decisions: DecisionEngine,
    registry: SourceRegistry,
    settings: Settings,
) -> QueryPlan:
    normalized = " ".join(query.split())
    analysis = await decisions.analyze_query(normalized)
    query_class = analysis.query_class
    if settings.sensitivity_hours:
        index = min(analysis.time_sensitivity, len(settings.sensitivity_hours) - 1)
        freshness = settings.sensitivity_hours[index]
    else:
        freshness = settings.freshness_by_class.get(
            query_class.value, settings.default_freshness_hours
        )
    phrasings = expand_phrasings(normalized, query_class, settings.query_phrasings)
    domains = registry.tier1_2_domains(limit=settings.site_scoped_queries)
    site_scoped = [f"{normalized} site:{domain}" for domain in domains]
    return QueryPlan(
        query=query,
        normalized=normalized,
        query_class=query_class,
        time_sensitivity=analysis.time_sensitivity,
        intent=analysis.intent,
        brief_schema=analysis.brief_schema,
        freshness_hours=freshness,
        phrasings=phrasings,
        site_scoped=site_scoped,
    )
