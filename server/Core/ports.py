from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Protocol, TypeVar

from pydantic import BaseModel

from Core.models import (
    ArticleType,
    Backend,
    Candidate,
    CandidateAssessment,
    ExtractedText,
    FetchedPage,
    QueryAnalysis,
    QueryClass,
    QueryPlan,
    SearchResult,
    StageEvent,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

ProgressCallback = Callable[[int, int], Awaitable[None]]


class SearchBackend(Protocol):
    name: Backend

    async def search(self, plan: QueryPlan, *, limit: int) -> SearchResult: ...


class LinkResolver(Protocol):
    async def resolve(self, url: str) -> str | None: ...


class ArticleFetcher(Protocol):
    async def fetch(self, url: str) -> FetchedPage: ...


class TextExtractor(Protocol):
    def extract(self, page: FetchedPage) -> ExtractedText: ...


class DecisionEngine(Protocol):
    async def analyze_query(self, query: str) -> QueryAnalysis: ...

    async def classify_query(self, query: str) -> QueryClass: ...

    async def relevance(
        self, query: str, candidates: Sequence[Candidate]
    ) -> list[float]: ...

    async def article_types(
        self, candidates: Sequence[Candidate]
    ) -> list[ArticleType]: ...

    async def assess(
        self, query: str, candidates: Sequence[Candidate]
    ) -> list[CandidateAssessment]: ...

    async def injection_risk(self, text: str) -> float: ...

    async def stance(
        self, question: str, items: Sequence[str], *, topic: str = ""
    ) -> list[str]: ...

    async def score(
        self, question: str, items: Sequence[str], *, topic: str = ""
    ) -> list[float]: ...


class Generator(Protocol):
    async def complete_json(
        self,
        *,
        schema: type[ModelT],
        system: str,
        user: str,
        max_tokens: int,
    ) -> ModelT: ...


class Cache(Protocol):
    async def get(self, key: str) -> bytes | None: ...

    async def set(self, key: str, value: bytes, ttl_s: int) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class ProgressSink(Protocol):
    async def emit(self, event: StageEvent) -> None: ...
