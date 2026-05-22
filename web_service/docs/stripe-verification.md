# Stripe Verification — three layers, when to use each

The Leafbind freemium checkout chain (Stripe → FastAPI `/stripe/webhook` →
`token_store.mint_tokens_if_absent` → `/payment/success` page) is the only path
that turns money into product access. A break anywhere along that chain means a
paying customer hands you cash and gets nothing back. The production audit on
2026-05-16 also found that Stripe's new agent-detection gating (an "I am an AI
agent" checkbox + "Agent Identity Token" field on every Checkout page) makes
Playwright-driven E2E tests on the real Checkout page impossible. So we verify
the chain in three layers, each catching a different class of failure.

Read this when:

- You're about to ship something that touches `web_service/routes/checkout.py`,
  `web_service/routes/webhook.py`, `web_service/routes/payment.py`, or
  `web_service/token_store.py`.
- A customer reports "I paid but no tokens" and you need a structured
  troubleshooting path.
- You're onboarding to the billing surface and want to know what already exists.

## Configured URLs (current, post-EB-273)

These are the literal strings Stripe is told about at session-creation time:

| Field | Value | Defined in |
|---|---|---|
| `success_url` | `https://leafbind.io/payment/success?session_id={CHECKOUT_SESSION_ID}` | `web_service/routes/checkout.py` (search `success_url=`) |
| `cancel_url` | `https://leafbind.io/pricing` | `web_service/routes/checkout.py` (search `cancel_url=`) |

`/payment/success` is server-rendered by FastAPI (not Next.js) so token strings
never enter a JS bundle. The Next.js `next.config.js` rewrites `/payment/success`
through to the FastAPI backend at `api.leafbind.io`. `/pricing` is served by
Next.js on Vercel.

**If you ever change either of these literals, run the EB-273 contract test
locally before pushing** — `pytest tests/test_web_payment_e2e.py::TestSuccessUrlContract -v`.
The test parses `checkout.py` and asserts the new path resolves to a registered
FastAPI route. If you rename `/payment/success` without moving the route, this
test fails with an explicit "customers completing checkout will land on a 404 page"
error message.

## Environment variables

The web service is fail-closed on these (`_require_env` in `web_service/config.py`
raises `ConfigurationError` if any is missing at startup):

| Variable | Purpose | Where it lives |
|---|---|---|
| `STRIPE_SECRET_KEY` | Server-side Stripe SDK auth (`sk_test_...` or `sk_live_...`) | `/etc/web_service.env` on the Hetzner VM |
| `STRIPE_PUBLISHABLE_KEY` | Client-side Stripe.js (`pk_test_...` or `pk_live_...`) | same as above |
| `STRIPE_WEBHOOK_SECRET` | HMAC-SHA256 secret for validating webhook signatures (`whsec_...`) | same as above |
| `STRIPE_PRICE_STARTER` | Stripe Price ID for the 3-token pack | same as above |
| `STRIPE_PRICE_STANDARD` | Stripe Price ID for the 10-token pack | same as above |
| `STRIPE_PRICE_POWER` | Stripe Price ID for the 25-token pack | same as above |
| `STRIPE_API_VERSION` | Pinned Stripe API version (currently `2026-04-22.dahlia`) | same as above |
| `TOKEN_HMAC_SECRET` | App-side HMAC secret for token derivation | same as above |
| `APP_ENV` | When set to `production`, webhook handler rejects `livemode: false` events (test events in prod = 400) | same as above |

For local development, `tests/conftest.py` sets placeholder values automatically
so unit tests pass without real secrets.

## The three verification layers

### Layer 1 — Unit tests (mocked Stripe)

**Where:** `tests/test_web_payment.py`, `tests/test_web_webhook.py` (~1200 lines combined).

**What it catches:** Every code path in the payment routes — happy paths,
expired tokens, malformed session_ids, DB failures, circuit-breaker open,
XSS injection guards, pack metadata fallback. Uses `unittest.mock` to mock
`stripe.checkout.Session.retrieve`, `stripe.Webhook.construct_event`, the
token_store helpers, and the executor — no network, no DB writes (except
where explicitly testing DB-failure paths).

**Run it:** `py -3.12 -m pytest tests/test_web_payment.py tests/test_web_webhook.py -q`
(127 tests, ~7s).

**When to add to it:** Any new error path, any new event type, any change to
the token-mint chain. This is where exhaustive coverage lives.

### Layer 2 — Pytest e2e with real signatures (EB-273)

**Where:** `tests/test_web_payment_e2e.py` (8 tests, ~1.3s).

**What it catches:**
- **`success_url` typos.** Parses `checkout.py` to extract the literal URL
  string, then asserts the path resolves via `TestClient`. A refactor that
  renames `/payment/success` without moving the route handler fails this test
  with a specific error message naming the broken path.
- **Webhook signature scheme drift.** Computes a real HMAC-SHA256 signature
  with the same algorithm `stripe.Webhook.construct_event` validates against.
  If Stripe ever changes their signing scheme (or our handler's tolerance
  window drifts), this test fails.
- **The webhook → mint → success-page chain.** POSTs a signed
  `checkout.session.completed`, asserts `mint_tokens_if_absent` is called with
  the right pack count, then GETs `/payment/success` and asserts all three
  minted tokens appear in the HTML alongside the `PAYMENT CONFIRMED` eyebrow.

