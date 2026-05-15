"""Payment-flow endpoints (server-rendered HTML by FastAPI, NOT Next.js).

These endpoints are FastAPI-owned because:
1. /payment/success injects raw token strings into the response — server-side
   rendering avoids a round-trip that would expose tokens through the
   Next.js framework's client-side state. Tokens never enter a Next.js bundle.
2. /payment/cancel is a static page; trivial to render server-side.
3. /recover is split: the UI page lives in Next.js (Unit 7); only the
   FastAPI POST /api/recover endpoint (Unit 6) lives here.

Token injection uses the <script type="application/json"> two-script pattern
(NOT inline JS string interpolation) to eliminate the </script> injection
class entirely. The token alphabet is regex-constrained to [A-Za-z0-9_-]
and session_id is Stripe-issued, so injection is already very unlikely —
but type="application/json" is safe-by-default regardless and costs nothing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time

import stripe
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from html import escape

from web_service import circuit_breaker, token_store
from web_service.templates.shell import footer_html, header_html
from web_service.config import get_settings
from web_service.job_queue import billing_executor

log = logging.getLogger(__name__)

router = APIRouter()

# Maps Stripe pack name → number of tokens to mint.
_PACK_TOKEN_COUNT: dict[str, int] = {
    "starter": 3,
    "standard": 10,
    "power": 25,
}

# Security headers applied to every success/cancel response.
_PAYMENT_HEADERS: dict[str, str] = {
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "private, no-store",
}


# ---------------------------------------------------------------------------
# HTML rendering helpers
# ---------------------------------------------------------------------------

def _base_html(title: str, body: str) -> str:
    """Page shell with brand CSS, Google Fonts, and payment-flow header/footer."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '    <meta charset="utf-8">\n'
        f"    <title>{title}</title>\n"
        '    <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '    <link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader&amp;family=DM+Sans&amp;family=IBM+Plex+Mono&amp;display=swap">\n'
        '    <link rel="stylesheet" href="/static/leafbind-tokens.css">\n'
        '    <style>body{margin:0;background-color:var(--color-surface);color:var(--color-text-base);}</style>\n'
        "</head>\n"
        "<body>\n"
        + header_html()
        + '\n<main class="lb-main">\n'
        + body
        + "\n</main>\n"
        + footer_html()
        + "\n</body>\n"
        "</html>"
    )


def _render_success_page(session_id: str, tokens: list[str], expires_at: int) -> str:
    """Render the payment success page with tokens injected via JSON data block.

    IMPORTANT: tokens are embedded via <script type="application/json"> (NOT
    inline JS string interpolation). A separate <script> reads the JSON and
    writes localStorage. This eliminates the </script> injection class entirely.

    json.dumps with ensure_ascii=True escapes any unicode that might confuse
    parsers. The token alphabet is [A-Za-z0-9_-] so this is belt-and-suspenders.
    """
    token_payload = json.dumps(
        {
            "tokens": tokens,
            "session_id": session_id,
            "expires_at": expires_at,
        },
        ensure_ascii=True,
    )
    body = f"""\
    <span class="lb-eyebrow lb-eyebrow--accent">PAYMENT CONFIRMED</span>
    <h1 class="lb-display">Welcome to Leafbind.</h1>
    <aside class="lb-callout">
        <strong>Bookmark this page</strong> &mdash; it is your recovery path.
        Your tokens are stored here for 7 days. If you close this tab without
        copying them, return to this URL to see them again.
    </aside>

    <!-- Token data as JSON; parsed by sibling script. NO JS interpolation of raw values. -->
    <script type="application/json" id="leafbind-tokens">{token_payload}</script>

    <div class="lb-card lb-token-card">
        <ol id="token-list" class="lb-token-list">
            <!-- populated by the script below -->
        </ol>
    </div>

    <div class="lb-action-row">
        <button class="lb-button-primary" onclick="downloadTokens()">Download tokens.txt</button>
        <button class="lb-button-ghost" onclick="window.print()">Print</button>
    </div>

    <p class="lb-recover-row">
        <a href="/" class="lb-link">Start converting &rarr;</a>
    </p>

    <script>
    (function() {{
        const dataEl = document.getElementById('leafbind-tokens');
        const data = JSON.parse(dataEl.textContent);
        // Render tokens
        const list = document.getElementById('token-list');
        data.tokens.forEach(function(t) {{
            const li = document.createElement('li');
            li.textContent = t;
            list.appendChild(li);
        }});
        // Write to localStorage for client-side recovery (Unit 7's /recover page reads this)
        try {{
            localStorage.setItem('leafbind.tokens', JSON.stringify(data));
        }} catch (e) {{
            // Storage quota or private-mode -- silently ignore; page-level recovery still works
        }}
        // Download helper
        window.downloadTokens = function() {{
            const text = data.tokens.join('\\n') + '\\n';
            const blob = new Blob([text], {{type: 'text/plain'}});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'leafbind-tokens.txt';
            a.click();
            URL.revokeObjectURL(url);
        }};
    }})();
    </script>"""
    return _base_html("Your Leafbind Tokens", body)


