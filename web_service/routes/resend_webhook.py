"""POST /webhooks/resend — EB-324 Unit 10 (Resend delivery webhook).

Receives Svix-signed events from Resend when a previously-sent email
transitions through delivery states. Verifies the signature, correlates
the event back to the originating job via `resend_message_id`, updates
`kindle_delivery_status`, and emits graded `send_to_kindle_*` telemetry.

Privacy invariants enforced here:
  - Raw payloads are NEVER logged.
  - The recipient address (`data.to[]` or substrings inside
    `bounce.message`) MUST NOT appear in any log record or in the
    telemetry details dict — the route scrubs it via _scrub_address
    before logging or emitting.
  - On unknown message_id (e.g., job already TTL-swept), 200 OK with a
    warning logged by message_id only, never by recipient.

Idempotency / out-of-order invariants:
  - Resend may retry on 4xx/5xx, so any error other than signature
    failure must return 200 to stop retries.
  - Terminal delivery states (delivered_to_mail_server / bounced /
    failed) stick — out-of-order `delivery_delayed` events arriving
    after a terminal state are logged and ignored.

WARNING: Like the Stripe webhook, this route requires raw request body
for signature validation. Do NOT add middleware upstream that consumes
`request.stream()`. The current middleware stack (CORSMiddleware) is
header-only and safe.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from web_service import job_store, recovery_events_store
from web_service.config import get_settings

log = logging.getLogger(__name__)
router = APIRouter()

# Terminal delivery states: once kindle_delivery_status reaches one of
# these, an out-of-order `delivery_delayed` event arriving afterward must
# NOT regress the state. Resend webhooks are not guaranteed in-order.
_TERMINAL_STATES: frozenset[str] = frozenset({
    "delivered_to_mail_server",
    "bounced",
    "failed",
})

# Resend event_type → (kindle_delivery_status value, telemetry event_type)
_EVENT_MAP: dict[str, tuple[str, str]] = {
    "email.delivered":        ("delivered_to_mail_server", "send_to_kindle_delivered_to_mail_server"),
    "email.bounced":          ("bounced",                  "send_to_kindle_bounced"),
    "email.failed":           ("failed",                   "send_to_kindle_delivery_failed"),
    "email.delivery_delayed": ("delivery_delayed",         "send_to_kindle_delivery_delayed"),
}

# Pattern for stripping email-like substrings out of any text headed for
# logs or telemetry details. Conservative — anything that looks like an
# address with @ gets replaced with `[redacted]`.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _scrub_address(text: str | None) -> str | None:
    """Replace any email-like substring with '[redacted]' so the recipient
    can't leak through bounce reasons / failure messages.
    """
    if not text:
        return text
    return _EMAIL_RE.sub("[redacted]", text)


@router.post("/webhooks/resend")
async def resend_webhook(request: Request) -> dict:
    """Handle a Svix-signed Resend webhook event.

    Returns 200 for handled events, unknown event types, unknown
    message_ids, duplicate events, and out-of-order arrivals so Resend
    stops retrying. Returns 401 for missing/invalid signatures (Svix
    convention) and 400 for malformed payloads.
    """
    settings = get_settings()
    secret = settings.resend_webhook_secret

    # ── Step 1: read raw body BEFORE parsing for Svix verify. ───────────
    raw_body = await request.body()
    headers = dict(request.headers)

    # Svix headers are commonly lowercased by ASGI, but defend against
    # both cases since requests can vary.
    svix_id = headers.get("svix-id") or headers.get("Svix-Id")
    svix_timestamp = headers.get("svix-timestamp") or headers.get("Svix-Timestamp")
    svix_signature = headers.get("svix-signature") or headers.get("Svix-Signature")
    if not (svix_id and svix_timestamp and svix_signature):
        log.warning("Resend webhook rejected: missing Svix signature headers")
        raise HTTPException(status_code=401, detail="Missing Svix signature headers")

    # ── Step 2: verify signature. ────────────────────────────────────────
    try:
        from svix.webhooks import Webhook, WebhookVerificationError
    except ImportError:
        log.error(
            "svix package is not installed — install with `pip install svix`. "
            "The webhook handler cannot verify signatures without it."
        )
        raise HTTPException(status_code=500, detail="Webhook verification unavailable")

    webhook = Webhook(secret)
    try:
        # svix.verify returns the parsed payload dict on success.
        payload = webhook.verify(raw_body, headers)
    except WebhookVerificationError as exc:
        # Log the class name only — never the raw signature bytes.
        log.warning(
            "Resend webhook rejected: signature verification failed (%s)",
            exc.__class__.__name__,
        )
        raise HTTPException(status_code=401, detail="Invalid Svix signature")

    # ── Step 3: shape validation. ────────────────────────────────────────
    event_type = payload.get("type") if isinstance(payload, dict) else None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not event_type or not isinstance(data, dict):
        log.warning(
            "Resend webhook payload missing 'type' or 'data' (svix_id=%s)",
            svix_id,
        )
        raise HTTPException(status_code=400, detail="Malformed webhook payload")

    message_id = data.get("email_id")
    if not message_id:
        log.warning(
            "Resend webhook payload missing data.email_id (svix_id=%s type=%s)",
            svix_id, event_type,
        )
        raise HTTPException(status_code=400, detail="Missing data.email_id")

    # ── Step 4: unknown event types → 200 no-op. ─────────────────────────
    if event_type not in _EVENT_MAP:
        log.info(
            "Resend webhook: ignoring event_type=%s (svix_id=%s)",
            event_type, svix_id,
        )
        return {"received": True, "handled": False, "reason": "unknown_event_type"}

    new_status, telemetry_event = _EVENT_MAP[event_type]

    # ── Step 5: correlate to job. ────────────────────────────────────────
    job = job_store.find_by_resend_message_id(message_id)
    if job is None:
        # Unknown message_id — log by message_id ONLY (never by recipient).
        log.warning(
            "Resend webhook for unknown message_id=%s (svix_id=%s event_type=%s) — "
            "job may have been TTL-swept or overwritten by a later send",
            message_id, svix_id, event_type,
        )
        return {"received": True, "handled": False, "reason": "unknown_message_id"}

    job_id = job["job_id"]
    current_status = job.get("kindle_delivery_status")

    # ── Step 6: idempotency + out-of-order guards. ───────────────────────
    if current_status == new_status:
        # Duplicate event — Resend retried after our 200 was delayed.
        # Treat as no-op (no telemetry re-emit).
        log.info(
            "Resend webhook idempotent no-op: job=%s already at status=%s",
            job_id, new_status,
        )
        return {"received": True, "handled": True, "transition": None}

    if event_type == "email.delivery_delayed" and current_status in _TERMINAL_STATES:
        # Out-of-order: terminal state must not regress.
        log.info(
            "Resend webhook out-of-order: ignoring delivery_delayed for job=%s "
            "already at terminal status=%s",
            job_id, current_status,
        )
        return {"received": True, "handled": False, "reason": "out_of_order_after_terminal"}

    # ── Step 7: update status + emit telemetry. ──────────────────────────
    job_store.update_kindle_delivery_status(job_id, new_status)

    telemetry_details: dict[str, Any] = {
        "job_id": job_id,
        "message_id": message_id,
        "previous_status": current_status,
        "new_status": new_status,
    }

    # Bounce subtype: surface in telemetry for dashboards. Scrub the human
    # message in case Resend echoed the recipient.
    if event_type == "email.bounced":
        bounce = data.get("bounce")
        if isinstance(bounce, dict):
            telemetry_details["bounce_type"] = bounce.get("type")
            telemetry_details["bounce_subtype"] = bounce.get("subType")
            telemetry_details["bounce_message"] = _scrub_address(bounce.get("message"))

    # Failure reason: Resend sometimes echoes recipient in `failed.reason`.
    if event_type == "email.failed":
        failed = data.get("failed")
        if isinstance(failed, dict):
            telemetry_details["failure_reason"] = _scrub_address(failed.get("reason"))

    try:
        recovery_events_store.log_event(telemetry_event, details=telemetry_details)
    except Exception:
        # Telemetry must never block the webhook return path; Resend would
        # retry on 5xx and we'd double-update the status.
        log.exception(
            "Telemetry log_event failed for job=%s event_type=%s",
            job_id, event_type,
        )

    return {"received": True, "handled": True, "transition": new_status}
