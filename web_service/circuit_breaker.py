"""Lightweight circuit breaker for SQLite DB outage protection.

Tracks consecutive DB failures and opens the circuit to prevent thread-pool
exhaustion during prolonged DB outages.

State machine:
  CLOSED  — normal operation; DB calls proceed
  OPEN    — >5 consecutive failures within 60s → short-circuit to 503 for 30s
  HALF-OPEN probe — after 30s open window expires, one request is allowed through
                    to test recovery; success resets counter and closes the circuit

Usage in route handlers:
    from web_service import circuit_breaker
    if circuit_breaker.circuit_is_open():
        raise HTTPException(503, detail={"error": "Service temporarily unavailable",
                                          "code": "DB_CIRCUIT_OPEN"})
    try:
        # do DB work
        circuit_breaker.db_call_succeeded()
    except sqlite3.OperationalError:
        circuit_breaker.db_call_failed()
        raise

Design note: module-level state is process-local and not shared across workers.
For multi-process deployments, each worker maintains its own circuit state — this
is acceptable given the circuit's purpose is to prevent thundering-herd against
a locked DB, not to coordinate across all workers.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

# Tunable constants
_FAILURE_THRESHOLD = 5       # Consecutive failures before opening
_FAILURE_WINDOW_SECS = 60    # Failures older than this don't count
_OPEN_DURATION_SECS = 30     # How long the circuit stays open before half-open probe

# Module-level state (process-local)
_consecutive_failures: int = 0
_circuit_open_until: float = 0.0
_last_failure_time: float = 0.0


def db_call_failed() -> None:
    """Record a DB call failure.

    If the last failure was more than _FAILURE_WINDOW_SECS ago, the streak
    is considered stale and the counter is reset to 1 (only the current failure).

    If the failure count reaches _FAILURE_THRESHOLD, the circuit is opened
    for _OPEN_DURATION_SECS.
    """
    global _consecutive_failures, _circuit_open_until, _last_failure_time

    now = time.monotonic()

    # Expire stale streak: if last failure was outside the window, restart count
    if _last_failure_time > 0 and (now - _last_failure_time) > _FAILURE_WINDOW_SECS:
        log.debug(
            "circuit_breaker: stale failure streak expired (gap=%.1fs); resetting counter",
            now - _last_failure_time,
        )
        _consecutive_failures = 0

    _consecutive_failures += 1
    _last_failure_time = now

    if _consecutive_failures >= _FAILURE_THRESHOLD:
        _circuit_open_until = now + _OPEN_DURATION_SECS
        log.error(
            "circuit_breaker: DB circuit OPENED after %d consecutive failures "
            "(within %.0fs window); circuit open for %.0fs",
            _consecutive_failures,
            _FAILURE_WINDOW_SECS,
            _OPEN_DURATION_SECS,
        )
    else:
        log.warning(
            "circuit_breaker: DB failure #%d/%d",
            _consecutive_failures,
            _FAILURE_THRESHOLD,
        )


def db_call_succeeded() -> None:
    """Record a successful DB call, resetting the failure counter.

    Called after any DB operation that completes without OperationalError.
    Resets both the consecutive failure count and the last_failure_time.
    Does NOT close the circuit if it is currently open — the circuit closes
    naturally when the open window expires (half-open probe pattern).
    """
    global _consecutive_failures, _last_failure_time

    if _consecutive_failures > 0:
        log.debug(
            "circuit_breaker: DB call succeeded; resetting failure counter from %d",
            _consecutive_failures,
        )
    _consecutive_failures = 0
    _last_failure_time = 0.0


def circuit_is_open() -> bool:
    """Return True if the circuit is currently open (DB calls should be rejected).

    The circuit opens when _FAILURE_THRESHOLD consecutive failures occur within
    _FAILURE_WINDOW_SECS. It closes automatically after _OPEN_DURATION_SECS
    (half-open probe: one request is allowed through to test recovery).

    Returns:
        True if the circuit is open and DB calls should short-circuit to 503.
        False if the circuit is closed (normal operation) or half-open window expired.
    """
    return time.monotonic() < _circuit_open_until
