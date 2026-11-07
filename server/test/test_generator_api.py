from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from Core.errors import GeneratorError
from Core.settings import Settings
from tool.generator_api import GEMINI_OPENAI_BASE, OpenAICompatibleGenerator


class Ping(BaseModel):
    answer: str


def settings(**overrides) -> Settings:
    defaults = {
        "app_env": "demo",
        "generator_api_key": "test-key",
        "generator_model": "gemini-3.5-flash-lite",
        "generator_base_url": "https://api.openai.com/v1",
        "generator_retry_base_s": 0.0,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def completion(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


async def test_groq_uses_max_completion_tokens() -> None:
    seen: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), json.loads(request.content)))
        return completion('{"answer": "ok"}')

    generator = OpenAICompatibleGenerator(
        settings(
            generator_base_url="https://api.groq.com/openai/v1",
            generator_model="qwen/qwen3.8-27b",
        ),
        transport=httpx.MockTransport(handler),
    )
    await generator.complete_json(
        schema=Ping, system="Return JSON.", user="Return an answer.", max_tokens=64
    )
    url, payload = seen[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert payload["max_completion_tokens"] == 64
    assert "max_tokens" not in payload
    assert payload["temperature"] == 0.2


async def test_retries_429_then_succeeds() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "0"},
                json={"error": "rate limited"},
            )
        return completion('{"answer": "ok"}')

    generator = OpenAICompatibleGenerator(
        settings(), transport=httpx.MockTransport(handler)
    )
    result = await generator.complete_json(
        schema=Ping, system="Return JSON.", user="Return an answer.", max_tokens=20
    )
    assert result.answer == "ok"
    assert len(calls) == 2


async def test_gemini_model_moves_to_gemini_base() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return completion('{"answer": "ok"}')

    generator = OpenAICompatibleGenerator(
        settings(), transport=httpx.MockTransport(handler)
    )
    result = await generator.complete_json(
        schema=Ping,
        system="Return JSON.",
        user="Return an answer.",
        max_tokens=20,
    )
    assert result.answer == "ok"
    assert str(seen[0].url) == f"{GEMINI_OPENAI_BASE}/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer test-key"


async def test_non_gemini_keeps_configured_base() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return completion('{"answer": "ok"}')

    generator = OpenAICompatibleGenerator(
        settings(generator_model="gpt-test"), transport=httpx.MockTransport(handler)
    )
    await generator.complete_json(
        schema=Ping, system="Return JSON.", user="Return an answer.", max_tokens=20
    )
    assert str(seen[0].url) == "https://api.openai.com/v1/chat/completions"


async def test_falls_back_to_json_object_then_plain() -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            return httpx.Response(400, json={"error": "json_schema unsupported"})
        return completion('```json\n{"answer": "fallback"}\n```')

    generator = OpenAICompatibleGenerator(
        settings(), transport=httpx.MockTransport(handler)
    )
    result = await generator.complete_json(
        schema=Ping, system="Return JSON.", user="Return an answer.", max_tokens=20
    )
    assert result.answer == "fallback"
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[1]["response_format"] == {"type": "json_object"}


async def test_raises_with_response_body_after_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    generator = OpenAICompatibleGenerator(
        settings(), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(GeneratorError) as error:
        await generator.complete_json(
            schema=Ping, system="Return JSON.", user="Return an answer.", max_tokens=20
        )
    assert "HTTP 400" in str(error.value)


async def test_invalid_content_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return completion("not json at all")

    generator = OpenAICompatibleGenerator(
        settings(), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(GeneratorError):
        await generator.complete_json(
            schema=Ping, system="Return JSON.", user="Return an answer.", max_tokens=20
        )
