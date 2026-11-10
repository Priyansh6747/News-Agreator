from __future__ import annotations

import re
from collections.abc import Sequence

from Core.models import (
    ArticleType,
    BriefSchema,
    Candidate,
    CandidateAssessment,
    QueryAnalysis,
    QueryClass,
    QueryIntent,
)

COMPARISON_TERMS = {"vs", "versus", "compare", "comparison", "difference", "better"}
MARKET_TERMS = {
    "gold",
    "silver",
    "oil",
    "bitcoin",
    "crypto",
    "stock",
    "stocks",
    "market",
    "markets",
    "price",
    "prices",
    "inflation",
    "rate",
    "rates",
    "dollar",
    "euro",
    "yield",
    "commodity",
    "commodities",
}
GEOPOLITICS_TERMS = {
    "war",
    "sanctions",
    "military",
    "nato",
    "treaty",
    "election",
    "conflict",
    "missile",
    "border",
    "diplomacy",
    "coup",
    "invasion",
    "ceasefire",
}
EVENT_TERMS = {
    "earthquake",
    "hurricane",
    "flood",
    "wildfire",
    "explosion",
    "crash",
    "storm",
    "shooting",
    "protest",
    "strike",
    "rescue",
    "killed",
    "dead",
}
COMPANY_TERMS = {
    "company",
    "ceo",
    "merger",
    "acquisition",
    "ipo",
    "layoffs",
    "revenue",
    "profit",
    "quarterly",
    "earnings",
    "startup",
    "valuation",
}

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(system|previous|above)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"reveal\s+your\s+(instructions|prompt)", re.IGNORECASE),
    re.compile(r"new\s+instructions\s*:", re.IGNORECASE),
    re.compile(r"do\s+not\s+tell\s+the\s+user", re.IGNORECASE),
]

OPINION_MARKERS = {"opinion", "editorial", "column", "commentary"}
PRESS_RELEASE_MARKERS = {"press release", "announces", "announcement"}
AGGREGATOR_DOMAINS = {"news.google.com", "news.yahoo.com", "msn.com", "bing.com"}

POSITIVE_TERMS = {
    "gain",
    "gained",
    "gains",
    "rise",
    "rises",
    "rose",
    "rising",
    "up",
    "higher",
    "surge",
    "surged",
    "record",
    "strong",
    "stronger",
    "boost",
    "boosted",
    "growth",
    "increase",
    "increased",
    "buy",
    "buying",
    "beat",
    "beats",
    "win",
    "wins",
    "advance",
    "advances",
    "positive",
}

