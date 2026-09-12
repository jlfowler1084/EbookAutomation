---
date: 2026-05-16
topic: eb45-phase3-accounts-persistent-tokens
status: ready-for-planning
---

# EB-45 Phase 3 — Magic-Link Accounts, Persistent Credits, and Conversion History

## Problem Frame

Phase 2 shipped paid conversions with a deliberate "no user accounts" privacy
positioning (`docs/brainstorms/2026-05-13-eb45-phase2-billing-requirements.md`):
49-char bearer tokens (`lb_pk_<43-char-base64url>`) with a 7-day TTL, recoverable
only via a revisitable success URL + `localStorage` fallback. The trade-off was
explicit and intentional — privacy as differentiator, zero PII in the leafbind DB.

Two pain points have emerged that justify revisiting the trade-off:

1. **Token loss is a real user-trust problem.** Bearer-token UX assumes users
   bookmark the success page, save tokens to a password manager, or download
   the `tokens.txt`. In practice, people close tabs, switch devices, and forget.
   The R8a-R8e recovery flow in Phase 2 catches some of this, but anyone who
   loses the success URL *and* the originating browser's `localStorage`
   *and* the Stripe receipt email is stranded.

2. **No mailing-list capture.** The product has no channel to tell paying
   customers about new features, promos, or service changes. Every purchase is
   a one-shot transaction — there is no relationship to compound.

Phase 3 pivots from "no PII" to "opt-in PII for compounding value," delivering
both fixes in one coherent surface area:

- **Magic-link accounts** — email + signed URL (no passwords, no OAuth). Standard
  pattern for utility SaaS (Substack, Notion, Vercel).
- **Persistent credit balance** — credits never expire while the account is
  active. The current per-pack token machinery is preserved internally for
  dispute/audit integrity; the user sees a single pooled count.
- **Conversion history with re-download** — last 30 days of converted output
  files retained on disk, listed on the account page. This is the
  compounding feature — the reason users come back beyond a promo email.
- **Mailing-list capture** — checked-by-default opt-in checkbox at signup,
  unsubscribe flow honored. The list is the marketing primitive that funds
  future product investment.

The anonymous free-tier flow at `https://leafbind.io` is preserved unchanged —
this is leafbind's top-of-funnel and SEO landing surface. Account creation is
introduced only when a user buys premium credits, with a soft upsell on the
post-purchase success page.

## Payment + Account Flow (Phase 3)

```
ANONYMOUS USER (unchanged from today)
  → / (conversion form) → free tier conversion → download → done

PAID USER (new flow)
  → /pricing → [Buy 3/10/25 credits]
  → POST /stripe/create-session (optionally with logged-in account_id)
  → Stripe Checkout (collects email — same as today)
  → User pays
  → Stripe redirects → GET /payment/success?session_id=xxx
    ├─ NOT logged in:
    │   - Server mints tokens (existing Phase 2 path, idempotent)
    │   - Success page shows tokens AS TODAY (bearer-token recovery preserved)
    │   - Above the token list: "Save your credits — create a free leafbind
    │     account" with email field + "Send magic link" button
    │   - On magic-link verify: tokens attached to account via account_id FK,
    │     account balance reflects the count
    │   - Stripe-collected email auto-populates the magic-link email field
    │     (user can edit)
    └─ Logged in:
        - Server mints tokens with account_id attached at creation time
        - Success page says "10 credits added to your account. Balance: 23"
        - One-click "Convert another book →"

LOGGED-IN USER (returning)
  → GET / → shell shows "Sign in" → magic-link login → session cookie set
  → / → conversion form sees session, shows balance, debits on premium use
  → /account → balance, conversion history (last 30 days), opt-in toggle
```

## Requirements

**Authentication (magic-link)**

- R1. New `/login` page (Next.js Client Component) with single email field
  and "Send magic link" button. On submit, POSTs to `/api/auth/request-link`;
  on success, shows "Check your inbox" UI. No password field anywhere.
