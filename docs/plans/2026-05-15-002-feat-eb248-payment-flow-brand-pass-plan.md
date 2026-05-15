---
title: "feat: EB-248 — Visual brand pass on the FastAPI-rendered payment flow"
type: feat
status: active
date: 2026-05-15
origin: docs/brainstorms/2026-05-15-eb248-stripe-payment-flow-design-pass-requirements.md
---

# feat: EB-248 — Visual brand pass on the FastAPI-rendered payment flow

## Overview

Apply the EB-233/EB-240 brand language to the 7 server-rendered HTML templates
in `web_service/routes/payment.py`. Establish a shared CSS pipeline so future
FastAPI-rendered pages can consume the same design tokens that the Next.js
marketing site uses, without coupling the two deploy units. Fix a pre-existing
XSS in `session_id` reflection while we're touching the templates. Preserve
the token-security architecture exactly.

## Problem Frame

The payment flow's 7 templates (success, expired, pending, retry, not-found,
invalid-session, cancel) render with inline styles defined as Python f-strings.
They look unmistakably "Phase 1" — system fonts, blue Vercel-style links,
basic margins. A paying user lands here right after handing over money; the
brand discontinuity undermines the trust moment.

EB-233 explicitly skipped these routes because they're deliberately FastAPI-rendered
(not Next.js) for token-security reasons: tokens are injected via a
`<script type="application/json">` block so they never enter a Next.js client
bundle. EB-248 is the follow-up brand pass.

It is also the empirical baseline test for INFRA-392 (Figma MCP deferred 2026-05-15):
if we ship this on-brand using `web-aesthetics` + Playwright iteration with no
drift incident, INFRA-392 stays deferred. AC #6 captures the evidence either way.

## Requirements Trace

From the origin doc (`docs/brainstorms/2026-05-15-eb248-stripe-payment-flow-design-pass-requirements.md`):

- **R1.** All 7 templates render with the EB-233/EB-240 brand (sand surface,
  forest accent, Newsreader serif, DM Sans body, IBM Plex Mono mono/eyebrow).
- **R2.** Shared CSS approach with single source of truth (`design-tokens.ts`).
- **R3.** Token-injection security architecture preserved exactly.
- **R4.** `web-aesthetics` AI-slop checklist passes (no spinners, no gradient
  meshes, no glassmorphism, no aggressive CTAs).
- **R5.** Mobile (375px) + desktop (1280px) responsive, Playwright evidence.
- **R6.** Drift-incident log on Jira EB-248 (or "no drift observed") —
  evidence path back to INFRA-392.
- **R7.** No backend logic changes — all existing tests in
  `tests/test_web_payment.py` continue to pass.
- **R8.** Existing `_PAYMENT_HEADERS` (Referrer-Policy: no-referrer,
  Cache-Control: private, no-store) preserved on all 7 templates.
- **R9.** Pre-existing XSS in `session_id` reflection fixed via `html.escape()`.

## Scope Boundaries

- No backend logic changes in `payment.py` route handlers.
- No changes to the Stripe Checkout configuration (success_url, cancel_url,
  line items).
- No migration of the page to Next.js — the FastAPI-served HTML pattern stays.
- No new product features. Visual + security-fix only.
- No changes to `token_store.py`, circuit breaker, or token TTL.
- No dark mode (matches EB-233 light-mode-only scope).

### Deferred to Separate Tasks

- Stripe post-purchase email design — separate ticket (co-deferred with the
  page in EB-233).
- Full marketing nav on the payment-flow shell — kept intentionally minimal
  (logo + footer copy only). If a richer shell becomes useful for payment
  pages, file separately.

## Context & Research

### Relevant Code and Patterns

- `web_service/routes/payment.py` — the file being redesigned. 7 `_render_*`
  helpers + 2 route handlers + `_PAYMENT_HEADERS` constant + `_base_html`
  shell function (lines 56–71).
- `web_service/main.py` — FastAPI app entry point. No `StaticFiles` mount
  exists today; one will be added.
- `web_service/frontend/design-tokens.ts` — TypeScript module exporting
  `colors` (9 keys), `type` (3 font families + 7 size scales), `space`
  (8 keys), `shadows` (3 keys), `radii` (2 keys).