**Run it:** `py -3.12 -m pytest tests/test_web_payment_e2e.py -v`.

**Runs in CI:** Yes (via `.github/workflows/web-tests.yml`). PRs that break
either contract are blocked from merging.

**When to add to it:** When you add new configured-URL strings (e.g., a
future return path for an embedded Checkout flow), or when you add new
webhook event types whose presence in production needs to be contract-tested.

### Layer 3 — Manual Stripe CLI verification

**Where:** `tools/verify_stripe_e2e.ps1` (PowerShell 7, manual).

**What it catches:** What Layer 1 and Layer 2 can't — the **real** Stripe edge
to your app handshake. Specifically:

- Stripe API key drift (wrong key set in env, key revoked in dashboard)
- Webhook endpoint URL drift in the Stripe dashboard (e.g., dashboard still
  pointing at a staging URL after a domain change)
- Webhook signing secret mismatch between dashboard and app env
- Nginx / Cloudflare WAF rules blocking the webhook POST
- The webhook handler hanging instead of returning 200 (Stripe's retry storm)

**Run it:** `pwsh tools/verify_stripe_e2e.ps1` (defaults to localhost:8000).
With a staging or canary URL: `pwsh tools/verify_stripe_e2e.ps1 -AppUrl https://staging.leafbind.io`.

**Prerequisites:**
1. Stripe CLI installed (`winget install Stripe.StripeCLI` on Windows, `brew install stripe/stripe-cli/stripe` on macOS, official tarball on Linux).
2. `stripe login` completed once (auth token cached in `%APPDATA%\stripe\config.toml`).
3. The target app running and reachable at the URL you pass.
4. The app's `STRIPE_WEBHOOK_SECRET` matches what `stripe listen` prints when
   it starts forwarding. For local dev, copy the CLI's secret into your local
   `.env` before running the script.

**Not in CI:** Stripe CLI in GitHub Actions requires either storing CLI auth
tokens as repo secrets (unsupported by Stripe) or interactive `stripe login`
(impossible in CI). Leave this layer for the dev machine.

**When to run:** Before a production deploy that touches the billing surface.
After a Cloudflare WAF rule change. When a customer reports "I paid but no
tokens" and you've ruled out the Layer 1 / Layer 2 paths.

## Troubleshooting: "I paid but no tokens"

When a customer reports they paid but didn't receive tokens, walk this
flowchart top-down. Each step bisects the failure surface.

1. **Did Stripe charge them?**
   - Check Stripe Dashboard → Payments → search by email / amount.
   - If no payment record exists, the user never completed checkout. Direct
     them to `/recover` or to retry.
   - If payment exists, continue.

2. **Did Stripe attempt to deliver the webhook?**
   - Stripe Dashboard → Developers → Webhooks → click the production endpoint
     → look at Recent attempts.
   - If no attempt was made, the Checkout Session didn't trigger
     `checkout.session.completed` (rare; check Stripe status page).
   - If an attempt was made but failed with 4xx/5xx, continue.
   - If an attempt was made and returned 200, jump to step 5.

3. **Did the webhook fail signature validation?**
   - If the Stripe attempt shows a 400, check the app logs for
     `webhook_signature_failure`. The structured log line includes
     `sig_header_prefix` and `err`.
   - Cause: `STRIPE_WEBHOOK_SECRET` in app env doesn't match the dashboard.
     Re-copy the dashboard endpoint's signing secret into the env file and
     restart the app.

4. **Did the webhook fail at the mint step?**
   - If the Stripe attempt shows a 500, check the app logs for `mint_failed`
     (DB write error) or `record_failed_mint_error` (the fallback also failed).
   - Cause: DB lock contention, disk full, or schema drift. Check
     `data/failed_mints` table — if the session_id is there, run the manual
     mint recovery script (see `web_service/token_store.py` or the
     EB-227 ops runbook).

5. **Webhook returned 200, but customer still has no tokens?**
   - Check `data/sessions` table for the session_id. If row exists with
     `payment_status='paid'`, tokens were minted; the issue is on the
     customer's success-page render.
   - Direct customer to `/recover` with their session_id (from their Stripe
     receipt email or the Checkout return URL).
   - If `/recover` also shows no tokens, escalate — the mint succeeded but
     decryption is failing (key version mismatch, `TOKEN_HMAC_SECRET` change).

6. **None of the above explains it?**
   - Run `pwsh tools/verify_stripe_e2e.ps1` against production with the
     customer's session_id to confirm the chain is healthy for a fresh event.
   - If the script reports a 200 but the customer report is persistent,
     the issue is browser-side (localStorage cleared, ad blocker stripped the
     token script, etc.). Send the customer the recovery link and rotate their
     tokens manually.

## Related references

- **EB-273** (Phase 1+2) — the pytest e2e test and manual CLI script
- **EB-291** (this file's parent ticket) — the CI workflow and these docs
- **EB-227** — async payment handling (`async_payment_succeeded` /
  `async_payment_failed` events for ACH/SEPA settlement)
- **EB-248** — payment-page brand pass and XSS hardening
- `web_service/routes/checkout.py` — Session creation, `success_url` literal
- `web_service/routes/webhook.py` — Signature validation, mint dispatch
- `web_service/routes/payment.py` — `/payment/success` rendering
- `web_service/token_store.py` — `mint_tokens_if_absent`,
  `get_tokens_for_session`, encryption / decryption
