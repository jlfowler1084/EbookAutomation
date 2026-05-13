---
date: 2026-05-13
topic: eb45-phase2-stripe-billing
status: ready-for-planning
amended: 2026-05-13
---

# EB-45 Phase 2 — Stripe Billing and Premium Tier Unlock

## Problem Frame

Phase 1 shipped the conversion engine: the free tier (Calibre pass-through) runs in
production at `https://leafbind.io` (Let's Encrypt cert active, verified 2026-05-13).
Phase 2 wires in the money: Stripe Checkout, signed credit tokens, and the premium
pipeline unlock. The `/convert` endpoint already accepts a `tier` field but currently
performs no token validation — a deliberate Phase 1 bypass forces `tier="premium"` on
every request. Phase 2 closes that gap (see "Phase 1 Bypass Removal" below) AND adds
real token validation.

The design constraint throughout is **no user accounts**. Credit tokens are stateless
opaque strings keyed by an HMAC secret. Privacy remains the differentiator.

> **Amended 2026-05-13** by the ce:plan deepening pass. Six refinements landed:
> chargeback handling (R3a), race-loser invariant (R4), mint-failure recovery (R4a),
> 4-code error taxonomy (R6), token storage schema extensions (R7), and `/recover`
> ownership clarification (R8c). See plan
> `docs/plans/2026-05-13-002-feat-eb45-phase2-stripe-billing-plan.md` for the
> originating findings.

---

## Payment and Token Flow

```
User → Pricing page → [Buy 3, 10, or 25 credits]
  → POST /stripe/create-session
       └─ Stripe Checkout Session created with
          payment_intent_data.metadata.checkout_session_id = session.id
          (CRITICAL for chargeback handling — propagates session_id to the
          resulting Charge via the PaymentIntent)
  → Stripe Checkout (hosted)
  → User pays
  → Stripe redirects → GET https://leafbind.io/payment/success?session_id=xxx
  → Server verifies session with Stripe API
  → Generates N HMAC-keyed tokens, stores (hash + encrypted-plaintext + key_version
     + payment_intent_id) in token DB
  → Success page displays N token strings + bookmark prompt + download button
  → User copies a token (or bookmarks the page / downloads tokens.txt for recovery)
  → Pastes into token field on conversion form
  → POST /convert (file + token + tier=premium + output_format)
  → Server validates token: regex format → hash lookup → exists, unused,
                            not expired, not disputed
  → Token marked used in same DB transaction (double-spend safe)
  → Premium pipeline runs
  → Job ID returned; user polls /status/{id}; downloads result

Parallel: Stripe webhook delivers checkout.session.completed (idempotent mint via
          pack_id UNIQUE constraint) AND charge.dispute.created (revokes all tokens
          for the disputed pack_id via PaymentIntent metadata lookup).
```

---

## Requirements

**Stripe Checkout**

- R1. Three credit packs offered at launch:
  - Starter: 3 credits for $2.99   ($1.00/credit — low-commit entry, charm-priced)
  - Standard: 10 credits for $7.99 ($0.80/credit — target tier, 20% discount)
  - Power: 25 credits for $14.99   ($0.60/credit — repeat-buyer anchor / decoy)
- R2. `POST /stripe/create-session` accepts `pack` param (`starter` | `standard` | `power`),
  creates a Stripe Checkout Session with `mode="payment"`, `success_url` set to
  `https://leafbind.io/payment/success?session_id={CHECKOUT_SESSION_ID}` (the literal Stripe
  template placeholder), `cancel_url` set to `https://leafbind.io/pricing`,
  `customer_creation="if_required"` and `payment_intent_data.receipt_email=None` (privacy:
  no email enters our DB; Stripe stores it for receipt purposes only). **Critically, the
  Checkout Session creation MUST set `payment_intent_data.metadata.checkout_session_id =
  session.id`** so the chargeback handler (R3a) can resolve session_id from the resulting
  Charge via a PaymentIntent retrieve. Without this, `charge.dispute.created` will silently
  fail to revoke disputed tokens because Charge metadata does NOT inherit from Session
  metadata. Returns the Stripe-hosted Checkout URL.
- R3. Stripe webhook endpoint (`POST https://leafbind.io/stripe/webhook`) subscribes to
  TWO event types: `checkout.session.completed` (mint tokens, R4) and
  `charge.dispute.created` (revoke tokens, R3a). Stripe secret key and webhook signing
  secret are environment variables only. The endpoint must:
  - Validate the `Stripe-Signature` header using `stripe.Webhook.construct_event(payload,
    sig, secret, tolerance=300)` — explicit 5-minute tolerance
  - Reject events outside tolerance (replay attack mitigation)
  - In production mode, assert `event["livemode"] is True` (rejects test-mode events
    accidentally pointed at production)
  - Use raw `await request.body()` for signature validation; module docstring warns
    against adding body-consuming middleware
  - Fail-startup on empty `STRIPE_WEBHOOK_SECRET` via `_require_env` (CVE-2026-41432 class)
  - Defensive `.get()` patterns on event payload to avoid `KeyError` → 500 → Stripe retry
    storms
  - Webhook is registered with Stripe under the leafbind.io HTTPS endpoint (Phase 1 TLS
    verified 2026-05-13).
- **R3a (new — chargeback handling).** On `charge.dispute.created`, resolve session_id via
  PaymentIntent metadata lookup (the single-hop pattern enabled by R2's
  `payment_intent_data.metadata` wiring): read `event["data"]["object"]["payment_intent"]`,
  call `stripe.PaymentIntent.retrieve(pi_id)`, read `pi.metadata["checkout_session_id"]`.
  Fallback: if PI metadata is absent, search `tokens` table by `payment_intent_id` column.
  Once session_id is resolved, call `mark_disputed(pack_id)` which UPDATEs all tokens for
  that pack_id with `disputed=1, disputed_at=now` (does NOT modify `used` or `used_at` —
  preserves audit distinguishability between "legitimately consumed then disputed" and
  "unused but revoked by chargeback"). Refunds remain out of scope; the `disputed` flag
  enables fraud analytics in future phases.

**Token Generation and Delivery**

- R4. On success page load (`GET /payment/success?session_id=xxx`):
  - Server calls Stripe API to verify the session is paid and not already processed.
  - Generates N tokens (one per credit) per the Token Format Specification below.
  - Stores in the token DB: `token_hash` (validation key, R7), `token_encrypted_for_recovery`
    (R8b), `key_version` (future-rotation enablement, default 1), `payment_intent_id`
    (chargeback fallback, R3a), `pack_id` (= Stripe session_id, UNIQUE, R4 idempotency),
    `created_at`, `expires_at` (7 days), `used` (false), `disputed` (false).
  - **Race-loser invariant (clarification):** Both this success-page path AND the webhook
    path (R3) call the same `mint_tokens_if_absent(session_id)` function. Under
    `BEGIN IMMEDIATE`, SQLite serializes writers — the second writer waits up to
    `busy_timeout=5000ms` for the first to COMMIT, then sees the winner's rows on its
    first SELECT. **If `INSERT OR IGNORE` ever returns rowcount=0 (which BEGIN IMMEDIATE
    should prevent), the function MUST log ERROR, re-SELECT inside the same transaction,
    and return DB-authoritative rows. It MUST NEVER return locally-generated tokens after
    an IGNORE collision — those tokens were silently dropped and the user would receive
    phantom tokens that don't exist in the DB.**
  - The `pack_id` UNIQUE constraint guarantees exactly one token set per session;
    `INSERT-or-ignore` (not raw INSERT) is the idempotency primitive.
- **R4a (new — mint-failure recovery).** If a DB write fails after Stripe verification
  succeeds (disk full, lock timeout beyond `busy_timeout`, segfault in cryptography lib),
  the handler MUST:
  - Log to a new `failed_mints(session_id, pack, error, attempt_count, created_at)` table
    (PRIMARY KEY on `session_id + attempt_count`; on conflict UPDATE attempt_count)
  - Return HTTP **500** (not 200) so Stripe's free retry budget (~3 days, ~20 retries
    with exponential backoff) attempts the mint again
  - For success-page failures: render a 503 page showing `session_id` and a
    "refresh in 30 seconds" message; rely on the webhook retry path for eventual
    completion
  - Webhook response policy: 400 on signature/parse failure (permanent, no retry),
    500 on DB write failure (transient, retry), 200 on success or idempotent no-op
  - Admin sweep daily query: `SELECT COUNT(*) FROM failed_mints WHERE created_at >
    now()-86400`; if >10, log ERROR — alert wiring deferred to Phase 4 monitoring
