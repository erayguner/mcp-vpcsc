"""Tests for the gcloud circuit breaker (framework §13.1)."""

from __future__ import annotations

import time

import pytest

from vpcsc_mcp.tools.circuit_breaker import (
    BreakerState,
    CircuitBreaker,
    CircuitOpen,
)


def test_closed_allows_calls():
    b = CircuitBreaker("test", failure_threshold=3, cool_off_seconds=0.05)
    b.before_call()
    b.record_success()
    assert b.state is BreakerState.CLOSED


def test_opens_after_threshold():
    b = CircuitBreaker("test", failure_threshold=3, cool_off_seconds=0.05)
    for _ in range(3):
        b.before_call()
        b.record_failure()
    assert b.state is BreakerState.OPEN
    with pytest.raises(CircuitOpen):
        b.before_call()


def test_half_open_then_closed_on_success():
    b = CircuitBreaker("test", failure_threshold=2, cool_off_seconds=0.02)
    b.record_failure()
    b.record_failure()
    assert b.state is BreakerState.OPEN
    time.sleep(0.03)
    # First call transitions to HALF_OPEN
    b.before_call()
    b.record_success()
    assert b.state is BreakerState.CLOSED


def test_half_open_failure_reopens_with_larger_cool_off():
    b = CircuitBreaker("test", failure_threshold=2, cool_off_seconds=0.02, max_cool_off=0.5)
    b.record_failure()
    b.record_failure()
    initial_cool_off = b.cool_off_seconds
    time.sleep(0.03)
    b.before_call()  # → HALF_OPEN
    b.record_failure()
    assert b.state is BreakerState.OPEN
    assert b.cool_off_seconds > initial_cool_off


def test_success_in_closed_resets_failure_count():
    b = CircuitBreaker("test", failure_threshold=3, cool_off_seconds=0.05)
    b.record_failure()
    b.record_failure()
    b.record_success()
    b.record_failure()
    # Still CLOSED because failure counter was reset
    assert b.state is BreakerState.CLOSED


def test_stats_shape():
    b = CircuitBreaker("test", failure_threshold=2, cool_off_seconds=0.01)
    b.record_success()
    b.record_failure()
    stats = b.stats
    assert stats["name"] == "test"
    assert stats["state"] in {"closed", "open", "half_open"}
    assert stats["failures"] == 1
    assert stats["successes"] == 1