- R2. `POST /api/auth/request-link` (FastAPI):
  - Validates email shape (RFC 5321 single address, no CRLF)
  - Looks up or creates a row in `accounts(email, …)` — *creation* triggers
    R7 (marketing opt-in capture)
  - Generates a signed URL token: `itsdangerous.URLSafeTimedSerializer`-signed
    payload `{account_id, nonce}`, 15-minute TTL, single-use
  - Sends the magic-link email via Resend SMTP (already configured per EB-264)
  - Returns 204 regardless of whether the email existed (no user-enumeration
    oracle)
  - Rate-limited: 3 requests / 15-minute window per email; 10 per source IP
    per hour (Cloudflare WAF or app-layer KV)
- R3. `GET /api/auth/verify?token=…` (FastAPI):
  - Validates signature + TTL + single-use (consumes a `nonce` from
    `magic_link_nonces` table)
  - Sets a `leafbind_session` HTTP-only Secure SameSite=Lax cookie with
    Itsdangerous-signed `{account_id, issued_at}` payload
  - Session lifetime: 90 days, sliding renewal on use
  - 302-redirects to `/account` on success, `/login?error=expired` on failure
- R4. `POST /api/auth/logout`: clears the session cookie, 302-redirects to `/`.
- R5. Server-side session helper `get_account_from_request(req)` returns
  `Account | None`; used by all account-aware routes. No session = anonymous,
  not 401. The free tier never requires a session.

**Account & credit model**

- R6. New `accounts` table:
  ```sql
  CREATE TABLE accounts (
      id                  INTEGER PRIMARY KEY AUTOINCREMENT,
      email               TEXT NOT NULL UNIQUE COLLATE NOCASE,
      created_at          INTEGER NOT NULL,
      last_login_at       INTEGER,
      marketing_opted_in  INTEGER NOT NULL DEFAULT 0,
      marketing_opted_in_at INTEGER,
      marketing_opted_out_at INTEGER,
      unsubscribe_token   TEXT NOT NULL UNIQUE     -- secrets.token_urlsafe(32)
  );
  CREATE INDEX idx_accounts_email ON accounts(email);
  ```
- R7. `tokens` table gains a nullable `account_id INTEGER REFERENCES accounts(id)`
  column. Existing Phase 2 tokens stay `account_id=NULL` (the "bearer" flow).
  New purchases by logged-in users set `account_id` at mint time.
  Anonymous purchases continue to mint with `account_id=NULL` and offer the
  R8 post-purchase claim flow.
- R8. **Post-purchase claim flow** (anonymous → account): on the success page,
  if the user is not logged in, the page offers "Save your credits — create
  a free account" with an inline magic-link form. Magic-link verify path
  detects a `pending_pack_id` URL param (or `localStorage` value) and runs
  `UPDATE tokens SET account_id=? WHERE pack_id=? AND account_id IS NULL`
  inside the same `BEGIN IMMEDIATE` transaction as the verify-side session
  cookie creation. Race-safe: if a second login claims the same pack first,
  the UPDATE matches 0 rows and the user sees a "this pack is already
  attached to another account" error.
- R9. **Pooled balance display** (hybrid model). The user-facing balance is
  computed on demand: `SELECT COUNT(*) FROM tokens WHERE account_id=? AND
  used=0 AND disputed=0` — no `credits_balance` column on `accounts`.
  Rationale: avoids the dual-write problem (token state + counter could
  drift), keeps the existing Phase 2 dispute logic intact, and the query is
  cheap with an index on `account_id`. Display formats: "23 credits",
  "1 credit", "0 credits — buy more".
- R10. **Credits never expire** while the account exists. The existing
  `expires_at` column on `tokens` is ignored for tokens with
  `account_id IS NOT NULL` (validation drops the `expires_at > now` clause
  in that branch). Anonymous tokens retain the 7-day expiry. Phase 3 does
  not add an inactivity sweep — that's a future decision when the
  accounting liability materially grows.
- R11. **No migration of in-flight bearer tokens.** Existing `lb_pk_*` tokens
  with `account_id=NULL` continue to validate at `/convert` under the Phase 2
  expires_at rule. After the natural 7-day expiry, the bearer code path is
  effectively dead for tokens issued before Phase 3 ships. The R8 claim
  flow exists for *new* anonymous purchases, not for pre-Phase-3 tokens.

**Marketing list**

