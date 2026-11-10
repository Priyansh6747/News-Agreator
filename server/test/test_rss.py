from __future__ import annotations

from pathlib import Path

import pytest

from Core.errors import FeedParseError
from Core.models import Backend
from tool.rss import parse_feed

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_parses_items_and_applies_date_gate(now) -> None:
    result = parse_feed(
        read("rss_basic.xml"),
        backend=Backend.PUBLISHER_RSS,
        max_items=20,
        now=now,
        default_publisher="BBC News",
        publisher_domain="bbc.com",
    )
    assert result.raw_count == 4
    assert len(result.items) == 2
    assert result.drops == {"undated": 1, "future_date": 1}

    by_title = {item.title: item for item in result.items}
    gold = by_title["Gold rises & dollar slips"]
    assert gold.publisher == "BBC News"
    assert gold.url == "https://bbc.com/news/business-1"
    assert gold.snippet == "Gold prices rose on Friday as the dollar softened against major peers."
    assert gold.backend is Backend.PUBLISHER_RSS
    assert by_title["Click counter"].url == "https://bbc.com/news/real-story"


def test_item_cap_counts_only_in_window_items(now) -> None:
    result = parse_feed(
        read("rss_basic.xml"),
        backend=Backend.PUBLISHER_RSS,
        max_items=1,
        now=now,
        publisher_domain="bbc.com",
    )
    assert [item.title for item in result.items] == ["Gold rises & dollar slips"]
    assert result.drops["feed_cap"] == 1
    assert result.drops["undated"] == 1


def test_oldest_cutoff_keeps_feed_history(now) -> None:
    result = parse_feed(
        read("rss_basic.xml"),
        backend=Backend.PUBLISHER_RSS,
        max_items=20,
        now=now,
        publisher_domain="bbc.com",
        oldest=now.replace(hour=9, minute=30, second=0),
    )
    assert [item.title for item in result.items] == ["Gold rises & dollar slips"]
    assert result.drops == {"undated": 1, "future_date": 1, "too_old": 1}


def test_html_challenge_is_rejected(now) -> None:
    with pytest.raises(FeedParseError):
        parse_feed(
            read("html_challenge.html"),
            backend=Backend.GOOGLE_NEWS,
            max_items=20,
            now=now,
        )


def test_publisher_link_gate(now) -> None:
    result = parse_feed(
        read("publisher_mismatch.xml"),
        backend=Backend.PUBLISHER_RSS,
        max_items=20,
        now=now,
        publisher_domain="bbc.com",
    )
    assert result.items == []
    assert result.drops == {"publisher_mismatch": 1}


def test_google_source_and_resolution_flag(now) -> None:
    result = parse_feed(
        read("google_news.xml"),
        backend=Backend.GOOGLE_NEWS,
        max_items=20,
        now=now,
        needs_resolution=True,
    )
    assert len(result.items) == 2
    assert {item.publisher for item in result.items} == {"Reuters", "BBC News"}
    assert all(item.needs_resolution for item in result.items)


def test_bing_news_source_field(now) -> None:
    result = parse_feed(
        read("bing_news.xml"),
        backend=Backend.BING_NEWS,
        max_items=20,
        now=now,
    )
    assert len(result.items) == 1
    item = result.items[0]
    assert item.publisher == "CNBC"
    assert item.snippet
    assert "apiclick" in item.url
