from __future__ import annotations

from typing import TypeVar

import httpx
from pydantic import BaseModel

from Core.errors import GeneratorError, GeneratorNotConfigured
from Core.settings import Settings

ModelT = TypeVar("ModelT", bound=BaseModel)


class OpenAICompatibleGenerator:
    def __init__(self, settings: Settings):
        if not settings.generator_api_key or not settings.generator_model:
            raise GeneratorNotConfigured()
        self._settings = settings

    async def complete_json(
        self,
        *,
        schema: type[ModelT],
        system: str,
        user: str,
        max_tokens: int,
    ) -> ModelT:
        payload = {
            "model": self._settings.generator_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                },
            },
        }
        headers = {"Authorization": f"Bearer {self._settings.generator_api_key}"}
        url = f"{self._settings.generator_base_url.rstrip('/')}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self._settings.generator_timeout_s) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise GeneratorError(str(error)) from error

        try:
            content = response.json()["choices"][0]["message"]["content"]
            return schema.model_validate_json(content)
        except (KeyError, IndexError, ValueError) as error:
            raise GeneratorError("invalid generator response") from error
