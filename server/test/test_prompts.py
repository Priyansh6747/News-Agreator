from __future__ import annotations

from Core.prompts import ExtractedFacts


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
