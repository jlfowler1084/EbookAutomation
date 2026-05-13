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


@contextmanager
def _get_conn(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Open a WAL-mode connection to web_service.db, closing it when done."""
    path = db_path or get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    """Create the jobs table if it does not exist. Idempotent."""
    with _get_conn(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
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
) -> None:
    """Insert a new job with status=queued."""
    settings = get_settings()
    now = int(time.time())
    if ttl is None:
        ttl = settings.job_ttl_free if tier == "free" else settings.job_ttl_premium
    with _get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs
                (job_id, status, tier, input_fmt, output_fmt, temp_dir, input_path,
                 created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, STATUS_QUEUED, tier, input_fmt, output_fmt, temp_dir, input_path,
             now, now + ttl),
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
    db_path: Path | None = None,
) -> None:
    with _get_conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, output_path = ?, output_size = ? WHERE job_id = ?",
            (STATUS_DONE, output_path, output_size, job_id),
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
