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

# EB-324 Unit 4: per-(job_id, recipient_hash) idempotency for Send-to-Kindle.
#
# The PRIMARY KEY is the atomic-claim race-gate: two simultaneous send
# attempts both try the INSERT inside their own BEGIN IMMEDIATE; whichever
# commits first wins, and the loser raises sqlite3.IntegrityError on the PK
# collision and returns {"status": "already_sent"} without invoking Resend.
#
# Recipient is stored as SHA-256 hash, not plaintext, so the privacy claim
# "the Kindle address never lives in our database" holds. Equality lookup
# works identically on the hashed key. claim_state lets the route mark the
# row sent vs. claimed-then-failed; failed claims are deleted to allow
# immediate retry.
#
# Deliberately separate from _SCHEMA_SQL (which lives in the same file but
# is logically the jobs table only) and from _LATER_COLUMNS (which can only
# ALTER jobs to add columns). New table → new constant + extra
# executescript() call in init_db().
_KINDLE_IDEMPOTENCY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kindle_send_idempotency (
    job_id         TEXT    NOT NULL,
    recipient_hash BLOB    NOT NULL,
    sent_at        INTEGER NOT NULL,
    claim_state    TEXT    NOT NULL CHECK (claim_state IN ('claimed', 'sent')),
    PRIMARY KEY (job_id, recipient_hash)
);
CREATE INDEX IF NOT EXISTS idx_kindle_send_idempotency_sent_at
    ON kindle_send_idempotency(sent_at);
"""

# EB-324: indexes on _LATER_COLUMNS columns must run AFTER the ADD COLUMNs land.
# CREATE INDEX IF NOT EXISTS is idempotent, but it raises "no such column" if the
# referenced column hasn't been added yet, so these live in _apply_migrations
# (which runs after the column-add loop).
_LATER_INDEXES: list[str] = [
    # Supports list_children() lookup for the result-page action cluster.
    "CREATE INDEX IF NOT EXISTS idx_jobs_parent_job_id ON jobs(parent_job_id)",
    # Supports find_by_resend_message_id() for Unit 10's webhook correlation.
    "CREATE INDEX IF NOT EXISTS idx_jobs_resend_message_id ON jobs(resend_message_id)",
]

# EB-245 + EB-274 + EB-324: post-launch columns added via idempotent ALTER TABLE.
# SQLite lacks IF NOT EXISTS for ADD COLUMN, so we check PRAGMA table_info first.
# vqa_pass is stored as INTEGER (0/1) — SQLite has no native BOOLEAN.
# original_filename (EB-274) is captured at upload time so the download response
# can attach the user's original filename via Content-Disposition.
# EB-324 additions:
#   - parent_job_id: re-convert child jobs link to their parent for the action-cluster UI
#   - resend_message_id: captured from Resend after Send-to-Kindle accept; used for
#     webhook correlation by Unit 10 (find_by_resend_message_id())
#   - kindle_delivery_status: graded delivery state populated by the Resend webhook —
#     'accepted_by_resend' → 'delivered_to_mail_server' / 'bounced' / 'failed' / 'delivery_delayed'
# NOTE: jobs.token_hash already exists as TEXT in the base _SCHEMA_SQL (line 35) and is
# reused for refund correlation per the EB-324 plan (P0-1 resolution). Do NOT re-add it.
_LATER_COLUMNS: list[tuple[str, str]] = [
    ("gemini_cost_usd",       "REAL    DEFAULT 0.0"),
    ("vqa_score",             "INTEGER"),
    ("vqa_pass",              "INTEGER"),
    ("vqa_cost_usd",          "REAL    DEFAULT 0.0"),
    ("vqa_skipped_reason",    "TEXT"),
    ("original_filename",     "TEXT"),
    ("parent_job_id",         "TEXT"),
    ("resend_message_id",     "TEXT"),
    ("kindle_delivery_status", "TEXT"),
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
        # EB-324: indexes that depend on _LATER_COLUMNS columns. CREATE INDEX
        # IF NOT EXISTS is idempotent; safe to re-run on every startup.
        for index_sql in _LATER_INDEXES:
            conn.execute(index_sql)
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
    # EB-293: busy_timeout MUST be set first, before any other PRAGMA, so
    # that the very first lock contention (e.g. two uvicorn workers racing
    # on the WAL-mode transition or on _apply_migrations) waits for the
    # lock instead of failing fast with "database is locked". Setting it
    # after journal_mode meant the first contended statement on a fresh
    # connection had no busy-handler installed.
    conn.execute("PRAGMA busy_timeout=5000")
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
    """Create the jobs table if it does not exist. Idempotent.

    Also applies AI-telemetry column migrations (EB-245) so existing prod
    databases gain the new columns on the first restart after deployment.
    """
    with _get_conn(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.executescript(_KINDLE_IDEMPOTENCY_SCHEMA_SQL)
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
    parent_job_id: str | None = None,
    token_hash_hex: str | None = None,
) -> None:
    """Insert a new job with status=queued.

    original_filename (EB-274) is the user's uploaded filename, used later by
    the download endpoint to set Content-Disposition. Optional for backward
    compat with pre-EB-274 callers and pre-migration DB rows.

    EB-324 additions:
        parent_job_id: when this job is a re-convert child, the originating
            parent's job_id. NULL for top-level uploads.
        token_hash_hex: for premium re-convert children, hex-encoded
            HMAC-SHA256 digest of the consumed token. Persisted so that
            token_store.refund_token() can locate the originating token if
            this child fails. NULL for free jobs and parent uploads.
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
                 created_at, expires_at, original_filename,
                 parent_job_id, token_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, STATUS_QUEUED, tier, input_fmt, output_fmt, temp_dir, input_path,
             now, now + ttl, original_filename,
             parent_job_id, token_hash_hex),
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


