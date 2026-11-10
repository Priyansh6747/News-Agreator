from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from math import isfinite

from countryinfo import CountryInfo
from pydantic import BaseModel, ConfigDict, Field

from Core.models import Brief, ChartPoint, ChartSeries, ChartSpec, MapData, MapPoint
from Core.ports import DecisionEngine, Generator
from Core.settings import Settings

PRESENTER_SYSTEM = (
    "You plan the charts for a news brief. Choose 2-5 charts. For each chart return only a kind "
    "(bar, line or pie) and a question. A local classifier named Laya answers the question; the "
    "server builds the chart from its answers, so never return values, categories or sources. "
    "Pie and bar questions are answered over the key facts; line questions are answered over the "
    "timeline. Extract approximate countries explicitly named in the supplied coverage, using "
    "ISO codes and story IDs; omit ambiguous places and organization hubs. Return only JSON "
    "matching the schema."
)

KIND_TITLES = {
    "pie": "Fact direction",
    "bar": "Fact impact",
    "line": "Timeline assessment",
}

ALLOWED_STANCES = {"up", "down", "flat"}
MAX_FACTS = 8
MAX_TIMELINE = 12
MAX_STORIES = 8


class ChartChoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str = "bar"
    question: str = ""


class PresenterLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    country: str = ""
    story_ids: list[str] = Field(default_factory=list)
    label: str | None = None
    summary: str | None = None


class PresenterOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    charts: list[ChartChoice] = Field(default_factory=list)
    locations: list[PresenterLocation] = Field(default_factory=list)


@dataclass
class Presentation:
    charts: list[ChartSpec]
    map: MapData | None = None
    fallback: bool = False
    message: str | None = None


def _clean(value: str | None, limit: int) -> str:
    if not value:
        return ""
    return " ".join(value.split())[:limit].strip()


def _clip(value: str, limit: int) -> str:
    return value[:limit].rstrip()


def _normalize_kind(value: str) -> str | None:
    key = value.strip().lower()
    return key if key in KIND_TITLES else None


def _timeline_days(brief: Brief) -> set[str]:
    return {entry.at.date().isoformat() for entry in brief.timeline}


def _fact_text(fact) -> str:
    return _clean(f"{fact.value or ''} {fact.meaning}", 260)


def _fact_label(fact) -> str:
    return _clean(f"{fact.value or ''} {fact.meaning}".strip(), 32)


def _default_choices(brief: Brief) -> list[ChartChoice]:
    topic = brief.query or "the topic"
    choices: list[ChartChoice] = []
    if len(brief.key_facts) >= 2:
        choices.append(
            ChartChoice(
                kind="pie",
                question=f"Did each key fact move {topic} up, down, or leave it flat?",
            )
        )
        choices.append(
            ChartChoice(
                kind="bar",
                question=f"How positive is each key fact for {topic}?",
            )
        )
    if len(_timeline_days(brief)) >= 2:
        choices.append(
            ChartChoice(
                kind="line",
                question=f"How positive was each update for {topic} over time?",
            )
        )
    if len(choices) < 2 and len(brief.key_facts) >= 2:
        choices.append(
            ChartChoice(
                kind="bar",
                question=f"How important is each key fact for {topic}?",
            )
        )
    if len(choices) < 2 and len(_timeline_days(brief)) >= 2:
        choices.append(
            ChartChoice(
                kind="line",
                question=f"How important was each update for {topic} over time?",
            )
        )
    return choices


def _valid_choices(
    raw_choices: list[ChartChoice],
    brief: Brief,
    settings: Settings,
) -> tuple[list[ChartChoice], bool]:
    facts_ok = len(brief.key_facts) >= 2
    timeline_ok = len(_timeline_days(brief)) >= 2
    choices: list[ChartChoice] = []
    seen: set[tuple[str, str]] = set()
    per_kind: Counter[str] = Counter()

    for raw in raw_choices:
        kind = _normalize_kind(raw.kind)
        question = _clean(raw.question, 160)
        if kind is None or not question:
            continue
        if kind == "line" and not timeline_ok:
            continue
        if kind in {"pie", "bar"} and not facts_ok:
            continue
        key = (kind, question.lower())
        if key in seen or per_kind[kind] >= 2:
            continue
        choices.append(ChartChoice(kind=kind, question=question))
        seen.add(key)
        per_kind[kind] += 1
        if len(choices) >= settings.presenter_max_charts:
            break

    fallback_added = False
    if len(choices) < 2:
        for default in _default_choices(brief):
            key = (default.kind, default.question.lower())
            if key in seen or per_kind[default.kind] >= 2:
                continue
            choices.append(default)
            seen.add(key)
            per_kind[default.kind] += 1
            fallback_added = True
            if len(choices) >= 2:
                break

    return choices[: settings.presenter_max_charts], fallback_added


