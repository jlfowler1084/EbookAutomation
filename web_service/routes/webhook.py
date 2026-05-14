"""Stripe webhook handler.

WARNING: This route requires raw request body for signature validation.
Do NOT add middleware upstream that consumes `request.stream()`. The current
middleware stack (CORSMiddleware) is header-only and safe. A startup check in
main.py's lifespan logs WARN if any non-allowlisted middleware is added.

Handles four event types:
  - checkout.session.completed: mint tokens IFF payment_status == "paid";
    extends PaymentIntent metadata with checkout_session_id for dispute lookup.
  - checkout.session.async_payment_succeeded (EB-227): for async payment methods
    (ACH/SEPA), this is the event that fires after funds settle. Mints tokens
    using the same code path as completed-with-paid.
  - checkout.session.async_payment_failed (EB-227): async payment failed to
    settle. Logged; no token side effects.
  - charge.dispute.created: revoke all tokens for the disputed session via
    PaymentIntent metadata lookup (single-hop) with token_store fallback.

Why the payment_status guard (EB-227): checkout.session.completed fires for
async payment methods with payment_status="unpaid". Minting tokens at that
point would hand out premium access before funds capture. The async_payment_
succeeded event fires later (hours/days) with payment_status="paid" and is
what should actually trigger the mint for async flows. Sync card payments
fire completed with payment_status="paid" directly and remain unaffected.

Response policy:
  - 400 on signature/parse failure (permanent -- Stripe will not retry)
  - 500 on DB write failure (transient -- Stripe retries with exponential
    backoff for ~3 days; mint-failure recovery via failed_mints table)
  - 200 on success or idempotent no-op (Stripe stops retrying)
  - 503 if DB circuit breaker is open (transient -- Stripe retries)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time

import stripe
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from web_service import circuit_breaker, token_store
from web_service.config import get_settings
from web_service.job_queue import billing_executor

log = logging.getLogger(__name__)

router = APIRouter()

# Maps pack name to token count.
_PACK_TOKEN_COUNT: dict[str, int] = {
    "starter": 3,
    "standard": 10,
    "power": 25,
}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request) -> dict:
    """Handle incoming Stripe webhook events.

    Validates the Stripe-Signature header before processing any event data.
    Processes four event types: checkout.session.completed (paid only),
    checkout.session.async_payment_succeeded, checkout.session.async_payment_
    failed, and charge.dispute.created. All other event types return 200 with
    no side effects (Stripe stops retrying unknown events).

    Returns:
        {"received": True} on success or idempotent no-op.

    Raises:
        HTTPException(400): Invalid signature or parse failure (permanent).
        HTTPException(500): DB write failure (transient; Stripe retries).
        HTTPException(503): DB circuit breaker open (transient; Stripe retries).
    """
    # --- Circuit breaker short-circuit ---
    if circuit_breaker.circuit_is_open():
        return JSONResponse(
            status_code=503,
            content={"error": "service degraded, retry"},
        )

    # --- Read raw body (BYTES -- never use request.json()) ---
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    settings = get_settings()
    # Set Stripe API key for subsequent PaymentIntent calls in this handler.
    stripe.api_key = settings.stripe_secret_key

    # --- Signature validation ---
    # JSONDecodeError is a subclass of ValueError -- single catch covers both.
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.stripe_webhook_secret, tolerance=300
        )
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        log.warning(
            "webhook_signature_failure",
            extra={
                "source_ip": request.client.host if request.client else "unknown",
                "sig_header_prefix": sig[:40],
                "payload_len": len(payload),
                "err": str(e)[:200],
            },
        )
        raise HTTPException(400, detail={"error": "invalid signature"})

    # --- Livemode assertion (production only) ---
    if os.environ.get("APP_ENV") == "production" and not event.get("livemode"):
        log.error(
            "test_event_in_production",
            extra={"event_id": event.get("id")},
        )
        raise HTTPException(400, detail={"error": "test event in production"})

    # --- Clock drift warning (advisory, does not block processing) ---
    now = time.time()
    drift = abs(now - event.get("created", now))
    if drift > 60:
        log.warning(
            "webhook_clock_drift_warn",
            extra={"drift_seconds": drift},
        )

    # --- Defensive event parsing (use .get() everywhere -- KeyError -> 500 -> retry storm) ---
    data = event.get("data", {})
    obj = data.get("object", {})
    event_type = event.get("type", "unknown")

    loop = asyncio.get_event_loop()

    # =========================================================================
    # checkout.session.completed  +  checkout.session.async_payment_succeeded
    # =========================================================================
    # Combined branch (EB-227). For sync card payments, completed fires with
    # payment_status="paid" → mint immediately. For async methods (ACH/SEPA),
    # completed fires with payment_status="unpaid" → short-circuit; the matching
    # async_payment_succeeded event will fire later with payment_status="paid"
    # and re-enter this branch. mint_tokens_if_absent is idempotent on session_id
    # so duplicate paid events for the same session are safe.
    if event_type in (
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    ):
        session_id = obj.get("id")
        payment_intent_id = obj.get("payment_intent")
        pack = obj.get("metadata", {}).get("pack", "starter")
        count = _PACK_TOKEN_COUNT.get(pack, 0)
        payment_status = obj.get("payment_status")

        if not session_id or count == 0:
            log.warning(
                "malformed_checkout_event",
                extra={"event_id": event.get("id")},
            )
            # Return 200 to stop Stripe retries on permanently-bad events.
            return {"received": True}

        # EB-227: only mint after funds have actually captured.
        if payment_status != "paid":
            log.info(
                "checkout_session_event_not_paid",
                extra={
                    "event_id": event.get("id"),
                    "event_type": event_type,
                    "session_id": session_id,
                    "payment_status": payment_status,
                },
            )
            return {"received": True}

        try:
            # Mint tokens (idempotent -- safe to call multiple times for same session).
            await loop.run_in_executor(
                billing_executor,
                token_store.mint_tokens_if_absent,
                session_id,
                count,
                payment_intent_id,
            )

            # Extend PaymentIntent metadata with checkout_session_id so the
            # dispute handler can resolve session_id via a single PI retrieve.
            # This is Unit 4's responsibility -- Unit 3 only seeded metadata.pack
            # at session creation because session.id wasn't available yet.
            if payment_intent_id:
                try:
                    await loop.run_in_executor(
                        billing_executor,
                        lambda: stripe.PaymentIntent.modify(
                            payment_intent_id,
                            metadata={
                                "checkout_session_id": session_id,
                                "pack": pack,
                            },
                        ),
                    )
                except stripe.error.StripeError as stripe_exc:
                    # Don't fail the whole webhook on PI metadata update failure --
                    # tokens are already minted. The dispute handler has a fallback
                    # path via find_session_by_payment_intent.
                    log.error(
                        "stripe_modify_failed",
                        extra={
                            "pi_id": payment_intent_id,
                            "err": str(stripe_exc)[:200],
                        },
                    )

            circuit_breaker.db_call_succeeded()

        except sqlite3.OperationalError as db_exc:
            circuit_breaker.db_call_failed()
            log.error(
                "mint_failed",
                extra={
                    "session_id": session_id,
                    "err": str(db_exc)[:200],
                },
            )
            # Best-effort: record the failure for admin sweep / manual recovery.
            try:
                await loop.run_in_executor(
                    billing_executor,
                    token_store.record_failed_mint,
                    session_id,
                    pack,
                    str(db_exc),
                )
            except Exception as record_exc:
                log.error(
                    "record_failed_mint_error",
                    extra={"session_id": session_id, "err": str(record_exc)[:200]},
                )
            # Return 500 to trigger Stripe's free retry budget (~3 days exponential backoff).
            raise HTTPException(
                500,
                detail={"error": "transient db failure, will retry"},
            )

    # =========================================================================
    # checkout.session.async_payment_failed  (EB-227)
    # =========================================================================
    # An async payment method (ACH/SEPA) failed to settle. No tokens were minted
    # (guarded by payment_status check above), so no revocation needed. Log and
    # return 200 to stop Stripe retries.
    elif event_type == "checkout.session.async_payment_failed":
        log.warning(
            "async_payment_failed",
            extra={
                "event_id": event.get("id"),
                "session_id": obj.get("id"),
                "payment_status": obj.get("payment_status"),
            },
        )

    # =========================================================================
    # charge.dispute.created
    # =========================================================================
    elif event_type == "charge.dispute.created":
        payment_intent_id = obj.get("payment_intent")
        if not payment_intent_id:
            log.warning(
                "dispute_no_pi",
                extra={"event_id": event.get("id")},
            )
            return {"received": True}

        # Primary path: resolve session_id via PaymentIntent metadata.
        session_id = None
        try:
            pi = await loop.run_in_executor(
                billing_executor,
                lambda: stripe.PaymentIntent.retrieve(payment_intent_id),
            )
            session_id = pi.metadata.get("checkout_session_id")
        except stripe.error.StripeError as stripe_exc:
            log.warning(
                "stripe_retrieve_failed_for_dispute",
                extra={
                    "pi_id": payment_intent_id,
                    "err": str(stripe_exc)[:200],
                },
            )

        # Fallback path: look up via token_store by payment_intent_id.
        if not session_id:
            session_id = await loop.run_in_executor(
                billing_executor,
                token_store.find_session_by_payment_intent,
                payment_intent_id,
            )

        if session_id:
            try:
                await loop.run_in_executor(
                    billing_executor,
                    token_store.mark_disputed,
                    session_id,
                )
                log.info(
                    "dispute_processed",
                    extra={
                        "session_id": session_id,
                        "pi_id": payment_intent_id,
                    },
                )
                circuit_breaker.db_call_succeeded()
            except sqlite3.OperationalError as db_exc:
                circuit_breaker.db_call_failed()
                log.error(
                    "dispute_mark_failed",
                    extra={
                        "session_id": session_id,
                        "err": str(db_exc)[:200],
                    },
                )
                raise HTTPException(
                    500,
                    detail={"error": "transient db failure, will retry"},
                )
        else:
            # Neither PI metadata nor token_store fallback resolved a session_id.
            # Best-effort revocation failed -- log ERROR and return 200 to stop retries.
            log.error(
                "dispute_unresolvable",
                extra={"pi_id": payment_intent_id},
            )

    # =========================================================================
    # Unknown event type
    # =========================================================================
    else:
        # Return 200 with no side effects to stop Stripe retries on
        # unsubscribed event types. No logging needed -- this is expected.
        pass

    return {"received": True}
