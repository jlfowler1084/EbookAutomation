"""Regression test for EB-293 — _apply_migrations race when uvicorn runs --workers 2.

The production incident: on the EB-292 deploy that added the `original_filename`
column to a prod DB that had not yet seen the migration, the service refused to
start with `sqlite3.OperationalError: duplicate column name: original_filename`.
Whichever worker won the race committed some ALTERs; the loser's PRAGMA snapshot
was stale by the time its ALTER fired, so it tried to re-add a column the winner
had just committed.

This test simulates the race by spawning two processes that both call
`job_store.init_db()` against a DB in the pre-migration state, synchronised on
a Barrier so they both reach `_apply_migrations` at the same instant. Both
workers must complete without raising.
"""

from __future__ import annotations

import multiprocessing as mp
import sqlite3
import traceback
from pathlib import Path

import pytest

from web_service.job_store import _LATER_COLUMNS, _SCHEMA_SQL


def _init_db_worker(db_path_str: str, barrier, results_queue) -> None:
    """Spawn-mode worker: wait at the barrier, then call init_db.

    Defined at module top level so multiprocessing.spawn (the default on Windows)
    can pickle and re-import it in the child process. Captures the full
    traceback on failure so the test can report which statement raised.
    """
    # Re-import in the child — under spawn, the child has a fresh interpreter
    from web_service.job_store import init_db

    try:
        barrier.wait(timeout=10)
        init_db(Path(db_path_str))
        results_queue.put(("ok", None))
    except Exception as exc:
        results_queue.put(("error", f"{exc!r}\n{traceback.format_exc()}"))


@pytest.mark.parametrize("trial", range(3))
def test_concurrent_init_db_against_pre_migration_db(tmp_path: Path, trial: int) -> None:
    """AC4 (EB-293): two processes calling init_db against a pre-migration DB
    must both return cleanly.

    Pre-migration state = the `jobs` table exists with the base schema, but the
    `_LATER_COLUMNS` entries have not yet been ALTER'd in. This mirrors what
    a prod DB looks like the moment a new `_LATER_COLUMNS` entry lands.

    Three trials make race surfacing reliable; on master (no fix) the unfixed
    code can pass occasionally if the two workers' PRAGMA/ALTER windows happen
    to serialise cleanly, but at least one trial should hit `OperationalError`
    ("duplicate column name" or "database is locked").
    """
    db_path = tmp_path / f"race_{trial}.db"

    # Set up the pre-migration state: jobs table with the base schema only.
    # _SCHEMA_SQL deliberately omits the _LATER_COLUMNS entries; those are
    # applied by _apply_migrations on every init_db() call.
    #
    # Pre-set WAL mode in the seed DB to mirror production reality: in prod
    # the DB has been WAL-mode for weeks, so the workers' first PRAGMA
    # journal_mode=WAL is a no-op. Without this, both spawn-mode workers
    # would race on the actual WAL transition (which needs an EXCLUSIVE lock)
    # and the loser would fail-fast on Linux runners — masking the real race
    # in _apply_migrations that this test is designed to exercise.
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()

    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(2)
    results: "mp.Queue" = ctx.Queue()

    p1 = ctx.Process(target=_init_db_worker, args=(str(db_path), barrier, results))
    p2 = ctx.Process(target=_init_db_worker, args=(str(db_path), barrier, results))
    p1.start()
    p2.start()
    p1.join(timeout=30)
    p2.join(timeout=30)

    assert not p1.is_alive(), "worker 1 hung past 30s"
    assert not p2.is_alive(), "worker 2 hung past 30s"

    outcomes = [results.get(timeout=5) for _ in range(2)]
    errors = [outcome[1] for outcome in outcomes if outcome[0] == "error"]
    assert errors == [], (
        f"trial {trial}: concurrent init_db raised {errors}. "
        "Expected both workers to succeed under the EB-293 fix."
    )

    # AC2 sanity: both workers should have seen the same final schema, with
    # every _LATER_COLUMNS entry present exactly once.
    final = sqlite3.connect(str(db_path))
    cols = [row[1] for row in final.execute("PRAGMA table_info(jobs)").fetchall()]
    final.close()
    for col, _type in _LATER_COLUMNS:
        assert cols.count(col) == 1, f"column {col} present {cols.count(col)} times, expected 1"


