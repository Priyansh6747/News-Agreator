from __future__ import annotations

from Core.models import FetchedPage
from Core.registry import SourceRegistry
from Core.settings import Settings
from tool.http import HttpClient


class HtmlArticleFetcher:
    def __init__(self, http: HttpClient, registry: SourceRegistry, settings: Settings):
        self._http = http
        self._registry = registry
        self._settings = settings

    async def fetch(self, url: str) -> FetchedPage:
        raise NotImplementedError("article fetching lands in the enrichment slice")
