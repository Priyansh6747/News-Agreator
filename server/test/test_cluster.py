from __future__ import annotations

from datetime import timedelta

import pytest

from Core.cluster import cluster_candidates, cosine, feature_vector
from Core.models import Tier
from Core.registry import SourceRegistry
from Core.settings import Settings
from test.helpers import NOW, make_candidate


def test_keeps_topic_only_overlap_apart(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    # Only the topic token "gold" is shared; one shared token is not enough.
    candidates = [
        make_candidate(title="Gold rises", url="https://www.reuters.com/a", snippet=None),
        make_candidate(
            title="Gold falls",
            url="https://www.bbc.com/b",
            publisher="BBC News",
            snippet=None,
            tier=Tier.T2,
            family="bbc",
        ),
    ]
    clusters = cluster_candidates(candidates, registry=registry, settings=settings)
    assert {cluster.headline for cluster in clusters} == {"Gold rises", "Gold falls"}
    assert len({cluster.id for cluster in clusters}) == 2
    assert {tuple(cluster.families) for cluster in clusters} == {("reuters",), ("bbc",)}


def test_number_conflict_blocks_template_merges(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    left = make_candidate(
        title="Gold Price Today: Gold Rises 4.31% on November 05, 2026 - USA Today",
        url="https://www.usatoday.com/gold-05",
        publisher="USA Today",
        snippet=None,
    )
    right = make_candidate(
        title="Gold Price Today: Gold Rises 2.83% on November 04, 2026 - USA Today",
        url="https://www.usatoday.com/gold-04",
        publisher="USA Today",
        snippet=None,
    )
    clusters = cluster_candidates([left, right], registry=registry, settings=settings)
    assert len(clusters) == 2


def test_number_subset_allows_same_story_merge(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    left = make_candidate(
        title="China extends gold buying streak to 24 months amid price slump - Chosunbiz",
        url="https://www.chosun.com/gold",
        publisher="Chosunbiz",
        snippet=None,
    )
    right = make_candidate(
        title=(
            "China extends gold buying streak to 24 months as prices slump below "
            "$4,000 - Investing.com"
        ),
        url="https://www.investing.com/gold",
        publisher="Investing.com",
        snippet=None,
    )
    clusters = cluster_candidates([left, right], registry=registry, settings=settings)
    assert len(clusters) == 1


def test_strips_publisher_suffix_before_matching(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    left = make_candidate(
        title="Gold drops as strong US payrolls boost dollar, yields - Reuters",
        url="https://www.reuters.com/payrolls",
        publisher="Reuters",
        snippet=None,
        tier=Tier.T1,
        family="reuters",
    )
    right = make_candidate(
        title="Gold drops 1% as strong U.S. payrolls boost dollar, yields - CNBC",
        url="https://www.cnbc.com/payrolls",
        publisher="CNBC",
        snippet=None,
        tier=Tier.T2,
        family="cnbc",
    )
    clusters = cluster_candidates([left, right], registry=registry, settings=settings)
    assert len(clusters) == 1
    assert clusters[0].headline == "Gold drops as strong US payrolls boost dollar, yields"


def test_merges_near_duplicate_titles(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    left = make_candidate(
        title="Gold prices climb as dollar softens",
        url="https://www.reuters.com/gold-softens",
        publisher="Reuters",
        snippet=None,
        tier=Tier.T1,
        family="reuters",
    )
    right = make_candidate(
        title="Gold prices climb as dollar weakens",
        url="https://www.bbc.com/news/gold-weakens",
        publisher="BBC News",
        snippet=None,
        tier=Tier.T2,
        family="bbc",
    )
    clusters = cluster_candidates([left, right], registry=registry, settings=settings)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert len(cluster.members) == 2
    assert cluster.members[0].candidate.url == left.url
    assert cluster.headline == left.title
    assert cluster.families == ["bbc", "reuters"]


def test_keeps_unrelated_titles_apart(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    gold = make_candidate(
        title="Gold prices climb as dollar softens",
        url="https://www.reuters.com/gold",
        snippet=None,
    )
    bitcoin = make_candidate(
        title="Bitcoin drops as ETF outflows accelerate",
        url="https://www.cnbc.com/bitcoin",
        publisher="CNBC",
        snippet=None,
        family="cnbc",
    )
    clusters = cluster_candidates([gold, bitcoin], registry=registry, settings=settings)
    assert len(clusters) == 2


def test_syndicated_copies_merge_with_different_headlines(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    snippet = (
        "Gold prices rose for a third straight session as the dollar weakened and "
        "investors sought safer assets amid geopolitical tensions."
    )
    left = make_candidate(
        title="Gold rally continues",
        url="https://www.reuters.com/rally",
        snippet=snippet,
        family="reuters",
    )
    right = make_candidate(
        title="Bullion extends gains",
        url="https://www.bbc.com/bullion",
        publisher="BBC News",
        snippet=snippet,
        family="bbc",
    )
    clusters = cluster_candidates([left, right], registry=registry, settings=settings)
    assert len(clusters) == 1
    assert len(clusters[0].members) == 2


def test_short_snippets_do_not_trigger_syndication(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    left = make_candidate(
        title="Gold rally continues",
        url="https://www.reuters.com/rally",
        snippet="Gold prices rose on Thursday.",
    )
    right = make_candidate(
        title="Bullion extends gains",
        url="https://www.bbc.com/bullion",
        publisher="BBC News",
        snippet="Gold prices rose on Thursday.",
    )
    clusters = cluster_candidates([left, right], registry=registry, settings=settings)
    assert len(clusters) == 2


def test_cluster_id_is_stable_and_input_order_independent(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    left = make_candidate(
        title="Gold prices climb as dollar softens",
        url="https://www.reuters.com/a",
        snippet=None,
    )
    right = make_candidate(
        title="Gold prices climb as dollar weakens",
        url="https://www.bbc.com/b",
        snippet=None,
    )
    forward = cluster_candidates([left, right], registry=registry, settings=settings)
    reverse = cluster_candidates([right, left], registry=registry, settings=settings)
    assert len(forward) == len(reverse) == 1
    assert forward[0].id == reverse[0].id


def test_representative_prefers_higher_tier(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    recent_low = make_candidate(
        title="Gold prices climb as dollar softens",
        url="https://www.example.com/recent",
        publisher="Example",
        snippet=None,
        tier=Tier.T4,
        family="example",
        published_at=NOW - timedelta(hours=1),
    )
    older_high = make_candidate(
        title="Gold prices climb as dollar weakens",
        url="https://www.reuters.com/older",
        publisher="Reuters",
        snippet=None,
        tier=Tier.T1,
        family="reuters",
        published_at=NOW - timedelta(hours=10),
    )
    cluster = cluster_candidates(
        [recent_low, older_high], registry=registry, settings=settings
    )[0]
    assert cluster.headline == older_high.title
    assert cluster.members[0].candidate.url == older_high.url
    assert cluster.first_seen == NOW - timedelta(hours=10)
    assert cluster.last_seen == NOW - timedelta(hours=1)


def test_single_candidate_stays_singleton(
    registry: SourceRegistry,
    settings: Settings,
) -> None:
    candidate = make_candidate(snippet=None)
    clusters = cluster_candidates([candidate], registry=registry, settings=settings)
    assert len(clusters) == 1
    assert clusters[0].id.startswith("c_")
    assert len(clusters[0].members) == 1


def test_feature_vector_is_deterministic_and_self_similar(
    settings: Settings,
) -> None:
    first = feature_vector("Gold prices climb as dollar softens", settings=settings)
    second = feature_vector("Gold prices climb as dollar softens", settings=settings)
    assert first == second
    assert cosine(first, second) == pytest.approx(1.0)
