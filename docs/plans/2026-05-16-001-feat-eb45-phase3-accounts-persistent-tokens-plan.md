---
title: "feat(EB-284): Phase 3 — Magic-link accounts, persistent credits, conversion history"
type: feat
status: superseded
date: 2026-05-16
superseded_on: 2026-05-16
superseded_by: docs/brainstorms/2026-05-16-eb45-phase3b-stripe-customer-binding-and-light-mailing-list-requirements.md
origin: docs/brainstorms/2026-05-16-eb45-phase3-accounts-persistent-tokens-requirements.md
---

> **SUPERSEDED 2026-05-16.** This plan was authored, document-reviewed, and then
> retired the same day after the review surfaced a simpler alternative that meets
> the same goals (token loss + opt-in mailing list) at ~20% of the implementation
> cost. The replacement direction is **Stripe-customer-binding** for credit recovery
> + a **standalone lightweight email-signup form** for the mailing list, with no
> first-party accounts table, no magic-link auth, no session cookies, no PII
> storage on leafbind's side, and no conversion-history retention infrastructure.
>
> The full document-review surfaced 12 auto-fixes (applied) + ~30 present findings,
> 8 of which were strategic premise challenges from the product-lens persona. The
> decisive challenge was: "Bind credits to Stripe `customer_id` and provide a
> `/recover?email=…` flow that calls Stripe Customer Search — ~70% of the value
> at <20% of the implementation cost, with the privacy positioning preserved."
>
> Jira tickets EB-284 (epic) + EB-285 through EB-289 (child tasks) were closed as
> Won't Do on 2026-05-16 with comments linking to this notice. The new direction
> is being brainstormed as Phase 3B (Stripe-binding flavor) and will produce a
> fresh requirements doc + plan + tickets.
>
> The remainder of this document is preserved for historical record. **Do not
> implement against it.**

# feat(EB-284): Phase 3 — Magic-link accounts, persistent credits, conversion history

## Overview

Phase 3 pivots leafbind.io from Phase 2's "no accounts / bearer tokens / 7-day TTL" architecture
to a magic-link-authenticated account model with persistent credits, 30-day conversion history
with re-download, and an opt-in mailing list. The anonymous free-tier flow at `/` is preserved
unchanged — login is introduced only at the point of paid intent and as an upsell on the
post-purchase success page.

The work is split across five Jira tickets (EB-285 through EB-289) under epic EB-284 and breaks
down into 16 implementation units, with EB-285 (Phase 3A — foundation) blocking the rest and
EB-286/287/288 (Phase 3B/3C/3D) parallelizable in separate worktrees once 3A merges. EB-289
(Phase 3E — UI integration) lands last.

## Problem Frame

Phase 2 shipped with two known trade-offs that have now materialized as product pain points:

1. **Token loss.** Bearer-token UX assumes users bookmark the success URL, save tokens to a
   password manager, or download `tokens.txt`. In practice people close tabs and switch
   devices. The R8a-R8e recovery flow from Phase 2 (revisitable success URL + `localStorage`)
   helps but doesn't survive losing the URL AND `localStorage` AND the Stripe receipt email.

2. **No mailing list.** Every purchase is a one-shot transaction with no channel to
   communicate updates, promos, or new features back to paying customers.

Phase 3 breaks the explicit Phase 2 "no PII" privacy positioning to capture opt-in PII for
compounding value, while preserving the anonymous free-tier funnel that drives leafbind.io's
SEO surface area. The full origin and decision rationale lives in
`docs/brainstorms/2026-05-16-eb45-phase3-accounts-persistent-tokens-requirements.md`.

## Requirements Trace

All requirement IDs reference the origin document.

- R1-R5 (magic-link auth routes + session helper) — Phase 3A, Units 3-5
- R6 (`accounts` table schema) — Phase 3A, Unit 1
- R7 (`tokens.account_id` migration) — Phase 3B, Unit 7
- R8 (post-purchase claim flow with race resolution) — Phase 3B, Unit 9
- R9 (pooled balance computed query) — Phase 3B, Unit 7
- R10 (credits never expire while account exists) — Phase 3B, Unit 8
- R11 (no migration of pre-Phase-3 bearer tokens) — Phase 3B, Unit 8 (no-op carry-forward)
- R12-R15 (marketing opt-in + unsubscribe) — Phase 3C, Units 10-11
- R16-R20 (conversion history + retention sweep + re-download) — Phase 3D, Units 12-14
- R21-R22 (`/account` UI + header signed-in indicator) — Phase 3E, Units 15-16
- R23-R24 (Stripe webhook + checkout `account_id` threading) — Phase 3B, Unit 8

## Scope Boundaries

**In scope:**
- Magic-link auth (request + verify with GET-then-confirm interstitial + logout)
- Session cookies via signed `itsdangerous` payload + `session_version` revocation backstop
- `accounts`, `magic_link_nonces`, `conversions` tables
- `tokens.account_id` nullable FK column + post-purchase claim flow with retry-on-pending-mint
- Pooled balance computed from `tokens` (no counter column)
- Conversion history with 30-day file retention, 100 GB cap, LRU prune
- Re-download route gated by session ownership
- `/account` page, `/login` page, signed-in header indicator
- Unsubscribe link with confirmation interstitial in all transactional emails
- Stripe webhook + success-page mint paths threading `account_id`
- Python Resend REST integration (`web_service/email.py`)
- ADR documenting the privacy-positioning reversal

**Out of scope for Phase 3:**
- Marketing email campaign tooling (segmentation, scheduling, analytics)
- Inactivity-based credit expiration sweep
- Self-service account deletion (stubs to support)
- OAuth providers
- Multi-device session management UI
- Email change flow
- GDPR geo-gated opt-in default
- Conversion history search / filter / pagination beyond the 30-day window

### Deferred to Separate Tasks

- Phase 2 compound retro (chargeback/idempotency patterns currently live only in plan docs) —
  file as a follow-up `docs/solutions/` entry after Phase 3 merges
- GDPR-compliant geo-gated opt-in default (`CF-IPCountry` detect, unchecked checkbox for EU) —
  file as separate ticket; not blocking Phase 3
- Marketing campaign tooling — separate epic
- Programmatic account deletion / data export — separate privacy-rights ticket

## Context & Research

### Relevant Code and Patterns

**Store conventions (mandatory to match):**
- `web_service/token_store.py:126-150` — `_get_conn()` contextmanager with
  `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000`. New stores copy this.
- `web_service/token_store.py:53-83` — `_SCHEMA_SQL` constant with `CREATE TABLE IF NOT EXISTS`.
- `web_service/job_store.py:53-72` — `_LATER_COLUMNS: list[tuple[str, str]]` +
  `_apply_migrations(conn)` runs idempotent `ALTER TABLE … ADD COLUMN` per row, gated by
  `PRAGMA table_info(...)`. **This is the canonical forward-only migration pattern.**
- `web_service/token_store.py:98-119` — frozen-dataclass result shapes (`MintResult`,
  `TokenValidationResult`), `str Enum` error code taxonomy. New stores follow this shape.
- All store APIs are sync — callers wrap in `loop.run_in_executor(billing_executor, ...)`.
  See `web_service/routes/webhook.py:179`, `web_service/routes/payment.py:300`,
  `web_service/routes/convert.py:81`.

