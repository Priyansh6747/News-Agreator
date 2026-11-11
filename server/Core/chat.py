from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import uuid4

from Core.conversations import ConversationStore
from Core.models import (
    Brief,
    ChatMessage,
    ChatRequest,
    ChatRole,
    ChatRun,
    ChatTurn,
    StageEvent,
)
from Core.ports import Clock, Generator, ProgressSink
from Core.prompts import (
    ChatDecision,
    ChatToolCall,
    build_chat_answer_messages,
    build_chat_decision_messages,
)
from Core.settings import Settings

logger = logging.getLogger(__name__)

ChatEventSink = Callable[[str, Any], Awaitable[None]]

GREETINGS = {
    "hi",
    "hello",
    "hey",
    "thanks",
    "thank you",
    "good morning",
    "good afternoon",
    "good evening",
}

FOLLOW_UP_PREFIXES = (
    "what about",
    "how about",
    "and ",
    "why",
    "compare",
    "tell me more",
    "what changed",
)


class ChatPipeline(Protocol):
    async def run(self, query: str, sink: ProgressSink | None = None) -> Brief: ...


class _StageSink:
    def __init__(
        self,
        events: list[StageEvent],
        on_event: ChatEventSink | None,
    ):
        self._events = events
        self._on_event = on_event

    async def emit(self, event: StageEvent) -> None:
        self._events.append(event)
        if self._on_event is not None:
            await self._on_event("stage", event)


