from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any, TypeVar

T = TypeVar("T")


class TTLCache:
    def __init__(self, max_entries: int = 512) -> None:
        self._items: dict[str, tuple[float, bytes]] = {}
        self._max_entries = max_entries

    async def get(self, key: str) -> bytes | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= monotonic():
            self._items.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: bytes, ttl_s: int) -> None:
        if len(self._items) >= self._max_entries:
            self._evict()
        self._items[key] = (monotonic() + ttl_s, value)

    def _evict(self) -> None:
        now = monotonic()
        for key in [key for key, (expires, _) in self._items.items() if expires <= now]:
            self._items.pop(key, None)
        if len(self._items) >= self._max_entries:
            oldest = min(self._items, key=lambda key: self._items[key][0])
            self._items.pop(oldest, None)

    def clear(self) -> None:
        self._items.clear()


class SingleFlight:
    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future[Any]] = {}

    async def run(self, key: str, factory: Callable[[], Awaitable[T]]) -> T:
        existing = self._inflight.get(key)
        if existing is not None:
            return await existing
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            result = await factory()
        except BaseException as error:
            self._inflight.pop(key, None)
            if not future.done():
                future.set_exception(error)
                future.exception()
            raise
        self._inflight.pop(key, None)
        if not future.done():
            future.set_result(result)
        return result