def _render_expired_page(session_id: str) -> str:
    """Render the 'tokens expired' page for revisits after the 7-day window."""
    body = (
        "    <h1>Tokens Expired</h1>\n"
        '    <p style="color: #555;">Your tokens for this session have expired. '
        "Tokens are valid for 7 days from the time of purchase.</p>\n"
        "    <p>If you need assistance, please\n"
        '    <a href="/recover" style="color: #0070f3;">visit the recovery page</a>\n'
        "    or contact support.</p>\n"
        f'    <p style="color: #666; font-size: 0.85em;">Session: {escape(session_id, quote=True)}</p>\n'
        '    <p><a href="/pricing" style="color: #0070f3;">Buy new tokens &rarr;</a></p>'
    )
    return _base_html("Tokens Expired — Leafbind", body)


def _render_retry_page(session_id: str, message: str) -> str:
    """Render a 'service degraded, please retry' page with auto-reload."""
    body = (
        "    <h1>Temporarily Unavailable</h1>\n"
        f'    <p style="color: #555;">{message}</p>\n'
        "    <p>Your payment was received and your tokens are being generated. "
        "Please refresh this page in 30 seconds to see your tokens.</p>\n"
        f'    <p style="color: #666; font-size: 0.85em;">Session: {escape(session_id, quote=True)}</p>\n'
        "    <script>\n"
        "    setTimeout(function() {{ window.location.reload(); }}, 30000);\n"
        "    </script>"
    )
    return _base_html("Generating Tokens — Leafbind", body)


def _render_pending_page(session_id: str) -> str:
    """Render a 'payment not yet confirmed' page with auto-reload."""
    body = (
        "    <h1>Payment Not Yet Confirmed</h1>\n"
        '    <p style="color: #555;">Your payment is being processed by Stripe. '
        "This usually takes just a few seconds.</p>\n"
        "    <p>Please refresh this page in 30 seconds to see your tokens.</p>\n"
        f'    <p style="color: #666; font-size: 0.85em;">Session: {escape(session_id, quote=True)}</p>\n'
        "    <script>\n"
        "    setTimeout(function() {{ window.location.reload(); }}, 30000);\n"
        "    </script>"
    )
    return _base_html("Confirming Payment — Leafbind", body)


def _render_not_found_page(session_id: str) -> str:
    """Render a 404 page for session IDs that don't exist in Stripe."""
    body = (
        "    <h1>Session Not Found</h1>\n"
        '    <p style="color: #555;">We could not find a payment session matching '
        "this URL. The URL may be incorrect or the session may have expired in "
        "Stripe's records.</p>\n"
        f'    <p style="color: #666; font-size: 0.85em;">Session: {escape(session_id, quote=True)}</p>\n'
        '    <p><a href="/recover" style="color: #0070f3;">Try the recovery page</a> '
        'or <a href="/pricing" style="color: #0070f3;">buy new tokens</a>.</p>'
    )
    return _base_html("Session Not Found — Leafbind", body)