- R5. Success page displays all N tokens as a list. Each token has a copy button.
  The page also includes: (a) a "Download tokens.txt" button that emits the token
  list as a plain text file client-side, (b) a "Print tokens" button, and
  (c) a prominent "Bookmark this page — it is your recovery path (see R8a-R8e)"
  notice at the top. Token injection into the HTML uses a `<script
  type="application/json" id="leafbind-tokens">...</script>` block parsed by a
  separate `<script>` (XSS-safer than inline JS string interpolation — eliminates
  the `</script>` injection class entirely). A "Start converting →" link goes to
  the conversion page. No email is sent by default (R8e defers opt-in email recovery
  to Phase 2.5).

**Token Validation**

- R6. `POST /convert` adds an optional `token` form field. When `tier=premium`, a valid
  token is required; absence or malformed token returns 422 with a clear error code.
  Phase 2 must also remove the Phase 1 tier bypass — see "Phase 1 Bypass Removal" below.
  **Four-code error taxonomy** (clarification):
  - `TOKEN_MALFORMED` — regex match fails (fast 422, no DB hit). Format issue only.
  - `TOKEN_INVALID_OR_EXPIRED` — token unknown OR expired. **Both conditions return the
    same code** to avoid leaking whether a guessed token was correctly-formatted (security:
    prevents format-correctness oracle).
  - `TOKEN_ALREADY_USED` — `used=1 AND disputed=0` (legitimate prior consume). User already
    knows their own use history, so this is informative.
  - `TOKEN_DISPUTED` — `disputed=1` (revoked by chargeback). Honest error message:
    "this credit pack has been refunded/disputed and is no longer valid."
  - `MISSING_TOKEN` — `tier=premium` but no token field provided.
