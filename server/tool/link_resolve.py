from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from tool.http import HttpClient


class GoogleNewsLinkResolver:
    def __init__(self, http: HttpClient | None = None, *, decoder=None):
        self._http = http
        if decoder is not None:
            self._decoder = decoder
            return
        try:
            from googlenewsdecoder import gnewsdecoder
        except ImportError:
            gnewsdecoder = None
        self._decoder = gnewsdecoder

    async def resolve(self, url: str) -> str | None:
        if not self._is_google_news(url):
            return url
        if self._decoder is None:
            return None
        try:
            result = await asyncio.to_thread(self._decoder, url, timeout=10.0)
        except Exception:  # noqa: BLE001
            return None
        decoded = self._decoded_url(result)
        if decoded is None:
            return None
        parts = urlsplit(decoded)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return None
        return decoded

    @staticmethod
    def _decoded_url(result) -> str | None:
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            if result.get("decoded_url"):
                return str(result["decoded_url"])
            if result.get("url"):
                return str(result["url"])
        return None

    @staticmethod
    def _is_google_news(url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return host == "news.google.com" or host.endswith(".news.google.com")
