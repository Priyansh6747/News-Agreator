from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel

from Core.errors import GeneratorError, GeneratorNotConfigured
from Core.settings import Settings
from tool.generator_api import OpenAICompatibleGenerator


class Ping(BaseModel):
    answer: str


async def run() -> None:
    settings = Settings()
    print(f"base:  {settings.generator_base_url}")
    print(f"model: {settings.generator_model}")
    print(f"key:   {'set' if settings.generator_api_key else 'missing'}")
    try:
        generator = OpenAICompatibleGenerator(settings)
        result = await generator.complete_json(
            schema=Ping,
            system="Return JSON.",
            user='Return {"answer":"ok"}',
            max_tokens=128,
        )
        print(f"result: {result}")
    except GeneratorNotConfigured:
        print("generator is not configured (set API key and model)")
    except GeneratorError as error:
        print(f"generator failed: {error}")


if __name__ == "__main__":
    asyncio.run(run())
