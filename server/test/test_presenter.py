from __future__ import annotations

from datetime import timedelta

from Core.models import (
    Article,
    Backend,
    BackendCoverage,
    Brief,
    Coverage,
    CoverageStatus,
    CredibilityScore,
    FactRow,
    ImportanceScore,
    QueryClass,
    Stage,
    StoryCluster,
    TextStatus,
    TimelineEntry,
)
from Core.presenter import (
    ChartChoice,
    PresenterLocation,
    PresenterOutput,
    build_presentation,
    fallback_presentation,
)
from Core.settings import Settings
from test.helpers import NOW, make_candidate


def make_article(publisher: str, url: str) -> Article:
    candidate = make_candidate(publisher=publisher, url=url)
    return Article(candidate=candidate, canonical_url=url)


def make_brief() -> Brief:
    stories = [
        StoryCluster(
            id="s1",
            headline="Iran strikes reported near border",
            members=[make_article("Reuters", "https://www.reuters.com/world/iran-strikes")],
            importance=ImportanceScore(score=82.0),
            credibility=CredibilityScore(score=74.0),
        ),
        StoryCluster(
            id="s2",
            headline="US urges restraint as talks stall",
            members=[make_article("BBC", "https://www.bbc.com/news/us-talks")],
            importance=ImportanceScore(score=65.0),
            credibility=CredibilityScore(score=86.0),
        ),
    ]
    facts = [
        FactRow(
            value="4.5%",
            meaning="Gold rose 4.5% this week",
            source_url="https://www.reuters.com/markets/gold",
            published_at=NOW,
        ),
        FactRow(
            value="$4,046",
            meaning="Spot gold traded at $4,046",
            source_url="https://www.kitco.com/gold",
            published_at=NOW,
        ),
        FactRow(
            value="830,000",
            meaning="Central banks bought 830,000 troy ounces",
            source_url="https://www.investing.com/gold",
            published_at=NOW,
        ),
    ]
    timeline = [
        TimelineEntry(
            at=NOW - timedelta(days=2),
            what="Prices started climbing",
            source_url="https://www.reuters.com/markets/gold",
        ),
        TimelineEntry(
            at=NOW - timedelta(days=1),
            what="Central bank buying reported",
            source_url="https://www.kitco.com/gold",
        ),
        TimelineEntry(
            at=NOW,
            what="Spot price held above $4,000",
            source_url="https://www.investing.com/gold",
        ),
    ]
    coverage = Coverage(
        status=CoverageStatus.PARTIAL,
        backends=[
            BackendCoverage(
                backend=Backend.GOOGLE_NEWS,
                attempted=1,
                returned=12,
                kept=8,
            ),
            BackendCoverage(
                backend=Backend.BING_NEWS,
                attempted=1,
                returned=5,
                kept=3,
            ),
        ],
        text_status={TextStatus.OK: 3, TextStatus.BLOCKED: 1},
        timings_ms={
            Stage.PLAN: 1200,
            Stage.RETRIEVE: 4000,
            Stage.RANK: 7000,
            Stage.CLUSTER: 3,
            Stage.SCORE: 0,
            Stage.ENRICH: 30000,
            Stage.BRIEF: 6000,
        },
    )
    return Brief(
        query="gold prices",
        query_class=QueryClass.MARKET,
        answer="Gold rose this week as central-bank buying continued.",
        key_facts=facts,
        timeline=timeline,
        stories=stories,
        coverage=coverage,
        generated_at=NOW,
    )


class FakeGenerator:
    def __init__(self, output: PresenterOutput) -> None:
        self.output = output
        self.user = ""
        self.calls = 0

    async def complete_json(self, *, schema, system, user, max_tokens):
        self.calls += 1
        self.user = user
        return self.output


class FakeDecisions:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, list[str]]] = []

    async def stance(self, question, items, *, topic=""):
        self.calls.append(("stance", question, topic, list(items)))
        return ["up", "up", "flat"][: len(items)]

    async def score(self, question, items, *, topic=""):
        self.calls.append(("score", question, topic, list(items)))
        if "over time" in question.lower():
            return [0.2, 0.6, 0.9][: len(items)]
        return [0.8, 0.6, 0.4][: len(items)]


