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
