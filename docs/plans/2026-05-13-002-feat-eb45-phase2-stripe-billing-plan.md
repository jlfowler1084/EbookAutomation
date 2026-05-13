---
title: "feat: EB-45 Phase 2 — Stripe Billing and Premium Tier Unlock"
type: feat
status: active
date: 2026-05-13
deepened: 2026-05-13
origin: docs/brainstorms/2026-05-13-eb45-phase2-billing-requirements.md
---

# feat: EB-45 Phase 2 — Stripe Billing and Premium Tier Unlock

## Overview

Add Stripe Checkout-based credit purchases and a single-use HMAC-keyed opaque
token redemption system to the leafbind.io freemium ebook conversion service.
Removes the Phase 1 `tier="premium"` bypass and replaces it with real token
validation. Adds three credit packs (Starter $2.99/3, Standard $7.99/10, Power
$14.99/25), an idempotent revisitable success page for token recovery without
email or accounts, and the supporting frontend pages (`/pricing`,
`/payment/success`, `/payment/cancel`, `/recover`).

Backend-first delivery: token store + crypto utilities land first so the API
contract is stable when the frontend is built. The plan also adds chargeback
handling, mint-failure recovery, and a fully specified error taxonomy that the
origin document underspecified — see "Plan-Time Refinements to Origin Document"
in Open Questions.

**Deepened 2026-05-13** by parallel review agents on Units 2, 4, 7. Findings
synthesized: race-loser semantics rewritten (Unit 2), dispute-metadata-lookup
bug fixed (Unit 3+4), separate billing executor pool (Unit 4), `<script
type="application/json">` for XSS-safer token injection (Unit 5+7), Files lists
corrected (Unit 7), plus 30+ smaller refinements.

(see origin: `docs/brainstorms/2026-05-13-eb45-phase2-billing-requirements.md`)

## Problem Frame

Phase 1 shipped the conversion engine at `https://leafbind.io` with TLS, CORS, a
working `/convert` endpoint, and a deliberate tier bypass (`tier="premium"` for
every request) so the public soft-launch wasn't gated on Stripe billing. Phase 2
closes the gate: real payment, real tokens, real validation.

Three constraints shape the design:
- **No user accounts** — credit tokens are stateless opaque strings keyed by an
  HMAC secret. Privacy is the differentiator vs Zamzar/CloudConvert.
- **No email collection by default** — Stripe Checkout's default behavior breaks
  this; the plan addresses it explicitly via `customer_creation="if_required"`
  and disabled receipts.
- **Idempotent recovery without PII** — the `/payment/success?session_id=xxx`
  URL is the canonical recovery mechanism. Stripe stores completed sessions
  indefinitely; our `pack_id UNIQUE` constraint makes the URL stable and
  re-displays the same tokens within the 7-day expiry window.

## Requirements Trace

**Stripe Checkout** (R1, R2, R3):
- R1. Three credit packs at launch: Starter $2.99/3, Standard $7.99/10, Power $14.99/25
- R2. `POST /stripe/create-session` with leafbind.io success_url + cancel_url + `payment_intent_data.metadata.checkout_session_id` (dispute propagation)
- R3. `POST /stripe/webhook` handles `checkout.session.completed` AND `charge.dispute.created` with signature validation + livemode assertion

**Token Generation and Delivery** (R4, R5):
- R4. Success-page-on-load generates N tokens, stores hash + encrypted-recovery + key_version + payment_intent_id
- R5. Display tokens with copy buttons + Download/Print buttons + bookmark notice

**Token Validation** (R6, R7, R8):
- R6. `POST /convert` validates token when `tier=premium`; remove Phase 1 bypass
- R7. Mark token used before conversion; no refund on conversion failure
- R8. Atomic validation in single DB transaction (BEGIN IMMEDIATE)

**Token Recovery** (R8a-R8e):
- R8a. `/payment/success` is idempotent and revisitable for 7 days
- R8b. Storage shape: hash + encrypted-plaintext via Fernet (HKDF-derived key) + key_version for future rotation
- R8c. `localStorage` fallback + `/recover` route (Next.js UI + FastAPI `POST /api/recover`)
- R8d. Response headers: `Referrer-Policy: no-referrer`, `Cache-Control: private, no-store`
- R8e. Email-based recovery deferred to Phase 2.5

**Frontend** (R9-R12):
- R9. `/pricing` page with 3-pack comparison
- R10. `UploadZone` token field with regex validation (`^lb_pk_[A-Za-z0-9_-]{43}$`)
- R11. `/payment/success` with idempotent revisit, tokens display, headers
- R12. `/payment/cancel` page

