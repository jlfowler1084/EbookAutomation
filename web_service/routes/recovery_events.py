"""POST /api/recovery-events/recover-view — Next.js page-load event log (EB-292).

Tiny endpoint that lets the `/recover` Next.js page report what state the
user arrived in (localStorage empty / has_tokens / has_expired_tokens /
invalid). Combined with the api_recover_post and payment_success_revisit
events, this gives the operator a 30-60 day picture of how much real
recovery-rail usage Phase 2 sees.

The endpoint accepts a small JSON body, validates the state value against a
whitelist, and writes one event row via recovery_events_store.log_event().
Returns 204 unconditionally — failures are absorbed inside the store
(fire-and-forget) so a busted instrumentation endpoint can never block the
user's recovery flow.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Body
from fastapi.responses import Response

from web_service import job_queue, recovery_events_store

log = logging.getLogger(__name__)

router = APIRouter()

# Whitelist of accepted localStorage_state values reported by RecoverClient.tsx.
# Anything outside this set is recorded as "unknown" so we still see traffic
# but the dataset stays clean.
_VALID_STATES: frozenset[str] = frozenset({
    "empty",
    "has_tokens",
    "has_expired_tokens",
    "invalid",
    "unavailable",  # localStorage threw (incognito, SSR, ITP, etc.)
})


@router.post("/api/recovery-events/recover-view", status_code=204)
async def log_recover_view(
    payload: dict = Body(default_factory=dict),
) -> Response:
    """Log a recover_page_view event with the user's localStorage state.

    Body shape: `{"localStorage_state": "<state>"}`. Unknown or missing
    state values are recorded as "unknown" rather than rejected.

    Always returns 204 No Content. Storage failures are absorbed by
    recovery_events_store.log_event() (fire-and-forget).
    """
    raw_state = payload.get("localStorage_state") if isinstance(payload, dict) else None
    if isinstance(raw_state, str) and raw_state in _VALID_STATES:
        state = raw_state
    else:
        state = "unknown"

    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            job_queue.billing_executor,
            recovery_events_store.log_event,
            "recover_page_view",
            {"localStorage_state": state},
        )
    except Exception as exc:
        # Should be unreachable — log_event swallows its own errors. Defence in depth.
        log.warning("recovery_events: failed to dispatch log_event err=%r", exc)

    return Response(status_code=204)
