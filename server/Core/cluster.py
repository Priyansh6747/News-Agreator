from __future__ import annotations

import hashlib
import math
import re
from datetime import UTC, datetime
from itertools import pairwise

from Core.models import Article, Candidate, CredibilityScore, ImportanceScore, StoryCluster
from Core.registry import SourceRegistry
from Core.settings import Settings

TOKEN_RE = re.compile(r"[a-z0-9]+")
ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9&.-]*\b")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _story_title(candidate: Candidate) -> str:
    title = candidate.title.strip()
    if " - " not in title:
        return title
    head, _, tail = title.rpartition(" - ")
    suffix = tail.strip().lower()
    publisher = (candidate.publisher or "").strip().lower()
    if publisher and (suffix == publisher or suffix in publisher or publisher in suffix):
        return head.strip()
    return title


def _numbers(title: str) -> set[float]:
    values: set[float] = set()
    for match in NUMBER_RE.findall(title):
        try:
            values.add(float(match.replace(",", "")))
        except ValueError:
            continue
    return values


def _number_conflict(left: Candidate, right: Candidate) -> bool:
    left_numbers = _numbers(_story_title(left))
    right_numbers = _numbers(_story_title(right))
    if not left_numbers or not right_numbers:
        return False
    return not (left_numbers <= right_numbers or right_numbers <= left_numbers)


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _entities(text: str) -> set[str]:
    return {
        match.group(0).lower()
        for match in ENTITY_RE.finditer(text)
        if len(match.group(0)) > 1
    }


def _fnv1a(value: str) -> int:
    digest = 2166136261
    for byte in value.encode("utf-8"):
        digest ^= byte
        digest = (digest * 16777619) & 0xFFFFFFFF
    return digest


def _add_feature(vector: list[float], feature: str, weight: float) -> None:
    digest = _fnv1a(feature)
    index = digest % len(vector)
    sign = 1.0 if digest & 0x80000000 else -1.0
    vector[index] += sign * weight


def feature_vector(text: str, *, settings: Settings) -> list[float]:
    tokens = _tokens(text)
    vector = [0.0] * settings.cluster_dims
    if not tokens:
        return vector

    entities = _entities(text)
    numbers = {token for token in tokens if any(char.isdigit() for char in token)}

    for token in tokens:
        weight = settings.cluster_token_weight
        if token in entities:
            weight *= settings.cluster_entity_boost
        if token in numbers:
            weight *= settings.cluster_number_boost
        _add_feature(vector, f"t:{token}", weight)

    for left, right in pairwise(tokens):
        _add_feature(vector, f"b:{left}_{right}", settings.cluster_bigram_weight)

    for token in tokens:
        padded = f"#{token}#"
        for index in range(max(1, len(padded) - 3)):
            gram = padded[index : index + 4]
            if len(gram) == 4:
                _add_feature(vector, f"c:{gram}", settings.cluster_char_weight)

    return vector


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    if not norm_left or not norm_right:
        return 0.0
    return dot / (norm_left * norm_right)


def _trigrams(tokens: list[str]) -> set[tuple[str, str, str]]:
    return {tuple(tokens[index : index + 3]) for index in range(len(tokens) - 2)}


def _same_copy(left: Candidate, right: Candidate, settings: Settings) -> bool:
    if not left.snippet or not right.snippet:
        return False
    left_lead = _tokens(left.snippet)
    right_lead = _tokens(right.snippet)
    if min(len(left_lead), len(right_lead)) < settings.cluster_min_lead_words:
        return False
    left_grams = _trigrams(_tokens(_story_title(left)) + left_lead)
    right_grams = _trigrams(_tokens(_story_title(right)) + right_lead)
    if not left_grams or not right_grams:
        return False
    containment = len(left_grams & right_grams) / min(len(left_grams), len(right_grams))
    return containment >= settings.syndication_containment


class _UnionFind:
    def __init__(self, size: int):
        self._parent = list(range(size))
        self._rank = [0] * size

    def find(self, value: int) -> int:
        parent = self._parent
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        rank = self._rank
        if rank[root_left] < rank[root_right]:
            root_left, root_right = root_right, root_left
        self._parent[root_right] = root_left
        if rank[root_left] == rank[root_right]:
            rank[root_left] += 1


def _representative_key(candidate: Candidate, settings: Settings) -> tuple:
    tier = settings.tier_scores.get(candidate.tier.value, 0.4)
    published = candidate.published_at or datetime.min.replace(tzinfo=UTC)
    return (-tier, -published.timestamp(), candidate.url)


def _cluster_id(members: list[Candidate]) -> str:
    joined = "\n".join(sorted(member.url for member in members))
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]
    return f"c_{digest}"


def _build_cluster(
    members: list[Candidate],
    *,
    registry: SourceRegistry,
    settings: Settings,
) -> StoryCluster:
    ordered = sorted(members, key=lambda member: _representative_key(member, settings))
    representative = ordered[0]
    families = sorted(
        {
            family
            for family in (
                member.family
                or registry.family_for(domain=member.domain, publisher=member.publisher)
                for member in ordered
            )
            if family
        }
    )
    dates = [member.published_at for member in ordered if member.published_at is not None]
    articles = [
        Article(
            candidate=member,
            canonical_url=member.url,
            resolved_publisher=member.publisher,
        )
        for member in ordered
    ]
    return StoryCluster(
        id=_cluster_id(ordered),
        headline=_story_title(representative),
        members=articles,
        families=families,
        importance=ImportanceScore(score=0.0),
        credibility=CredibilityScore(score=0.0),
        first_seen=min(dates) if dates else None,
        last_seen=max(dates) if dates else None,
    )


def cluster_candidates(
    candidates: list[Candidate],
    *,
    registry: SourceRegistry,
    settings: Settings,
) -> list[StoryCluster]:
    if not candidates:
        return []

    vectors = [
        feature_vector(_story_title(candidate), settings=settings)
        for candidate in candidates
    ]
    token_sets = [
        set(_tokens(_story_title(candidate))) for candidate in candidates
    ]
    union_find = _UnionFind(len(candidates))

    for left_index in range(len(candidates)):
        for right_index in range(left_index + 1, len(candidates)):
            if union_find.find(left_index) == union_find.find(right_index):
                continue
            left = candidates[left_index]
            right = candidates[right_index]
            if _same_copy(left, right, settings):
                union_find.union(left_index, right_index)
                continue
            if _number_conflict(left, right):
                continue
            shared = len(token_sets[left_index] & token_sets[right_index])
            if (
                shared >= settings.cluster_min_shared_tokens
                and cosine(vectors[left_index], vectors[right_index])
                >= settings.cluster_cosine_threshold
            ):
                union_find.union(left_index, right_index)

    groups: dict[int, list[Candidate]] = {}
    for index, candidate in enumerate(candidates):
        groups.setdefault(union_find.find(index), []).append(candidate)

    clusters = [
        _build_cluster(members, registry=registry, settings=settings)
        for members in groups.values()
    ]
    clusters.sort(
        key=lambda cluster: (cluster.last_seen or datetime.min.replace(tzinfo=UTC), cluster.id),
        reverse=True,
    )
    return clusters
