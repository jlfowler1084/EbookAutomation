---
title: "feat(EB-45 Phase 3B): Stripe-customer-binding credit recovery + standalone double-opt-in mailing list"
type: feat
status: active
date: 2026-05-24
deepened: 2026-05-24
origin: docs/brainstorms/2026-05-16-eb45-phase3b-stripe-customer-binding-and-light-mailing-list-requirements.md
ship_strategy: split
ship_now: [3B.2, 3B.3]
ship_gated_until: 2026-06-15   # 3B.1 recovery + F1, pending EB-292 real measurement gate
---

# feat(EB-45 Phase 3B): Stripe-Customer-Binding Credit Recovery + Standalone Mailing List

## Overview

Phase 3B delivers the two Phase 2 pain points — token loss and no mailing-list channel — at ~20% of
the retired magic-link plan's cost, while **preserving** the Phase 2 "no first-party PII for credits"
positioning. It splits into two architecturally independent surfaces:

1. **Credit recovery via Stripe customer binding.** A `/recover/email` flow looks up a buyer by the
   email Stripe already holds, then emails a signed, time-limited link revealing their tokens. No
   first-party accounts table, no auth, no session cookies for the credit side.
2. **Standalone double-opt-in mailing list.** A footer signup form + `subscribers` table, completely
   independent of credits.

This plan supersedes the retired magic-link Phase 3 (EB-284 epic + EB-285–289, all closed). It carries
forward one **hard technical prerequisite (F1)** discovered in document review and re-confirmed against
source during planning: Phase 2's `customer_creation="if_required"` does not create Stripe Customers for
guest checkouts, so the recovery flow has no customers to bind to until Phase 2 is patched and existing
purchases are backfilled. F1 is the first executable unit.

## Ship Strategy (post-document-review decision, 2026-05-24)

Document review (7 personas) returned a P0 from three independent reviewers: the override of the
EB-292 hold rests on a **survivorship-biased single signal** (83% empty-`localStorage` is measured
*among people who already reached `/recover` because they lost their tokens* — not among all buyers),
EB-292's gate required three signals, and the recovery half carries all the irreversible,
high-blast-radius work (live billing patch + historical Stripe backfill) on the thinnest evidence.

**Operator decision (2026-05-24): SPLIT the ship.**

- **Ship now — mailing list (3B.2 + 3B.3):** F1-independent, touches no billing code, serves an
  unambiguous gap (no marketing channel) that needs no measurement gate. This is the actionable tranche.
- **Re-gated to ~2026-06-15 — recovery (3B.1 + F1, Units 1, 2, 7, 8):** held until the *real* EB-292
  measurement decision with an unbiased denominator. The earlier override (EB-292 comment 2026-05-24) is
  hereby **narrowed to the mailing-list half only**; recovery returns to "wait for the gate." The
  recovery units below are fully specified and review-corrected so they are ready to unpause, but they do
  **not** ship in this tranche.