def test_apply_migrations_no_op_on_fully_migrated_db(tmp_path: Path) -> None:
    """AC2 (EB-293): re-running init_db against an already-migrated DB must be
    a no-op (no spurious ALTERs, no log noise, no exceptions). Single-process
    smoke test that complements the concurrent test above.
    """
    from web_service.job_store import init_db

    db_path = tmp_path / "fully_migrated.db"

    # First call lays down both base schema and _LATER_COLUMNS
    init_db(db_path)

    # Second call must be a no-op
    init_db(db_path)
    init_db(db_path)  # and a third, for good measure

    final = sqlite3.connect(str(db_path))
    cols = [row[1] for row in final.execute("PRAGMA table_info(jobs)").fetchall()]
    final.close()
    for col, _type in _LATER_COLUMNS:
        assert cols.count(col) == 1, f"column {col} duplicated to {cols.count(col)} entries"


def test_token_hash_column_is_not_duplicated_by_eb_324_migration(tmp_path: Path) -> None:
    """EB-324 P0-1 regression: jobs.token_hash already exists in the base _SCHEMA_SQL
    (line 35) as TEXT and is reused for refund correlation per the EB-324 plan.

    The earlier draft of the plan called for adding `token_hash BLOB` via
    _LATER_COLUMNS, which would have raised `sqlite3.OperationalError: duplicate
    column name: token_hash` on every prod boot. This regression test asserts that
    _LATER_COLUMNS does NOT contain a `token_hash` entry, and that after init_db()
    the column appears exactly once with TEXT affinity (the base-schema type).
    """
    from web_service.job_store import init_db

    # Static assertion: _LATER_COLUMNS must not include token_hash. If a future
    # change ever re-adds it, this test fails immediately with a clear message.
    assert all(col != "token_hash" for col, _type in _LATER_COLUMNS), (
        "token_hash is in _LATER_COLUMNS — the column already exists in the base "
        "_SCHEMA_SQL (line 35) as TEXT. Adding it to _LATER_COLUMNS would raise "
        "duplicate-column-name on every prod boot. See EB-324 plan P0-1 resolution."
    )

    # Dynamic assertion: a fresh DB, after init_db(), has token_hash exactly once
    # and with the TEXT affinity from the base schema.
    db_path = tmp_path / "token_hash_check.db"
    init_db(db_path)

    final = sqlite3.connect(str(db_path))
    rows = final.execute("PRAGMA table_info(jobs)").fetchall()
    final.close()
    token_hash_rows = [row for row in rows if row[1] == "token_hash"]
    assert len(token_hash_rows) == 1, (
        f"token_hash appears {len(token_hash_rows)} times in jobs schema, expected 1"
    )
    # PRAGMA table_info: row[2] is the type clause (case preserved from CREATE TABLE).
    assert token_hash_rows[0][2].upper() == "TEXT", (
        f"token_hash type is {token_hash_rows[0][2]!r}, expected TEXT — if this fails, "
        "the base schema has drifted from the EB-324 plan's reuse-as-hex strategy."
    )


def test_eb_324_new_columns_present_after_migration(tmp_path: Path) -> None:
    """EB-324 Unit 1: parent_job_id, resend_message_id, kindle_delivery_status
    must land via _LATER_COLUMNS and appear exactly once after init_db()."""
    from web_service.job_store import init_db

    db_path = tmp_path / "eb_324_columns.db"
    init_db(db_path)

    final = sqlite3.connect(str(db_path))
    cols = [row[1] for row in final.execute("PRAGMA table_info(jobs)").fetchall()]
    final.close()

    for required in ("parent_job_id", "resend_message_id", "kindle_delivery_status"):
        assert required in cols, f"EB-324 column {required} missing after init_db()"
        assert cols.count(required) == 1, (
            f"EB-324 column {required} appears {cols.count(required)} times, expected 1"
        )


def test_eb_324_indexes_created_after_migration(tmp_path: Path) -> None:
    """EB-324 Unit 1: idx_jobs_parent_job_id and idx_jobs_resend_message_id must
    land via _LATER_INDEXES inside _apply_migrations (NOT in _SCHEMA_SQL, which
    runs before the columns exist)."""
    from web_service.job_store import init_db

    db_path = tmp_path / "eb_324_indexes.db"
    init_db(db_path)

    final = sqlite3.connect(str(db_path))
    indexes = {
        row[0]
        for row in final.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='jobs'"
        ).fetchall()
    }
    final.close()

    assert "idx_jobs_parent_job_id" in indexes, (
        "idx_jobs_parent_job_id missing — list_children() lookup will table-scan"
    )
    assert "idx_jobs_resend_message_id" in indexes, (
        "idx_jobs_resend_message_id missing — find_by_resend_message_id() will table-scan"
    )
