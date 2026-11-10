from __future__ import annotations

import json
from datetime import datetime, timedelta

from Core.models import (
    Article,
    CredibilityScore,
    ImportanceScore,
    StoryCluster,
)
from Core.prompts import ExtractedFacts, build_brief_prompt
from test.helpers import NOW, make_candidate


def cluster(identifier: str, published_at: datetime) -> StoryCluster:
    candidate = make_candidate(
        title=f"Gold {identifier}",
        url=f"https://www.reuters.com/{identifier}",
        published_at=published_at,
    )
    return StoryCluster(
        id=identifier,
        headline=candidate.title,
        members=[Article(candidate=candidate, canonical_url=candidate.url)],
        importance=ImportanceScore(score=1.0),
        credibility=CredibilityScore(score=1.0),
        first_seen=published_at,
        last_seen=published_at,
    )


def test_prompt_marks_context_clusters_as_background() -> None:
    prompt = build_brief_prompt(
        "gold",
        [
            cluster("current", NOW - timedelta(hours=1)),
            cluster("background", NOW - timedelta(days=5)),
        ],
        now=NOW,
        freshness_hours=24,
    )
    payload = json.loads(prompt.split("only:\n", 1)[1])
    background = {item["cluster_id"]: item["background"] for item in payload}
    assert background == {"current": False, "background": True}


def test_normalizes_top_level_list_with_aliases() -> None:
    result = ExtractedFacts.model_validate(
        [{"fact": "Gold rose", "number": "4.5%", "evidence": "Gold rose 4.5%."}]
    )
    assert len(result.facts) == 1
    assert result.facts[0].claim == "Gold rose"
    assert result.facts[0].value == "4.5%"
    assert result.facts[0].quote == "Gold rose 4.5%."


def test_normalizes_items_key() -> None:
    result = ExtractedFacts.model_validate({"items": [{"claim": "Gold fell"}]})
    assert result.facts[0].claim == "Gold fell"


def test_ignores_extra_keys() -> None:
    result = ExtractedFacts.model_validate(
        {"facts": [{"claim": "Gold rose", "source": "article"}]}
    )
    assert result.facts[0].claim == "Gold rose"
    assert result.facts[0].value is None