NEGATIVE_TERMS = {
    "fall",
    "falls",
    "fell",
    "falling",
    "drop",
    "drops",
    "dropped",
    "down",
    "lower",
    "loss",
    "losses",
    "weak",
    "weaker",
    "decline",
    "declined",
    "cut",
    "cuts",
    "sell",
    "selling",
    "slump",
    "slumped",
    "fear",
    "fears",
    "risk",
    "risks",
    "negative",
    "miss",
    "misses",
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class HeuristicDecisionEngine:
    async def classify_query(self, query: str) -> QueryClass:
        tokens = _tokens(query)
        if tokens & COMPARISON_TERMS:
            return QueryClass.COMPARISON
        if tokens & EVENT_TERMS:
            return QueryClass.EVENT
        if tokens & GEOPOLITICS_TERMS:
            return QueryClass.GEOPOLITICS
        if tokens & MARKET_TERMS:
            return QueryClass.MARKET
        if tokens & COMPANY_TERMS:
            return QueryClass.COMPANY
        return QueryClass.OTHER

    async def analyze_query(self, query: str) -> QueryAnalysis:
        query_class = await self.classify_query(query)
        tokens = _tokens(query)
        if tokens & COMPARISON_TERMS:
            intent = QueryIntent.COMPARISON
        elif tokens & {"what", "how", "why", "explain", "explained", "explainer", "meaning"}:
            intent = QueryIntent.EXPLAINER
        elif tokens & (MARKET_TERMS | {"price", "prices", "rate", "rates"}):
            intent = QueryIntent.PRICE_CHECK
        elif tokens & COMPANY_TERMS:
            intent = QueryIntent.COMPANY_CHECK
        elif tokens & (EVENT_TERMS | GEOPOLITICS_TERMS):
            intent = QueryIntent.EVENT_UPDATE
        else:
            intent = QueryIntent.OTHER

        sensitivity = {
            QueryClass.MARKET: 3,
            QueryClass.EVENT: 2,
            QueryClass.GEOPOLITICS: 2,
            QueryClass.COMPANY: 1,
            QueryClass.COMPARISON: 0,
            QueryClass.OTHER: 1,
        }[query_class]
        if intent is QueryIntent.EXPLAINER:
            sensitivity = 0
        schema = {
            QueryClass.MARKET: BriefSchema.PRICE_TABLE,
            QueryClass.EVENT: BriefSchema.EVENT_TIMELINE,
            QueryClass.GEOPOLITICS: BriefSchema.CONFLICT_SUMMARY,
            QueryClass.COMPANY: BriefSchema.COMPANY_SNAPSHOT,
            QueryClass.COMPARISON: BriefSchema.COMPARISON_TABLE,
            QueryClass.OTHER: BriefSchema.GENERAL_BRIEF,
        }[query_class]
        if intent is QueryIntent.EXPLAINER:
            schema = BriefSchema.GENERAL_BRIEF

        return QueryAnalysis(
            query_class=query_class,
            time_sensitivity=sensitivity,
            intent=intent,
            brief_schema=schema,
        )

    def _relevance_scores(
        self, query: str, candidates: Sequence[Candidate]
    ) -> list[float]:
        query_tokens = _tokens(query)
        lowered = query.lower()
        scores: list[float] = []
        for candidate in candidates:
            text = f"{candidate.title} {candidate.snippet or ''}"
            overlap = (
                len(query_tokens & _tokens(text)) / len(query_tokens) if query_tokens else 0.0
            )
            phrase_bonus = 0.2 if lowered in text.lower() else 0.0
            scores.append(min(1.0, 0.8 * overlap + phrase_bonus))
        return scores

    async def relevance(
        self, query: str, candidates: Sequence[Candidate]
    ) -> list[float]:
        return self._relevance_scores(query, candidates)

    async def article_types(
        self, candidates: Sequence[Candidate]
    ) -> list[ArticleType]:
        return [self._article_type(candidate) for candidate in candidates]

    async def assess(
        self, query: str, candidates: Sequence[Candidate]
    ) -> list[CandidateAssessment]:
        scores = self._relevance_scores(query, candidates)
        return [
            CandidateAssessment(
                relevance=score,
                article_type=self._article_type(candidate),
                confidence=score,
            )
            for candidate, score in zip(candidates, scores)
        ]

    def _article_type(self, candidate: Candidate) -> ArticleType:
        title = candidate.title.lower()
        if any(marker in title for marker in OPINION_MARKERS):
            return ArticleType.OPINION
        if any(marker in title for marker in PRESS_RELEASE_MARKERS):
            return ArticleType.PRESS_RELEASE
        if candidate.domain in AGGREGATOR_DOMAINS:
            return ArticleType.AGGREGATOR
        return ArticleType.REPORT

    async def injection_risk(self, text: str) -> float:
        matches = sum(1 for pattern in INJECTION_PATTERNS if pattern.search(text))
        return min(1.0, 0.4 * matches)

    async def stance(
        self, question: str, items: Sequence[str], *, topic: str = ""
    ) -> list[str]:
        results: list[str] = []
        for item in items:
            tokens = _tokens(item)
            positive = len(tokens & POSITIVE_TERMS)
            negative = len(tokens & NEGATIVE_TERMS)
            if positive > negative:
                results.append("up")
            elif negative > positive:
                results.append("down")
            else:
                results.append("flat")
        return results

    async def score(
        self, question: str, items: Sequence[str], *, topic: str = ""
    ) -> list[float]:
        results: list[float] = []
        for item in items:
            tokens = _tokens(item)
            positive = len(tokens & POSITIVE_TERMS)
            negative = len(tokens & NEGATIVE_TERMS)
            results.append(min(1.0, max(0.0, 0.5 + 0.25 * positive - 0.25 * negative)))
        return results
