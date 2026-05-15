---
title: "EB-248: Visual brand pass on the FastAPI-rendered payment flow"
type: requirements
status: ready-for-planning
date: 2026-05-15
origin: https://jlfowler1084.atlassian.net/browse/EB-248
related:
  - https://jlfowler1084.atlassian.net/browse/EB-233
  - https://jlfowler1084.atlassian.net/browse/EB-240
  - https://jlfowler1084.atlassian.net/browse/INFRA-392
ticket_corrections:
  - "EB-248 description points to `app/checkout/success/page.tsx`; actual file is `web_service/routes/payment.py`. Stripe redirects to `/payment/success`, not `/checkout/success`. Update ticket scope wording before implementation."
---

# EB-248: Visual brand pass on the FastAPI-rendered payment flow

## Reframe

The ticket as filed assumed this was a new Next.js page. Code inspection revealed
the page already exists as **server-rendered FastAPI HTML** at
`web_service/routes/payment.py`. The decision to keep it out of Next.js is
deliberate and load-bearing: tokens are injected into the HTML via a
`<script type="application/json">` two-script pattern so they never enter a
Next.js client-side bundle. Migrating to Next.js would regress a settled
security tradeoff.

EB-233's design system pass explicitly skipped the payment route for this reason.
EB-248 is the follow-up: apply the same brand language to the FastAPI-rendered
flow without compromising the token-security architecture.

## Why this is a baseline test for INFRA-392

This brainstorm and the upcoming implementation are the empirical check on
whether Claude needs a Figma spec to ship on-brand UI. If the work below
produces visual consistency with the rest of leafbind (EB-233/EB-240 brand,
both Done/merged as of 2026-05-15) using only `web-aesthetics` + Playwright
iteration, INFRA-392 stays deferred. If a specific drift incident makes the
build awkward in a way a Figma frame would fix, log it on EB-248 (see AC #6
below) and reactivate INFRA-392.

## Scope

### What this covers

A consistent visual brand pass across **7 templates** in the FastAPI payment
flow, plus a shared CSS approach so future FastAPI-served pages don't have to
rebuild the brand each time:

1. **`/payment/success`** — tokens displayed, downloadable, recoverable. The
   highest-trust moment in the funnel. Needs a tasteful branding moment without
   undermining the utility (the tokens are the product).
2. **`/payment/success` (expired)** — same URL, >7 days post-mint. Soft
   recovery framing, links to `/recover` and `/pricing`.
3. **`/payment/success` (pending)** — `payment_status != "paid"`. Auto-reload
   after 30s. Patience-inducing, not alarming.
4. **`/payment/success` (retry / service-degraded)** — circuit breaker open or
   DB read failure. "Your payment was received; tokens are being generated."
   Auto-reload after 30s. Reassuring but honest.
5. **`/payment/success` (not found, 404)** — Stripe doesn't recognize the
   session. Cool tone, links to `/recover` and `/pricing`.
6. **`/payment/success` (invalid session ID, 422)** — `session_id` doesn't
   start with `cs_`. Polite "URL looks wrong" + recovery link.
7. **`/payment/cancel`** — user backed out of Stripe Checkout, no charge. Easy
   "try again" CTA back to `/pricing`.

### Out of scope

- **Token-security architecture changes.** The `<script type="application/json">`
  + localStorage pattern stays exactly as-is. Brand pass touches presentation,
  not the security model.
- **Stripe Checkout configuration changes** (success_url, cancel_url, line items,
  pricing).
- **Backend logic changes** in `payment.py` (circuit breaker, token minting,
  expiry rules).
- **Token-pack pricing copy.** Pricing live on `/pricing` is owned by EB-243's
  recent repositioning; don't re-litigate it here.
- **Email design** for receipts/confirmations. Stripe receipt emails are
  deliberately disabled (`receipt_email=None`); leafbind doesn't send any
  post-purchase email today. Separate ticket if/when one is needed.
- **Dark mode.** Matches EB-233 light-mode-only scope.

## Design direction (resolved in brainstorm)

