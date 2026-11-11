from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

from Core.models import ChatConversation, ChatMessage, ChatRole


def _title(content: str) -> str:
    cleaned = " ".join(content.split())
    return cleaned[:60] or "New conversation"


def _message(role: ChatRole, content: str, now: datetime) -> ChatMessage:
    return ChatMessage(
        id=uuid4().hex,
        role=role,
        content=content,
        created_at=now,
    )


class ConversationStore:
    def __init__(
        self,
        *,
        max_conversations: int = 50,
        max_messages: int = 60,
    ):
        self._max_conversations = max(1, max_conversations)
        self._max_messages = max(1, max_messages)
        self._conversations: dict[str, ChatConversation] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    def lock(self, conversation_id: str) -> asyncio.Lock:
        lock = self._locks.get(conversation_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[conversation_id] = lock
        return lock

    async def begin(
        self,
        conversation_id: str | None,
        content: str,
        now: datetime,
    ) -> tuple[ChatConversation, ChatMessage]:
        async with self._guard:
            identifier = conversation_id or uuid4().hex
            conversation = self._conversations.get(identifier)
            if conversation is None:
                conversation = ChatConversation(
                    id=identifier,
                    title=_title(content),
                    messages=[],
                    created_at=now,
                    updated_at=now,
                )
                self._conversations[identifier] = conversation
                self._evict_locked(exclude=identifier)

            message = _message(ChatRole.USER, content, now)
            conversation.messages.append(message)
            conversation.updated_at = now
            self._trim_locked(conversation)
            return conversation, message

    async def append(self, conversation_id: str, message: ChatMessage) -> None:
        async with self._guard:
            conversation = self._conversations[conversation_id]
            conversation.messages.append(message)
            conversation.updated_at = message.created_at
            self._trim_locked(conversation)

    async def get(self, conversation_id: str) -> ChatConversation | None:
        async with self._guard:
            return self._conversations.get(conversation_id)

    async def delete(self, conversation_id: str) -> None:
        async with self._guard:
            self._conversations.pop(conversation_id, None)
            self._locks.pop(conversation_id, None)

    async def clear(self) -> None:
        async with self._guard:
            self._conversations.clear()
            self._locks.clear()

    def _trim_locked(self, conversation: ChatConversation) -> None:
        if len(conversation.messages) > self._max_messages:
            del conversation.messages[: -self._max_messages]

    def _evict_locked(self, *, exclude: str) -> None:
        while len(self._conversations) > self._max_conversations:
            candidates = [
                conversation
                for identifier, conversation in self._conversations.items()
                if identifier != exclude
            ]
            if not candidates:
                return
            oldest = min(candidates, key=lambda item: item.updated_at)
            self._conversations.pop(oldest.id, None)
            self._locks.pop(oldest.id, None)
