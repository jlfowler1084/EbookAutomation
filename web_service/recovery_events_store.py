"""SQLite store for Phase 2 recovery-rail usage events (EB-292).

Append-only counter for measuring how often users hit the existing recovery
surfaces. The data drives the post-measurement decision in EB-292 about whether
Phase 3 recovery infrastructure (Stripe-customer-binding, accounts, etc.) is
justified by real usage or is solving a hypothetical problem.

Three event types feed this store:
  - api_recover_post: POST /api/recover called (session_id paste form)
  - payment_success_revisit: GET /payment/success rendered for an
    already-completed session (idempotent revisit path, not first-render)
  - recover_page_view: GET /recover loaded in the Next.js layer, with the
    user's localStorage state (empty / has_tokens / has_expired_tokens)

Design:
  - Append-only — never UPDATE or DELETE rows (no sweep). Storage cost is
    bounded by total event volume × ~200 bytes/row; expected <1 MB over a
    60-day measurement window even with heavy use.
  - Fire-and-forget — log_event() catches all exceptions and logs WARN; a
    failure to write a counter row MUST NOT break the recovery or payment
    flows. Measurement is best-effort.
  - Sync API — callers wrap in loop.run_in_executor() per the convention
    established by web_service/token_store.py and web_service/job_store.py.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from web_service.config import get_settings

log = logging.getLogger(__name__)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS recovery_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    details     TEXT
);
CREATE INDEX IF NOT EXISTS idx_recovery_events_type_time
    ON recovery_events(event_type, created_at);
"""


# Whitelist of accepted event_type values. Anything else is rejected at
# log_event() time to keep the dataset clean for the post-measurement query.
_VALID_EVENT_TYPES: frozenset[str] = frozenset({
    "api_recover_post",
    "payment_success_revisit",
    "recover_page_view",
})


@contextmanager
def _get_conn(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Open a WAL-mode connection to the same web_service.db used by tokens/jobs.

    Mirrors web_service/token_store.py:126 connection helper. Same DB file —
    new table only.
    """
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    """Create the recovery_events table if it doesn't exist. Idempotent."""
    with _get_conn(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
    log.info(
        "recovery_events_store: DB initialised at %s",
        db_path or get_settings().db_path,
    )


def log_event(
    event_type: str,
    details: dict | None = None,
    db_path: Path | None = None,
) -> None:
    """Record one recovery-rail event. Fire-and-forget — never raises.

    Failures to write a counter row are logged at WARN but do NOT propagate.
    The recovery and payment flows must remain functional even if the
    instrumentation table is unavailable.

    Args:
        event_type: One of the values in _VALID_EVENT_TYPES.
        details: Optional structured context (will be JSON-serialised).
        db_path: Optional DB path override (for tests).
    """
    if event_type not in _VALID_EVENT_TYPES:
        log.warning(
            "recovery_events_store: rejected unknown event_type=%r (no row written)",
            event_type,
        )
        return

    try:
        details_json = json.dumps(details, sort_keys=True) if details is not None else None
    except (TypeError, ValueError) as ser_exc:
        log.warning(
            "recovery_events_store: details not JSON-serialisable for event_type=%s err=%r",
            event_type,
            ser_exc,
        )
        details_json = None

    now = int(time.time())
    try:
        with _get_conn(db_path) as conn:
            conn.execute(
                "INSERT INTO recovery_events (event_type, created_at, details) VALUES (?, ?, ?)",
                (event_type, now, details_json),
            )
    except Exception as exc:
        log.warning(
            "recovery_events_store: failed to log event_type=%s err=%r (continuing)",
            event_type,
            exc,
        )


def count_events_since(
    event_type: str,
    since_unix: int,
    db_path: Path | None = None,
) -> int:
    """Return the count of events of a given type since the given timestamp.

    Used by the post-measurement query in EB-292's success criteria:
        SELECT event_type, COUNT(*) FROM recovery_events
        WHERE created_at > strftime('%s','now') - 30*86400
        GROUP BY event_type
    """
    with _get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM recovery_events WHERE event_type=? AND created_at >= ?",
            (event_type, since_unix),
        ).fetchone()
    return row[0] if row else 0
