from __future__ import annotations

from Core.coverage import CoverageCollector
from Core.models import Attempt, Backend, CoverageStatus, Stage, TextStatus


def test_empty_collector_is_unavailable() -> None:
    assert CoverageCollector().finish().status is CoverageStatus.UNAVAILABLE


def test_completed_attempt_with_kept_items_is_complete() -> None:
    coverage = CoverageCollector()
    coverage.record_attempt(Backend.BING_NEWS, Attempt.COMPLETED, returned=3, elapsed_ms=120)
    coverage.record_kept(Backend.BING_NEWS, 3)
    report = coverage.finish()
    assert report.status is CoverageStatus.COMPLETE
    assert report.attempts[0].returned == 3
    assert report.backends[0].kept == 3


def test_failed_attempt_marks_partial() -> None:
    coverage = CoverageCollector()
    coverage.record_attempt(Backend.BING_NEWS, Attempt.COMPLETED, returned=2)
    coverage.record_kept(Backend.BING_NEWS, 2)
    coverage.record_attempt(Backend.GDELT, Attempt.NOT_STARTED)
    assert coverage.finish().status is CoverageStatus.PARTIAL


def test_empty_backend_marks_partial() -> None:
    coverage = CoverageCollector()
    coverage.record_attempt(Backend.BING_NEWS, Attempt.COMPLETED, returned=1)
    coverage.record_kept(Backend.BING_NEWS, 1)
    coverage.record_attempt(Backend.GDELT, Attempt.EMPTY)
    assert coverage.finish().status is CoverageStatus.PARTIAL


def test_forced_status_overrides_derived_status() -> None:
    coverage = CoverageCollector()
    coverage.record_attempt(Backend.BING_NEWS, Attempt.COMPLETED, returned=2)
    coverage.record_kept(Backend.BING_NEWS, 2)
    coverage.force_status(CoverageStatus.UNAVAILABLE)
    assert coverage.finish().status is CoverageStatus.UNAVAILABLE


def test_drops_text_status_timings_and_notes() -> None:
    coverage = CoverageCollector()
    coverage.record_attempt(Backend.BING_NEWS, Attempt.COMPLETED, returned=1)
    coverage.record_kept(Backend.BING_NEWS, 1)
    coverage.add_drop("duplicate", 2, backend=Backend.BING_NEWS)
    coverage.record_text_status(TextStatus.NOT_FETCHED, 4)
    coverage.record_timing(Stage.RANK, 15)
    coverage.note("hello")
    coverage.note("hello")
    report = coverage.finish()
    assert report.drops == {"duplicate": 2}
    assert report.backends[0].drops == {"duplicate": 2}
    assert report.text_status[TextStatus.NOT_FETCHED] == 4
    assert report.timings_ms[Stage.RANK] == 15
    assert report.notes == ["hello"]
