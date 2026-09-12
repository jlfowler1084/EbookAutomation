---
date: 2026-05-16
topic: eb45-phase3b-stripe-customer-binding-and-light-mailing-list
status: paused-pending-measurement
paused_on: 2026-05-16
paused_reason: "Document review surfaced repeated product-lens critique across two consecutive plans: 'building stateful infrastructure for an unmeasured problem.' Plus a feasibility showstopper (customer_creation='if_required' does not create Stripe Customers for guest card checkouts, breaking the entire Stripe-binding recovery flow for existing Phase 2 purchases). Decision: instrument Phase 2's existing recovery rails for 30-60 days, then re-evaluate this brainstorm against data."
supersedes: docs/brainstorms/2026-05-16-eb45-phase3-accounts-persistent-tokens-requirements.md
---

> **PAUSED 2026-05-16 — pending Phase 2 recovery measurement.**
>
> This brainstorm survived its own design pass but did not survive the document-review's
> second round of product-lens critique. The pattern is now unmistakable: two consecutive
> deep brainstorm+plan attempts at "fix token loss + capture mailing list" (the retired
> magic-link plan AND this lighter Stripe-binding plan) both got the same recommendation
> from the product-lens reviewer: **"measure first, don't build stateful infrastructure for
> an unmeasured problem."**
>
> A separate feasibility finding makes the decision easier: Phase 2's
> `customer_creation="if_required"` does NOT create Stripe Customer objects for guest card
> checkouts (the Phase 2 code's own inline comment confirms this), which means the
> Stripe-binding recovery flow would find zero customers for the majority of existing
> purchases without a prerequisite Phase 2 patch + backfill.
>
> **Decision (operator, 2026-05-16):** instrument Phase 2's existing recovery rails for
> 30-60 days, then revisit this brainstorm against actual usage data.
>
> The design work captured below is preserved as reusable input IF the measurement justifies
> resuming the work. Specifically reusable: the no-enumeration response pattern, the rate-limit
> design, the form-submit-is-the-opt-in mailing-list framing, the Resend integration shape.
> The Stripe-Customer-binding architecture itself is gated on resolving the
> `customer_creation` issue first.
>
> Instrumentation work tracked at: **EB-292** — "Phase 2 recovery instrumentation —
> measure /api/recover usage before committing to Phase 3"
> (https://jlfowler1084.atlassian.net/browse/EB-292).
>
> **Do not plan or implement against this doc until the measurement results land.**

# EB-45 Phase 3B — Stripe-Customer-Binding Recovery + Standalone Mailing List (Option H) [PAUSED]

## Problem Frame

This document replaces the retired Phase 3 magic-link-accounts direction
(see `docs/brainstorms/2026-05-16-eb45-phase3-accounts-persistent-tokens-requirements.md`
status: superseded; and `docs/plans/2026-05-16-001-feat-eb45-phase3-accounts-persistent-tokens-plan.md`
status: superseded). The original direction was authored, planned, document-reviewed
(7 persona reviewers in parallel), and retired all on 2026-05-16 after the product-lens
reviewer surfaced a simpler alternative that meets the same two stated goals — solve
token loss + capture mailing list — at ~20% of the implementation cost AND preserves
the Phase 2 "no PII on our side" privacy positioning.

Phase 3B splits the original two goals into two architecturally independent surfaces:

1. **Credit recovery via Stripe customer binding.** Leafbind never stores email; Stripe
   already does as part of the Checkout receipt. A new `/recover` flow accepts an email,
   calls `stripe.Customer.search` server-side, finds the customer, queries our existing
   `tokens` table by `payment_intent_id`, and emails a signed one-time link revealing
   the user's unconsumed (and revoked-but-displayed) tokens. No first-party `accounts`
   table, no magic-link auth, no session cookies, no PII storage on leafbind's side.

2. **Standalone lightweight mailing-list signup.** A separate footer-only signup form
   with double opt-in. New `subscribers` table holds email + opt-in confirmation +
   unsubscribe token + source field. Completely independent of credits, conversions,
   or any auth surface.

Both surfaces use the existing Resend SMTP infrastructure (configured per EB-264 with
authenticated `send.leafbind.io` subdomain). The Phase 2 bearer-token system at
`web_service/token_store.py` is unchanged; the existing session_id-paste `/recover`
endpoint at `web_service/routes/recover.py:21-51` is preserved alongside the new
email-based path as a precise-recovery fallback.

## Requirements

**Credit recovery (Stripe-customer-binding)**

- R1. The existing `POST /api/recover` (session_id paste form) remains unchanged and is
  the **precise recovery path** for users who have a Stripe receipt with the session_id
  but lost the original success URL. See `web_service/routes/recover.py`.
- R2. A new email-based recovery path is added. Surface decision: the existing `/recover`
  Next.js page (referenced from `/pricing` footer and `/payment/cancel`) gains a second
  form: "Lost your tokens? Enter the email you used at checkout." Server endpoint:
  `POST /api/recover/email`.
- R3. `POST /api/recover/email` accepts `{"email": str}`:
  - Validates email shape (RFC 5321, single address, no CRLF)
  - Calls `stripe.Customer.search(query=f"email:'{escaped_email}'")` server-side via
    the `stripe` SDK (using `STRIPE_SECRET_KEY` from existing env config)
  - If a customer is found AND that customer has at least one valid token (`account_id`
    irrelevant — Phase 3B does not introduce `account_id`; the link goes through
    `payment_intent_id` already stored on each token row via Phase 2 R7):
    - Generates a signed token: `itsdangerous.URLSafeTimedSerializer`-signed payload
      `{customer_id, issued_at}` with 1-hour TTL
    - Sends a recovery email via Resend with link
      `https://leafbind.io/recover/show?token=<signed>`
  - If no customer is found OR the customer has no valid tokens, **does NOT send an email**
    and returns the SAME HTTP response as the happy path (204) — no enumeration oracle
  - Rate-limited: 3 requests / 24-hour window per email (sha256-bucketed, persisted to
    SQLite per the EB-264 KV pattern adapted for the FastAPI side), 10 requests / hour
    per source IP
- R4. The recovery email is sent from `support@leafbind.io` (matches the EB-264 sender
  identity; users' replies bounce into the operator support inbox, which is useful for
  surfacing "my link didn't arrive" tickets). Plain-text body, no HTML, no tracking pixels,
  and **no unsubscribe footer** (recovery is transactional, not marketing — see R13).
  Subject: "Your leafbind credit recovery link" (or similar — exact copy deferred to
  planning).
- R5. `GET /recover/show?token=…` is the email-link landing page:
  - Validates the signed token + 1-hour TTL (rejects expired or tampered tokens with
    a clear error page + "request a new recovery email" link)
  - **Revisitable within TTL** — does NOT consume the token on view. Users can re-open
    the link to copy tokens again within the 1-hour window. The token itself, plus the
    Stripe-Customer-Search gate at R3, is the bearer secret.
  - Queries `tokens` table for all rows where the row's `payment_intent_id` resolves to
    the customer_id from the signed payload (via Stripe PaymentIntent retrieve, OR
    via a Stripe-Customer-ID column added to tokens at mint time — implementation
    detail, see Outstanding Questions)
  - Renders all matching tokens (unconsumed AND disputed) with these states:
    - **Unconsumed + not expired:** displayed with copy button, "Valid until <expires_at>"
    - **Unconsumed + expired:** displayed greyed-out with "Expired on <expires_at>"
    - **Disputed (refunded):** displayed with prominent "This pack was refunded and
      these credits are no longer valid" notice + dispute date
    - **Already-used:** NOT displayed (user knows their own use history; no value)
  - Sets `Referrer-Policy: no-referrer`, `Cache-Control: private, no-store`
- R6. `/recover/show` HTML is FastAPI-rendered (not Next.js) using the existing
  `_BrandStaticFiles` + `_render_*` helper pattern from
  `docs/solutions/best-practices/fastapi-nextjs-css-token-sharing-python-shell-2026-05-15.md`,
  per the same architectural split as `/payment/success`.
- R7. All user-controlled values reflected in HTML (email shown in error pages,
  token strings in the list) MUST be escaped via `html.escape(value, quote=True)` per
  `docs/solutions/security-issues/xss-unescaped-session-id-fastapi-fstring-templates-2026-05-15.md`.

**Standalone mailing list**

- R8. A new `<SubscribeForm />` component appears in the global marketing footer
  (`web_service/frontend/components/Footer.tsx`) on every page. Single field (email)
  + submit button labeled "Subscribe to updates." NO opt-in checkbox needed — the act
  of submitting the form IS the explicit opt-in action (different from the retired
  Phase 3C plan which bundled marketing opt-in into a multi-purpose magic-link signup).
- R9. `POST /api/subscribe` accepts `{"email": str, "source": str}`:
  - Validates email shape
  - INSERT-or-ignore into `subscribers` table (UNIQUE on email; subsequent submissions
    are no-ops)
  - Sends a double-opt-in confirmation email via Resend to the submitted address:
    "Confirm your subscription: <link>"
  - Returns 204 regardless of new vs existing email (no enumeration oracle for
    "is X already subscribed?")
  - Rate-limited: 5 requests / hour per IP
- R10. `subscribers` table schema (planning will finalize types and indices):
  - `email TEXT UNIQUE` (lowercased + trimmed at insert)
  - `opted_in_at INTEGER` (when the form was submitted)
  - `opted_in_confirmed_at INTEGER` (NULL until confirmation link clicked; only
    `opted_in_confirmed_at IS NOT NULL` rows are eligible for marketing sends)
  - `unsubscribe_token TEXT UNIQUE` (generated at submit time)
  - `source TEXT DEFAULT 'footer'` (captures origin of the signup; even though only
    'footer' ships at launch, including the column now avoids a migration emergency
    when you add 'pricing' or 'homepage' later)
  - `unsubscribed_at INTEGER` (NULL while active)
- R11. `GET /subscribe/confirm?token=…` (token = `unsubscribe_token` per current spec,
  but see Outstanding Questions — security review surfaced a token-reuse concern that
  may warrant separate tokens for confirm vs unsubscribe):
  - Confirmation-link TTL: **72 hours** from initial signup (planning may adjust;
    sufficient for users who check email once a day or two)
  - Sets `opted_in_confirmed_at = now`
  - Renders "Subscription confirmed! Thanks for joining." + a link back to `/`
  - Idempotent — re-clicking shows the same confirmation page without error
- R12. `GET /unsubscribe?token=…`:
  - Renders confirmation page: "Confirm: unsubscribe `<email>` from leafbind updates?
    [Confirm] [Cancel]"
  - POST `/unsubscribe?token=…` flips `unsubscribed_at = now`, rotates
    `unsubscribe_token`, renders "You've been unsubscribed."
  - Confirmation interstitial mitigates forwarded-email accidental unsubscribe; token
    rotation mitigates leaked-token replay
- R13. Email-footer attachment: confirmation emails (R9) and any future marketing emails
  include a one-click unsubscribe footer with the user's current `unsubscribe_token`.
  Recovery emails (R4) do NOT include this footer — recovery is transactional, not
  marketing.
- R14. **Send infrastructure scope:** Phase 3B only captures the list and ships the
  unsubscribe path. **Out of scope:** marketing campaign tooling (segmentation,
  scheduling, A/B testing, open/click tracking, list export tooling). Operator queries
  the SQLite table manually (`SELECT email FROM subscribers WHERE opted_in_confirmed_at
  IS NOT NULL AND unsubscribed_at IS NULL`) to extract the list for Resend Broadcasts
  or Mailchimp send.
- R15. **Content commitment:** operator commits to monthly product-update sends
  beginning by 2026-08-01. Cadence: first Monday of each month. Content shape: changelog
  summary with screenshots of features shipped that month. This is a self-imposed
  deadline to mitigate the "collect emails you never send to" anti-pattern flagged by
  document-review. If 2026-08-01 passes without a send, operator deactivates the
  signup form rather than letting the list rot. (Tracked as a separate post-Phase-3B
  checkpoint, not as an implementation requirement.)

## Success Criteria

- A user who lost their token bookmark + localStorage + Stripe receipt URL can enter
  their checkout email at `/recover`, receive a recovery email within 60 seconds, click
  the link, and see their unconsumed tokens (and any disputed packs as informational
  context) within the 1-hour TTL window.
- The same email can be entered 3 times in 24 hours; the 4th request is rate-limited
  with a clear "try again in N hours" message.
- A user who never purchased through leafbind (no matching Stripe customer) enters their
  email at `/recover/email` and sees the same "if a matching account exists, we sent you
  an email" response as a real customer — no enumeration possible.
- The recovery link continues to work within its 1-hour TTL even after the user
  navigates away and re-opens it.
- After the 1-hour TTL, the link renders an "expired" page with a "request a new link"
  button that returns to `/recover`.
- Disputed tokens shown in recovery are clearly marked "this pack was refunded" with
  the dispute date.
- A visitor on any leafbind page can subscribe via the footer form, receive a
  confirmation email within 60 seconds, click the link, and reach the "subscription
  confirmed" page.
- A subscriber who clicks the unsubscribe link in any leafbind marketing email lands
  on a confirmation interstitial; submitting the confirmation flips their state to
  unsubscribed AND rotates their unsubscribe token (so the leaked link self-invalidates).
- A subscriber who hits the confirmation link twice (e.g., browser back-button)
  succeeds idempotently — no error, no double-subscribe.
- The Phase 2 anonymous bearer-token validation flow at `/convert` is unchanged.
- The session_id paste form at `POST /api/recover` is unchanged and continues to
  redirect to `/payment/success?session_id=…` for users who have the session ID.
- Operator can query `SELECT email FROM subscribers WHERE opted_in_confirmed_at IS NOT
  NULL AND unsubscribed_at IS NULL` to extract the current list.
- `support@leafbind.io` outbound deliverability for recovery + confirmation emails
  passes mail-tester score ≥ 9/10 (same bar as EB-264 contact form).

## Scope Boundaries

**In scope:**

- Email-based recovery via Stripe Customer Search at `/recover/email` + `/recover/show`
- 1-hour TTL signed link, revisitable within TTL, single-use enforcement NOT required
- Per-email + per-IP rate limiting on recovery requests (sha256-bucketed, SQLite-persisted)
- No-enumeration response pattern (identical UX for matched + unmatched emails)
- Disputed tokens shown in recovery with informational notice
- Standalone footer mailing-list signup form + `subscribers` table
- Double opt-in confirmation flow
- Per-IP rate limit on subscribe endpoint
- Unsubscribe confirmation interstitial + token rotation on toggle
- Self-imposed content commitment: monthly cadence starting by 2026-08-01

**Out of scope for Phase 3B:**

- First-party accounts, magic-link auth, session cookies, account dashboard, conversion
  history, persistent credit balance — all retired with the prior Phase 3 plan
- Marketing campaign tooling: segmentation, scheduling, A/B testing, open/click tracking,
  programmatic list export UI
- Conversion history / re-download infrastructure (deferred indefinitely pending demand
  evidence)
- GDPR geo-gated opt-in toggle (the form-submit-IS-the-opt-in design is GDPR-safer than
  the retired checked-checkbox-bundled-in-magic-link-signup pattern; geo-gate complexity
  not needed)
- Removing the session_id paste form at `POST /api/recover` — that path remains as a
  precise-recovery alternative for users with the Stripe receipt
- Marketing email A/B testing or analytics — purely captured list + send infrastructure
- Self-service subscriber-data export ("download my data" GDPR Article 20) — handled by
  contact form for now
- Phase 2 compound retro (chargeback/webhook idempotency patterns) — file as separate
  follow-up `docs/solutions/` ticket

## Key Decisions

- **Stripe-customer-binding over first-party accounts.** Solves the same token-loss
  problem at ~20% of the implementation cost. Stripe already stores the email; we
  query against their data instead of duplicating it. Preserves Phase 2 privacy
  positioning. (Rationale: `docs/plans/2026-05-16-001-feat-eb45-phase3-accounts-persistent-tokens-plan.md`
  supersession notice + product-lens review findings.)
- **Recovery link is revisitable, not single-use, within the 1-hour TTL.** Matches
  Phase 2's success-page pattern. Users frequently navigate away from token-display
  pages and need to re-open them. The TTL itself plus the Stripe-Customer-Search gate
  at R3 are sufficient bearer-secret protection.
- **No-enumeration response on `/recover/email`.** Identical HTTP response and UI
  message regardless of whether Stripe finds a matching customer. Prevents an attacker
  from probing whether a given email made purchases.
- **Recovery shows disputed tokens with notice (not hidden).** Trade-off considered:
  hiding is cleaner UX (no clutter) but transparent display explains why the balance
  is lower than the user expects and avoids "where did my credits go?" support tickets.
  The `disputed_at` date in the notice gives audit clarity.
- **Recovery email from `support@leafbind.io`.** Reuses EB-264's authenticated sender
  identity. Users' replies bounce into the operator support inbox, which is useful for
  surfacing "my recovery link didn't arrive" complaints rather than dropping them into
  a noreply void.
- **Recovery rate limit: 3/day/email + 10/hour/IP.** Per-email cap blocks email-bombing
  a victim's inbox via the recovery form (a real attack vector since the form accepts
  arbitrary email input). Per-IP cap blocks the same attack from a single source.
  Bucketed via the EB-264 sha256 pattern, persisted to SQLite (NOT in-memory) so the
  limit survives service restarts and is not multiplied by uvicorn worker count —
  a finding from the retired plan's feasibility review.
- **Mailing list is footer-only at launch.** Lowest friction, always visible, doesn't
  compete with the conversion-form primary CTA. Pricing-page and homepage placements
  are deferred until baseline footer conversion is measured.
- **Double opt-in for the mailing list.** Standard GDPR practice; protects Resend
  domain reputation by ensuring only verified addresses receive marketing email;
  filters bots and typos at the source. The one-confirmation-click cost is industry-
  standard and improves list quality more than it hurts signup rate.
- **No opt-in checkbox on the subscribe form.** Submitting the standalone form IS
  the explicit opt-in action. The checked-checkbox concern from the retired plan only
  applied because that plan bundled marketing consent into a multi-purpose magic-link
  signup. A single-purpose form doesn't have that conflict.
- **Source field on `subscribers` table at launch despite single-form scope.** Adding
  `source TEXT DEFAULT 'footer'` at table-creation time is zero ongoing cost; adding
  it later requires a separate `ALTER TABLE` migration (trivially fast in SQLite, but
  still extra work). Including it now avoids a future migration when a second signup
  surface ships.
- **Self-imposed content deadline (2026-08-01).** Mitigates the "collect emails you
  never use" anti-pattern that the product-lens review flagged on the retired plan.
  If the deadline passes without a send, operator deactivates the form rather than
  letting list value erode through silence.
- **Recovery email does NOT include the mailing-list unsubscribe footer.** Recovery is
  transactional, not marketing — a user who used the recovery flow has not consented
  to marketing email, and confusing the two would violate the no-PII privacy story.
  The two systems are completely separate.

## Dependencies / Assumptions

- Phase 2 is live and healthy: tokens table has `payment_intent_id` column populated for
  all rows (verified per Phase 2 brainstorm R7); `support@leafbind.io` outbound
  authenticated via EB-264-configured DKIM/SPF/DMARC ✓
- Stripe Customer object is created at Checkout — verified: Phase 2's
  `web_service/routes/checkout.py:115-122` sets `customer_creation="if_required"`,
  which creates a Customer for guest checkouts that complete payment. Customer email
  is captured by Stripe and queryable via the Customer Search API.
- Stripe Customer Search API access is enabled on the Stripe account (search is a
  paid-tier feature; verify before planning).
- `stripe` Python SDK is already in `requirements.txt` (used by Phase 2 webhook +
  checkout).
- New env var: none new required for recovery — reuses `STRIPE_SECRET_KEY` and
  `RESEND_API_KEY` from EB-264.
- New env var for recovery link signing: `RECOVERY_LINK_SECRET` (`itsdangerous` signing
  key). Distinct from any other signing secret. Stored in `/etc/web_service.env` mode 0640.
- `itsdangerous` and `email-validator` are NOT in `requirements.txt` per the retired
  plan's feasibility verification — these are net-new Python deps for Phase 3B.
- Resend Broadcasts (or Mailchimp / equivalent) is the assumed downstream marketing-send
  tool — out of scope for this brainstorm, but the operator must have an account ready
  before the 2026-08-01 first-send deadline.

## Outstanding Questions

### Resolved During This Brainstorm

- ✓ Approach: Option H (Stripe-binding for recovery + standalone mailing list)
- ✓ Recovery link TTL: 1 hour
- ✓ Recovery link revisitability: revisitable within TTL (not single-use)
- ✓ No-match recovery UX: identical response (no enumeration)
- ✓ Recovery email from address: `support@leafbind.io`
- ✓ Disputed-token visibility: show with refunded notice
- ✓ Recovery rate limit: yes (3/day/email + 10/hour/IP, SQLite-persisted)
- ✓ Form placement: footer only at launch
- ✓ Opt-in flow: double opt-in
- ✓ Source field captured at launch
- ✓ Content plan: monthly product updates, deadline 2026-08-01

### Deferred to Planning

- **Token→customer lookup mechanism.** Two options the implementer chooses between:
  (a) at recovery time, retrieve each PaymentIntent for the customer's charges and
  match against `tokens.payment_intent_id` — accurate but multi-API-call; (b) add a
  `customer_id TEXT` column to tokens at mint time (via `_LATER_COLUMNS` pattern in
  `web_service/token_store.py`) and join directly — faster and cleaner but requires
  a migration. Recommend (b) — same `_LATER_COLUMNS` pattern from `job_store.py:53-72`
  is well-trodden and the column is genuinely useful.
- Recovery email subject + body copy — keep terse, plain-text, matches existing Worker
  patterns at `cloudflare/contact-worker/src/send.ts:81,110`.
- Subscribe confirmation email subject + body copy — same convention.
- Whether the recovery-email rate limit and the subscribe rate limit share a SQLite
  schema or are independent — implementer's call; either is acceptable.
- Exact visual placement of the footer subscribe form (e.g., third column, dedicated
  row, inline next to copyright) — minor design pass.
- Whether existing session_id-paste recovery (`POST /api/recover`) and new email-recovery
  (`POST /api/recover/email`) are presented as two visually-distinct forms on `/recover`,
  tabs, or progressive disclosure — minor design pass.
- Recovery email send infrastructure: reuse the Python Resend integration that Phase 3A
  planned (`web_service/email.py`) — that module needs to land in Phase 3B since Phase 3A
  is retired. Whether to name it `web_service/email.py` or `web_service/recovery_email.py`
  is an implementer call.

### Deferred to Follow-up Tickets

- Phase 2 compound retro (chargeback + webhook idempotency patterns) — file as a
  separate `docs/solutions/` writeup after Phase 3B merges. Load-bearing for any
  future credit-related work.
- Self-service subscriber data export ("download my data" / GDPR Article 20) — file
  as separate privacy-rights ticket if it materializes.
- Marketing campaign automation (segmentation, scheduling, analytics) — separate epic
  when the list reaches the size that manual SQLite export becomes painful (~500+
  subscribers).
- Pricing-page and homepage signup-form placements — defer until baseline footer
  conversion rate is measured.

## Proposed Ticket Breakdown

Phase 3B is much smaller than the retired Phase 3. Three implementation tickets:

- **EB-XXXa (Phase 3B.1) — Stripe-customer-binding recovery flow.**
  R1-R7. New `/api/recover/email` endpoint, signed-link generation, `/recover/show`
  FastAPI HTML render path, rate limiting, Stripe Customer Search integration,
  no-enumeration UX. Also: lands `web_service/email.py` (Python Resend integration)
  since this is the first non-Worker email send. Optionally lands the `tokens.customer_id`
  column ALTER if the implementer chooses path (b) in Outstanding Questions.
- **EB-XXXb (Phase 3B.2) — Standalone mailing-list signup + double-opt-in.**
  R8-R11. New `subscribers` table, `POST /api/subscribe` endpoint, footer
  `<SubscribeForm />` component, double-opt-in confirmation email + `/subscribe/confirm`
  landing page.
- **EB-XXXc (Phase 3B.3) — Unsubscribe flow + email footer attachment.**
  R12-R13. `/unsubscribe` confirmation interstitial, token rotation on toggle, email
  footer template for all marketing sends (recovery emails excluded). Lightest of the
  three; can ship in parallel with B.2 or after.

Recommended sequencing: 3B.1 (recovery) first since it solves the more-pressing pain
point; 3B.2 and 3B.3 can land in either order or in parallel since they share no code
surface with 3B.1 and minimal overlap with each other.

## Next Steps

→ Run `/document-review` against this requirements doc (per the brainstorming skill's
  Phase 3.5).
→ File the three tickets above under a new EB epic.
→ Run `/ce:plan` to produce the implementation plan.
→ Execute via `/ce:work` (or hand off to Sonnet via a session-handoff prompt).
