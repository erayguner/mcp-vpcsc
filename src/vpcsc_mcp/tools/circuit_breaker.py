"""Circuit breaker for external dependencies (gcloud subprocess, etc.).

Implements AGENT_GOVERNANCE_FRAMEWORK §13.1 — every external dependency sits
behind a breaker with documented open/half-open/closed thresholds. An open
breaker denies cleanly rather than failing silently.

States:
- CLOSED:    normal operation; failures increment a rolling count
- OPEN:      requests rejected fast for ``cool_off_seconds``
- HALF_OPEN: one trial request allowed; success → CLOSED, failure → OPEN
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpen(RuntimeError):
    """Raised when a call is rejected by an open circuit."""

    def __init__(self, name: str, retry_after: float):
        super().__init__(f"circuit '{name}' open; retry after {retry_after:.1f}s")
        self.name = name
        self.retry_after = retry_after


@dataclass
class BreakerStats:
    state: str
    failures: int
    successes: int
    last_failure_at: float | None
    cool_off_seconds: float
    failure_threshold: int


class CircuitBreaker:
    """Threshold + cool-off circuit breaker.

    - Opens after ``failure_threshold`` consecutive failures.
    - Stays open for ``cool_off_seconds``, then transitions to HALF_OPEN.
    - In HALF_OPEN the next call is a trial; success closes, failure re-opens
      with the cool-off doubled (capped).
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        cool_off_seconds: float = 30.0,
        max_cool_off: float = 300.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.cool_off_seconds = cool_off_seconds
        self._initial_cool_off = cool_off_seconds
        self.max_cool_off = max_cool_off
        self._lock = threading.Lock()
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._successes = 0
        self._opened_at: float | None = None
        self._last_failure_at: float | None = None

    # -- public API -------------------------------------------------------

    def before_call(self) -> None:
        """Raise CircuitOpen if the breaker rejects the call.

        Transitions OPEN → HALF_OPEN when the cool-off has elapsed.
        """
        with self._lock:
            if self._state is BreakerState.OPEN and self._opened_at is not None:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self.cool_off_seconds:
                    self._state = BreakerState.HALF_OPEN
                else:
                    raise CircuitOpen(
                        self.name,
                        retry_after=self.cool_off_seconds - elapsed,
                    )

    def record_success(self) -> None:
        with self._lock:
            self._successes += 1
            if self._state in (BreakerState.HALF_OPEN, BreakerState.OPEN):
                self._state = BreakerState.CLOSED
                self._failures = 0
                self._opened_at = None
                self.cool_off_seconds = self._initial_cool_off
            else:
                self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._last_failure_at = time.time()
            if self._state is BreakerState.HALF_OPEN:
                self._state = BreakerState.OPEN
                self._opened_at = time.monotonic()
                self.cool_off_seconds = min(
                    self.cool_off_seconds * 2,
                    self.max_cool_off,
                )
            elif self._state is BreakerState.CLOSED and self._failures >= self.failure_threshold:
                self._state = BreakerState.OPEN
                self._opened_at = time.monotonic()

    @property
    def state(self) -> BreakerState:
        return self._state

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failures": self._failures,
                "successes": self._successes,
                "last_failure_at": self._last_failure_at,
                "cool_off_seconds": self.cool_off_seconds,
                "failure_threshold": self.failure_threshold,
            }

    def reset_for_tests(self) -> None:
        with self._lock:
            self._state = BreakerState.CLOSED
            self._failures = 0
            self._successes = 0
            self._opened_at = None
            self._last_failure_at = None
            self.cool_off_seconds = self._initial_cool_off


# Module-level breaker for the gcloud subprocess dependency.
gcloud_breaker = CircuitBreaker(
    "gcloud",
    failure_threshold=5,
    cool_off_seconds=30.0,
    max_cool_off=300.0,
)