# ---------------------------------------------------------------------------
# /payment/success
# ---------------------------------------------------------------------------

@router.get("/payment/success")
async def payment_success(session_id: str) -> HTMLResponse:
    """Render the payment success page for a completed Stripe Checkout session.

    Idempotent: revisiting the same URL within the 7-day token expiry window
    re-displays the same tokens (decrypted from the DB, not re-minted).

    Flow:
    1. Validate session_id shape (must start with "cs_").
    2. Short-circuit if circuit breaker is open (503).
    3. SELECT existing tokens from DB (read-only, no mint).
    4. If tokens exist and not expired: render success page.
    5. If tokens exist but expired: render expired page.
    6. If no tokens: verify with Stripe, then mint.
    7. Handle all Stripe and DB error paths.

    Returns:
        HTMLResponse with Referrer-Policy + Cache-Control headers.
    """
    # --- Step 1: Validate session_id shape ---
    if not session_id.startswith("cs_"):
        return HTMLResponse(
            status_code=422,
            content=_base_html(
                "Invalid Session — Leafbind",
                "<h1>Invalid Session ID</h1>"
                '<p style="color: #555;">The session ID in this URL does not look valid. '
                "Stripe session IDs start with <code>cs_</code>.</p>"
                '<p><a href="/recover" style="color: #0070f3;">Try the recovery page</a></p>',
            ),
            headers={"X-Error-Code": "INVALID_SESSION_ID"},
        )

    # --- Step 2: Circuit breaker check ---
    if circuit_breaker.circuit_is_open():
        return HTMLResponse(
            status_code=503,
            content=_render_retry_page(session_id, "Service temporarily degraded"),
            headers=_PAYMENT_HEADERS,
        )

    # --- Step 3: Read-only DB lookup (idempotent revisit path) ---
    loop = asyncio.get_event_loop()

    try:
        result = await loop.run_in_executor(
            billing_executor,
            token_store.get_tokens_for_session,
            session_id,
        )
        circuit_breaker.db_call_succeeded()
    except sqlite3.OperationalError as db_exc:
        circuit_breaker.db_call_failed()
        log.error(
            "payment_success: DB read failed for session=%s err=%r",
            session_id,
            str(db_exc)[:200],
        )
        return HTMLResponse(
            status_code=503,
            content=_render_retry_page(session_id, "Database temporarily unavailable"),
            headers=_PAYMENT_HEADERS,
        )

    # --- Step 4: Tokens exist in DB ---
    if result is not None:
        tokens, expires_at = result

        # --- Step 5: Check expiry on revisit ---
        if int(time.time()) > expires_at:
            log.info(
                "payment_success: tokens expired for session=%s (expires_at=%d)",
                session_id,
                expires_at,
            )
            return HTMLResponse(
                status_code=200,
                content=_render_expired_page(session_id),
                headers=_PAYMENT_HEADERS,
            )

        log.info(
            "payment_success: cache hit for session=%s (%d tokens)", session_id, len(tokens)
        )
        return HTMLResponse(
            status_code=200,
            content=_render_success_page(session_id, tokens, expires_at),
            headers=_PAYMENT_HEADERS,
        )

    # --- Step 6: No tokens yet — verify with Stripe and mint ---
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    try:
        session = await loop.run_in_executor(
            billing_executor,
            lambda: stripe.checkout.Session.retrieve(
                session_id,
                expand=["line_items"],
            ),
        )
    except stripe.error.InvalidRequestError:
        # Session doesn't exist in Stripe (typo'd URL, cancelled session, etc.)
        log.warning(
            "payment_success: Stripe session not found: session_id=%s", session_id
        )
        return HTMLResponse(
            status_code=404,
            content=_render_not_found_page(session_id),
            headers=_PAYMENT_HEADERS,
        )
    except stripe.error.StripeError as stripe_exc:
        log.error(
            "payment_success: Stripe API error for session=%s err=%r",
            session_id,
            str(stripe_exc)[:200],
        )
        return HTMLResponse(
            status_code=503,
            content=_render_retry_page(
                session_id, "Payment verification temporarily unavailable"
            ),
            headers=_PAYMENT_HEADERS,
        )

    # Check payment_status — user may have landed here before payment completed
    if session.payment_status != "paid":
        log.info(
            "payment_success: payment_status=%r for session=%s (not yet paid)",
            session.payment_status,
            session_id,
        )
        return HTMLResponse(
            status_code=200,
            content=_render_pending_page(session_id),
            headers=_PAYMENT_HEADERS,
        )

    # Payment verified — determine pack and mint tokens
    pack = (session.metadata or {}).get("pack", "starter")
    count = _PACK_TOKEN_COUNT.get(pack, 0)
    if count == 0:
        log.error(
            "payment_success: unknown pack=%r for session=%s; defaulting to starter (3)",
            pack,
            session_id,
        )
        count = 3  # safe fallback; don't refuse to serve tokens for unknown pack name

    payment_intent_id = session.payment_intent or ""

    try:
        mint_result = await loop.run_in_executor(
            billing_executor,
            token_store.mint_tokens_if_absent,
            session_id,
            count,
            payment_intent_id,
        )
        circuit_breaker.db_call_succeeded()
    except sqlite3.OperationalError as db_exc:
        circuit_breaker.db_call_failed()
        log.error(
            "payment_success: DB mint failed for session=%s err=%r",
            session_id,
            str(db_exc)[:200],
        )
        # Best-effort: log to failed_mints so admin sweep can act
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
                "payment_success: record_failed_mint also failed: %r",
                str(record_exc)[:200],
            )
        return HTMLResponse(
            status_code=503,
            content=_render_retry_page(
                session_id,
                "Token generation temporarily failed — refresh in 30 seconds",
            ),
            headers=_PAYMENT_HEADERS,
        )

    tokens = mint_result.tokens

    # Determine expires_at for the newly minted tokens by reading back from DB
    # (mint_tokens_if_absent doesn't return expires_at in MintResult, so we use the
    # known TTL: mint_time + 7 days).
    expires_at = int(time.time()) + (7 * 24 * 3600)

    log.info(
        "payment_success: minted %d tokens for session=%s (from_cache=%s)",
        len(tokens),
        session_id,
        mint_result.from_cache,
    )

    return HTMLResponse(
        status_code=200,
        content=_render_success_page(session_id, tokens, expires_at),
        headers=_PAYMENT_HEADERS,
    )


# ---------------------------------------------------------------------------
# /payment/cancel
# ---------------------------------------------------------------------------

@router.get("/payment/cancel")
async def payment_cancel() -> HTMLResponse:
    """Static page shown when the user cancels a Stripe Checkout session.

    No charge was made. Links to /pricing (try again) and /recover (if tokens
    were previously purchased and need recovery).
    """
    body = (
        "    <h1>Payment Cancelled</h1>\n"
        '    <p style="color: #555;">Your payment was cancelled. No charge was made.</p>\n'
        "    <p>\n"
        '        <a href="/pricing" style="color: #0070f3;">View pricing and try again &rarr;</a>\n'
        "    </p>\n"
        '    <p style="margin-top: 2em; font-size: 0.9em;">\n'
        '        Already have tokens from a previous purchase? '
        '<a href="/recover" style="color: #555;">Recover your tokens</a>.\n'
        "    </p>"
    )
    return HTMLResponse(
        status_code=200,
        content=_base_html("Payment Cancelled — Leafbind", body),
        headers=_PAYMENT_HEADERS,
    )
