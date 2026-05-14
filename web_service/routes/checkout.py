"""POST /stripe/create-session — create a Stripe Checkout session for token pack purchase.

The endpoint accepts a `pack` form field (starter | standard | power), looks up
the corresponding pre-created Stripe Price ID from Settings, and delegates to
the Stripe Checkout API to return a hosted payment URL.

Key design decisions (from Phase 2 plan, Unit 3):
- Stored Price IDs (env vars) over inline price_data — avoids mismatched currencies
  and tax settings; idempotent re-runs against the same Price object.
- customer_creation="if_required" — guest checkout, no mandatory Stripe Customer
  object. Reduces friction for one-off purchases.
- receipt_email=None in payment_intent_data — privacy: disables automatic Stripe
  receipts. Users get tokens delivered by us, not Stripe's receipt email.
- payment_intent_data.metadata.pack seeded here. Unit 4 webhook handler will
  call stripe.PaymentIntent.modify() on checkout.session.completed to add
  checkout_session_id to the PaymentIntent metadata, completing the chain.
- Stripe SDK calls are blocking — run in billing_executor (ThreadPoolExecutor)
  to avoid blocking the asyncio event loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time

import stripe
from fastapi import APIRouter, Form, HTTPException, Request

from web_service.config import get_settings
from web_service.job_queue import billing_executor

log = logging.getLogger(__name__)

router = APIRouter()

# Maps the pack name received from the client to the Settings field name
# that holds the corresponding Stripe Price ID.
_PACK_TO_PRICE_KEY: dict[str, str] = {
    "starter": "stripe_price_starter",
    "standard": "stripe_price_standard",
    "power": "stripe_price_power",
}

# EB-227: idempotency-key time bucket. A 30s window de-duplicates rapid
# double-clicks from the same client without colliding distinct purchases.
_IDEMPOTENCY_BUCKET_SECONDS = 30


def _derive_idempotency_key(pack: str, client_host: str) -> str:
    """Return a stable Stripe idempotency key for the current logical request.

    Key shape: SHA256(pack:client_host:30s-time-bucket), truncated to 32 hex
    chars. Same (pack, client_host) within a 30s window resolves to the same
    key — Stripe will then return the existing Session URL instead of creating
    a duplicate one on a client double-click or network retry.
    """
    bucket = int(time.time() // _IDEMPOTENCY_BUCKET_SECONDS)
    seed = f"{pack}:{client_host}:{bucket}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


@router.post("/stripe/create-session", status_code=200)
async def create_checkout_session(
    request: Request,
    pack: str = Form(...),
) -> dict:
    """Create a Stripe Checkout session for the requested token pack.

    Args:
        request: FastAPI Request — used to derive a per-client idempotency key.
        pack: One of "starter", "standard", or "power".

    Returns:
        {"checkout_url": str, "session_id": str}

    Raises:
        422 INVALID_PACK: if pack is not one of the three known values.
        503 STRIPE_API_ERROR: if the Stripe API call fails.
    """
    if pack not in _PACK_TO_PRICE_KEY:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid pack", "code": "INVALID_PACK"},
        )

    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    price_key = _PACK_TO_PRICE_KEY[pack]
    price_id = getattr(settings, price_key)

    # EB-227: derive an idempotency key from (pack, client IP, 30s bucket).
    # Stripe retains keys ≥24h; duplicate POSTs from the same client within
    # the bucket window get the existing Session URL instead of a new charge.
    client_host = request.client.host if request.client else "unknown"
    idempotency_key = _derive_idempotency_key(pack, client_host)

    loop = asyncio.get_event_loop()
    try:
        session = await loop.run_in_executor(
            billing_executor,
            lambda: stripe.checkout.Session.create(
                mode="payment",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=(
                    "https://leafbind.io/payment/success"
                    "?session_id={CHECKOUT_SESSION_ID}"
                ),
                cancel_url="https://leafbind.io/pricing",
                # Guest checkout: create a Stripe Customer only if needed
                # (e.g. if user is already logged into Stripe's portal).
                customer_creation="if_required",
                payment_intent_data={
                    # Disable automatic Stripe receipt emails — privacy policy.
                    "receipt_email": None,
                    # Seed pack metadata on the PaymentIntent for Unit 4's
                    # checkout.session.completed webhook, which will modify
                    # the PI to add checkout_session_id (completing the chain).
                    "metadata": {"pack": pack},
                },
                # Session-level metadata for Stripe Dashboard debugging.
                metadata={"pack": pack},
                idempotency_key=idempotency_key,
            ),
        )
    except stripe.error.StripeError as exc:
        log.error(
            "Stripe API error creating checkout session for pack=%r: %s",
            pack,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail={"error": "stripe upstream error", "code": "STRIPE_API_ERROR"},
        )

    log.info(
        "Created Stripe Checkout session=%s for pack=%r",
        session.id,
        pack,
    )
    return {"checkout_url": session.url, "session_id": session.id}