- R12. The signup form (R1) includes a checkbox **checked by default**:
  *"Send me product updates and promos (you can unsubscribe anytime)."*
  Captured into `accounts.marketing_opted_in` at account creation.
  Subsequent logins do NOT reset this preference.
- R13. The footer of every transactional email includes a one-click
  unsubscribe link: `https://leafbind.io/unsubscribe?token=<unsubscribe_token>`
  that flips `marketing_opted_in=0` and sets `marketing_opted_out_at=now`
  without requiring login. Honored under both CAN-SPAM and GDPR Article 7.
- R14. **GDPR exposure flag.** Checked-by-default opt-in is CAN-SPAM
  compliant (US) but violates GDPR Article 7 (EU explicit consent
  requirement). Phase 3 ships with the checked-default behavior for all
  geographies as an explicit accepted risk; the mitigation path (geo-detect
  EU visitors via Cloudflare `CF-IPCountry` header and serve an unchecked
  checkbox) is filed as a follow-up ticket but not blocking. Operator
  acknowledges that EU complaints, if they arrive, will need the geo-gate
  fix as immediate-priority work.
- R15. The marketing email send infrastructure itself (campaign tooling,
  list segmentation, deliverability monitoring) is OUT OF SCOPE for Phase 3.
  Phase 3 only captures the list and provides the unsubscribe link.
  Operator may export the list manually (CSV from SQLite) and send through
  Resend Broadcasts or Mailchimp until campaign-side automation is its own
  epic.

**Conversion history & re-download**

- R16. New `conversions` table:
  ```sql
  CREATE TABLE conversions (
      id                INTEGER PRIMARY KEY AUTOINCREMENT,
      account_id        INTEGER NOT NULL REFERENCES accounts(id),
      job_id            TEXT NOT NULL,                  -- ties to job_store
      original_filename TEXT NOT NULL,
      output_format     TEXT NOT NULL,                  -- 'kfx', 'epub', etc.
      tier              TEXT NOT NULL,                  -- 'free' or 'premium'
      created_at        INTEGER NOT NULL,
      file_path         TEXT,                           -- on-disk path; NULL after retention
      file_size_bytes   INTEGER,
      retention_until   INTEGER NOT NULL                -- created_at + 30 days
  );
  CREATE INDEX idx_conversions_account ON conversions(account_id, created_at DESC);
  ```
- R17. **History is logged-in only.** Anonymous conversions (whether free or
  premium-bearer-token) do NOT write to `conversions`. The table is keyed on
  `account_id NOT NULL` — there is no anonymous history. This preserves the
  privacy story for users who never sign up.
- R18. **File retention storage.** Output files for logged-in conversions are
  copied to `/var/leafbind/conversions/<account_id>/<job_id>.<ext>` on the
  VM at job-completion time. The path is recorded in `conversions.file_path`.
  Free-tier conversions are eligible for retention if the user is logged in.
  Storage budget cap: 100 GB total directory size; if exceeded, oldest files
  are pruned (LRU on `created_at`) regardless of `retention_until`.
  Operator monitoring is via a daily disk-usage log line, not active
  alerting in Phase 3.
- R19. **Daily retention sweep.** A `cleanup_expired_conversion_files()`
  function runs every 24h (same cadence as `cleanup_expired_jobs`):
  `DELETE` the file from disk for all rows where
  `retention_until < now AND file_path IS NOT NULL`, then `UPDATE` the row
  to `file_path=NULL`. The metadata row persists (so the history list still
  shows "Hot Hand by Howard Wasdin — Oct 12, 2025, KFX (expired)" with a
  disabled download button). Metadata rows older than 365 days are deleted
  outright to bound table growth.
- R20. **Re-download route.** `GET /account/conversions/<id>/download` checks
  the request's session cookie matches `conversions.account_id`, that
  `file_path IS NOT NULL`, and that the file exists on disk. Returns the file
  as an attachment with appropriate `Content-Type` and `Content-Disposition`.
  404 on missing, 403 on wrong account.

**Account UI**

