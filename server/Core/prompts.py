from __future__ import annotations

import json
from datetime import datetime, timedelta

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from Core.models import Brief, ChatMessage, StoryCluster
from Core.settings import Settings

BRIEF_SYSTEM = (
    "You write structured news briefs from clustered headlines and extracted facts. "
    "Use only the cluster ids supplied by the user. Never invent a URL, publisher, date, "
    "or fact. Every timeline entry, key fact, and position must cite one cluster id from "
    "the input. A disagreement needs at least two positions from different cluster ids. "
    "Clusters marked background: true are older than the current news window; use them "
    "for timeline, history, and comparison context only, and never present their figures "
    "as current. The timeline must include background clusters when any are supplied, so "
    "it covers more than today. If the evidence is thin, say so in thin_sourcing instead "
    "of guessing."
)

FACT_SYSTEM = (
    "You extract verifiable facts from one news article. Return 3 to 5 concrete facts. "
    "Each fact must include the number, percentage, date, or amount that carries the claim, "
    "and a verbatim quote of at most 25 words. Do not return an empty list when the text "
    "contains prices, percentages, dates, or named events. Do not infer or add external "
    "knowledge. Example: "
    '{"facts": [{"claim": "Gold rose 4.5%", "value": "4.5%", '
    '"quote": "Gold prices surged 4.5 per cent for the week."}]}'
)


class DraftFactRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: str
    meaning: str
    cluster_id: str


class DraftTimelineEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    at: datetime
    what: str
    cluster_id: str


class DraftPosition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim: str
    cluster_id: str


class DraftDisagreement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str
    positions: list[DraftPosition] = Field(min_length=2)


class BriefDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer: str
    key_facts: list[DraftFactRow] = Field(default_factory=list)
    timeline: list[DraftTimelineEntry] = Field(default_factory=list)
    disagreements: list[DraftDisagreement] = Field(default_factory=list)
    thin_sourcing: list[str] = Field(default_factory=list)


class ChatToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = "news_brief"
    query: str = ""


class ChatDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reply: str | None = None
    tool_calls: list[ChatToolCall] = Field(default_factory=list)


CHAT_SYSTEM = (
    "You are NewsAgreator, a news analyst chat assistant. You can answer directly or call one "
    "tool.\n"
    "Tool: news_brief(query: string) retrieves recent news and builds a grounded brief. Use it "
    "for current events, markets, companies, conflicts, prices, or anything that needs fresh "
    "sources.\n"
    "Use reply for greetings, thanks, capability questions, and follow-ups that can be answered "
    "from the supplied latest brief.\n"
    "When you call news_brief, make the query self-contained: resolve pronouns and follow-ups "
    "into a full search query that includes the topic.\n"
    "Never invent facts, numbers, publishers, or URLs. If the tool result is partial, say so.\n"
    "Return only JSON matching the ChatDecision schema: either reply, or tool_calls with one "
    "news_brief call. Today is {today}."
)

CHAT_ANSWER_SYSTEM = (
    "You are NewsAgreator answering the latest message in a news chat. Use only the supplied "
    "news_brief tool result and the conversation. Write a concise, conversational answer to the "
    "user's latest message in plain text. Do not use markdown, headings, or bullet lists. Do not "
    "repeat the structured brief or every fact. State uncertainty when coverage is partial. "
    "Stories older than the current news window are background context; never present them as "
    "current."
)


class DraftFact(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    claim: str = Field(
        validation_alias=AliasChoices("claim", "fact", "statement", "text")
    )
    value: str | None = Field(
        default=None,
        validation_alias=AliasChoices("value", "number", "amount", "data"),
    )
    quote: str | None = Field(
        default=None,
        validation_alias=AliasChoices("quote", "evidence", "excerpt", "source_quote"),
    )


class ExtractedFacts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    facts: list[DraftFact] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, value):
        if isinstance(value, list):
            return {"facts": value}
        if isinstance(value, dict) and "facts" not in value:
            for key in ("fact", "items", "data", "results"):
                if key in value:
                    return {"facts": value[key]}
        return value


def _cluster_payload(
    cluster: StoryCluster,
    *,
    background: bool = False,
) -> dict[str, object]:
    return {
        "cluster_id": cluster.id,
        "headline": cluster.headline,
        "background": background,
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


def build_brief_prompt(
    query: str,
    clusters: list[StoryCluster],
    brief_schema: str | None = None,
    *,
    now: datetime | None = None,
    freshness_hours: int | None = None,
) -> str:
    cutoff = (
        now - timedelta(hours=freshness_hours)
        if now is not None and freshness_hours is not None
        else None
    )
    payload = [
        _cluster_payload(
            cluster,
            background=(
                cutoff is not None
                and cluster.last_seen is not None
                and cluster.last_seen < cutoff
            ),
        )
        for cluster in clusters
    ]
    schema_line = f"Preferred brief schema: {brief_schema}\n" if brief_schema else ""
    return (
        f"Query: {query}\n"
        f"{schema_line}\n"
        "Clusters (JSON). Cite these cluster_id values only:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _chat_history(messages: list[ChatMessage], limit: int) -> list[dict[str, str]]:
    kept = [message for message in messages if message.content.strip()]
    window = kept[-max(1, limit) :]
    return [
        {"role": message.role.value, "content": message.content}
        for message in window
    ]


def brief_context(brief: Brief, max_chars: int = 12000) -> str:
    payload = {
        "query": brief.query,
        "generated_at": brief.generated_at.isoformat(),
        "coverage": brief.coverage.status.value,
        "answer": brief.answer,
        "key_facts": [
            {
                "value": fact.value,
                "meaning": fact.meaning,
                "published_at": fact.published_at.isoformat(),
            }
            for fact in brief.key_facts[:8]
        ],
        "timeline": [
            {"at": entry.at.isoformat(), "what": entry.what}
            for entry in brief.timeline[:12]
        ],
        "stories": [
            {
                "headline": story.headline,
                "publishers": sorted(
                    {
                        member.candidate.publisher
                        for member in story.members
                        if member.candidate.publisher
                    }
                ),
                "first_seen": (
                    story.first_seen.isoformat() if story.first_seen else None
                ),
                "last_seen": story.last_seen.isoformat() if story.last_seen else None,
                "importance": story.importance.score,
                "facts": [fact.claim for fact in story.facts[:3]],
            }
            for story in brief.stories[:8]
        ],
        "thin_sourcing": brief.thin_sourcing,
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def build_chat_decision_messages(
    messages: list[ChatMessage],
    latest_brief: Brief | None,
    *,
    settings: Settings,
    now: datetime,
) -> list[dict[str, str]]:
    system = CHAT_SYSTEM.format(today=now.date().isoformat())
    if latest_brief is not None:
        system = (
            f"{system}\n\nLatest news_brief result already in the conversation:\n"
            f"{brief_context(latest_brief, settings.chat_context_chars)}"
        )
    return [
        {"role": "system", "content": system},
        *_chat_history(messages, settings.chat_history_messages),
    ]


def build_chat_answer_messages(
    messages: list[ChatMessage],
    brief: Brief,
    *,
    settings: Settings,
) -> list[dict[str, str]]:
    system = (
        f"{CHAT_ANSWER_SYSTEM}\n\nnews_brief result:\n"
        f"{brief_context(brief, settings.chat_context_chars)}"
    )
    return [
        {"role": "system", "content": system},
        *_chat_history(messages, settings.chat_history_messages),
    ]


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
