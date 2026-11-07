from __future__ import annotations

from Core.models import ExtractedText, FetchedPage


class TrafilaturaExtractor:
    def extract(self, page: FetchedPage) -> ExtractedText:
        raise NotImplementedError("text extraction lands in the enrichment slice")