- R21. New `/account` page (Next.js, Server Component with session-cookie read):
  - Header: "Hi, <email>" with sign-out link
  - Balance card: large pooled count + "Buy more credits →" link to `/pricing`
  - Conversion history card: scrolling list of last 30 days, columns
    *Date | Filename | Format | Tier | Action*. Action is "Download" if
    `file_path IS NOT NULL`, "Expired" disabled-state otherwise.
  - Preferences section: marketing opt-in toggle with current state
  - Account section: delete-account button (Phase 3 stub: shows a "Contact
    support" link to `/contact`; programmatic self-service deletion deferred
    to a future privacy-rights ticket)
- R22. The global header (`Header.tsx` or equivalent) gains a "Sign in"
  link when no session cookie is present, and a "<email> ▾" dropdown
  (Account / Sign out) when one is. Free-tier conversion still works
  without sign-in.

**Stripe integration changes**

- R23. `POST /stripe/create-session` reads the session cookie. If logged in,
  `payment_intent_data.metadata.account_id = str(account.id)` is added to
  the Checkout session. The webhook handler in `web_service/routes/webhook.py`
  reads this metadata on `checkout.session.completed` and passes the
  `account_id` to `mint_tokens_if_absent()`, which inserts rows with
  the FK populated.
- R24. **Stripe email is NOT used as the account email.** Stripe collects
  email for receipt purposes; leafbind never reads it from Stripe and
  never inserts it into `accounts`. Account email comes exclusively from
  the magic-link signup flow. This avoids the silent-account-creation
  failure mode where a user has a Stripe-side email they don't realize is
  also a leafbind account.

## Success Criteria

- A first-time user can buy a credit pack, click "Save your credits" on
  the success page, receive a magic-link email within 60 seconds, click
  the link, and land on `/account` with their credits visible.
- A returning user can paste their email at `/login`, receive a magic-link
  email, click it, and reach `/account` showing the correct balance and
  the last 30 days of conversions.
- A logged-in user converting a PDF sees the conversion appear in their
  history within 5 seconds of job completion, with a working Download
  button for the next 30 days.
- A user can click the unsubscribe link in any transactional email
  without logging in, and the `accounts.marketing_opted_in` flag flips to
  0 on first click.
- Existing Phase 2 bearer tokens (`account_id=NULL`, 7-day TTL) continue
  to validate at `/convert` under the existing rules until their natural
  expiry; no regression in Phase 2 success criteria.
- A user with no account can convert a PDF on the free tier at `/`
  without seeing any signup wall or sign-in prompt blocking the flow.
- A user with no account who buys a premium pack and never claims it
  still receives working bearer tokens on the success page (Phase 2
  R8a-R8e recovery path intact for unclaimed packs).
- Disk usage in `/var/leafbind/conversions/` stays under 100 GB; the
  daily sweep runs without error and removes expired files within 24 hours
  of their `retention_until`.
- A magic-link token cannot be replayed after one successful use, and
  rejects after its 15-minute TTL.
- The session cookie survives a 30-day idle period (sliding renewal)
  but is invalidated within 90 days of last activity.

## Scope Boundaries

**In scope:**
- Magic-link auth (request + verify + logout + session cookies)
- `accounts` table with marketing opt-in fields
- `tokens.account_id` FK column + claim flow for post-purchase signup
- Pooled credit balance display (computed query, no counter column)
- Per-pack token internals preserved for dispute/audit integrity
- Anonymous bearer-token flow preserved (no migration)
- `conversions` table + 30-day file retention + daily sweep
- Re-download route gated by session ownership
- `/account` page with balance, history, preferences, sign-out
- Header sign-in / signed-in indicator
- Unsubscribe link in all transactional emails (`/unsubscribe?token=…`)
- Post-purchase magic-link upsell on `/payment/success`
- Stripe webhook integration to attach `account_id` to minted tokens

**Out of scope for Phase 3:**
- Marketing email campaign tooling (segmentation, scheduling, A/B testing,
  open/click tracking) — list capture only
- Inactivity-based credit expiration sweep
- Self-service account deletion (Phase 3 stubs as "contact support")
- OAuth providers (Google/Apple) — magic link only
- Multi-device session management UI (list active sessions, revoke)
- Email change flow — fixed at signup; change requires support intervention
- GDPR-compliant geo-gated opt-in default (filed as follow-up; risk accepted)
- Conversion history search / filter / pagination (linear list, 30-day window)
- Subscription / recurring credit replenishment
- Team accounts / shared balances
- Notification preferences (per-feature email toggles) — only the binary
  marketing opt-in exists