**Mint paths to update for `account_id` threading:**
- `web_service/routes/webhook.py:146-185` — primary `mint_tokens_if_absent` call site.
- `web_service/routes/payment.py:394-414` — secondary idempotent mint call site (success-page
  render when webhook hasn't fired yet). **Both must update in the same change.**
- `web_service/routes/checkout.py:115-122` — seeds `payment_intent_data.metadata`.
- `web_service/routes/checkout.py:51-61` — `_derive_idempotency_key()` must include
  `account.id` in the seed to prevent anonymous-then-logged-in collisions inside the 30s bucket.

**Frontend integration points:**
- `web_service/frontend/next.config.js:19-24` — proxy rewrites. New auth/unsubscribe/download
  endpoints land here, which keeps cookies same-origin (`SameSite=Lax` rather than `None`).
- `web_service/frontend/lib/api.ts:66-73` — `ApiError` + `fetch` pattern; new auth client
  methods extend this file.
- `web_service/frontend/components/Header.tsx:11-17` — currently auth-state-free; becomes
  Server Component reading `cookies()` from `next/headers`.
- `web_service/frontend/app/(app)/contact/page.tsx`, `recover/page.tsx` — Server Component
  pattern (`async` + `await searchParams`). `/account` and `/login` follow this convention.

**Middleware safety guard:**
- `web_service/main.py:44` — `_MIDDLEWARE_ALLOWLIST = {"CORSMiddleware"}`.
  `_check_middleware_safety()` at `main.py:103-121` warns on startup if non-allowlisted
  middleware is added. The webhook handler in `routes/webhook.py` depends on raw
  `await request.body()` access for Stripe signature validation; SessionMiddleware would break this.
- **Decision: do NOT install Starlette SessionMiddleware.** Roll a `get_account_from_request(req)`
  helper that reads `req.cookies.get("leafbind_session")` directly and verifies via
  `itsdangerous.URLSafeTimedSerializer`. Preserves the webhook invariant cleanly.

**Existing Resend integration (TypeScript only):**
- `cloudflare/contact-worker/src/send.ts:22-50` — Resend REST API call pattern to port.
- **Python email send is net new.** No `smtplib` / `email.mime` / `resend` SDK in the repo
  today. `tools/email_to_kindle.py` is unrelated (Kindle email feature, not transactional).

### Institutional Learnings

- `docs/solutions/best-practices/leafbind-email-auth-stack-2026-05-16.md` — production-proven
  Resend + DKIM/SPF/DMARC stack. **Reuse verbatim; do not redesign.** Magic-link mail passes
  authentication via the same `send.leafbind.io` subdomain SPF + `resend._domainkey` DKIM
  selector already in place.
- `docs/solutions/best-practices/cloudflare-workers-first-deployment-leafbind-2026-05-16.md` —
  establishes the KV rate-limit prefix-bucket pattern (`rl:ip:<bucket>`,
  `rl:email:<sha256>:<bucket>`, `floor(unix/3600)`-style fixed windows) and the
  sha256-bucketed email storage rule. **Apply the same pattern to magic-link request limits**
  even though Phase 3 routes live in FastAPI rather than a Worker — same conceptual model.
- `docs/solutions/security-issues/xss-unescaped-session-id-fastapi-fstring-templates-2026-05-15.md` —
  `html.escape(value, quote=True)` is **mandatory** for any user-controlled value reflected
  in FastAPI f-string templates. Phase 3 magic-link confirmation pages, `/unsubscribe`
  pages, and any email-bearing FastAPI HTML render path must honor this. Extend the existing
  CI grep to cover `magic_token`, `user_email`, `download_url`.
- `docs/solutions/best-practices/fastapi-nextjs-css-token-sharing-python-shell-2026-05-15.md` —
  the FastAPI-renders-payment-pages / Next.js-renders-public split is the deliberate
  architecture. The `_BrandStaticFiles` subclass + `_render_*` helper pattern for multi-state
  routes applies directly to the 4+ magic-link verify states (sent / consumed / expired /
  invalid).
- `docs/solutions/best-practices/vercel-production-branch-misconfiguration-2026-05-15.md` —
  `productionBranch: master` fix is already in place; Phase 3 frontend changes deploy
  normally. Standard `vercel ls` verification ritual still applies.
- `docs/solutions/workflow-issues/cloudflare-cache-purge-fallback-querystring-2026-05-14.md` —
  `leafbind.io` apex is DNS-only to Vercel (not CF-proxied). No CF cache purge needed for
  account-page deploys or post-retention sweep. Only `api.leafbind.io` (FastAPI) is CF-proxied.
- `docs/templates/subagent-delegation-contract.md` — canonical per-stream coordinator/subagent
  contract: `files_in_scope` allowlist, Phase A checkpoint commit, STATUS.md (untracked),
  frozen shared interfaces, never `git add .`. **Use verbatim for the 3B/3C/3D parallel
  worktree spawn** (see "Phased Delivery" below).

### External References

External research was deliberately skipped — the auth stack (FastAPI + `itsdangerous` +
SQLite + Resend) is well-trodden, and the codebase has strong local patterns for every
moving piece. If implementation surfaces a question about specifically novel territory
(e.g., `itsdangerous` cookie sliding-renewal patterns), the implementer should consult
`framework-docs-researcher` at that point.

## Key Technical Decisions

- **Roll-our-own cookie reader, not `SessionMiddleware`.** Preserves the webhook raw-body
  invariant guarded by `_MIDDLEWARE_ALLOWLIST` at `web_service/main.py:44` without extending
  the allowlist (which is a forward-looking guard worth keeping tight). The
  `get_account_from_request()` helper reads `req.cookies.get("leafbind_session")` directly,
  verifies via `itsdangerous.URLSafeTimedSerializer`, returns `Account | None`. Cost: ~20 lines.
- **Magic-link verify uses GET-then-confirm interstitial.** Email-client URL prefetching
  (Outlook SafeLinks, iCloud Private Relay, corporate scanners) follows inbound URLs to scan
  for malware and would consume the single-use nonce before the user ever clicks. The
  interstitial renders "Sign in as you@example.com" with a Confirm button that POSTs to the
  actual verify endpoint. Single-use nonce only consumed at POST time.
  **Note on Outlook SafeLinks:** when a corporate Outlook tenant rewrites the link via
  `safelinks.protection.outlook.com`, the signed token is logged at Microsoft's edge.
  The 15-min TTL and POST-time nonce consumption keep the practical risk bounded, but
  this is a known disclosure path inherent to corporate-email magic-link flows.
- **`session_version` revocation backstop.** `accounts.session_version INTEGER NOT NULL DEFAULT 1`,
  carried in the signed cookie payload as `{account_id, session_version, issued_at}`. Logout
  bumps the version; `get_account_from_request()` rejects cookies with stale version. Solves
  the "lost device, can't force logout" hole without a sessions table. **Implication:**
  bumping `session_version` invalidates ALL existing cookies for that account simultaneously,
  so logout on any device signs the user out everywhere. This is the intended security
  trade — the alternative is a full sessions table which is out of scope for Phase 3. The
  `/account` sign-out copy and the ADR should call this out explicitly so users are not
  surprised.
- **R8 claim race resolved with bounded retry-on-pending-mint.** The brainstorm assumed
  "0 rows matched = already claimed by another account." Flow analysis surfaced a third
  state: tokens don't exist yet because the user beat the Stripe webhook (which can lag
  1-30 seconds). Solution: if the claim UPDATE returns 0 rows AND no rows exist for the
  pack_id, sleep 2 s and retry up to 3 times. After 3 retries with still no rows, render
  "Your purchase is still being processed. This page will refresh in 10 seconds." Auto-refresh.
- **Token consumption FIFO by `created_at` then `rowid`.** Brainstorm was silent on which
  token gets consumed when the user has 10 across 2 packs. FIFO matches user expectation
  ("oldest credits first") and means disputes are scoped predictably (newest pack still has
  unspent tokens if older pack is disputed).
- **Migration deploy = documented maintenance window.** `tokens.account_id ALTER TABLE` runs
  in `_apply_migrations()` at lifespan startup. The webhook holds `BEGIN IMMEDIATE` across
  Stripe API calls; under `busy_timeout=5000ms`, a slow webhook can collide with the ALTER
  and crash the migration. Plan: (a) pause Stripe webhook delivery via Stripe Dashboard
  ~30 seconds before deploy, (b) deploy code, (c) lifespan startup runs migration with
  `PRAGMA busy_timeout=30000` (temporary 30 s override for the ALTER specifically),
  (d) verify migration logs, (e) resume webhook delivery. Stripe's ~3-day retry budget
  absorbs the pause window safely. Net downtime: ~60 seconds.
- **Sweep ordering: DB UPDATE first, then `unlink`.** A crash mid-sweep with the file
  unlinked but DB row still pointing to the file would render a broken Download button.
  The reverse (DB row updated, file still on disk) leaves an orphan that gets re-swept on
  the next run — harmless.
- **Disk-full at job-completion copy: log warning, do not block conversion.** Insert the
  `conversions` row with `file_path=NULL`. The conversion still completes and the user can
  download via the existing `/status/<id>/download` route within the job's lifecycle.
  Long-term retention is the only thing they lose.