def _last_user(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role is ChatRole.USER and message.content.strip():
            return message.content.strip()
    return "news"


def _latest_brief(messages: list[ChatMessage]) -> Brief | None:
    for message in reversed(messages):
        if message.role is ChatRole.ASSISTANT and message.brief is not None:
            return message.brief
    return None


def _heuristic_decision(
    messages: list[ChatMessage],
    latest_brief: Brief | None,
) -> ChatDecision:
    message = _last_user(messages)
    lowered = message.lower()
    if lowered in GREETINGS or lowered.startswith(("who are you", "what can you do")):
        return ChatDecision(
            reply=(
                "Hello. Ask me about a story, market, or event and I'll run the "
                "news pipeline."
            )
        )
    query = message
    if latest_brief is not None and (
        len(message) < 80 or lowered.startswith(FOLLOW_UP_PREFIXES)
    ):
        query = f"{latest_brief.query} {message}"
    return ChatDecision(
        tool_calls=[ChatToolCall(name="news_brief", query=query[:300])]
    )


def _normalize_decision(
    decision: ChatDecision,
    messages: list[ChatMessage],
    latest_brief: Brief | None,
) -> ChatDecision | None:
    for call in decision.tool_calls:
        if call.name.strip().lower().replace(" ", "_") != "news_brief":
            continue
        query = " ".join(call.query.split())[:300]
        if query:
            return ChatDecision(
                tool_calls=[ChatToolCall(name="news_brief", query=query)]
            )
    reply = (decision.reply or "").strip()
    if reply:
        return ChatDecision(reply=reply)
    if latest_brief is not None:
        return _heuristic_decision(messages, latest_brief)
    return None


class ChatService:
    def __init__(
        self,
        *,
        pipeline: ChatPipeline,
        generator: Generator | None,
        store: ConversationStore,
        settings: Settings,
        clock: Clock,
    ):
        self._pipeline = pipeline
        self._generator = generator
        self._store = store
        self._settings = settings
        self._clock = clock

    async def run(
        self,
        request: ChatRequest,
        on_event: ChatEventSink | None = None,
    ) -> ChatTurn:
        conversation_id = request.conversation_id or uuid4().hex
        lock = self._store.lock(conversation_id)
        async with lock:
            conversation, user = await self._store.begin(
                conversation_id,
                request.message,
                self._clock.now(),
            )
            await self._emit(
                on_event,
                "conversation",
                {"conversation_id": conversation.id},
            )
            decision = await self._decide(conversation.messages)
            assistant = await self._respond(conversation.messages, decision, on_event)
            await self._store.append(conversation.id, assistant)
            turn = ChatTurn(
                conversation_id=conversation.id,
                user=user,
                assistant=assistant,
            )
            await self._emit(on_event, "chat", turn)
            return turn

    async def _decide(self, messages: list[ChatMessage]) -> ChatDecision:
        latest_brief = _latest_brief(messages)
        if self._generator is not None:
            try:
                decision = await self._generator.complete_chat(
                    schema=ChatDecision,
                    messages=build_chat_decision_messages(
                        messages,
                        latest_brief,
                        settings=self._settings,
                        now=self._clock.now(),
                    ),
                    max_tokens=self._settings.chat_decision_max_tokens,
                )
                normalized = _normalize_decision(decision, messages, latest_brief)
                if normalized is not None:
                    return normalized
            except Exception as error:  # noqa: BLE001
                logger.warning("chat decision failed (%s); using heuristic", error)
        return _heuristic_decision(messages, latest_brief)

    async def _respond(
        self,
        messages: list[ChatMessage],
        decision: ChatDecision,
        on_event: ChatEventSink | None,
    ) -> ChatMessage:
        if decision.tool_calls:
            return await self._run_tool(
                messages,
                decision.tool_calls[0].query,
                on_event,
            )
        content = (decision.reply or "").strip()
        if not content:
            content = "Ask me about a story, market, or event."
        return self._message(ChatRole.ASSISTANT, content)

    async def _run_tool(
        self,
        messages: list[ChatMessage],
        query: str,
        on_event: ChatEventSink | None,
    ) -> ChatMessage:
        started = self._clock.now()
        stages: list[StageEvent] = []
        await self._emit(
            on_event,
            "tool",
            {"name": "news_brief", "query": query, "status": "started"},
        )
        try:
            brief = await self._pipeline.run(query, _StageSink(stages, on_event))
        except Exception:
            logger.exception("news_brief tool failed")
            elapsed = int((self._clock.now() - started).total_seconds() * 1000)
            await self._emit(
                on_event,
                "tool",
                {"name": "news_brief", "query": query, "status": "failed"},
            )
            return self._message(
                ChatRole.ASSISTANT,
                (
                    f"I couldn't finish the news run for '{query}'. "
                    "The sources or the model did not respond; try again."
                ),
                run=ChatRun(
                    query=query,
                    status="failed",
                    elapsed_ms=elapsed,
                    stages=stages,
                ),
            )

        await self._emit(
            on_event,
            "tool",
            {"name": "news_brief", "query": query, "status": "completed"},
        )
        await self._emit(on_event, "brief", brief)
        answer = await self._answer(messages, brief, on_event)
        elapsed = int((self._clock.now() - started).total_seconds() * 1000)
        return self._message(
            ChatRole.ASSISTANT,
            answer,
            brief=brief,
            run=ChatRun(
                query=query,
                status="completed",
                elapsed_ms=elapsed,
                stages=stages,
                coverage_status=brief.coverage.status.value,
                story_count=len(brief.stories),
            ),
        )

    async def _answer(
        self,
        messages: list[ChatMessage],
        brief: Brief,
        on_event: ChatEventSink | None,
    ) -> str:
        if self._generator is None:
            answer = brief.answer.strip() or "The brief is ready, but no answer was generated."
            await self._emit(on_event, "token", answer)
            return answer

        chunks: list[str] = []
        try:
            async for delta in self._generator.stream_text(
                messages=build_chat_answer_messages(
                    messages,
                    brief,
                    settings=self._settings,
                ),
                max_tokens=self._settings.chat_answer_max_tokens,
            ):
                chunks.append(delta)
                await self._emit(on_event, "token", delta)
        except Exception as error:  # noqa: BLE001
            logger.warning("chat answer stream failed (%s); using brief answer", error)

        answer = "".join(chunks).strip()
        if answer:
            return answer
        answer = brief.answer.strip() or "The brief is ready, but no answer was generated."
        await self._emit(on_event, "token", answer)
        return answer

    def _message(self, role: ChatRole, content: str, **kwargs: Any) -> ChatMessage:
        return ChatMessage(
            id=uuid4().hex,
            role=role,
            content=content,
            created_at=self._clock.now(),
            **kwargs,
        )

    async def _emit(
        self,
        on_event: ChatEventSink | None,
        kind: str,
        payload: Any,
    ) -> None:
        if on_event is not None:
            await on_event(kind, payload)