- Programmatic CSV export of the subscriber list (operator queries SQLite
  manually in Phase 3)
- Mobile app or PWA installability
- Account-page Stripe Customer Portal embed for invoice management

## Key Decisions

- **Magic link over password.** Eliminates password reset support load and
  password-manager friction; ~40% lower signup-form abandonment per
  industry data. The one downside (email delivery is now in the critical
  signup path) is mitigated by the existing Resend integration from EB-264
  having proven deliverability.
- **Magic link over OAuth.** OAuth (Google/Apple) is faster at signup but
  introduces a third-party provider dependency, OAuth-app maintenance
  burden, and adds an account-linking edge case (email used for OAuth ≠
  email used for receipts). Not worth the complexity until evidence shows
  users want it.
- **Hybrid credit model (per-pack internal, pooled display).** A pure
  pooled-balance counter would require dual-writing token state + counter,
  which inevitably drifts. Computing balance on demand from the existing
  `tokens` table is cheap (indexed), reuses 100% of the Phase 2 dispute
  logic, and avoids the "negative balance after late chargeback" footgun.
- **Credits never expire.** Industry standard for prepaid credit SaaS
  (Vercel, OpenAI). At $1/credit max and the current user volume, the
  accounting liability is negligible until the product is much larger.
  Adding an inactivity sweep later is straightforward when the math
  changes.
- **Free tier stays anonymous.** Free tier is the SEO landing surface and
  top-of-funnel; gating it would hurt conversion materially. Login is
  introduced only at the point of paid intent.
- **Checked-by-default marketing opt-in (US/CAN-SPAM compliant).** Trades
  GDPR exposure for ~2x faster list growth. Operator accepts the risk and
  has filed a geo-gated unchecked-for-EU mitigation as a follow-up ticket.
- **No bearer-token migration.** Existing pre-Phase-3 tokens expire
  naturally within 7 days of Phase 2 ship date. Building a migration UI
  would cost more in implementation + support than the at-most-handful of
  affected users justifies.
- **History gated to logged-in users only.** No anonymous history. This is
  both a storage-cost decision (no per-IP file retention) and a privacy
  decision (anonymous users gave no consent to data retention).
- **30-day file retention with 100 GB cap.** Matches typical "I lost my
  Kindle copy" support-ticket window. The cap protects against runaway
  storage; LRU pruning beats the retention rule when capacity binds.
- **Stripe email NOT reused as account email.** Avoids the
  silent-account-creation failure mode where a user has a Stripe-side
  email they don't realize is also a leafbind login. Account creation is
  always an explicit magic-link signup.
- **Pooled balance computed, not stored.** Single source of truth (the
  `tokens` table). The query is `O(log n)` with the existing
  `account_id` index. Skipping the counter column eliminates an entire
  class of consistency bugs.

## Dependencies / Assumptions

- Phase 2 is live and healthy at `https://leafbind.io` ✓
- Resend SMTP credentials configured in `/etc/web_service.env` (per
  EB-264 contact form work, verified 2026-05-15)
- `support@leafbind.io` outbound deliverability is healthy (SPF + DKIM
  passing per EB-264 R2; DMARC `p=none` per EB-278 — sufficient for
  magic-link delivery to major mailbox providers)
- New env vars added to `/etc/web_service.env`:
  - `MAGIC_LINK_SECRET` — `itsdangerous` signing key for magic-link tokens
  - `SESSION_COOKIE_SECRET` — `itsdangerous` signing key for session cookies
  - `LEAFBIND_CONVERSION_RETENTION_DIR` — defaults to `/var/leafbind/conversions/`
- `/var/leafbind/conversions/` directory exists on the VM with sufficient
  free space (100 GB budget) and is owned by the web service uid
- Python deps added to `requirements.txt`:
  - `itsdangerous` (signed URL + cookie tokens) — likely already installed
  - `email-validator` (RFC 5321 validation) — likely already installed
- Cloudflare KV namespace for app-layer rate-limiting on
  `/api/auth/request-link` (or equivalent in-process limiter — choice
  deferred to planning)