- `web_service/frontend/tools/check-token-drift.mjs` — existing Node script
  that validates `design-tokens.ts` `colors` against `globals.css :root`.
  Pattern to follow + extend.
- `web_service/frontend/components/Header.tsx` + `Footer.tsx` — current
  Next.js shell. Tiny: logo + 3 nav links in the header (Convert / Pricing /
  Quality). Footer is comparably small.
- `web_service/frontend/app/globals.css` — current CSS variables. Reference
  for the same variable shape the FastAPI CSS will export.
- `tests/test_web_payment.py` — comprehensive existing test suite:
  `TestPaymentSuccessHappyPaths`, `TestPaymentSuccessEdgeCases`,
  `TestPaymentSuccessErrorPaths`, `TestPaymentSuccessCircuitBreaker`,
  `TestPaymentCancel`, `TestXSSInjectionGuards`, `TestResponseHeaders`,
  `TestGetTokensForSession`. Extend this; do not write a parallel runner.

### Institutional Learnings

- `docs/solutions/best-practices/test-baseline-before-investing-in-tooling-2026-05-15.md`
  — the decision pattern this work validates.
- `docs/plans/2026-05-14-002-feat-eb233-leafbind-design-system-plan.md`
  — the EB-233 plan that established the Next.js brand and shipped the
  token system this plan mirrors.

### External References

None required. All decisions are grounded in existing repo patterns.

## Key Technical Decisions

### D1. Shared CSS via build-time generation, committed to git

A new Node script at `web_service/frontend/tools/gen-fastapi-css.mjs`
reads `design-tokens.ts` and emits
`web_service/static/leafbind-tokens.css`. Runs in the same `prebuild` step
as `check-token-drift.mjs`. The generated CSS is **committed to git** (not
generated at runtime) so:
- The CSS is diff-reviewable in PRs.
- FastAPI doesn't need a Node runtime on the deploy VM.
- The two deploy units (Vercel for Next.js, Hetzner for FastAPI) stay
  decoupled — the shared artifact lives in the git tree, not in a build
  pipeline both must run.

**Rationale:** Alternatives considered: (a) manual CSS file with no
generation — drift risk too high given recent token-change cadence (EB-240
changed 3 token values within days of EB-233 shipping); (c) inline `<style>`
blocks in Python — duplicates token CSS into every response, breaks browser
caching for what should be a static asset. Build-time generation with a
committed artifact threads the needle.

### D2. FastAPI `StaticFiles` mount at `/static/`

Add `app.mount("/static", StaticFiles(directory="web_service/static"),
name="static")` to `web_service/main.py`. The brand CSS is served at
`/static/leafbind-tokens.css`. The mount is greenfield — no prior static-file
serving exists in FastAPI today.

### D3. Per-endpoint cache policy split

The brand CSS is **not** user-specific. It carries
`Cache-Control: public, max-age=3600, immutable` (set via the static-file
mount or a one-line middleware). The HTML payment-flow pages keep their
existing `Cache-Control: private, no-store` — token-bearing responses must
not be cached. The two endpoints live at different paths, so there is no
conflict.

**Rationale:** Brand CSS is reusable, low-sensitivity, and benefits from CDN
caching. Token-bearing HTML must never be cached. Separating policies by
endpoint is correct; applying the strict policy to brand CSS would
unnecessarily punish performance.

### D4. Shell as a hand-mirrored Python module, not a build-rendered Next.js fragment

A new module `web_service/templates/shell.py` exports `header_html()` and
`footer_html()` returning plain HTML strings. The 7 payment templates
compose these via `_base_html`. The payment-flow shell is intentionally
**minimal** — just the leafbind logo + footer copy (no Convert/Pricing/Quality
nav). A user mid-payment doesn't need the marketing nav.

**Rationale:** Three options considered:
- (a) Render the Next.js `Header.tsx`/`Footer.tsx` to static HTML at build
  time — adds React-SSR-to-static-HTML tooling that doesn't exist in this
  repo, overkill for a one-page-deep shell.
- (b) Cross-service include — couples the two deploy units at runtime.
- (c) Hand-mirror in Python — drift risk acknowledged.

The minimality of the payment-flow shell (logo + footer copy, no nav) makes
hand-mirroring trivially correct. A CI check (added in Unit 1) compares
text content of the shell against the React components to catch drift.

### D5. Trust-moment treatment on `/payment/success` (happy path)