- **Forwarded unsubscribe = confirmation interstitial + token rotation on toggle.** The
  brainstorm's R13 specifies one-click unsubscribe (CAN-SPAM standard). The flow analyzer
  surfaced that a forwarded marketing email with an unrotated token lets a third party
  unsubscribe the original account. Compliance interpretation: CAN-SPAM requires "easy to
  comply" — a confirmation page with one prominent button still counts. Decision: render
  `/unsubscribe?token=…` as a confirmation page ("Confirm: unsubscribe `<email>` from
  marketing emails?"), and rotate `unsubscribe_token` on every opt-in/opt-out toggle so
  leaked tokens self-invalidate.
- **Marketing unsubscribe scope is marketing only.** Magic-link emails are always sent
  regardless of `marketing_opted_in` status. Email-footer copy must distinguish.
- **Stale-prior-session is overwritten silently with `/account` banner.** When user A is
  logged in and user B types their email at `/login` on the same browser, the new magic-link
  verify silently replaces the session cookie. `/account` renders a banner: "Signed in as
  you@example.com. Not you? [Sign out]." This matches Substack/Notion behavior — full
  confirmation would block the common case (user signing in on a friend's device).
- **Resend integration in Python (option 1 from research).** Mirror the Worker's
  `cloudflare/contact-worker/src/send.ts:22-50` pattern as `web_service/email.py` using
  `httpx`. Adds `RESEND_API_KEY` env var, `_require_env()` enforced.
- **Next.js auth endpoints proxied via `next.config.js` rewrites.** Keeps cookies
  same-origin (`SameSite=Lax`), matches the existing `/api/recover` and `/payment/success`
  proxy pattern.
- **ADR for privacy-positioning reversal lands in 3A.** New `docs/decisions/ADR-EB-284-privacy-positioning-reversal.md`
  documents the Phase 2 → Phase 3 stance change. Future engineers reading the codebase need
  the rationale on record, not just buried in a brainstorm.
- **Anonymous-then-claimed history shows "Conversions since you signed up."** Pre-signup
  bearer-token conversions aren't in `conversions` (R17 anonymity). UI copy sets the
  expectation up-front instead of confusing returning users.

## Open Questions

### Resolved During Planning

- **Magic-link prefetch defense** — GET-then-confirm interstitial.
- **Session revocation strategy** — `session_version` increment on logout.
- **Claim flow race** — bounded retry-on-pending-mint with auto-refresh page.
- **Token consumption order** — FIFO by `created_at`, `rowid`.
- **Migration deploy strategy** — paused webhook + temporary `busy_timeout=30000`.
- **Forwarded unsubscribe** — confirmation page + token rotation; marketing-only scope.
- **Stale session collision** — silent overwrite + `/account` banner.
- **Email send infrastructure** — Python Resend REST via `httpx`, new `web_service/email.py`.
- **Migration runner location** — extend `web_service/token_store.py` with its own
  `_LATER_COLUMNS` + `_apply_migrations()` mirroring `web_service/job_store.py:53-72`.
- **Session cookie format** — `itsdangerous`-signed `{account_id, session_version, issued_at}`
  JSON payload. HTTP-only, Secure, SameSite=Lax, 90-day sliding renewal.

### Deferred to Implementation

- Exact magic-link email subject + body copy. Keep terse and plain-text per the existing
  Worker pattern at `cloudflare/contact-worker/src/send.ts:81,110`.
- Exact `/login` and `/account` visual layouts. Server-rendered with the existing
  `_BrandStaticFiles` styling primitives. If significant Figma iteration is needed, file
  as a sibling design ticket.
- Rate-limit numeric tuning (Phase 3A starts with 3 link requests / 15 min / email and
  10 / hr / source IP per origin doc; tune post-launch on observed abuse).
- Whether to use Cloudflare KV or app-process (in-memory + DB) for auth route rate
  limiting. Recommend app-process for Phase 3 (FastAPI runs on a single VM); revisit if
  scaling forces a multi-instance deploy.
- Exact retry backoff interval for claim flow (plan says 2 s × 3 attempts; implementer
  may adjust based on observed webhook lag).
- LRU prune threshold tuning (plan: prune to 90 GB when total exceeds 100 GB; tune
  post-launch on observed conversion volume).

## Output Structure

New files and directories created by Phase 3:

```
web_service/
├── accounts_store.py              [Unit 1]
├── conversions_store.py           [Unit 12]
├── email.py                       [Unit 2]
├── session.py                     [Unit 4]  -- get_account_from_request() helper
└── routes/
    ├── auth.py                    [Unit 3]  -- /api/auth/{request-link, verify, logout, me}
    ├── account.py                 [Unit 14] -- /account/conversions/<id>/download
    └── unsubscribe.py             [Unit 11] -- /unsubscribe confirmation page

web_service/frontend/
├── app/(app)/
│   ├── login/page.tsx             [Unit 5]  -- Server Component
│   └── account/page.tsx           [Unit 15] -- Server Component
└── components/
    ├── LoginForm.tsx              [Unit 5]  -- "use client"
    └── AccountMenu.tsx            [Unit 16] -- header dropdown ("use client")

(NOTE: ClaimAccountUpsell and PendingClaimRefresh are FastAPI-rendered HTML helpers
in web_service/routes/auth.py and web_service/routes/payment.py respectively — NOT React
components. The /payment/success page is server-rendered by FastAPI, so React hydration
boundaries are not needed for these surfaces.)

docs/decisions/
└── ADR-EB-284-privacy-positioning-reversal.md  [Unit 6]

tests/
├── test_web_accounts_store.py     [Unit 1]
├── test_web_conversions_store.py  [Unit 12]
├── test_web_email.py              [Unit 2]
├── test_web_session.py            [Unit 4]
├── test_web_auth_routes.py        [Unit 3]
├── test_web_account_routes.py     [Unit 14]
└── test_web_unsubscribe_routes.py [Unit 11]
```

Modified files (per unit; full list in the individual unit sections):
`web_service/main.py`, `web_service/config.py`, `web_service/token_store.py`,
`web_service/routes/webhook.py`, `web_service/routes/checkout.py`,
`web_service/routes/payment.py`, `web_service/routes/convert.py`,
`web_service/pipeline_runner.py`, `web_service/frontend/lib/api.ts`,
`web_service/frontend/next.config.js`, `web_service/frontend/components/Header.tsx`,
`requirements.txt`, `feature-manifest.json`.

This is a scope declaration showing the expected output shape. The implementer may
adjust the structure if implementation reveals a better layout. Per-unit `**Files:**`
sections remain authoritative.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not
> implementation specification. The implementing agent should treat it as context, not code
> to reproduce.*

### Magic-link flow (GET-then-confirm)

```
User → /login (Next.js Client Component)
     → submit email
     → POST /api/auth/request-link (FastAPI, proxied via next.config.js rewrite)
         → email-validator shape check
         → INSERT-or-NOOP accounts row (UNIQUE email)
         → INSERT magic_link_nonces (account_id, nonce, expires_at = now + 15 min)
         → render token = itsdangerous.URLSafeTimedSerializer({account_id, nonce}).dumps()
         → email Resend: "Sign in to leafbind: https://leafbind.io/api/auth/verify?token=…"
         → return 204 (same response for existing/new email — no enumeration)
User clicks link in email
     → GET /api/auth/verify?token=… (FastAPI)
         → unsign + validate TTL (no nonce consumption yet)
         → render interstitial: "Sign in as you@example.com [Confirm]"
              ↑ defeats email-client URL prefetch (Outlook/iCloud/corporate scanners)
User clicks Confirm
     → POST /api/auth/verify?token=… (FastAPI)
         → unsign + validate TTL + delete nonce (single-use enforcement here)
         → bump accounts.last_login_at
         → Set-Cookie: leafbind_session = signed({account_id, session_version, issued_at})
         → 302 → /account
```

### Claim flow state machine (R8 with race resolution)

```
                           User on /payment/success (anonymous)
                                          |
                                          v
                          ClaimAccountUpsell: email + "Save credits"
                                          |
                                          v
                      Magic-link request-link → verify → POST /api/auth/verify
                                          |
                                          v
                     POST also reads pending_pack_id from URL param or localStorage
                                          |
                                          v
                        BEGIN IMMEDIATE
                                          |
                                          v
                UPDATE tokens SET account_id=? WHERE pack_id=? AND account_id IS NULL
                                          |
              +---------------------------+----------------------------+
              v                                                        v
       rowcount > 0                                              rowcount == 0
              |                                                        |
              v                                                        v
       COMMIT → /account                                  SELECT EXISTS(pack_id) ?
                                                                       |
                                       +-------------------------------+--------------------+
                                       v                                                    v
                                no rows exist                                       rows exist + account_id != NULL
                                       |                                                    |
                                       v                                                    v
                                ROLLBACK; attempt_count++                            ROLLBACK
                                       |                                                    |
                                       v                                                    v
                              attempt_count <= 3 ?                              render "this pack is attached
                                       |                                          to another account" error
                          +------------+------------+
                          v                         v
                         yes                        no
                          |                          |
                          v                          v
                  sleep 2 s; retry         render PendingClaimRefresh:
                                            "Your purchase is being processed.
                                             Auto-refresh in 10 seconds."
```

The pending-mint case is the realistic race when a user pays, types email, and clicks
the magic link within ~5 seconds — Stripe webhook may not have fired yet. After 3 retries
(~6 seconds) we surrender to the auto-refresh UI, which the webhook will resolve within
its normal lag window.

### Migration ordering for `tokens.account_id`

```
T-30s: Stripe Dashboard → pause webhook delivery for endpoint
T-0:   Deploy new code (containing tokens._LATER_COLUMNS entry for account_id)
T+1s:  Service restarts → lifespan startup runs init_db()
            → token_store._apply_migrations() with PRAGMA busy_timeout=30000
            → ALTER TABLE tokens ADD COLUMN account_id INTEGER REFERENCES accounts(id)
            → completes within a few hundred ms on an empty/small webhook window
T+5s:  Verify migration log line ("token_store: ADD COLUMN account_id applied")
T+5s:  Stripe Dashboard → resume webhook delivery
T+5..120s: Stripe redelivers any queued events (within their 3-day budget)
```

## Implementation Units

### Phase 3A — Foundation (EB-285)

These six units are sequential dependencies for everything that follows; ship and merge
EB-285 before spawning 3B/3C/3D.

---

- [ ] **Unit 1: `accounts_store.py` + `magic_link_nonces` table + migration runner**

**Goal:** Land the `accounts` and `magic_link_nonces` tables and the forward-only
migration runner that subsequent units extend.

**Requirements:** R6 (accounts schema)

**Dependencies:** None — first unit of Phase 3.

**Files:**
- Create: `web_service/accounts_store.py`
- Modify: `web_service/main.py` (call `accounts_store.init_db()` in lifespan)
- Modify: `web_service/token_store.py` (add empty `_LATER_COLUMNS` + `_apply_migrations()`
  mirror of `web_service/job_store.py:53-72`, ready for Unit 7's column addition)
- Test: `tests/test_web_accounts_store.py`

**Approach:**
- Mirror `web_service/token_store.py:126-150` for the connection contextmanager
  (`PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000`).
- Mirror `web_service/job_store.py:53-72` for `_LATER_COLUMNS` + `_apply_migrations(conn)`.
- `accounts` schema includes `session_version INTEGER NOT NULL DEFAULT 1` (revocation
  backstop), `unsubscribe_token TEXT NOT NULL UNIQUE` (generated via `secrets.token_urlsafe(32)`
  at INSERT time), and `marketing_opted_in INTEGER NOT NULL DEFAULT 0` (Unit 10 populates).
- `magic_link_nonces (nonce TEXT PRIMARY KEY, account_id INTEGER, expires_at INTEGER)`.
  No FK constraint enforcement (decorative — matches existing pattern).
- Public API: `create_or_get_account(email) → Account`, `bump_session_version(account_id)`,
  `consume_nonce(nonce) → account_id | None`, `record_nonce(account_id, nonce, expires_at)`.

**Patterns to follow:**
- `web_service/job_store.py` for migration runner shape.
- `web_service/token_store.py` for store API shape (frozen dataclass `Account`,
  `_get_conn()` contextmanager, sync API).

**Test scenarios:**
- *Happy path:* `create_or_get_account("a@b.com")` twice returns same `id` and `unsubscribe_token`.
- *Happy path:* `record_nonce` then `consume_nonce` returns `account_id`, second consume returns `None`.
- *Edge case:* email collation is case-insensitive — `"A@B.com"` and `"a@b.com"` resolve to same row.
- *Edge case:* `consume_nonce` past `expires_at` returns `None` and deletes the row.
- *Edge case:* `bump_session_version` increments by 1 atomically under concurrent calls.
- *Integration:* `init_db()` is idempotent — second run does not duplicate rows.
- *Migration:* adding a column to `_LATER_COLUMNS` and re-running `_apply_migrations` adds
  the column; running again is a no-op (verifies the `PRAGMA table_info` gate).

**Verification:**
- `pytest tests/test_web_accounts_store.py -v` passes.
- DB inspection after `init_db()` shows `accounts` and `magic_link_nonces` tables present
  with expected schema.

---

- [ ] **Unit 2: `web_service/email.py` — Python Resend integration**

**Goal:** Python-side transactional email send via Resend REST API. Used by Units 3, 9, 11.

**Requirements:** R2 (email send), R13 (unsubscribe link in transactional emails)

**Dependencies:** None — can land in parallel with Unit 1 conceptually but sequenced after
for review-ergonomic reasons.

**Files:**
- Create: `web_service/email.py`
- Modify: `web_service/config.py` (add `RESEND_API_KEY = _require_env("RESEND_API_KEY")`)
- Modify: `requirements.txt` (add `httpx>=0.27,<1.0` explicitly — currently only a
  transitive dependency via `anthropic`/`google-genai`/`openai`, would silently break
  `web_service/email.py` if any of those SDKs is removed)
- Test: `tests/test_web_email.py`

**Approach:**
- Mirror `cloudflare/contact-worker/src/send.ts:22-50` — POST to
  `https://api.resend.com/emails` with `Authorization: Bearer ${RESEND_API_KEY}`.
- Public API: `send_email(to: str, subject: str, text_body: str, *, include_unsubscribe_link: bool = False, unsubscribe_token: str | None = None) → SendResult`
  where `SendResult` is `@dataclass(frozen=True)` with `ok`, `message_id`, `error` fields.
- Plain-text only (matches Worker pattern). From: `leafbind <support@leafbind.io>`.
- When `include_unsubscribe_link=True`, append a footer: `\n\n---\nUnsubscribe from marketing emails: https://leafbind.io/unsubscribe?token={token}`.
  Magic-link emails set `include_unsubscribe_link=False` (per R13 scope decision).
- Retry on 5xx: one retry with 2 s jitter.

**Patterns to follow:**
- `cloudflare/contact-worker/src/send.ts:22-50` (Resend REST contract).
- `web_service/token_store.py` for `SendResult` shape (frozen dataclass).

**Test scenarios:**
- *Happy path:* mock `httpx.post` returning 200 + message_id; `send_email(...)` returns `ok=True`.
- *Error path:* mock 5xx → retried once → still 5xx → `ok=False, error="resend_5xx"`.
- *Error path:* mock 4xx → no retry → `ok=False, error="resend_4xx_<status>"`.
- *Error path:* `httpx.TimeoutException` → retried once → `ok=False` on second timeout.
- *Edge case:* `include_unsubscribe_link=True` with `unsubscribe_token=None` raises `ValueError`.
- *Edge case:* `text_body` containing `\r\n` is normalized to `\n` (prevents header injection).

**Verification:**
- `pytest tests/test_web_email.py -v` passes.
- Manual smoke: `python -c "from web_service.email import send_email; print(send_email('your@email', 'test', 'hello'))"`
  delivers to inbox in <60 s (run with real `RESEND_API_KEY` set).

---

- [ ] **Unit 3: Magic-link auth routes (`web_service/routes/auth.py`)**

**Goal:** Land `POST /api/auth/request-link`, `GET /api/auth/verify` (interstitial),
`POST /api/auth/verify` (consume + set cookie), `POST /api/auth/logout`, `GET /api/auth/me`.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** Units 1 (accounts), 2 (email), 4 (session helper — implement Unit 4 first).

**Files:**
- Create: `web_service/routes/auth.py`
- Modify: `web_service/main.py` (mount the router; add to `_MIDDLEWARE_ALLOWLIST` only if
  needed — should NOT be needed since we use direct cookie reads).
- Modify: `web_service/config.py` (add `MAGIC_LINK_SECRET = _require_env(...)`,
  `SESSION_COOKIE_SECRET = _require_env(...)`).
- Modify: `requirements.txt` (add `itsdangerous`, `email-validator`).
- Modify: `web_service/frontend/lib/api.ts` (add `requestMagicLink`, `logout`, `getMe`).
- Modify: `web_service/frontend/next.config.js` (rewrite `/api/auth/*` → FastAPI).
- Test: `tests/test_web_auth_routes.py`

**Execution note:** Implement test-first. Auth routes are high-risk for subtle correctness
bugs (single-use enforcement, TTL, signature validation); failing tests for each property
keep the implementation honest.

**Approach:**
- `POST /api/auth/request-link` body: `{"email": str, "marketing_opted_in": bool}` (Unit 10
  populates the bool; default `True` for now per checked-default decision).
- 204 response for both new and existing accounts (no enumeration oracle, R2).
- App-process rate limit: in-memory dict keyed on `sha256(normalized_email)` and source IP.
  Per-email: 3 requests / 15-min window. Per-IP: 10 / hour. Implementer chooses an in-memory
  TTL cache helper (no new dependency needed; `cachetools` or just a dict + timestamp).
- `GET /api/auth/verify?token=…` renders the interstitial HTML with a `<form action="/api/auth/verify?token=…" method="POST">` and a confirm button.
  Uses `html.escape(quote=True)` for the displayed email and token (per
  `docs/solutions/security-issues/xss-unescaped-session-id-fastapi-fstring-templates-2026-05-15.md`).
- `POST /api/auth/verify?token=…` performs nonce consumption + session-cookie set in the
  same transaction. Bumps `accounts.last_login_at`. **Response routing:** if `pending_pack_id`
  is absent, 302 → `/account` (the default path). If `pending_pack_id` is present, hand
  off to Unit 9's claim flow, which may produce a 302 (claim succeeded), 409 (already
  attached to another account), or 202 PendingClaimRefresh render (race exhausted retries).
  See Unit 9 for the claim-flow state machine.
- `POST /api/auth/logout` calls `bump_session_version(account_id)`, clears cookie via
  `Set-Cookie: leafbind_session=; Max-Age=0; ...`, 302 → `/`.
- `GET /api/auth/me` returns `{"email": str, "credits_balance": int}` for header hydration
  (Unit 16) or 401 if no session. Read-only; no side effects.

**Patterns to follow:**
- `web_service/routes/recover.py` for FastAPI router file shape.
- `web_service/routes/payment.py` for FastAPI-rendered HTML response pattern (use
  `_render_*` helper pattern from
  `docs/solutions/best-practices/fastapi-nextjs-css-token-sharing-python-shell-2026-05-15.md`).

**Test scenarios:**
- *Happy path:* request-link → receive email → POST verify → cookie set → /me returns email.
- *Happy path:* request-link returns 204 for both new and existing emails (same response).
- *Edge case:* request-link with malformed email → 422.
- *Edge case:* GET verify renders the interstitial (does NOT consume the nonce).
- *Edge case:* POST verify with a nonce already consumed → 410 with "link already used" message.
- *Edge case:* POST verify with an expired token (>15 min) → 410.
- *Edge case:* POST verify with a token whose signature is tampered → 400.
- *Edge case:* rate limit: 4th request within 15 min for same email → 429.
- *Edge case:* rate limit: 11th request within 1 hr from same IP → 429.
- *Error path:* email send fails (mocked Resend 5xx) → still returns 204 (so as not to leak
  whether the email landed) BUT logs ERROR for operator alerting.
- *Edge case:* logout without a session cookie → 204 (idempotent).
- *Integration:* full request → verify → /me round-trip via FastAPI TestClient with cookie
  jar enabled.

**Verification:**
- `pytest tests/test_web_auth_routes.py -v` passes.
- Manual end-to-end smoke: `curl -X POST .../api/auth/request-link -d 'email=you@example.com'`
  delivers a working link.

---

- [ ] **Unit 4: Session cookie helper (`web_service/session.py`)**

**Goal:** Land `get_account_from_request(req: Request) → Account | None` for use by all
account-aware routes.

**Requirements:** R5

**Dependencies:** Unit 1 (`accounts_store.get_account_by_id`).

**Files:**
- Create: `web_service/session.py`
- Test: `tests/test_web_session.py`

**Approach:**
- `set_session_cookie(response, account)` — builds the cookie via
  `itsdangerous.URLSafeTimedSerializer(SESSION_COOKIE_SECRET).dumps({account_id, session_version, issued_at})`.
  Cookie attributes: HTTP-only, Secure, SameSite=Lax, `Max-Age=90 * 86400`, `Path=/`.
- `get_account_from_request(req)`:
  - Read `req.cookies.get("leafbind_session")`. If absent, return None.
  - Unsign with `max_age=90 * 86400`. On `SignatureExpired` or `BadSignature`, return None.
  - Look up account via `accounts_store.get_account_by_id`. If account doesn't exist, return None.
  - If `payload.session_version != account.session_version`, return None (revoked).
  - If `now - payload.issued_at > 30 * 86400`, re-issue the cookie (sliding renewal).
    Return `Account` with a marker so the caller can re-set the cookie on the response.
- Public function returns `Account | None`. Free-tier endpoints simply ignore the None case.

**Test scenarios:**
- *Happy path:* valid signed cookie → returns Account with matching id.
- *Edge case:* missing cookie → returns None.
- *Edge case:* tampered signature → returns None.
- *Edge case:* TTL expired (>90 days) → returns None.
- *Edge case:* `session_version` in cookie < account's `session_version` → returns None
  (revoked).
- *Edge case:* account row deleted but cookie still valid → returns None.
- *Edge case:* sliding renewal — issued_at >30d ago, <90d ago → returns Account + re-issue flag.
- *Edge case:* two cookies issued for same account with version=1, then `bump_session_version`
  runs (logout from one device); both cookies now return None (global-logout semantics).

**Verification:**
- `pytest tests/test_web_session.py -v` passes.

---

- [ ] **Unit 5: `/login` Next.js page + `LoginForm` client component**

**Goal:** Ship the frontend `/login` route.

**Requirements:** R1

**Dependencies:** Unit 3 (API endpoint exists).

**Files:**
- Create: `web_service/frontend/app/(app)/login/page.tsx` (Server Component)
- Create: `web_service/frontend/components/LoginForm.tsx` ("use client")
- Modify: `web_service/frontend/lib/api.ts` (`requestMagicLink` already added in Unit 3)
- Test: none — frontend component testing infrastructure not in scope for this phase.
  Manual visual + functional verification.

**Approach:**
- Server Component renders the page chrome and embeds `<LoginForm />`.
- LoginForm: single email field, marketing checkbox checked by default (Unit 10 controls
  the label and copy), "Send magic link" submit button.
- On submit, POST to `/api/auth/request-link` (proxied via `next.config.js`).
- On success, swap to "Check your inbox at `<email>` — the magic link expires in 15 minutes."
- On 429, show "Too many requests — try again in a few minutes."
- Validation matches the Phase 2 RecoverClient pattern (button label is stable; success
  state moves focus for a11y).

**Patterns to follow:**
- `web_service/frontend/app/(app)/recover/page.tsx` (Server Component pattern).
- `web_service/frontend/components/RecoverClient.tsx` ("use client" form pattern).

**Test scenarios:**
- Test expectation: none — no JS test infrastructure in scope. Manual verification only.

**Verification:**
- Navigate to `/login` on dev server, submit email, observe magic-link email arrives.
- Click link, land on interstitial, click Confirm, land on `/account` placeholder.

---

- [ ] **Unit 6: ADR for privacy-positioning reversal**

**Goal:** Document the architectural decision to reverse the Phase 2 "no PII" stance.

**Requirements:** None (cross-cutting documentation).

**Dependencies:** None.

**Files:**
- Create: `docs/decisions/ADR-EB-284-privacy-positioning-reversal.md`

**Approach:**
- Use the existing `docs/decisions/ADR-EB-181-data-exemption-scope.md` as a template.
- Sections: Status (Accepted), Context (Phase 2 stance), Decision (Phase 3 pivot), Consequences,
  Alternatives Considered (account-required-for-all vs. light email-only).
- Reference the brainstorm doc and this plan as supporting artifacts.

**Test scenarios:** Test expectation: none — documentation unit, no behavior change.

**Verification:**
- `git add docs/decisions/ADR-EB-284-privacy-positioning-reversal.md` and the file renders
  cleanly in GitHub markdown.

---

### Phase 3B — Credit binding (EB-286)

Depends on Phase 3A merge. Three units. Parallelizable with 3C and 3D in separate worktrees.

---

- [ ] **Unit 7: `tokens.account_id` migration + `mint_tokens_if_absent` signature**

**Goal:** Add the FK column, extend the mint API, expose pooled balance helper.

**Requirements:** R7, R9, R10

**Dependencies:** Unit 1 (`_apply_migrations()` runner present in `token_store.py`).

**Files:**
- Modify: `web_service/token_store.py` (add `account_id` to `_LATER_COLUMNS`, extend
  `mint_tokens_if_absent` keyword arg, extend INSERT statement, add
  `count_available_credits(account_id) → int` helper, modify
  `validate_and_consume` to skip the `expires_at > now` clause when `account_id IS NOT NULL`).
- Test: `tests/test_web_token_store.py` (extend existing file)

**Execution note:** The migration ALTER runs in `_apply_migrations()` with a temporary
`PRAGMA busy_timeout=30000` override applied at the migration boundary. Confirm the
existing `busy_timeout=5000` is restored after the ALTER completes (PRAGMA is per-connection).

**Approach:**
- Append `("account_id", "INTEGER REFERENCES accounts(id)")` to `_LATER_COLUMNS` in
  `web_service/token_store.py`.
- `mint_tokens_if_absent(session_id, count, payment_intent_id, *, account_id: int | None = None, db_path=None)`.
- INSERT statement adds an 8th column at the end.
- `count_available_credits(account_id)` returns
  `SELECT COUNT(*) FROM tokens WHERE account_id=? AND used=0 AND disputed=0`.
  Single-statement query, no transaction needed (read-only, WAL provides snapshot isolation).
- **Performance:** add a partial index for constant-time balance reads.
  `CREATE INDEX IF NOT EXISTS idx_tokens_account_balance ON tokens(account_id) WHERE account_id IS NOT NULL AND used=0 AND disputed=0;`
  The header dropdown calls this on every logged-in page load; without the index it
  degrades to a table scan at scale. Include the CREATE INDEX in `_apply_migrations()`
  alongside the `account_id` column add.
- `validate_and_consume(token)` adds a branch: load the token row's `account_id`; if
  non-NULL, the UPDATE WHERE clause omits `expires_at > now` (account-bound credits don't
  expire).

**Patterns to follow:**
- `web_service/job_store.py:53-72` for migration column-add pattern.
- Existing `mint_tokens_if_absent` body for transaction shape.

**Test scenarios:**
- *Happy path:* mint with `account_id=42` → row inserted with `account_id=42`.
- *Happy path:* mint with `account_id=None` → row inserted with `account_id=NULL` (existing behavior).
- *Migration:* run `_apply_migrations` once → column added. Re-run → no-op.
- *Edge case:* `count_available_credits` for non-existent account → returns 0.
- *Edge case:* `count_available_credits` for account with mixed used/unused/disputed → only counts unused-and-not-disputed.
- *Integration:* account-bound token (`account_id` set, `expires_at` in the past) validates
  successfully — expiry skipped.
- *Integration:* anonymous token (`account_id=NULL`, `expires_at` in the past) returns
  `INVALID_OR_EXPIRED` (existing Phase 2 behavior preserved).
- *Race:* two concurrent `validate_and_consume` calls on the same account-bound token →
  exactly one succeeds (existing BEGIN IMMEDIATE invariant).

**Verification:**
- `pytest tests/test_web_token_store.py -v` passes.
- Pre-merge: deploy to staging, run migration manually, verify column added without
  hitting `busy_timeout`.

---

- [ ] **Unit 8: Webhook + checkout + payment.py thread `account_id`**

**Goal:** Wire `account_id` through the three mint call sites.

**Requirements:** R23, R24

**Dependencies:** Units 4 (session helper), 7 (mint signature).

**Files:**
- Modify: `web_service/routes/webhook.py` (lines 146-185 area; read
  `obj.get("metadata", {}).get("account_id")`, parse int, pass to mint).
- Modify: `web_service/routes/checkout.py` (lines 115-122 metadata; seed
  `payment_intent_data.metadata.account_id` from session; also extend
  `_derive_idempotency_key()` at lines 51-61 to include `account.id`).
- Modify: `web_service/routes/payment.py` (lines 394-414 area; mirror webhook update).
- Test: `tests/test_web_webhook.py`, `tests/test_web_checkout.py`, `tests/test_web_payment.py`
  (extend existing files).

**Approach:**
- `checkout.py`: call `get_account_from_request(request)` (Unit 4). If non-None, add
  `metadata["account_id"] = str(account.id)`. Idempotency key seed: include
  `f":{account.id or 'anon'}"` to prevent anonymous-then-logged-in collision within the 30 s bucket.
- `webhook.py`: in the `checkout.session.completed` and `checkout.session.async_payment_succeeded`
  handlers, parse `account_id` from metadata. Pass to `mint_tokens_if_absent(account_id=...)`.
  Existing chargeback handler is unchanged.
- `payment.py`: success page mint path mirrors webhook — same metadata read + pass-through.

**Patterns to follow:**
- Existing metadata-read patterns in `web_service/routes/webhook.py` and
  `web_service/routes/payment.py`.

**Test scenarios:**
- *Happy path:* logged-in user creates checkout → metadata includes `account_id` →
  webhook fires → tokens minted with `account_id` populated.
- *Happy path:* anonymous user creates checkout → metadata has no `account_id` → tokens
  minted with `account_id=NULL` (Phase 2 behavior preserved).
- *Edge case:* webhook receives an event with malformed `account_id` (non-numeric string) →
  logs warning, mints with `account_id=NULL` (does not 500).
- *Race:* idempotency key collision avoidance — anonymous click then logged-in click within
  30 s on same pack produces two distinct Stripe sessions.
- *Integration:* `stripe trigger checkout.session.completed` with `metadata.account_id=1`
  via Stripe CLI mints account-bound tokens.

**Verification:**
- `pytest tests/test_web_webhook.py tests/test_web_checkout.py tests/test_web_payment.py -v` passes.
- Manual: log in, buy a pack, observe `tokens` table has `account_id` populated.

---

- [ ] **Unit 9: Post-purchase claim flow (success-page upsell + claim retry)**

**Goal:** Anonymous-purchase users can save credits via inline magic-link signup; race with
webhook resolved via bounded retry.

**Requirements:** R8

**Dependencies:** Units 3 (auth routes), 7 (mint with account_id), 8 (mint already threading).

**Files:**
- Modify: `web_service/routes/payment.py` (extend `/payment/success` render to include
  the `ClaimAccountUpsell` form when no session cookie is present; accept `pending_pack_id`
  query/localStorage carry-through).
- Modify: `web_service/routes/auth.py` (POST verify accepts optional `pending_pack_id`
  query param; after nonce consumption, runs the claim UPDATE with retry loop).
- Implement: `ClaimAccountUpsell` as a plain HTML form embedded in the FastAPI-rendered
  success page (`web_service/routes/payment.py`). Form action posts to
  `/api/auth/request-link?pending_pack_id=<id>`. Hidden input carries the session_id. No
  React component, no hydration boundary — the success page is server-rendered by FastAPI.
- Implement: `PendingClaimRefresh` as a FastAPI HTML render helper in
  `web_service/routes/auth.py` (e.g., `_render_pending_claim(session_id) → HTMLResponse`).
  Returns a page with a `<meta http-equiv="refresh" content="10">` tag for no-JS users
  AND a small inline script for JS users that re-POSTs to the claim endpoint with a fresh
  session/nonce cycle if needed (per the retry budget consideration in Open Questions).
- Test: extend `tests/test_web_auth_routes.py` with claim scenarios; extend
  `tests/test_web_payment.py` with upsell-render scenarios.

**Approach:**
- Success page (`payment.py`): if `get_account_from_request(request) is None`, render the
  existing token list AND below it an upsell card with the magic-link signup form. Form
  action: `POST /api/auth/request-link?pending_pack_id=<session_id>`. Hidden input carries
  the session_id.
- Magic-link email body in this flow varies: standard "Sign in" copy is fine — the
  `pending_pack_id` flows through the magic link URL as a signed payload extension (extend
  the nonce-payload signed JSON to include it).
- Verify POST: after consuming nonce + setting cookie, IF `pending_pack_id` is set:
  - BEGIN IMMEDIATE
  - `UPDATE tokens SET account_id=? WHERE pack_id=? AND account_id IS NULL`
  - If rowcount > 0: COMMIT, 302 → /account
  - Else: `SELECT EXISTS(SELECT 1 FROM tokens WHERE pack_id=?)`
    - If exists with `account_id` already set: ROLLBACK, 409 "already claimed by another account"
    - If no rows: ROLLBACK, attempt_count++. If attempt_count <= 3: sleep 2 s and retry.
      If attempt_count == 4: 202 → render PendingClaimRefresh page (auto-refresh after 10 s
      with a "Try claiming again" link that re-POSTs).
- PendingClaimRefresh renders a banner: "Your purchase is still being processed. This page
  will refresh in 10 seconds." Plus a meta refresh tag for users with no JS.

**Patterns to follow:**
- `web_service/routes/payment.py` for HTML rendering pattern.
- The existing recovery flow at `web_service/routes/recover.py` for the
  Next.js + FastAPI hybrid.

**Test scenarios:**
- *Happy path:* anonymous purchase → magic-link signup with `pending_pack_id` → verify
  POST → tokens attached, /account shows balance.
- *Race:* concurrent claim by two different accounts on same pack_id → second sees 409
  "already claimed" (NOT pending-mint loop, since rows DO exist with non-NULL account_id).
- *Race:* claim before webhook fires (no rows exist for pack_id) → enters retry loop;
  webhook fires during the 6 s window → next retry succeeds, 302 → /account.
- *Race:* claim before webhook fires AND webhook never fires (3 retries exhausted) →
  renders PendingClaimRefresh page; manual reclaim eventually succeeds when webhook lands.
- *Edge case:* magic-link signup WITHOUT `pending_pack_id` (normal login flow) → standard
  302 → /account with no claim attempt.
- *Edge case:* `pending_pack_id` referencing a pack that already has `account_id` set to
  the SAME account (idempotent re-claim) → succeeds silently (rowcount=0 from WHERE clause
  but SELECT shows account match → treat as success).
- *Edge case:* dispute lands on a pack mid-claim → claim succeeds (attaches account_id);
  validate_and_consume later returns DISPUTED.
- *Integration:* full anonymous-buy + claim flow via FastAPI TestClient + mock Stripe webhook.

**Verification:**
- `pytest tests/test_web_auth_routes.py tests/test_web_payment.py -v` passes.
- Manual: simulate webhook lag (delay Stripe webhook delivery via Stripe CLI), click claim,
  observe retry behavior in logs.

---

### Phase 3C — Marketing opt-in + unsubscribe (EB-287)

Depends on Phase 3A merge. Two units. Parallelizable with 3B and 3D.

---

- [ ] **Unit 10: Opt-in capture + email-footer attachment**

**Goal:** Wire the marketing checkbox at signup and on the `/account` preferences toggle;
unsubscribe-token rotation on every flip.

**Requirements:** R12, R14, R15

**Dependencies:** Units 1 (accounts schema), 3 (request-link route), 15 (/account preferences UI — partial; this unit ships the backend).

**Files:**
- Modify: `web_service/routes/auth.py` (request-link payload accepts
  `marketing_opted_in: bool`; passes to `create_or_get_account`).
- Modify: `web_service/accounts_store.py` (add `set_marketing_preference(account_id, opted_in: bool)` —
  flips flag, rotates `unsubscribe_token` via `secrets.token_urlsafe(32)`, sets the
  `marketing_opted_in_at` / `marketing_opted_out_at` timestamp).
- Create: backend endpoint `PATCH /api/account/preferences` (in `web_service/routes/auth.py`
  or new `web_service/routes/account.py` — implementer choice; suggest `account.py` to
  keep `auth.py` focused).
- Modify: `web_service/email.py` (footer attachment as designed in Unit 2).
- Test: extend `tests/test_web_accounts_store.py` and `tests/test_web_auth_routes.py`.

**Approach:**
- `marketing_opted_in` is captured at first signup ONLY — subsequent magic-link logins
  do NOT modify it (per R12).
- Token rotation on every toggle ensures leaked unsubscribe tokens (from forwarded emails,
  log captures) self-invalidate.

**Test scenarios:**
- *Happy path:* signup with `marketing_opted_in=True` → row has flag=1.
- *Happy path:* second login from same email does NOT modify the flag.
- *Happy path:* `PATCH /api/account/preferences` with `marketing_opted_in=false` flips
  flag AND rotates unsubscribe_token.
- *Edge case:* `PATCH /api/account/preferences` without session cookie → 401.
- *Edge case:* set same value (already true → true) → no-op, no token rotation.
- *Integration:* email sent to opted-in user contains unsubscribe footer with current token;
  email sent to opted-out user (transactional like magic-link) contains NO marketing
  unsubscribe footer (per R13 marketing-scope decision).

**Verification:**
- `pytest tests/test_web_accounts_store.py tests/test_web_auth_routes.py -v` passes.

---

- [ ] **Unit 11: `/unsubscribe` confirmation page route**

**Goal:** Land `GET /unsubscribe?token=…` confirmation page + `POST /unsubscribe?token=…`
flip-and-confirm.

**Requirements:** R13

**Dependencies:** Unit 1 (accounts), 10 (`set_marketing_preference`).

**Files:**
- Create: `web_service/routes/unsubscribe.py`
- Modify: `web_service/main.py` (mount the router)
- Modify: `web_service/frontend/next.config.js` (rewrite `/unsubscribe` → FastAPI)
- Test: `tests/test_web_unsubscribe_routes.py`

**Approach:**
- `GET /unsubscribe?token=…` looks up account by token, renders confirmation page:
  "Unsubscribe `<email>` from marketing emails? [Confirm] [Cancel]." Uses
  `html.escape(quote=True)` on the displayed email.
- POST flips the flag via `set_marketing_preference` (which rotates the token). Renders
  "You've been unsubscribed. [Resubscribe]." Resubscribe is a separate
  `POST /unsubscribe/resubscribe?account_id=…` that requires the *new* (just-rotated) token
  OR a logged-in session.
- Token validation: GET with non-existent token renders "This link has expired or is no
  longer valid. [Manage preferences on /account]."

**Patterns to follow:**
- `web_service/routes/recover.py` for FastAPI HTML route shape.
- `docs/solutions/security-issues/xss-unescaped-session-id-fastapi-fstring-templates-2026-05-15.md`
  for f-string escape discipline.

**Test scenarios:**
- *Happy path:* GET with valid token → confirmation page rendered with correct email.
- *Happy path:* POST → flag flips → confirmation page shows resubscribe option.
- *Edge case:* GET with invalid/rotated token → "link expired" page.
- *Edge case:* POST without prior GET (direct curl) → still flips the flag (one-click
  acceptable; confirmation page is UX, not security).
- *Edge case:* resubscribe via the rotated token (just received in confirmation page) →
  flag flips back.
- *Edge case:* leaked token (post-rotation) → "link expired" page.
- *Integration:* forwarded email scenario — Alice forwards email to Bob, Bob clicks link,
  sees confirmation page with Alice's email, can't accidentally proceed without explicit click.
- *Security:* email field is HTML-escaped (XSS test with `<script>alert(1)</script>@x.com`).

**Verification:**
- `pytest tests/test_web_unsubscribe_routes.py -v` passes.
- Manual: send a test marketing email to self, click unsubscribe footer link, observe flow.

---

### Phase 3D — Conversion history + retention (EB-288)

Depends on Phase 3A merge. Three units. Parallelizable with 3B and 3C.

---

- [ ] **Unit 12: `conversions_store.py` + retention sweep**

**Goal:** Land the `conversions` table store + daily file-retention sweep + LRU prune.

**Requirements:** R16, R17, R18, R19

**Dependencies:** Unit 1 (accounts table FK target).

**Files:**
- Create: `web_service/conversions_store.py`
- Modify: `web_service/main.py` (call `conversions_store.init_db()` in lifespan;
  schedule daily `cleanup_expired_conversion_files()` alongside existing cleanup tasks).
- Modify: `web_service/config.py` (add
  `LEAFBIND_CONVERSION_RETENTION_DIR = Path(os.environ.get("LEAFBIND_CONVERSION_RETENTION_DIR", "/var/leafbind/conversions"))`).
- Test: `tests/test_web_conversions_store.py`

**Approach:**
- Schema per R16 (origin doc): `(id, account_id NOT NULL, job_id, original_filename,
  output_format, tier, created_at, file_path, file_size_bytes, retention_until)`.
- Schema column nullability: `file_path TEXT` and `file_size_bytes INTEGER` are BOTH
  nullable. After the daily sweep runs, expired rows have `file_path=NULL`. The
  disk-full-at-copy-time fallback path (Unit 13) also inserts NULL for both columns.
  All sweep/LRU queries must filter `WHERE file_path IS NOT NULL` to avoid no-op work
  on already-pruned rows.
- Public API:
  - `record_conversion(account_id, job_id, original_filename, output_format, tier, file_path, file_size_bytes)`
  - `list_recent_for_account(account_id, limit=50) → list[Conversion]`
  - `get_conversion(conversion_id, account_id) → Conversion | None` (account-gated lookup
    for the download route)
  - `cleanup_expired_conversion_files() → SweepResult` (deletes files for rows where
    `retention_until < now AND file_path IS NOT NULL`, sets `file_path=NULL`)
  - `cleanup_old_metadata() → int` (deletes rows older than 365 days)
  - `prune_to_budget(target_bytes=90 * 1024**3) → SweepResult` (when total dir usage
    exceeds 100 GB, prune oldest until under 90 GB)
- Sweep ordering for atomicity: per row, BEGIN IMMEDIATE → UPDATE file_path=NULL → COMMIT →
  os.unlink (file delete is OUTSIDE the transaction). If unlink fails, log warning;
  next sweep will be a no-op on this row (file_path already NULL). Orphan file is harmless.
- Disk usage check uses `shutil.disk_usage()` for free-space and `os.walk` for
  directory-size accounting.

**Patterns to follow:**
- `web_service/token_store.py` for store shape.
- `web_service/job_store.py:cleanup_expired_jobs` for sweep cadence and shape.

**Test scenarios:**
- *Happy path:* `record_conversion` then `list_recent_for_account` returns the row.
- *Happy path:* `get_conversion(id, account_id=42)` returns row when account matches.
- *Edge case:* `get_conversion(id, account_id=99)` returns None when account differs (gating).
- *Sweep:* row with `retention_until < now AND file_path = "/tmp/x"` → after sweep, row
  exists with `file_path=NULL`, `/tmp/x` deleted.
- *Sweep:* `os.unlink` raises (file already deleted) → DB still updated, no exception
  bubbles up to caller.
- *Cleanup:* row older than 365 days deleted entirely.
- *LRU:* directory exceeds 100 GB → `prune_to_budget` deletes oldest files until under 90 GB.
- *Edge case:* sweep run with empty `conversions` table → no-op, no error.
- *Race:* in-flight `list_recent_for_account` during sweep → reads committed (WAL snapshot
  isolation) — no torn reads.

**Verification:**
- `pytest tests/test_web_conversions_store.py -v` passes.

---

- [ ] **Unit 13: Pipeline-runner hook to copy output + record conversion**

**Goal:** When a job completes for a logged-in account, copy the output file to
the retention dir and record the row.

**Requirements:** R16, R17

**Dependencies:** Unit 12 (conversions_store), Unit 4 (session helper), Unit 8
(account_id threading through to job submission).

**Files:**
- Modify: `web_service/pipeline_runner.py` (post-job hook — if `job.account_id` is set,
  copy output file to retention dir and call `record_conversion`).
- Modify: `web_service/job_store.py` (add nullable `account_id` to `jobs` via
  `_LATER_COLUMNS`, captured at upload time from `get_account_from_request`).
- Modify: `web_service/routes/convert.py` (capture `account_id` from session into the
  job row at upload time).
- Test: extend `tests/test_web_job_store.py` and `tests/test_web_pipeline_runner.py`.

**Approach:**
- `jobs.account_id INTEGER` (nullable; anonymous jobs stay NULL).
- At convert.py upload time: `account = get_account_from_request(request); job.account_id = account.id if account else None`.
- After job completes (existing pipeline_runner success path), if `job.account_id` is non-None:
  - Compute target path with an opaque random component:
    `LEAFBIND_CONVERSION_RETENTION_DIR / str(account_id) / secrets.token_urlsafe(16) / f"{job_id}.{ext}"`.
    The random middle segment defeats path-enumeration attacks if the retention dir is
    ever accidentally exposed via a misconfigured static-file route or Nginx alias —
    knowing `account_id` and `job_id` alone is insufficient to construct the URL.
  - `shutil.copy2(job.output_path, target_path)`. On `OSError` (disk full, permission):
    log WARNING, set `file_path=None` in the conversions row, continue.
  - `record_conversion(account_id, job_id, original_filename=job.original_filename, output_format=job.output_format, tier=job.tier, file_path=target_path_or_none, file_size_bytes=stat.st_size)`.

**Patterns to follow:**
- Existing `web_service/pipeline_runner.py` job-completion path.
- `web_service/job_store.py:53-72` for the `account_id` ALTER on `jobs`.

**Test scenarios:**
- *Happy path:* logged-in user converts → conversion row inserted, file present at
  retention path.
- *Happy path:* anonymous user converts → NO conversion row inserted.
- *Edge case:* `shutil.copy2` raises `OSError` (mocked) → row inserted with `file_path=NULL`,
  conversion succeeds, no exception bubbles up.
- *Edge case:* `original_filename` is `None` → recorded as `"unknown"`.
- *Edge case:* `retention_until` is set to `created_at + 30 * 86400`.
- *Integration:* end-to-end convert → status poll → conversion appears in
  `list_recent_for_account` within 5 s.

**Verification:**
- `pytest tests/test_web_job_store.py tests/test_web_pipeline_runner.py -v` passes.
- Manual: log in, convert a PDF, observe file appears at
  `/var/leafbind/conversions/<account_id>/<job_id>.kfx`.

---

- [ ] **Unit 14: Re-download route `/account/conversions/<id>/download`**

**Goal:** Land the session-gated re-download endpoint.

**Requirements:** R20

**Dependencies:** Units 4 (session helper), 12 (conversions_store).

**Files:**
- Create: `web_service/routes/account.py` (re-uses Unit 10's planned location; if Unit 10
  shipped to `auth.py` instead, create this file fresh).
- Modify: `web_service/main.py` (mount the router).
- Modify: `web_service/frontend/next.config.js` (rewrite `/account/conversions/*` → FastAPI).
- Test: `tests/test_web_account_routes.py`

**Approach:**
- `GET /account/conversions/<id>/download`:
  - `account = get_account_from_request(request)`. If None → 401 redirect to `/login?next=/account`.
  - `conv = conversions_store.get_conversion(id, account_id=account.id)`. If None → 404 (or 403 if exists for other account; safer to return 404 to avoid leaking).
  - If `conv.file_path is None` or file doesn't exist on disk → 410 "this file was deleted as part of the 30-day retention window".
  - Return `FileResponse(conv.file_path, media_type=..., filename=conv.original_filename)`.
- `GET /api/account/conversions?limit=50` for Unit 15's history list — returns JSON.
- `GET /api/account/balance` for Unit 16's header dropdown — returns
  `{"credits_balance": count_available_credits(account.id)}`.

**Test scenarios:**
- *Happy path:* logged-in owner downloads → file served with correct filename.
- *Edge case:* anonymous request → 401.
- *Edge case:* logged-in but not owner → 404 (not 403 — avoid leakage).
- *Edge case:* file swept (`file_path IS NULL`) → 410.
- *Edge case:* row exists with file_path set but file missing on disk → 410 (race with sweep mid-download).
- *Integration:* concurrent download + sweep — Linux open-FD semantics keep download alive.

**Verification:**
- `pytest tests/test_web_account_routes.py -v` passes.

---

### Phase 3E — Account UI + header (EB-289)

Depends on Phase 3A, 3B, 3C, 3D merges. Two units. Sequential.

---

- [ ] **Unit 15: `/account` Server Component**

**Goal:** Ship the `/account` UI integrating balance, history, preferences.

**Requirements:** R21

**Dependencies:** Units 3, 7 (balance API), 10 (preferences API), 14 (history API).

**Files:**
- Create: `web_service/frontend/app/(app)/account/page.tsx` (Server Component)
- Create: helper component files as the implementer decides (Balance card, History list,
  Preferences toggle, Delete-account stub).
- Modify: `web_service/frontend/lib/api.ts` (`getAccount`, `getBalance`,
  `getConversionHistory`, `patchPreferences`).

**Approach:**
- Server Component reads `cookies()` via `next/headers`. **Unauthenticated visitor path:**
  if no `leafbind_session` cookie is present OR `/api/auth/me` returns 401, server-side
  `redirect("/login?next=/account")` — matches the canonical pattern from Unit 14's
  download route. No flash of signed-in state for the brief loading window.
- For authenticated requests: calls FastAPI's `/api/auth/me` +
  `/api/account/balance` + `/api/account/conversions` in parallel on the server.
- Renders four cards: identity (email + sign-out), balance, history, preferences.
- History list renders Date / Filename / Format / Tier / Action columns. Action is a
  `<a href="/account/conversions/<id>/download">Download</a>` when file_path is non-NULL,
  or a disabled "Expired" label otherwise.
- Preferences toggle is a small Client Component that PATCHes `/api/account/preferences`.
- Delete-account is a `<a href="/contact?topic=account-deletion">` link.
- `noindex, nofollow` meta tag in the page layout.

**Patterns to follow:**
- `web_service/frontend/app/(app)/recover/page.tsx` (Server Component pattern).
- `web_service/frontend/app/(app)/contact/page.tsx` (similar info-architecture layout).

**Test scenarios:**
- Test expectation: none — no JS test infrastructure in scope. Manual visual + functional verification.

**Verification:**
- Navigate to `/account`, observe balance + history + preferences. Toggle preference,
  observe persistence. Click Download on a recent conversion, observe file download.

---

- [ ] **Unit 16: Header signed-in indicator**

**Goal:** Header shows "Sign in" or "<email> ▾" dropdown based on session.

**Requirements:** R22

**Dependencies:** Units 3 (auth routes), 7 (balance API).

**Files:**
- Modify: `web_service/frontend/components/Header.tsx` (convert to Server Component or
  add an SSR-readable `AccountMenu` slot).
- Create: `web_service/frontend/components/AccountMenu.tsx` ("use client" for dropdown
  interactivity).

**Approach:**
- Header reads `cookies()` server-side and renders one of two slots: a "Sign in" link or
  `<AccountMenu email={email} balance={balance} />`.
- AccountMenu is a Client Component with a click-to-toggle dropdown containing:
  Account (link to /account), Sign out (POST to /api/auth/logout).
- Sign-out POST triggers a full page reload via `router.refresh()` after success.
- Free-tier conversion at `/` still works without sign-in — Header is informational only.

**Patterns to follow:**
- Existing `Header.tsx` styling.
- Next.js App Router `cookies()` from `next/headers` for Server Component cookie reads.

**Test scenarios:**
- Test expectation: none — no JS test infrastructure in scope. Manual visual verification.

**Verification:**
- Visit `/` anonymous → header shows "Sign in".
- Log in → refresh `/` → header shows email dropdown with correct balance.
- Sign out → header returns to "Sign in".

---

## System-Wide Impact

- **Interaction graph:** Phase 3 touches the FastAPI middleware allowlist (must NOT extend),
  the Stripe webhook handler (must thread `account_id`), the success-page render
  (must add upsell), the conversion form (must capture `account_id`), the
  `pipeline_runner` job-completion hook (must copy outputs for logged-in users), the
  Next.js Header (must become session-aware), and `next.config.js` rewrites (must proxy
  new auth/account endpoints).
- **Error propagation:** Email-send failures in `web_service/email.py` log WARN but do
  NOT propagate to the user — `/api/auth/request-link` returns 204 either way (no
  enumeration oracle). Sweep failures log WARN and continue with the next row.
  Disk-full at job-completion copy degrades gracefully to `file_path=NULL` (no
  conversion failure).
- **State lifecycle risks:**
  - The `tokens.account_id` ALTER under WAL is the biggest single risk — mitigated via
    paused-webhook deploy window (see Operational Notes).
  - Sweep ordering (DB update first, unlink second) prevents zombie download buttons; the
    failure mode is orphan files which are harmless and re-swept.
  - Magic-link nonce single-use is enforced at POST time (not GET) — defeats email-client
    URL prefetching.
  - Session revocation: `session_version` increment on logout invalidates all existing
    cookies for that account.
- **API surface parity:** `mint_tokens_if_absent` signature change (new keyword arg) is
  backward compatible — existing call sites without `account_id` continue to work and
  produce anonymous tokens. Both webhook AND success-page mint paths must be updated in
  the same change to avoid race-dependent attribution drift.
- **Integration coverage:** Stripe CLI (`stripe trigger checkout.session.completed`) with
  custom metadata is the canonical integration test for the webhook path. Manual
  end-to-end on staging covers the success-page idempotent revisit path.
- **Unchanged invariants:**
  - Phase 2 anonymous bearer-token validation rules continue to apply to tokens with
    `account_id IS NULL`.
  - Phase 2 dispute logic (`mark_disputed(pack_id)`) is unchanged — chargebacks still
    revoke at the pack level regardless of account attachment.
  - Free-tier `/convert` flow does NOT require a session (`get_account_from_request`
    returning None is a normal anonymous case, not a 401).
  - `_MIDDLEWARE_ALLOWLIST` at `web_service/main.py:44` stays at `{"CORSMiddleware"}` —
    Phase 3 deliberately avoids adding SessionMiddleware.
  - Webhook raw-body reading at `web_service/routes/webhook.py` is unchanged; no
    middleware introduced consumes the body upstream.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `ALTER TABLE tokens ADD COLUMN account_id` collides with active webhook holding `BEGIN IMMEDIATE` longer than the default 5 s busy_timeout, crashing migration | Pause Stripe webhook delivery via Stripe Dashboard ~30 s before deploy; raise `PRAGMA busy_timeout=30000` for the migration specifically; resume webhook delivery post-migration. Stripe's ~3-day retry budget absorbs the pause. |
| Email-client URL prefetching (Outlook SafeLinks, iCloud Private Relay) consumes single-use magic-link nonces before user clicks | GET-then-confirm interstitial: nonce only consumed on POST after explicit user click. |
| User races Stripe webhook to claim — claim UPDATE finds 0 rows because tokens don't exist yet | Bounded retry loop (3 × 2 s) with auto-refresh fallback page; webhook completes within its normal lag window. |
| Stale `session_version` allows revoked cookies to continue working until natural expiry | `session_version` carried in signed cookie payload; `get_account_from_request` rejects cookies with version < current account version. Logout bumps the version. |
| Forwarded marketing email lets third party unsubscribe the original account | Confirmation interstitial requires explicit click on `/unsubscribe` page; `unsubscribe_token` rotates on every opt-in/opt-out toggle so leaked tokens self-invalidate. |
| Sweep crash leaves file unlinked but DB row still pointing to file (broken Download button) | DB UPDATE `file_path=NULL` runs BEFORE `os.unlink`; orphan-file failure mode is harmless and re-swept. |
| Disk full at job-completion copy time blocks conversion | `OSError` caught → conversion row inserted with `file_path=NULL` → conversion still succeeds via the standard `/status/<id>/download` path. |
| Anonymous-then-logged-in idempotency collision on the same pack | `_derive_idempotency_key()` extended to include `account.id`; anonymous and logged-in clicks within the 30 s bucket produce distinct Stripe sessions. |
| GDPR Article 7 violation from checked-default opt-in for EU visitors | Explicitly accepted risk; geo-gated mitigation filed as separate ticket. Operator acknowledges immediate-priority fix if EU complaints arrive. |
| User signs out in Tab A; Tab B's `/account` shows stale content | Acceptable staleness; Tab B's next request to a protected endpoint (e.g., `/api/account/balance` for header refresh) will see the bumped `session_version` and return 401 → Header re-renders as anonymous. |
| Magic-link rate limit (3 / 15 min / email) is too tight for legitimately failing email delivery | Numeric tuning deferred to post-launch; in-process counter is easy to adjust without redeploy if necessary. |

## Operational / Rollout Notes

**Migration deploy sequence (Phase 3A):**

1. Confirm staging environment matches production schema before starting.
2. In Stripe Dashboard, navigate to Developers → Webhooks → leafbind production endpoint
   and click "Disable endpoint". This pauses webhook delivery; Stripe queues events for
   redelivery within the ~3-day retry budget.
3. Wait 30 seconds to let any in-flight webhook transactions complete.
4. Deploy Phase 3A code to production (includes the migration runner with the
   `tokens._LATER_COLUMNS` entry).
5. Observe service restart logs: `token_store: ADD COLUMN account_id applied` should
   appear within 5 seconds. If `OperationalError: database is locked` appears, the
   busy_timeout=30000 override was insufficient — escalate (likely a long-running webhook
   transaction that didn't drain in step 3).
6. Verify schema via:
   `sqlite3 data/web_service.db "PRAGMA table_info(tokens)" | grep account_id`
7. In Stripe Dashboard, re-enable the webhook endpoint. Verify the next several events
   process successfully via the FastAPI logs.
8. Net expected downtime: ~60 seconds. Free-tier conversions at `/` continue to work
   throughout (no migration impact).

**Phase 3B/3C/3D parallel spawn (subagent coordination):**

Once EB-285 merges to master:

1. Create three worktree branches via the project's standard worktree skill:
   `feat/EB-286-credit-binding`, `feat/EB-287-marketing-optin`, `feat/EB-288-conversion-history`.
2. Use `docs/templates/subagent-delegation-contract.md` verbatim. Per-stream
   `files_in_scope` allowlists:
   - **EB-286:** `web_service/token_store.py`, `web_service/routes/{webhook,checkout,payment,auth}.py`, `web_service/frontend/components/{ClaimAccountUpsell,PendingClaimRefresh}.tsx`, `tests/test_web_{token_store,webhook,checkout,payment,auth_routes}.py`
   - **EB-287:** `web_service/routes/{auth,unsubscribe}.py` (auth only for the
     marketing-checkbox addition), `web_service/accounts_store.py` (preference setter),
     `web_service/email.py` (footer attachment if not landed in Unit 2),
     `tests/test_web_{accounts_store,unsubscribe_routes}.py`
   - **EB-288:** `web_service/conversions_store.py`, `web_service/pipeline_runner.py`,
     `web_service/job_store.py` (account_id column), `web_service/routes/{convert,account}.py`
     (for the upload-time `account_id` capture and the download route),
     `web_service/main.py` (lifespan registration), `tests/test_web_{conversions_store,job_store,pipeline_runner,account_routes}.py`
3. Frozen shared interfaces (declare in each contract under "Frozen shared interfaces"):
   - `web_service.accounts_store.Account` dataclass fields
   - `web_service.accounts_store.create_or_get_account(email) → Account` signature
   - `web_service.accounts_store.set_marketing_preference(account_id, opted_in)` signature
   - `web_service.session.get_account_from_request(request) → Account | None` signature
   - `web_service.token_store.mint_tokens_if_absent(..., account_id=None)` signature
   - `web_service.token_store.count_available_credits(account_id) → int` signature
   - `next.config.js` rewrites list shape (each stream adds its own entries; coordinator
     resolves merge conflict)
4. Note the overlap on `web_service/routes/auth.py`:
   - EB-286 adds the `pending_pack_id` parameter to POST verify.
   - EB-287 adds the `marketing_opted_in` field to the request-link payload.
   - These are non-conflicting line additions but both touch the file. Coordinator should
     sequence: EB-286 merges first (heavier change), then EB-287 rebases its single-field
     addition.
5. Each stream lands its own PR; coordinator gates merges on AC verification per ticket.

**Secrets management:**

Phase 3 introduces three new secrets that must be operationally distinct and stored
outside the repo:

- `MAGIC_LINK_SECRET` — `itsdangerous` signing key for magic-link URL tokens.
  Rotation invalidates all in-flight magic links (15-min blast radius — minor).
- `SESSION_COOKIE_SECRET` — `itsdangerous` signing key for session cookies.
  **MUST be a distinct value from `MAGIC_LINK_SECRET`.** Using the same secret would
  allow a compromised magic-link token to be re-signed as a session cookie. Rotation
  invalidates all active sessions for all users (mass logout — acceptable response to
  suspected compromise; document the operator runbook).
- `RESEND_API_KEY` — Resend SMTP API key. Rotation requires generating a new key in
  the Resend dashboard and updating the env var; no user impact beyond the brief restart
  window.

Storage: all three in the systemd `EnvironmentFile` at `/etc/web_service.env`,
mode `0640`, owner `root:web_service`. Never commit to git; never echo to logs; never
include in `Get-Content` / `cat` output during debugging (per the global CLAUDE.md
log-sanitization rule). Staging and production must use distinct values.

**Cleanup:**
- After all five Phase 3 tickets merge, delete the worktree branches and update the
  feature manifest via `tools/verify-manifest.ps1`.
- File the follow-up: Phase 2 compound retro into `docs/solutions/` covering chargeback
  + webhook idempotency + `mint_tokens_if_absent` race patterns. None of these are
  documented as solutions today, despite being load-bearing for Phase 3.

## Documentation Plan

- `docs/decisions/ADR-EB-284-privacy-positioning-reversal.md` — written as Phase 3A Unit 6.
- After all Phase 3 tickets merge: Phase 2 compound retro at
  `docs/solutions/best-practices/leafbind-phase2-stripe-webhook-idempotency-patterns-2026-MM-DD.md`.
  Captures the `mint_tokens_if_absent` race-loser invariant, `payment_intent_data.metadata`
  propagation for dispute lookup, and the success-page-vs-webhook idempotency model.
- After all Phase 3 tickets merge: file ticket for GDPR-compliant geo-gated opt-in default
  using `CF-IPCountry` header detection.
- Update `CLAUDE.md`'s "Current Priorities" section if the priority list moves.

## Sources & References

- **Origin document:** `docs/brainstorms/2026-05-16-eb45-phase3-accounts-persistent-tokens-requirements.md`
- **Phase 2 reference:** `docs/brainstorms/2026-05-13-eb45-phase2-billing-requirements.md`
- **Related code:**
  - `web_service/token_store.py` (migration target, mint signature update)
  - `web_service/job_store.py:53-72` (canonical `_LATER_COLUMNS` migration pattern)
  - `web_service/routes/webhook.py`, `web_service/routes/checkout.py`,
    `web_service/routes/payment.py` (Stripe `account_id` threading sites)
  - `web_service/main.py:44, 103-121, 152-158` (middleware allowlist, lifespan startup)
  - `web_service/frontend/next.config.js:19-24` (proxy rewrite pattern)
  - `cloudflare/contact-worker/src/send.ts:22-50` (Resend REST pattern to port)
- **Solutions (apply verbatim):**
  - `docs/solutions/best-practices/leafbind-email-auth-stack-2026-05-16.md`
  - `docs/solutions/best-practices/cloudflare-workers-first-deployment-leafbind-2026-05-16.md`
  - `docs/solutions/security-issues/xss-unescaped-session-id-fastapi-fstring-templates-2026-05-15.md`
  - `docs/solutions/best-practices/fastapi-nextjs-css-token-sharing-python-shell-2026-05-15.md`
- **Subagent contract:** `docs/templates/subagent-delegation-contract.md`
- **Jira tickets:** EB-284 (epic), EB-285 (3A), EB-286 (3B), EB-287 (3C), EB-288 (3D), EB-289 (3E)