def make_output() -> PresenterOutput:
    return PresenterOutput(
        charts=[
            ChartChoice(
                kind="pie",
                question="Did each key fact move gold prices up or down?",
            ),
            ChartChoice(
                kind="bar",
                question="How positive is each key fact for gold prices?",
            ),
            ChartChoice(
                kind="line",
                question="How positive was each update for gold prices over time?",
            ),
        ],
        locations=[
            PresenterLocation(
                country="IR",
                story_ids=["s1"],
                label="Iran",
                summary="Strikes near the border",
            ),
            PresenterLocation(
                country="United States",
                story_ids=["s2"],
                label="United States",
                summary="Diplomatic talks",
            ),
        ],
    )


async def test_presenter_uses_laya_for_chart_data(settings: Settings) -> None:
    generator = FakeGenerator(make_output())
    decisions = FakeDecisions()
    presentation = await build_presentation(
        make_brief(),
        generator=generator,
        decisions=decisions,
        settings=settings,
    )

    assert generator.calls == 1
    assert "Laya" in generator.user
    assert "fact_stances" not in generator.user
    assert [chart.kind for chart in presentation.charts] == ["pie", "bar", "line"]

    pie = presentation.charts[0]
    assert pie.value_format == "number"
    assert {(p.label, p.value) for p in pie.series[0].points} == {
        ("Up", 2.0),
        ("Flat", 1.0),
    }
    assert "2 up" in (pie.takeaway or "")

    bar = presentation.charts[1]
    assert bar.value_format == "percent"
    assert [p.value for p in bar.series[0].points] == [0.8, 0.6, 0.4]

    line = presentation.charts[2]
    assert line.value_format == "percent"
    assert [p.value for p in line.series[0].points] == [0.2, 0.6, 0.9]
    assert all(point.at for point in line.series[0].points)

    assert [call[0] for call in decisions.calls] == ["stance", "score", "score"]
    assert all(call[2] == "gold prices" for call in decisions.calls)

    assert presentation.map is not None
    assert {point.country_code for point in presentation.map.points} == {"IR", "US"}
    iran = next(point for point in presentation.map.points if point.country_code == "IR")
    assert iran.story_ids == ["s1"]
    assert -90 <= iran.lat <= 90
    assert -180 <= iran.lon <= 180


async def test_presenter_invalid_choices_fall_back(settings: Settings) -> None:
    output = PresenterOutput(
        charts=[
            ChartChoice(kind="radar", question="Not a supported chart"),
            ChartChoice(kind="pie", question=""),
            ChartChoice(kind="bar", question="How positive is each fact?"),
            ChartChoice(kind="bar", question="How positive is each fact?"),
        ]
    )
    presentation = await build_presentation(
        make_brief(),
        generator=FakeGenerator(output),
        decisions=FakeDecisions(),
        settings=settings,
    )

    assert presentation.fallback is True
    assert 2 <= len(presentation.charts) <= settings.presenter_max_charts
    assert all(chart.series for chart in presentation.charts)
    assert all(chart.kind in {"bar", "line", "pie"} for chart in presentation.charts)


async def test_presenter_map_validation_groups_countries(settings: Settings) -> None:
    output = make_output()
    output.locations = [
        PresenterLocation(country="IR", story_ids=["s1"], label="Iran"),
        PresenterLocation(country="Iran", story_ids=["s2"], label="Iran again"),
        PresenterLocation(country="Xanadu", story_ids=["s1"]),
        PresenterLocation(country="US", story_ids=["missing"]),
    ]
    presentation = await build_presentation(
        make_brief(),
        generator=FakeGenerator(output),
        decisions=FakeDecisions(),
        settings=settings,
    )

    assert presentation.map is not None
    assert len(presentation.map.points) == 1
    iran = presentation.map.points[0]
    assert iran.country_code == "IR"
    assert iran.story_ids == ["s1", "s2"]


async def test_presenter_without_generator_uses_fallback(settings: Settings) -> None:
    presentation = await build_presentation(
        make_brief(),
        generator=None,
        decisions=FakeDecisions(),
        settings=settings,
    )
    assert presentation.fallback is True
    assert presentation.map is None
    assert len(presentation.charts) >= 2


async def test_fallback_presentation_uses_laya(settings: Settings) -> None:
    decisions = FakeDecisions()
    presentation = await fallback_presentation(
        make_brief(), decisions=decisions, settings=settings
    )
    assert presentation.fallback is True
    assert presentation.map is None
    assert 2 <= len(presentation.charts) <= 3
    assert decisions.calls
