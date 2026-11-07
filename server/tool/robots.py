from __future__ import annotations

from tool.http import HttpClient


class RobotsCache:
    def __init__(self, http: HttpClient):
        self._http = http

    async def allowed(self, url: str) -> bool:
        raise NotImplementedError("robots.txt checks land in the enrichment slice")
