"""Tests for web_service.circuit_breaker — lightweight DB-outage protection.

Exercises:
- Initial state is closed (circuit_is_open() returns False)
- 5 consecutive failures within 60s open the circuit for 30s
- db_call_succeeded() resets the failure counter
- After 30s open window, circuit returns to closed (half-open probe)
- Failures spanning > 60s do not accumulate (counter resets on stale last_failure)
"""

from __future__ import annotations

import time

import pytest

import web_service.circuit_breaker as cb


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Reset circuit breaker module state before each test."""
    cb._consecutive_failures = 0
    cb._circuit_open_until = 0.0
    cb._last_failure_time = 0.0
    yield
    # Cleanup after test too
    cb._consecutive_failures = 0
    cb._circuit_open_until = 0.0
    cb._last_failure_time = 0.0


class TestInitialState:
    def test_initially_closed(self):
        """Circuit must start in the closed state."""
        assert cb.circuit_is_open() is False

    def test_no_failures_yet(self):
        """Failure counter must start at zero."""
        assert cb._consecutive_failures == 0


class TestCircuitOpens:
    def test_five_failures_opens_circuit(self):
        """5 consecutive failures within 60s must open the circuit."""
        for _ in range(5):
            cb.db_call_failed()
        assert cb.circuit_is_open() is True

    def test_four_failures_stays_closed(self):
        """Only 4 failures must not open the circuit."""
        for _ in range(4):
            cb.db_call_failed()
        assert cb.circuit_is_open() is False

    def test_circuit_opens_for_30s(self):
        """Once open, circuit must remain open for ~30s."""
        for _ in range(5):
            cb.db_call_failed()
        now = time.monotonic()
        assert cb._circuit_open_until > now
        # Should be open for approximately 30s (allow small tolerance)
        assert cb._circuit_open_until <= now + 31


class TestSuccessResetsCounter:
    def test_success_resets_failure_count(self):
        """db_call_succeeded() must reset the consecutive failure counter."""
        for _ in range(4):
            cb.db_call_failed()
        cb.db_call_succeeded()
        assert cb._consecutive_failures == 0

    def test_success_does_not_reopen_closed_circuit(self):
        """Calling succeeded on a closed circuit must keep it closed."""
        cb.db_call_succeeded()
        assert cb.circuit_is_open() is False

    def test_failure_after_reset_restarts_count(self):
        """After a success reset, 4 subsequent failures must not open the circuit."""
        for _ in range(4):
            cb.db_call_failed()
        cb.db_call_succeeded()
        for _ in range(4):
            cb.db_call_failed()
        # Reset means we need 5 new failures to open
        assert cb.circuit_is_open() is False

    def test_five_failures_after_reset_opens_circuit(self):
        """After a success reset, 5 new consecutive failures DO open the circuit."""
        for _ in range(4):
            cb.db_call_failed()
        cb.db_call_succeeded()
        for _ in range(5):
            cb.db_call_failed()
        assert cb.circuit_is_open() is True


class TestHalfOpenAfterTimeout:
    def test_circuit_closes_after_open_window(self):
        """After the 30s open window expires, circuit_is_open() must return False."""
        for _ in range(5):
            cb.db_call_failed()
        # Force the open-until timestamp to the past
        cb._circuit_open_until = time.monotonic() - 1.0
        assert cb.circuit_is_open() is False

    def test_circuit_is_open_during_window(self):
        """circuit_is_open() returns True while within the 30s window."""
        for _ in range(5):
            cb.db_call_failed()
        # Manually set open_until to far future to ensure we're in window
        cb._circuit_open_until = time.monotonic() + 100.0
        assert cb.circuit_is_open() is True


class TestStaleFailureExpiry:
    def test_old_failures_dont_accumulate(self):
        """Failures with last_failure_time > 60s ago must reset the counter."""
        # Simulate 4 old failures by setting last_failure_time to >60s ago
        cb._consecutive_failures = 4
        cb._last_failure_time = time.monotonic() - 61.0
        # One new failure — should restart the count from 1 (not 5)
        cb.db_call_failed()
        # Counter should be 1 (stale failures expired), not 5
        assert cb._consecutive_failures == 1
        assert cb.circuit_is_open() is False

    def test_four_fresh_plus_one_resets_not_five(self):
        """4 fresh failures + 1 after >60s gap = counter reset to 1, no open."""
        for _ in range(4):
            cb.db_call_failed()
        # Simulate time passing (backdate last_failure_time)
        cb._last_failure_time = time.monotonic() - 61.0
        cb.db_call_failed()
        # If correctly expiring stale failures, counter is now 1, not 5
        assert cb._consecutive_failures == 1
        assert cb.circuit_is_open() is False
