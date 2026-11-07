from __future__ import annotations

import pytest

from Core.models import BriefSchema, QueryClass, QueryIntent
from Core.query_plan import plan_query
from Core.registry import SourceRegistry
from Core.settings import Settings
from tool.decisions_heuristic import HeuristicDecisionEngine

CASES = [
    ("gold prices", QueryClass.MARKET),
    ("earthquake in japan", QueryClass.EVENT),
    ("nato sanctions", QueryClass.GEOPOLITICS),
    ("apple earnings", QueryClass.COMPANY),
    ("nvidia vs amd", QueryClass.COMPARISON),
    ("weather tomorrow", QueryClass.OTHER),
]


@pytest.mark.parametrize(("query", "expected"), CASES)
async def test_classifies_query(
    query: str,
    expected: QueryClass,
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    plan = await plan_query(
        query,
        decisions=HeuristicDecisionEngine(),
        registry=registry,
        settings=settings,
    )
    assert plan.query_class is expected


async def test_market_plan_has_window_phrasings_and_sites(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    plan = await plan_query(
        "gold prices",
        decisions=HeuristicDecisionEngine(),
        registry=registry,
        settings=settings,
    )
    assert plan.freshness_hours == settings.sensitivity_hours[3]
    assert plan.time_sensitivity == 3
    assert plan.intent is QueryIntent.PRICE_CHECK
    assert plan.brief_schema is BriefSchema.PRICE_TABLE
    assert plan.phrasings[0] == "gold prices"
    assert len(plan.phrasings) <= settings.query_phrasings
    assert len(plan.site_scoped) == settings.site_scoped_queries
    assert all("site:" in query for query in plan.site_scoped)


async def test_explainer_uses_evergreen_window(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    plan = await plan_query(
        "what is inflation",
        decisions=HeuristicDecisionEngine(),
        registry=registry,
        settings=settings,
    )
    assert plan.intent is QueryIntent.EXPLAINER
    assert plan.time_sensitivity == 0
    assert plan.brief_schema is BriefSchema.GENERAL_BRIEF
    assert plan.freshness_hours == settings.sensitivity_hours[0]


async def test_normalizes_whitespace(
    settings: Settings,
    registry: SourceRegistry,
) -> None:
    plan = await plan_query(
        "  gold   prices  ",
        decisions=HeuristicDecisionEngine(),
        registry=registry,
        settings=settings,
    )
    assert plan.normalized == "gold prices"
    assert plan.phrasings[0] == "gold prices"