- R7. Token validation gate: regex format match → `token_hash` exists in DB →
  `used=0 AND disputed=0 AND expires_at > now`. On successful validation (before
  conversion starts), the token is marked `used=true, used_at=now`. If the conversion
  subsequently fails, the token remains used — no refunds in Phase 2 (out of scope).
- R8. The validation step is atomic: token lookup and mark-used happen in a single
  DB transaction (`BEGIN IMMEDIATE`) to prevent double-spend under concurrent requests.
  `UPDATE tokens SET used=1, used_at=? WHERE token_hash=? AND used=0 AND disputed=0
  AND expires_at>?` rowcount is the primary race gate; rowcount=0 triggers an inline
  disambiguation SELECT to return the appropriate 4-code error.

**Token Recovery (P1 Finding #3 resolution)**

- R8a. The `/payment/success?session_id=xxx` page is idempotent and revisitable for the
  lifetime of the tokens (7 days). On revisit, the server looks up the existing token
  set by `pack_id=session_id` and re-renders the same tokens (decrypting the
  `token_encrypted_for_recovery` column using the row's `key_version` to select the
  correct HKDF-derived Fernet key) — no new tokens are minted, no new Stripe API call
  to verify payment is needed beyond the first render. After the 7-day token expiry,
  the page renders a "tokens expired" notice instead of the token list.
- R8b. Token storage shape extends from hash-only to hash + encrypted-plaintext +
  key_version. The token DB stores the raw token symmetrically encrypted with a Fernet
  key derived from `TOKEN_HMAC_SECRET` via HKDF-SHA256 (info=`b"leafbind-token-recovery-v{N}"`
  where N matches `key_version`), in addition to the validation hash. This enables R8a
  without weakening validation — the hash column remains the auth check; the encrypted
  column is recovery-display only. A DB leak alone (without the env secret) cannot forge
  or recover tokens. The `key_version` column enables future `TOKEN_HMAC_SECRET` rotation
  without invalidating in-flight recovery URLs (NOT supported within an active 7-day
  window in Phase 2; the column enables the future capability cheaply).
- R8c. Client-side + server-side recovery: on `/payment/success` render, the token list and
  session_id are written to `localStorage` under key `leafbind.tokens` via a separate
  inline script. Recovery flow has two routes:
  - **Next.js UI page at `/recover`** — Client Component (`components/RecoverClient.tsx`)
    reads localStorage on mount; renders TokenList if present, OR "no tokens found on this
    device" with a session_id paste form if empty.
  - **FastAPI `POST /api/recover`** — accepts a session_id from the paste form, validates
    the shape (must start with `cs_`), 302-redirects to `/payment/success?session_id=<id>`
    (the canonical recovery URL — Stripe stores completed sessions indefinitely, so the
    URL re-renders the original tokens). This is the cross-device fallback for users who
    have the Stripe receipt email but lost both the original URL and the originating
    browser's localStorage.
  - `/recover` is linked from `/pricing` footer and `/payment/cancel`.
- R8d. Response headers on `/payment/success` and `/recover`: `Referrer-Policy: no-referrer`,
  `Cache-Control: private, no-store`. The success URL is treated as a bearer secret —
  anyone with the URL can re-display the tokens within the 7-day window.
- R8e. Out of scope for Phase 2: email-based recovery (opt-in or otherwise). If real-world
  chargeback or support volume in the 60 days post-launch indicates the revisitable-URL
  pattern is insufficient, an opt-in email delivery path will be filed as a Phase 2.5
  ticket. The opt-in must preserve the "no email by default" privacy story.

**Frontend**

- R9. New `/pricing` page: 3-pack comparison table (Starter / Standard / Power), "Buy"
  button for each pack, plain prose explaining what premium adds (KFX output, smart heading
  detection, footnote linking, 100 MB limit), and a disclosure that tokens expire 7 days
  after purchase. Links to the conversion page for free tier. Footer link to `/recover`.
- R10. Conversion form (`UploadZone` component — NOT `UploadForm`, which is a 14-line
  shim) adds a collapsible `<details><summary>` "I have a token" section below the format
  selector. The token input field runs the validation regex
  (`^lb_pk_[A-Za-z0-9_-]{43}$`, see Token Format Specification) on blur, with leading/trailing
  whitespace trimmed before the check; only well-formed tokens trigger the auto-switch to
  `premium` tier and unlock the KFX format option (`FormatSelector.tsx` already gates by
  tier prop — NO modification required). This UX auto-switch is client-side convenience
  only — the server enforces token validation independently per R6 regardless of the
  `tier` value sent by the client.
- R11. `/payment/success` page: server-rendered by FastAPI (NOT Next.js), idempotent on
  revisit (R8a), shows token list with copy buttons + Download/Print buttons (R5), displays
  expiry date (7 days out), shows prominent bookmark notice, links to `/` to start
  converting. Sets `Referrer-Policy: no-referrer` and `Cache-Control: private, no-store`
  headers. Token injection via `<script type="application/json">` two-script pattern (R5).
- R12. `/payment/cancel` page: single paragraph, link back to `/pricing`, footer link
  to `/recover`. Server-rendered by FastAPI (NOT Next.js).

---

### Phase 1 Bypass Removal (P1 Finding #5 resolution)

Phase 1 shipped with a deliberate tier-check bypass (commit `6c43558`, PR #51, merged
2026-05-13) to enable public soft-launch on leafbind.io before Stripe billing was ready.
Phase 2 MUST remove this bypass as part of the token-validation work in R6.

**Files to modify:**

1. `web_service/routes/convert.py` — remove the bypass line:
   - Delete line 29: `tier = "premium"  # EB-45 Phase 1: bypass tier checks until Phase 2 billing lands`
   - The line sits between `settings = get_settings()` and `file_bytes = await file.read()`.
   - Without this line, the `tier` value from `Form("free")` (line 22) flows through unchanged
     into `validation.validate_upload(...)`. R6's token-validation replaces this with:
     if `tier=="premium"`, a valid token is required.

2. `tests/test_web_endpoints.py` — remove the skip decorator on `test_kfx_on_free_tier_returns_422`:
   - Delete the 5-line `@pytest.mark.skip(reason="EB-45 Phase 1...")` block immediately above
     `def test_kfx_on_free_tier_returns_422`.
   - The test body is correct as-is and reverts to its original Phase 1 behavior: `tier=free`
     + `output_format=kfx` → 422 via `validation.py:155` (`INVALID_OUTPUT_FORMAT`).

3. No other files require changes. `web_service/validation.py` already gates KFX to premium
   independently. The frontend (`web_service/frontend/lib/api.ts`, `components/FormatSelector.tsx`,
   `components/UploadZone.tsx`) defaults `tier="free"` and reads tier dynamically — no hardcoded
   premium values. `web_service/config.py` has no bypass-related defaults.

**Verification after removal:**
- `pytest tests/test_web_*.py -v` passes with zero skips on `TestConvertEndpoint`.
- `curl -X POST https://leafbind.io/convert -F output_format=kfx -F tier=free -F file=@x.pdf`
  returns 422 with code `INVALID_OUTPUT_FORMAT`.
- `curl -X POST https://leafbind.io/convert -F output_format=kfx -F tier=premium -F file=@x.pdf`
  (no token) returns 422 with the new R6 `MISSING_TOKEN` code.
- `git grep -nE 'EB-45 Phase 1|tier bypass|bypass tier'` returns no matches in `web_service/`
  or `tests/`.

---

### Token Format Specification (P1 Finding #7 resolution)

**Wire format:** `lb_pk_<43-char-base64url>` — 49 chars total.

- Prefix `lb_pk_` identifies leafbind premium-key tokens (distinct from future admin/refund
  namespaces and visually distinct from `sk_`/`pk_`/`ghp_` keys users may have nearby).
- Body is `secrets.token_bytes(32)` base64url-encoded with `=` padding stripped (43 chars).
  256 bits of entropy — brute-force is computationally infeasible.
- Character set: `[A-Za-z0-9_-]` (base64url alphabet, URL-safe, copy-paste-safe).

**Validation regex (client + server):** `^lb_pk_[A-Za-z0-9_-]{43}$`

**Generation (server-side, Python):**
```python
import secrets, base64
raw = secrets.token_bytes(32)
token = "lb_pk_" + base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
```

**Stored in DB:**
- `token_hash` (PRIMARY KEY) = `HMAC-SHA256(TOKEN_HMAC_SECRET, token_string)` — 32 raw bytes
  stored as SQLite `BLOB`. Defense-in-depth: a DB leak alone (without the env secret)
  cannot be used to forge or replay tokens.
- `token_encrypted_for_recovery` = symmetric encryption of the raw token using a Fernet key
  derived from `TOKEN_HMAC_SECRET` via HKDF-SHA256 (info=`b"leafbind-token-recovery-v{N}"`
  where N matches `key_version`). Used only by the R8a/R8b recovery flow; never used for
  validation.
- `key_version INTEGER NOT NULL DEFAULT 1` — enables future `TOKEN_HMAC_SECRET` rotation
  without a migration emergency. Phase 2 only writes version 1; the field exists to make
  future rotation a non-migration event.
- `payment_intent_id TEXT` — populated at mint time from the Stripe Session. Used as a
  fallback by the R3a chargeback handler if `PaymentIntent.metadata.checkout_session_id`
  is missing (operator error or pre-R2 wiring).
- `disputed_at INTEGER` — separate from `used_at`; populated by R3a chargeback handler.
  Allows audit-distinguishability between "legitimately consumed then disputed" and
  "unused but revoked by chargeback."

**Not bcrypt/argon2:** those defend low-entropy user passwords. 256-bit random tokens
already exceed any feasible brute-force budget; the ~100 ms hashing cost per validation
buys nothing measurable.

**DB schema (the `tokens` table referenced in R4):**
```sql
CREATE TABLE tokens (
    token_hash                   BLOB PRIMARY KEY,     -- HMAC-SHA256(secret, raw_token), 32 bytes
    token_encrypted_for_recovery BLOB NOT NULL,         -- symmetric-encrypted raw token (R8b)
    key_version                  INTEGER NOT NULL DEFAULT 1,    -- future rotation
    pack_id                      TEXT NOT NULL UNIQUE,  -- Stripe session_id (R4 idempotency key)
    payment_intent_id            TEXT,                  -- R3a chargeback fallback
    created_at                   INTEGER NOT NULL,
    expires_at                   INTEGER NOT NULL,      -- created_at + 7 days
    used                         INTEGER NOT NULL DEFAULT 0,
    used_at                      INTEGER,
    disputed                     INTEGER NOT NULL DEFAULT 0,   -- distinct from used (R3a)
    disputed_at                  INTEGER
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

**Server-side validation order (atomic, single `BEGIN IMMEDIATE` txn):**
1. Regex-match the submitted token; 422 on malformed (no DB hit) → `TOKEN_MALFORMED`.
2. Compute `lookup_hash = HMAC-SHA256(TOKEN_HMAC_SECRET, token)`.
3. `BEGIN IMMEDIATE` (serializes against any other writer; `busy_timeout=5000ms`).
4. `UPDATE tokens SET used=1, used_at=? WHERE token_hash=? AND used=0 AND disputed=0
   AND expires_at>?`. If `rowcount=1`, COMMIT and return OK.
5. If `rowcount=0`, disambiguation SELECT inside the same txn:
   - Row missing → `TOKEN_INVALID_OR_EXPIRED`
   - `disputed=1` → `TOKEN_DISPUTED`
   - `used=1, disputed=0` → `TOKEN_ALREADY_USED`
   - `expires_at <= now` → `TOKEN_INVALID_OR_EXPIRED`
6. ROLLBACK, return 422 with the appropriate error code.
7. (On step 4 success) start conversion (R7: failed conversions do not refund).

**Client-side (R10 refinement):** the `UploadZone` "I have a token" field runs the regex
above on blur (with whitespace trimmed); only valid-format tokens trigger the auto-switch
to premium tier. Server still enforces independently per R6.

---

## Success Criteria

- A user purchases any of the three packs (Starter $2.99/3, Standard $7.99/10, or Power
  $14.99/25) and receives the corresponding number of valid tokens.
- A user pastes one token into the conversion form and receives a KFX output within 3 minutes.
- A token cannot be used twice (second attempt returns a clear `TOKEN_ALREADY_USED` error).
- Expired tokens (after 7 days) are rejected with an informative message.
- Disputed tokens (chargeback) are rejected with `TOKEN_DISPUTED` and an honest message.
- Page refresh on `/payment/success` does not generate a duplicate set of tokens; revisiting
  the URL within the 7-day window re-displays the original tokens (R8a recovery flow).
- The `/recover` route displays previously-shown tokens when localStorage has them (R8c),
  shows a session_id paste form otherwise, and 302-redirects to `/payment/success` on paste.
- Stripe webhook receipt for a `checkout.session.completed` event is idempotent with
  a prior success-page visit for the same session (via `pack_id UNIQUE` + race-loser SELECT).
- A `charge.dispute.created` webhook for a `pack_id` marks all tokens unusable
  (`disputed=1, disputed_at=now`) within 5 seconds, using PaymentIntent metadata lookup.
- A premium conversion that fails mid-job (VM crash, pipeline error) does not restore
  the spent token — the 422 error message informs the user that the token was consumed
  and refunds are out of scope for Phase 2.
- If DB write fails after Stripe payment verification succeeds: the user sees a "refresh
  in 30 seconds" page with their `session_id`, a `failed_mints` row is logged, and the
  webhook retry path (R3 + R4a) completes the mint within 1 hour.
- If Stripe verification fails on success-page render: the user sees a retry page; the
  webhook eventually completes the mint.
- Stripe-collected email is not stored in `web_service.db`; only `pack_id` (= session_id),
  `payment_intent_id`, and token hashes are retained.
- Phase 1 tier bypass is fully removed: `git grep` for bypass-related comments
  in `web_service/` and `tests/` returns no matches; no skipped tests in `TestConvertEndpoint`.

---

## Scope Boundaries

**In scope:**
- Stripe Checkout (hosted page, no custom card form, `mode=payment` for one-time purchases)
- HMAC-SHA256-keyed opaque token generation per the Token Format Specification
- Token DB (hash PK + encrypted-recovery BLOB + key_version + payment_intent_id +
  pack_id UNIQUE + used + used_at + disputed + disputed_at + created_at + expires_at) for
  double-spend prevention AND R8a-R8e recovery
- `failed_mints` table for mint-failure recovery (R4a)
- Three-tier pack pricing (Starter / Standard / Power)
- Single-use-per-token atomic validation at `/convert` with 4-code error taxonomy
- Pricing page, success page (with bookmark + download nudges), cancel page, `/recover` route
  (Next.js UI + FastAPI POST /api/recover)
- Token field in conversion form with regex-validated auto-switch
- Phase 1 tier bypass removal
- Chargeback handling (`charge.dispute.created` with PaymentIntent metadata lookup, R3a)
- `livemode` assertion in production webhook handler
- Separate billing executor pool (operational concern — handled in the plan's Unit 4)

**Out of scope for Phase 2:**
- Subscription / recurring billing
- Token refunds or re-issuance
- Email delivery of tokens (deferred to Phase 2.5 pending real chargeback data)
- Cross-device recovery for users who lose both the success URL AND the originating
  browser's localStorage AND don't have their Stripe receipt email (acknowledged gap;
  mitigated by R5 download/print nudges and R8c session_id paste-box)
- Usage analytics dashboard
- Rate limiting enforcement at app-layer (deferred to Phase 4 per the Phase 1
  requirements doc); Cloudflare edge rate-limit on `/stripe/webhook` is operational
  config, not code
- Docker isolation per job (documented upgrade path only)
- Stripe Customer Portal or receipts management
- `TOKEN_HMAC_SECRET` rotation within an active 7-day window (unsupported; `key_version`
  column enables future rotation)
- `charge.dispute.funds_withdrawn`, `charge.dispute.closed` lifecycle events (Phase 2
  handles only `created`; revisit if dispute rate >0.5%)

---

## Key Decisions

- **One token per credit (not a count-bearing token):** Eliminates decrement logic and
  race conditions. Each token is a simple one-way door: exists → mark used → done.
- **Show tokens on success page (not email):** Consistent with the no-PII/no-accounts
  design. The privacy story stays intact. The chargeback risk from "user closes tab before
  copying" is resolved by R8a-R8e — the success URL itself is the recovery mechanism
  (Stripe stores it indefinitely), with localStorage and download-button fallbacks for
  belt-and-suspenders.
- **Revisitable success URL as recovery mechanism (P1 Finding #3 resolution):** Stripe
  Checkout Sessions with `status=complete` are retrievable from Stripe indefinitely, and
  our own `pack_id` index makes the success URL a stable, no-PII recovery path. This
  resolves the "tokens lost if tab closes" trade-off without introducing email or user
  accounts. Cost: token storage shape extends to hash + encrypted-plaintext + key_version
  (see R8b + Token Format Specification).
- **$2.99/3, $7.99/10, $14.99/25 three-tier ladder (P1 Finding #4 resolution):** Starter
  uses sub-$3 charm pricing to clear the impulse threshold for a zero-authority brand
  (ProfitWell: 3-4% conversion lift). Standard is the target tier — a visible 20% discount
  drives 60-70% of buyers per industry data on 3-tier pages. Power tier serves repeat
  users and acts as an anchor (decoy effect: 25-40% AOV lift, per CXL/Economist data).
  All tiers maintain >96% gross margin at ~$0.02 VM cost; Starter still nets ~$2.60 after
  Stripe fees. Supersedes the 5/20 placeholder in the original requirements doc.
- **HMAC-SHA256-keyed opaque tokens (not JWT, not signed payloads):** Token DB is required
  anyway for double-spend prevention (R8) and recovery (R8a), so there's no benefit to
  self-describing tokens. The HMAC operation is the lookup-keying function with a secret
  in `.env`, providing defense-in-depth against DB-leak forgery. Opaque tokens are short
  (49 chars total), don't leak metadata, and don't carry JWT's algorithm-confusion risk.
- **`payment_intent_data.metadata.checkout_session_id` at Checkout Session creation
  (NEW):** Stripe Disputes are parented to Charges; Charge metadata is INDEPENDENT of
  Session metadata. Without explicit propagation, the `charge.dispute.created` handler
  cannot resolve back to session_id, and disputed tokens are never revoked. Setting
  `payment_intent_data.metadata.checkout_session_id = session.id` at session creation
  propagates the link through the PaymentIntent so the dispute handler can resolve
  session_id via single-hop PI retrieve. The `payment_intent_id` column on `tokens` is
  the fallback if propagation somehow fails.
- **Disputed flag separate from used flag (NEW):** `disputed=1, used=0` is a valid state
  meaning "unused but revoked by chargeback." `mark_disputed(pack_id)` sets `disputed=1,
  disputed_at=?` WITHOUT modifying `used`. This preserves audit distinguishability:
  `used=1, disputed=1` is "legitimately consumed, later disputed" (important for chargeback
  fraud analytics), separate from `used=1, disputed=0` (clean use). Error code
  `TOKEN_DISPUTED` distinct from `TOKEN_ALREADY_USED`.
- **`key_version` column enables future rotation (NEW):** Adding `key_version INTEGER NOT
  NULL DEFAULT 1` to `tokens` at Phase 2 launch is near-zero cost. Without it, a future
  rotation of `TOKEN_HMAC_SECRET` would require a migration emergency (re-decrypt and
  re-encrypt all in-flight rows, or live with broken recovery). With it, rotation becomes
  a code change (`MultiFernet` + bump `key_version=2`) with no migration. Phase 2 does
  not support rotation within an active 7-day window; the column makes the future
  capability cheap.
- **Stripe Checkout email-collection bypass:** `customer_creation="if_required"` +
  `payment_intent_data.receipt_email=None` + disabled in Dashboard preserves the "no email
  by default" privacy story. Stripe will still collect email at Checkout (their hosted
  page requires it), but Stripe stores it, not our DB. Document this trade-off in the
  privacy policy.

---

## Dependencies / Assumptions

- Phase 1 is live and healthy: `/health` returns OK on `claude-dev-01` ✓ (verified 2026-05-13)
- Domain + TLS configured: `https://leafbind.io` ✓ (Let's Encrypt cert active,
  auto-renewal via `certbot.timer` on 60-day cycle, verified 2026-05-13)