def _build_prompt(brief: Brief, settings: Settings) -> str:
    kinds: list[str] = []
    if len(brief.key_facts) >= 2:
        kinds.extend(["pie", "bar"])
    if len(_timeline_days(brief)) >= 2:
        kinds.append("line")

    rules = (
        f"Choose between 2 and {settings.presenter_max_charts} charts. Return only a kind and "
        "one question per chart; do not return values, categories or sources.\n"
        "Laya answers the question and the server builds the chart from its answers.\n"
        "- pie: Laya classifies each key fact as up, down, flat or unrelated. Ask a direction "
        "question about the topic.\n"
        "- bar: Laya scores each key fact from 0 to 1. Ask a positivity, impact or importance "
        "question about the topic.\n"
        "- line: Laya scores each timeline entry from 0 to 1 and the server averages by day. Ask "
        "a question about change over time. Only use line when the timeline spans two or more "
        "days.\n"
        "Use at most two charts of each kind; every question must be distinct, short and "
        "answerable from the provided data. Prefer a mix of kinds.\n"
        f"For locations, return at most {settings.presenter_max_locations} countries explicitly "
        "named in the supplied stories. Use ISO 3166-1 alpha-2 codes when possible and include "
        "only story IDs from the list. Omit ambiguous places and organization mentions that are "
        "only headquarters. Markers are approximate country centers.\n\n"
    )

    facts = "\n".join(
        f"{fact.value or '-'} | {fact.meaning} | {fact.published_at.date().isoformat()}"
        for fact in brief.key_facts[:12]
    )
    timeline = "\n".join(
        f"{entry.at.isoformat()} | {entry.what}" for entry in brief.timeline[:14]
    )
    stories = "\n".join(
        f"[{story.id}] {story.headline} | "
        f"{story.members[0].candidate.publisher or 'unknown'} | "
        f"{_clip(story.members[0].candidate.snippet or '', 220)}"
        for story in brief.stories[:MAX_STORIES]
    )

    data = (
        f"Topic: {brief.query}\n"
        f"Answer:\n{_clip(brief.answer, 1400)}\n\n"
        f"Allowed chart kinds: {', '.join(kinds) or 'none'}\n\n"
        f"Key facts (value | meaning | published):\n{facts or '-'}\n\n"
        f"Timeline (at | what):\n{timeline or '-'}\n\n"
        f"Stories (id | headline | publisher | snippet):\n{stories or '-'}"
    )
    budget = max(1200, settings.presenter_text_chars - len(rules) - 200)
    return rules + _clip(data, budget)


async def _resolve_choice(
    choice: ChartChoice,
    brief: Brief,
    decisions: DecisionEngine,
) -> ChartSpec | None:
    question = _clean(choice.question, 160)
    subtitle = f"Laya · {question}"

    if choice.kind == "pie":
        facts = brief.key_facts[:MAX_FACTS]
        if len(facts) < 2:
            return None
        stances = await decisions.stance(
            question,
            [_fact_text(fact) for fact in facts],
            topic=brief.query,
        )
        counts: Counter[str] = Counter(
            stance for stance in stances if stance in ALLOWED_STANCES
        )
        if sum(counts.values()) < 2:
            return None
        labels = {"up": "Up", "down": "Down", "flat": "Flat"}
        points = [
            ChartPoint(label=labels[key], value=float(counts[key]))
            for key in ("up", "down", "flat")
            if counts[key]
        ]
        takeaway = " · ".join(
            f"{counts[key]} {labels[key].lower()}"
            for key in ("up", "down", "flat")
            if counts[key]
        )
        return ChartSpec(
            kind="pie",
            title=KIND_TITLES["pie"],
            subtitle=subtitle,
            takeaway=takeaway or None,
            value_format="number",
            value_suffix="facts",
            series=[ChartSeries(label="Facts", points=points)],
        )

    if choice.kind == "bar":
        facts = brief.key_facts[:MAX_FACTS]
        if len(facts) < 2:
            return None
        scores = await decisions.score(
            question,
            [_fact_text(fact) for fact in facts],
            topic=brief.query,
        )
        if len(scores) != len(facts):
            return None
        points = [
            ChartPoint(label=_fact_label(fact), value=float(score))
            for fact, score in zip(facts, scores)
        ]
        return ChartSpec(
            kind="bar",
            title=KIND_TITLES["bar"],
            subtitle=subtitle,
            value_format="percent",
            series=[ChartSeries(label="Laya score", points=points)],
        )

    if choice.kind == "line":
        entries = brief.timeline[:MAX_TIMELINE]
        if len(entries) < 2 or len(_timeline_days(brief)) < 2:
            return None
        scores = await decisions.score(
            question,
            [entry.what for entry in entries],
            topic=brief.query,
        )
        if len(scores) != len(entries):
            return None
        by_day: dict[str, list[float]] = defaultdict(list)
        for entry, score in zip(entries, scores):
            by_day[entry.at.date().isoformat()].append(float(score))
        if len(by_day) < 2:
            return None
        points = [
            ChartPoint(
                label=date.fromisoformat(day).strftime("%b %d"),
                value=sum(values) / len(values),
                at=f"{day}T00:00:00+00:00",
            )
            for day, values in sorted(by_day.items())
        ]
        return ChartSpec(
            kind="line",
            title=KIND_TITLES["line"],
            subtitle=subtitle,
            value_format="percent",
            series=[ChartSeries(label="Laya score", points=points)],
        )

    return None


