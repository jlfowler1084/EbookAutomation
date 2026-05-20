"""POST /send-to-kindle/{job_id} — EB-324 Unit 4 (minimal scope).

This route emails the EPUB output of a completed conversion to a user's
Kindle inbox via Resend. The minimal-scope landing covers the two
load-bearing invariants from the PR #141 reviewer:

  1. **Atomic idempotency claim.** Two simultaneous POSTs for the same
     ``(job_id, recipient_hash)`` MUST NOT both reach Resend. The PRIMARY
     KEY on ``kindle_send_idempotency`` is the race-gate.

  2. **No recipient in logs on failure.** Every Resend failure surfaces as
     a ``KindleSendError`` (see email_client.py) whose ``repr`` carries no
     recipient. The handler logs only the sanitized error.

Plan scenarios NOT yet covered (deferred to a follow-up scenario suite):
  - 30 MB size cap (R3.3)
  - Strict kindle.com / free.kindle.com domain allowlist (R3.1)
  - Display-name + plus-aliasing rejection (R3.4)
  - Format allowlist enforcement beyond a basic EPUB check (R3.3)
  - Output-path filesystem-boundary check (P1-4 hardening)
  - Telemetry emission (Unit 9b)
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException

from web_service import email_client, job_store
from web_service.config import get_settings
from web_service.job_store import STATUS_DONE

log = logging.getLogger(__name__)
router = APIRouter()

# The 60-second idempotency window: a retry within the window for the same
# (job_id, recipient_hash) returns "already_sent" without invoking Resend.
# After the window elapses, the opportunistic DELETE in _try_claim prunes
# the stale row so the next attempt is allowed to re-send.
_IDEMPOTENCY_WINDOW_SECONDS = 60


def _now() -> int:
    """Module-level time helper so tests can patch the clock without mocking
    sqlite3 or threading concerns. Always returns an integer epoch second.
    """
    return int(time.time())


@router.post("/send-to-kindle/{job_id}", status_code=200)
def send_to_kindle(
    job_id: str,
    recipient: str = Form(...),
) -> dict:
    settings = get_settings()

    # Feature gate: the minimal route lacks domain allowlist, size cap, and
    # output-path boundary checks. Production keeps this dark until the
    # validation suite lands. Override per-deploy via WEB_SEND_TO_KINDLE_ENABLED.
    if not settings.send_to_kindle_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Send-to-Kindle is not enabled for this deployment",
                "code": "SERVICE_DISABLED",
            },
        )

    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "Job not found", "code": "JOB_NOT_FOUND"},
        )
    if job["status"] != STATUS_DONE:
        raise HTTPException(
            status_code=422,
            detail={"error": "Job is not done", "code": "INVALID_JOB_STATE"},
        )
    output_path_str = job.get("output_path")
    if not output_path_str:
        raise HTTPException(
            status_code=410,
            detail={"error": "Output not available", "code": "OUTPUT_EXPIRED"},
        )
    output_path = Path(output_path_str)
    if not output_path.exists():
        raise HTTPException(
            status_code=410,
            detail={"error": "Output file no longer on disk", "code": "OUTPUT_EXPIRED"},
        )

    # Normalize: strip + lowercase. Full RFC-5322 + domain allowlist is a
    # follow-up scenario; for the minimal claim/log-leak tests the recipient
    # only needs to be a deterministic key.
    normalized = recipient.strip().lower()
    if not normalized:
        raise HTTPException(
            status_code=422,
            detail={"error": "Recipient is required", "code": "MISSING_RECIPIENT"},
        )

    recipient_hash = hashlib.sha256(normalized.encode("utf-8")).digest()

    # Atomic claim — PRIMARY KEY collision is how concurrent requests learn
    # someone already sent. Returns "already_sent" without invoking Resend.
    claim_outcome = _try_claim(job_id=job_id, recipient_hash=recipient_hash)
    if claim_outcome == "already_sent":
        return {"status": "already_sent"}

    # The claim succeeded → we own the send. Call Resend, then mark the row
    # 'sent' on success; on failure delete the claim so the user can retry.
    try:
        result = email_client.send_with_attachment(
            from_addr=settings.send_to_kindle_from,
            to=[normalized],
            subject="Your EPUB from leafbind",
            html="<p>Your converted ebook is attached. Forward this to your "
                 "Kindle to add it to your library.</p>",
            attachments=[
                {
                    "filename": output_path.name,
                    "content": output_path.read_bytes(),
                }
            ],
        )
    except email_client.KindleSendError as exc:
        _release_claim(job_id=job_id, recipient_hash=recipient_hash)
        # exc.code and exc.http_status are sanitized — no recipient in repr.
        log.warning(
            "Send-to-Kindle send failed for job %s: code=%s http_status=%s",
            job_id, exc.code, exc.http_status,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Send failed; please retry", "code": "SEND_FAILED"},
        )
    except Exception as exc:
        # Defense in depth: email_client is contracted to raise only
        # KindleSendError, but we still don't trust that contract — if a
        # future change leaks a raw resend exception, the route MUST NOT
        # let the recipient surface via the exception repr/traceback. Log
        # only the error CLASS name (which is part of the SDK's namespace,
        # never PII), never str(exc) (which could contain response body
        # snippets in some SDK versions).
        _release_claim(job_id=job_id, recipient_hash=recipient_hash)
        log.warning(
            "Send-to-Kindle send raised an un-translated exception for job %s: "
            "class=%s — email_client.send_with_attachment should have caught this",
            job_id, exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Send failed; please retry", "code": "SEND_FAILED"},
        )

    _mark_claim_sent(job_id=job_id, recipient_hash=recipient_hash)
    # Persist the Resend message_id on the job for Unit 10's webhook
    # correlation. Failure to persist isn't fatal — log and continue.
    try:
        _persist_resend_message_id(job_id, result.message_id)
    except Exception:
        log.exception(
            "Could not persist resend_message_id for job %s — webhook "
            "correlation will be degraded for this send",
            job_id,
        )

    return {"status": "sent"}


def _try_claim(*, job_id: str, recipient_hash: bytes) -> str:
    """Attempt an atomic claim row. Returns 'claimed' or 'already_sent'.

    The BEGIN IMMEDIATE / DELETE-expired / INSERT shape mirrors
    token_store.validate_and_consume (line 374-385). The opportunistic
    DELETE removes rows older than the idempotency window so a retry
    after the window elapses is allowed to re-send (plan line 422).
    PRIMARY KEY violation -> sqlite3.IntegrityError -> caller treats as
    "someone else owns this send."
    """
    settings = get_settings()
    now = _now()
    expiry_cutoff = now - _IDEMPOTENCY_WINDOW_SECONDS

    conn = sqlite3.connect(str(settings.db_path))
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Sweep expired claims first — both stale 'claimed' rows from
            # workers that crashed mid-send AND old 'sent' rows whose 60s
            # window has elapsed. Idempotent: DELETE on no matching rows is
            # a no-op.
            conn.execute(
                "DELETE FROM kindle_send_idempotency WHERE sent_at < ?",
                (expiry_cutoff,),
            )
            conn.execute(
                "INSERT INTO kindle_send_idempotency "
                "(job_id, recipient_hash, sent_at, claim_state) "
                "VALUES (?, ?, ?, 'claimed')",
                (job_id, recipient_hash, now),
            )
            conn.commit()
            return "claimed"
        except sqlite3.IntegrityError:
            conn.rollback()
            return "already_sent"
    finally:
        conn.close()


def _mark_claim_sent(*, job_id: str, recipient_hash: bytes) -> None:
    settings = get_settings()
    conn = sqlite3.connect(str(settings.db_path))
    try:
        conn.execute(
            "UPDATE kindle_send_idempotency SET claim_state='sent' "
            "WHERE job_id = ? AND recipient_hash = ?",
            (job_id, recipient_hash),
        )
        conn.commit()
    finally:
        conn.close()


def _release_claim(*, job_id: str, recipient_hash: bytes) -> None:
    """Delete a 'claimed' row after the Resend send failed."""
    settings = get_settings()
    conn = sqlite3.connect(str(settings.db_path))
    try:
        conn.execute(
            "DELETE FROM kindle_send_idempotency "
            "WHERE job_id = ? AND recipient_hash = ? AND claim_state = 'claimed'",
            (job_id, recipient_hash),
        )
        conn.commit()
    finally:
        conn.close()


def _persist_resend_message_id(job_id: str, message_id: str) -> None:
    """Persist the Resend message id AND set kindle_delivery_status to the
    immediate-post-accept baseline. Unit 10's webhook handler transitions
    this field on subsequent delivery events (delivered/bounced/failed/delayed).
    """
    settings = get_settings()
    conn = sqlite3.connect(str(settings.db_path))
    try:
        conn.execute(
            "UPDATE jobs SET resend_message_id = ?, kindle_delivery_status = ? "
            "WHERE job_id = ?",
            (message_id, "accepted_by_resend", job_id),
        )
        conn.commit()
    finally:
        conn.close()
