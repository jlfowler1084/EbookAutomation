---
date: 2026-05-13
topic: eb45-phase2-stripe-billing
status: ready-for-planning
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

---

## Payment and Token Flow

```
User → Pricing page → [Buy 3, 10, or 25 credits]
  → POST /stripe/create-session
  → Stripe Checkout (hosted)
  → User pays
  → Stripe redirects → GET https://leafbind.io/payment/success?session_id=xxx
  → Server verifies session with Stripe API
  → Generates N HMAC-keyed tokens, stores (hash + encrypted-plaintext) in token DB
  → Success page displays N token strings + bookmark prompt + download button
  → User copies a token (or bookmarks the page / downloads tokens.txt for recovery)
  → Pastes into token field on conversion form
  → POST /convert (file + token + tier=premium + output_format)
  → Server validates token: regex format → hash lookup → exists, unused, not expired
  → Token marked used in same DB transaction (double-spend safe)
  → Premium pipeline runs
  → Job ID returned; user polls /status/{id}; downloads result
```

---

## Requirements

**Stripe Checkout**

- R1. Three credit packs offered at launch:
  - Starter: 3 credits for $2.99   ($1.00/credit — low-commit entry, charm-priced)
  - Standard: 10 credits for $7.99 ($0.80/credit — target tier, 20% discount)
  - Power: 25 credits for $14.99   ($0.60/credit — repeat-buyer anchor / decoy)
- R2. `POST /stripe/create-session` accepts `pack` param (`starter` | `standard` | `power`),
  creates a Stripe Checkout Session with `success_url` set to
  `https://leafbind.io/payment/success?session_id={CHECKOUT_SESSION_ID}` (the literal Stripe
  template placeholder — Stripe substitutes the real session ID at redirect time) and
  `cancel_url` set to `https://leafbind.io/pricing`. Returns the Stripe-hosted Checkout URL.
- R3. Stripe webhook endpoint (`POST https://leafbind.io/stripe/webhook`) handles
  `checkout.session.completed` events as a belt-and-suspenders backup — idempotent with
  the success page flow. Stripe secret key and webhook signing secret are environment
  variables only. The endpoint must validate the `Stripe-Signature` header (using the
  webhook signing secret) and reject events with timestamps outside a 5-minute tolerance
  to prevent replay attacks. Webhook is registered with Stripe under the leafbind.io
  HTTPS endpoint (Phase 1 TLS verified 2026-05-13).

**Token Generation and Delivery**

- R4. On success page load (`GET /payment/success?session_id=xxx`):
  - Server calls Stripe API to verify the session is paid and not already processed.
  - Generates N tokens (one per credit) per the Token Format Specification below.
  - Stores in the token DB: `token_hash` (validation key, R7), `token_encrypted_for_recovery`
    (R8b), `pack_id` (= Stripe session_id, prevents re-processing on page refresh),
    `created_at`, `expires_at` (7 days), `used` (false).
  - The `pack_id` column has a UNIQUE constraint; concurrent webhook + success-page calls
    must use INSERT-or-ignore (not INSERT) to guarantee exactly one token set per session.
- R5. Success page displays all N tokens as a list. Each token has a copy button.
  The page also includes: (a) a "Download tokens.txt" button that emits the token
  list as a plain text file client-side, (b) a "Print tokens" button, and
  (c) a prominent "Bookmark this page — it is your recovery path (see R8a-R8e)"
  notice at the top. A "Start converting →" link goes to the conversion page. No
  email is sent by default (R8e defers opt-in email recovery to Phase 2.5).

**Token Validation**

- R6. `POST /convert` adds an optional `token` form field. When `tier=premium`, a valid
  token is required; absence or malformed token returns 422 with a clear error message.
  Phase 2 must also remove the Phase 1 tier bypass — see "Phase 1 Bypass Removal" below.
- R7. Token validation checks: regex format match (see Token Format Specification),
  token hash exists in DB, `used=false`, `expires_at` in future. On successful validation
  (before conversion starts), the token is marked `used=true`. If the conversion subsequently
  fails, the token remains used — no refunds in Phase 2 (out of scope).
- R8. The validation step is atomic: token lookup and mark-used happen in a single
  DB transaction (`BEGIN IMMEDIATE`) to prevent double-spend under concurrent requests.

