from __future__ import annotations

from time import monotonic
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from Core.settings import Settings
from tool.http import HttpClient


class RobotsCache:
    def __init__(self, http: HttpClient, settings: Settings):
        self._http = http
        self._settings = settings
        self._cache: dict[str, tuple[RobotFileParser, float]] = {}

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return False
        parser = await self._parser(f"{parts.scheme}://{parts.netloc}")
        return parser.can_fetch(self._settings.http_user_agent, url)

    async def _parser(self, origin: str) -> RobotFileParser:
        now = monotonic()
        cached = self._cache.get(origin)
        if cached is not None and cached[1] > now:
            return cached[0]

        parser = RobotFileParser()
        parser.set_url(f"{origin}/robots.txt")
        try:
            response = await self._http.get(
                parser.url, cache_ttl_s=self._settings.robots_cache_ttl_s
            )
            if response.status < 400:
                parser.parse(response.body.decode("utf-8", errors="ignore").splitlines())
            else:
                parser.parse([])
        except Exception:  # noqa: BLE001
            parser.parse([])
        self._cache[origin] = (parser, now + self._settings.robots_cache_ttl_s)
        return parser
