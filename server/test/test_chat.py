from __future__ import annotations

from typing import Any

from Core.chat import ChatService
from Core.conversations import ConversationStore
from Core.models import (
    Brief,
    ChatRequest,
    Coverage,
    CoverageStatus,
    EventState,
    FactRow,
    QueryClass,
    Stage,
    StageEvent,
    TimelineEntry,
)
from Core.prompts import ChatDecision, ChatToolCall
from Core.settings import Settings
from test.helpers import NOW
from tool.fixture_adapters import StaticClock

STAGES = (
    Stage.PLAN,
    Stage.RETRIEVE,
    Stage.RANK,
    Stage.CLUSTER,
    Stage.SCORE,
    Stage.ENRICH,
    Stage.BRIEF,
    Stage.PRESENT,
)


def make_brief(query: str = "gold prices") -> Brief:
    return Brief(
        query=query,
        query_class=QueryClass.MARKET,
        answer="Gold rose on safe-haven demand.",
        key_facts=[
            FactRow(
                value="$2,400",
                meaning="Spot gold price",
                source_url="https://example.com/gold",
                published_at=NOW,
            )
        ],
        timeline=[
            TimelineEntry(
                at=NOW,
                what="Gold rose 1%.",
                source_url="https://example.com/gold",
            )
        ],
        stories=[],
        coverage=Coverage(status=CoverageStatus.COMPLETE),
        generated_at=NOW,
    )


class FakePipeline:
    def __init__(self, *, brief: Brief | None = None, error: Exception | None = None):
        self.brief = brief or make_brief()
        self.error = error
        self.queries: list[str] = []

    async def run(self, query: str, sink=None) -> Brief:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        if sink is not None:
            for stage in STAGES:
                await sink.emit(
                    StageEvent(stage=stage, state=EventState.STARTED, at=NOW)
                )
                await sink.emit(
                    StageEvent(
                        stage=stage,
                        state=EventState.FINISHED,
                        at=NOW,
                        elapsed_ms=1,
                    )
                )
        return self.brief


class FakeGenerator:
    def __init__(
        self,
        decisions: list[ChatDecision],
        *,
        chunks: list[str] | None = None,
        fail_stream: bool = False,
    ):
        self.decisions = list(decisions)
        self.chunks = chunks or ["Gold ", "rose."]
        self.fail_stream = fail_stream
        self.decision_messages: list[list[dict[str, str]]] = []
        self.answer_messages: list[list[dict[str, str]]] = []

    async def complete_chat(self, *, schema, messages, max_tokens):
        self.decision_messages.append(messages)
        return self.decisions.pop(0)

    async def stream_text(self, *, messages, max_tokens):
        self.answer_messages.append(messages)
        if self.fail_stream:
            raise RuntimeError("stream down")
        for chunk in self.chunks:
            yield chunk


def make_service(
    *,
    pipeline: FakePipeline,
    generator: FakeGenerator | None,
    store: ConversationStore,
    settings: Settings,
    clock: StaticClock,
) -> ChatService:
    return ChatService(
        pipeline=pipeline,
        generator=generator,
        store=store,
        settings=settings,
        clock=clock,
    )


def collect_events():
    events: list[tuple[str, Any]] = []

    async def on_event(kind: str, payload: Any) -> None:
        events.append((kind, payload))

    return events, on_event


async def test_tool_turn_streams_stages_and_answer(
    settings: Settings,
    clock: StaticClock,
) -> None:
    pipeline = FakePipeline()
    generator = FakeGenerator(
        [ChatDecision(tool_calls=[ChatToolCall(query="gold prices")])],
        chunks=["Gold ", "rose."],
    )
    store = ConversationStore()
    events, on_event = collect_events()

    turn = await make_service(
        pipeline=pipeline,
        generator=generator,
        store=store,
        settings=settings,
        clock=clock,
    ).run(ChatRequest(message="gold prices"), on_event)

    assert turn.assistant.content == "Gold rose."
    assert turn.assistant.brief is not None
    assert turn.assistant.brief.query == "gold prices"
    assert turn.assistant.run is not None
    assert turn.assistant.run.status == "completed"
    assert turn.assistant.run.story_count == 0
    assert len(turn.assistant.run.stages) == 2 * len(STAGES)
    assert pipeline.queries == ["gold prices"]

    kinds = [kind for kind, _ in events]
    assert kinds[0] == "conversation"
    assert kinds.count("token") == 2
    assert kinds[-1] == "chat"
    assert "tool" in kinds
    assert "brief" in kinds
    assert "Gold rose on safe-haven demand." in generator.answer_messages[0][0]["content"]