**Turnstile dropped from launch** (flagged by 4 reviewers — not in the brainstorm, no Python-side
siteverify exists today, adds friction the data doesn't justify). The subscribe form relies on the
per-IP rate limit + double opt-in; Turnstile is a follow-up if abuse appears.

See the "Document-Review Corrections (2026-05-24)" section near the end for the full list of findings and
how each was resolved.

## Problem Frame

Phase 2 shipped accountless bearer tokens (`lb_pk_*`, 30-day TTL) recoverable only via a revisitable
success URL + `localStorage` + the Stripe receipt. The triple-failure case (lost all three) strands the
user. EB-292 instrumentation (shipped, Done) is measuring the real rate; after the 2026-05-24
document review, the operator narrowed the earlier override to the mailing-list half only and re-gated
the recovery half to the ~2026-06-15 measurement decision.

The product-lens reviewer twice flagged "building stateful infrastructure for an unmeasured problem."
Phase 3B answers that critique by (a) gating on the EB-292 measurement decision, (b) adding **zero**
first-party credit state — recovery reads Stripe, not a new accounts DB — and (c) committing the
mailing list to a concrete send cadence (R15) so it isn't a list that rots.

Full origin and decision rationale: see origin
`docs/brainstorms/2026-05-16-eb45-phase3b-stripe-customer-binding-and-light-mailing-list-requirements.md`.

## Requirements Trace

All R-IDs reference the origin document.

**Recovery (3B.1):**
- R1 — existing `POST /api/recover` session_id-paste path unchanged (precise-recovery fallback) — Unit verification only
- R2 — new email-recovery surface on `/recover` page + `POST /api/recover/email` — Units 7, 8
- R3 — `POST /api/recover/email`: validate, look up Stripe customer via **`Customer.list(email=...)`** (exact match, strongly consistent — NOT `Customer.search`), signed 1h link, no-enumeration 204, rate-limited — Units 7, 4 (email infra: Unit 3)
- R4 — recovery email from `support@leafbind.io`, plain-text, **no unsubscribe footer** (transactional) — Unit 7 (sends via the Unit 3 email helper)
- R5 — `GET /recover/show?token=` revisitable-within-TTL landing page, token/expiry validation, token-state rendering — Unit 8
- R6 — `/recover/show` is FastAPI-rendered via `_render_*` + `_BrandStaticFiles` — Unit 8
- R7 — `html.escape(quote=True)` on all reflected user/Stripe values — Units 7, 8
- **F1 (feasibility prerequisite, not in origin R-list)** — patch `customer_creation="always"` + backfill existing purchases — Units 1, 2

**Mailing list (3B.2):**
- R8 — footer `<SubscribeForm/>`, submit-is-opt-in (no checkbox) — Unit 11
- R9 — `POST /api/subscribe`: validate, insert-or-ignore, double-opt-in email, 204 no-enumeration, per-IP rate limit (Turnstile dropped from launch — see Ship Strategy) — Unit 9
- R10 — `subscribers` table schema — Unit 9 (store: Unit added under 3B.2 as part of 9)
- R11 — `GET /subscribe/confirm?token=`, 72h TTL, single-use confirm token, idempotent — Unit 10

**Unsubscribe (3B.3):**
- R12 — `GET /unsubscribe?token=` interstitial + `POST` flips state + rotates token — Unit 12
- R13 — marketing-email unsubscribe footer + List-Unsubscribe headers; recovery emails excluded — Unit 13
- R14 — send-infra scope: capture + unsubscribe only; manual SQLite export — Scope Boundaries
- R15 — operator content commitment (monthly from 2026-08-01) — operational note, not code

## Scope Boundaries

**In scope:** everything in the origin "In scope" list — email-recovery via Stripe customer binding,
1-hour revisitable signed link, per-email + per-IP SQLite-persisted rate limiting, no-enumeration
responses, disputed-token display, footer mailing-list signup, double opt-in, unsubscribe interstitial +
token rotation. Plus the F1 forward-fix and backfill (prerequisite for any recovery value).

**Out of scope** (carried from origin): first-party accounts, magic-link auth, session cookies, account
dashboard, conversion history, persistent credit balance (all retired with the prior plan); marketing
campaign tooling (segmentation, scheduling, A/B, open/click tracking, list-export UI); conversion
history/re-download; GDPR geo-gated opt-in (the submit-is-opt-in design is GDPR-safer and needs no
geo-gate); removing `POST /api/recover`; programmatic subscriber data export.

### Deferred to Separate Tasks

- **Phase 2 compound retro** (chargeback/webhook idempotency patterns) — file a `docs/solutions/` entry
  after 3B merges. No reusable Stripe-idempotency learning exists yet (research confirmed the only
  Stripe solution doc is the XSS payment-page fix).
- **`docs/solutions/` entry for the `customer_creation`/Customer-binding behavior** — compound after
  F1 lands, since it's a non-obvious Stripe gotcha future credit work will hit.
- **Self-service subscriber data export** (GDPR Art. 20) — separate privacy-rights ticket if it
  materializes; contact form covers it for now.
- **Pricing-page / homepage signup placements** — defer until baseline footer conversion is measured.

## Context & Research

### Relevant Code and Patterns

Confirmed current state (repo-relative paths; line refs are directional, prefer pattern references):

- `web_service/routes/recover.py` — existing `POST /api/recover` is a thin paste-form→`302 /payment/success`
  redirect (no DB/Stripe). Already EB-292-instrumented via fire-and-forget `recovery_events_store.log_event`.
  New `/api/recover/email` + `/recover/show` are net-new and do not collide.
- `web_service/token_store.py` — `_get_conn()` WAL/`busy_timeout=5000`/`foreign_keys=ON`; `_SCHEMA_SQL`
  fixed-schema (tokens/failed_mints/refund_ledger); **`payment_intent_id` IS stored + indexed per token
  row**; no `customer_id`/email column. `mint_tokens_if_absent(session_id, count, payment_intent_id)`
  with `BEGIN IMMEDIATE` idempotency on `pack_id`. `get_tokens_for_session()`,
  `find_session_by_payment_intent()`. Frozen-dataclass results + `TokenValidationErrorCode(str, Enum)`.
  **token_store has NO migration runner** — `_apply_migrations` must be ported from `job_store.py`.
- `web_service/job_store.py` — canonical forward-only migration: `_LATER_COLUMNS: list[tuple[str,str]]`
  + `_LATER_INDEXES` + `_apply_migrations(conn)` (BEGIN IMMEDIATE, `PRAGMA table_info` gate, ALTER absent
  columns, then indexes). Race-safe across `--workers 2`. Migration-race test precedent:
  `tests/test_web_job_store_migration_race.py`.
- `web_service/recovery_events_store.py` (EB-292) — **cleanest template for a brand-new SQLite store in
  the same `data/web_service.db`**: `_SCHEMA_SQL` + `_get_conn` + `init_db()` + fire-and-forget writer +
  `_VALID_*` whitelist. Mirror this for `subscribers_store.py`.
- `web_service/routes/checkout.py` — **F1 at the `customer_creation="if_required"` line** inside
  `stripe.checkout.Session.create`; `receipt_email=None`; pack metadata seeded. One-line patch site.
- `web_service/routes/payment.py` — `GET /payment/success` render; `_render_*` HTML helpers + `_base_html`
  shell (consumes `header_html()`/`footer_html()` from `web_service/templates/shell.py`); security headers
  `Referrer-Policy: no-referrer`, `Cache-Control: private, no-store`. **The idiom `/recover/show` reuses.**
- `web_service/routes/webhook.py` — mint call site in the combined `checkout.session.completed` +
  `checkout.session.async_payment_succeeded` branch; raw-body signature validation (never `request.json()`).
  `web_service/main.py` `_MIDDLEWARE_ALLOWLIST = {"CORSMiddleware","SlowAPIMiddleware"}` guard — do not
  add body-reading middleware.
- `web_service/email_client.py` (EB-324) — **existing Resend SDK wrapper**: lazy `import resend`, api_key
  wiring, `SendResult` frozen dataclass, `_extract_message_id`, recipient-privacy hardening (never logs
  `to`). Currently attachment-oriented + gated behind `WEB_SEND_TO_KINDLE_ENABLED`. Extend with a
  plain/html no-attachment sender; decouple the new sender from the Kindle gate.
- `cloudflare/contact-worker/src/send.ts` (EB-264) — TS Resend REST + double-send/throttle precedent
  (not directly reusable from Python, but the plain-text email shape and 24h throttle idea port).
- Frontend: `web_service/frontend/components/Footer.tsx` exists (Tailwind 6-col grid; SubscribeForm slots
  as a new row/column). `web_service/frontend/app/(app)/recover/page.tsx` + `components/RecoverClient.tsx`
  (renders the `POST /api/recover` form; EB-292 logs page view). `lib/api.ts` `fetch`+`ApiError` pattern.
  `next.config.js` `rewrites()` proxies `/api/recover`, `/api/recovery-events/recover-view`,
  `/payment/success` → FastAPI. **New FastAPI endpoints must be added to the rewrites array.**
- `requirements.txt` — `stripe>=12` PRESENT (Customer.search/list available), `resend>=2.30` PRESENT,
  `email-validator>=2.3` PRESENT, `cryptography` PRESENT, `slowapi` PRESENT, `svix` PRESENT.
  **`itsdangerous` ABSENT** — do not add it; use `cryptography` (Fernet) or `web_service/crypto.py` HMAC.
- Tests: flat `tests/test_web_*.py`, TestClient + class-grouped, `reset_settings()` autouse fixture,
  `TestClient(main_mod.app, follow_redirects=False)`. Billing e2e precedent
  `tests/test_web_payment_e2e.py` runs in CI (`.github/workflows/web-tests.yml`).

### Institutional Learnings

- `docs/solutions/best-practices/leafbind-email-auth-stack-2026-05-16.md` — outbound mail via Resend on
  `send.leafbind.io`, DKIM-aligned to `leafbind.io`; **DMARC is `p=none` until ~2026-06-15** — verify a
  new sender against mail-tester before launch. Keep both DKIM selectors.
- `docs/solutions/best-practices/cloudflare-workers-first-deployment-leafbind-2026-05-16.md` — rate-limit
  shape: prefix-bucketed keys (`rl:ip:<ip>:<bucket>`, `rl:email:<sha256-lowercased-email>:<bucket>`,
  `bucket = floor(unix/window)`); **always hash the email, never store plaintext; fail closed on
  store-write failure.** Port the bucketing math to SQLite.
- `docs/solutions/security-issues/xss-unescaped-session-id-fastapi-fstring-templates-2026-05-15.md` —
  `html.escape(value, quote=True)` is mandatory for every reflected value; add CI grep guard + template
  XSS regression tests with real `<script>` payloads. Applies to reflected `email` + token params.
- `docs/solutions/best-practices/fastapi-nextjs-css-token-sharing-python-shell-2026-05-15.md` —
  FastAPI owns stateful/private pages (`private, no-store` via `_BrandStaticFiles`); one `_render_<state>`
  helper per state; shared shell hand-mirrored in `shell.py` (drift-checked). Build recovery + confirm
  pages this way.
- `docs/solutions/best-practices/vercel-production-branch-misconfiguration-2026-05-15.md` — Vercel
  productionBranch must be `master`; trust `vercel ls`, not the green PR check, for ship confirmation.
- `web_service/docs/stripe-verification.md` — the three-layer billing verification convention
  (mocked unit → signed-event e2e → manual CLI script). Any billing-touching change (F1 patch, mint
  customer_id threading) must extend all three layers.

### External References

- Stripe: `customer_creation` default for `payment` mode is `if_required` (since 2022-08-01); only
  features needing a persisted Customer (e.g. `setup_future_usage`) force creation — **ordinary guest
  card checkout gets none**. `="always"` reliably creates one per completed session. Even under
  `if_required`, Checkout **collects an email** into `session.customer_details.email`. (Stripe changelog;
  Checkout Session API ref; Guest Customer FAQ.)
- Stripe Customer **Search** is eventually consistent (<1 min typical, up to 1h in incidents) and does
  substring matching — **unsafe right after purchase and imprecise.** Use **`Customer.list(email=...)`**
  (exact match, strongly consistent) for the recovery lookup. (Customer Search / List API refs.)
- **F1 backfill verdict: feasible.** Checkout always stores the buyer email in
  `session.customer_details.email` and `charge.billing_details.email`, independent of `receipt_email=None`.
  Backfill: list historical Checkout Sessions, read the email, `Customer.create` + match to our stored
  `tokens.payment_intent_id`. (Charge object ref; email-receipts resolution hierarchy.)
- Resend: official `resend` Python SDK is current (already a dep); `POST /emails` Bearer auth; `text`
  alone valid for plain-text; `200 {id}` / error `{error:{code,message}}`; 5 req/s/team default. 40 MB
  message cap. (Resend API ref; Send-with-Python.)
- Email compliance: a recovery email is **transactional** (CAN-SPAM primary-purpose test; GDPR/PECR
  service basis) → no marketing unsubscribe footer, kept on a separate stream. (FTC CAN-SPAM guide; ICO.)
- RFC 8058 one-click: bulk senders (5k/day) must send `List-Unsubscribe` + `List-Unsubscribe-Post:
  List-Unsubscribe=One-Click`; the mailbox POST may unsubscribe silently (safe — client-triggered), while
  the in-body human link must be a **GET → interstitial → POST** (the forwarded-email accidental-unsub
  defense). (Mailgun/RFC 8058; Gmail/Yahoo 2024 rules.)
- OWASP Forgot-Password: identical response **and constant-time** for matched/unmatched email; do the
  email send async so the matched path doesn't leak via latency; count the request not the match.

## Key Technical Decisions

- **F1 forward-fix + backfill is the gate for all recovery value.** `customer_creation="always"` (one
  line in `checkout.py`) fixes new purchases; a one-time backfill tool populates legacy rows. Without
  both, `/recover/email` finds nothing for existing customers. The brainstorm's Dependencies section
  claiming `if_required` already creates customers is **stale and wrong** — confirmed against source.
- **Store `customer_id` on the token at mint time (option b), don't search at recovery time.** Capture
  `session.customer` in the webhook + success-page mint paths and persist it on the token row. O(1),
  strongly consistent, no Search dependency. Requires porting the `job_store` migration runner into
  `token_store` to add a nullable `customer_id` column + index.
- **Recovery lookup uses `Customer.list(email=...)`, not `Customer.search`.** Exact match, strongly
  consistent — avoids the Search substring-match imprecision and the eventual-consistency hole right
  after purchase. (Overrides origin R3's wording, which named `Customer.search`.)
- **No new signing dependency — use `cryptography` (Fernet), already in `requirements.txt`.** Mint the
  recovery link as a Fernet-encrypted `{customer_id, issued_at}` payload with a 1h TTL enforced on
  decrypt. Revisitable within TTL; newest-link-wins (a new recovery request for the same email rotates
  the signing nonce so older links die). Overrides the origin's `itsdangerous` assumption.
- **Reuse `email_client.py`, don't create `email.py`.** Add a plain/html no-attachment `send_email`
  sibling and decouple it from the Kindle `WEB_SEND_TO_KINDLE_ENABLED` gate via a small config addition.
- **`subscribers` is a new store module mirroring `recovery_events_store.py`**, not a token_store column.
  Completely independent of credits.
- **Separate confirm and unsubscribe tokens (security-review finding).** Confirm token: single-use, 72h
  TTL, dies on confirmation. Unsubscribe token: long-lived, scoped to unsubscribe only, **rotated on
  use**. A signed token encodes `{subscriber_id, action}` so a confirm token can never act as an
  unsubscribe token.
- **No-enumeration is constant-time, not just same-body.** Both `/api/recover/email` and `/api/subscribe`
  return `204` for matched/unmatched, and send email **asynchronously** (via `billing_executor`) so the
  matched path doesn't leak via latency. Rate-limit counters increment on the request, not the match.
- **SQLite-persisted, sha256-bucketed rate limiting**, shared primitive for recovery + subscribe. Per the
  Cloudflare-KV learning adapted to SQLite: hash the email, fixed-window buckets, fail closed. Persisted
  (not in-memory) so limits survive restarts and aren't multiplied by worker count.
- **Recovery email is transactional → no unsubscribe footer, separate sending identity considerations.**
  Marketing emails (confirm + future sends) carry the List-Unsubscribe headers + in-body GET interstitial.
- ~~**Turnstile-gate the public subscribe form.**~~ **DROPPED from launch (2026-05-24 review).** Four
  reviewers flagged it: not in the brainstorm (scope creep), **no Python-side Turnstile siteverify exists
  today** (the existing Turnstile lives in the separate Cloudflare contact-worker — this would be net-new
  greenfield, not "wire up existing infra"), and it adds friction the current data doesn't justify.
  Launch relies on the per-IP rate limit + double opt-in (what the brainstorm specified). Add Turnstile as
  a follow-up if abuse appears — and if added, apply it to the recovery endpoint too (security reviewer).
- **Subscriber email is the only new PII; credit recovery stays accountless.** The bounded privacy delta
  is already recorded in Scope/System-Wide Impact; implementation must also document the VM
  disk-encryption, file-permission, and backup posture for `data/web_service.db`.

## Open Questions

### Resolved During Planning

- F1 backfill feasibility → **feasible** (Checkout retains email on Session/Charge regardless of
  `receipt_email=None`). Backfill is Unit 2.
- Token→customer lookup mechanism (origin "deferred to planning", options a/b) → **option (b)**, store
  `customer_id` at mint; backfill legacy rows by `payment_intent_id`.
- Signing library → `cryptography`/Fernet (no new dep), not `itsdangerous`.
- Customer lookup API → `Customer.list(email=...)`, not `.search`.
- Confirm vs unsubscribe token → **separate** tokens.
- Email module → extend `email_client.py`.
- Rate-limit storage → SQLite-persisted sha256 buckets, shared store.

### Deferred to Implementation

- Exact recovery + confirmation email subject/body copy (keep terse, plain-text; match
  `cloudflare/contact-worker/src/send.ts` tone).
- Exact Fernet payload field layout and nonce-rotation storage — decide when wiring Unit 4b against real
  code.
- Whether the recovery rate-limit table and subscribe rate-limit table share one schema or are separate
  (either acceptable; lean shared).
- Footer SubscribeForm exact visual placement (minor design pass).
- Backfill batch size / pagination tuning and whether to run it as a one-shot CLI or an idempotent
  re-runnable maintenance script (lean re-runnable, dry-run default).
- Whether `/recover/show` link should be revoked on first view or strictly TTL-bounded (lean TTL-bounded
  + newest-wins per origin R5).

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation
> specification. The implementing agent should treat it as context, not code to reproduce.*

### Recovery flow (3B.1)

```
User on /recover  ──(new email form)──▶  POST /api/recover/email {email}
                                              │ validate shape (email-validator, no CRLF)
                                              │ rate-limit check (per-email 3/24h + per-IP 10/hr, sha256 buckets, SQLite)
                                              │ ALWAYS return 204 (no-enumeration)
                                              │ async (billing_executor):
                                              │     Customer.list(email=...)  ── none ─▶ stop (no email sent)
                                              │            │ found
                                              │            ▼
                                              │     mint Fernet link {customer_id, issued_at}, TTL 1h, rotate nonce
                                              │     send recovery email (transactional, no unsub footer)
                                              ▼
Email link ─▶ GET /recover/show?token=…  (FastAPI-rendered, private/no-store)
                  │ Fernet-decrypt + TTL check + nonce-current check  ── fail ─▶ _render_expired (request-new link)
                  │ resolve customer_id → tokens (via stored tokens.customer_id; legacy via PI match)
                  ▼
              render token states: unconsumed+valid (copy) | expired (greyed) | disputed (refunded notice)
              (used tokens omitted)  · all values html.escape(quote=True)
```

### Mailing-list flow (3B.2 + 3B.3)

```
Footer SubscribeForm ─▶ POST /api/subscribe {email, source}
                            │ validate · per-IP rate limit · 204 no-enumeration
                            │ INSERT-or-ignore subscribers(email UNIQUE, opted_in_at, confirm_token, unsub_token, source)
                            │ async send double-opt-in confirm email (confirm_token, 72h)
                            ▼
GET /subscribe/confirm?token=  ─▶ single-use confirm token, set opted_in_confirmed_at, idempotent "confirmed" page

Marketing email footer: List-Unsubscribe + List-Unsubscribe-Post (one-click POST) + in-body GET link
In-body link ─▶ GET /unsubscribe?token=  ─▶ interstitial "Confirm unsubscribe <email>?" [Confirm]
                                              └▶ POST /unsubscribe?token=  set unsubscribed_at, ROTATE unsub_token
```

## Output Structure

New files (repo-relative); modified files are listed per unit:

```
web_service/
├── recovery_link.py            [Unit 4b] Fernet signed-link mint/verify + nonce rotation (recovery tranche)
├── rate_limit_store.py         [Unit 4a] SQLite sha256-bucketed per-email/per-IP limiter (shared)
├── subscribers_store.py        [Unit 9]  subscribers table store (mirrors recovery_events_store.py)
└── routes/
    ├── recover_email.py        [Units 7,8]  POST /api/recover/email + GET /recover/show
    ├── subscribe.py            [Units 9,10] POST /api/subscribe + GET /subscribe/confirm
    └── unsubscribe.py          [Unit 12]    GET/POST /unsubscribe

web_service/frontend/components/
└── SubscribeForm.tsx           [Unit 11]  footer signup ("use client")

tools/
└── backfill_stripe_customers.py [Unit 2]  one-time/idempotent legacy-row customer_id backfill

tests/
├── test_web_token_store_customer_id.py   [Unit 1]
├── test_web_recovery_link.py             [Unit 4b]
├── test_web_rate_limit_store.py          [Unit 4a]
├── test_web_recover_email_routes.py      [Units 7,8]
├── test_web_subscribers_store.py         [Unit 9]
├── test_web_subscribe_routes.py          [Units 9,10]
└── test_web_unsubscribe_routes.py        [Unit 12]
```

(Endpoint route files may be consolidated if the implementer finds a cleaner layout; per-unit `Files`
sections are authoritative.)

## Implementation Units

### Shared foundations (land first — used by both 3B.1 and 3B.2/3B.3)

- [ ] **Unit 3 (foundation): Python plain/HTML email sender on `email_client.py`**

**Goal:** A no-attachment transactional/marketing email sender reusing the existing Resend plumbing,
decoupled from the Kindle feature gate.

**Requirements:** R4 (recovery email), R9/R13 (mailing-list emails)

**Dependencies:** None.

**Files:**
- Modify: `web_service/email_client.py` (add `send_email(*, from_addr, to, subject, text, html=None, headers=None) -> SendResult`)
- Modify: `web_service/config.py` (add a mailing/recovery from-address + ensure `resend_api_key` loads
  without `WEB_SEND_TO_KINDLE_ENABLED`; new flag e.g. `WEB_EMAIL_ENABLED` or unconditional key load)
- Test: extend `tests/test_web_send_to_kindle.py` or new `tests/test_web_email_client_send.py`

**Approach:** Mirror `send_with_attachment` (lazy `import resend`, api_key wiring, `_extract_message_id`,
never log `to`). Support optional `headers` (for List-Unsubscribe in the mailing-list send path). Plain
`text` is valid alone. Retry once on 5xx/timeout; map 4xx to a sanitized error.

**Patterns to follow:** `web_service/email_client.py` existing wrapper; `SendResult` shape.

**Test scenarios:**
- Happy path: mock Resend `200 {id}` → `SendResult(ok=True, message_id=...)`.
- Error path: 5xx → one retry → still 5xx → `ok=False`, sanitized error, `to` never in message.
- Error path: 4xx → no retry → `ok=False`.
- Edge: `headers` dict passed through to the Resend payload.
- Edge: api_key wiring works with Kindle gate OFF (regression: recovery email must send independently).

**Verification:** new sender unit tests pass; sending does not require `WEB_SEND_TO_KINDLE_ENABLED=1`.

---

- [ ] **Unit 4a (foundation): shared SQLite rate-limit store**

**Goal:** A sha256-bucketed, SQLite-persisted per-email/per-IP rate limiter shared by the now-shipping
mailing-list tranche and the later recovery tranche.

**Requirements:** R3 (recovery rate limit), R9 (subscribe rate limit)

**Dependencies:** None.

**Files:**
- Create: `web_service/rate_limit_store.py` (`check_and_increment(scope, key, limit, window_s) -> bool`)
- Modify: `web_service/main.py` (init the rate-limit table in lifespan, alongside other `init_db()` calls)
- Test: `tests/test_web_rate_limit_store.py`

**Approach:** `rate_limit_store` mirrors `recovery_events_store.py` shape: a
`rate_limit_buckets(scope, bucket_key, count, window_start)` table; key = `sha256(lowercased_email)` for
email scope, client-IP bucket from `web_service/rate_limit.py:trusted_client_key()` for IP scope (IPv6
`/64`); fixed window `floor(unix/window)`; **fail closed** if the DB write errors. Do not key on
`request.client.host` in production, where Cloudflare/nginx can collapse traffic to loopback.

**Patterns to follow:** `web_service/recovery_events_store.py` (store shape); the Cloudflare-KV
bucketing learning; `web_service/rate_limit.py:trusted_client_key()` for client identity.

**Test scenarios:**
- Rate limit happy: under limit returns allow; at limit+1 within window returns deny.
- Rate limit edge: window rollover resets the count.
- Rate limit edge: email hashed not stored plaintext (assert no plaintext email in the row).
- Rate limit failure: simulated DB write error → **fail closed** (deny), not allow.
- Production keying: loopback peer + trusted CF header yields the real client key; untrusted peer falls
  back safely.

**Verification:** rate-limit unit tests pass; rate-limit table created idempotently in lifespan.

---

- [ ] **Unit 4b (foundation, recovery tranche): signed recovery-link primitive + nonce store**

**Goal:** A Fernet-based signed 1h recovery link with persisted nonce rotation (newest-link-wins).

**Requirements:** R3 (signed link), R5 (TTL/revisitable)

**Dependencies:** Recovery tranche only; do not block 3B.2/3B.3 on this unit.

**Files:**
- Create: `web_service/recovery_link.py` (`mint_link(customer_id) -> str`, `verify_link(token) -> customer_id | None`)
- Modify: `web_service/config.py` (`RECOVERY_LINK_SECRET` Fernet key load; separate from `crypto.py` keys)
- Modify: `web_service/main.py` (init `recovery_link_nonces` table in lifespan)
- Test: `tests/test_web_recovery_link.py`

**Approach:** `recovery_link` Fernet-encrypts `{customer_id, issued_at, nonce}` with a dedicated
`RECOVERY_LINK_SECRET`; `verify_link` decrypts, enforces 1h TTL, and checks the nonce against
`recovery_link_nonces(customer_id PRIMARY KEY, current_nonce, updated_at)`. Minting a new link rotates
the persisted nonce so older links die.

**Patterns to follow:** `web_service/recovery_events_store.py` (store shape); `web_service/crypto.py` for
constant-time helpers, but do not reuse its token hash/encryption secret.

**Test scenarios:**
- Happy: mint→verify round-trips returning customer_id within TTL; revisitable (verify twice succeeds).
- Edge: verify past 1h TTL → None.
- Edge: tampered/garbage token → None (no exception leak).
- Edge: minting a new link rotates the nonce → the older link's verify → None (newest wins).
- Security: recovery link key differs from token hash/at-rest encryption keys.

**Verification:** recovery-link unit tests pass; nonce table created idempotently in lifespan.

---

### Phase 3B.1 — Stripe-customer-binding recovery (R1–R7) — **F1-gated**

- [ ] **Unit 1 (F1 forward-fix): `customer_creation="always"` + capture & persist `customer_id`**

**Goal:** New purchases create a Stripe Customer and bind it to the minted tokens, so future recovery has
data to find. This is the prerequisite that unblocks the entire recovery half.

**Requirements:** F1; supports R3/R5

**Dependencies:** None — must land first in 3B.1.

**Execution note:** Test-first. This touches the billing mint path; per `web_service/docs/stripe-verification.md`
extend all three verification layers (mocked unit, signed-event e2e, manual CLI script).

**Files:**
- Modify: `web_service/routes/checkout.py` (`customer_creation="always"`)
- Modify: `web_service/token_store.py` (port `job_store` migration runner: `_LATER_COLUMNS` +
  `_LATER_INDEXES` + `_apply_migrations()`; add nullable `customer_id TEXT` + index; thread
  `customer_id` through `mint_tokens_if_absent(..., customer_id=None)` and the INSERT)
- Modify: `web_service/routes/webhook.py` (read `session.get("customer")` on
  `checkout.session.completed`/`async_payment_succeeded`; pass to mint)
- Modify: `web_service/routes/payment.py` (success-page mint path mirrors the webhook customer_id pass-through)
- Modify: `web_service/main.py` (token_store `init_db()` now runs `_apply_migrations`)
- Test: `tests/test_web_token_store_customer_id.py`; extend `tests/test_web_webhook.py`,
  `tests/test_web_payment.py`, `tests/test_web_checkout.py`

**Approach:** Migration ALTER runs in `_apply_migrations` with a temporary `PRAGMA busy_timeout=30000` at
the migration boundary (per the retired plan's deploy note; webhook holds `BEGIN IMMEDIATE` during Stripe
calls — pause webhook delivery ~30s during the deploy that ships the ALTER). `customer_id` is nullable;
existing rows stay NULL until backfill (Unit 2).

**Patterns to follow:** `web_service/job_store.py:_apply_migrations`; existing `mint_tokens_if_absent`
transaction shape; webhook metadata-read pattern.

**Test scenarios:**
- Happy: logged Checkout with `customer_creation="always"` → webhook receives `customer` → token row has
  `customer_id` populated.
- Happy: success-page mint (webhook not yet fired) also persists `customer_id` → identical row.
- Migration: run `_apply_migrations` once adds column+index; re-run is a no-op (PRAGMA table_info gate).
- Migration race: two workers run migration concurrently → exactly one ALTER, no error (mirror
  `tests/test_web_job_store_migration_race.py`).
- Edge: session with `customer=None` (declined/edge) → mint with `customer_id=NULL`, no 500.
- Integration: `stripe trigger checkout.session.completed` (signed e2e) yields a customer-bound token.
- Regression: anonymous Phase 2 validate/consume path unchanged.

**Verification:** all three Stripe verification layers pass; new tokens carry `customer_id`; migration
idempotent and race-safe.

---

- [ ] **Unit 2 (F1 backfill): one-time `customer_id` backfill for legacy token rows**

**Goal:** Populate `customer_id` for pre-patch purchases so existing customers can recover. Feasible
because Checkout retained the buyer email on Session/Charge even with `receipt_email=None`.

**Requirements:** F1

**Dependencies:** Unit 1 (column exists).

**Files:**
- Create: `tools/backfill_stripe_customers.py` (idempotent, `--dry-run` default, `--apply` to write)
- Test: `tests/test_web_backfill_stripe_customers.py` (mock Stripe list/create)

**Approach:** For each token row with `customer_id IS NULL` and a `payment_intent_id`: retrieve the PI
(strongly consistent, by stored ID — not Search), expand `latest_charge`, read email from
`charge.billing_details.email` (fallback `receipt_email`); if a Customer with that email exists
(`Customer.list(email=...)`) reuse it, else `Customer.create(email=...)`; write `customer_id` back to the
token row. Idempotent: re-running skips rows already populated. Log coverage stats (rows matched vs
email-missing). Honest gap: rows whose charge never captured an email (not expected for Checkout-
originated payments) are reported as unrecoverable, not failed.

**Patterns to follow:** existing Stripe SDK usage in `web_service/routes/`; `token_store` write helpers;
run Stripe calls outside request context (this is a CLI tool).

**Test scenarios:**
- Happy: legacy row + PI with `billing_details.email` + no existing Customer → creates Customer, writes
  customer_id.
- Happy: email already has a Customer → reuses it (no duplicate create).
- Idempotent: row already has customer_id → skipped; second full run writes nothing new.
- Edge: PI/charge with no email → reported unrecoverable, row left NULL, run continues.
- Dry-run: `--dry-run` reports intended writes, mutates nothing (DB + Stripe create not called).
- Edge: pagination over many PIs handled.

**Verification:** dry-run on prod-like data reports realistic coverage; `--apply` populates rows
idempotently; spot-check a backfilled row recovers correctly via Unit 8.

---

- [ ] **Unit 7: `POST /api/recover/email` — lookup, no-enumeration, rate-limited send**

**Goal:** Accept an email, look up the Stripe customer, and (only on match) email a signed recovery link —
with a constant-time, identical response regardless of match.

**Requirements:** R2, R3, R4, R7

**Dependencies:** Units 3 (email), 4 (link + rate limit), 1 (customer_id exists).

**Execution note:** Test-first — no-enumeration and rate-limit correctness are easy to get subtly wrong.

**Files:**
- Create: `web_service/routes/recover_email.py` (`POST /api/recover/email`)
- Modify: `web_service/main.py` (include router)
- Modify: `web_service/frontend/next.config.js` (add `/api/recover/email` rewrite)
- Modify: `web_service/frontend/components/RecoverClient.tsx` (second "recover by email" form)
- Modify: `web_service/frontend/lib/api.ts` (`recoverByEmail(email)`)
- Test: `tests/test_web_recover_email_routes.py`

**Approach:** Validate email (email-validator, reject CRLF). Rate-limit check (per-email 3/24h + per-IP
10/hr) incrementing on the request (not the match). Return `204` immediately; do the
`Customer.list(email=...)` → mint link → `email_client.send_email` work **async on `billing_executor`** so
matched/unmatched latency is indistinguishable. On Resend failure, log ERROR (operator alert) but the
response is still 204.

**Patterns to follow:** `web_service/routes/recover.py` router shape + EB-292 fire-and-forget executor
pattern; OWASP forgot-password generic-response rule.

**Test scenarios:**
- Happy: known email (mock `Customer.list` → 1) → 204; email send invoked with a valid signed link.
- No-enumeration: unknown email → 204, **same body/status**; no email sent.
- Constant-time: matched and unmatched both return synchronously before the async send (assert send is
  off-thread).
- Edge: malformed email → 422 (shape failure is acceptable to distinguish; not an enumeration oracle).
- Rate limit: 4th request for same email in 24h → 429; counter incremented even for unmatched email.
- Rate limit: 11th request from same IP in 1h → 429.
- Error: Resend 5xx → still 204, ERROR logged.
- Security: reflected email in any error output is `html.escape(quote=True)`.

**Verification:** route tests pass; manual: real email → recovery email arrives < 60s with a working link.

---

- [ ] **Unit 8: `GET /recover/show?token=` — FastAPI-rendered token reveal**

**Goal:** Validate the signed link and render the customer's recoverable tokens with correct per-state UI.

**Requirements:** R5, R6, R7

**Dependencies:** Units 4 (verify_link), 1 (customer_id), 7 (link issuance).

**Files:**
- Modify: `web_service/routes/recover_email.py` (`GET /recover/show`)
- Modify: `web_service/frontend/next.config.js` (add `/recover/show` rewrite → FastAPI)
- Modify: `web_service/token_store.py` (add `get_tokens_for_customer(customer_id)` read helper)
- Test: extend `tests/test_web_recover_email_routes.py`

**Approach:** `verify_link(token)` → customer_id or render `_render_expired` (with a "request a new link"
link back to `/recover`). Resolve tokens via `tokens.customer_id` (new rows) plus legacy rows matched by
backfill. Render states: unconsumed+valid (copy button, "valid until"), unconsumed+expired (greyed),
disputed (prominent "refunded" notice + dispute date); **omit used tokens**. Reuse the `_render_*` +
`_base_html` shell idiom from `payment.py`; set `Referrer-Policy: no-referrer`, `Cache-Control:
private, no-store`; `html.escape(quote=True)` every reflected value.

**Patterns to follow:** `web_service/routes/payment.py` `_render_*` helpers + `_PAYMENT_HEADERS`;
`web_service/templates/shell.py` for header/footer; the XSS-escape solution doc.

**Test scenarios:**
- Happy: valid token → page lists the customer's unconsumed tokens with copy buttons.
- Revisitable: same link viewed twice within TTL both render (no single-use consumption).
- Edge: expired token → expired page with request-new-link CTA; tampered token → same expired/invalid page.
- State: disputed pack → rendered with refunded notice + date; used token → not displayed.
- State: customer with zero recoverable tokens → friendly empty state (no leak of why).
- Security: a `<script>`-laden email/token reflected into the page is escaped (template XSS regression).
- Headers: response carries `private, no-store` + `no-referrer`.

**Verification:** route tests + template XSS test pass; manual: click a real recovery link → tokens shown.

---

### Phase 3B.2 — Standalone mailing list + double opt-in (R8–R11) — **F1-independent**

- [ ] **Unit 9: `subscribers` store + `POST /api/subscribe` (double-opt-in send)**

**Goal:** Capture footer signups into a `subscribers` table and send a double-opt-in confirmation email,
with no-enumeration response and abuse gating.

**Requirements:** R8, R9, R10

**Dependencies:** Units 3 (email), 4a (rate limit).

**Files:**
- Create: `web_service/subscribers_store.py` (table + `insert_or_ignore`, `set_confirmed`, token helpers)
- Create: `web_service/routes/subscribe.py` (`POST /api/subscribe`)
- Modify: `web_service/main.py` (init_db + include router)
- Modify: `web_service/frontend/next.config.js` (`/api/subscribe` rewrite)
- Test: `tests/test_web_subscribers_store.py`, `tests/test_web_subscribe_routes.py`

**Approach:** `subscribers(email UNIQUE lowercased, opted_in_at, opted_in_confirmed_at NULL,
confirm_token UNIQUE, unsubscribe_token UNIQUE, source DEFAULT 'footer', unsubscribed_at NULL)` — mirror
`recovery_events_store.py` store shape. `POST /api/subscribe` validates email, per-IP rate-limits
(5/hr), INSERT-or-ignore, returns `204` regardless of new/existing (no "already subscribed" oracle),
async-sends the confirm email (single-use `confirm_token`, 72h). Separate confirm vs unsubscribe tokens
minted at insert. Turnstile is intentionally out of launch scope; rely on per-IP rate limiting + double
opt-in.

**Patterns to follow:** `web_service/recovery_events_store.py`; `secrets.token_urlsafe(32)` for tokens.

**Test scenarios:**
- Happy: new email → row inserted (unconfirmed), confirm email sent, 204.
- No-enumeration: existing email → 204 same response; no duplicate row; no confirm resend; no
  `opted_in_at` reset.
- Edge: malformed email → 422.
- Rate limit: 6th signup from same IP in 1h → 429.
- Store: confirm_token and unsubscribe_token are distinct and unique.
- Security: email lowercased + trimmed at insert; UNIQUE collision is a no-op.

**Verification:** store + route tests pass; manual: footer submit → confirm email < 60s.

---

- [ ] **Unit 10: `GET /subscribe/confirm?token=` — single-use confirm**

**Goal:** Confirm a subscription (double-opt-in step 2), idempotently.

**Requirements:** R11

**Dependencies:** Unit 9.

**Files:**
- Modify: `web_service/routes/subscribe.py` (`GET /subscribe/confirm`)
- Modify: `web_service/frontend/next.config.js` (`/subscribe/confirm` rewrite → FastAPI render)
- Test: extend `tests/test_web_subscribe_routes.py`

**Approach:** Look up by `confirm_token`; enforce 72h TTL from `opted_in_at`; set
`opted_in_confirmed_at=now`; render a "confirmed" page (FastAPI `_render_*`). Idempotent: re-clicking shows
the same confirmation without error and without flipping state again. After confirmation the confirm
token is spent.

**Patterns to follow:** `payment.py` `_render_*`; `html.escape`.

**Test scenarios:**
- Happy: valid token → `opted_in_confirmed_at` set, confirmation page shown.
- Idempotent: second click → same page, no error, no double-confirm side effect.
- Edge: expired (>72h) token → "link expired, re-subscribe" page.
- Edge: unknown/garbage token → generic invalid page (no enumeration).
- Security: reflected values escaped.

**Verification:** route tests pass; only `opted_in_confirmed_at IS NOT NULL` rows are marketing-eligible.

---

- [ ] **Unit 11: footer `SubscribeForm` component + frontend wiring**

**Goal:** Ship the visible signup surface in the global footer.

**Requirements:** R8

**Dependencies:** Unit 9 (endpoint exists).

**Files:**
- Create: `web_service/frontend/components/SubscribeForm.tsx` ("use client")
- Modify: `web_service/frontend/components/Footer.tsx` (embed SubscribeForm)
- Modify: `web_service/frontend/lib/api.ts` (`subscribeToMailingList(email)`)
- Test: none — no frontend unit-test infra; add a Playwright spec if practical
  (`web_service/frontend/tests/subscribe-form.spec.ts`).

**Approach:** Single email field + "Subscribe to updates" button. On submit POST `/api/subscribe`; on
success swap to "Check your inbox to confirm." Mirror `RecoverClient` client-state patterns and design
tokens already in `Footer.tsx`.

**Patterns to follow:** `web_service/frontend/components/RecoverClient.tsx`; `lib/api.ts`
`createCheckoutSession` + `ApiError` shape.

**Test scenarios:** Test expectation: none (no JS unit-test infra) — manual + optional Playwright:
submit → "check your inbox" state; invalid email → inline error.

**Verification:** footer form renders on every page; submit produces a confirm email.

---

### Phase 3B.3 — Unsubscribe + email footer (R12–R13) — **F1-independent**

- [ ] **Unit 12: `/unsubscribe` interstitial + POST + token rotation**

**Goal:** Honor unsubscribes safely against forwarded-email accidental triggers, with token rotation.

**Requirements:** R12

**Dependencies:** Unit 9 (subscribers + unsubscribe_token).

**Files:**
- Create: `web_service/routes/unsubscribe.py` (`GET` interstitial + `POST` action)
- Modify: `web_service/main.py` (include router)
- Modify: `web_service/frontend/next.config.js` (`/unsubscribe` rewrite → FastAPI render)
- Test: `tests/test_web_unsubscribe_routes.py`

**Approach:** `GET /unsubscribe?token=` renders a confirmation interstitial ("Confirm: unsubscribe
`<email>`?" [Confirm]) — **never** unsubscribes on GET (forwarded-email/scanner defense, RFC 8058).
`POST /unsubscribe?token=` sets `unsubscribed_at=now` and **rotates `unsubscribe_token`** (leaked-link
self-invalidation); renders "unsubscribed." The unsubscribe token is scoped to unsubscribe only (cannot
confirm or read state). Keep the suppression record permanent even after rotation.

**Patterns to follow:** `payment.py` `_render_*`; `secrets.token_urlsafe` for rotation; `html.escape`.

**Test scenarios:**
- Happy: GET renders interstitial only (no state change); POST flips `unsubscribed_at` + rotates token.
- Security: the old (pre-rotation) token POSTed again → no-op/invalid (self-invalidated).
- Edge: GET/POST with unknown token → generic invalid page.
- Idempotent: POST twice → second is a no-op on an already-unsubscribed row.
- Scope: an unsubscribe token cannot be used at `/subscribe/confirm` (separate-token property).

**Verification:** route tests pass; forwarded-link GET cannot unsubscribe; rotation invalidates old links.

---

- [ ] **Unit 13 (fold into Units 9/12): marketing-email footer + List-Unsubscribe headers**

**Goal:** Every marketing email (confirm email + future sends) carries compliant unsubscribe affordances;
recovery emails are excluded.

**Requirements:** R13

**Dependencies:** Units 3 (email headers passthrough), 9 (unsubscribe_token), 12 (unsubscribe route).
This is not a standalone implementation tranche; wire the confirm-email footer/headers while building
the mailing-list send path, and coordinate the one-click POST behavior with Unit 12.

**Files:**
- Modify: `web_service/routes/subscribe.py` (confirm email includes footer + headers)
- Modify: `web_service/email_client.py` only if a shared footer/header helper is cleanest
- Test: extend `tests/test_web_subscribe_routes.py` (assert headers/footer present)

**Approach:** For marketing-class sends, append an in-body footer with the GET unsubscribe link
(`/unsubscribe?token=<unsubscribe_token>`) and set `List-Unsubscribe: <https://…/unsubscribe?token=…>` +
`List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers (the mailbox one-click POST hits the same
route; allow a POST-with-header path to unsubscribe silently per RFC 8058 — distinct from the human GET
interstitial). **Recovery emails (Unit 7) pass none of these** (transactional).

**Patterns to follow:** RFC 8058 header pair; CAN-SPAM transactional/marketing split.

**Test scenarios:**
- Happy: confirm email payload includes the in-body unsubscribe link + both List-Unsubscribe headers.
- Exclusion: recovery email (Unit 7) has **no** unsubscribe footer/headers (regression assert).
- Edge: one-click POST (header path) unsubscribes without the interstitial; human GET still shows it.

**Verification:** header/footer assertions pass; recovery vs marketing classes are correctly differentiated.

---

### Documentation

No standalone ADR unit ships with this tranche. The accountless-credit / subscriber-email privacy delta is
already recorded in Scope Boundaries and System-Wide Impact. EB-336 implementation must still document the
subscriber-email-at-rest posture (VM disk encryption, DB file permissions, and backup handling) in its
close-out or an operations note before shipping.

## System-Wide Impact

- **Interaction graph:** F1 changes touch the live mint path (checkout → webhook/success → token_store).
  The `_MIDDLEWARE_ALLOWLIST` webhook raw-body invariant must not be disturbed — no new body-reading
  middleware. New routes are additive.
- **Error propagation:** recovery/subscribe endpoints absorb downstream (Stripe/Resend) failures and
  still return 204 (no-enumeration); failures are logged for operator alerting, never surfaced to the
  caller.
- **State lifecycle risks:** the `tokens.account_id`→here-`customer_id` migration runs at lifespan startup
  while the webhook may hold `BEGIN IMMEDIATE` — mitigate with the paused-webhook + temporary
  `busy_timeout=30000` deploy window. Backfill is idempotent and re-runnable.
- **API surface parity:** `customer_creation="always"` affects **all** new checkouts (free of charge to
  existing flows; Phase 2 success/recovery behavior preserved). Both mint call sites (webhook +
  success-page) must thread `customer_id` together.
- **Integration coverage:** signed Stripe e2e (`tests/test_web_payment_e2e.py`) must cover a
  customer-bound mint; a recovery round-trip (email → link → show) needs an integration test with mocked
  Stripe `Customer.list`.
- **Unchanged invariants:** `POST /api/recover` paste flow, Phase 2 anonymous bearer-token
  validate/consume, dispute handling (`mark_disputed`), and the no-PII credit positioning all remain
  intact. The only new persisted PII is confirmed subscriber emails.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| F1 backfill coverage gap (charge with no captured email) | Confirmed unlikely for Checkout-originated payments (email always collected); backfill reports unrecoverable rows explicitly rather than failing. Verify the corpus is 100% Checkout before claiming full coverage. |
| `customer_creation="always"` unintended side effects on Checkout | One-line, well-documented Stripe behavior; covered by signed e2e + manual CLI verification across all three layers before deploy. |
| token_store migration collides with in-flight webhook (`BEGIN IMMEDIATE`) | Paused-webhook + temporary `busy_timeout=30000` deploy window (~60s); Stripe's ~3-day retry budget absorbs the pause. Migration-race test. |
| Enumeration leak via latency, not body | Async email send on `billing_executor`; rate-limit counter increments on request not match; explicit constant-time test. |
| Email-bombing a victim via the recovery form | Per-email (3/24h) **and** per-IP (10/hr) sha256-bucketed SQLite limits, fail-closed; counts unmatched requests too. |
| Deliverability of a new high-volume sender while DMARC `p=none` | Send on `send.leafbind.io`, DKIM-aligned; mail-tester ≥9/10 before launch; recovery (transactional) kept on a separate class from marketing. |
| Forwarded-email accidental unsubscribe | GET interstitial never unsubscribes; only POST acts; unsubscribe token rotates on use. |
| Token reuse across confirm/unsubscribe | Separate, action-scoped tokens. |
| "Collect emails you never send" anti-pattern | Operator content commitment R15 (monthly from 2026-08-01) or deactivate the form; double-opt-in keeps only confirmed addresses. |
| Stripe Customer.search imprecision/eventual consistency | Use `Customer.list(email=...)` (exact, strongly consistent); store customer_id at mint to avoid lookup latency entirely for new purchases. |

## Documentation / Operational Notes

- **Deploy choreography for Unit 1:** pause Stripe webhook delivery ~30s before deploying the migration,
  deploy, verify the `_apply_migrations` log line, resume delivery. Run the Unit 2 backfill `--dry-run`
  first, review coverage, then `--apply`.
- **Pre-launch email check:** verify the new sender against mail-tester (≥9/10); watch DMARC aggregate
  reports (policy still `p=none` until ~2026-06-15).
- **Ship confirmation:** confirm Vercel landed frontend changes as Production via `vercel ls` (not the PR
  check); productionBranch must be `master`.
- **Add a CI grep guard** extending the XSS guard to the new reflected params (`email`, recovery/confirm/
  unsubscribe tokens).
- **Compound after merge:** file `docs/solutions/` entries for (a) the `customer_creation`/Customer-binding
  Stripe gotcha and (b) the Phase 2 chargeback/idempotency retro (deferred items above).
- **EB-292:** revisit the measurement data at ~2026-06-15 regardless — to validate the override decision
  retrospectively.

## Document-Review Corrections (2026-05-24)

Seven-persona review applied. Resolutions below are authoritative over the unit bodies above where they
conflict; implementers must honor them. `[fixed-inline]` = corrected in the sections above;
`[apply-at-impl]` = a binding correction the implementer must make when building the unit.

**Strategic (resolved by operator decision — see Ship Strategy):**
- **Override rests on a survivorship-biased single signal** (product-lens ×2, adversarial, P0). The 83%
  empty-`localStorage` figure is measured among `/recover` visitors, who are self-selected token-losers —
  not a triple-failure rate across all buyers. EB-292 required three signals. → **Split ship; recovery
  re-gated to 2026-06-15.** `[fixed-inline]`
- **Cost inverted vs. evidence** (product-lens P1): recovery half holds all irreversible billing work. →
  split. `[fixed-inline]`
- **Turnstile** (scope/feasibility/product/security): dropped from launch. `[fixed-inline]`

**Correctness bugs (P0/P1 — must fix before/at implementation):**
- **[apply-at-impl] Per-IP rate limit collapses in prod (feasibility P0).** All traffic is
  CF→nginx→uvicorn(`127.0.0.1`); keying on `request.client.host` makes per-IP limits *global*, defeating
  email-bombing defense and enabling endpoint DoS. **Derive the client IP from the existing
  `web_service/rate_limit.py` `trusted_client_key()` (CF-Connecting-IP gated on loopback peer), not
  `request.client.host`**, before sha256/bucketing. Applies to Unit 4a (both subscribe + recovery scopes).
- **[apply-at-impl] `customer_id` lost on idempotent mint race (adversarial/feasibility P1).**
  `mint_tokens_if_absent` is SELECT-first on `pack_id`; if the success page mints before the webhook, the
  webhook's later call hits the `from_cache` path and never writes `customer_id`. **Backfill on cache-hit:
  `UPDATE tokens SET customer_id=? WHERE pack_id=? AND customer_id IS NULL`** so whichever path supplies
  it wins. Add the race test. (Unit 1 — recovery tranche.)
- **[apply-at-impl] `customer_creation="always"` may not populate `Customer.email` (feasibility/adversarial
  P1).** The lookup keys on `Customer.email`; if Stripe leaves it null on auto-created guest Customers,
  recovery silently finds zero (masked by the no-enumeration 204). **Unit 1 must assert via signed e2e
  that the created Customer carries a non-null email; if not, `Customer.modify(email=session.customer_details.email)`
  in the mint path.** (Unit 1 — recovery tranche.)

**Security (P1/P2 — apply at implementation):**
- **[apply-at-impl] Separate `RECOVERY_LINK_SECRET` (adversarial P1, security P2).** Do NOT reuse
  `crypto.py`'s `token_hmac_secret`/Fernet — a link-key leak must not compromise the token-hash/at-rest
  encryption keys. Independent env var (or at minimum a distinct HKDF info label); add a test asserting the
  two Fernet keys differ. Consider `MultiFernet` for rotation (else accept 1h-link wholesale invalidation).
- **[apply-at-impl] Nonce-rotation store (security P1, coherence/scope P2).** Newest-link-wins requires
  persisted per-customer nonce state — Unit 4b is **not** stateless. Add a
  `recovery_link_nonces(customer_id PRIMARY KEY, current_nonce, updated_at)` table (in
  `data/web_service.db`), written on mint, checked on verify.
- **[apply-at-impl] Recovery token in URL leaks (security P1).** Disable Resend click-tracking for recovery
  emails (`click_tracking: false`); redact the `token` query param from nginx/uvicorn access logs;
  `Referrer-Policy: no-referrer` is necessary but not sufficient.
- **[apply-at-impl] `/recover/show` authz isolation (security P1, adversarial P1).** `get_tokens_for_customer`
  must filter strictly `WHERE customer_id = <decrypted>`; add a cross-customer isolation test. If
  `Customer.list(email=...)` returns **multiple** Customers (duplicate-per-email), recovery must **union**
  tokens across all matches, not bind to the first.
- **[apply-at-impl] No-enumeration is structural, not incidental (security P2, adversarial P2).** The
  synchronous path must execute identical branches for matched/unmatched (rate-limit increment → 204); ALL
  Stripe work (`Customer.list`, mint, send) runs off-thread on `billing_executor`. Add a test with a
  mocked `Customer.list` that sleeps, asserting matched/unmatched 204 latency delta is within a tight bound
  and no `stripe.*` call occurs before the response.
- **[apply-at-impl] 429 header leakage (security P2).** Recovery/subscribe 429s carry **no** `Retry-After`
  / `X-RateLimit-*` headers; generic body only. Add assertions.
- **[apply-at-impl] Global send circuit-breaker (security P2).** Add an overall recovery-email-per-hour cap
  (operator-configurable) on top of per-email/per-IP, to bound multi-IP victim bombing and ESP cost.
- **[apply-at-impl] Subscriber email at rest (security P2).** Document the VM disk-encryption + file-perm +
  backup posture for `data/web_service.db`; confirm the DB is not world-readable and is excluded from
  unencrypted backups. (Now-shipping tranche.)
- **[apply-at-impl] Mask email on `/unsubscribe` interstitial (design/security P2).** The interstitial is
  GET-reachable from forwarded mail — show `j***@domain`, not the full address. (Now-shipping tranche.)

**Coherence / consistency (apply at implementation):**
- **[fixed-inline] Dangling "Unit 6" ref** in R3/R4 removed (consolidated into Unit 7; email infra is Unit 3).
- **[fixed-inline] R3 `Customer.search` → `Customer.list(email=...)`** (exact, strongly consistent).
- **[apply-at-impl] Confirm-token semantics (coherence P1):** confirm token is single-use and spent on
  confirmation; re-clicking shows the same "confirmed" page (state-idempotent), **not** a re-confirm.
  Expired (>72h) / unknown token → friendly "re-subscribe" page with a CTA back to the footer form. The
  TTL counts from the *original* `opted_in_at`; **re-submitting an existing unconfirmed email is a no-op
  that does NOT reset `opted_in_at` and does NOT resend** (prevents TTL-extension + confirm-spam). (Unit 9/10.)
- **[apply-at-impl] Unsubscribe-token action scoping (coherence P2):** the signed token encodes
  `{subscriber_id, action}`; `/subscribe/confirm` and `/unsubscribe` each reject a token whose `action`
  field is wrong. (Unit 12.)

**Feasibility / ops (apply at implementation — recovery tranche unless noted):**
- **[apply-at-impl] Migration resilience (feasibility/adversarial P2):** `busy_timeout=30000` at the
  migration boundary — not the manual webhook-pause — is the real safety mechanism, since `/convert`'s
  `validate_and_consume` also contends. Make `_apply_migrations` catch a lock-timeout and bounded-retry the
  ALTER rather than crashing lifespan; confirm the single-nullable-column ALTER does no table rewrite.
- **[apply-at-impl] Backfill robustness (adversarial P1/P3, scope P3):** dedup — `Customer.list` first with
  a same-run in-memory `email→customer_id` cache (defeats create-then-list eventual consistency); handle
  multiple Customers per email; treat `payment_intent_id IN (NULL,'')` as the unrecoverable-by-PI bucket
  and fall back to listing Checkout Sessions by `pack_id` to read `customer_details.email`; add a `--lock-file`
  to bar concurrent runs. Keep idempotent + `--dry-run` default. Confirm the PI→`pack_id` 1:1 invariant.
- **[apply-at-impl] `send_email` error model (feasibility P3):** the existing `email_client.SendResult` has
  no `ok` field and the existing sender *raises* `KindleSendError`. Pick one model for `send_email` (extend
  `SendResult` with `ok`+sanitized error, OR raise and let the caller treat any exception as failure) and
  document the divergence. (Unit 3 — now-shipping tranche.)
- **[apply-at-impl] `RECOVERY_LINK_SECRET` boot semantics:** decide whether it's `_require_env`-at-boot
  (can block restart on un-provisioned hosts, like the Resend keys) or flag-gated; fast-fail on
  missing/malformed Fernet key. (Recovery tranche.)
- **[apply-at-impl] Multi-email buyer limitation:** recovery only reveals tokens for the exact email typed;
  state this in scope + the `/recover/show` empty/partial copy. (Recovery tranche.)
- **[apply-at-impl] Dispute-after-recovery:** `/recover/show` reads token state fresh per request; disputed
  tokens render notice-only (no copyable value). Add a test. (Recovery tranche.)

**Scope / structure (apply at implementation):**
- **Merge Unit 13 into Unit 9** — the marketing-footer + `List-Unsubscribe` headers are a few lines in the
  same file; add the RFC 8058 header assertions to `test_web_subscribe_routes.py` and the recovery-exclusion
  assertion to Unit 7's tests. (Brings the count down; now-shipping tranche.) `[fixed-inline]`
- **Demote Unit 14 ADR** to the "Compound after merge" list (the privacy delta is already recorded in
  Scope/Decisions/System-Wide Impact) — unless the operator wants it as a standalone artifact.
  `[fixed-inline]`
- **Split Unit 4** into 4a (`rate_limit_store.py`, used by both halves — ships now) and 4b
  (`recovery_link.py` + nonce table — recovery tranche), so the mailing-list tranche isn't blocked on the
  Fernet work. `[fixed-inline]`

**Design copy/state gaps (apply at implementation — now-shipping tranche where mailing-list):**
- **[apply-at-impl]** Provide the confirmation-email + recovery-email copy templates (subject, one-line
  purpose, explicit TTL, "didn't sign up?" line) — these are user-facing surfaces, not pure impl details.
- **[apply-at-impl]** Specify `SubscribeForm` loading / network-error / success states + focus management
  (move focus to success message via `aria-live`, WCAG 4.1.3). Specify the footer form's placement (own
  full-width row vs. column; mobile collapse). Specify the two-`/recover`-forms layout (email primary,
  session_id paste secondary/collapsed) — recovery tranche.
- **[apply-at-impl]** Specify `/subscribe/confirm` expired/invalid CTA (re-subscribe link) and the 429
  client copy ("Too many attempts, try again later" — no enumeration).

## Sources & References

- **Origin document:** [docs/brainstorms/2026-05-16-eb45-phase3b-stripe-customer-binding-and-light-mailing-list-requirements.md](docs/brainstorms/2026-05-16-eb45-phase3b-stripe-customer-binding-and-light-mailing-list-requirements.md)
- **Superseded prior plan:** docs/plans/2026-05-16-001-feat-eb45-phase3-accounts-persistent-tokens-plan.md (status: superseded)
- **Measurement gate:** EB-292 (Done; override recorded 2026-05-24)
- Related code: web_service/routes/checkout.py (F1), web_service/token_store.py, web_service/job_store.py
  (migration pattern), web_service/recovery_events_store.py (store template), web_service/email_client.py,
  web_service/routes/payment.py (`_render_*`), web_service/templates/shell.py
- Stripe verification convention: web_service/docs/stripe-verification.md
- External: Stripe Checkout `customer_creation` + Customer List/Search API refs; Resend Python send;
  FTC CAN-SPAM transactional test; RFC 8058 one-click; OWASP Forgot-Password.
