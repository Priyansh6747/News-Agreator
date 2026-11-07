from __future__ import annotations

import re
from collections.abc import Sequence

from Core.models import ArticleType, Candidate, CandidateAssessment, QueryClass

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

    async def assess(
        self, query: str, candidates: Sequence[Candidate]
    ) -> list[CandidateAssessment]:
        query_tokens = _tokens(query)
        lowered = query.lower()
        assessments: list[CandidateAssessment] = []
        for candidate in candidates:
            text = f"{candidate.title} {candidate.snippet or ''}"
            overlap = (
                len(query_tokens & _tokens(text)) / len(query_tokens) if query_tokens else 0.0
            )
            phrase_bonus = 0.2 if lowered in text.lower() else 0.0
            relevance = min(1.0, 0.8 * overlap + phrase_bonus)
            assessments.append(
                CandidateAssessment(
                    relevance=relevance,
                    article_type=self._article_type(candidate),
                    confidence=relevance,
                )
            )
        return assessments

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
