from __future__ import annotations

import asyncio
import logging
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
from Core.ports import DecisionEngine
from tool.laya_questions import (
    QUERY_CLASS_QUESTIONS,
    article_type_questions,
    assessment_questions,
    injection_question,
    query_analysis_questions,
    relevance_questions,
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

    async def analyze_query(self, query: str) -> QueryAnalysis:
        try:
            result = await self._predict(
                {"query": query}, query_analysis_questions()
            )
            answers = result["answers"]
            try:
                query_class = QueryClass(answers["query_class"]["choice"])
            except ValueError:
                query_class = QueryClass.OTHER
            sensitivity = round(float(answers["time_sensitivity"]["score"]))
            sensitivity = max(0, min(3, sensitivity))
            try:
                intent = QueryIntent(answers["intent"]["choice"])
            except ValueError:
                intent = QueryIntent.OTHER
            try:
                brief_schema = BriefSchema(answers["brief_schema"]["choice"])
            except ValueError:
                brief_schema = BriefSchema.GENERAL_BRIEF
            return QueryAnalysis(
                query_class=query_class,
                time_sensitivity=sensitivity,
                intent=intent,
                brief_schema=brief_schema,
            )
        except Exception as error:
            if self._fallback is None:
                raise
            logger.warning(
                "laya analyze_query failed (%s); using fallback", type(error).__name__
            )
            return await self._fallback.analyze_query(query)

    def _state(self, candidate: Candidate, query: str | None = None) -> dict:
        state = {
            "title": candidate.title,
            "snippet": candidate.snippet or "",
            "publisher": candidate.publisher or "",
        }
        if query is not None:
            state["query"] = query
        return state

    async def relevance(
        self, query: str, candidates: Sequence[Candidate]
    ) -> list[float]:
        if not candidates:
            return []
        questions = relevance_questions(query)
        requests = [
            {"state": self._state(candidate, query), "questions": questions}
            for candidate in candidates
        ]
        try:
            results = await self._predict_batch(requests)
            if len(results) != len(candidates):
                raise ValueError("laya returned a mismatched batch size")
            return [
                _clamp(float(result["answers"]["relevant"]["noul"]))
                for result in results
            ]
        except Exception as error:
            if self._fallback is None:
                raise
            logger.warning(
                "laya relevance failed (%s); using fallback", type(error).__name__
            )
            return await self._fallback.relevance(query, candidates)

    async def article_types(
        self, candidates: Sequence[Candidate]
    ) -> list[ArticleType]:
        if not candidates:
            return []
        questions = article_type_questions()
        requests = [
            {"state": self._state(candidate), "questions": questions}
            for candidate in candidates
        ]
        try:
            results = await self._predict_batch(requests)
            if len(results) != len(candidates):
                raise ValueError("laya returned a mismatched batch size")
            return [
                ARTICLE_TYPES.get(
                    result["answers"]["article_type"]["choice"],
                    ArticleType.UNKNOWN,
                )
                for result in results
            ]
        except Exception as error:
            if self._fallback is None:
                raise
            logger.warning(
                "laya article_types failed (%s); using fallback", type(error).__name__
            )
            return await self._fallback.article_types(candidates)

    async def assess(
        self, query: str, candidates: Sequence[Candidate]
    ) -> list[CandidateAssessment]:
        if not candidates:
            return []
        questions = assessment_questions(query)
        requests = [
            {"state": self._state(candidate, query), "questions": questions}
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

    async def stance(
        self, question: str, items: Sequence[str], *, topic: str = ""
    ) -> list[str]:
        if not items:
            return []
        questions = {
            "stance": {
                "type": "choice",
                "instructions": question,
                "criteria": {
                    "up": "the item indicates an increase or positive movement for the topic",
                    "down": "the item indicates a decrease or negative movement for the topic",
                    "flat": "the item indicates no clear change for the topic",
                    "unrelated": "the item is not about the topic",
                },
            }
        }
        requests = [
            {"state": {"query": topic, "text": item}, "questions": questions}
            for item in items
        ]
        try:
            results = await self._predict_batch(requests)
            if len(results) != len(items):
                raise ValueError("laya returned a mismatched batch size")
            allowed = {"up", "down", "flat", "unrelated"}
            stances: list[str] = []
            for result in results:
                choice = str(result["answers"]["stance"]["choice"]).lower()
                stances.append(choice if choice in allowed else "unrelated")
            return stances
        except Exception as error:
            if self._fallback is None:
                raise
            logger.warning("laya stance failed (%s); using fallback", type(error).__name__)
            return await self._fallback.stance(question, items, topic=topic)

    async def score(
        self, question: str, items: Sequence[str], *, topic: str = ""
    ) -> list[float]:
        if not items:
            return []
        questions = {
            "score": {
                "type": "noul",
                "instructions": question,
                "criteria": {
                    "true": "the item strongly supports a positive answer to the question",
                    "false": "the item does not support a positive answer to the question",
                },
            }
        }
        requests = [
            {"state": {"query": topic, "text": item}, "questions": questions}
            for item in items
        ]
        try:
            results = await self._predict_batch(requests)
            if len(results) != len(items):
                raise ValueError("laya returned a mismatched batch size")
            return [_clamp(float(result["answers"]["score"]["noul"])) for result in results]
        except Exception as error:
            if self._fallback is None:
                raise
            logger.warning("laya score failed (%s); using fallback", type(error).__name__)
            return await self._fallback.score(question, items, topic=topic)