| Decision | Choice | Why |
| --- | --- | --- |
| Render path | Keep FastAPI server-side HTML | Token-security architecture; explicit comment in `payment.py` lines 1–16 |
| Token-injection pattern | Unchanged | `<script type="application/json">` + sibling script writes to localStorage |
| Design tokens source | `web_service/frontend/design-tokens.ts` is the canonical reference; FastAPI mirrors them via a strategy selected in planning (manual CSS, build-time generation, or shared JSON export). FastAPI does **not** import the TS module — the security boundary stays intact. | Drift-free mirror approach to be chosen during planning |
| Visual reference | EB-233/EB-240 brand (sand surface, forest accent, Newsreader serif, DM Sans body, IBM Plex Mono mono/eyebrow) | Visual continuity with `/`, `/pricing`, marketing pages |
| Shared shell | Yes — header strip and footer matching the Next.js shell | Cross-page consistency; users won't notice the rendering boundary |
| State differentiation | Each of the 7 templates gets its own micro-treatment within the shared shell | Success-vs-pending-vs-error tone requires different visual weight |

## Acceptance criteria

(Renumbered to add SEC-003 / SEC-004 corrections from document review. Original
6 ACs became 10; AC #6 — drift-incident log — is preserved in place.)

1. All 7 templates render with the EB-233/EB-240 brand language: sand-based
   surface, forest-green accents, the project type stack (Newsreader serif,
   DM Sans body, IBM Plex Mono for eyebrows/code/tokens), matching radii and
   shadows from `design-tokens.ts`. EB-233 is Done; EB-240 merged to master
   2026-05-15 (commit 5a798e0). If either becomes unstable mid-implementation,
   planning pauses until the brand reference is fixed again.
2. Shared CSS approach implemented — a single source of truth for color, type,
   spacing, shadow, radii values consumed by the FastAPI templates. Approach
   selected during planning (manual mirror vs build-time generation vs another
   option). No hardcoded hex values inside Python string literals; all visual
   values go through CSS variables.
3. Token rendering on the success page preserves the existing security
   architecture exactly — `<script type="application/json">` block, sibling
   `<script>` that parses and writes to localStorage, no token strings in any
   JS string interpolation. Test by inspecting the rendered HTML and confirming
   no token appears anywhere outside the JSON payload.
4. Visual review against the `web-aesthetics` skill's "AI slop" checklist passes
   on each of the 7 templates (skill at `~/.claude/skills/web-aesthetics/SKILL.md`).
   Specifically: no gradient meshes, no generic glassmorphism, no aggressive CTAs,
   restrained motion (no eager spinners or progress bars on the pending/retry
   auto-reload states). AC #1's brand requirements apply uniformly to all 7
   templates including both the fresh success state and the expired-token variant.
5. Responsive behavior at mobile (375px) and desktop (1280px) breakpoints —
   Playwright screenshots of each of the 7 states in the PR description.
6. **Drift-incident log.** If during this work Claude generated something
   off-brand that was hard to fix without a visual spec (a Figma frame), record
   the specific failure mode in EB-248's Jira comments before close. This is
   the evidence that either reactivates INFRA-392 or confirms it stays deferred.
   Absence of such a log is itself a valid signal — record "no drift incidents
   observed" if that's the case.
7. No backend behavior changes — `payment.py` route logic, token mint flow,
   circuit breaker, and expiry rules behave identically. Verify by running
   the existing comprehensive test suite at `tests/test_web_payment.py`
   (covers all 7 states plus `TestXSSInjectionGuards` for the
   `<script type="application/json">` pattern); all tests pass before and after.
8. **Response headers preserved on every template.** All 7 templates return
   `Referrer-Policy: no-referrer` and `Cache-Control: private, no-store` —
   the headers currently set by `_PAYMENT_HEADERS` in `payment.py`. Verify in
   the Playwright smoke test by inspecting response headers, not just rendered
   HTML. A brand-pass refactor that drops these headers from any template is
   a regression that fails this AC.
9. **`session_id` HTML-escaped in all non-success templates.** The current
   `_render_expired_page`, `_render_retry_page`, `_render_pending_page`, and
   `_render_not_found_page` reflect `session_id` directly via Python f-strings
   (e.g., `f'<p>Session: {session_id}</p>'`). The `cs_` prefix check is not
   sufficient — a crafted URL `?session_id=cs_<script>...` bypasses the prefix
   check. This brand pass fixes that latent XSS by wrapping every reflected
   `session_id` in `html.escape()`. Add a regression test asserting this in
   `tests/test_web_payment.py`.
10. Manual smoke test: fire a Stripe test-mode checkout, confirm the redirect
    lands on the rebranded success page and tokens display correctly. Record
    in the PR description.

## State-specific design notes

These belong in planning, but capture the spirit here so the design pass
doesn't flatten all 7 states into the same treatment:

- **Success**: highest trust moment. Brand moment + tokens in a readable
  monospace block + obvious download/print actions + a CTA back to `/` (start
  converting). Bookmark callout stays; rephrase warmly.
- **Expired**: not a failure — a recovery moment. Reframe the URL as "old
  receipt," surface `/recover` and `/pricing` as parallel paths forward.
- **Pending**: reassuring. Show what's happening (Stripe is confirming,
  tokens are minting). The auto-reload happens silently every 30s. Consider
  a subtle animation that signals "still working" without spinning eagerly.