@lru_cache(maxsize=256)
def _country_info(identifier: str) -> tuple[str, str, float, float] | None:
    key = identifier.strip()
    if not key:
        return None
    try:
        info = CountryInfo(key)
        lat, lon = info.latlng()
        code = info.iso(2)
        name = info.name()
    except Exception:  # noqa: BLE001
        return None
    if code is None or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    if not isfinite(float(lat)) or not isfinite(float(lon)):
        return None
    if not -90 <= float(lat) <= 90 or not -180 <= float(lon) <= 180:
        return None
    return str(code).upper(), str(name), float(lat), float(lon)


def _resolve_map(
    brief: Brief,
    locations: list[PresenterLocation],
    settings: Settings,
) -> MapData | None:
    story_ids = {story.id for story in brief.stories}
    grouped: dict[str, dict[str, object]] = {}
    for location in locations:
        info = _country_info(location.country)
        if info is None:
            continue
        code, country, lat, lon = info
        valid_ids = [story_id for story_id in location.story_ids if story_id in story_ids]
        if not valid_ids:
            continue
        entry = grouped.get(code)
        if entry is None:
            if len(grouped) >= settings.presenter_max_locations:
                continue
            entry = {
                "country": country,
                "lat": lat,
                "lon": lon,
                "label": _clean(location.label, 80) or country,
                "summary": _clean(location.summary, 200) or None,
                "story_ids": set(),
            }
            grouped[code] = entry
        ids = entry["story_ids"]
        assert isinstance(ids, set)
        ids.update(valid_ids)

    points = [
        MapPoint(
            country_code=code,
            country=str(entry["country"]),
            label=str(entry["label"]),
            lat=float(entry["lat"]),
            lon=float(entry["lon"]),
            story_ids=sorted(entry["story_ids"]),
            summary=entry["summary"] if isinstance(entry["summary"], str) else None,
        )
        for code, entry in grouped.items()
    ]
    return MapData(points=points) if points else None


async def fallback_presentation(
    brief: Brief,
    *,
    decisions: DecisionEngine,
    settings: Settings,
) -> Presentation:
    charts: list[ChartSpec] = []
    limit = max(1, min(3, settings.presenter_max_charts))
    for choice in _default_choices(brief):
        if len(charts) >= limit:
            break
        try:
            spec = await _resolve_choice(choice, brief, decisions)
        except Exception:  # noqa: BLE001
            spec = None
        if spec is not None:
            charts.append(spec)
    return Presentation(
        charts=charts,
        map=None,
        fallback=True,
        message="fallback charts" if charts else "chart data unavailable",
    )


async def build_presentation(
    brief: Brief,
    *,
    generator: Generator | None,
    decisions: DecisionEngine,
    settings: Settings,
) -> Presentation:
    if not settings.presenter_enabled:
        return Presentation(
            charts=[],
            map=None,
            fallback=True,
            message="presenter disabled",
        )
    if generator is None:
        return await fallback_presentation(
            brief, decisions=decisions, settings=settings
        )

    result = await generator.complete_json(
        schema=PresenterOutput,
        system=PRESENTER_SYSTEM,
        user=_build_prompt(brief, settings),
        max_tokens=settings.presenter_max_tokens,
    )
    map_data = _resolve_map(brief, result.locations, settings)
    choices, fallback_added = _valid_choices(result.charts, brief, settings)

    charts: list[ChartSpec] = []
    attempted: set[tuple[str, str]] = set()
    for choice in choices:
        attempted.add((choice.kind, choice.question.lower()))
        try:
            spec = await _resolve_choice(choice, brief, decisions)
        except Exception:  # noqa: BLE001
            spec = None
        if spec is not None:
            charts.append(spec)

    if len(charts) < 2:
        for default in _default_choices(brief):
            if len(charts) >= 2:
                break
            key = (default.kind, default.question.lower())
            if key in attempted:
                continue
            attempted.add(key)
            try:
                spec = await _resolve_choice(default, brief, decisions)
            except Exception:  # noqa: BLE001
                spec = None
            if spec is not None:
                charts.append(spec)
                fallback_added = True

    message: str | None = None
    if not charts:
        message = "chart data unavailable"
    elif fallback_added:
        message = "fallback charts"

    return Presentation(
        charts=charts[: settings.presenter_max_charts],
        map=map_data,
        fallback=fallback_added,
        message=message,
    )
