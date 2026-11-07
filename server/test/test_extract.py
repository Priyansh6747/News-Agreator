from __future__ import annotations

import pytest

from Core.errors import ExtractionFailed
from Core.models import FetchedPage
from tool.extract import TrafilaturaExtractor


def page(html: str) -> FetchedPage:
    return FetchedPage(
        url="https://www.bbc.com/news/gold",
        final_url="https://www.bbc.com/news/gold",
        status=200,
        content_type="text/html",
        html=html,
    )


def test_extracts_article_text() -> None:
    paragraphs = "".join(
        f"<p>Gold prices rose in session {index} as the dollar weakened and "
        f"traders weighed the path for interest rates.</p>"
        for index in range(10)
    )
    body = f"<html><body><article><h1>Gold rises</h1>{paragraphs}</article></body></html>"
    extracted = TrafilaturaExtractor().extract(page(body))
    assert "Gold prices" in extracted.text
    assert extracted.word_count > 10
    assert 0.0 < extracted.quality <= 1.0


def test_empty_page_raises() -> None:
    with pytest.raises(ExtractionFailed):
        TrafilaturaExtractor().extract(
            page("<html><body><nav>Menu</nav></body></html>")
        )


def test_paywall_markers_raise() -> None:
    body = (
        "<html><body><article><h1>Gold rises</h1>"
        "<p>Gold prices rose as the dollar weakened.</p>"
        "<p>Subscribe to continue reading. Already a subscriber? Sign in to continue.</p>"
        "</article></body></html>"
    )
    with pytest.raises(ExtractionFailed):
        TrafilaturaExtractor().extract(page(body))
