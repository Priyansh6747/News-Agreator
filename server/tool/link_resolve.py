from __future__ import annotations

from tool.http import HttpClient


class GoogleNewsLinkResolver:
    def __init__(self, http: HttpClient):
        self._http = http

    async def resolve(self, url: str) -> str | None:
        raise NotImplementedError("link resolution lands in the enrichment slice")
