from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from Core.models import ArticleType, Candidate, CandidateAssessment, QueryClass
from Core.ports import DecisionEngine
from tool.laya_questions import (
    QUERY_CLASS_QUESTIONS,
    assessment_questions,
    injection_question,
)

logger = logging.getLogger(__name__)

ARTICLE_TYPES = {
    "straight_report": ArticleType.REPORT,
    "opinion_piece": ArticleType.OPINION,
    "company_announcement": ArticleType.PRESS_RELEASE,
    "live_roundup": ArticleType.AGGREGATOR,
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class LayaDecisionEngine:
    def __init__(
        self,
        *,
        fallback: DecisionEngine | None = None,
        router=None,
        preload: bool = False,
        device: str | None = None,
        default: str = "english",
        max_loaded: int = 2,
        batch_size: int = 32,
    ):
        self._fallback = fallback
        self._batch_size = batch_size
        self._lock = asyncio.Lock()
        if router is None:
            from laya import Router

            options: dict[str, object] = {
                "preload": preload,
                "default": default,
                "max_loaded": max_loaded,
            }
            if device:
                options["device"] = device
            router = Router(**options)
        self._router = router

    async def _predict(self, state, questions):
        async with self._lock:
            return await asyncio.to_thread(self._router.predict, state, questions)

    async def _predict_batch(self, requests):
        async with self._lock:
            return await asyncio.to_thread(
                self._router.predict_batch,
                requests,
                batch_size=self._batch_size,
                sort_by_length=True,
            )

    async def classify_query(self, query: str) -> QueryClass:
        try:
            result = await self._predict({"query": query}, QUERY_CLASS_QUESTIONS)
            return QueryClass(result["answers"]["query_class"]["choice"])
        except Exception as error:
            if self._fallback is None:
                raise
            logger.warning(
                "laya classify_query failed (%s); using fallback", type(error).__name__
            )
            return await self._fallback.classify_query(query)

    async def assess(
        self, query: str, candidates: Sequence[Candidate]
    ) -> list[CandidateAssessment]:
        if not candidates:
            return []
        questions = assessment_questions(query)
        requests = [
            {
                "state": {
                    "query": query,
                    "title": candidate.title,
                    "snippet": candidate.snippet or "",
                    "publisher": candidate.publisher or "",
                },
                "questions": questions,
            }
            for candidate in candidates
        ]
        try:
            results = await self._predict_batch(requests)
            if len(results) != len(candidates):
                raise ValueError("laya returned a mismatched batch size")
            assessments: list[CandidateAssessment] = []
            for result in results:
                answers = result["answers"]
                relevance = _clamp(float(answers["relevant"]["noul"]))
                article_type = ARTICLE_TYPES.get(
                    answers["article_type"]["choice"], ArticleType.UNKNOWN
                )
                confidence = answers["relevant"].get("answer_confidence")
                assessments.append(
                    CandidateAssessment(
                        relevance=relevance,
                        article_type=article_type,
                        confidence=(
                            _clamp(float(confidence)) if confidence is not None else None
                        ),
                    )
                )
            return assessments
        except Exception as error:
            if self._fallback is None:
                raise
            logger.warning("laya assess failed (%s); using fallback", type(error).__name__)
            return await self._fallback.assess(query, candidates)

    async def injection_risk(self, text: str) -> float:
        try:
            result = await self._predict({"text": text}, injection_question())
            return _clamp(float(result["answers"]["injection"]["noul"]))
        except Exception as error:
            if self._fallback is None:
                raise
            logger.warning(
                "laya injection_risk failed (%s); using fallback", type(error).__name__
            )
            return await self._fallback.injection_risk(text)