Specific to settle the design-lens F-04 finding:
- **Eyebrow** above headline: `<span class="lb-eyebrow">PAYMENT CONFIRMED</span>`
  in IBM Plex Mono, uppercase, tracked letter-spacing — reuses the EB-240
  eyebrow pattern.
- **Headline**: `<h1 class="lb-display">Welcome to Leafbind.</h1>` in
  Newsreader serif at the display scale.
- **Body explanation** in DM Sans, normal weight.
- **Token block**: monospaced (IBM Plex Mono) on `--color-surface-muted`
  background with a `--color-accent` 1px border-left, generous padding.
- **Action row**: primary "Download tokens.txt" button on `--color-brand`
  with sand text; ghost "Print" button; tertiary "Start converting →" link.
- **No illustration, no big-logo-at-top-of-body** (logo lives in the shell
  header, doesn't need to duplicate). Brand trust comes from typography
  and palette, not iconography.

### D6. Pending/retry animation: pulsing eyebrow opacity

Specific to settle the design-lens F-06 finding:
- The eyebrow on `_render_pending_page` reads `<span class="lb-eyebrow lb-pulse">PROCESSING</span>`.
- CSS: `.lb-pulse { animation: lb-pulse 2s ease-in-out infinite; }` and
  `@keyframes lb-pulse { 0%, 100% { opacity: 0.5; } 50% { opacity: 1; } }`.
- `@media (prefers-reduced-motion: reduce) { .lb-pulse { animation: none; opacity: 1; } }`.
- No spinner, no progress bar, no skeleton. Plex Mono eyebrow is the brand's
  rhythm element; pulsing it signals "still working" using brand vocabulary.
- Retry page reuses the same animation with copy `CATCHING UP` instead of
  `PROCESSING`.

### D7. Information architecture per template

Top-to-bottom order (all templates use the shared shell):

| Template | Body order |
|---|---|
| Success | eyebrow `PAYMENT CONFIRMED` → headline → bookmark callout → token block → action row → "Start converting →" |
| Expired | eyebrow `TOKENS EXPIRED` → headline → explanation → recovery CTAs (recover / pricing) → session ID (small, muted) |
| Pending | eyebrow `PROCESSING` (pulsing) → headline → "Stripe is confirming; auto-refreshes in 30s" → session ID |
| Retry | eyebrow `CATCHING UP` (pulsing) → headline → reassurance → session ID |
| Not found | eyebrow `SESSION NOT FOUND` → headline → explanation → recovery CTAs → session ID |
| Invalid session | eyebrow `INVALID URL` → headline → polite "URL looks wrong" → recovery CTAs |
| Cancel | eyebrow `PAYMENT CANCELLED` → headline → "no charge made" → CTA back to /pricing → recover link |

Eyebrow text is consistent: uppercase, Plex Mono, tracked, in
`--color-text-muted` (or `--color-accent` for the success state).

### D8. Pre-existing XSS fix via `html.escape()`

Every reflection of `session_id` (or any user-controlled value) into HTML
goes through `html.escape(value, quote=True)` from the standard library.
Currently four helpers (`_render_expired_page`, `_render_retry_page`,
`_render_pending_page`, `_render_not_found_page`) reflect `session_id`
directly via Python f-strings. All four are fixed in this work. A new
test in `tests/test_web_payment.py` asserts that a crafted
`session_id=cs_<script>alert(1)</script>` is escaped in the rendered HTML.

## Open Questions

### Resolved During Planning

- Where does the shared CSS live? → `web_service/static/leafbind-tokens.css`,
  served by a new `StaticFiles` mount (D1, D2).
- Manual vs build-time generation? → Build-time, committed (D1).
- Shell mechanism? → Hand-mirrored Python module with CI text-content check (D4).
- Trust-moment treatment? → Eyebrow + Newsreader headline + monospaced token
  block (D5).
- Pending animation idiom? → Pulsing eyebrow opacity (D6).
- IA order per template? → See D7 table.
- Cache policy split? → CSS public, HTML private (D3).

### Deferred to Implementation

- Exact Newsreader font-weight for the display headline — depends on how the
  font renders at the actual sizes used. Pick during visual iteration with
  the `design-iterator` agent.
- Exact button corner radius — `--radius-sm` or `--radius-md`. Try both at
  Playwright screenshot time, pick the one that reads more "polished paid
  product" vs "casual web form."
- Whether the bookmark callout uses a left-border accent or a top-border
  accent — visual iteration call.

## Implementation Units

### Unit 1: Shared CSS pipeline + StaticFiles mount + drift-guard extension

- [ ] **Goal:** Stand up the build-time CSS generation, the FastAPI static
  mount, and the drift-guard coverage for the new surface.

**Requirements:** R1, R2

**Dependencies:** None.

**Files:**
- Create: `web_service/frontend/tools/gen-fastapi-css.mjs`
- Create: `web_service/static/leafbind-tokens.css` (committed; generator output)
- Modify: `web_service/frontend/tools/check-token-drift.mjs` — add a third
  surface check (generated CSS).
- Modify: `web_service/frontend/package.json` — `prebuild` runs both
  scripts.
- Modify: `web_service/main.py` — add `app.mount("/static", StaticFiles(...), name="static")`.
- Modify: `web_service/frontend/tools/README.md` (if present) — note the new
  script. If not present, skip.
- Test: `tests/test_web_static.py` — new file: GET `/static/leafbind-tokens.css`
  returns 200 with `Cache-Control: public, max-age=3600`.
- Test: `tests/test_web_payment.py` — no changes in this unit.

**Approach:**
- The generator reads `design-tokens.ts` using the same regex pattern as
  `check-token-drift.mjs`. Extract `colors`, `type` (size scale only —
  font-family vars are intentionally not in the CSS since they're injected
  by Next.js `next/font`; FastAPI uses Google Fonts CSS link or equivalent
  per a small decision in this unit), `space`, `shadows`, `radii`.
- Emit a `:root { ... }` block with CSS variables matching the pattern in
  `globals.css` so the variable names line up (`--color-brand`,
  `--space-4`, `--shadow-md`, etc.).
- Also emit a small set of utility classes: `.lb-eyebrow`, `.lb-display`,
  `.lb-body`, `.lb-pulse`, `.lb-card`, `.lb-button-primary`, `.lb-button-ghost`,
  `.lb-link`. These are the brand primitives consumed by the 7 templates
  in Units 3–5.
- The drift-guard extension reads the generated CSS, builds a third Map,
  and validates 3-way: `design-tokens.ts` ⇔ `globals.css` ⇔
  `leafbind-tokens.css`. Same Map-diff pattern as the existing script.
- Font loading for FastAPI HTML: include a `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader&family=DM+Sans&family=IBM+Plex+Mono&display=swap">` in `_base_html`. Cheaper than self-hosting; cache hit likely from Next.js's `next/font` having already loaded them on /pricing.

**Execution note:** Test-first for the static-file serving check —
write `tests/test_web_static.py` before adding the mount, so the failing
test drives the mount addition.

**Patterns to follow:**
- `web_service/frontend/tools/check-token-drift.mjs` for the regex parsing
  and Map-diff pattern.
- `web_service/main.py` for how routers and middleware are wired today.

**Test scenarios:**
- Happy path: GET `/static/leafbind-tokens.css` returns 200, body contains
  `--color-brand: #2f5d3a` (the actual current brand value).
- Happy path: response includes `Cache-Control: public, max-age=3600`.
- Edge case: GET `/static/missing-file.css` returns 404.
- Drift guard: when `design-tokens.ts` declares a color key that the
  generated CSS doesn't emit, `check-token-drift.mjs` exits non-zero.
- Drift guard: when generated CSS has a `--color-*` variable not in
  `design-tokens.ts`, the script exits non-zero.

**Verification:**
- `npm run prebuild` from `web_service/frontend/` runs both scripts to
  completion with zero drift output.
- `pytest tests/test_web_static.py` passes.
- The committed `web_service/static/leafbind-tokens.css` is human-readable
  and reviewable in the PR diff.

---

### Unit 2: Shell module (`shell.py`) + CI text-content drift check

- [ ] **Goal:** Define the payment-flow shell as a Python module the 7
  templates compose, with a guard against drift from the Next.js shell.

**Requirements:** R1

**Dependencies:** Unit 1 (the CSS that the shell references).

**Files:**
- Create: `web_service/templates/__init__.py`
- Create: `web_service/templates/shell.py` — exports `header_html()` and
  `footer_html()`.
- Create: `web_service/frontend/tools/check-shell-drift.mjs` — compares the
  Python shell's link text and logo path against `Header.tsx` and `Footer.tsx`.
- Modify: `web_service/frontend/package.json` — `prebuild` runs the shell
  drift check.
- Test: `tests/test_web_shell.py` — new file: `header_html()` and
  `footer_html()` return well-formed HTML containing the expected brand
  text and an inline-SVG logo.

**Approach:**
- `header_html()` returns: `<header class="lb-header"><a href="/" aria-label="leafbind home"><svg ...logo paths...></svg></a></header>` — intentionally no nav. Payment-flow users don't need Convert/Pricing/Quality mid-payment.
- `footer_html()` returns minimal copy + a `/pricing` link + a `/recover`
  link. Plain text + `.lb-link` class.
- The logo SVG is inline (no external request). Same paths as `web_service/frontend/components/Logo.tsx`.
- `check-shell-drift.mjs` reads the Python module and the React files,
  extracts (a) the logo SVG `<path d="..." />` values and (b) the visible
  link text. Asserts both sides match. Exits non-zero on drift.

**Execution note:** Test-first — write the shell test first to anchor the
expected HTML output.

**Patterns to follow:**
- `web_service/frontend/components/Header.tsx` for the visual layout.
- `check-token-drift.mjs` for the Node-side drift-check pattern.

**Test scenarios:**
- Happy path: `header_html()` returns a string containing
  `<a href="/" aria-label="leafbind home">` and an `<svg` element.
- Happy path: `footer_html()` returns a string containing
  `<a href="/pricing"` and `<a href="/recover"`.
- Happy path: both return well-formed HTML (parseable by an HTML parser
  without errors).
- Drift: if `Header.tsx` `aria-label` changes from "leafbind home" to
  something else, `check-shell-drift.mjs` exits non-zero.

**Verification:**
- `pytest tests/test_web_shell.py` passes.
- `node web_service/frontend/tools/check-shell-drift.mjs` exits 0.

---

### Unit 3: Brand pass + security fixes on `_render_success_page` + `_base_html`

- [ ] **Goal:** Refactor `_base_html` to consume the new CSS + shell, then
  rebrand the success page (highest-trust template). Also fix the
  pre-existing XSS in `session_id` reflection.

**Requirements:** R1, R3, R4, R8, R9

**Dependencies:** Unit 1, Unit 2.

**Files:**
- Modify: `web_service/routes/payment.py` — refactor `_base_html` to:
  - Replace inline-style `<body>` with class-based styling using the new CSS.
  - Include `<link rel="stylesheet" href="/static/leafbind-tokens.css">`.
  - Include the Google Fonts link from Unit 1.
  - Inject `header_html()` and `footer_html()` from the shell module.
  - Wrap the body in a `<main class="lb-main">` so layout CSS can target it.
- Modify: `_render_success_page` — rebuild markup with brand classes:
  `lb-eyebrow`, `lb-display`, token block in `lb-card`, action row with
  `lb-button-primary` + `lb-button-ghost`.
- Modify: All four helpers that reflect `session_id` (`_render_expired_page`,
  `_render_retry_page`, `_render_pending_page`, `_render_not_found_page`)
  — wrap every `{session_id}` reflection in `html.escape(session_id, quote=True)`.
  In this unit, only `_render_success_page` is rebranded; the other helpers
  get the security fix and remain visually unchanged until Units 4–5.
- Modify: `web_service/routes/payment.py` — add `from html import escape` at
  the top.
- Modify: `tests/test_web_payment.py` — extend `TestXSSInjectionGuards`
  with the new session_id XSS regression test.

**Approach:**
- The `<script type="application/json">` block stays exactly as-is — it's
  the load-bearing security architecture. No change to the
  token-injection JSON payload, only to the surrounding HTML.
- The token list `<ol id="token-list">` becomes `<ol class="lb-token-list">`
  inside an `<div class="lb-card lb-token-card">` wrapper.
- The "bookmark this page" callout becomes a `<aside class="lb-callout">`
  with the warm rephrasing per origin doc.
- All hardcoded `#0070f3` and other inline color values are removed.
- The `<button onclick="downloadTokens()">` calls remain — JS download
  helper is unchanged; just restyle the buttons with `lb-button-*` classes.

**Execution note:** **Test-first** for the security regression. Write the
XSS test that fails against current code, then apply `html.escape()`. This
is exactly the kind of latent issue where a failing test before the fix
prevents regression.

**Patterns to follow:**
- The existing `_render_success_page` `<script type="application/json">`
  pattern stays exactly.
- `web_service/frontend/app/(marketing)/page.tsx` for visual reference —
  same brand applied to a Next.js page.

**Test scenarios:**
- Happy path: `GET /payment/success?session_id=cs_test123` with mocked
  cached tokens renders HTML containing `lb-eyebrow`, `lb-display`,
  `lb-token-list`, `lb-button-primary`.
- Happy path: rendered HTML includes `<link rel="stylesheet" href="/static/leafbind-tokens.css">`.
- Happy path: response headers still include `Referrer-Policy: no-referrer`
  and `Cache-Control: private, no-store` (R8).
- Security: `GET /payment/success?session_id=cs_<script>alert(1)</script>`
  is rejected by the prefix validator (422). The 422 response renders
  invalid-session-id HTML with `&lt;script&gt;` escaped, not as raw HTML.
  (This is the XSS regression case for the prefix-bypass attempt.)
- Security: any session_id that does pass the prefix check but contains
  HTML special characters reflects as escaped — e.g.,
  `?session_id=cs_test<img onerror=alert(1)>` if it reached `_render_*_page`,
  the rendered output would contain `&lt;img onerror=...&gt;`, not
  executable HTML.
- Security: the existing `TestXSSInjectionGuards` `<script type="application/json">`
  pattern still passes — token JSON encoding unchanged.
- Integration: `TestPaymentSuccessHappyPaths` (all 3 packs) still passes
  after the markup refactor.

**Verification:**
- `pytest tests/test_web_payment.py -v` — all classes pass.
- Manual: load `/payment/success?session_id=cs_<fixture>` in a browser,
  confirm the rebrand looks like the marketing pages.

---

### Unit 4: Auto-reload state templates (`_render_pending_page`, `_render_retry_page`)

- [ ] **Goal:** Rebrand the two auto-reload states with the pulsing
  eyebrow animation. Keep the auto-reload script behavior.

**Requirements:** R1, R4

**Dependencies:** Unit 1, Unit 2, Unit 3 (which fixes the session_id XSS
in these helpers).

**Files:**
- Modify: `web_service/routes/payment.py` — rewrite `_render_pending_page`
  and `_render_retry_page` body HTML to use brand classes including the
  `lb-eyebrow lb-pulse` combination on the eyebrow text.

**Approach:**
- The inline `<script>setTimeout(window.location.reload, 30000)</script>`
  stays — it's the auto-reload behavior, not a visual concern.
- The eyebrow is the only animated element. Headline + body copy +
  session ID are static.
- Pending uses `PROCESSING` eyebrow. Retry uses `CATCHING UP`. Different
  copy in the body but same animation idiom.
- Add `aria-live="polite"` to the headline element so screen readers
  announce state changes if the page content updates without a full reload.
- The reduced-motion media query in the CSS (Unit 1) means the animation
  is automatically disabled for users with that preference. No additional
  JS needed.

**Patterns to follow:**
- Unit 3's `_render_success_page` rewrite for the markup pattern.
- The animation CSS lives in `leafbind-tokens.css` (emitted by Unit 1).

**Test scenarios:**
- Happy path: `_render_pending_page` output contains
  `<span class="lb-eyebrow lb-pulse">PROCESSING</span>`.
- Happy path: `_render_retry_page` output contains
  `<span class="lb-eyebrow lb-pulse">CATCHING UP</span>`.
- Happy path: both outputs contain the auto-reload `<script>setTimeout(...)</script>` block.
- Edge case: both outputs include `aria-live="polite"` on the headline.
- Security: session_id reflected in both pages is escaped (from Unit 3).
- Integration: `TestPaymentSuccessEdgeCases` `unpaid` case (which routes
  to pending) still passes.
- Integration: `TestPaymentSuccessErrorPaths` `stripe_down` case (which
  routes to retry) still passes.

**Verification:**
- `pytest tests/test_web_payment.py -v` — all classes pass.
- Manual: trigger the pending state in a browser (use a real test-mode
  Stripe session that hasn't been confirmed yet), confirm the eyebrow
  pulses smoothly.

---

### Unit 5: Error/recovery state templates (`_render_expired_page`, `_render_not_found_page`, `_render_invalid_session_page`, `_render_cancel_page`) + extract invalid-session-id helper

- [ ] **Goal:** Rebrand the 4 remaining states. Also extract the inline
  invalid-session-id HTML (currently inlined in the route handler) into a
  proper `_render_invalid_session_page` helper for parity with the rest.

**Requirements:** R1, R4

**Dependencies:** Unit 1, Unit 2, Unit 3 (for the session_id escape pattern
that's already applied).

**Files:**
- Modify: `web_service/routes/payment.py`:
  - Rewrite `_render_expired_page`, `_render_not_found_page`,
    `_render_cancel_page` with brand classes.
  - Extract the invalid-session-id HTML from the `payment_success` route
    handler (currently lines 234–244) into a new
    `_render_invalid_session_page(session_id)` helper.
  - Update the route handler to call the new helper.

**Approach:**
- All four templates use the same shell + brand structure as Units 3 and 4.
- Eyebrow text per D7 IA table: `TOKENS EXPIRED`, `SESSION NOT FOUND`,
  `INVALID URL`, `PAYMENT CANCELLED`.
- Recovery CTAs (recover, pricing) styled as `lb-button-ghost` or
  `lb-link` depending on visual hierarchy — pick during iteration.
- The session-id display (small, muted) goes in a `<p class="lb-session-id">`
  at the bottom. `html.escape(session_id, quote=True)` per Unit 3.

**Patterns to follow:**
- Units 3 and 4 markup pattern.

**Test scenarios:**
- Happy path: each of the 4 helpers returns HTML containing the expected
  eyebrow text and the shared shell HTML.
- Happy path: each helper's HTML uses brand classes (no hardcoded hex).
- Edge case: `_render_invalid_session_page` is called from the route
  handler when session_id doesn't start with `cs_` — test verifies the
  route returns 422 + the new template.
- Security: session_id reflections in all 4 templates are escaped.
- Integration: `TestPaymentSuccessEdgeCases` `expired_tokens`,
  `malformed_session_id` still pass.
- Integration: `TestPaymentCancel` still passes.

**Verification:**
- `pytest tests/test_web_payment.py -v` — all classes pass.
- Manual: load each state in a browser by constructing the URLs and
  exercising the conditions (or stubbing them).

---

### Unit 6: Playwright responsive smoke test + drift-incident log + PR description compilation

- [ ] **Goal:** Capture mobile + desktop screenshots for all 7 templates as
  AC #5 / R5 evidence. Run the existing test suite to confirm zero
  regressions. Write the PR description including the drift-incident log
  per AC #6 / R6.

**Requirements:** R5, R6, R7

**Dependencies:** Units 1–5.

**Files:**
- Create: `web_service/frontend/tools/screenshot-payment-flow.mjs` — a
  small Playwright script that loads each of the 7 states (via fixtures
  or directly-constructed URLs against a local instance) and saves
  PNG screenshots to a `.screenshots/eb-248/` directory.
- Modify: `.gitignore` — add `.screenshots/` (these are PR artifacts, not
  committed).
- Test: no new test file. This unit is the **verification** unit.

**Approach:**
- The screenshot script starts a local uvicorn instance against a test
  DB, seeds tokens for a known session_id, then visits each of the
  7 templates at both 375px and 1280px viewports.
- 14 PNGs total (7 states × 2 widths). Uploaded to the PR description
  as evidence.
- The drift-incident log per AC #6 is captured in the PR description
  as a section titled "INFRA-392 drift evidence" — explicitly says either
  "no drift incidents observed during this work" OR lists the specific
  pattern that was hard to fix without a visual spec.
- Final pre-merge: run the full `pytest tests/test_web_payment.py`
  + the new `test_web_static.py` + `test_web_shell.py` — every test
  green.

**Patterns to follow:**
- Any existing Playwright invocation pattern in the repo. (Per Phase 1
  scan, the Playwright plugin is enabled at project scope but no existing
  screenshot script exists — this is the first one.)

**Test scenarios:**
- Verification only — no test file added.
- Screenshot output exists for all 14 combinations.
- Existing test suite passes:
  `TestPaymentSuccessHappyPaths`, `TestPaymentSuccessEdgeCases`,
  `TestPaymentSuccessErrorPaths`, `TestPaymentSuccessCircuitBreaker`,
  `TestPaymentCancel`, `TestXSSInjectionGuards`, `TestResponseHeaders`,
  `TestGetTokensForSession`, `TestPaymentSuccessHappyPaths` (success state),
  `test_web_static.py` (Unit 1), `test_web_shell.py` (Unit 2).
- Lighthouse run on the deployed success page in test mode meets or
  improves on the EB-230 Unit 9 baseline.

**Verification:**
- 14 PNG screenshots exist under `.screenshots/eb-248/`.
- All tests green.
- PR description includes the drift-incident log and the screenshot
  evidence.

## System-Wide Impact

- **Interaction graph:** New `/static/*` route on FastAPI app. New
  `web_service/templates/` Python package. New `web_service/static/`
  directory served by FastAPI.
- **Error propagation:** Unchanged. The brand pass touches presentation
  only; error paths in `payment.py` still produce the same HTTP status
  codes and redirect targets.
- **State lifecycle risks:** None. Token mint, expiry, and recovery flows
  are untouched.
- **API surface parity:** `GET /payment/success`, `GET /payment/cancel`
  URLs and response shapes unchanged. Only HTML markup and CSS change.
- **Integration coverage:** Existing `tests/test_web_payment.py` covers
  the route-level integration. New CSS-endpoint test and shell-module
  test extend it. Playwright screenshots cover visual regression.
- **Unchanged invariants:** The `<script type="application/json">`
  token-injection pattern stays byte-for-byte. `_PAYMENT_HEADERS` constant
  stays. Token TTL, circuit breaker thresholds, mint idempotency all
  unchanged. The 7 route states' triggering conditions (which template
  the handler picks per request state) are not modified.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Drift between FastAPI shell and Next.js shell after this ticket lands | `check-shell-drift.mjs` (Unit 2) runs in `prebuild`; CI fails on drift |
| Generated `leafbind-tokens.css` desyncs from `design-tokens.ts` after a future token bump | `check-token-drift.mjs` (extended in Unit 1) validates the 3-way relationship; CI fails on drift |
| Google Fonts loaded via CDN link adds a third-party request to the payment-page critical path | Cache-friendly (`display=swap`); fonts are already loaded by Next.js on /pricing so browser cache likely warm; revisit if Lighthouse regressions appear |
| Pre-existing XSS exploited before fix lands | The brand-pass commit includes the fix; ship together. If urgent, a separate hotfix could apply just the `html.escape()` change |
| Playwright script flaky on CI | Run locally for PR-time evidence; defer CI integration to a follow-up if needed |
| FastAPI static-file mount conflicts with nginx static serving | nginx config (deploy/nginx.conf) currently proxies everything to FastAPI. No conflict; FastAPI serves /static itself |

## Documentation / Operational Notes

- After merge: nothing to add to runbooks — the static-file mount and
  shell module are self-explanatory in the diff.
- After merge: comment on INFRA-392 with the AC #6 drift-incident log
  outcome. If "no drift observed," INFRA-392 stays deferred. If a real
  drift incident logged, INFRA-392 reactivates with that as concrete
  evidence.
- After merge: file the post-purchase email design ticket (co-deferred
  with EB-248 from EB-233).

## Sources & References

- **Origin document:** [docs/brainstorms/2026-05-15-eb248-stripe-payment-flow-design-pass-requirements.md](docs/brainstorms/2026-05-15-eb248-stripe-payment-flow-design-pass-requirements.md)
- Existing code: `web_service/routes/payment.py`, `web_service/main.py`,
  `web_service/frontend/design-tokens.ts`,
  `web_service/frontend/tools/check-token-drift.mjs`,
  `web_service/frontend/components/Header.tsx`,
  `web_service/frontend/components/Footer.tsx`,
  `tests/test_web_payment.py`
- Related plan: [docs/plans/2026-05-14-002-feat-eb233-leafbind-design-system-plan.md](docs/plans/2026-05-14-002-feat-eb233-leafbind-design-system-plan.md)
- Related ticket: INFRA-392 (deferred Figma MCP)
- Related ticket: EB-233 (Done), EB-240 (merged 2026-05-15)
- Decision pattern: `docs/solutions/best-practices/test-baseline-before-investing-in-tooling-2026-05-15.md`
