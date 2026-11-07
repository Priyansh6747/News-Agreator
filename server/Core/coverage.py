from __future__ import annotations

from Core.models import (
    Attempt,
    Backend,
    BackendAttempt,
    BackendCoverage,
    Coverage,
    CoverageStatus,
    Stage,
    TextStatus,
)

FAILED_ATTEMPTS = {
    Attempt.DIRECT_TIMEOUT,
    Attempt.RELAY_FAILURE,
    Attempt.ABORTED_BY_DEADLINE,
    Attempt.OTHER_FETCH_FAILURE,
    Attempt.NOT_STARTED,
    Attempt.EMPTY,
    Attempt.ALL_UNDATED,
    Attempt.PARTIAL_UNDATED,
    Attempt.NEGATIVE_CACHE,
}


class CoverageCollector:
    def __init__(self) -> None:
        self._backends: dict[Backend, BackendCoverage] = {}
        self._attempts: list[BackendAttempt] = []
        self._drops: dict[str, int] = {}
        self._text_status: dict[TextStatus, int] = {}
        self._timings: dict[Stage, int] = {}
        self._notes: list[str] = []
        self._forced_status: CoverageStatus | None = None

    def _backend(self, backend: Backend) -> BackendCoverage:
        if backend not in self._backends:
            self._backends[backend] = BackendCoverage(backend=backend)
        return self._backends[backend]

    def record_attempt(
        self,
        backend: Backend,
        attempt: Attempt,
        *,
        returned: int = 0,
        elapsed_ms: int = 0,
        detail: str | None = None,
    ) -> None:
        entry = self._backend(backend)
        entry.attempted += 1
        entry.returned += returned
        self._attempts.append(
            BackendAttempt(
                backend=backend,
                attempt=attempt,
                returned=returned,
                elapsed_ms=elapsed_ms,
                detail=detail,
            )
        )

    def record_kept(self, backend: Backend, count: int = 1) -> None:
        self._backend(backend).kept += count

    def add_drop(self, reason: str, count: int = 1, backend: Backend | None = None) -> None:
        if count <= 0:
            return
        self._drops[reason] = self._drops.get(reason, 0) + count
        if backend is not None:
            entry = self._backend(backend)
            entry.drops[reason] = entry.drops.get(reason, 0) + count

    def record_text_status(self, status: TextStatus, count: int = 1) -> None:
        self._text_status[status] = self._text_status.get(status, 0) + count

    def record_timing(self, stage: Stage, elapsed_ms: int) -> None:
        self._timings[stage] = elapsed_ms

    def note(self, message: str) -> None:
        if message and message not in self._notes:
            self._notes.append(message)

    def force_status(self, status: CoverageStatus) -> None:
        self._forced_status = status

    def finish(self) -> Coverage:
        kept = sum(entry.kept for entry in self._backends.values())
        attempts = self._attempts
        if not attempts or kept == 0:
            status = CoverageStatus.UNAVAILABLE
        elif any(attempt.attempt in FAILED_ATTEMPTS for attempt in attempts):
            status = CoverageStatus.PARTIAL
        else:
            status = CoverageStatus.COMPLETE
        if self._forced_status is not None:
            status = self._forced_status
        return Coverage(
            status=status,
            backends=list(self._backends.values()),
            attempts=list(attempts),
            drops=dict(self._drops),
            text_status=dict(self._text_status),
            timings_ms=dict(self._timings),
            notes=list(self._notes),
        )
