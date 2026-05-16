"""SQLite job store for web service conversion jobs (data/web_service.db).

Separate from data/ebook_patterns.db — this DB tracks transient web service state only.
All access is synchronous; callers in async context should use run_in_executor for writes.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from web_service.config import get_settings

log = logging.getLogger(__name__)

# Valid job status values
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_EXPIRED = "expired"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    status      TEXT    NOT NULL DEFAULT 'queued',
    tier        TEXT    NOT NULL DEFAULT 'free',
    input_fmt   TEXT    NOT NULL,
    output_fmt  TEXT    NOT NULL,
    token_hash  TEXT,
    created_at  INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL,
    error_msg   TEXT,
    input_path  TEXT,
    output_path TEXT,
    output_size INTEGER,
    temp_dir    TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status   ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_expires  ON jobs(expires_at);
"""

# EB-245 + EB-274: post-launch columns added via idempotent ALTER TABLE.
# SQLite lacks IF NOT EXISTS for ADD COLUMN, so we check PRAGMA table_info first.
# vqa_pass is stored as INTEGER (0/1) — SQLite has no native BOOLEAN.
# original_filename (EB-274) is captured at upload time so the download response
# can attach the user's original filename via Content-Disposition.
_LATER_COLUMNS: list[tuple[str, str]] = [
    ("gemini_cost_usd",    "REAL    DEFAULT 0.0"),
    ("vqa_score",          "INTEGER"),
    ("vqa_pass",           "INTEGER"),
    ("vqa_cost_usd",       "REAL    DEFAULT 0.0"),
    ("vqa_skipped_reason", "TEXT"),
    ("original_filename",  "TEXT"),
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply idempotent column-add migrations under a SQLite write lock (EB-293).

    BEGIN IMMEDIATE acquires a RESERVED lock so that concurrent workers
    (uvicorn runs the service with --workers 2 in prod) serialise correctly:
    the loser waits up to PRAGMA busy_timeout for the winner to commit, then
    re-reads PRAGMA table_info inside the same transaction and finds nothing
    to add. Without the lock, two workers could both read a pre-migration
    PRAGMA snapshot and both try to ALTER the same column, raising
    "duplicate column name". Re-running against a fully-migrated DB is a no-op.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        for col, type_clause in _LATER_COLUMNS:
            if col not in existing:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {type_clause}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


@contextmanager
def _get_conn(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Open a WAL-mode connection to web_service.db, closing it when done."""
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # EB-293: busy_timeout lets BEGIN IMMEDIATE writers wait for the lock
    # instead of failing fast with "database is locked" when two uvicorn
    # workers race on _apply_migrations during a fresh-column deploy.
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
    """Create the jobs table if it does not exist. Idempotent.

    Also applies AI-telemetry column migrations (EB-245) so existing prod
    databases gain the new columns on the first restart after deployment.
    """
    with _get_conn(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
        _apply_migrations(conn)
    log.info("web_service.db initialised at %s", db_path or get_settings().db_path)


def new_job_id() -> str:
    return str(uuid.uuid4())


def create_job(
    job_id: str,
    tier: str,
    input_fmt: str,
    output_fmt: str,
    temp_dir: str,
    input_path: str = "",
    ttl: int | None = None,
    db_path: Path | None = None,
    *,
    original_filename: str | None = None,
) -> None:
    """Insert a new job with status=queued.

    original_filename (EB-274) is the user's uploaded filename, used later by
    the download endpoint to set Content-Disposition. Optional for backward
    compat with pre-EB-274 callers and pre-migration DB rows.
    """
    settings = get_settings()
    now = int(time.time())
    if ttl is None:
        ttl = settings.job_ttl_free if tier == "free" else settings.job_ttl_premium
    with _get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs
                (job_id, status, tier, input_fmt, output_fmt, temp_dir, input_path,
                 created_at, expires_at, original_filename)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, STATUS_QUEUED, tier, input_fmt, output_fmt, temp_dir, input_path,
             now, now + ttl, original_filename),
        )


def get_job(job_id: str, db_path: Path | None = None) -> dict | None:
    """Return job as a dict, or None if not found."""
    with _get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    return dict(row) if row else None


def set_running(job_id: str, db_path: Path | None = None) -> None:
    with _get_conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ? WHERE job_id = ?",
            (STATUS_RUNNING, job_id),
        )


def set_done(
    job_id: str,
    output_path: str,
    output_size: int,
    *,
    gemini_cost_usd: float = 0.0,
    vqa_score: int | None = None,
    vqa_pass: bool | None = None,
    vqa_cost_usd: float = 0.0,
    vqa_skipped_reason: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Mark a job as done and persist AI telemetry (EB-245).

    AI fields default to no-op values so free-tier callers can keep the
    positional 3-arg call shape. SQLite stores vqa_pass as 0/1 because it
    has no native BOOLEAN; we coerce here.
    """
    vqa_pass_int = None if vqa_pass is None else int(bool(vqa_pass))
    with _get_conn(db_path) as conn:
        conn.execute(
            """
            UPDATE jobs SET
                status = ?, output_path = ?, output_size = ?,
                gemini_cost_usd = ?, vqa_score = ?, vqa_pass = ?,
                vqa_cost_usd = ?, vqa_skipped_reason = ?
            WHERE job_id = ?
            """,
            (
                STATUS_DONE, output_path, output_size,
                gemini_cost_usd, vqa_score, vqa_pass_int,
                vqa_cost_usd, vqa_skipped_reason,
                job_id,
            ),
        )


def set_failed(job_id: str, error_msg: str, db_path: Path | None = None) -> None:
    with _get_conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, error_msg = ? WHERE job_id = ?",
            (STATUS_FAILED, error_msg, job_id),
        )


def set_expired(job_id: str, db_path: Path | None = None) -> None:
    with _get_conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ? WHERE job_id = ?",
            (STATUS_EXPIRED, job_id),
        )


def get_expired_jobs(db_path: Path | None = None) -> list[dict]:
    """Return jobs whose TTL has elapsed and are not already expired."""
    now = int(time.time())
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE expires_at <= ? AND status != ?",
            (now, STATUS_EXPIRED),
        ).fetchall()
    return [dict(r) for r in rows]


def purge_job(job_id: str, db_path: Path | None = None) -> None:
    """Delete a job record entirely (called after temp files are cleaned up)."""
    with _get_conn(db_path) as conn:
        conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
