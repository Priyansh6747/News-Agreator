from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol


class Dated(Protocol):
    published_at: datetime | None


def _sort_key(item: Dated, fallback: datetime) -> datetime:
    return item.published_at or fallback


def select_with_context[ItemT: Dated](
    items: list[ItemT],
    *,
    limit: int,
    now: datetime,
    freshness_hours: int,
    context_share: float = 0.25,
) -> list[ItemT]:
    if limit <= 0:
        return []
    if len(items) <= limit:
        return list(items)

    fallback = datetime.min.replace(tzinfo=now.tzinfo)
    ordered = sorted(items, key=lambda item: _sort_key(item, fallback), reverse=True)
    cutoff = now - timedelta(hours=max(freshness_hours, 0))
    fresh = [
        item
        for item in ordered
        if item.published_at is None or item.published_at >= cutoff
    ]
    older = [
        item
        for item in ordered
        if item.published_at is not None and item.published_at < cutoff
    ]

    context_quota = min(len(older), max(0, int(limit * context_share)))
    if context_quota == 0:
        selected = fresh[:limit]
    else:
        if context_quota == 1 or context_quota >= len(older):
            context = older[:context_quota]
        else:
            step = (len(older) - 1) / (context_quota - 1)
            context = [older[round(index * step)] for index in range(context_quota)]
        selected = fresh[: limit - len(context)] + context
        if len(selected) < limit:
            chosen = {id(item) for item in selected}
            for item in older:
                if id(item) in chosen:
                    continue
                selected.append(item)
                if len(selected) >= limit:
                    break

    selected.sort(key=lambda item: _sort_key(item, fallback), reverse=True)
    return selected