- A Stripe account and publishable/secret keys must be available before development
  begins. Env vars added to `/etc/web_service.env`:
  - `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `TOKEN_HMAC_SECRET` (used for both validation hashing and recovery-column Fernet key
    derivation via HKDF)
  - `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_STANDARD`, `STRIPE_PRICE_POWER` (created via
    `deploy/stripe_bootstrap.py`)
- Stripe's test mode is used for all development; live mode enabled only at launch.
- The Stripe webhook endpoint (`https://leafbind.io/stripe/webhook`) must be registered
  in the Stripe Dashboard before live-mode launch — the leafbind.io HTTPS endpoint is
  ready (Phase 1). Subscribe to BOTH `checkout.session.completed` AND
  `charge.dispute.created` events.
- `chrony` or `systemd-timesyncd` active on `claude-dev-01` to keep clock within the
  Stripe webhook 5-minute tolerance window (verify via `timedatectl status`).
- Cloudflare DNS-only mode in Phase 2 (no proxy); operational rate-limit rule on
  `/stripe/webhook` will be configured via the Cloudflare Dashboard.

---

## Outstanding Questions

### Resolved Pre-Planning

- **[Domain / TLS]** ✅ `leafbind.io` registered, TLS active, webhook URL available
- **[P1 #3 — Token loss]** ✅ Resolved via R8a-R8e (revisitable success URL + localStorage + download)
- **[P1 #4 — Pack sizes]** ✅ Resolved: three-tier ladder $2.99 / $7.99 / $14.99
- **[P1 #5 — KFX bypass]** ✅ Resolved: Phase 1 Bypass Removal section enumerates exact deletions
- **[P1 #7 — Token format spec]** ✅ Resolved: Token Format Specification section pins format

### Resolved During Plan Deepening (2026-05-13)

- **[R3a — Chargeback handling]** ✅ `charge.dispute.created` webhook with PI metadata
  lookup; `payment_intent_data.metadata.checkout_session_id` set at Session creation.
- **[R4 — Race-loser invariant]** ✅ NEVER return locally-generated tokens after INSERT
  OR IGNORE collision; re-SELECT inside same txn and return DB-authoritative rows.
- **[R4a — Mint-failure recovery]** ✅ `failed_mints` table + return 500 on DB write
  failure to trigger Stripe retry budget; daily admin sweep query.
- **[R6 — Error taxonomy]** ✅ Four codes: `TOKEN_MALFORMED`, `TOKEN_INVALID_OR_EXPIRED`,
  `TOKEN_ALREADY_USED`, `TOKEN_DISPUTED` (plus `MISSING_TOKEN` for absence).
- **[R7 — Storage schema]** ✅ Token table extends with `key_version`, `payment_intent_id`,
  `disputed_at`. Token validation gate includes `disputed=0` check.
- **[R8c — Recovery ownership]** ✅ Next.js owns `/recover` UI page; FastAPI exposes
  `POST /api/recover` for cross-device session_id paste lookup.

### Deferred to Implementation (Plan-Owned)

- **Exact body of `mint_tokens_if_absent(session_id)`** — pseudo-code in plan Unit 2 is
  directional; the implementer adjusts for the specific Stripe SDK calls and SQLite
  transaction semantics observed during development.
- **`failed_mints` table location** — Recommended: extend `web_service/token_store.py`
  rather than create a third module. Verify during implementation.
- **Symmetric encryption library** — Fernet (recommended) via HKDF-SHA256-derived key.
  `cryptography.hazmat.primitives.ciphers.aead.AESGCM` is the fallback if AAD support is
  needed (Phase 2 has no AAD requirement).
- **Cloudflare rate-limit rule numeric tuning** — Initial 30/min per source IP on
  `/stripe/webhook`; tune post-launch based on Stripe webhook delivery volume and observed
  scanner noise.
- **Token cleanup sweep cadence** — Initial 60 minutes (matches `cleanup_expired_jobs`);
  revise post-launch based on table growth.
- **Frontend component testing infrastructure** — No Jest/Testing Library set up in
  Phase 1; introducing it for Phase 2 is out of scope. File as separate ticket if frontend
  test coverage becomes a priority.

---

## Next Steps

→ `/ce:plan` produced `docs/plans/2026-05-13-002-feat-eb45-phase2-stripe-billing-plan.md`
  (deepened 2026-05-13).
→ Phase 2 implementation begins with `/ce:work` on Unit 1 (Config + secrets + dependencies
  + startup checks). Recommended sequencing: backend foundations (Units 1-3) → Stripe
  routes (Units 4-5) → conversion integration (Unit 6) → frontend (Unit 7) → deployment
  (Unit 8). The plan documents the full phased delivery (2A through 2E).
