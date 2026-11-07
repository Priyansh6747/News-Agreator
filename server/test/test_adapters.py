from __future__ import annotations

from urllib.parse import quote

from tool.bing_news import build_query_url as bing_url
from tool.bing_news import decode_redirect
from tool.gdelt import build_query_url as gdelt_url
from tool.google_news import build_query_url as google_url

TARGET = "https://www.reuters.com/markets/commodities/gold"


def test_google_news_url_encodes_query() -> None:
    url = google_url("gold prices")
    assert url.startswith("https://news.google.com/rss/search?")
    assert "q=gold+prices" in url
    assert "ceid=US%3Aen" in url


def test_bing_url_requests_rss() -> None:
    url = bing_url("gold prices")
    assert url.startswith("https://www.bing.com/news/search?")
    assert "format=rss" in url


def test_bing_redirect_decodes_target() -> None:
    redirect = f"https://www.bing.com/news/apiclick.aspx?url={quote(TARGET, safe='')}"
    assert decode_redirect(redirect) == TARGET


def test_bing_redirect_ignores_other_hosts() -> None:
    assert decode_redirect("https://example.com/?url=https%3A%2F%2Ffoo.com") is None


def test_gdelt_url_uses_artlist() -> None:
    url = gdelt_url("gold prices")
    assert url.startswith("https://api.gdeltproject.org/api/v2/doc/doc?")
    assert "mode=artlist" in url
    assert "format=json" in url
    assert "maxrecords=250" in url