**Token Recovery (P1 Finding #3 resolution)**

- R8a. The `/payment/success?session_id=xxx` page is idempotent and revisitable for the
  lifetime of the tokens (7 days). On revisit, the server looks up the existing token
  set by `pack_id=session_id` and re-renders the same tokens (decrypting the
  `token_encrypted_for_recovery` column) — no new tokens are minted, no new Stripe API
  call to verify payment is needed beyond the first render. After the 7-day token expiry,
  the page renders a "tokens expired" notice instead of the token list.
- R8b. Token storage shape extends from hash-only to hash + encrypted-plaintext. The
  token DB stores the raw token symmetrically encrypted with a key derived from
  `TOKEN_HMAC_SECRET`, in addition to the validation hash. This enables R8a without
  weakening validation — the hash column remains the auth check; the encrypted column is
  recovery-display only. A DB leak alone (without the env secret) cannot forge or recover
  tokens.
- R8c. Client-side fallback: on `/payment/success` render, the token list and session_id
  are written to `localStorage` under key `leafbind.tokens`. A separate `/recover` route
  reads localStorage and displays previously-shown tokens for users who lost the success
  URL but kept the browser. The route shows a friendly "no tokens found on this device"
  state if empty. `/recover` is linked from `/pricing` footer and `/payment/cancel`.
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
- R10. Conversion form (`UploadZone` component) adds a collapsible "I have a token" section
  below the format selector. The token input field runs the validation regex
  (`^lb_pk_[A-Za-z0-9_-]{43}$`, see Token Format Specification) on blur; only well-formed
  tokens trigger the auto-switch to `premium` tier and unlock the KFX format option.
  This UX auto-switch is client-side convenience only — the server enforces token
  validation independently per R6 regardless of the `tier` value sent by the client.
- R11. `/payment/success` page: server-rendered, idempotent on revisit (R8a), shows token
  list with copy buttons + Download/Print buttons (R5), displays expiry date (7 days out),
  shows prominent bookmark notice, links to `/` to start converting. Sets
  `Referrer-Policy: no-referrer` and `Cache-Control: private, no-store` headers.
- R12. `/payment/cancel` page: single paragraph, link back to `/pricing`, footer link
  to `/recover`.

---

### Phase 1 Bypass Removal (P1 Finding #5 resolution)

Phase 1 shipped with a deliberate tier-check bypass (commit `6c43558`, PR #51, merged
2026-05-13) to enable public soft-launch on leafbind.io before Stripe billing was ready.
Phase 2 MUST remove this bypass as part of the token-validation work in R6.

**Files to modify:**

1. `web_service/routes/convert.py` — remove the bypass line:
   - Delete line 29: `tier = "premium"  # EB-45 Phase 1: bypass tier checks until Phase 2 billing lands`
   - The line sits between `settings = get_settings()` (line 28) and `file_bytes = await file.read()` (line 30 after removal).
   - Without this line, the `tier` value from `Form("free")` (line 22) flows through unchanged
     into `validation.validate_upload(...)` (line 37). R6's token-validation replaces this with:
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
  (no token) returns 422 with the new R6 "missing/invalid token" message.
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
- `token_encrypted_for_recovery` = symmetric encryption of the raw token using a key derived
  from `TOKEN_HMAC_SECRET` (Fernet recommended for simplicity; AES-256-GCM if there's a
  specific reason). Used only by the R8a/R8b recovery flow; never used for validation.

**Not bcrypt/argon2:** those defend low-entropy user passwords. 256-bit random tokens
already exceed any feasible brute-force budget; the ~100 ms hashing cost per validation
buys nothing measurable.

**DB schema (the `tokens` table referenced in R4):**
```sql
CREATE TABLE tokens (
    token_hash                   BLOB PRIMARY KEY,     -- HMAC-SHA256(secret, raw_token), 32 bytes
    token_encrypted_for_recovery BLOB,                  -- symmetric-encrypted raw token (R8b)
    pack_id                      TEXT NOT NULL UNIQUE,  -- Stripe session_id (R4 idempotency key)
    created_at                   INTEGER NOT NULL,
    expires_at                   INTEGER NOT NULL,      -- created_at + 7 days
    used                         INTEGER NOT NULL DEFAULT 0,
    used_at                      INTEGER
);
CREATE INDEX idx_tokens_pack_id ON tokens(pack_id);
```

**Server-side validation order (atomic, single `BEGIN IMMEDIATE` txn):**
1. Regex-match the submitted token; 422 on malformed (no DB hit).
2. Compute `lookup_hash = HMAC-SHA256(TOKEN_HMAC_SECRET, token)`.
3. `SELECT` row by `token_hash` PK with `used=0 AND expires_at > now`.
4. If no row: rollback, return 422 "invalid or expired token".
5. `UPDATE tokens SET used=1, used_at=? WHERE token_hash=? AND used=0`; if `rowcount=0`,
   another request won the race — rollback, return 422 "token already used".
6. `COMMIT`, then start conversion (R7: failed conversions do not refund).

**Client-side (R10 refinement):** the `UploadZone` "I have a token" field runs the regex
above on blur; only valid-format tokens trigger the auto-switch to premium tier. Server
still enforces independently per R6.

---

## Success Criteria

- A user purchases any of the three packs (Starter $2.99/3, Standard $7.99/10, or Power
  $14.99/25) and receives the corresponding number of valid tokens.
- A user pastes one token into the conversion form and receives a KFX output within 3 minutes.
- A token cannot be used twice (second attempt returns a clear 422 error).
- Expired tokens (after 7 days) are rejected with an informative message.
- Page refresh on `/payment/success` does not generate a duplicate set of tokens; revisiting
  the URL within the 7-day window re-displays the original tokens (R8a recovery flow).
- The `/recover` route displays previously-shown tokens when localStorage has them (R8c)
  and shows a friendly empty state otherwise.
- Stripe webhook receipt for a `checkout.session.completed` event is idempotent with
  a prior success-page visit for the same session.
- A premium conversion that fails mid-job (VM crash, pipeline error) does not restore
  the spent token — the 422 error message informs the user that the token was consumed
  and refunds are out of scope for Phase 2.
- Phase 1 tier bypass is fully removed: `git grep` for bypass-related comments
  in `web_service/` and `tests/` returns no matches; no skipped tests in `TestConvertEndpoint`.

---

## Scope Boundaries

**In scope:**
- Stripe Checkout (hosted page, no custom card form)
- HMAC-SHA256-keyed opaque token generation per the Token Format Specification
- Token DB (hash + encrypted-plaintext, pack_id, used, expires_at) for double-spend
  prevention AND R8a-R8e recovery
- Three-tier pack pricing (Starter / Standard / Power)
- Single-use-per-token validation at `/convert`
- Pricing page, success page (with bookmark + download nudges), cancel page, `/recover` route
- Token field in conversion form with regex-validated auto-switch
- Phase 1 tier bypass removal

**Out of scope for Phase 2:**
- Subscription / recurring billing
- Token refunds or re-issuance
- Email delivery of tokens (deferred to Phase 2.5 pending real chargeback data)
- Cross-device recovery for users who lose both the success URL AND the originating
  browser's localStorage (acknowledged gap; mitigated by R5 download/print nudges)
- Usage analytics dashboard
- Rate limiting enforcement (deferred to Phase 4 per the Phase 1 requirements doc)
- Docker isolation per job (documented upgrade path only)
- Stripe Customer Portal or receipts management

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
  accounts. Cost: token storage shape extends to hash + encrypted-plaintext (see R8b +
  Token Format Specification).
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

---

## Dependencies / Assumptions

- Phase 1 is live and healthy: `/health` returns OK on `claude-dev-01` ✓ (verified 2026-05-13)
- Domain + TLS configured: `https://leafbind.io` ✓ (Let's Encrypt cert active,
  auto-renewal via `certbot.timer` on 60-day cycle, verified 2026-05-13)
- A Stripe account and publishable/secret keys must be available before development
  begins. Env vars added to `/etc/web_service.env`:
  - `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `TOKEN_HMAC_SECRET` (used for both validation hashing and recovery-column encryption key derivation)
- Stripe's test mode is used for all development; live mode enabled only at launch.
- The Stripe webhook endpoint (`https://leafbind.io/stripe/webhook`) must be registered
  in the Stripe Dashboard before live-mode launch — the leafbind.io HTTPS endpoint is
  ready (Phase 1).

---

## Outstanding Questions

### Resolved Pre-Planning

- **[Domain / TLS]** ✅ `leafbind.io` registered, TLS active, webhook URL available
- **[P1 #3 — Token loss]** ✅ Resolved via R8a-R8e (revisitable success URL + localStorage + download)
- **[P1 #4 — Pack sizes]** ✅ Resolved: three-tier ladder $2.99 / $7.99 / $14.99
- **[P1 #5 — KFX bypass]** ✅ Resolved: Phase 1 Bypass Removal section enumerates exact deletions
- **[P1 #7 — Token format spec]** ✅ Resolved: Token Format Specification section pins format

### Deferred to Planning

- **[Affects R4][Technical]** Where in the codebase does the token DB table live — extend
  `web_service/job_store.py` with a `tokens` table, or create a new `web_service/token_store.py`?
  Recommendation: new `token_store.py` to keep token concerns isolated from job state.
- **[Affects R2][Needs research]** Stripe Checkout `mode` parameter: `payment` for one-time
  purchases is correct; confirm no subscription mode is used accidentally during planning.
- **[Affects R8b][Technical]** Symmetric encryption library choice for
  `token_encrypted_for_recovery`: `cryptography.fernet` (simpler API, AES-128-CBC + HMAC)
  vs `cryptography.hazmat.primitives.ciphers.aead.AESGCM` (AES-256-GCM, modern AEAD).
  Recommend Fernet for simplicity unless there's a specific reason to prefer raw AESGCM.

---

## Next Steps

→ `/ce:plan` for structured Phase 2 implementation planning.
  Recommend starting with the backend (Stripe session endpoint + token store + validation
  + recovery flow) before the frontend, so the API contract is stable when the UI is built.
