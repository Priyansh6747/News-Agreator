from __future__ import annotations

from Core.models import RawItem
from Core.urls import canonical_url, normalize_title


def dedupe_items(items: list[RawItem]) -> tuple[list[RawItem], int]:
    seen: set[str] = set()
    kept: list[RawItem] = []
    dropped = 0
    for item in items:
        keys = [f"url:{canonical_url(item.url)}"]
        title = normalize_title(item.title)
        if title:
            keys.append(f"title:{title}")
        if any(key in seen for key in keys):
            dropped += 1
            continue
        seen.update(keys)
        kept.append(item)
    return kept, dropped
