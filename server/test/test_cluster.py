from __future__ import annotations

from Core.cluster import cluster_candidates
from Core.models import Tier
from Core.registry import SourceRegistry
from Core.settings import Settings
from test.helpers import make_candidate


def test_creates_singleton_clusters(registry: SourceRegistry, settings: Settings) -> None:
    candidates = [
        make_candidate(title="Gold rises", url="https://www.reuters.com/a"),
        make_candidate(
            title="Gold falls",
            url="https://www.bbc.com/b",
            publisher="BBC News",
            tier=Tier.T2,
            family="bbc",
        ),
    ]
    clusters = cluster_candidates(candidates, registry=registry, settings=settings)
    assert [cluster.headline for cluster in clusters] == ["Gold rises", "Gold falls"]
    assert clusters[0].id != clusters[1].id
    assert clusters[0].id.startswith("c_")
    assert clusters[0].families == ["reuters"]
    assert clusters[1].families == ["bbc"]


def test_cluster_id_is_stable(registry: SourceRegistry, settings: Settings) -> None:
    candidate = make_candidate()
    first = cluster_candidates([candidate], registry=registry, settings=settings)[0]
    second = cluster_candidates([candidate], registry=registry, settings=settings)[0]
    assert first.id == second.id
