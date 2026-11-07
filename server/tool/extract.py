from __future__ import annotations

import re

import trafilatura

from Core.errors import ExtractionFailed
from Core.models import ExtractedText, FetchedPage

PAYWALL_MARKERS = (
    "subscribe to continue",
    "sign in to continue",
    "create a free account",
    "already a subscriber",
    "this article is for subscribers",
    "subscription required",
)


class TrafilaturaExtractor:
    def __init__(self, *, min_chars: int = 200):
        self._min_chars = min_chars

    def extract(self, page: FetchedPage) -> ExtractedText:
        text = trafilatura.extract(
            page.html,
            url=page.final_url or page.url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            output_format="txt",
        )
        if not text:
            raise ExtractionFailed("no main text found")
        cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(cleaned) < self._min_chars:
            raise ExtractionFailed("extracted text is too short")

        lowered = cleaned.lower()
        markers = sum(1 for marker in PAYWALL_MARKERS if marker in lowered)
        if markers >= 2:
            raise ExtractionFailed("paywall markers in extracted text")

        word_count = len(cleaned.split())
        return ExtractedText(
            text=cleaned,
            title=None,
            published_at=None,
            word_count=word_count,
            quality=min(1.0, word_count / 300),
        )
