from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from Core.models import Tier

DATA_DIR = Path(__file__).resolve().parent / "data"
UNKNOWN_RISK = 0.6


def _normalize_name(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())


class SourceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    publisher: str
    tier: Tier
    risk: float = Field(ge=0.0, le=1.0)
    notes: str | None = None


class FamilyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    domains: list[str] = Field(default_factory=list)


class Feed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publisher: str
    domain: str
    url: str
    section: str


class DenyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    mode: Literal["skip", "snippet_only"]
    reason: str
    evidence: str


class FetchPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["fetch", "snippet_only", "skip"] = "fetch"
    reason: str | None = None


class SourceRegistry:
    def __init__(
        self,
        sources: list[SourceEntry],
        families: list[FamilyEntry],
        feeds: list[Feed],
        denylist: list[DenyEntry],
    ):
        self._sources = {entry.domain: entry for entry in sources}
        self._by_publisher = {_normalize_name(entry.publisher): entry for entry in sources}
        self._families = families
        self._feeds = feeds
        self._denylist = {entry.domain: entry for entry in denylist}
        self._family_by_domain: dict[str, str] = {}
        self._family_by_name: dict[str, str] = {}
        for family in families:
            self._family_by_name[_normalize_name(family.name)] = family.id
            self._family_by_name[_normalize_name(family.id)] = family.id
            for domain in family.domains:
                self._family_by_domain[domain] = family.id

    @classmethod
    def load(cls, data_dir: Path | None = None) -> SourceRegistry:
        root = data_dir or DATA_DIR
        sources = json.loads((root / "source_tiers.json").read_text(encoding="utf-8"))
        families = json.loads((root / "publisher_families.json").read_text(encoding="utf-8"))
        feeds = json.loads((root / "publisher_feeds.json").read_text(encoding="utf-8"))
        denylist = json.loads((root / "fetch_denylist.json").read_text(encoding="utf-8"))
        return cls(
            sources=[SourceEntry.model_validate(entry) for entry in sources["sources"]],
            families=[FamilyEntry.model_validate(entry) for entry in families["families"]],
            feeds=[Feed.model_validate(entry) for entry in feeds["feeds"]],
            denylist=[DenyEntry.model_validate(entry) for entry in denylist["domains"]],
        )

    def source_for(self, domain: str | None = None, publisher: str | None = None) -> SourceEntry | None:
        if publisher:
            entry = self._by_publisher.get(_normalize_name(publisher))
            if entry is not None:
                return entry
        if domain and domain in self._sources:
            return self._sources[domain]
        return None

    def tier_for(self, domain: str | None = None, publisher: str | None = None) -> Tier:
        entry = self.source_for(domain=domain, publisher=publisher)
        return entry.tier if entry else Tier.UNREVIEWED

    def publisher_for(self, domain: str | None) -> str | None:
        entry = self._sources.get(domain or "")
        return entry.publisher if entry else None

    def family_for(self, domain: str | None = None, publisher: str | None = None) -> str | None:
        if publisher:
            family = self._family_by_name.get(_normalize_name(publisher))
            if family:
                return family
        if domain and domain in self._family_by_domain:
            return self._family_by_domain[domain]
        entry = self.source_for(domain=domain, publisher=publisher)
        if entry:
            return self._family_by_domain.get(entry.domain)
        return None

    def risk_for(self, domain: str | None = None, publisher: str | None = None) -> float:
        entry = self.source_for(domain=domain, publisher=publisher)
        return entry.risk if entry else UNKNOWN_RISK

    def fetch_policy(self, domain: str | None) -> FetchPolicy:
        entry = self._denylist.get(domain or "")
        if entry:
            return FetchPolicy(mode=entry.mode, reason=entry.reason)
        return FetchPolicy(mode="fetch")

    def feeds(self) -> list[Feed]:
        return list(self._feeds)

    def tier1_2_domains(self, limit: int = 3) -> list[str]:
        ranked = sorted(
            (entry for entry in self._sources.values() if entry.tier in {Tier.T1, Tier.T2}),
            key=lambda entry: (entry.tier, entry.domain),
        )
        seen: list[str] = []
        for entry in ranked:
            if entry.domain not in seen:
                seen.append(entry.domain)
            if len(seen) >= limit:
                break
        return seen
