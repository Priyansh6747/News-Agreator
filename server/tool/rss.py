from __future__ import annotations

import calendar
import html
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import feedparser

from Core.errors import FeedParseError
from Core.models import Backend, RawItem, SearchResult
from Core.urls import canonical_url, publisher_matches

ACCEPTED_SHAPES = ("<rss", "<feed", "<rdf:rdf")
REJECTED_SHAPES = ("<!doctype html", "<html")
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def _looks_like_feed(xml: bytes) -> bool:
    head = xml[:2048].decode("utf-8", errors="ignore").lower()
    if any(marker in head for marker in REJECTED_SHAPES):
        return False
    return any(marker in head for marker in ACCEPTED_SHAPES)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(TAG_RE.sub(" ", value))
    return SPACE_RE.sub(" ", text).strip()


def _entry_link(entry: dict) -> str | None:
    link = entry.get("link")
    if link:
        return str(link).strip()
    for candidate in entry.get("links", []):
        if candidate.get("rel") in (None, "alternate") and candidate.get("href"):
            return str(candidate["href"]).strip()
    return None


def _unwrap_link(link: str) -> str:
    marker = link.find("*http")
    if marker >= 0:
        return link[marker + 1 :]
    return link


def _is_http(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _entry_date(entry: dict) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)


def _entry_publisher(entry: dict) -> str | None:
    for key in ("source", "news_source"):
        value = entry.get(key)
        if isinstance(value, dict):
            title = value.get("title") or value.get("href")
            if title:
                return str(title)
        elif isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _entry_snippet(entry: dict, title: str) -> str | None:
    value = entry.get("summary") or entry.get("description")
    if not value:
        content = entry.get("content")
        if isinstance(content, list) and content:
            value = content[0].get("value")
    text = _clean_text(value)
    if not text or len(text) < 40:
        return None
    if text.lower() == title.lower():
        return None
    return text[:400]


def parse_feed(
    xml: bytes,
    *,
    backend: Backend,
    max_items: int,
    now: datetime,
    future_tolerance_h: int = 1,
    default_publisher: str | None = None,
    publisher_domain: str | None = None,
    needs_resolution: bool = False,
) -> SearchResult:
    if not _looks_like_feed(xml):
        raise FeedParseError("response is not an RSS or Atom document")

    parsed = feedparser.parse(xml)
    entries = parsed.get("entries", [])
    raw_count = len(entries)
    if not entries and parsed.get("bozo"):
        raise FeedParseError(str(parsed.get("bozo_exception", "unknown parse error")))

    drops: dict[str, int] = {}
    items: list[RawItem] = []
    future_limit = now + timedelta(hours=future_tolerance_h)

    for index, entry in enumerate(entries):
        if index >= max_items:
            drops["feed_cap"] = drops.get("feed_cap", 0) + (raw_count - max_items)
            break
        title = _clean_text(entry.get("title"))
        if not title:
            drops["title"] = drops.get("title", 0) + 1
            continue
        link = _entry_link(entry)
        if not link:
            drops["link"] = drops.get("link", 0) + 1
            continue
        link = _unwrap_link(link)
        if not _is_http(link):
            drops["link"] = drops.get("link", 0) + 1
            continue
        if publisher_domain and not publisher_matches(link, publisher_domain):
            drops["publisher_mismatch"] = drops.get("publisher_mismatch", 0) + 1
            continue
        published_at = _entry_date(entry)
        if published_at is None:
            drops["undated"] = drops.get("undated", 0) + 1
            continue
        if published_at > future_limit:
            drops["future_date"] = drops.get("future_date", 0) + 1
            continue

        items.append(
            RawItem(
                title=title,
                url=canonical_url(link),
                publisher=_entry_publisher(entry) or default_publisher,
                snippet=_entry_snippet(entry, title),
                published_at=published_at,
                backend=backend,
                needs_resolution=needs_resolution,
            )
        )

    return SearchResult(items=items, raw_count=raw_count, drops=drops)
