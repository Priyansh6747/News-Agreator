from __future__ import annotations

import httpx
import pytest

from main import app
from router.deps import get_chat_service, get_conversation_store


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.fixture(autouse=True)
async def reset_chat() -> None:
    get_chat_service.cache_clear()
    store = get_conversation_store()
    await store.clear()
    get_conversation_store.cache_clear()
    yield
    get_chat_service.cache_clear()
    get_conversation_store.cache_clear()


async def test_chat_endpoint_returns_a_turn() -> None:
    async with client() as http:
        response = await http.post(
            "/api/v1/chat",
            json={"message": "gold prices"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_id"]
    assert payload["user"]["role"] == "user"
    assert payload["assistant"]["role"] == "assistant"
    assert payload["assistant"]["content"]
    assert payload["assistant"]["brief"]["query"] == "gold prices"
    assert payload["assistant"]["run"]["status"] == "completed"


async def test_chat_stream_emits_chat_events() -> None:
    async with client() as http, http.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "gold prices"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in response.aiter_text()])

    assert "event: conversation" in body
    assert "event: tool" in body
    assert "event: stage" in body
    assert "event: brief" in body
    assert "event: token" in body
    assert "event: chat" in body


async def test_get_and_delete_conversation() -> None:
    async with client() as http:
        created = await http.post("/api/v1/chat", json={"message": "gold prices"})
        conversation_id = created.json()["conversation_id"]

        loaded = await http.get(f"/api/v1/conversations/{conversation_id}")
        assert loaded.status_code == 200
        assert len(loaded.json()["messages"]) == 2

        deleted = await http.delete(f"/api/v1/conversations/{conversation_id}")
        assert deleted.status_code == 204

        missing = await http.get(f"/api/v1/conversations/{conversation_id}")
        assert missing.status_code == 404


async def test_invalid_chat_bodies_return_422() -> None:
    async with client() as http:
        empty = await http.post("/api/v1/chat", json={"message": "  "})
        too_long = await http.post(
            "/api/v1/chat",
            json={"message": "x" * 2001},
        )

    assert empty.status_code == 422
    assert too_long.status_code == 422
