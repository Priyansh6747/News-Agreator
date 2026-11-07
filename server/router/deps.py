from __future__ import annotations

import importlib.util
import logging
from functools import lru_cache

from Core.errors import GeneratorNotConfigured
from Core.models import Backend
from Core.pipeline import Pipeline, SystemClock
from Core.ports import DecisionEngine
from Core.registry import SourceRegistry
from Core.settings import Settings, get_settings
from tool.article_fetch import HtmlArticleFetcher
from tool.bing_news import BingNewsBackend
from tool.decisions_heuristic import HeuristicDecisionEngine
from tool.extract import TrafilaturaExtractor
from tool.fixture_adapters import FixtureSearchBackend
from tool.gdelt import GdeltBackend
from tool.generator_api import OpenAICompatibleGenerator
from tool.google_news import GoogleNewsBackend
from tool.http import HttpClient
from tool.link_resolve import GoogleNewsLinkResolver
from tool.publisher_rss import PublisherRssBackend

logger = logging.getLogger(__name__)
_http_client: HttpClient | None = None


def _enabled(settings: Settings, backend: Backend) -> bool:
    return backend.value in settings.enabled_backends


def _build_decisions(
    settings: Settings,
) -> tuple[DecisionEngine, int | None, int | None]:
    heuristic = HeuristicDecisionEngine()
    if settings.app_env == "demo" or settings.decision_engine == "heuristic":
        return heuristic, None, None
    try:
        from tool.decisions_laya import LayaDecisionEngine

        return (
            LayaDecisionEngine(
                fallback=heuristic,
                preload=settings.laya_preload,
                device=settings.laya_device,
                default=settings.laya_default_model,
                max_loaded=settings.laya_max_loaded,
                batch_size=settings.laya_batch_size,
            ),
            settings.laya_assess_top or None,
            settings.laya_type_top or None,
        )
    except Exception as error:  # noqa: BLE001
        logger.warning("laya unavailable (%s); using heuristic", type(error).__name__)
        return heuristic, None, None


def build_pipeline(settings: Settings) -> Pipeline:
    global _http_client
    registry = SourceRegistry.load()
    clock = SystemClock()
    decisions, assess_top, type_top = _build_decisions(settings)

    if settings.app_env == "demo":
        now = clock.now()
        backends = [
            FixtureSearchBackend(backend, now)
            for backend in Backend
            if _enabled(settings, backend)
        ]
        return Pipeline(
            backends=backends,
            decisions=decisions,
            registry=registry,
            settings=settings,
            clock=clock,
            assess_top=assess_top,
            type_top=type_top,
        )

    _http_client = HttpClient(settings)
    http = _http_client
    backends = []
    if _enabled(settings, Backend.GOOGLE_NEWS):
        backends.append(GoogleNewsBackend(http, settings, clock))
    if _enabled(settings, Backend.BING_NEWS):
        backends.append(BingNewsBackend(http, settings, registry, clock))
    if _enabled(settings, Backend.GDELT):
        backends.append(GdeltBackend(http, settings, registry, clock))
    if _enabled(settings, Backend.PUBLISHER_RSS):
        backends.append(PublisherRssBackend(http, registry, settings, clock))

    generator = None
    try:
        generator = OpenAICompatibleGenerator(settings)
    except GeneratorNotConfigured:
        pass

    return Pipeline(
        backends=backends,
        decisions=decisions,
        registry=registry,
        settings=settings,
        clock=clock,
        resolver=GoogleNewsLinkResolver(http),
        fetcher=HtmlArticleFetcher(http, registry, settings),
        extractor=TrafilaturaExtractor(),
        generator=generator,
        assess_top=assess_top,
        type_top=type_top,
    )


@lru_cache(maxsize=1)
def get_pipeline() -> Pipeline:
    return build_pipeline(get_settings())


async def close_pipeline() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
    get_pipeline.cache_clear()


def readiness() -> dict[str, object]:
    settings = get_settings()
    pipeline = get_pipeline()
    return {
        "status": "ready" if pipeline.backends else "degraded",
        "app_env": settings.app_env,
        "backends": [backend.name.value for backend in pipeline.backends],
        "generator": pipeline.generator is not None,
        "decision_engine": type(pipeline.decisions).__name__,
        "laya_installed": importlib.util.find_spec("laya") is not None,
    }