async def test_direct_reply_skips_the_pipeline(
    settings: Settings,
    clock: StaticClock,
) -> None:
    pipeline = FakePipeline()
    generator = FakeGenerator([ChatDecision(reply="Hello there.")])
    events, on_event = collect_events()

    turn = await make_service(
        pipeline=pipeline,
        generator=generator,
        store=ConversationStore(),
        settings=settings,
        clock=clock,
    ).run(ChatRequest(message="hello"), on_event)

    assert turn.assistant.content == "Hello there."
    assert turn.assistant.brief is None
    assert turn.assistant.run is None
    assert pipeline.queries == []
    assert generator.answer_messages == []
    assert [kind for kind, _ in events] == ["conversation", "chat"]


async def test_follow_up_receives_the_latest_brief_context(
    settings: Settings,
    clock: StaticClock,
) -> None:
    pipeline = FakePipeline()
    generator = FakeGenerator(
        [
            ChatDecision(tool_calls=[ChatToolCall(query="gold prices")]),
            ChatDecision(reply="It is still supported by demand."),
        ],
        chunks=["First answer."],
    )
    store = ConversationStore()
    service = make_service(
        pipeline=pipeline,
        generator=generator,
        store=store,
        settings=settings,
        clock=clock,
    )

    first = await service.run(ChatRequest(message="gold prices"))
    second = await service.run(
        ChatRequest(
            conversation_id=first.conversation_id,
            message="why is it holding up?",
        )
    )

    assert second.assistant.content == "It is still supported by demand."
    decision_system = generator.decision_messages[1][0]["content"]
    assert "gold prices" in decision_system
    assert "$2,400" in decision_system
    assert "Gold rose 1%." in decision_system
    loaded = await store.get(first.conversation_id)
    assert loaded is not None
    assert len(loaded.messages) == 4


async def test_no_generator_uses_heuristic_and_brief_answer(
    settings: Settings,
    clock: StaticClock,
) -> None:
    pipeline = FakePipeline()
    store = ConversationStore()
    service = make_service(
        pipeline=pipeline,
        generator=None,
        store=store,
        settings=settings,
        clock=clock,
    )
    events, on_event = collect_events()

    news = await service.run(ChatRequest(message="gold prices"), on_event)
    assert news.assistant.content == pipeline.brief.answer
    assert news.assistant.brief is not None
    assert [kind for kind, _ in events].count("token") == 1

    greeting = await service.run(ChatRequest(message="hello"))
    assert "Hello" in greeting.assistant.content
    assert pipeline.queries == ["gold prices"]


async def test_stream_failure_falls_back_to_the_brief_answer(
    settings: Settings,
    clock: StaticClock,
) -> None:
    pipeline = FakePipeline()
    generator = FakeGenerator(
        [ChatDecision(tool_calls=[ChatToolCall(query="gold prices")])],
        fail_stream=True,
    )
    events, on_event = collect_events()

    turn = await make_service(
        pipeline=pipeline,
        generator=generator,
        store=ConversationStore(),
        settings=settings,
        clock=clock,
    ).run(ChatRequest(message="gold prices"), on_event)

    assert turn.assistant.content == pipeline.brief.answer
    tokens = [payload for kind, payload in events if kind == "token"]
    assert tokens == [pipeline.brief.answer]


async def test_pipeline_failure_marks_the_run_failed(
    settings: Settings,
    clock: StaticClock,
) -> None:
    pipeline = FakePipeline(error=RuntimeError("sources down"))
    generator = FakeGenerator(
        [ChatDecision(tool_calls=[ChatToolCall(query="gold prices")])]
    )

    turn = await make_service(
        pipeline=pipeline,
        generator=generator,
        store=ConversationStore(),
        settings=settings,
        clock=clock,
    ).run(ChatRequest(message="gold prices"))

    assert turn.assistant.brief is None
    assert turn.assistant.run is not None
    assert turn.assistant.run.status == "failed"
    assert "couldn't finish" in turn.assistant.content
