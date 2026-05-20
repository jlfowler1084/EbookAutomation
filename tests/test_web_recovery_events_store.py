"""Tests for web_service.recovery_events_store (EB-292)."""

from __future__ import annotations

import sqlite3
import time

import pytest

from web_service import recovery_events_store


@pytest.fixture()
def db_path(tmp_path):
    """A fresh SQLite DB file for each test."""
    p = tmp_path / "recovery_events_test.db"
    recovery_events_store.init_db(p)
    return p


class TestInitDb:
    def test_creates_table(self, db_path):
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='recovery_events'"
            ).fetchone()
        assert row is not None

    def test_idempotent(self, db_path):
        # Second call must not raise
        recovery_events_store.init_db(db_path)
        recovery_events_store.init_db(db_path)
        # And the table is still there
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='recovery_events'"
            ).fetchone()
        assert row is not None


class TestLogEvent:
    def test_logs_valid_event(self, db_path):
        recovery_events_store.log_event("api_recover_post", db_path=db_path)
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                "SELECT event_type, created_at, details FROM recovery_events"
            ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "api_recover_post"
        assert isinstance(rows[0][1], int)
        assert rows[0][2] is None

    def test_logs_with_details(self, db_path):
        recovery_events_store.log_event(
            "api_recover_post",
            details={"result": "success"},
            db_path=db_path,
        )
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT details FROM recovery_events"
            ).fetchone()
        assert row[0] == '{"result": "success"}'

    def test_logs_three_event_types(self, db_path):
        for et in ("api_recover_post", "payment_success_revisit", "recover_page_view"):
            recovery_events_store.log_event(et, db_path=db_path)
        with sqlite3.connect(str(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM recovery_events").fetchone()[0]
        assert count == 3

    def test_rejects_unknown_event_type(self, db_path):
        # Must not raise, must not insert a row
        recovery_events_store.log_event("malicious_type", db_path=db_path)
        with sqlite3.connect(str(db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM recovery_events").fetchone()[0]
        assert count == 0

    def test_non_serialisable_details_falls_back_to_null(self, db_path):
        # set objects are not JSON-serialisable
        recovery_events_store.log_event(
            "api_recover_post",
            details={"bad": {1, 2, 3}},
            db_path=db_path,
        )
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT details FROM recovery_events"
            ).fetchone()
        # Row still written, details NULL because serialisation failed
        assert row is not None
        assert row[0] is None

    def test_fire_and_forget_does_not_raise_on_db_failure(self, tmp_path):
        # Point at a non-existent parent that can't be created
        # (use a path under an existing file, which can't be a directory)
        existing_file = tmp_path / "not_a_dir"
        existing_file.write_text("blocking", encoding="utf-8")
        bad_path = existing_file / "child.db"
        # Must not raise — log_event swallows exceptions
        recovery_events_store.log_event(
            "api_recover_post", db_path=bad_path
        )


class TestCountEventsSince:
    def test_zero_when_empty(self, db_path):
        n = recovery_events_store.count_events_since(
            "api_recover_post", since_unix=0, db_path=db_path
        )
        assert n == 0

    def test_counts_only_matching_type(self, db_path):
        for _ in range(3):
            recovery_events_store.log_event("api_recover_post", db_path=db_path)
        for _ in range(2):
            recovery_events_store.log_event("recover_page_view", db_path=db_path)
        assert recovery_events_store.count_events_since(
            "api_recover_post", since_unix=0, db_path=db_path
        ) == 3
        assert recovery_events_store.count_events_since(
            "recover_page_view", since_unix=0, db_path=db_path
        ) == 2

    def test_respects_since_cutoff(self, db_path):
        future = int(time.time()) + 3600
        recovery_events_store.log_event("api_recover_post", db_path=db_path)
        assert recovery_events_store.count_events_since(
            "api_recover_post", since_unix=future, db_path=db_path
        ) == 0


# ---------------------------------------------------------------------------
# EB-324 Unit 9a: telemetry whitelist extension
# ---------------------------------------------------------------------------


class TestEB324EventTypes:
    """Each of the 14 EB-324 event types must be in _VALID_EVENT_TYPES, and
    log_event() must accept and persist each one (rather than silently
    dropping it via the unknown-event-type guard at line 112-117).

    If an implementer adds a Send-to-Kindle or re-convert event in a later
    unit without extending _VALID_EVENT_TYPES, this test catches it.
    """

    EB_324_EVENT_TYPES = [
        # Re-convert (Unit 3 emits)
        "reconvert_attempted",
        "reconvert_succeeded",
        "reconvert_failed",
        "reconvert_refund_applied",
        # Send-to-Kindle send-side (Unit 4 emits)
        "send_to_kindle_attempted",
        "send_to_kindle_rejected_by_validation",
        "send_to_kindle_accepted_by_resend",
        "send_to_kindle_send_error",
        # Send-to-Kindle delivery-side (Unit 10 webhook handler emits)
        "send_to_kindle_delivered_to_mail_server",
        "send_to_kindle_bounced",
        "send_to_kindle_delivery_failed",
        "send_to_kindle_delivery_delayed",
        # Result-page UX (Unit 6 emits)
        "expired_action_attempted",
        # Internal invariant violation (Unit 4 emits on output_path boundary failure)
        "kindle_send_invariant_violation",
    ]

    @pytest.mark.parametrize("event_type", EB_324_EVENT_TYPES)
    def test_event_type_in_whitelist(self, event_type):
        assert event_type in recovery_events_store._VALID_EVENT_TYPES, (
            f"EB-324 event type {event_type!r} missing from _VALID_EVENT_TYPES — "
            "log_event() would silently drop it."
        )

    @pytest.mark.parametrize("event_type", EB_324_EVENT_TYPES)
    def test_log_event_persists_each_eb_324_type(self, db_path, event_type):
        recovery_events_store.log_event(
            event_type,
            details={"job_id": "j_test", "extra": "data"},
            db_path=db_path,
        )
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT event_type, details FROM recovery_events WHERE event_type = ?",
                (event_type,),
            ).fetchone()
        assert row is not None, f"{event_type} was not persisted"
        assert row[0] == event_type
        assert "j_test" in row[1]  # details JSON contains the job_id

    def test_format_selector_engaged_is_NOT_in_whitelist(self):
        """R11 (FormatSelector visibility) is deferred per plan-review P1-15;
        format_selector_engaged ships with R11, not Wave 1. If a future change
        adds it to _VALID_EVENT_TYPES without lifting the R11 deferral, this
        regression test catches the drift."""
        assert "format_selector_engaged" not in recovery_events_store._VALID_EVENT_TYPES, (
            "format_selector_engaged is in _VALID_EVENT_TYPES — R11 is deferred per "
            "EB-324 plan P1-15, so this event should not ship in Wave 1."
        )
