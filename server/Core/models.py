from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryClass(StrEnum):
    MARKET = "market"
    GEOPOLITICS = "geopolitics"
    COMPANY = "company"
    EVENT = "event"
    COMPARISON = "comparison"
    OTHER = "other"


class QueryIntent(StrEnum):
    PRICE_CHECK = "price_check"
    EVENT_UPDATE = "event_update"
    EXPLAINER = "explainer"
    COMPARISON = "comparison"
    COMPANY_CHECK = "company_check"
    OTHER = "other"


class BriefSchema(StrEnum):
    PRICE_TABLE = "price_table"
    EVENT_TIMELINE = "event_timeline"
    CONFLICT_SUMMARY = "conflict_summary"
    COMPANY_SNAPSHOT = "company_snapshot"
    COMPARISON_TABLE = "comparison_table"
    GENERAL_BRIEF = "general_brief"


class QueryAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_class: QueryClass = QueryClass.OTHER
    time_sensitivity: int = Field(default=1, ge=0, le=3)
    intent: QueryIntent = QueryIntent.OTHER
    brief_schema: BriefSchema = BriefSchema.GENERAL_BRIEF


class Backend(StrEnum):
    GOOGLE_NEWS = "google_news"
    BING_NEWS = "bing_news"
    GDELT = "gdelt"
    PUBLISHER_RSS = "publisher_rss"


