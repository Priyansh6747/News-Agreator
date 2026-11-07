from __future__ import annotations

import httpx

from main import app


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


async def test_health_and_ready() -> None:
    async with client() as http:
        health = await http.get("/health")
        ready = await http.get("/ready")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json()["app_env"] == "demo"
    assert ready.json()["backends"]


async def test_brief_endpoint() -> None:
    async with client() as http:
        response = await http.post("/api/v1/brief", json={"query": "gold prices"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "gold prices"
    assert payload["coverage"]["status"] in {"complete", "partial", "unavailable"}
    assert isinstance(payload["stories"], list)


async def test_invalid_body_returns_422() -> None:
    async with client() as http:
        response = await http.post("/api/v1/brief", json={"query": "x"})
    assert response.status_code == 422


async def test_stream_endpoint_emits_stages_and_brief() -> None:
    async with client() as http, http.stream(
        "POST",
        "/api/v1/brief/stream",
        json={"query": "gold prices"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in response.aiter_text()])
    assert "event: stage" in body
    assert "event: brief" in body
