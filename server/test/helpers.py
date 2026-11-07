from __future__ import annotations

from datetime import UTC, datetime, timedelta

from Core.models import Backend, Candidate, Tier
from Core.urls import domain_of

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def make_candidate(
    *,
    title: str = "Gold rises as dollar softens",
    url: str = "https://www.reuters.com/markets/commodities/gold-rises",
    publisher: str | None = "Reuters",
    backend: Backend = Backend.PUBLISHER_RSS,
    published_at: datetime | None = NOW - timedelta(hours=1),
    snippet: str | None = "Gold prices rose on Thursday.",
    tier: Tier = Tier.T2,
    family: str | None = "reuters",
) -> Candidate:
    return Candidate(
        title=title,
        url=url,
        publisher=publisher,
        domain=domain_of(url),
        snippet=snippet,
        published_at=published_at,
        backend=backend,
        tier=tier,
        family=family,
    )
