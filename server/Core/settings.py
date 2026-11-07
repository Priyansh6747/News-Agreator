from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEWS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["demo", "dev", "prod"] = "demo"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    enabled_backends: list[str] = Field(
        default_factory=lambda: ["google_news", "bing_news", "gdelt", "publisher_rss"]
    )

    candidate_target: int = 60
    candidate_cap: int = 80
    select_top: int = 20
    fetch_max_reps: int = 8

    fetch_concurrency: int = 4
    per_domain_concurrency: int = 1
    fetch_timeout_s: float = 12.0
    body_cap_mb: float = 5.0
    per_domain_min_spacing_s: float = 1.0
    query_cache_ttl_s: int = 300
    http_user_agent: str = "NewsAgreator/0.1"
    http_max_redirects: int = 3

    google_news_max_queries: int = 4
    google_news_item_cap: int = 60
    bing_news_max_queries: int = 2
    bing_news_item_cap: int = 20
    publisher_feed_item_cap: int = 20
    gdelt_max_records: int = 75
    gdelt_timeout_s: float = 20.0
    gdelt_cooldown_s: int = 900
    publisher_feed_stopwords: list[str] = Field(
        default_factory=lambda: [
            "the",
            "a",
            "an",
            "and",
            "or",
            "of",
            "in",
            "on",
            "for",
            "to",
            "with",
            "as",
            "at",
            "by",
            "from",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "this",
            "that",
            "these",
            "those",
            "latest",
            "news",
        ]
    )

    future_date_tolerance_h: int = 1
    default_freshness_hours: int = 96
    drop_undated: bool = True
    freshness_by_class: dict[str, int] = Field(
        default_factory=lambda: {
            "market": 24,
            "event": 48,
            "geopolitics": 72,
            "company": 168,
            "comparison": 336,
            "other": 96,
        }
    )

    query_phrasings: int = 3
    site_scoped_queries: int = 3

    cluster_cosine_threshold: float = 0.615
    cluster_inverted_index_cap: int = 250
    syndication_containment: float = 0.85
    min_corroborating_families: int = 2

    rank_weights: dict[str, float] = Field(
        default_factory=lambda: {"relevance": 0.45, "tier": 0.30, "recency": 0.25}
    )
    pre_rank_weights: dict[str, float] = Field(
        default_factory=lambda: {"relevance": 0.50, "tier": 0.30, "recency": 0.20}
    )
    min_candidate_relevance: float = 0.4
    type_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "report": 1.0,
            "opinion": 0.85,
            "press_release": 0.75,
            "aggregator": 0.5,
            "unknown": 0.9,
        }
    )
    tier_scores: dict[str, float] = Field(
        default_factory=lambda: {
            "T1": 1.0,
            "T2": 0.75,
            "T3": 0.5,
            "T4": 0.25,
            "unreviewed": 0.4,
        }
    )
    importance_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "severity": 0.55,
            "tier": 0.20,
            "corroboration": 0.15,
            "recency": 0.10,
        }
    )
    credibility_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "tier": 0.30,
            "risk": 0.50,
            "corroboration": 0.20,
        }
    )
    high_risk_threshold: float = 0.8
    high_risk_cap: float = 40.0

    pipeline_deadline_s: float = 90.0

    decision_engine: Literal["laya", "heuristic"] = "laya"
    laya_preload: bool = False
    laya_device: str | None = None
    laya_default_model: str = "english"
    laya_max_loaded: int = 2
    laya_batch_size: int = 32
    laya_assess_top: int = 20

    generator_base_url: str = "https://api.openai.com/v1"
    generator_api_key: str = ""
    generator_model: str = ""
    generator_timeout_s: float = 60.0
    generator_max_tokens: int = 1600


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
