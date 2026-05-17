"""POST /api/recover — server-side session_id paste-form endpoint.

This is the cross-device recovery path for users who have a Stripe receipt
email with the session_id but lost the original URL and their browser's
localStorage. The Next.js /recover UI page (Unit 7) reads localStorage
client-side; this endpoint handles the paste-form post case.

On valid session_id shape, 302-redirects to /payment/success?session_id=<id>
(the canonical recovery URL — Stripe stores completed sessions indefinitely
and our pack_id index re-renders the original tokens within the 30-day window).

EB-292: every call is logged to recovery_events_store as an
`api_recover_post` event for the 30-60 day measurement window.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import RedirectResponse

from web_service import job_queue, recovery_events_store

router = APIRouter()


def _log_event(result: str) -> None:
    """Fire-and-forget event log. Never raises — instrumentation is best-effort."""
    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            job_queue.billing_executor,
            recovery_events_store.log_event,
            "api_recover_post",
            {"result": result},
        )
    except Exception:
        # Swallow — measurement failure must not break the recovery flow.
        pass


@router.post("/api/recover")
async def recover_tokens(session_id: str = Form(...)) -> RedirectResponse:
    """Accept a Stripe session_id paste and redirect to the canonical success URL.

    Strips leading/trailing whitespace from clipboard-paste inputs.
    Validates that the session_id starts with "cs_" and has a minimum length.
    On valid input, 302-redirects to /payment/success?session_id=<id>.

    Args:
        session_id: Stripe Checkout session ID pasted by the user.

    Returns:
        302 RedirectResponse to /payment/success?session_id=<id>.

    Raises:
        422 MALFORMED_SESSION_ID: if the session_id shape is invalid.
    """
    # Strip whitespace from clipboard-paste inputs before validation
    session_id = session_id.strip()

    if not session_id.startswith("cs_") or len(session_id) < 5:
        _log_event("malformed")
        raise HTTPException(
            status_code=422,
            detail={"error": "Invalid session ID format", "code": "MALFORMED_SESSION_ID"},
        )

    # 302 to canonical recovery URL; /payment/success handles all auth/render logic
    _log_event("success")
    return RedirectResponse(
        url=f"/payment/success?session_id={session_id}",
        status_code=302,
    )