- Existing `tokens` table will gain an `account_id` column via a
  forward-only ALTER TABLE migration; SQLite supports this without
  rewrite for the simple-column case (no NOT NULL, no FK enforcement
  required — `PRAGMA foreign_keys=ON` is best-effort referential check
  on writes only)

## Outstanding Questions

### Resolved during this brainstorm

- **Approach** — ✅ B½ (magic-link + balance + history) over the lighter A/B
  variants and the heavier C variant
- **Migration** — ✅ Honor existing bearer tokens in place; no migration UI
- **Free tier gating** — ✅ Stays anonymous
- **Marketing opt-in default** — ✅ Checked-by-default (CAN-SPAM compliant,
  GDPR risk accepted and filed as follow-up)
- **Credit model** — ✅ Hybrid (per-pack internal, pooled display, computed
  balance — no counter column)
- **Credit expiry** — ✅ Never expire while account exists
- **History contents** — ✅ Metadata + downloadable output file
- **Retention window** — ✅ 30 days with 100 GB total cap and LRU prune

### Deferred to planning

- Exact magic-link email body + subject line (R2) — copy decisions belong
  in the implementation ticket
- Exact `/login` and `/account` page layouts — visual/IA decisions belong
  in the design pass (likely a separate Figma iteration ticket if needed)
- Rate-limit numeric tuning (R2 currently has placeholder
  3/15min/email + 10/hr/IP — tune post-launch on observed abuse)
- Session cookie vs JWT debate — recommend signed cookie via `itsdangerous`
  for server-side simplicity; planner may override if there's a strong
  reason
- Whether to use Cloudflare KV or in-process for rate-limiting — planner's
  call based on deployment constraints
- Migration script for the `tokens.account_id ALTER TABLE` — straightforward
  but worth a tested deploy
- Whether the post-purchase upsell on `/payment/success` should show only
  for "first-purchase" sessions or for all anonymous purchases — UX call

### Deferred to follow-up tickets (not Phase 3)

- GDPR-compliant geo-gated opt-in default (Cloudflare `CF-IPCountry`
  detect + unchecked checkbox for EU) — file as separate ticket
- Self-service account deletion / data export — separate privacy-rights
  ticket
- Marketing campaign tooling (segmentation, scheduling, analytics) —
  separate marketing epic
- Inactivity-based credit expiration sweep — re-evaluate when accounting
  liability materially grows
- OAuth providers (Google/Apple) — only if evidence shows demand
- Email change flow — only if support burden justifies

## Proposed Ticket Breakdown

Phase 3 splits cleanly into five implementation tickets, broadly executable
in the order shown (3A blocks everything; 3B/3C/3D can parallelize once 3A
ships; 3E integrates the rest):

- **EB-XXXa (Phase 3A) — Magic-link auth + accounts table + email send.**
  R1, R2, R3, R4, R5, R6. The foundation. Ships `/login`, `/api/auth/*`,
  `accounts` table, session cookie helper, Resend integration for
  magic-link email.
- **EB-XXXb (Phase 3B) — Credit binding + claim flow.** R7, R8, R9, R10,
  R11, R23, R24. `tokens.account_id` column, post-purchase claim flow,
  pooled balance query, Stripe webhook attaches `account_id` on
  logged-in purchases.
- **EB-XXXc (Phase 3C) — Marketing opt-in + unsubscribe.** R12, R13, R14,
  R15. Opt-in checkbox in signup form, unsubscribe route, list capture.
- **EB-XXXd (Phase 3D) — Conversion history + re-download.** R16, R17,
  R18, R19, R20. `conversions` table, file retention plumbing, daily
  sweep, download route.
- **EB-XXXe (Phase 3E) — Account UI page + signed-in header.** R21, R22.
  `/account` page, header indicator, integrates the prior four tickets
  into a single user-visible surface.

## Next Steps

→ File the five tickets above under EB-45 as Phase 3 sub-tasks
→ Run `/ce:plan` against this requirements doc to produce
  `docs/plans/2026-05-16-eb45-phase3-accounts-persistent-tokens-plan.md`
→ Execute Phase 3A first (foundation), then parallelize 3B/3C/3D in
  separate worktrees, integrate via 3E
