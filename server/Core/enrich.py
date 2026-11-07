from __future__ import annotations

import asyncio

from Core.coverage import CoverageCollector
from Core.errors import ExtractionFailed, FetchBlocked, HttpError, HttpTimeout
from Core.models import Fact, StoryCluster, TextStatus, validate_http_url
from Core.ports import (
    ArticleFetcher,
    Clock,
    DecisionEngine,
    Generator,
    LinkResolver,
    TextExtractor,
)
from Core.prompts import FACT_SYSTEM, ExtractedFacts, build_fact_prompt
from Core.registry import SourceRegistry
from Core.settings import Settings


def _set_status(
    member,
    status: TextStatus,
    coverage: CoverageCollector,
) -> None:
    member.text_status = status
    coverage.record_text_status(status)


def _to_facts(
    result,
    cluster: StoryCluster,
    source_url: str,
    published_at,
) -> list[Fact]:
    if isinstance(result, ExtractedFacts):
        drafts = result.facts
    else:
        drafts = ExtractedFacts.model_validate(result.model_dump()).facts

    facts: list[Fact] = []
    for draft in drafts:
        claim = draft.claim.strip()
        if not claim:
            continue
        quote = draft.quote
        if quote:
            words = quote.split()
            if len(words) > 25:
                quote = " ".join(words[:25])
        try:
            facts.append(
                Fact(
                    claim=claim,
                    value=draft.value,
                    source_url=source_url,
                    published_at=published_at,
                    quote=quote,
                    cluster_id=cluster.id,
                )
            )
        except ValueError:
            continue
    return facts


async def _enrich_cluster(
    cluster: StoryCluster,
    *,
    query: str,
    resolver: LinkResolver | None,
    fetcher: ArticleFetcher,
    extractor: TextExtractor,
    generator: Generator | None,
    decisions: DecisionEngine,
    registry: SourceRegistry,
    settings: Settings,
    coverage: CoverageCollector,
    clock: Clock,
) -> None:
    representative = cluster.members[0]
    for member in cluster.members[1:]:
        _set_status(member, TextStatus.NOT_FETCHED, coverage)

    candidate = representative.candidate
    policy = registry.fetch_policy(candidate.domain)
    if policy.mode != "fetch":
        _set_status(representative, TextStatus.SKIPPED_POLICY, coverage)
        return

    url = representative.canonical_url
    if candidate.needs_resolution:
        resolved = await resolver.resolve(url) if resolver is not None else None
        if not resolved:
            _set_status(representative, TextStatus.NOT_FETCHED, coverage)
            coverage.note(f"could not resolve {url}")
            return
        url = resolved
        representative.canonical_url = resolved

    try:
        page = await fetcher.fetch(url)
    except HttpTimeout:
        _set_status(representative, TextStatus.TIMEOUT, coverage)
        coverage.note(f"timeout fetching {url}")
        return
    except FetchBlocked as error:
        _set_status(representative, TextStatus.BLOCKED, coverage)
        coverage.note(f"blocked {url}: {error.reason}")
        return
    except HttpError as error:
        _set_status(representative, TextStatus.BLOCKED, coverage)
        coverage.note(f"fetch failed {url}: {error.reason}")
        return
    except Exception as error:  # noqa: BLE001
        _set_status(representative, TextStatus.BLOCKED, coverage)
        coverage.note(f"fetch failed {url}: {type(error).__name__}")
        return

    try:
        extracted = extractor.extract(page)
    except ExtractionFailed as error:
        _set_status(representative, TextStatus.THIN, coverage)
        coverage.note(f"extraction failed {url}: {error}")
        return

    representative.word_count = extracted.word_count
    representative.fetched_at = clock.now()
    representative.canonical_url = page.final_url or url

    if extracted.word_count < settings.extract_min_words:
        _set_status(representative, TextStatus.THIN, coverage)
        return

    try:
        injection_risk = await decisions.injection_risk(extracted.text)
    except Exception as error:  # noqa: BLE001
        _set_status(representative, TextStatus.BLOCKED, coverage)
        coverage.note(
            f"injection gate failed for {representative.canonical_url}: "
            f"{type(error).__name__}; blocked"
        )
        return
    if injection_risk >= settings.injection_threshold:
        _set_status(representative, TextStatus.BLOCKED, coverage)
        coverage.note(
            f"injection risk {injection_risk:.2f} blocked "
            f"{representative.canonical_url}"
        )
        return

    if generator is None:
        _set_status(representative, TextStatus.OK, coverage)
        coverage.note("generator not configured; article text read but no facts extracted")
        return

    prompt = build_fact_prompt(
        query,
        cluster,
        extracted.text[: settings.fact_text_chars],
    )
    try:
        result = await generator.complete_json(
            schema=ExtractedFacts,
            system=FACT_SYSTEM,
            user=prompt,
            max_tokens=settings.fact_max_tokens,
        )
    except Exception as error:  # noqa: BLE001
        _set_status(representative, TextStatus.OK, coverage)
        coverage.note(
            f"fact extraction failed {representative.canonical_url}: "
            f"{type(error).__name__}: {str(error)[:300]}"
        )
        return

    published_at = representative.candidate.published_at or clock.now()
    try:
        validate_http_url(representative.canonical_url)
    except ValueError:
        _set_status(representative, TextStatus.OK, coverage)
        coverage.note(f"invalid source URL for facts: {representative.canonical_url}")
        return

    facts = _to_facts(result, cluster, representative.canonical_url, published_at)
    cluster.facts = facts
    _set_status(representative, TextStatus.OK, coverage)
    if not facts:
        coverage.note(f"no facts extracted for {representative.canonical_url}")


async def enrich_clusters(
    clusters: list[StoryCluster],
    *,
    query: str,
    resolver: LinkResolver | None,
    fetcher: ArticleFetcher | None,
    extractor: TextExtractor | None,
    generator: Generator | None,
    decisions: DecisionEngine,
    registry: SourceRegistry,
    settings: Settings,
    coverage: CoverageCollector,
    clock: Clock,
) -> list[StoryCluster]:
    if not clusters:
        return []

    selected = clusters[: settings.fetch_max_reps]
    selected_ids = {id(cluster) for cluster in selected}
    for cluster in clusters:
        if id(cluster) in selected_ids:
            continue
        for member in cluster.members:
            _set_status(member, TextStatus.NOT_FETCHED, coverage)

    if fetcher is None or extractor is None:
        for cluster in selected:
            for member in cluster.members:
                policy = registry.fetch_policy(member.candidate.domain)
                status = (
                    TextStatus.SKIPPED_POLICY
                    if policy.mode != "fetch"
                    else TextStatus.NOT_FETCHED
                )
                _set_status(member, status, coverage)
        coverage.note("article fetch and extraction are not enabled in this build")
        return clusters

    semaphore = asyncio.Semaphore(max(1, settings.fetch_concurrency))

    async def process(cluster: StoryCluster) -> None:
        async with semaphore:
            await _enrich_cluster(
                cluster,
                query=query,
                resolver=resolver,
                fetcher=fetcher,
                extractor=extractor,
                generator=generator,
                decisions=decisions,
                registry=registry,
                settings=settings,
                coverage=coverage,
                clock=clock,
            )

    await asyncio.gather(*(process(cluster) for cluster in selected))
    return clusters
