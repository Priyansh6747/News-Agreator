from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from Core.models import Backend, ExtractedText, FetchedPage, QueryPlan, RawItem, SearchResult
from Core.prompts import BriefDraft, ChatDecision, ChatToolCall, ExtractedFacts

DEMO_PATH = Path(__file__).resolve().parents[1] / "Core" / "data" / "demo_candidates.json"


class StaticClock:
    def __init__(self, now: datetime):
        self._now = now

    def now(self) -> datetime:
        return self._now


def load_demo_items(backend: Backend, now: datetime) -> list[RawItem]:
    payload = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    items: list[RawItem] = []
    for entry in payload["items"]:
        if entry["backend"] != backend.value:
            continue
        items.append(
            RawItem(
                title=entry["title"],
                url=entry["url"],
                publisher=entry.get("publisher"),
                snippet=entry.get("snippet"),
                published_at=now - timedelta(hours=entry["age_hours"]),
                backend=backend,
                needs_resolution=entry.get("needs_resolution", False),
            )
        )
    return items


class FixtureSearchBackend:
    def __init__(self, backend: Backend, now: datetime):
        self.name = backend
        self._items = load_demo_items(backend, now)

    async def search(self, plan: QueryPlan, *, limit: int) -> SearchResult:
        tokens = [
            token for token in plan.normalized.lower().split() if token and not token.startswith("site:")
        ]
        matched = [
            item
            for item in self._items
            if any(token in f"{item.title} {item.snippet or ''}".lower() for token in tokens)
        ]
        return SearchResult(items=matched[:limit], raw_count=len(matched))


class FixtureLinkResolver:
    async def resolve(self, url: str) -> str | None:
        return url


class FixtureArticleFetcher:
    async def fetch(self, url: str) -> FetchedPage:
        return FetchedPage(
            url=url,
            final_url=url,
            status=200,
            content_type="text/html",
            html="<html><body><p>Fixture article body.</p></body></html>",
            elapsed_ms=1,
        )


class FixtureTextExtractor:
    def extract(self, page: FetchedPage) -> ExtractedText:
        text = "Gold prices rose in fixture data."
        return ExtractedText(
            text=text,
            title=None,
            published_at=None,
            word_count=len(text.split()),
            quality=0.9,
        )


class FixtureGenerator:
    async def complete_json(
        self,
        *,
        schema: type,
        system: str,
        user: str,
        max_tokens: int,
    ):
        if schema is BriefDraft:
            return BriefDraft(answer="Fixture brief generated from fixture clusters.")
        if schema is ExtractedFacts:
            return ExtractedFacts(facts=[])
        raise ValueError(f"unsupported schema: {schema.__name__}")

    async def complete_chat(
        self,
        *,
        schema: type,
        messages: list[dict[str, str]],
        max_tokens: int,
    ):
        last = next(
            (
                message["content"]
                for message in reversed(messages)
                if message.get("role") == "user"
            ),
            "",
        ).strip()
        if schema is ChatDecision:
            if last.lower() in {"hi", "hello", "hey", "thanks", "thank you"}:
                return ChatDecision(
                    reply="Hello. Ask me about a story, market, or event."
                )
            return ChatDecision(tool_calls=[ChatToolCall(query=last[:300])])
        return await self.complete_json(
            schema=schema,
            system="",
            user=last,
            max_tokens=max_tokens,
        )

    async def stream_text(
        self,
        *,
        messages: list[dict[str, str]],
        max_tokens: int,
    ):
        yield "Fixture answer."
