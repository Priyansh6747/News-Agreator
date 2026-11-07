from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Core.models import (
    Article,
    Backend,
    Candidate,
    CredibilityScore,
    ImportanceScore,
    StoryCluster,
)
from Core.prompts import FACT_SYSTEM, ExtractedFacts, build_fact_prompt
from Core.registry import SourceRegistry
from Core.settings import Settings
from Core.urls import domain_of
from tool.article_fetch import HtmlArticleFetcher
from tool.extract import TrafilaturaExtractor
from tool.generator_api import OpenAICompatibleGenerator
from tool.http import HttpClient
from tool.link_resolve import GoogleNewsLinkResolver


async def run(url: str, query: str) -> None:
    settings = Settings()
    registry = SourceRegistry.load()
    http = HttpClient(settings)
    resolver = GoogleNewsLinkResolver(http)
    fetcher = HtmlArticleFetcher(http, registry, settings)
    extractor = TrafilaturaExtractor()
    generator = OpenAICompatibleGenerator(settings)

    try:
        resolved = await resolver.resolve(url)
        print(f"resolved: {resolved}")
        if not resolved:
            return
        page = await fetcher.fetch(resolved)
        extracted = extractor.extract(page)
        print(f"text: {extracted.word_count} words")
        candidate = Candidate(
            title="Gold prices probe",
            url=page.final_url,
            publisher=registry.publisher_for(domain_of(page.final_url)),
            domain=domain_of(page.final_url),
            snippet=None,
            published_at=None,
            backend=Backend.PUBLISHER_RSS,
        )
        cluster = StoryCluster(
            id="c_probe",
            headline=candidate.title,
            members=[
                Article(
                    candidate=candidate,
                    canonical_url=page.final_url,
                )
            ],
            families=[],
            importance=ImportanceScore(score=0.0),
            credibility=CredibilityScore(score=0.0),
        )
        prompt = build_fact_prompt(
            query, cluster, extracted.text[: settings.fact_text_chars]
        )
        print(f"prompt chars: {len(prompt)}")
        print("--- prompt head ---")
        print(prompt[:1200])
        print("--- prompt tail ---")
        print(prompt[-800:])
        result = await generator.complete_json(
            schema=ExtractedFacts,
            system=FACT_SYSTEM,
            user=prompt,
            max_tokens=settings.fact_max_tokens,
        )
        print("--- current prompt ---")
        print(result.model_dump_json(indent=2))

        stronger = (
            f"{FACT_SYSTEM}\n"
            "Extract 3 to 5 concrete facts. Each fact must include the number, "
            "percentage, date, or amount that carries the claim and a verbatim "
            "quote of at most 25 words. Do not return an empty list when the text "
            "contains prices, percentages, dates, or named events.\n"
            'Example: {"facts": [{"claim": "Gold rose 4.5%", "value": "4.5%", '
            '"quote": "Gold prices surged 4.5 per cent for the week."}]}'
        )
        result2 = await generator.complete_json(
            schema=ExtractedFacts,
            system=stronger,
            user=prompt,
            max_tokens=max(settings.fact_max_tokens, 2048),
        )
        print("--- stronger prompt ---")
        print(result2.model_dump_json(indent=2))
    except Exception as error:  # noqa: BLE001
        print(f"failed: {type(error).__name__}: {error}")
    finally:
        await http.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe fact extraction for one URL.")
    parser.add_argument("url")
    parser.add_argument("--query", default="gold prices")
    args = parser.parse_args()
    asyncio.run(run(args.url, args.query))


if __name__ == "__main__":
    main()
