from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


async def run(url: str) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from Core.registry import SourceRegistry
    from Core.settings import Settings
    from tool.article_fetch import HtmlArticleFetcher
    from tool.extract import TrafilaturaExtractor
    from tool.http import HttpClient
    from tool.link_resolve import GoogleNewsLinkResolver

    settings = Settings(app_env="dev")
    registry = SourceRegistry.load()
    http = HttpClient(settings)
    resolver = GoogleNewsLinkResolver(http)
    fetcher = HtmlArticleFetcher(http, registry, settings)
    extractor = TrafilaturaExtractor()

    try:
        resolved = await resolver.resolve(url)
        print(f"input:    {url}")
        print(f"resolved: {resolved}")
        if not resolved:
            print("link resolution failed")
            return

        page = await fetcher.fetch(resolved)
        print(f"fetched:  HTTP {page.status} {page.final_url} ({page.elapsed_ms} ms)")
        extracted = extractor.extract(page)
        print(f"text:     {extracted.word_count} words, quality {extracted.quality:.2f}")
        print("---")
        print(extracted.text[:500])
    except Exception as error:  # noqa: BLE001
        print(f"failed:   {type(error).__name__}: {error}")
    finally:
        await http.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe link resolution, fetch and extraction.")
    parser.add_argument(
        "url",
        nargs="?",
        default="https://www.bbc.com/news",
    )
    args = parser.parse_args()
    asyncio.run(run(args.url))


if __name__ == "__main__":
    main()
