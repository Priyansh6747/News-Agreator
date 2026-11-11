from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from sse_starlette.sse import EventSourceResponse

from Core.models import ChatConversation, ChatRequest, ChatTurn
from router.deps import get_chat_service, get_conversation_store

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatTurn)
async def create_chat(request: ChatRequest) -> ChatTurn:
    return await get_chat_service().run(request)


@router.post("/chat/stream")
async def stream_chat(request: ChatRequest) -> EventSourceResponse:
    queue: asyncio.Queue[Any] = asyncio.Queue()

    async def on_event(kind: str, payload: Any) -> None:
        await queue.put((kind, payload))

    async def produce() -> None:
        try:
            await get_chat_service().run(request, on_event)
        except Exception as error:  # noqa: BLE001
            await queue.put(("error", {"message": str(error)}))
        finally:
            await queue.put(None)

    async def events():
        task = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                kind, payload = item
                if kind == "stage":
                    yield {"event": "stage", "data": payload.model_dump_json()}
                elif kind == "brief":
                    yield {"event": "brief", "data": payload.model_dump_json()}
                elif kind == "chat":
                    yield {"event": "chat", "data": payload.model_dump_json()}
                elif kind == "token":
                    yield {"event": "token", "data": json.dumps({"delta": payload})}
                elif kind in {"conversation", "tool"}:
                    yield {"event": kind, "data": json.dumps(payload)}
                else:
                    yield {"event": "error", "data": json.dumps(payload)}
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return EventSourceResponse(events())


@router.get("/conversations/{conversation_id}", response_model=ChatConversation)
async def get_conversation(conversation_id: str) -> ChatConversation:
    conversation = await get_conversation_store().get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str) -> Response:
    await get_conversation_store().delete(conversation_id)
    return Response(status_code=204)
