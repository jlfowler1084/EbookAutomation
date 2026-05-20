"""Resend SDK wrapper for Send-to-Kindle (EB-324 Unit 4).

Provides a single entry point — ``send_with_attachment`` — that calls the
Resend Python SDK and translates every failure mode into a sanitized
``KindleSendError``. The translation is load-bearing for the P1-3 privacy
guard: the route handler's failure log MUST NOT contain the recipient
address. By keeping the address inside the wrapper and re-raising an
exception whose ``args`` and ``__str__`` only carry an error code +
non-sensitive context, we make it impossible for an uncaught Resend error
or a logged exception to leak the address.

Layered defenses against leaking the recipient (test_no_recipient_in_logs
plus test_kindle_send_error_has_no_context_or_cause):
  1. ``KindleSendError.__init__`` never accepts or stores the recipient.
  2. Every raise inside an ``except`` block uses ``from None`` to suppress
     Python's implicit ``__context__`` chaining. Without ``from None``,
     the original Resend exception (which can carry a response body
     containing the recipient) survives in the chain even though we never
     wrote ``from exc`` — a subtle distinction that the F4 review caught.
  3. The wrapper logs only the error code + class name, never the body
     of the underlying Resend response.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SendResult:
    """Outcome of a successful Resend send.

    message_id: The Resend-issued ID for the outbound email — persisted on
        the job row for webhook correlation (Unit 10). Never PII.
    """
    message_id: str


class KindleSendError(Exception):
    """Sanitized translation of any Resend send failure.

    ``code`` is a short machine-friendly label (e.g., 'RESEND_HTTP_ERROR',
    'RESEND_EXCEPTION', 'INVALID_RESEND_RESPONSE'). ``str(err)`` and
    ``err.args`` MUST contain no recipient address — the route's logging
    is allowed to call repr on this exception without privacy risk.
    """

    def __init__(self, code: str, *, http_status: int | None = None) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(f"KindleSendError({code})")


def send_with_attachment(
    *,
    from_addr: str,
    to: list[str],
    subject: str,
    html: str,
    attachments: list[dict[str, Any]],
) -> SendResult:
    """Send a single email with one or more attachments via Resend.

    The Resend SDK is imported lazily so any test that imports this module
    but never calls send_with_attachment doesn't need the SDK installed.

    Args:
        from_addr: Verified Resend sender address (the configured
            ``WEB_SEND_TO_KINDLE_FROM``).
        to: Single-element list with the normalized recipient. Passed
            through unchanged to Resend — the wrapper does NOT log it.
        subject: Plain-text subject line.
        html: HTML body. Resend requires either html or text; we send html.
        attachments: List of dicts with at least ``filename`` and
            ``content`` (bytes) keys. Resend expects base64-encoded content
            on the wire, but the SDK handles encoding when ``content`` is
            bytes-like.

    Returns:
        SendResult with the Resend-issued message_id.

    Raises:
        KindleSendError: any failure to hand the message to Resend. The
            error's repr is sanitized — no recipient or raw response body.
    """
    # Import the SDK with explicit error capture. The raise happens OUTSIDE
    # the except block so Python's implicit __context__ chain stays None
    # (per the F4 finding — `from None` alone only sets __suppress_context__,
    # it does NOT clear __context__ when the raise is lexically inside an
    # except block).
    resend_module = None
    sdk_missing = False
    try:
        import resend as resend_module  # local import: keeps test import-cost minimal
    except ImportError as exc:
        log.error(
            "Resend SDK is not installed — install with `pip install resend`. "
            "Underlying error class: %s",
            exc.__class__.__name__,
        )
        sdk_missing = True
    if sdk_missing:
        raise KindleSendError("RESEND_SDK_NOT_INSTALLED") from None

    # Wire the per-deploy API key to the Resend module-level attribute. The
    # SDK reads resend.api_key inside Emails.send; without this assignment
    # the call falls back to None and Resend rejects with an auth error.
    # Re-setting on every call is cheap and keeps the wrapper stateless
    # against environment-variable rotations.
    from web_service.config import get_settings as _get_settings
    resend_module.api_key = _get_settings().resend_api_key

    # Resend's local-attachment contract is Base64-encoded string content; the
    # 40 MB limit is measured AFTER encoding. The Python SDK does NOT
    # auto-encode raw bytes — passing bytes either fails or corrupts the
    # attachment. Encode here so callers can hand us raw bytes from
    # Path.read_bytes() without thinking about the wire format.
    encoded_attachments: list[dict[str, Any]] = []
    for att in attachments:
        att_out = dict(att)
        content = att_out.get("content")
        if isinstance(content, bytes):
            att_out["content"] = base64.b64encode(content).decode("ascii")
        encoded_attachments.append(att_out)

    payload: dict[str, Any] = {
        "from": from_addr,
        "to": to,
        "subject": subject,
        "html": html,
        "attachments": encoded_attachments,
    }

    # Same pattern as the import block: capture the failure condition inside
    # the except, exit the block, then raise outside so __context__ is None.
    response: Any = None
    send_error: Exception | None = None
    try:
        response = resend_module.Emails.send(payload)
    except Exception as exc:
        send_error = exc
    if send_error is not None:
        log.warning(
            "Send-to-Kindle delivery to Resend failed: error_class=%s",
            send_error.__class__.__name__,
        )
        raise KindleSendError("RESEND_EXCEPTION") from None

    message_id = _extract_message_id(response)
    if not message_id:
        log.warning("Resend returned a 2xx response without a usable message id")
        # No active exception here — plain `from None` suffices to clear __cause__.
        raise KindleSendError("INVALID_RESEND_RESPONSE") from None

    return SendResult(message_id=message_id)


def _extract_message_id(response: Any) -> str | None:
    """Pull the message_id out of a Resend response (dict or model object).

    Resend's SDK has historically returned plain dicts (`{"id": "..."}`),
    but newer versions return Pydantic-style models. Support both shapes
    without coupling to a specific SDK version.
    """
    if response is None:
        return None
    if isinstance(response, dict):
        value = response.get("id")
        return str(value) if value else None
    value = getattr(response, "id", None)
    return str(value) if value else None