- **Retry**: similar to pending but with a soft "we're catching up" framing.
  Avoid alarm language; the user has already paid.
- **Not found** (404): polite, not punishing. The URL might be old or typo'd.
  Surface `/recover` and `/pricing` clearly.
- **Invalid session ID** (422): same tone as not-found, but with a one-liner
  about the URL shape. Avoid technical jargon (don't say "starts with `cs_`"
  in user copy).
- **Cancel**: friendly. The user chose to back out — don't make them feel bad.
  Emphasize "no charge made" and offer a clear path back to `/pricing`.

## Open questions for planning

- **Shared CSS strategy:** Three plausible options:
  (a) Manual `web_service/static/leafbind-payment.css` mirroring tokens by hand
      (~30 min one-time + drift risk),
  (b) Build-time generation script that reads `design-tokens.ts` and emits CSS
      (~1 hr one-time + zero drift),
  (c) A runtime read of a shared `tokens.json` from both Next.js (via import)
      and FastAPI (via file read) — requires extracting tokens from .ts to .json
      as a separate step.
  Pick during planning. Default: build-time generation, since recent history
  (EB-240) shows tokens change at least once per design ticket.
- **Static asset path.** Where does the shared CSS live and how is it served?
  FastAPI does not currently serve static files from `web_service/`. Either
  add a static-file mount, host the CSS inline in `<style>` blocks, or
  serve it through Next.js + reference from FastAPI HTML with an absolute URL
  (introduces a request between two services for a brand-only asset).
- **Header/footer shared shell mechanism.** Should the FastAPI templates link
  to the Next.js header/footer URL via iframe (no — bad), embed it via a
  build-time snippet (yes, manageable), or maintain a hand-mirrored copy
  (drift risk)?
- **Test fixtures (resolved).** `tests/test_web_payment.py` already exists with
  comprehensive coverage: `TestPaymentSuccessHappyPaths`,
  `TestPaymentSuccessEdgeCases`, `TestPaymentSuccessErrorPaths`,
  `TestPaymentSuccessCircuitBreaker`, `TestPaymentCancel`,
  `TestXSSInjectionGuards`, `TestResponseHeaders`, `TestGetTokensForSession`.
  All 7 states are already exercised via `fastapi.testclient.TestClient`.
  The brand pass should extend this harness with new HTML assertions
  (no hardcoded hex, expected CSS-variable references, response headers
  per AC #8) rather than write a parallel test runner.
- **`check-token-drift.mjs` scope expansion.** The existing token-drift guard
  at `web_service/frontend/tools/check-token-drift.mjs` watches
  `design-tokens.ts` vs `app/globals.css`. The new FastAPI CSS file is a third
  consumer that needs to be added to that guard — otherwise the next token
  bump after EB-248 silently desyncs the payment flow. Plan must include the
  guard delta as a concrete deliverable.

## Success criteria

- The 7 payment-flow templates feel visually continuous with `/`, `/pricing`,
  `/quality`, and the marketing pages.
- Token-security architecture is preserved with zero regressions.
- A future ticket that adds an 8th payment-flow state (or a different FastAPI
  HTML surface) can reuse the shared CSS approach without re-deciding the
  brand mirror question.
- EB-248 AC #6 either logs a concrete Figma-justifying drift incident or
  records "no drift observed" — giving INFRA-392 a real signal either way.

## References

- `web_service/routes/payment.py` — the file being redesigned
- `web_service/routes/checkout.py` — defines the Stripe `success_url`
- `web_service/routes/webhook.py` — verifies and processes Stripe events
- `web_service/token_store.py` — token mint + read flow (do not modify)
- `web_service/frontend/design-tokens.ts` — token source of truth
- `docs/plans/2026-05-14-002-feat-eb233-leafbind-design-system-plan.md` —
  EB-233 plan that established the Next.js brand
- `docs/brainstorms/2026-05-15-infra392-figma-mcp-setup-requirements.md` —
  deferred Figma ticket this work tests against
- `docs/solutions/best-practices/test-baseline-before-investing-in-tooling-2026-05-15.md` —
  the decision pattern this ticket validates
