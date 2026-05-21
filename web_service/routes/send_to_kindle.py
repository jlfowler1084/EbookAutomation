"""POST /send-to-kindle/{job_id} — EB-324 Unit 4.

Emails the EPUB output of a completed conversion to a user's Kindle inbox
via Resend. Behind ``WEB_SEND_TO_KINDLE_ENABLED`` feature flag (default
false); production deploys flip the flag per-deploy once the remaining
Ops pre-enable items (Resend domain + API key + Cloudflare WAF rule) are
provisioned.

Request pipeline:

    feature-flag gate          → 503 SERVICE_DISABLED if off
    parent existence + done    → 404 / 422
    output file on disk        → 410 OUTPUT_EXPIRED
    validate_kindle_recipient  → 422 INVALID_RECIPIENT_FORM / _DOMAIN
    validate_kindle_format     → 422 FORMAT_NOT_KINDLE_ELIGIBLE
    validate_kindle_attachment_size → 422 OUTPUT_TOO_LARGE_FOR_KINDLE
    P1-4 path-boundary check   → 500 + kindle_send_invariant_violation
    atomic SQLite claim        → 200 already_sent if duplicate in 60s
    email_client.send_with_attachment
       success                 → 200 sent + persist resend_message_id +
                                 kindle_delivery_status=accepted_by_resend
       KindleSendError         → 502 SEND_FAILED + delete claim row
       any other Exception     → 502 SEND_FAILED + delete claim row
                                 (defense-in-depth; wrapper contract failure)

Privacy invariants enforced through this pipeline:

  1. **Atomic idempotency claim** (PRIMARY KEY on ``kindle_send_idempotency``):
     two simultaneous POSTs for the same (job_id, recipient_hash) cannot
     both reach Resend.
  2. **No recipient in logs on failure**: every send error surfaces as a
     sanitized ``KindleSendError`` (see ``email_client.py``); route logs
     only the error class + code, never ``str(exc)``.
  3. **Output-path filesystem-boundary check (P1-4)**: a corrupted
     ``output_path`` row can't redirect Resend to read ``/etc/web_service.env``
     because ``Path.resolve()`` + ``is_relative_to(settings.temp_dir)``
     refuses anything outside the expected hierarchy.
  4. **Recipient never stored plaintext**: SHA-256 hash is the
     ``kindle_send_idempotency`` PRIMARY KEY component.

Out of this PR's scope (deferred):
  - Signed-event e2e test (``tests/test_web_send_to_kindle_signed.py``)
  - Manual smoke script (``tools/verify_send_to_kindle.ps1``)
  - Server-side ``send_to_kindle_*`` telemetry emits (Unit 9b)
  - Production Resend / Cloudflare provisioning (Ops)
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request

from web_service import email_client, job_store, recovery_events_store, validation
from web_service.config import get_settings
from web_service.job_store import STATUS_DONE
from web_service.rate_limit import kindle_job_id_key, limiter

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
@limiter.limit("10/minute")
@limiter.limit("3/minute", key_func=kindle_job_id_key)
def send_to_kindle(
    request: Request,
    job_id: str,
    recipient: str = Form(...),
) -> dict:
    settings = get_settings()

    # Feature gate: the validation suite has landed, but production deploys
    # stay dark until Ops provisions the Resend domain + API key + Cloudflare
    # WAF rule and explicitly flips the per-deploy flag.
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

    # ---- Validation pipeline (R3.1 + R3.3 + R3.4 + P1-4) ----
    #
    # Order: cheap parse/equality checks first; filesystem cost (stat,
    # resolve) last. Each block maps a validator failure to its canonical
    # HTTPException code so the frontend can render targeted error copy.

    recipient_result = validation.validate_kindle_recipient(recipient)
    if not recipient_result.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "error": recipient_result.message,
                "code": recipient_result.code.value,
            },
        )
    normalized = recipient_result.normalized

    format_result = validation.validate_kindle_format(job["output_fmt"])
    if not format_result.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "error": format_result.message,
                "code": format_result.code.value,
            },
        )

    size_result = validation.validate_kindle_attachment_size(output_path.stat().st_size)
    if not size_result.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "error": size_result.message,
                "code": size_result.code.value,
            },
        )

    # P1-4 hardening: resolve output_path and assert it lives inside
    # settings.temp_dir. A corrupted output_path row (e.g., from a future
    # SQL-injection in another route) could otherwise redirect Resend to
    # read /etc/web_service.env and exfiltrate API keys via the attachment.
    # Treats both paths as resolved (symlink-aware) before comparison.
    try:
        resolved_output = output_path.resolve(strict=True)
        resolved_temp = settings.temp_dir.resolve(strict=False)
        if not resolved_output.is_relative_to(resolved_temp):
            raise ValueError("output_path escapes temp_dir hierarchy")
    except (OSError, ValueError) as exc:
        log.error(
            "Kindle send invariant violation: output_path for job %s does not "
            "resolve inside temp_dir (%s). Refusing to send.",
            job_id, exc,
        )
        try:
            recovery_events_store.log_event(
                "kindle_send_invariant_violation",
                details={
                    "job_id": job_id,
                    "reason": "output_path_outside_temp_dir",
                },
            )
        except Exception:
            log.exception(
                "Could not record kindle_send_invariant_violation telemetry"
            )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Output path failed integrity check",
                "code": "KINDLE_SEND_INVARIANT_VIOLATION",
            },
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
