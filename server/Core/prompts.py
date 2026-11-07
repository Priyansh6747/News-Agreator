from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from Core.models import StoryCluster

BRIEF_SYSTEM = (
    "You write structured news briefs from clustered headlines and extracted facts. "
    "Use only the cluster ids supplied by the user. Never invent a URL, publisher, date, "
    "or fact. Every timeline entry, key fact, and position must cite one cluster id from "
    "the input. A disagreement needs at least two positions from different cluster ids. "
    "If the evidence is thin, say so in thin_sourcing instead of guessing."
)

FACT_SYSTEM = (
    "You extract verifiable facts from one news article. Return 3 to 5 concrete facts. "
    "Each fact must include the number, percentage, date, or amount that carries the claim, "
    "and a verbatim quote of at most 25 words. Do not return an empty list when the text "
    "contains prices, percentages, dates, or named events. Do not infer or add external "
    "knowledge."
)


class DraftFactRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    meaning: str
    cluster_id: str


class DraftTimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: datetime
    what: str
    cluster_id: str


class DraftPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    cluster_id: str


class DraftDisagreement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    positions: list[DraftPosition] = Field(min_length=2)


class BriefDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    key_facts: list[DraftFactRow] = Field(default_factory=list)
    timeline: list[DraftTimelineEntry] = Field(default_factory=list)
    disagreements: list[DraftDisagreement] = Field(default_factory=list)
    thin_sourcing: list[str] = Field(default_factory=list)


class DraftFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    value: str | None = None
    quote: str | None = None


class ExtractedFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: list[DraftFact] = Field(default_factory=list)


def _cluster_payload(cluster: StoryCluster) -> dict[str, object]:
    return {
        "cluster_id": cluster.id,
        "headline": cluster.headline,
        "publishers": sorted(
            {member.candidate.publisher for member in cluster.members if member.candidate.publisher}
        ),
        "first_seen": cluster.first_seen.isoformat() if cluster.first_seen else None,
        "last_seen": cluster.last_seen.isoformat() if cluster.last_seen else None,
        "importance": cluster.importance.score,
        "credibility": cluster.credibility.score,
        "facts": [
            {
                "claim": fact.claim,
                "value": fact.value,
                "quote": fact.quote,
                "source_url": fact.source_url,
                "published_at": fact.published_at.isoformat(),
            }
            for fact in cluster.facts
        ],
    }


def build_brief_prompt(query: str, clusters: list[StoryCluster]) -> str:
    payload = [_cluster_payload(cluster) for cluster in clusters]
    return (
        f"Query: {query}\n\n"
        "Clusters (JSON). Cite these cluster_id values only:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def build_fact_prompt(query: str, cluster: StoryCluster, text: str) -> str:
    publishers = sorted(
        {member.candidate.publisher for member in cluster.members if member.candidate.publisher}
    )
    return (
        f"Query: {query}\n"
        f"Headline: {cluster.headline}\n"
        f"Publishers: {', '.join(publishers) or 'unknown'}\n\n"
        f"Article text:\n{text}"
    )
