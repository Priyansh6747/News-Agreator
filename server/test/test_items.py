from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from Core.items import select_with_context

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


@dataclass
class Item:
    name: str
    published_at: datetime | None


def test_keeps_newest_plus_evenly_spaced_context() -> None:
    fresh = [Item(f"fresh-{index}", NOW - timedelta(minutes=index)) for index in range(10)]
    older = [
        Item(f"old-{index}", NOW - timedelta(days=index + 1)) for index in range(25)
    ]
    selected = select_with_context(
        fresh + older,
        limit=8,
        now=NOW,
        freshness_hours=1,
        context_share=0.25,
    )
    names = {item.name for item in selected}
    assert len(selected) == 8
    assert len([name for name in names if name.startswith("fresh")]) == 6
    assert "old-0" in names
    assert "old-24" in names


def test_returns_all_items_when_under_limit() -> None:
    items = [Item("a", NOW), Item("b", NOW - timedelta(days=1))]
    assert select_with_context(
        items, limit=5, now=NOW, freshness_hours=24, context_share=0.25
    ) == items


def test_without_context_keeps_newest_items() -> None:
    items = [Item(f"fresh-{index}", NOW - timedelta(minutes=index)) for index in range(10)]
    selected = select_with_context(
        items, limit=3, now=NOW, freshness_hours=24, context_share=0.25
    )
    assert [item.name for item in selected] == ["fresh-0", "fresh-1", "fresh-2"]


def test_short_fresh_set_fills_from_context() -> None:
    fresh = [Item("fresh-0", NOW), Item("fresh-1", NOW - timedelta(minutes=1))]
    older = [
        Item(f"old-{index}", NOW - timedelta(days=index + 1)) for index in range(10)
    ]
    selected = select_with_context(
        fresh + older,
        limit=6,
        now=NOW,
        freshness_hours=1,
        context_share=0.5,
    )
    assert len(selected) == 6
    assert "fresh-0" in {item.name for item in selected}
    assert "fresh-1" in {item.name for item in selected}
