from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from tool.bing_news import build_query_url as bing_url
from tool.bing_news import decode_redirect
from tool.gdelt import build_query_url as gdelt_url
from tool.google_news import build_query_url as google_url

TARGET = "https://www.reuters.com/markets/commodities/gold"
START = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
END = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def test_google_news_url_encodes_query() -> None:
    url = google_url("gold prices")
    assert url.startswith("https://news.google.com/rss/search?")
    assert "q=gold+prices" in url
    assert "ceid=US%3Aen" in url


def test_google_news_url_appends_when_window() -> None:
    url = google_url("gold prices", when="30d")
    assert "when%3A30d" in url


def test_bing_url_requests_rss() -> None:
    url = bing_url("gold prices")
    assert url.startswith("https://www.bing.com/news/search?")
    assert "format=rss" in url


def test_bing_redirect_decodes_target() -> None:
    redirect = f"https://www.bing.com/news/apiclick.aspx?url={quote(TARGET, safe='')}"
    assert decode_redirect(redirect) == TARGET


def test_bing_redirect_ignores_other_hosts() -> None:
    assert decode_redirect("https://example.com/?url=https%3A%2F%2Ffoo.com") is None


def test_gdelt_url_uses_artlist_window() -> None:
    url = gdelt_url("gold prices", start=START, end=END)
    assert url.startswith("https://api.gdeltproject.org/api/v2/doc/doc?")
    assert "mode=artlist" in url
    assert "format=json" in url
    assert "maxrecords=250" in url
    assert "startdatetime=20261010120000" in url
    assert "enddatetime=20261106120000" in url
