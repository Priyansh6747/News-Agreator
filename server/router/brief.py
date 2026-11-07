from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from Core.models import Brief, BriefRequest
from router.deps import get_pipeline

router = APIRouter(prefix="/api/v1", tags=["brief"])


@router.post("/brief", response_model=Brief)
async def create_brief(request: BriefRequest) -> Brief:
    return await get_pipeline().run(request.query)


@router.post("/brief/stream")
async def stream_brief(request: BriefRequest) -> EventSourceResponse:
    queue: asyncio.Queue[Any] = asyncio.Queue()

    class QueueSink:
        async def emit(self, event: Any) -> None:
            await queue.put(("stage", event))

    async def produce() -> None:
        try:
            brief = await get_pipeline().run(request.query, QueueSink())
            await queue.put(("brief", brief))
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
                else:
                    yield {"event": "error", "data": json.dumps(payload)}
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return EventSourceResponse(events())
