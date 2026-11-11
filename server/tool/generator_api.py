from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import TypeVar

import httpx
from pydantic import BaseModel

from Core.errors import GeneratorError, GeneratorNotConfigured
from Core.settings import Settings

ModelT = TypeVar("ModelT", bound=BaseModel)

GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"


def parse_stream_delta(line: str) -> str | None:
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data or data == "[DONE]":
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    delta = first.get("delta")
    if not isinstance(delta, dict):
        return None
    content = delta.get("content")
    return content if isinstance(content, str) and content else None


class OpenAICompatibleGenerator:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not settings.generator_api_key or not settings.generator_model:
            raise GeneratorNotConfigured()
        self._settings = settings
        self._transport = transport
        self._base_url = self._resolve_base_url(settings)

    @staticmethod
    def _resolve_base_url(settings: Settings) -> str:
        base = settings.generator_base_url.rstrip("/")
        model = settings.generator_model.lower()
        if not base:
            base = GEMINI_OPENAI_BASE if "gemini" in model else "https://api.openai.com/v1"
        if "gemini" in model and "openai.com" in base:
            base = GEMINI_OPENAI_BASE
        if "generativelanguage.googleapis.com" in base and not base.endswith("/openai"):
            base = f"{base}/openai"
        return base

    async def complete_json(
        self,
        *,
        schema: type[ModelT],
        system: str,
        user: str,
        max_tokens: int,
    ) -> ModelT:
        return await self.complete_chat(
            schema=schema,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )

    async def complete_chat(
        self,
        *,
        schema: type[ModelT],
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> ModelT:
        headers = {"Authorization": f"Bearer {self._settings.generator_api_key}"}
        url = f"{self._base_url}/chat/completions"
        token_field = (
            "max_completion_tokens" if "groq.com" in self._base_url else "max_tokens"
        )
        instruction = (
            "Return only a JSON object that matches the requested schema. "
            "No markdown fences, no commentary."
        )
        prepared = [dict(message) for message in messages]
        if prepared and prepared[0].get("role") == "system":
            prepared[0]["content"] = f"{prepared[0]['content']}\n{instruction}"
        else:
            prepared.insert(0, {"role": "system", "content": instruction})
        formats: list[dict | None] = [
            {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                },
            },
            {"type": "json_object"},
            None,
        ]

        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._settings.generator_timeout_s,
        ) as client:
            last_error = "unknown generator failure"
            for index, response_format in enumerate(formats):
                payload = {
                    "model": self._settings.generator_model,
                    "messages": prepared,
                    token_field: max_tokens,
                    "temperature": self._settings.generator_temperature,
                }
                if response_format is not None:
                    payload["response_format"] = response_format
                response = None
                for attempt in range(3):
                    try:
                        response = await client.post(url, json=payload, headers=headers)
                    except httpx.HTTPError as error:
                        raise GeneratorError(str(error)) from error
                    if (
                        response.status_code == 429
                        or response.status_code >= 500
                    ) and attempt < 2:
                        await asyncio.sleep(self._retry_delay(response, attempt))
                        continue
                    break
                if response is None:
                    raise GeneratorError("generator returned no response")

                if response.status_code >= 400:
                    last_error = (
                        f"HTTP {response.status_code}: {response.text[:500]}"
                    )
                    retryable = response.status_code in {400, 422}
                    if retryable and index < len(formats) - 1:
                        continue
                    raise GeneratorError(last_error)

                try:
                    content = response.json()["choices"][0]["message"]["content"]
                    return self._parse(schema, content)
                except (KeyError, IndexError, TypeError) as error:
                    last_error = "invalid generator response shape"
                    if index < len(formats) - 1:
                        continue
                    raise GeneratorError(last_error) from error
                except ValueError as error:
                    last_error = f"invalid JSON from generator: {error}"
                    if index < len(formats) - 1:
                        continue
                    raise GeneratorError(last_error) from error

        raise GeneratorError(last_error)

    async def stream_text(
        self,
        *,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> AsyncIterator[str]:
        headers = {"Authorization": f"Bearer {self._settings.generator_api_key}"}
        url = f"{self._base_url}/chat/completions"
        token_field = (
            "max_completion_tokens" if "groq.com" in self._base_url else "max_tokens"
        )
        payload = {
            "model": self._settings.generator_model,
            "messages": messages,
            "stream": True,
            token_field: max_tokens,
            "temperature": self._settings.generator_temperature,
        }
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._settings.generator_timeout_s,
        ) as client, client.stream(
            "POST", url, json=payload, headers=headers
        ) as response:
            if response.status_code >= 400:
                body = await response.aread()
                raise GeneratorError(
                    f"HTTP {response.status_code}: "
                    f"{body.decode('utf-8', errors='replace')[:500]}"
                )
            async for line in response.aiter_lines():
                delta = parse_stream_delta(line)
                if delta:
                    yield delta

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        header = response.headers.get("retry-after")
        if header:
            try:
                return min(float(header), 10.0)
            except ValueError:
                pass
        return min(self._settings.generator_retry_base_s * (2**attempt), 10.0)

    @staticmethod
    def _parse(schema: type[ModelT], content) -> ModelT:
        if not isinstance(content, str):
            raise TypeError("generator content is not text")
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return schema.model_validate_json(text)
        except ValueError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return schema.model_validate_json(text[start : end + 1])
            raise
