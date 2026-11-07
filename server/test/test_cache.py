from __future__ import annotations

from tool.cache import TTLCache


async def test_expired_entry_is_missing() -> None:
    cache = TTLCache()
    await cache.set("key", b"value", 0)
    assert await cache.get("key") is None


async def test_evicts_when_full() -> None:
    cache = TTLCache(max_entries=2)
    await cache.set("a", b"1", 60)
    await cache.set("b", b"2", 60)
    await cache.set("c", b"3", 60)
    assert await cache.get("a") is None
    assert await cache.get("b") == b"2"
    assert await cache.get("c") == b"3"