**Phase 1 Bypass Removal** (P1 Finding #5):
- Delete `tier = "premium"` line in `web_service/routes/convert.py:29`
- Delete `@pytest.mark.skip` decorator in `tests/test_web_endpoints.py` on `test_kfx_on_free_tier_returns_422`

**Token Format Specification** (P1 Finding #7):
- Wire format: `lb_pk_<43-char-base64url>` (49 chars, 256 bits entropy)
- Validation regex: `^lb_pk_[A-Za-z0-9_-]{43}$`
- Server-side hash: `HMAC-SHA256(TOKEN_HMAC_SECRET, token)` → SQLite BLOB PK

## Scope Boundaries

**In scope:**
- Stripe Checkout (`mode=payment` for one-time purchases, stored Price IDs)
- HMAC-SHA256-keyed opaque token generation per the Token Format Specification
- Token DB (hash PK + encrypted-recovery BLOB + key_version + payment_intent_id, `pack_id UNIQUE`, used flag, expires_at, disputed flag with separate disputed_at column)
- Three-tier pack pricing
- Single-use-per-token atomic validation at `/convert` with 4-code error taxonomy
- Frontend: pricing, success, cancel, recover pages + UploadZone token field
- Phase 1 tier bypass removal
- Chargeback handling (`charge.dispute.created` webhook with payment-intent metadata lookup) — refinement to R3
- Mint-failure recovery (`failed_mints` table + retry via Stripe's free retry budget) — refinement to R4
- Error taxonomy: `TOKEN_MALFORMED` / `TOKEN_INVALID_OR_EXPIRED` / `TOKEN_ALREADY_USED` / `TOKEN_DISPUTED`
- Token cleanup sweep (purges `expires_at < now - 30 days AND used=1`)
- `MAX_TOKENS_PER_SESSION = 25` guard (app-level + schema comment)
- Separate billing executor pool (4 workers, distinct from 3-worker conversion pool)
- Lightweight circuit breaker for DB outages
- Structured logging events + NTP startup check + livemode assertion

**Out of scope for Phase 2:**
- Subscription / recurring billing
- Token refunds or re-issuance for conversion failures
- Email delivery of tokens (deferred to Phase 2.5)
- Cross-device recovery beyond `session_id` paste-box (acknowledged gap)
- Usage analytics dashboard
- Rate limiting enforcement at app-layer (Phase 4) — Cloudflare rate-limit at edge is operational config, not code
- Docker isolation per job (documented upgrade path)
- Stripe Customer Portal or receipts management
- Stripe Tax integration (currency=USD only at launch)
- TOKEN_HMAC_SECRET rotation within an active 7-day window (unsupported; key_version column enables future rotation)
- `charge.dispute.funds_withdrawn`, `charge.dispute.closed` lifecycle events (Phase 2 handles only `created`; revisit if dispute rate >0.5%)

### Deferred to Separate Tasks

- **feature-manifest.json web_service entries**: orthogonal gap inherited from Phase 1; file a new ticket post-Phase-2 ship.
- **Email-based token recovery (Phase 2.5)**: file ticket if real chargeback volume in the 60 days post-launch indicates the revisitable-URL pattern is insufficient.
- **`StripeClient` v15+ migration**: pin to `stripe~=12.5` for Phase 2 stability; track v15 `StripeObject` dict-removal as a separate refactor when Stripe v12 EOL approaches.
- **Prometheus alerting rule setup**: structured log events are emitted in Phase 2; alert wiring is Phase 4.

## Context & Research

### Relevant Code and Patterns

| What | Where | How Phase 2 mirrors |
|---|---|---|
| FastAPI app structure + lifespan | `web_service/main.py` | New `checkout`, `webhook`, `payment`, `recover` routers added via `include_router()` in `create_app()`; lifespan extends to init token cleanup sweep + NTP startup check |
| Settings dataclass + env loading | `web_service/config.py` | Extend `Settings` with `stripe_secret_key`, `stripe_publishable_key`, `stripe_webhook_secret`, `token_hmac_secret`, `stripe_price_starter/standard/power`; all populated via `_require_env` (fail-closed on missing). **Frozen dataclass makes runtime mutation impossible — no runtime nullity checks needed.** |
| SQLite CRUD with WAL + `_get_conn` | `web_service/job_store.py` | New `token_store.py` follows same `@contextmanager` + WAL pattern; **adds `PRAGMA busy_timeout=5000`** (gap from job_store that Phase 2 fixes). All `BEGIN IMMEDIATE` blocks wrapped in try/except for `sqlite3.OperationalError` → 503 with retry hint |
| Pure-function validator + structured errors | `web_service/validation.py` | New `token_validation.py` returns `TokenValidationResult` with `ValidationError`-shaped error codes (`TokenValidationErrorCode` enum: `MALFORMED`, `INVALID_OR_EXPIRED`, `ALREADY_USED`, `DISPUTED`) |
| Route module shape | `web_service/routes/convert.py`, `status.py`, `download.py` | New `web_service/routes/checkout.py`, `webhook.py`, `payment.py`, `recover.py` follow the ~30-65 line, single-`router = APIRouter()`, `HTTPException(status, detail={"error","code"})` pattern |
| Test fixtures (clear_settings, project_root, client) | `tests/test_web_endpoints.py`, `tests/test_web_validation.py` | Reuse all three fixtures in new test files; Stripe SDK mocked at import boundary |
| Next.js Server vs Client Component split | `web_service/frontend/app/page.tsx` (Server) + `app/UploadForm.tsx` (`"use client"`) | New pages are Server Components by default with `metadata` export; only interactive logic (token paste, copy buttons, localStorage reads) is Client Component |
| **Inline `style={}` styling — NO Tailwind** | `web_service/frontend/components/UploadZone.tsx`, `ConversionStatus.tsx` | Phase 2 continues inline style objects. Color palette: `#0070f3` (primary), `#555` (muted text), `#666` (caption), `#ccc` (border), `#fafafa`/`#f0f7ff` (surface), `red` (error). NO `className=`, NO CSS files. |
| Typed fetch API client | `web_service/frontend/lib/api.ts` | Extend with typed `createCheckoutSession(pack: string): Promise<CheckoutResponse>` matching `startConversion` shape exactly (`async`, `Promise<TypedInterface>`, throws on non-2xx via `err.detail?.error ?? err.error ?? HTTP {status}` pattern); add `validateTokenFormat(token)` |
| `UploadForm.tsx` is a thin 14-line shim | `web_service/frontend/app/UploadForm.tsx` | **Token state lives in `components/UploadZone.tsx`** (where `outputFormat` already lives), NOT in the `UploadForm.tsx` shim. The plan's Files list reflects this. |
| FormatSelector already has tier gate | `web_service/frontend/components/FormatSelector.tsx:9-13` | **No modification needed.** `FREE_FORMATS = ["epub","mobi"]` vs `PREMIUM_FORMATS = ["epub","mobi","kfx"]` already in place. UploadZone.tsx:87 hardcodes `tier="free"` today — Phase 2 changes this to state-derived `tier` |
| Frozen dataclass pattern | `web_service/pipeline_runner.py` `RunResult` | `TokenIssueResult`, `MintResult` follow same shape |

### Institutional Learnings

- **`docs/solutions/best-practices/pre-implementation-render-check-2026-04-22.md`**: when (not if) a Phase 2 cross-layer issue surfaces, instrument every layer (Stripe webhook payload, DB row state, localStorage, FE state) before touching any one of them. **Apply as observability/debug-logging design principle for the webhook + success-page race in Unit 4** — structured log events for `webhook_signature_failure`, `mint_failed`, `validate_consume`, `stripe_api_call` emitted in Phase 2 even though alert wiring is Phase 4.
- **`docs/solutions/eb-142-calibre-stderr-capture.md`**: capture FULL stderr/stdout from external integrations; don't truncate. **Apply to Stripe webhook handler + success page Stripe verification — log the full event body (truncated to 1KB to prevent disk fill during attack), signature header, source IP, and DB transaction outcome on every failure. Phase 2 evidence-loss costs real money and trust.**
- **`docs/solutions/developer-experience/project-hook-gap-analysis-and-sync-2026-05-10.md`**: the global `settings.json` credential-write guard blocks writes to `.env`. **Phase 2 secrets (Stripe keys, HMAC secret) get added manually by Joe, not by Claude. The plan calls out the `/etc/web_service.env` manual edit in Unit 8.**
- **No prior solutions exist for Stripe / HMAC / Fernet / atomic SQLite / webhooks / privacy-first design in this repo.** This is greenfield. File `ce:compound` entries after Phase 2 ships for each non-trivial sub-decision (HMAC binding scheme, atomic-consume SQL pattern, idempotency design, encryption key derivation, dispute metadata propagation pattern).

### External References

- **Stripe Python SDK** (pin `stripe~=12.5`): https://pypi.org/project/stripe/, https://github.com/stripe/stripe-python/blob/master/CHANGELOG.md
- **Stripe Checkout Sessions API**: https://docs.stripe.com/api/checkout/sessions/create?lang=python
- **Stripe Webhook Signature Verification**: https://docs.stripe.com/webhooks/signatures
- **Stripe Webhook Best Practices (event ordering, retries)**: https://docs.stripe.com/webhooks/best-practices
- **Stripe Disputes API + Charge metadata propagation**: https://docs.stripe.com/api/disputes/object, https://docs.stripe.com/api/charges/object#charge_object-metadata
- **Stripe IPs (for optional allowlist — NOT recommended; use Cloudflare rate-limit instead)**: https://docs.stripe.com/ips
- **`cryptography` library** (pin `cryptography~=48.0`): https://pypi.org/project/cryptography/
- **Fernet docs**: https://cryptography.io/en/latest/fernet/
- **HKDF docs**: https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#hkdf
- **Python stdlib `hmac.compare_digest`**: https://docs.python.org/3/library/hmac.html#hmac.compare_digest
- **FastAPI raw body for webhooks**: https://fastapi.tiangolo.com/reference/request/
- **SQLite isolation under WAL**: https://www.sqlite.org/wal.html#concurrency, https://www.sqlite.org/isolation.html
- **CVE-2026-41432** (empty webhook secret silently disables verification — pattern to mitigate): https://github.com/advisories/GHSA-xff3-5c9p-2mr4
- **CVE-2026-40481** (webhook body-size DoS): https://vulnerability.circl.lu/vuln/cve-2026-40481

## Key Technical Decisions

- **Pin `stripe~=12.5`, not v15+** — v15.0.0 introduced a breaking change where `StripeObject` no longer inherits from `dict` (`.get()`, `.update()`, `.items()` removed). For Phase 2's simple Checkout + webhook flow, v12.x is the last comfortable major. Track the v15 migration as a separate future refactor.

- **Stored `Price` IDs over inline `price_data`** — Three Products + Prices created once in the Stripe Dashboard (or a one-shot bootstrap script in Unit 3). Env vars `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_STANDARD`, `STRIPE_PRICE_POWER` reference them. Enables repricing without code deploys, audit trail in Dashboard, and future Adaptive Pricing if needed.

- **`payment_intent_data.metadata.checkout_session_id` set at Checkout Session creation** — Stripe Disputes are parented to Charges, not Sessions; Charge metadata is independent of Session metadata. Setting `payment_intent_data={"metadata": {"checkout_session_id": session.id}}` at session creation propagates the link through the PaymentIntent so the dispute handler can resolve session_id via single-hop PI retrieve. Without this, `charge.dispute.created` handling is silently broken. **Critical Phase 2 fix — see Unit 3 + Unit 4.**

- **Token DB shape: hash PK + encrypted_for_recovery BLOB + key_version + payment_intent_id** — The `key_version INTEGER NOT NULL DEFAULT 1` column enables future `TOKEN_HMAC_SECRET` rotation without a migration emergency. The `payment_intent_id TEXT` column is the fallback path for dispute handling if Charge metadata propagation fails. Both added now at near-zero cost; painful to retrofit under incident pressure.

- **Fernet over AESGCM for `token_encrypted_for_recovery` column** — Single-use opaque tokens have no AAD requirement and no replay concern (single-use semantics). Fernet's batteries-included AES-128-CBC + HMAC-SHA256 is the right level. `MultiFernet` is available for future key rotation without re-encrypting all rows.

- **HKDF-SHA256 derives the Fernet key from `TOKEN_HMAC_SECRET`** with `info=b"leafbind-token-recovery-v1"` — domain separation ensures a leak in one role (HMAC validation) doesn't compromise the other (recovery encryption). HKDF instances are single-use; reinstantiate per derivation. The `-v1` suffix corresponds to `key_version=1` in the DB.

- **Idempotency via `pack_id UNIQUE` + SELECT-first-then-INSERT, NOT race-loser local-token return** — Both webhook and success-page paths call the same `mint_tokens_if_absent(session_id)` function. Under `BEGIN IMMEDIATE`, SQLite serializes writers — the second writer waits up to `busy_timeout=5000` for the first to COMMIT, then sees the winner's rows on its first SELECT. **If somehow `INSERT OR IGNORE` returns rowcount=0 (which BEGIN IMMEDIATE should prevent), treat as invariant violation: log ERROR, re-SELECT inside the same txn, return DB-authoritative rows. NEVER return locally-generated tokens after an IGNORE collision — they were silently dropped and the user would receive phantom tokens.**

- **Disputed flag distinct from used flag** — `disputed=1, used=0` is a valid state meaning "unused but revoked by chargeback; reject at validate_and_consume." `mark_disputed(pack_id)` sets `disputed=1, disputed_at=?` WITHOUT modifying `used`. This preserves audit distinguishability: `used=1, disputed=1` is "legitimately consumed, later disputed" (important for chargeback fraud analytics), separate from `used=1, disputed=0` (clean use). Error code `TOKEN_DISPUTED` distinct from `TOKEN_ALREADY_USED`.

- **Separate billing executor pool (4 workers) distinct from conversion pool (3 workers)** — Webhook timeout is 30s; PDF conversion timeout is 120s. Shared pool guarantees Stripe timeout under conversion load. New `ThreadPoolExecutor(max_workers=4, thread_name_prefix='billing')` for Stripe SDK + token store operations.

- **Webhook DB-write failure returns 500 (not 200)** — Plan v1 said "return 200 after signature validation succeeds regardless of downstream." v2 changes this: return 400 on signature/parse failure (permanent, no Stripe retry), 500 on DB write failure (transient, Stripe retries with exponential backoff for ~3 days). Write to `failed_mints(session_id, pack, error, attempt_count)` table either way so admin sweep can act if all retries exhaust.

- **New `web_service/token_store.py`, not extending `job_store.py`** — Token concerns (hash storage, encrypted-recovery, used/expired/disputed state, atomic single-use validation) are sufficiently distinct from job state to warrant module isolation. The two stores share the same SQLite DB file but the table operations are independent.

- **Four-code error taxonomy at `/convert` token validation**:
  - `TOKEN_MALFORMED` — regex fails (fast 422, no DB hit)
  - `TOKEN_INVALID_OR_EXPIRED` — unknown OR expired (same code to avoid leaking which condition; security trade-off documented)
  - `TOKEN_ALREADY_USED` — `used=1 AND disputed=0` (legitimate consume)
  - `TOKEN_DISPUTED` — `disputed=1` (revoked; user sees honest error)

- **Stripe Checkout email-collection bypass** — `customer_creation="if_required"` + `payment_intent_data.receipt_email=None` + disabled in Dashboard preserves the "no email by default" privacy story. Stripe will still collect email at Checkout (their hosted page requires it), but Stripe stores it, not our DB. Document this trade-off in the privacy policy.

- **Webhook hardening at nginx + Cloudflare layers** — nginx body cap 256KB (CVE-2026-40481 DoS mitigation with headroom for future event subscriptions), Cloudflare rate-limit rule on `/stripe/webhook` (defense-in-depth; nginx IP allowlist is rejected because Stripe's IPs change without notice). Explicit `tolerance=300` in `Webhook.construct_event()`. `livemode` assertion in production prevents test-mode events from minting live tokens. Fail-startup on empty `STRIPE_WEBHOOK_SECRET` via `_require_env` (CVE-2026-41432 class).

- **Lightweight circuit breaker for DB outages** — In-memory counter: >5 consecutive failures in 60s → handler short-circuits to 503 for next 30s without touching DB. Half-open probe lets one request through to test recovery. ~40 lines of code; prevents thread-pool exhaustion during prolonged DB outages.

- **Server-rendered token injection via `<script type="application/json">`** — Payment success page (FastAPI Python, NOT Next.js) serializes tokens via `json.dumps(..., ensure_ascii=True)` into a `<script type="application/json" id="leafbind-tokens">...</script>` block. A separate `<script>` reads `JSON.parse(document.getElementById('leafbind-tokens').textContent)` and writes localStorage. Eliminates `</script>` injection class entirely; safer than inline JS string interpolation.

- **NTP startup check + 60s drift warning** — `timedatectl show --property=NTPSynchronized --value` at app startup; log ERROR if not synchronized but continue (don't refuse boot — worse failure mode). On every webhook signature validation, log WARN if `abs(now - event_timestamp) > 60s` — early warning before the 5-minute rejection threshold.

- **Subprocess pattern unchanged** — Stripe SDK calls (blocking I/O) go through `loop.run_in_executor(billing_executor)` (NOT the conversion executor). No new threading concerns; new pool is the operational fix.

## Open Questions

### Resolved During Planning

- **Token DB file location**: New `web_service/token_store.py`, not extending `job_store.py`. Rationale: distinct concerns, same DB file is fine.
- **Stripe Checkout `mode` parameter**: Pin `mode="payment"` explicitly. No subscription mode.
- **Symmetric encryption library**: Fernet via HKDF-derived key from `TOKEN_HMAC_SECRET`. `MultiFernet` provides future rotation path; `key_version` column enables it.
- **Stripe SDK version**: `stripe>=12.0.0,<13.0.0`. Avoid v15 breaking change for Phase 2.
- **Stored vs inline Price IDs**: Stored.
- **Dispute metadata propagation**: `payment_intent_data.metadata.checkout_session_id` set at Session creation; dispute handler does single-hop PaymentIntent retrieve to resolve back to session_id.
- **Token storage shape**: hash PK + encrypted-recovery BLOB + key_version + payment_intent_id + used + used_at + disputed + disputed_at + pack_id UNIQUE + created_at + expires_at.
- **`/recover` ownership**: **Option A** — Next.js owns the UI page at `/recover`; FastAPI exposes `POST /api/recover` for the session_id lookup endpoint. Preserves Phase 1 split (Next = UI, FastAPI = API + payment-callback HTML).
- **Executor pool architecture**: Separate `billing_executor` (4 workers) distinct from `conversion_executor` (3 workers) because 30s webhook timeout vs 120s conversion timeout is incompatible on shared pool.
- **Webhook response policy**: 400 on signature/parse failure, 500 on DB write failure (lets Stripe retry), 200 on success or idempotent no-op.

### Plan-Time Refinements to Origin Document

The flow analyzer + deepening agents surfaced multiple gaps in the origin requirements doc that this plan addresses. **The origin doc should be amended in a follow-up commit post-Phase-2 ship** to align with what the plan actually delivers:

1. **R3a (new)** — Subscribe to `charge.dispute.created`; resolve session_id via PaymentIntent metadata propagation (`payment_intent_data.metadata.checkout_session_id` set at Session creation in R2); on dispute, mark all tokens for that `pack_id` as `disputed=1, disputed_at=now` (does NOT modify `used`).
2. **R4 (clarification)** — On `INSERT OR IGNORE` rowcount=0 (which `BEGIN IMMEDIATE` should prevent), treat as invariant violation: log ERROR, re-SELECT inside same txn, return DB-authoritative rows. NEVER return locally-generated tokens.
3. **R4a (new — mint-failure recovery)** — If DB write fails after Stripe verification succeeds: log to `failed_mints(session_id, pack, error, attempt_count, ts)` table, return 500 to trigger Stripe's free retry budget (~3 days exponential backoff). Webhook AND success-page both follow this pattern.
4. **R6 (error taxonomy)** — Four distinct codes: `TOKEN_MALFORMED`, `TOKEN_INVALID_OR_EXPIRED`, `TOKEN_ALREADY_USED`, `TOKEN_DISPUTED`. The TOKEN_DISPUTED code is shown to users on chargeback-revoked tokens with an honest error message.
5. **R7 (storage refinement)** — Token table extends to include `key_version` (future rotation), `payment_intent_id` (dispute fallback), and `disputed_at` (separate from `used_at`).
6. **R8c (cross-device extension)** — `/recover` Next.js UI page; FastAPI `POST /api/recover` accepts a session_id paste-box; on validation, 302-redirects to `/payment/success?session_id=…` (the canonical recovery URL).

### Deferred to Implementation

- **Exact body of `mint_tokens_if_absent(session_id)`** — pseudo-code in Unit 2 is directional; the implementer adjusts for the specific Stripe SDK calls and SQLite transaction semantics observed during development.
- **Token cleanup sweep cadence** — Initial value 60 minutes (matches `cleanup_expired_jobs` in `job_queue.py`); revise post-launch based on table growth.
- **`failed_mints` table location** — Recommended: extend `web_service/token_store.py` rather than create a third module. Verify during implementation.
- **Frontend styling specifics beyond color palette** — Match existing Phase 1 inline-style aesthetic; designer pass deferred to Phase 3.
- **Stripe Dashboard webhook endpoint configuration** — Real `whsec_*` value is generated when the endpoint is registered; goes in `/etc/web_service.env` manually by Joe (credential-write hook blocks Claude from writing this).
- **Cloudflare rate-limit rule numeric tuning** — Initial value 30/min per source IP on `/stripe/webhook`; tune post-launch based on Stripe webhook delivery volume + observed scanner noise.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

**Payment + token-redemption flow:**

```mermaid
sequenceDiagram
    participant U as User Browser
    participant FE as Next.js (/pricing)
    participant API as FastAPI
    participant SC as Stripe Checkout
    participant SW as Stripe Webhook
    participant TS as token_store
    participant Q as Job Queue

    U->>FE: Click "Buy Starter"
    FE->>API: POST /stripe/create-session {pack: "starter"}
    Note over API: payment_intent_data.metadata.checkout_session_id = session.id<br/>customer_creation="if_required"<br/>receipt_email=None
    API->>SC: Create Checkout Session
    SC-->>API: session.url, session.id
    API-->>FE: {checkout_url}
    FE->>U: button disabled while pending; window.location = checkout_url
    U->>SC: Pay (hosted)

    par Webhook path (billing_executor pool)
        SC->>SW: POST /stripe/webhook (checkout.session.completed)
        SW->>SW: construct_event(payload, sig, secret, tolerance=300)
        SW->>SW: assert event["livemode"] in production
        SW->>TS: mint_tokens_if_absent(session_id, count)
        TS->>TS: BEGIN IMMEDIATE; SELECT by pack_id
        alt rows exist (success-page won race)
            TS->>TS: decrypt + return existing
        else no rows
            TS->>TS: generate N tokens; INSERT OR IGNORE
            TS->>TS: if any IGNORE collision (shouldn't happen under IMMEDIATE), re-SELECT
        end
        TS-->>SW: {tokens: [...]}
        alt DB write failed
            SW-->>SC: 500 (Stripe retries up to 3 days)
            SW->>TS: write to failed_mints
        else success
            SW-->>SC: 200 OK
        end
    and Success-page path
        SC->>U: 302 → /payment/success?session_id=xxx
        U->>API: GET /payment/success?session_id=xxx
        API->>SC: retrieve(session_id, expand=line_items)
        SC-->>API: paid=true
        API->>TS: mint_tokens_if_absent(session_id, count)
        Note over TS: Same function as webhook path<br/>BEGIN IMMEDIATE serializes
        TS-->>API: {tokens: [...]}
        API-->>U: HTML with tokens via <script type="application/json"><br/>+ inline script writes localStorage<br/>+ Referrer-Policy + Cache-Control headers
    end

    Note over U: User copies lb_pk_xxx token
    U->>FE: /convert page, paste token, upload PDF
    FE->>API: POST /convert (file, token, tier=premium, output_format=kfx)
    API->>TS: validate_and_consume(token)
    TS->>TS: BEGIN IMMEDIATE; UPDATE WHERE hash=? AND used=0 AND disputed=0 AND expires_at>now
    alt rowcount=1 (success)
        TS->>TS: COMMIT
        TS-->>API: {ok: true}
        API->>Q: enqueue job_id (conversion_executor pool)
        API-->>FE: 202 {job_id}
    else rowcount=0
        TS->>TS: SELECT to disambiguate (inside same txn)
        TS-->>API: {ok: false, code: MALFORMED|INVALID_OR_EXPIRED|ALREADY_USED|DISPUTED}
        API-->>FE: 422 {error, code}
    end
```

**Token table state machine:**

```
(none) ──INSERT OR IGNORE──> active{used=0, disputed=0, expires_at>now}
                                 │
                                 ├──UPDATE used=1──> used{used=1, disputed=0}
                                 ├──charge.dispute.created──> revoked{used=0, disputed=1}
                                 ├──UPDATE used=1 then dispute──> disputed-after-use{used=1, disputed=1}
                                 └──time passes──> expired{used=0, expires_at<=now}

All states readable for 30 days past expiry via cleanup sweep retention
(sweep deletes only used=1 AND expires_at < now - 30 days).
```

## Output Structure

```
web_service/
├── crypto.py                       # NEW: HKDF + Fernet helpers, key derivation from TOKEN_HMAC_SECRET (with key_version support)
├── token_store.py                  # NEW: SQLite tokens table CRUD; mint_tokens_if_absent + validate_and_consume + mark_disputed + failed_mints CRUD
├── token_validation.py             # NEW: pure-function token validator returning TokenValidationResult with 4-code enum
├── circuit_breaker.py              # NEW: lightweight 5-fail/60s/30s-open counter for DB outages
├── config.py                       # MODIFY: add Stripe + token env var fields to Settings; add startup checks (NTP, env-mismatch)
├── main.py                         # MODIFY: include_router for checkout/webhook/payment/recover; lifespan starts token cleanup sweep + billing_executor + NTP check
├── job_queue.py                    # MODIFY: add cleanup_expired_tokens sweep + cleanup_failed_mints sweep + billing_executor pool definition
└── routes/
    ├── checkout.py                 # NEW: POST /stripe/create-session (with payment_intent_data.metadata)
    ├── webhook.py                  # NEW: POST /stripe/webhook (checkout.session.completed + charge.dispute.created + livemode assertion + circuit breaker)
    ├── payment.py                  # NEW: GET /payment/success (server-rendered with <script type="application/json">), /payment/cancel
    ├── recover.py                  # NEW: POST /api/recover (session_id paste lookup)
    └── convert.py                  # MODIFY: remove Phase 1 bypass; add token validation; 4-code error taxonomy

web_service/frontend/
├── app/
│   ├── pricing/page.tsx            # NEW: 3-pack comparison Server Component with metadata export
│   ├── recover/page.tsx            # NEW: Server wrapper with searchParams: Promise<{session_id?: string}>
│   └── status/[id]/page.tsx        # (existing — pattern reference)
├── components/
│   ├── BuyButtons.tsx              # NEW: Client child for /pricing — disabled-while-pending pattern
│   ├── RecoverClient.tsx           # NEW: Client component reading localStorage + session_id paste form
│   ├── TokenField.tsx              # NEW: Client Component, regex validation on blur, inline error display
│   ├── TokenList.tsx               # NEW: Client Component, copy/download/print buttons
│   └── UploadZone.tsx              # MODIFY: add token state, <details> collapsible, state-derived tier (replaces hardcoded tier="free")
└── lib/
    └── api.ts                      # MODIFY: add createCheckoutSession(pack): Promise<CheckoutResponse>, validateTokenFormat helper

tests/
├── test_web_token_store.py         # NEW (includes race-loser invariant test, DISPUTED state test, key_version test)
├── test_web_token_validation.py    # NEW
├── test_web_crypto.py              # NEW (HKDF determinism, domain separation tests)
├── test_web_circuit_breaker.py     # NEW
├── test_web_checkout.py            # NEW (verifies payment_intent_data.metadata.checkout_session_id is set)
├── test_web_webhook.py             # NEW (signature failure tests, livemode test, dispute metadata lookup test, executor isolation test)
├── test_web_payment.py             # NEW (idempotent revisit, <script type="application/json"> rendering test)
├── test_web_recover.py             # NEW
└── test_web_endpoints.py           # MODIFY: un-skip test_kfx_on_free_tier_returns_422

deploy/
├── README.md                       # MODIFY: add Stripe env var setup + NTP check + Cloudflare rate-limit configuration walkthrough
└── stripe_bootstrap.py             # NEW: idempotent script to create Products + Prices in Stripe Dashboard

requirements.txt                    # MODIFY: add stripe~=12.5, cryptography~=48.0
```

## Implementation Units

- [ ] **Unit 1: Config + secrets + dependencies + startup checks**

**Goal:** Extend `Settings` with Stripe + token env vars; add new dependencies; add startup checks (NTP sync, env-mismatch detection); document env var setup. No runtime logic yet — scaffolding + startup hardening.

**Requirements:** R2, R3, R4 (env vars), Token Format Specification (HMAC secret)

**Dependencies:** None

**Files:**
- Modify: `web_service/config.py`
- Modify: `web_service/main.py` (add startup checks to lifespan)
- Modify: `requirements.txt`
- Modify: `deploy/README.md`
- Test: extend `tests/test_web_config.py`

**Approach:**
- Add to `Settings` dataclass: `stripe_secret_key`, `stripe_publishable_key`, `stripe_webhook_secret`, `token_hmac_secret`, `stripe_price_starter`, `stripe_price_standard`, `stripe_price_power` — all `str` populated via `_require_env()` (fail-closed). **Frozen dataclass makes runtime mutation impossible — no runtime nullity checks needed in handlers.**
- `requirements.txt`: pin `stripe>=12.0.0,<13.0.0`, `cryptography>=48.0.0,<49.0.0`
- **NTP startup check in lifespan**: shell out to `timedatectl show --property=NTPSynchronized --value` (or read `/run/systemd/timesync/synchronized`). If not synchronized, log ERROR but continue (refusing boot creates worse failure mode). Surface in `/health` response if not synced.
- **Env-mismatch startup check**: assert `STRIPE_PUBLISHABLE_KEY` prefix matches `STRIPE_SECRET_KEY` prefix (`pk_test_` ↔ `sk_test_` or `pk_live_` ↔ `sk_live_`). Log WARN at startup with masked secret prefixes for audit.
- `deploy/README.md` new "Stripe Configuration" section: list env vars with placeholder values; `STRIPE_WEBHOOK_SECRET` comes from `stripe listen` (dev) or Dashboard endpoint registration (prod).

**Patterns to follow:**
- `web_service/config.py:27-34` `_require_env()` fail-closed pattern
- `web_service/config.py:37-51` `Settings` dataclass field ordering
- `web_service/main.py` lifespan pattern for adding new init steps

**Test scenarios:**
- Happy path: All 7 new env vars set → `load_settings()` returns Settings with each field populated
- Error path: Any of the 7 unset → `ConfigurationError("Required environment variable '...' is not set...")` with the variable named
- Edge case: `STRIPE_PUBLISHABLE_KEY="pk_test_..."` + `STRIPE_SECRET_KEY="sk_live_..."` (env mismatch) → startup logs WARN
- Edge case: NTP not synced → startup logs ERROR but service starts; `/health` includes `ntp_synced=false`
- Happy path: Phase 1 settings still load (regression check)

**Verification:**
- `py -3.12 -c "from web_service.config import load_settings; load_settings()"` with all env vars succeeds
- `pip install -r requirements.txt` succeeds on Hetzner VM

---

- [ ] **Unit 2: Token store + crypto utilities + circuit breaker**

**Goal:** Implement the `tokens` + `failed_mints` table CRUD (idempotent mint with NO race-loser local-token return, atomic single-use consume with 4-code error disambiguation, recovery lookup, dispute revocation), the HKDF→Fernet key derivation helpers with key_version support, and the lightweight circuit breaker for DB outages. This is the heart of Phase 2 — payment correctness, idempotency, recovery, and resilience all depend on this module.

**Requirements:** R4, R7, R8, R8a, R8b, R4a (mint-failure recovery), Token Format Specification

**Dependencies:** Unit 1

**Execution note:** **Test-first** for `mint_tokens_if_absent`, `validate_and_consume`, and `mark_disputed` — these are the highest-correctness-cost functions in Phase 2. Write race-condition and double-spend tests BEFORE the implementation. Include explicit invariant tests for the race-loser branch (which should be unreachable under BEGIN IMMEDIATE).

**Files:**
- Create: `web_service/crypto.py`
- Create: `web_service/token_store.py`
- Create: `web_service/circuit_breaker.py`
- Test: `tests/test_web_crypto.py`
- Test: `tests/test_web_token_store.py`
- Test: `tests/test_web_circuit_breaker.py`

**Approach:**

- **`crypto.py`** exposes:
  - `derive_fernet_key(secret: bytes, key_version: int = 1) -> bytes` — HKDF-SHA256, `info=f"leafbind-token-recovery-v{key_version}".encode()`, 32-byte output base64url-encoded for Fernet. Single-use HKDF instances per derivation.
  - `get_fernet(key_version: int = 1) -> Fernet` — cached singleton per key_version
  - `mint_token() -> tuple[str, bytes]` — returns `(token_string, token_hash)`. Token = `"lb_pk_" + base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()`. Hash = `HMAC-SHA256(TOKEN_HMAC_SECRET, token).digest()`.
  - `compute_token_hash(token: str) -> bytes` — for `validate_and_consume` lookup keying.

- **`token_store.py`** schema:
  ```sql
  CREATE TABLE tokens (
      token_hash                   BLOB PRIMARY KEY,
      token_encrypted_for_recovery BLOB NOT NULL,
      key_version                  INTEGER NOT NULL DEFAULT 1,        -- future rotation
      pack_id                      TEXT NOT NULL UNIQUE,              -- Stripe session_id (R4 idempotency key)
      payment_intent_id            TEXT,                              -- dispute fallback (R3a)
      created_at                   INTEGER NOT NULL,
      expires_at                   INTEGER NOT NULL,
      used                         INTEGER NOT NULL DEFAULT 0,
      used_at                      INTEGER,
      disputed                     INTEGER NOT NULL DEFAULT 0,        -- distinct from used
      disputed_at                  INTEGER                            -- distinct from used_at
  );
  -- NOTE: MAX_TOKENS_PER_SESSION = 25 enforced in mint_tokens_if_absent (app-level)
  CREATE INDEX idx_tokens_pack_id ON tokens(pack_id);
  CREATE INDEX idx_tokens_payment_intent ON tokens(payment_intent_id);

  CREATE TABLE failed_mints (
      session_id    TEXT NOT NULL,
      pack          TEXT NOT NULL,
      error         TEXT NOT NULL,
      attempt_count INTEGER NOT NULL DEFAULT 1,
      created_at    INTEGER NOT NULL,
      PRIMARY KEY (session_id, attempt_count)
  );
  ```
  Note: `jobs.token_hash` is intentionally NOT a FK — it is a historical audit record; cleanup of consumed-and-30-days-old tokens leaves orphan strings in `jobs` which is acceptable.

- **`_get_conn(db_path)`** mirrors `job_store._get_conn` but **adds `PRAGMA busy_timeout=5000`**. All write paths wrap `BEGIN IMMEDIATE` in try/except for `sqlite3.OperationalError` (message containing "locked") → caller maps to 503 with retry hint.

- **`mint_tokens_if_absent(session_id, count, payment_intent_id, db_path=None) -> MintResult`**:
  1. Raise `ValueError` if `count > MAX_TOKENS_PER_SESSION`
  2. `BEGIN IMMEDIATE` (RESERVED lock; serializes against any concurrent writer)
  3. `SELECT token_encrypted_for_recovery, key_version FROM tokens WHERE pack_id=? ORDER BY rowid`
  4. **If rows exist:** decrypt each via `get_fernet(key_version).decrypt(...)`, return `MintResult(tokens=[...], from_cache=True)`. COMMIT.
  5. **Otherwise:** generate `count` token strings via `crypto.mint_token()`; for each, INSERT row with all columns set. `INSERT OR IGNORE` defends against the (theoretically impossible under IMMEDIATE) race. **If any row's rowcount=0: log ERROR (invariant violation), re-SELECT inside same txn, return DB-authoritative rows.** Never return locally-generated tokens after an IGNORE collision.
  6. Assert post-INSERT SELECT returns exactly `count` rows. COMMIT. Return `MintResult(tokens=[...], from_cache=False)`.

- **`validate_and_consume(token, db_path=None) -> TokenValidationResult`**:
  1. Compute `token_hash = compute_token_hash(token)`
  2. `BEGIN IMMEDIATE`
  3. `UPDATE tokens SET used=1, used_at=? WHERE token_hash=? AND used=0 AND disputed=0 AND expires_at>?`
  4. **If rowcount=1:** COMMIT, return `TokenValidationResult(ok=True)`
  5. **If rowcount=0:** disambiguation SELECT inside same txn:
     - No row → `INVALID_OR_EXPIRED` (does NOT distinguish unknown from expired — security)
     - Row exists with `disputed=1` → `DISPUTED`
     - Row exists with `used=1, disputed=0` → `ALREADY_USED`
     - Row exists with `expires_at <= now` → `INVALID_OR_EXPIRED`
  6. ROLLBACK, return appropriate error code.

- **`mark_disputed(pack_id, db_path=None) -> int`**:
  - `BEGIN IMMEDIATE`
  - `UPDATE tokens SET disputed=1, disputed_at=? WHERE pack_id=?` — does NOT modify `used` or `used_at`
  - Returns rowcount. COMMIT.

- **`record_failed_mint(session_id, pack, error_str, db_path=None) -> None`**:
  - INSERT into `failed_mints`; on conflict, UPDATE `attempt_count = attempt_count + 1`.

- **`cleanup_expired_tokens(db_path=None) -> int`**:
  - DELETE rows WHERE `used=1 AND expires_at < now - 30*24*3600`. Returns deleted rowcount.
  - WAL snapshot isolation guarantees no in-flight reader sees a row mid-delete; `used=1` filter ensures we never delete a token that could still be validated.

- **`cleanup_failed_mints(db_path=None) -> int`** (Phase 2 sweep target):
  - DELETE WHERE `created_at < now - 7*24*3600` (one-week retention for admin investigation).

- **`circuit_breaker.py`** — module-level state:
  - `_consecutive_failures: int = 0`, `_circuit_open_until: float = 0`
  - `def db_call_failed()`: increments counter; if `>= 5` and last failure within 60s, set `_circuit_open_until = now() + 30`
  - `def db_call_succeeded()`: resets counter
  - `def circuit_is_open() -> bool`: returns `now() < _circuit_open_until`
  - Used by webhook + success-page handlers to short-circuit to 503 during DB outage.

**Patterns to follow:**
- `web_service/job_store.py` `_get_conn` + `_SCHEMA_SQL` + idempotent `init_db()` + `db_path` injection
- `web_service/validation.py:ValidationResult` for `MintResult`, `TokenValidationResult`, `ValidationError` shapes
- `web_service/pipeline_runner.py:RunResult` for frozen dataclass result shape

**Test scenarios:**
- **Happy path** — `mint_tokens_if_absent("cs_test_xxx", 3, "pi_test_abc")` returns 3 unique tokens matching regex; rows persisted with `used=0, disputed=0, key_version=1`
- **Happy path** — `validate_and_consume(token)` fresh → `ok=True`; subsequent call → `ALREADY_USED`
- **Critical invariant** — Two concurrent `mint_tokens_if_absent` for same session_id: only one set of tokens persists; both calls return identical token lists (race-loser SELECTs winner's rows). Verify with `threading.Thread` ×2 + `barrier` synchronization to maximize race likelihood.
- **Critical invariant** — Simulate `INSERT OR IGNORE rowcount=0` by manually inserting a conflicting row mid-txn (via a second connection without BEGIN IMMEDIATE — pathological but possible): assert function logs ERROR + re-SELECTs + returns DB-authoritative tokens, NOT locally-generated ones.
- **Critical invariant** — Two concurrent `validate_and_consume` on same token: exactly one returns `ok=True`, the other returns `ALREADY_USED`. Verify under `threading.Thread` ×2 with barrier.
- **Edge case** — `count=26` raises `ValueError("count exceeds MAX_TOKENS_PER_SESSION")`
- **Edge case** — Token with `expires_at == now` returns `INVALID_OR_EXPIRED` (strict >)
- **Edge case** — `validate_and_consume("lb_pk_doesntexist...")` returns `INVALID_OR_EXPIRED` (NOT distinguishable from expired — security)
- **Edge case** — `validate_and_consume("not_a_token")` returns `MALFORMED` (regex fail, no DB hit)
- **Edge case** — Token on row with `disputed=1, used=0`: returns `DISPUTED`
- **Edge case** — Token on row with `disputed=1, used=1`: returns `DISPUTED` (dispute precedence over already-used because user paid via chargeback)
- **Error path** — DB locked beyond busy_timeout raises `sqlite3.OperationalError`; caller catches and maps to 503
- **Integration** — `init_db()` runs twice → idempotent
- **Integration** — `mint_tokens_if_absent` followed by `validate_and_consume` on returned token: succeeds; encrypted-recovery column still decrypts to original raw token (recovery survives consumption)
- **Edge case** — `cleanup_expired_tokens` deletes only `used=1 AND expires_at < now - 30d`; unused-expired rows retained
- **Edge case** — `cleanup_failed_mints` deletes only rows `> 7 days old`
- **Edge case** — `derive_fernet_key(secret, key_version=1)` ≠ `derive_fernet_key(secret, key_version=2)` (domain separation via info param)
- **Edge case** — `mark_disputed(pack_id)` sets `disputed=1, disputed_at=now`, leaves `used` and `used_at` unchanged
- **Server-restart simulation** — Concurrent mint test where one process is SIGKILL'd between SELECT and INSERT: survivor either sees complete row set or successfully mints its own (no half-committed state)
- **Circuit breaker** — 5 consecutive `db_call_failed()` within 60s → `circuit_is_open()` returns True for 30s; after 30s, half-open probe; `db_call_succeeded()` resets

**Verification:**
- All test scenarios pass; `pytest tests/test_web_token_store.py tests/test_web_crypto.py tests/test_web_circuit_breaker.py -v` 100% green
- Manual concurrency stress: 100 threads mint+validate against same DB → no double-spend, no orphans, no SQLITE_BUSY beyond 5000ms

---

- [ ] **Unit 3: Token validation module + Stripe Checkout session endpoint**

**Goal:** Pure-function `token_validation.validate_token_format(token)` mirroring `validation.validate_upload` shape; `POST /stripe/create-session` route creating Checkout session with **`payment_intent_data.metadata.checkout_session_id`** (critical for dispute propagation); idempotent `stripe_bootstrap.py` script.

**Requirements:** R2, R10, R3a (dispute propagation via PI metadata), Token Format Specification

**Dependencies:** Unit 1, Unit 2

**Files:**
- Create: `web_service/token_validation.py`
- Create: `web_service/routes/checkout.py`
- Create: `deploy/stripe_bootstrap.py`
- Test: `tests/test_web_token_validation.py`
- Test: `tests/test_web_checkout.py`
- Modify: `web_service/main.py` (include_router for checkout)

**Approach:**

- `token_validation.py`:
  - `TokenValidationErrorCode(str, Enum)`: `MALFORMED`, `INVALID_OR_EXPIRED`, `ALREADY_USED`, `DISPUTED`
  - `validate_token_format(token: str) -> TokenValidationResult` — pure regex match against `^lb_pk_[A-Za-z0-9_-]{43}$`. Returns structured result with `TokenValidationErrorCode.MALFORMED` on failure.

- `checkout.py` route (sketch):
  ```python
  @router.post("/stripe/create-session", status_code=200)
  async def create_checkout_session(pack: str = Form(...)):
      if pack not in {"starter", "standard", "power"}:
          raise HTTPException(422, detail={"error": "invalid pack", "code": "INVALID_PACK"})
      price_id = {"starter": settings.stripe_price_starter, "standard": ..., "power": ...}[pack]
      # CRITICAL: payment_intent_data.metadata propagates session_id to the resulting Charge
      # so charge.dispute.created can resolve back to session_id via PI retrieve.
      session = await loop.run_in_executor(
          billing_executor,
          lambda: stripe.checkout.Session.create(
              mode="payment",
              line_items=[{"price": price_id, "quantity": 1}],
              success_url="https://leafbind.io/payment/success?session_id={CHECKOUT_SESSION_ID}",
              cancel_url="https://leafbind.io/pricing",
              customer_creation="if_required",
              payment_intent_data={
                  "receipt_email": None,                              # privacy: disable Stripe receipts
                  "metadata": {"checkout_session_id": "<filled after create>"},  # NOTE: see below
              },
              metadata={"pack": pack},
          ),
      )
      # After creation, update PaymentIntent metadata with session.id (PI metadata isn't writable in initial create — use a second call)
      # ALTERNATIVE: use `client_reference_id=session.id` as a stable echo; verify against Stripe SDK behavior during implementation
      return {"checkout_url": session.url, "session_id": session.id}
  ```
  **Implementation note for dispute propagation:** `payment_intent_data.metadata` is set on the PaymentIntent at session creation. The resulting Charge's metadata is independent unless explicitly propagated. Two viable patterns:
  1. **Set `metadata` on `payment_intent_data` at session creation** — propagates to PI but not automatically to Charge. The dispute handler reads `event["data"]["object"]["payment_intent"]`, calls `stripe.PaymentIntent.retrieve(pi_id)`, reads `pi.metadata["checkout_session_id"]`. Single-hop lookup.
  2. **Update PI metadata on `checkout.session.completed` webhook** — set `metadata.checkout_session_id` via `stripe.PaymentIntent.modify(pi_id, metadata={...})` once we have both IDs.
  Recommend pattern 1 (simpler, no second API call). Verify against Stripe SDK v12.x docs during implementation; the alternative pattern 2 is the fallback.

- `stripe_bootstrap.py`: idempotent script — reads `STRIPE_SECRET_KEY`, creates Products + Prices for the three packs ($2.99, $7.99, $14.99 USD), prints IDs in `STRIPE_PRICE_STARTER=price_xxx` format. Looks up by Product `name` before creating to avoid duplicates.

**Patterns to follow:**
- `web_service/routes/convert.py` route module shape, HTTPException pattern
- `web_service/validation.py:ValidationResult` for `TokenValidationResult`
- `web_service/job_queue.py:_executor` for executor pattern (use `billing_executor` here)

**Test scenarios:**
- **Happy path** — `validate_token_format("lb_pk_" + "A"*43)` returns `ok=True`
- **Edge case** — `validate_token_format("lb_pk_" + "A"*42)` → `MALFORMED` (one char short)
- **Edge case** — `validate_token_format("lb_pk_" + "@"*43)` → `MALFORMED` (invalid char)
- **Edge case** — `validate_token_format("sk_live_xxx")` → `MALFORMED` (wrong prefix)
- **Happy path** — `POST /stripe/create-session` with `pack=starter` → 200 + `{checkout_url, session_id}` (Stripe SDK mocked)
- **Critical** — Mocked Stripe call receives `payment_intent_data.metadata.checkout_session_id = session.id` (verify the dispute-propagation wiring)
- **Critical** — Mocked Stripe call receives `mode="payment"`, `customer_creation="if_required"`, `payment_intent_data.receipt_email=None` (privacy bypass)
- **Edge case** — `pack=invalid` → 422 + `INVALID_PACK`
- **Error path** — Stripe SDK raises `StripeError` → 503 with `code=STRIPE_API_ERROR`
- **Edge case** — `bootstrap.py` run twice with existing Products → no duplicates created; prints same Price IDs

**Verification:**
- All tests pass
- Manual: `stripe_bootstrap.py` against test mode creates Products + Prices; output is paste-ready for `.env`
- Manual: trigger a test Checkout → verify resulting PaymentIntent has `metadata.checkout_session_id` set (Stripe Dashboard inspection)

---

- [ ] **Unit 4: Stripe webhook handler + idempotent mint + dispute handler with PI metadata lookup**

**Goal:** Implement `POST /stripe/webhook` with signature validation, `checkout.session.completed` mint (via shared `mint_tokens_if_absent`), `charge.dispute.created` revocation (via PaymentIntent metadata lookup — **this fixes the dispute-metadata bug**), structured logging, circuit breaker integration, livemode assertion, and middleware-safety documentation.

**Requirements:** R3, R3a (chargeback handling), R4 (mint logic shared with success page)

**Dependencies:** Unit 2 (token_store + circuit_breaker), Unit 3 (checkout endpoint sets the PI metadata)

**Execution note:** **Test-first** for signature validation, race-condition scenarios, and the dispute handler PI metadata lookup. The CVE-2026-41432 mitigation must have an explicit test (startup with empty `STRIPE_WEBHOOK_SECRET` must raise `ConfigurationError`).

**Files:**
- Create: `web_service/routes/webhook.py`
- Test: `tests/test_web_webhook.py`
- Modify: `web_service/main.py` (include_router; lifespan adds startup assertion for middleware stack)
- Modify: `web_service/job_queue.py` (add `billing_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='billing')`)

**Approach:**

- Module docstring on `webhook.py`:
  > **WARNING:** This route requires raw request body for Stripe signature validation. Do NOT add middleware upstream that consumes `request.stream()`. The current middleware stack (CORSMiddleware) is header-only and safe. A startup assertion in `main.py` lifespan iterates `app.user_middleware` and warns on body-consuming middleware additions.

- Webhook handler (sketch):
  ```python
  @router.post("/stripe/webhook")
  async def stripe_webhook(request: Request):
      # JSONDecodeError is a ValueError subclass — single catch covers both.
      if circuit_breaker.circuit_is_open():
          raise HTTPException(503, detail={"error": "service degraded, retry"})

      payload = await request.body()      # RAW BYTES; cached by Starlette after first call
      sig = request.headers.get("stripe-signature", "")
      try:
          event = stripe.Webhook.construct_event(
              payload, sig, settings.stripe_webhook_secret, tolerance=300
          )
      except (ValueError, stripe.error.SignatureVerificationError) as e:
          log.warning(
              "webhook_signature_failure",
              extra={"source_ip": request.client.host, "sig_header": sig[:40], "payload_len": len(payload), "err": str(e)[:200]},
          )
          metrics.webhook_signature_failures.inc()
          raise HTTPException(400, detail={"error": "invalid signature"})

      # Production safety: reject test-mode events in production. livemode flag is set by Stripe.
      if os.environ.get("APP_ENV") == "production" and not event.get("livemode"):
          log.error("test_event_in_production", extra={"event_id": event.get("id")})
          raise HTTPException(400, detail={"error": "test event in production"})

      # Defensive: use .get() to avoid KeyError → 500 → Stripe retry storm
      data = event.get("data", {})
      obj = data.get("object", {})
      event_type = event.get("type", "unknown")

      now = time.time()
      drift = abs(now - event.get("created", now))
      if drift > 60:
          log.warning("webhook_clock_drift_warn", extra={"drift_seconds": drift})

      if event_type == "checkout.session.completed":
          session_id = obj.get("id")
          payment_intent_id = obj.get("payment_intent")
          pack = obj.get("metadata", {}).get("pack", "starter")
          count = {"starter": 3, "standard": 10, "power": 25}.get(pack, 0)
          if not session_id or count == 0:
              log.warning("malformed_checkout_event", extra={"event_id": event.get("id")})
              return {"received": True}  # 200 to stop Stripe retries on permanently-bad events

          try:
              await loop.run_in_executor(
                  billing_executor,
                  token_store.mint_tokens_if_absent, session_id, count, payment_intent_id,
              )
              circuit_breaker.db_call_succeeded()
          except sqlite3.OperationalError as e:
              circuit_breaker.db_call_failed()
              log.error("mint_failed", extra={"session_id": session_id, "err": str(e)[:200]})
              await loop.run_in_executor(billing_executor, token_store.record_failed_mint, session_id, pack, str(e))
              # Return 500 to trigger Stripe's free retry budget (~3 days exponential backoff)
              raise HTTPException(500, detail={"error": "transient db failure, will retry"})

      elif event_type == "charge.dispute.created":
          # CRITICAL: Charge metadata is independent of Session metadata.
          # Resolve session_id via PaymentIntent metadata (set in Unit 3 at session creation).
          payment_intent_id = obj.get("payment_intent")
          if not payment_intent_id:
              log.warning("dispute_no_pi", extra={"event_id": event.get("id")})
              return {"received": True}
          try:
              pi = await loop.run_in_executor(
                  billing_executor,
                  lambda: stripe.PaymentIntent.retrieve(payment_intent_id),
              )
              session_id = pi.metadata.get("checkout_session_id")
              if not session_id:
                  # Fallback: search token_store by payment_intent_id
                  session_id = await loop.run_in_executor(
                      billing_executor,
                      token_store.find_session_by_payment_intent, payment_intent_id,
                  )
              if session_id:
                  await loop.run_in_executor(billing_executor, token_store.mark_disputed, session_id)
                  log.info("dispute_processed", extra={"session_id": session_id, "pi_id": payment_intent_id})
              else:
                  log.error("dispute_unresolvable", extra={"pi_id": payment_intent_id})
          except stripe.error.StripeError as e:
              circuit_breaker.db_call_failed()
              raise HTTPException(500, detail={"error": "stripe upstream error"})

      else:
          # Unknown event types: 200 to stop retries; no side effects.
          pass

      return {"received": True}
  ```

- Lifespan startup assertion in `main.py`:
  ```python
  # Iterate registered middleware; warn if any are body-consuming (best-effort heuristic)
  for mw in app.user_middleware:
      cls_name = mw.cls.__name__ if hasattr(mw, "cls") else type(mw).__name__
      if cls_name not in {"CORSMiddleware"}:
          log.warning("non_allowlisted_middleware", extra={"middleware": cls_name})
  ```

- Cloudflare rate-limit rule (operational, NOT in code): >30 req/min from any single source IP to `/stripe/webhook` → challenge/block. Configured via Cloudflare Dashboard; documented in `deploy/README.md`.

- nginx config (deployed in Unit 8): `client_max_body_size 256k` on `/stripe/webhook` location block (headroom for future event subscriptions; DoS-bounded by Cloudflare rate-limit upstream).

**Patterns to follow:**
- `web_service/routes/convert.py` route module shape
- External research: Stripe Webhook signature validation pattern (https://docs.stripe.com/webhooks/signatures)

**Test scenarios:**
- **Happy path** — Valid signed `checkout.session.completed` → 200 OK, `mint_tokens_if_absent` called with correct `session_id`, `count`, `payment_intent_id`
- **Happy path** — Valid signed `charge.dispute.created` with metadata.checkout_session_id on PI → 200 OK, `mark_disputed` called with correct `session_id`
- **Critical** — `charge.dispute.created` WITHOUT metadata.checkout_session_id on PI → fallback to `find_session_by_payment_intent(payment_intent_id)` succeeds; `mark_disputed` called
- **Critical** — `charge.dispute.created` with neither PI metadata nor matching payment_intent_id in DB → log ERROR, return 200, no side effects
- **Edge case** — Invalid signature → 400 with structured WARN log capturing source_ip + sig_header + payload_len
- **Edge case** — Timestamp >5 min old → 400 (replay mitigation)
- **Edge case** — `STRIPE_WEBHOOK_SECRET` empty at startup → `ConfigurationError` raised (CVE-2026-41432 mitigation; assert startup fails)
- **Edge case** — Webhook arrives BEFORE success page → mint occurs in webhook path; success page later SELECTs and re-displays
- **Edge case** — Webhook arrives AFTER success page → `mint_tokens_if_absent` finds existing rows, returns them, no INSERT
- **Edge case** — Stripe retries webhook 3x for same event → second/third hit existing rows, return 200 idempotently
- **Edge case** — Production mode + test-mode event (`livemode=false`) → 400 with `test_event_in_production` ERROR log
- **Edge case** — Unknown event type (e.g., `customer.created`) → 200 with no side effects
- **Edge case** — Malformed event (missing `data.object.id`) → 200 with WARN log (defensive `.get()` prevents KeyError)
- **Edge case** — DB write fails after signature validation → 500 returned + `failed_mints` row written + circuit breaker counter incremented
- **Edge case** — Circuit breaker open (>5 consecutive failures in 60s) → 503 short-circuit response without DB hit
- **Edge case** — Clock drift >60s → WARN log emitted; webhook still processes (drift <5min)
- **Integration** — Concurrent webhook + success-page for same session: only one set of tokens persists, both paths return successfully (covers race-loser invariant)
- **Integration** — Webhook process killed mid-mint: survivor (Stripe retry OR success-page) completes mint cleanly
- **Integration** — Body-consuming dummy middleware registered → startup assertion logs WARN
- **Integration** — Executor pool isolation: spawn 3 long-running tasks on `conversion_executor`; webhook still completes within 30s on `billing_executor`

**Verification:**
- All tests pass
- Manual: `stripe listen --forward-to localhost:8000/stripe/webhook` + `stripe trigger checkout.session.completed` → tokens minted; PI metadata.checkout_session_id verified in Stripe Dashboard
- Manual: `stripe trigger charge.dispute.created` after a mint → tokens marked `disputed=1, disputed_at=now`
- Manual: clock skew injection (`timedatectl set-time +6min`) → webhook 400s with drift detection
- Production cutover: register webhook endpoint in Stripe Dashboard; first 10 real events flow cleanly

---

- [ ] **Unit 5: Payment endpoints — success, cancel; XSS-safer token injection**

**Goal:** Implement `/payment/success` (idempotent revisit, server-rendered with `<script type="application/json">` token injection) and `/payment/cancel`. Headers enforce `Referrer-Policy: no-referrer` + `Cache-Control: private, no-store`. The `/recover` API endpoint lives in Unit 6.

**Requirements:** R4, R5, R8a, R8b, R8d, R11, R12, R4a (mint-failure recovery)

**Dependencies:** Unit 2 (token_store), Unit 4 (shared mint logic)

**Files:**
- Create: `web_service/routes/payment.py`
- Test: `tests/test_web_payment.py`
- Modify: `web_service/main.py` (include_router)

**Approach:**

- `GET /payment/success?session_id=<id>`:
  1. Validate `session_id` shape (starts with `cs_`)
  2. Check circuit breaker; if open → 503
  3. SELECT by pack_id in `token_store`. If rows exist → decrypt all via `crypto.get_fernet(key_version).decrypt(...)` for each row's `key_version` → render
  4. Otherwise: call `stripe.checkout.Session.retrieve(session_id, expand=["line_items", "payment_intent"])` via `billing_executor`. If `payment_status="paid"`, call `mint_tokens_if_absent(session_id, count, payment_intent_id)` → render returned tokens
  5. If Stripe verify fails → 503 with `session_id` shown for retry
  6. If DB write fails after Stripe verify → 500 (parallel to webhook handler) + `record_failed_mint`; user sees "Payment confirmed, tokens generating — refresh in 30 seconds"
  7. If `expires_at` passed → render "tokens expired" notice

- **XSS-safer token injection** (Agent 4 Q9): tokens are rendered into the HTML via a TWO-script pattern:
  ```html
  <script type="application/json" id="leafbind-tokens">
  {{ tokens_json|safe }}  <!-- json.dumps(payload, ensure_ascii=True) -->
  </script>
  <script>
  // Separate script reads the JSON block and writes to localStorage.
  // No string interpolation into JS context — eliminates </script> injection class.
  const data = JSON.parse(document.getElementById('leafbind-tokens').textContent);
  try {
    localStorage.setItem('leafbind.tokens', JSON.stringify(data));
  } catch (e) { /* ignore quota/private-mode errors */ }
  </script>
  ```
  The `tokens_json` payload is `json.dumps({tokens: [...], session_id, expires_at}, ensure_ascii=True)`. The regex-constrained token alphabet (`[A-Za-z0-9_-]`) and Stripe-issued session_id make injection unlikely, but `type="application/json"` is the safe-by-default pattern regardless.

- Response headers: `Referrer-Policy: no-referrer`, `Cache-Control: private, no-store`

- Server-rendered HTML uses FastAPI's `HTMLResponse` with f-string templating (lightweight; the page is simple). Inline style objects matching Phase 1 color palette.

- `GET /payment/cancel`: static HTML, single paragraph, link to `/pricing`, footer link to `/recover`

**Patterns to follow:**
- `web_service/routes/download.py` `FileResponse` + `BackgroundTasks` pattern
- Phase 1 frontend `app/page.tsx` inline-style aesthetic and color palette
- Agent 4 Q9 finding: `<script type="application/json">` XSS-safer pattern

**Test scenarios:**
- **Happy path** — `GET /payment/success?session_id=cs_test_xxx` (tokens in DB via webhook) → 200, HTML contains tokens, `Referrer-Policy: no-referrer` header
- **Happy path** — `GET /payment/success?session_id=cs_test_xxx` (no row, Stripe verify succeeds) → 200, tokens minted, HTML rendered
- **Edge case** — Stripe `payment_status=unpaid` → 200 with "payment not yet confirmed" page
- **Edge case** — Invalid session_id shape → 422
- **Edge case** — Stripe API down → 503 with session_id shown
- **Edge case** — DB write fails after Stripe verify → 500 + `failed_mints` row + user sees "refresh in 30s"
- **Edge case** — Token expired (`expires_at < now`) → 200 with "tokens expired" notice
- **Critical** — Rendered HTML uses `<script type="application/json">` for token injection (verify with HTML parsing in test)
- **Critical** — Token JSON payload is escaped via `json.dumps(..., ensure_ascii=True)` (verify by injecting a token-shaped value containing `</script>` — should be escaped as `</script>`)
- **Integration** — Revisit 3 times within 7 days → same tokens shown all 3 times
- **Integration** — Revisit after expiry → "tokens expired" notice
- **Happy path** — `GET /payment/cancel` → 200, HTML with link to `/pricing` and `/recover`

**Verification:**
- All tests pass
- Manual end-to-end (test mode): purchase → see tokens → close tab → revisit URL → same tokens
- HTTP headers verified via `curl -I https://leafbind.io/payment/success?session_id=cs_test_xxx`

---

- [ ] **Unit 6: Recover endpoint (FastAPI POST /api/recover) + Conversion integration**

**Goal:** Implement `POST /api/recover` (server-side session_id lookup that 302-redirects to `/payment/success`) AND the `/convert` integration that removes Phase 1 bypass + adds token validation + 4-code error taxonomy. Bundled because both touch the conversion + recovery API surface and share testing.

**Requirements:** R6, R7, R8, R8c (recover endpoint), Phase 1 Bypass Removal (P1 #5)

**Dependencies:** Unit 2, Unit 3

**Files:**
- Create: `web_service/routes/recover.py`
- Modify: `web_service/routes/convert.py`
- Modify: `tests/test_web_endpoints.py` (un-skip the test; add token validation tests)
- Test: `tests/test_web_recover.py`

**Approach:**

- `recover.py`:
  ```python
  @router.post("/api/recover")
  async def recover_tokens(session_id: str = Form(...)):
      if not session_id.startswith("cs_"):
          raise HTTPException(422, detail={"error": "invalid session_id format", "code": "MALFORMED_SESSION_ID"})
      # 302 to canonical recovery URL; no token data returned via this endpoint to avoid duplicating the rendering logic
      return RedirectResponse(url=f"/payment/success?session_id={session_id}", status_code=302)
  ```

- `convert.py` modifications:
  - Remove line 29: `tier = "premium"  # EB-45 Phase 1: bypass tier checks until Phase 2 billing lands`
  - Add `token: str | None = Form(default=None)` parameter
  - After `validation.validate_upload(...)` and BEFORE `job_store.create_job(...)`:
    - If `tier == "premium"`:
      - Token required: if `None` → 422 with `code=MISSING_TOKEN`
      - `token_validation.validate_token_format(token)` → if fails → 422 with `code=TOKEN_MALFORMED`
      - `token_store.validate_and_consume(token)` → if fails → 422 with the specific code (`TOKEN_INVALID_OR_EXPIRED`, `TOKEN_ALREADY_USED`, `TOKEN_DISPUTED`)
    - If `tier == "free"`: ignore token field (free tier doesn't consume tokens)
  - Remove `@pytest.mark.skip` decorator on `test_kfx_on_free_tier_returns_422` in `tests/test_web_endpoints.py`

**Patterns to follow:**
- Existing `validation.validate_upload()` integration pattern in `convert.py:33-45`
- Phase 1 test patterns in `tests/test_web_endpoints.py` `TestConvertEndpoint`

**Test scenarios:**
- **Happy path (free)** — `tier=free, output_format=epub, file=PDF, no token` → 202 with job_id
- **Happy path (premium + token)** — `tier=premium, output_format=kfx, valid unused token` → 202; subsequent call → 422 `TOKEN_ALREADY_USED`
- **Edge case (un-skipped)** — `tier=free, output_format=kfx` → 422 `INVALID_OUTPUT_FORMAT` (bypass removal restores this)
- **Edge case** — `tier=premium, output_format=kfx, NO token` → 422 `MISSING_TOKEN`
- **Edge case** — `tier=premium, malformed token` → 422 `TOKEN_MALFORMED`
- **Edge case** — `tier=premium, unknown token (correct format)` → 422 `TOKEN_INVALID_OR_EXPIRED`
- **Edge case** — `tier=premium, expired token` → 422 `TOKEN_INVALID_OR_EXPIRED` (same code as unknown — security)
- **Edge case** — `tier=premium, already-used token` → 422 `TOKEN_ALREADY_USED`
- **Edge case** — `tier=premium, disputed token` → 422 `TOKEN_DISPUTED` (distinct code, honest message)
- **Integration** — Concurrent `/convert` with same token from two clients → exactly one 202, other 422 `TOKEN_ALREADY_USED`
- **Integration** — `pytest tests/test_web_*.py -v` ZERO skipped tests
- **Edge case** — `git grep -nE 'EB-45 Phase 1|tier bypass|bypass tier'` returns no matches in `web_service/` or `tests/`
- **Recover endpoint** — `POST /api/recover` with valid session_id → 302 to `/payment/success?session_id=<id>`
- **Recover endpoint** — `POST /api/recover` with malformed session_id → 422

**Verification:**
- All tests pass
- `git grep -nE 'tier = "premium"' web_service/ tests/` returns no hits in source
- Manual end-to-end: purchase Starter pack in Stripe test mode → use one of 3 tokens to convert PDF→KFX → succeeds → reuse same token → 422 `TOKEN_ALREADY_USED`

---

- [ ] **Unit 7: Frontend pages + UploadZone token integration**

**Goal:** Build the Next.js frontend pages and integrate the token field into `UploadZone.tsx` (NOT the `UploadForm.tsx` shim). `FormatSelector.tsx` does NOT need modification — it already gates by tier prop.

**Requirements:** R5 (download/print/bookmark UI in success page handled by Unit 5), R8c (Next.js /recover UI), R9, R10, R12

**Dependencies:** Unit 3 (checkout endpoint), Unit 5 (success/cancel endpoints — Next.js does NOT own those paths), Unit 6 (recover API endpoint)

**Files:**
- Create: `web_service/frontend/app/pricing/page.tsx` (Server Component with `metadata` export)
- Create: `web_service/frontend/app/recover/page.tsx` (Server wrapper with `searchParams: Promise<{session_id?: string}>`)
- Create: `web_service/frontend/components/BuyButtons.tsx` (Client child for /pricing)
- Create: `web_service/frontend/components/RecoverClient.tsx` (Client child reading localStorage + session_id paste form)
- Create: `web_service/frontend/components/TokenField.tsx` (Client Component, regex validation on blur, inline error display)
- Create: `web_service/frontend/components/TokenList.tsx` (Client Component, copy/download/print buttons)
- **Modify: `web_service/frontend/components/UploadZone.tsx`** (NOT `UploadForm.tsx`) — add token state, `<details>` collapsible, state-derived tier replacing hardcoded `tier="free"` at line 87
- Modify: `web_service/frontend/lib/api.ts` (add typed `createCheckoutSession`)

**Approach:**

- **Inline `style={}` styling — NO Tailwind.** Color palette: `#0070f3` (primary), `#555` (muted text), `#666` (caption), `#ccc` (border), `#fafafa`/`#f0f7ff` (surface), `red` (error). NO `className=`, NO CSS files.

- **`FormatSelector.tsx` requires NO modification.** It already has `FREE_FORMATS = ["epub","mobi"]` vs `PREMIUM_FORMATS = ["epub","mobi","kfx"]` (`FormatSelector.tsx:9-13`). UploadZone.tsx:87 currently hardcodes `tier="free"` — Phase 2 changes this to state-derived `tier`.

- `/pricing/page.tsx` (Server Component, `metadata` export):
  - Renders 3-pack comparison table inline (Starter / Standard / Power with prices, credit counts, what premium unlocks: KFX output, smart heading detection, footnote linking, 100MB limit)
  - Delegates Buy buttons to `<BuyButtons />` Client child
  - Footer link to `/recover`
  - 7-day token-expiry disclosure

- `BuyButtons.tsx` (Client Component):
  - Three buttons (one per pack)
  - On click: `setCreating(true)`; `disabled={creating}`; label flips to "Redirecting to checkout…"; calls `createCheckoutSession(pack)`; `window.location.href = resp.checkout_url`. **NO 3-second timer-debounce** — the async round-trip prevents double-submission; matches Phase 1's `UploadZone:setUploading(true)` pattern.

- `/recover/page.tsx` (Server wrapper):
  ```typescript
  interface Props { searchParams: Promise<{ session_id?: string }> }
  export const metadata = { title: 'Recover Tokens — Leafbind' };
  export default async function RecoverPage({ searchParams }: Props) {
    const { session_id } = await searchParams;
    return <RecoverClient initialSessionId={session_id} />;
  }
  ```

- `RecoverClient.tsx` (Client Component):
  - On mount, `localStorage.getItem("leafbind.tokens")` → if present, render `TokenList`
  - If empty (or incognito): render "no tokens found on this device" + session_id paste form
  - Paste form: `<input>` + button → calls `POST /api/recover` with session_id → server 302s to `/payment/success?session_id=<id>`
  - `initialSessionId` prop: if present, pre-fills the paste form

- `TokenField.tsx` (Client Component):
  - Controlled input; regex `^lb_pk_[A-Za-z0-9_-]{43}$` on blur
  - Trim whitespace before regex check (clipboard-paste reliability)
  - Inline error: `<p style={{ color: "red", fontSize: "0.9em" }}>{error}</p>` (matching Phase 1 UploadZone error display at line 90)
  - On valid → calls `onValidToken` callback prop

- `TokenList.tsx` (Client Component):
  - Renders tokens with copy buttons
  - "Download tokens.txt" → Blob + `URL.createObjectURL` (client-side, no server hit)
  - "Print" → `window.print()` (CSS print stylesheet shows only token list)

- `UploadZone.tsx` modifications:
  - Add `useState` for `token: string` and `useState` for `tokenError: string | null`
  - Derived `tier: "free" | "premium"` = `tokenValid ? "premium" : "free"` (replaces hardcoded `tier="free"` at line 87)
  - Add `<details><summary style={{cursor: "pointer", color: "#0070f3"}}>I have a token</summary>...<TokenField onValidToken={setToken} />...</details>` collapsible section below FormatSelector
  - Pass `tier` to `FormatSelector` (which already gates by it)
  - Pass `token` to `startConversion(file, outputFormat, tier, token)` (extend `lib/api.ts` signature)

- `lib/api.ts` additions:
  ```typescript
  export interface CheckoutResponse {
    checkout_url: string;
    session_id: string;
  }
  export async function createCheckoutSession(pack: string): Promise<CheckoutResponse> {
    // Mirror startConversion shape: POST form data, throw on non-2xx via existing error pattern.
  }
  ```
  Extend `startConversion` to accept optional `token` parameter.

- `/payment/success` and `/payment/cancel` are FastAPI-only (Unit 5). **No Next.js pages exist at those paths.** If frontend + backend share a domain via nginx reverse proxy, ensure `/payment/*` routes upstream to FastAPI before Next.js catch-all.

**Patterns to follow:**
- `web_service/frontend/app/page.tsx` Server Component pattern (with `metadata` export)
- `web_service/frontend/app/status/[id]/page.tsx` Next.js 15 `params: Promise<>` / `searchParams: Promise<>` pattern
- `web_service/frontend/components/UploadZone.tsx` Client Component with `useState` form state
- `web_service/frontend/lib/api.ts` typed fetch wrapper, error envelope unwrap pattern at lines 32-35

**Test scenarios:**
- Component tests deferred to manual smoke (no Jest set up in Phase 1; introducing it for Phase 2 is out of scope — file separate ticket)
- **Manual happy path** — `/pricing` renders 3 packs; click Starter → button disabled + "Redirecting to checkout…" → Stripe Checkout opens
- **Manual edge case** — Click Starter rapidly → button disabled prevents second invocation
- **Manual edge case** — `/recover` with empty localStorage → "no tokens" + paste-box; paste session_id → redirected to `/payment/success` with tokens
- **Manual edge case** — `/recover` with localStorage tokens → TokenList with copy/download/print
- **Manual edge case** — `/recover?session_id=cs_test_xxx` (URL-pasted session_id) → paste-box pre-filled
- **Manual happy path** — UploadZone: enter valid token → tier auto-switches to premium, KFX unlocks, submit → conversion succeeds
- **Manual edge case** — Enter malformed token → inline `<p style={{color: "red"}}>` error appears, tier stays "free"
- **Manual edge case** — Enter valid-format unknown token → tier switches, KFX unlocks, submit → 422 `TOKEN_INVALID_OR_EXPIRED` rendered as UI error
- **Manual edge case** — Enter token with leading/trailing whitespace → trimmed before regex check, accepted

**Verification:**
- `npm run build --prefix web_service/frontend` completes without TypeScript errors
- Manual end-to-end test mode: complete Stripe Checkout → tokens on success page → close browser → revisit URL → tokens still there → new browser → `/recover` → "no tokens" → paste session_id → tokens recovered
- DevTools: `localStorage["leafbind.tokens"]` set after success page render
- DevTools: NetworkTab shows correct API calls (POST /stripe/create-session, POST /api/recover)

---

- [ ] **Unit 8: Deployment — env vars, systemd, nginx, Cloudflare, Stripe Dashboard, cleanup sweeps**

**Goal:** Wire all Phase 2 secrets into `/etc/web_service.env`, register Stripe webhook endpoint, configure nginx + Cloudflare hardening, start token cleanup + failed_mints sweeps, verify end-to-end live.

**Requirements:** R3 (webhook registration), Token Cleanup, Mint-failure cleanup, Operational hardening

**Dependencies:** All preceding units

**Files:**
- Modify: `web_service/job_queue.py` (add `cleanup_expired_tokens` + `cleanup_failed_mints` sweep tasks + `billing_executor` pool)
- Modify: `web_service/main.py` (lifespan starts the new sweep tasks + initializes billing_executor)
- Modify: `deploy/nginx.conf` (add `/stripe/webhook` location with `client_max_body_size 256k`)
- Modify: `deploy/README.md` (Stripe Dashboard webhook walkthrough + Cloudflare rate-limit + NTP check)

**Approach:**

- `cleanup_expired_tokens` mirrors `cleanup_expired_jobs`: hourly sweep, runs in `billing_executor`.
- `cleanup_failed_mints` runs daily; removes `failed_mints` rows older than 7 days.
- `main.py` lifespan creates `billing_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='billing')`, exposes via module-level for import by routes.
- nginx config — add `location = /stripe/webhook { ... }` block ABOVE catch-all `location /`:
  ```nginx
  location = /stripe/webhook {
      proxy_pass http://127.0.0.1:8001;
      client_max_body_size 256k;       # CVE-2026-40481 + future event-subscription headroom
      include /etc/nginx/proxy_params;
  }
  ```
- Cloudflare rate-limit rule (Dashboard, NOT in repo code): `>30 req/min from any single source IP to /stripe/webhook → challenge`. Documented in `deploy/README.md`.

- **VM-side operational steps (USER actions, credential-write hook blocks Claude):**
  1. SSH to `claude-dev-01`
  2. `git pull origin master` (after Phase 2 PR merges)
  3. Verify NTP: `timedatectl status` shows `System clock synchronized: yes`
  4. Generate secrets: `openssl rand -hex 32` for `TOKEN_HMAC_SECRET`
  5. Run `deploy/stripe_bootstrap.py` against Stripe test mode → obtain `STRIPE_PRICE_*` IDs
  6. Add all 7 env vars to `/etc/web_service.env` manually:
     - `STRIPE_SECRET_KEY=sk_test_...`
     - `STRIPE_PUBLISHABLE_KEY=pk_test_...`
     - `STRIPE_WEBHOOK_SECRET=whsec_...` (from Stripe Dashboard endpoint registration)
     - `TOKEN_HMAC_SECRET=<openssl rand -hex 32>`
     - `STRIPE_PRICE_STARTER=price_...`, `STRIPE_PRICE_STANDARD=price_...`, `STRIPE_PRICE_POWER=price_...`
  7. Stripe Dashboard: register webhook endpoint `https://leafbind.io/stripe/webhook`, subscribe to `checkout.session.completed` + `charge.dispute.created`, copy signing secret
  8. Cloudflare Dashboard: add rate-limit rule on `/stripe/webhook` (30/min/IP → challenge)
  9. `sudo cp deploy/nginx.conf /etc/nginx/sites-available/leafbind` → `sudo nginx -t && sudo systemctl reload nginx`
  10. `sudo systemctl restart ebookweb.service`
  11. Verify: `curl https://leafbind.io/health` returns `{"status":"ok"}`; `stripe trigger checkout.session.completed` → tokens appear in DB
  12. Live-mode switch: swap `sk_test_` → `sk_live_` keys, register NEW live-mode webhook endpoint in Stripe Dashboard, update `STRIPE_WEBHOOK_SECRET` to new `whsec_live_*`, restart service, real $2.99 purchase test

**Patterns to follow:**
- Phase 1 deployment pattern: systemd `EnvironmentFile=/etc/web_service.env`, drop-in override at `/etc/systemd/system/ebookweb.service.d/override.conf` (already in place)
- nginx config style from existing `deploy/nginx.conf`

**Test scenarios:**
- **Manual happy path** — End-to-end test mode purchase produces tokens visible on success page within 5 seconds
- **Manual edge case** — Webhook arrives before user redirects → tokens already minted by webhook; success page renders existing tokens
- **Manual edge case** — `stripe trigger charge.dispute.created` after a mint → tokens for that session have `disputed=1`
- **Manual edge case** — Token >30 days past `expires_at` with `used=1` → deleted by next cleanup sweep
- **Manual edge case** — `failed_mints` row >7 days old → deleted by daily cleanup
- **Operational** — `curl -X POST https://leafbind.io/stripe/webhook -d 'oversized 300KB body'` returns 413 (nginx body cap fires)
- **Operational** — `>30 req/min` from a single IP → Cloudflare rate-limit challenges
- **Operational** — `sudo systemctl restart ebookweb.service` → `/health` returns 200 within 5s
- **Operational** — Clock skew: `sudo timedatectl set-time +6min` → webhook 400s with drift detection

**Verification:**
- Live `/health` returns 200 with `ntp_synced: true`
- Stripe Dashboard webhook delivery log shows green checkmarks
- Manual purchase in Stripe test mode succeeds end-to-end
- `pytest tests/test_web_*.py -v` zero skips, all passing
- `git grep -nE 'EB-45 Phase 1|tier bypass|bypass tier'` returns no matches

---

## System-Wide Impact

- **Interaction graph:**
  - New routes (`/stripe/create-session`, `/stripe/webhook`, `/payment/success`, `/payment/cancel`, `/api/recover`) join existing route module pattern
  - **Two separate executor pools**: `conversion_executor` (3 workers, 120s timeouts) and `billing_executor` (4 workers, fast Stripe + token ops)
  - `cleanup_expired_tokens` + `cleanup_failed_mints` sweep tasks run alongside `cleanup_expired_jobs` in same event loop; all use `billing_executor`
  - Stripe SDK calls (blocking) → all routed through `billing_executor`
  - New `failed_mints` table: written by webhook handler + success-page handler on DB failures; cleaned by daily sweep
  - Circuit breaker is in-memory module state in `circuit_breaker.py`; affects webhook + success-page short-circuit behavior
- **Error propagation:**
  - Token validation failures → structured 422 with `code` enum (4 codes)
  - Stripe API errors at success-page render → 503 with session_id shown + recovery hint; webhook retry eventually completes
  - DB lock beyond `busy_timeout` → `sqlite3.OperationalError` → 503 + circuit breaker increment
  - Webhook DB failure → 500 (triggers Stripe retry budget) + `failed_mints` row + circuit breaker increment
  - Webhook signature failure → 400 + structured WARN log
- **State lifecycle risks:**
  - Token consumed but conversion fails → user loses credit (R7, documented)
  - Mint partial failure → `BEGIN IMMEDIATE` guarantees all-or-nothing
  - Dispute mid-consume race → distinguishable error codes (`DISPUTED` vs `ALREADY_USED`)
  - Cleanup vs active reads → WAL snapshot isolation + `used=1 AND expires_at < now - 30d` filter prevents data loss
- **API surface parity:**
  - `/convert` now requires `token` for premium tier; free-tier callers unaffected
  - `lib/api.ts` adds `createCheckoutSession`; existing exports unchanged
- **Integration coverage (cross-layer scenarios unit tests alone won't prove):**
  - End-to-end Stripe test-mode purchase (manual in Unit 8)
  - Webhook + success-page race for same session (integration test in Unit 4)
  - Concurrent `/convert` double-spend prevention (integration test in Unit 2)
  - `/recover` cross-device flow (manual in Unit 7)
  - Executor pool isolation: long-running conversions don't starve webhooks (integration test in Unit 4)
- **Unchanged invariants:**
  - Existing `/convert`, `/status/{id}`, `/download/{id}`, `/health` semantics unchanged for free-tier callers
  - `web_service.db` schema additions are additive (new `tokens` + `failed_mints` tables, no changes to `jobs`)
  - `pipeline_runner.py`, `validation.py`, `job_store.py` read-only from Phase 2's perspective for free-tier flows
  - Phase 1 CORS, TLS, nginx routing for non-Stripe paths unchanged
  - `FormatSelector.tsx` unchanged (already has tier gate)

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Stripe SDK v15 breaking change accidentally pulled via lockfile | Med | High | Pin `stripe>=12.0.0,<13.0.0`; CI smoke test |
| `TOKEN_HMAC_SECRET` leak (logs, error pages, frontend bundle) | Low | Critical | Never log secret; frozen `Settings`; secret never crosses to frontend |
| Empty `STRIPE_WEBHOOK_SECRET` (CVE-2026-41432) | Low | Critical | `_require_env` fails app startup |
| Webhook + success-page race | Med | Med (fewer tokens shown) | `pack_id UNIQUE` + BEGIN IMMEDIATE serialization + invariant test |
| **Dispute metadata propagation broken (session_id unreachable)** | High (default Stripe behavior) | Critical (chargeback fraud unrevoked) | `payment_intent_data.metadata.checkout_session_id` at session creation + PI lookup in dispute handler + fallback via `payment_intent_id` column |
| **Executor pool exhaustion** (shared with conversions) | High under load | High (webhook timeout → Stripe retries) | Separate `billing_executor(4 workers)` distinct from `conversion_executor(3 workers)` |
| Webhook DB-write failure silently swallowed | High under DB issues | High (paid users with no tokens) | Return 500 → Stripe retries; `failed_mints` table for admin sweep |
| DB lock contention | Med | Low (request 503; user retries) | `busy_timeout=5000`; try/except → 503 |
| Stripe Checkout default email collection breaks "no email" story | High (default behavior) | Low (no PII in our DB) | `customer_creation="if_required"` + `receipt_email=None`; documented |
| Chargeback after token consumed | Cert | Low (fraud cost; documented) | `disputed=1, used=1` audit trail; cost-of-business |
| Encryption key rotation invalidates recovery URLs | Low | Med | `key_version` column enables future MultiFernet rotation; out-of-scope for in-flight 7-day window |
| VM clock skew rejects valid webhooks | Low | Med | NTP startup check + 60s drift WARN; `timedatectl` verification in deploy |
| Test/live secret env mismatch | Med (operator error) | High (all webhooks fail silently) | Startup assertion: `pk_*` prefix matches `sk_*` prefix |
| Replay attack (test event in production) | Low | Med | `livemode` assertion in production blocks test events |
| Body-consuming middleware addition breaks signature validation | Low | High | Module docstring + startup assertion logs WARN on non-allowlisted middleware |
| Server-rendered token XSS via `</script>` injection | Low | Med | `<script type="application/json">` two-script pattern eliminates JS-context escaping |
| Frontend Token paste with whitespace fails regex | Med | Low | `TokenField` trims before regex check |
| `cryptography` library compile failures on Ubuntu 24.04 | Low | Med | Test `pip install cryptography>=48.0.0` during deploy; pin to wheel-available version |
| `stripe_bootstrap.py` run twice creates duplicates | Med | Low | Idempotent (Product lookup by name before create) |
| Token table grows unbounded | Low | Med | `cleanup_expired_tokens` sweep + `cleanup_failed_mints` sweep; Phase 4 disk monitoring |
| Prolonged DB outage exhausts thread pool | Med | High | Circuit breaker: >5 fail/60s → 503 short-circuit for 30s |
| Cloudflare rate-limit too aggressive | Low | Med | Initial 30/min/IP; tune post-launch based on Stripe delivery volume |

**Dependencies / Prerequisites:**
- Stripe account with test + live API keys — required before Unit 3 begins
- `chrony` or `systemd-timesyncd` active on `claude-dev-01` (verify: `timedatectl status`)
- Phase 1 TLS + nginx + systemd setup complete (verified 2026-05-13)
- `TOKEN_HMAC_SECRET` generated via `openssl rand -hex 32` BEFORE service restart
- Cloudflare account access for rate-limit rule (operational, Phase 2 prerequisite)

## Phased Delivery

### Phase 2A — Backend foundations (Units 1, 2, 3)
- Config + dependencies + startup checks
- Token store + crypto + circuit breaker
- Token validation + Stripe Checkout endpoint with PI metadata wiring
- **Gate:** all unit tests pass; `stripe_bootstrap.py` validated against test mode; PI metadata propagation verified end-to-end via Stripe Dashboard inspection

### Phase 2B — Webhook + payment endpoints (Units 4, 5)
- Webhook handler with dispute PI lookup + idempotent mint + circuit breaker
- Payment success/cancel endpoints with `<script type="application/json">` token injection
- **Gate:** webhook delivers `checkout.session.completed` end-to-end via `stripe listen`; `charge.dispute.created` correctly marks tokens disputed

### Phase 2C — Recovery API + Conversion integration (Unit 6)
- `POST /api/recover` endpoint
- Remove Phase 1 bypass + add token validation to `/convert` with 4-code error taxonomy
- **Gate:** un-skipped test passes; `git grep` shows no bypass references; 4-code error taxonomy returns correct codes per scenario

### Phase 2D — Frontend (Unit 7)
- `/pricing`, `/recover` Next.js pages
- TokenField + TokenList + BuyButtons + RecoverClient components
- UploadZone integration with state-derived tier
- **Gate:** `npm run build` succeeds; manual flow on Vercel preview deployment passes

### Phase 2E — Deployment + live verification (Unit 8)
- VM env vars (manual by Joe), Stripe Dashboard webhook + Cloudflare rate-limit, nginx hardening, service restart
- Live test-mode end-to-end purchase + dispute trigger
- **Final gate:** live `https://leafbind.io/pricing` → Stripe Checkout → success page → tokens → /convert → KFX output; `stripe trigger charge.dispute.created` correctly revokes tokens

## Documentation / Operational Notes

- **Pre-launch checklist (operational):**
  - [ ] Stripe account created, test + live keys obtained
  - [ ] `stripe_bootstrap.py` run against test mode; Price IDs captured
  - [ ] `TOKEN_HMAC_SECRET` generated and saved (`openssl rand -hex 32`)
  - [ ] All 7 env vars added to `/etc/web_service.env`
  - [ ] Stripe Dashboard test-mode webhook endpoint registered for `checkout.session.completed` + `charge.dispute.created`; signing secret in `.env`
  - [ ] Cloudflare rate-limit rule on `/stripe/webhook` configured (30/min/IP → challenge)
  - [ ] `timedatectl status` confirms clock sync
  - [ ] nginx config reloaded with new `/stripe/webhook` location block
  - [ ] Service restarted, `/health` returns 200 with `ntp_synced: true`
  - [ ] Manual test-mode purchase end-to-end succeeds
  - [ ] `stripe trigger charge.dispute.created` for a test session correctly marks tokens disputed
  - [ ] Manual env-mismatch check passes (no WARN log on startup)
- **Privacy policy update:** disclose that Stripe collects email at Checkout for receipt purposes; email is stored only by Stripe, NOT by leafbind.io. The leafbind.io database stores only Stripe session IDs, payment intent IDs, and token hashes.
- **Worktree workflow:** Phase 2 code lives in a new worktree branch `worktree/EB-45-phase2-billing`; `web_service/`, `tests/`, `deploy/` are NOT in `exempt_paths`.
- **Live-mode switch checklist:** swap test keys for live keys, register NEW live-mode webhook endpoint in Stripe Dashboard (separate from test-mode), update `STRIPE_WEBHOOK_SECRET` to new `whsec_live_*`, restart service, real $2.99 Starter purchase test (test own card, then refund via Stripe Dashboard).
- **Secret rotation runbook:** to rotate `TOKEN_HMAC_SECRET`: (1) drain in-flight 7-day token window by pausing new purchases for 7 days, (2) generate new secret, (3) bump `key_version=2` in code, (4) update env var, (5) restart service. Existing rows with `key_version=1` will fail to decrypt — acceptable because all tokens past their 7-day expiry. Phase 2 does NOT support rotation within an active window.
- **Structured logging fields emitted in Phase 2** (Phase 4 wires alerts):
  - `webhook_signature_failure` { source_ip, sig_header_prefix, payload_len, err }
  - `mint_failed` { session_id, pack, err }
  - `validate_consume` { token_hash_prefix, code, duration_ms }
  - `stripe_api_call` { endpoint, duration_ms, status }
  - `dispute_processed` { session_id, pi_id }
  - `dispute_unresolvable` { pi_id }
  - `webhook_clock_drift_warn` { drift_seconds }
  - `test_event_in_production` { event_id }
  - `non_allowlisted_middleware` { middleware }
- **Compounding artifacts (post-Phase-2 ship):** file `ce:compound` entries for: (a) HMAC binding scheme with HKDF domain separation + key_version rotation pattern, (b) atomic SQLite single-use consume + race-loser invariant (NEVER return locally-generated tokens after IGNORE collision), (c) Stripe webhook + success-page idempotency design via `pack_id UNIQUE`, (d) Fernet via HKDF-derived key with key_version, (e) dispute metadata propagation via `payment_intent_data.metadata` at session creation (Charge metadata is NOT inherited from Session — single-hop PI retrieve), (f) separate executor pool pattern for fast vs slow operations.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-05-13-eb45-phase2-billing-requirements.md](docs/brainstorms/2026-05-13-eb45-phase2-billing-requirements.md) (commit 994a1b0)
- **Phase 1 plan (pattern reference):** [docs/plans/2026-05-13-001-feat-eb45-freemium-web-service-plan.md](docs/plans/2026-05-13-001-feat-eb45-freemium-web-service-plan.md)
- **Phase 1 PR (tier bypass to remove):** https://github.com/jlfowler1084/EbookAutomation/pull/51 (squash-merged at 6c43558)
- **Stripe Python SDK:** https://pypi.org/project/stripe/ (pin `~=12.5`)
- **Stripe Checkout Sessions API:** https://docs.stripe.com/api/checkout/sessions/create?lang=python
- **Stripe Webhook Signatures:** https://docs.stripe.com/webhooks/signatures
- **Stripe Webhook Best Practices (event ordering, retries):** https://docs.stripe.com/webhooks/best-practices
- **Stripe Disputes API + metadata propagation:** https://docs.stripe.com/api/disputes/object, https://docs.stripe.com/api/charges/object#charge_object-metadata
- **`cryptography` library:** https://pypi.org/project/cryptography/ (pin `~=48.0`)
- **Fernet docs:** https://cryptography.io/en/latest/fernet/
- **HKDF docs:** https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#hkdf
- **Python stdlib `hmac.compare_digest`:** https://docs.python.org/3/library/hmac.html#hmac.compare_digest
- **SQLite isolation under WAL:** https://www.sqlite.org/wal.html#concurrency, https://www.sqlite.org/isolation.html
- **CVE-2026-41432 (empty webhook secret pattern):** https://github.com/advisories/GHSA-xff3-5c9p-2mr4
- **CVE-2026-40481 (webhook body-size DoS):** https://vulnerability.circl.lu/vuln/cve-2026-40481
- **Institutional learning — pre-implementation render check:** [docs/solutions/best-practices/pre-implementation-render-check-2026-04-22.md](docs/solutions/best-practices/pre-implementation-render-check-2026-04-22.md)
- **Institutional learning — stderr capture:** [docs/solutions/eb-142-calibre-stderr-capture.md](docs/solutions/eb-142-calibre-stderr-capture.md)
- **Related ticket:** [EB-45](https://jlfowler1084.atlassian.net/browse/EB-45)