class Tier(StrEnum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    UNREVIEWED = "unreviewed"


class ArticleType(StrEnum):
    REPORT = "report"
    OPINION = "opinion"
    PRESS_RELEASE = "press_release"
    AGGREGATOR = "aggregator"
    UNKNOWN = "unknown"


class TextStatus(StrEnum):
    OK = "ok"
    THIN = "thin"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    SKIPPED_POLICY = "skipped-policy"
    NOT_FETCHED = "not-fetched"


class CoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class Attempt(StrEnum):
    COMPLETED = "completed"
    EMPTY = "empty"
    ALL_UNDATED = "all-undated"
    PARTIAL_UNDATED = "partial-undated"
    DIRECT_TIMEOUT = "direct-timeout"
    RELAY_FAILURE = "relay-failure"
    ABORTED_BY_DEADLINE = "aborted-by-deadline"
    OTHER_FETCH_FAILURE = "other-fetch-failure"
    NEGATIVE_CACHE = "negative-cache"
    NOT_STARTED = "not-started"


class Stage(StrEnum):
    PLAN = "plan"
    RETRIEVE = "retrieve"
    RANK = "rank"
    CLUSTER = "cluster"
    SCORE = "score"
    ENRICH = "enrich"
    BRIEF = "brief"
    PRESENT = "present"


class EventState(StrEnum):
    STARTED = "started"
    PROGRESS = "progress"
    FINISHED = "finished"
    FAILED = "failed"


def validate_http_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("must be an absolute http(s) URL")
    return value


def ensure_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    normalized: str
    query_class: QueryClass = QueryClass.OTHER
    time_sensitivity: int = 1
    intent: QueryIntent = QueryIntent.OTHER
    brief_schema: BriefSchema = BriefSchema.GENERAL_BRIEF
    freshness_hours: int = 96
    lookback_hours: int | None = None
    phrasings: list[str] = Field(default_factory=list)
    site_scoped: list[str] = Field(default_factory=list)
    language: str = "en"
    region: str = "US"

    @property
    def lookback(self) -> int:
        return self.lookback_hours or self.freshness_hours

    @property
    def all_queries(self) -> list[str]:
        seen: list[str] = []
        for query in [self.normalized, *self.phrasings, *self.site_scoped]:
            if query and query not in seen:
                seen.append(query)
        return seen


class RawItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    url: str
    publisher: str | None = None
    snippet: str | None = None
    published_at: datetime | None = None
    backend: Backend
    needs_resolution: bool = False

    @field_validator("published_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        return ensure_aware(value)


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RawItem] = Field(default_factory=list)
    raw_count: int = 0
    drops: dict[str, int] = Field(default_factory=dict)
    detail: str | None = None


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    url: str
    publisher: str | None = None
    domain: str | None = None
    snippet: str | None = None
    published_at: datetime | None = None
    backend: Backend
    tier: Tier = Tier.UNREVIEWED
    family: str | None = None
    article_type: ArticleType | None = None
    relevance: float | None = Field(default=None, ge=0.0, le=1.0)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    needs_resolution: bool = False

    @field_validator("published_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        return ensure_aware(value)


class CandidateAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance: float = Field(ge=0.0, le=1.0)
    article_type: ArticleType = ArticleType.UNKNOWN
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class Article(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: Candidate
    canonical_url: str
    resolved_publisher: str | None = None
    word_count: int | None = None
    text_status: TextStatus = TextStatus.NOT_FETCHED
    fetched_at: datetime | None = None


class ImportanceScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=100.0)
    severity: float = 0.0
    tier: float = 0.0
    corroboration: float = 0.0
    recency: float = 0.0


class CredibilityScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=100.0)
    tier: float = 0.0
    propaganda_risk: float = 0.0
    corroboration: float = 0.0
    capped: bool = False


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    value: str | None = None
    source_url: str
    published_at: datetime
    quote: str | None = None
    cluster_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("source_url")
    @classmethod
    def _url(cls, value: str) -> str:
        return validate_http_url(value)

    @field_validator("quote")
    @classmethod
    def _quote(cls, value: str | None) -> str | None:
        if value is not None and len(value.split()) > 25:
            raise ValueError("quote must be at most 25 words")
        return value


class StoryCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    headline: str
    members: list[Article] = Field(min_length=1)
    families: list[str] = Field(default_factory=list)
    importance: ImportanceScore
    credibility: CredibilityScore
    facts: list[Fact] = Field(default_factory=list)
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class FactRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    meaning: str
    source_url: str
    published_at: datetime

    @field_validator("source_url")
    @classmethod
    def _url(cls, value: str) -> str:
        return validate_http_url(value)


class TimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: datetime
    what: str
    source_url: str

    @field_validator("source_url")
    @classmethod
    def _url(cls, value: str) -> str:
        return validate_http_url(value)


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    source_url: str
    published_at: datetime

    @field_validator("source_url")
    @classmethod
    def _url(cls, value: str) -> str:
        return validate_http_url(value)


class Disagreement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    positions: list[Position] = Field(min_length=2)


class BackendCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Backend
    attempted: int = 0
    returned: int = 0
    kept: int = 0
    drops: dict[str, int] = Field(default_factory=dict)


class BackendAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Backend
    attempt: Attempt
    returned: int = 0
    elapsed_ms: int = 0
    detail: str | None = None


class Coverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CoverageStatus
    backends: list[BackendCoverage] = Field(default_factory=list)
    attempts: list[BackendAttempt] = Field(default_factory=list)
    drops: dict[str, int] = Field(default_factory=dict)
    text_status: dict[TextStatus, int] = Field(default_factory=dict)
    timings_ms: dict[Stage, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


ChartKind = Literal["bar", "line", "pie"]
ChartValueFormat = Literal["number", "duration", "percent"]


class ChartPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: float
    at: str | None = None


class ChartSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    points: list[ChartPoint] = Field(default_factory=list)


class ChartSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ChartKind
    title: str
    subtitle: str | None = None
    takeaway: str | None = None
    value_format: ChartValueFormat = "number"
    value_suffix: str | None = None
    series: list[ChartSeries] = Field(default_factory=list)


class MapPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country_code: str
    country: str
    label: str
    lat: float
    lon: float
    story_ids: list[str] = Field(default_factory=list)
    summary: str | None = None


class MapData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    points: list[MapPoint] = Field(default_factory=list)


class Brief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    query_class: QueryClass
    answer: str
    key_facts: list[FactRow] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    disagreements: list[Disagreement] = Field(default_factory=list)
    thin_sourcing: list[str] = Field(default_factory=list)
    stories: list[StoryCluster] = Field(default_factory=list)
    coverage: Coverage
    generated_at: datetime
    charts: list[ChartSpec] = Field(default_factory=list)
    map: MapData | None = None


class StageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Stage
    state: EventState
    counts: dict[str, int] = Field(default_factory=dict)
    message: str | None = None
    elapsed_ms: int | None = None
    at: datetime


class BriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=300)

    @field_validator("query")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("query must contain at least two characters")
        return cleaned


class FetchedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    final_url: str
    status: int
    content_type: str | None = None
    html: str
    elapsed_ms: int = 0


class ExtractedText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    title: str | None = None
    published_at: datetime | None = None
    word_count: int
    quality: float = Field(ge=0.0, le=1.0)


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    status: Literal["completed", "failed"]
    elapsed_ms: int
    stages: list[StageEvent] = Field(default_factory=list)
    coverage_status: str | None = None
    story_count: int | None = None


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: ChatRole
    content: str
    created_at: datetime
    brief: Brief | None = None
    run: ChatRun | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("message must not be empty")
        return cleaned


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    user: ChatMessage
    assistant: ChatMessage


class ChatConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