# ---------------------------------------------------------------------------
# EB-324: parent/child re-convert and Send-to-Kindle delivery helpers
# ---------------------------------------------------------------------------


def list_children(parent_job_id: str, db_path: Path | None = None) -> list[dict]:
    """Return all re-convert child jobs for a given parent, oldest first.

    Used by the extended GET /status/{job_id} response (Unit 5) so the result
    page can render each child's progress in the action cluster. Empty list
    when the parent has no children (the common case).
    """
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE parent_job_id = ? ORDER BY created_at ASC",
            (parent_job_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_kindle_delivery_status(
    job_id: str,
    status: str,
    db_path: Path | None = None,
) -> None:
    """Set the Send-to-Kindle delivery status on a job row.

    Called from /send-to-kindle when Resend accepts the request (status=
    'accepted_by_resend') and from /webhooks/resend (Unit 10) when delivery
    events arrive ('delivered_to_mail_server', 'bounced', 'failed',
    'delivery_delayed'). The webhook handler is responsible for idempotency
    semantics (e.g., ignoring 'delivery_delayed' arriving after 'delivered').
    """
    with _get_conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET kindle_delivery_status = ? WHERE job_id = ?",
            (status, job_id),
        )


def find_by_resend_message_id(
    resend_message_id: str,
    db_path: Path | None = None,
) -> dict | None:
    """Return the job whose resend_message_id matches, or None.

    Used by /webhooks/resend (Unit 10) to correlate inbound Svix-signed
    delivery events back to the originating Send-to-Kindle send. Returns
    None when the message_id has no matching job — typically because the
    job's row was already TTL-swept, or because Resend is retrying a
    webhook after the column was overwritten by a later send attempt
    (Wave 1 stores latest-send-only per the `resend_message_id` semantics
    decision in the plan).
    """
    if not resend_message_id:
        return None
    with _get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE resend_message_id = ?",
            (resend_message_id,),
        ).fetchone()
    return dict(row) if row else None


def set_resend_message_id(
    job_id: str,
    resend_message_id: str,
    db_path: Path | None = None,
) -> None:
    """Persist the Resend-issued message_id on the job after a successful send.

    Stored so Unit 10's webhook handler can correlate inbound delivery events
    back to the originating job via find_by_resend_message_id().
    """
    with _get_conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET resend_message_id = ? WHERE job_id = ?",
            (resend_message_id, job_id),
        )


def find_by_resend_message_id(
    resend_message_id: str,
    db_path: Path | None = None,
) -> dict | None:
    """Reverse-lookup a job by its stored Resend message_id, or None.

    Used by Unit 10's /webhooks/resend handler to find which job a delivery
    event refers to. Returns at most one row (resend_message_id is unique
    per send because Resend generates a fresh UUID per outbound message),
    but the index does NOT enforce uniqueness — multiple NULL rows must
    coexist for jobs that never invoked Send-to-Kindle.
    """
    with _get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE resend_message_id = ?",
            (resend_message_id,),
        ).fetchone()
    return dict(row) if row else None
