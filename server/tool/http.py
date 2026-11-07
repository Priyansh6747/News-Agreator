from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import monotonic, perf_counter
from urllib.parse import urljoin, urlsplit

import httpx

from Core.errors import HttpBodyTooLarge, HttpError, HttpTimeout
from Core.settings import Settings
from tool.cache import SingleFlight, TTLCache

ACCEPT = "application/rss+xml, application/xml, text/xml, application/json;q=0.8, */*"
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass(slots=True)
class HttpResponse:
    url: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    elapsed_ms: int = 0
    from_cache: bool = False


class HttpClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            timeout=settings.fetch_timeout_s,
        )
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}
        self._cache = TTLCache(max_entries=512)
        self._flight = SingleFlight()

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout_s: float | None = None,
        cache_ttl_s: int | None = None,
    ) -> HttpResponse:
        ttl = self._settings.query_cache_ttl_s if cache_ttl_s is None else cache_ttl_s
        if ttl <= 0:
            return await self._fetch(url, headers, timeout_s, ttl)
        cached = await self._cache.get(url)
        if cached is not None:
            return HttpResponse(url=url, status=200, body=cached, from_cache=True)
        return await self._flight.run(
            url, lambda: self._fetch(url, headers, timeout_s, ttl)
        )

    async def _fetch(
        self,
        url: str,
        headers: dict[str, str] | None,
        timeout_s: float | None,
        ttl: int,
    ) -> HttpResponse:
        host = self._host(url)
        semaphore = self._semaphores.setdefault(
            host, asyncio.Semaphore(self._settings.per_domain_concurrency)
        )
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with semaphore, lock:
            await self._wait_turn(host)
            response = await self._request(url, headers, timeout_s)
        if ttl > 0 and response.status == 200 and response.body:
            await self._cache.set(url, response.body, ttl)
        return response

    async def _wait_turn(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            wait = self._settings.per_domain_min_spacing_s - (monotonic() - last)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_request[host] = monotonic()

    async def _request(
        self,
        url: str,
        headers: dict[str, str] | None,
        timeout_s: float | None,
    ) -> HttpResponse:
        started = perf_counter()
        current = url
        request_headers = {
            "User-Agent": self._settings.http_user_agent,
            "Accept": ACCEPT,
            "Accept-Language": "en-US,en;q=0.9",
            **(headers or {}),
        }
        timeout = httpx.Timeout(timeout_s or self._settings.fetch_timeout_s)

        for _ in range(self._settings.http_max_redirects + 1):
            parts = urlsplit(current)
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                raise HttpError(current, "unsupported scheme")
            try:
                async with self._client.stream(
                    "GET", current, headers=request_headers, timeout=timeout
                ) as response:
                    if response.status_code in REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise HttpError(current, "redirect without location")
                        current = urljoin(current, location)
                        continue
                    body = await self._read_body(response, current)
                    return HttpResponse(
                        url=current,
                        status=response.status_code,
                        headers=dict(response.headers),
                        body=body,
                        elapsed_ms=int((perf_counter() - started) * 1000),
                    )
            except httpx.TimeoutException as error:
                raise HttpTimeout(current) from error
            except httpx.HTTPError as error:
                raise HttpError(current, type(error).__name__) from error

        raise HttpError(url, "too many redirects")

    async def _read_body(self, response: httpx.Response, url: str) -> bytes:
        limit = int(self._settings.body_cap_mb * 1024 * 1024)
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > limit:
                raise HttpBodyTooLarge(url, limit)
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _host(url: str) -> str:
        return (urlsplit(url).hostname or "").lower()

    async def aclose(self) -> None:
        await self._client.aclose()
