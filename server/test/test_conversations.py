from __future__ import annotations

from datetime import UTC, datetime, timedelta

from Core.conversations import ConversationStore
from Core.models import ChatMessage, ChatRole

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def message(role: ChatRole, content: str, at: datetime = NOW) -> ChatMessage:
    return ChatMessage(id=f"{role.value}-{content}", role=role, content=content, created_at=at)


async def test_begin_creates_conversation_and_user_message() -> None:
    store = ConversationStore(max_conversations=5, max_messages=10)
    conversation, user = await store.begin(None, "gold prices", NOW)

    assert conversation.id
    assert conversation.title == "gold prices"
    assert conversation.messages == [user]
    assert user.role is ChatRole.USER
    assert user.content == "gold prices"
    assert conversation.created_at == NOW
    assert conversation.updated_at == NOW


async def test_begin_reuses_an_existing_conversation() -> None:
    store = ConversationStore()
    conversation, _ = await store.begin(None, "gold prices", NOW)
    again, user = await store.begin(conversation.id, "what about europe", NOW)

    assert again is conversation
    assert len(again.messages) == 2
    assert again.messages[-1] is user


async def test_append_and_get() -> None:
    store = ConversationStore()
    conversation, _ = await store.begin(None, "gold prices", NOW)
    assistant = message(ChatRole.ASSISTANT, "Gold rose.", NOW + timedelta(seconds=1))
    await store.append(conversation.id, assistant)

    loaded = await store.get(conversation.id)
    assert loaded is not None
    assert [item.content for item in loaded.messages] == ["gold prices", "Gold rose."]
    assert loaded.updated_at == NOW + timedelta(seconds=1)


async def test_trims_to_max_messages() -> None:
    store = ConversationStore(max_messages=2)
    conversation, _ = await store.begin(None, "one", NOW)
    await store.append(conversation.id, message(ChatRole.ASSISTANT, "two", NOW))
    await store.append(conversation.id, message(ChatRole.USER, "three", NOW))

    assert [item.content for item in conversation.messages] == ["two", "three"]


async def test_evicts_oldest_conversation() -> None:
    store = ConversationStore(max_conversations=2)
    first, _ = await store.begin(None, "one", NOW)
    second, _ = await store.begin(None, "two", NOW + timedelta(seconds=1))
    third, _ = await store.begin(None, "three", NOW + timedelta(seconds=2))

    assert await store.get(first.id) is None
    assert await store.get(second.id) is not None
    assert await store.get(third.id) is not None


async def test_delete_and_clear() -> None:
    store = ConversationStore()
    conversation, _ = await store.begin(None, "gold prices", NOW)
    await store.delete(conversation.id)
    assert await store.get(conversation.id) is None

    other, _ = await store.begin(None, "oil", NOW)
    await store.clear()
    assert await store.get(other.id) is None


def test_lock_is_stable_per_conversation() -> None:
    store = ConversationStore()
    assert store.lock("abc") is store.lock("abc")
    assert store.lock("abc") is not store.lock("def")
