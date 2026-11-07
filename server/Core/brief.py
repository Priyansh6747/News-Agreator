from __future__ import annotations

from datetime import datetime

from Core.coverage import CoverageCollector
from Core.models import (
    Brief,
    CoverageStatus,
    Disagreement,
    FactRow,
    Position,
    QueryPlan,
    StoryCluster,
    TimelineEntry,
    validate_http_url,
)
from Core.ports import Clock, Generator
from Core.prompts import BRIEF_SYSTEM, BriefDraft, build_brief_prompt
from Core.settings import Settings


def _representative(cluster: StoryCluster | None) -> tuple[str, datetime] | None:
    if cluster is None:
        return None
    members = [member for member in cluster.members if member.candidate.published_at]
    if not members:
        return None
    member = max(members, key=lambda item: item.candidate.published_at)
    url = member.canonical_url or member.candidate.url
    try:
        validate_http_url(url)
    except ValueError:
        return None
    return url, member.candidate.published_at


def _from_draft(
    draft: BriefDraft,
    *,
    query: str,
    plan: QueryPlan,
    clusters: list[StoryCluster],
    coverage: CoverageCollector,
    clock: Clock,
) -> Brief:
    index = {cluster.id: cluster for cluster in clusters}
    key_facts: list[FactRow] = []
    for row in draft.key_facts:
        representative = _representative(index.get(row.cluster_id))
        if representative is None:
            coverage.note(f"dropped fact with unknown cluster id: {row.cluster_id}")
            continue
        key_facts.append(
            FactRow(
                value=row.value,
                meaning=row.meaning,
                source_url=representative[0],
                published_at=representative[1],
            )
        )

    timeline: list[TimelineEntry] = []
    for entry in draft.timeline:
        representative = _representative(index.get(entry.cluster_id))
        if representative is None:
            coverage.note(f"dropped timeline entry with unknown cluster id: {entry.cluster_id}")
            continue
        timeline.append(
            TimelineEntry(at=entry.at, what=entry.what, source_url=representative[0])
        )

    disagreements: list[Disagreement] = []
    for item in draft.disagreements:
        positions: list[Position] = []
        for position in item.positions:
            representative = _representative(index.get(position.cluster_id))
            if representative is None:
                continue
            positions.append(
                Position(
                    claim=position.claim,
                    source_url=representative[0],
                    published_at=representative[1],
                )
            )
        if len(positions) >= 2:
            disagreements.append(Disagreement(topic=item.topic, positions=positions))

    return Brief(
        query=query,
        query_class=plan.query_class,
        answer=draft.answer.strip(),
        key_facts=key_facts,
        timeline=timeline,
        disagreements=disagreements,
        thin_sourcing=list(draft.thin_sourcing),
        stories=clusters,
        coverage=coverage.finish(),
        generated_at=clock.now(),
    )


def _fallback(
    *,
    query: str,
    plan: QueryPlan,
    clusters: list[StoryCluster],
    coverage: CoverageCollector,
    clock: Clock,
) -> Brief:
    key_facts: list[FactRow] = []
    for cluster in clusters:
        for fact in cluster.facts:
            key_facts.append(
                FactRow(
                    value=fact.value or fact.claim,
                    meaning=fact.claim,
                    source_url=fact.source_url,
                    published_at=fact.published_at,
                )
            )

    timeline: list[TimelineEntry] = []
    entries: list[tuple[datetime, str, str]] = []
    for cluster in clusters:
        for member in cluster.members:
            if member.candidate.published_at is None:
                continue
            url = member.canonical_url or member.candidate.url
            try:
                validate_http_url(url)
            except ValueError:
                continue
            entries.append((member.candidate.published_at, member.candidate.title, url))
    entries.sort(key=lambda item: item[0], reverse=True)
    for published_at, title, url in entries[:5]:
        timeline.append(TimelineEntry(at=published_at, what=title, source_url=url))

    publishers = {
        member.candidate.publisher
        for cluster in clusters
        for member in cluster.members
        if member.candidate.publisher
    }
    if clusters:
        answer = (
            f"{len(clusters)} stories from {len(publishers)} publishers were ranked for "
            f"'{query}'. Article text was not read in this build, so the brief is limited "
            "to headlines and source metadata."
        )
    else:
        answer = f"No stories were found for '{query}'."

    thin: list[str] = []
    if not key_facts:
        thin.append("No article text was read; no key facts were extracted.")
    status = coverage.finish().status
    if status is not CoverageStatus.COMPLETE:
        thin.append(f"Coverage is {status.value}.")

    return Brief(
        query=query,
        query_class=plan.query_class,
        answer=answer,
        key_facts=key_facts,
        timeline=timeline,
        disagreements=[],
        thin_sourcing=thin,
        stories=clusters,
        coverage=coverage.finish(),
        generated_at=clock.now(),
    )


async def build_brief(
    *,
    query: str,
    plan: QueryPlan,
    clusters: list[StoryCluster],
    coverage: CoverageCollector,
    generator: Generator | None,
    settings: Settings,
    clock: Clock,
) -> Brief:
    if generator is not None and clusters:
        try:
            result = await generator.complete_json(
                schema=BriefDraft,
                system=BRIEF_SYSTEM,
                user=build_brief_prompt(query, clusters),
                max_tokens=settings.generator_max_tokens,
            )
            draft = BriefDraft.model_validate(result.model_dump())
            if draft.answer.strip():
                return _from_draft(
                    draft,
                    query=query,
                    plan=plan,
                    clusters=clusters,
                    coverage=coverage,
                    clock=clock,
                )
            coverage.note("generator returned an empty answer; using fallback")
        except Exception as error:  # noqa: BLE001
            coverage.note(f"generator unavailable: {type(error).__name__}")

    return _fallback(
        query=query,
        plan=plan,
        clusters=clusters,
        coverage=coverage,
        clock=clock,
    )
