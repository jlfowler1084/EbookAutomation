[EB-248] Visual brand pass on the FastAPI-rendered payment flow at web_service/routes/payment.py

Model: SONNET
Reason: Multi-file implementation work across Python (FastAPI templates, shell module, security regression test), Node (CSS generator, drift guards, Playwright screenshots), and CSS (token mirror + utility classes). 6 implementation units with concrete test scenarios. Plan and design decisions already made in Opus; this is THINK+DO execution, not THINK DEEPLY.

## Read these first, in order

1. `docs/plans/2026-05-15-002-feat-eb248-payment-flow-brand-pass-plan.md` — the full plan. Source of truth for what to build. All P1 design decisions (trust moment, pending animation, shell mechanism) and P2 architecture decisions (build-time CSS gen, StaticFiles mount, cache policy split) are resolved with rationale.
2. `docs/brainstorms/2026-05-15-eb248-stripe-payment-flow-design-pass-requirements.md` — origin doc. Acceptance criteria are the contract.
3. `web_service/routes/payment.py` — the file being redesigned. Read all 452 lines before editing anything. The token-security architecture (`<script type="application/json">` pattern, `_PAYMENT_HEADERS` constant, security-sensitive comments at lines 1–16) is load-bearing and must be preserved exactly.
4. `tests/test_web_payment.py` — the existing comprehensive test suite. Extend this; do not write a parallel runner. Classes: `TestPaymentSuccessHappyPaths`, `TestPaymentSuccessEdgeCases`, `TestPaymentSuccessErrorPaths`, `TestPaymentSuccessCircuitBreaker`, `TestPaymentCancel`, `TestXSSInjectionGuards`, `TestResponseHeaders`, `TestGetTokensForSession`.

## Phase 0: Branch setup (verify only)

The worktree already exists. Verify:

```powershell
git worktree list
# Confirm: F:/Projects/EbookAutomation/.worktrees/feat-EB-248-stripe-success-page  <SHA>  [feat/EB-248-stripe-success-page]

Set-Location F:\Projects\EbookAutomation\.worktrees\feat-EB-248-stripe-success-page
git status                # clean
git rev-parse --abbrev-ref HEAD  # feat/EB-248-stripe-success-page
```

If the worktree is missing or on the wrong branch: stop and ask the user before running `git worktree add` — there may be context you don't have.

Install dependencies in the worktree:

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 -m pip install -r dev-requirements.txt
Set-Location web_service/frontend
npm install
Set-Location ..\..
```

Baseline test run — establish clean state before changing anything:

```powershell
py -3.12 -m pytest tests/test_web_payment.py -v
```

All classes must pass. If any baseline test fails, STOP and diagnose before any other work. Do not start implementing on top of a red baseline.

## Phase 1: Execute the plan via ce:work

Invoke `ce:work` with the plan path. ce:work handles unit-by-unit execution including the explicit test-first execution notes on Units 1, 2, and 3.

Units must land in plan order (1 → 6) because each builds on the previous:

- **Unit 1**: Shared CSS pipeline + StaticFiles mount + drift-guard extension. Has `Execution note: Test-first` — write `tests/test_web_static.py` before adding the FastAPI mount.
- **Unit 2**: Shell module (`web_service/templates/shell.py`) + CI text-content drift check (`check-shell-drift.mjs`). Has `Execution note: Test-first` — write `tests/test_web_shell.py` first.
- **Unit 3**: Brand pass + pre-existing XSS fix on `_render_success_page` + `_base_html`. **Critical security regression**: write the failing XSS test in `TestXSSInjectionGuards` BEFORE applying `html.escape()`. This is the canonical TDD case in this plan.
- **Unit 4**: `_render_pending_page` + `_render_retry_page` with pulsing eyebrow animation. Reuses the CSS classes from Unit 1.
- **Unit 5**: `_render_expired_page`, `_render_not_found_page`, `_render_cancel_page`, plus extracting the inline invalid-session-id HTML into a new helper.
- **Unit 6**: Playwright screenshots (mobile 375px + desktop 1280px × 7 states = 14 PNGs) + final test run + PR description compilation including the AC #6 drift-incident log.

After each unit, run the relevant test scope and verify all green before moving on. Commit per unit on the worktree branch.

## Gotchas surfaced during planning + review

These were validated by 4 reviewer agents on the brainstorm doc. Do not relitigate; do not assume they're optional.

### Security (NON-NEGOTIABLE)

- **The `<script type="application/json">` token-injection pattern stays byte-for-byte.** Tokens are NOT moved into a separate fetch, NOT inlined as JS, NOT migrated to a Next.js page. The pattern is documented at `payment.py:1-16` as a deliberate security choice — preserving it is AC #3.
- **`_PAYMENT_HEADERS` (Referrer-Policy: no-referrer, Cache-Control: private, no-store) applies to all 7 templates.** A brand-pass refactor of `_base_html` must NOT drop these headers. AC #8 is the regression gate.
- **`html.escape(value, quote=True)` on every reflection of `session_id`** in the 4 helpers (`_render_expired_page`, `_render_retry_page`, `_render_pending_page`, `_render_not_found_page`). The `cs_` prefix check is not sufficient — a payload like `?session_id=cs_<script>alert(1)</script>` passes the prefix check. This is a real pre-existing XSS; AC #9 is the fix.
- **The new `/static/leafbind-tokens.css` endpoint carries `Cache-Control: public, max-age=3600, immutable`** — NOT the strict `private, no-store` policy. Brand CSS is reusable and not user-specific. The two cache policies live at different paths, so there is no conflict.

### Architecture

- **Build-time CSS generation, committed to git.** `gen-fastapi-css.mjs` reads `design-tokens.ts` and emits `web_service/static/leafbind-tokens.css`. The CSS file IS committed (so it's diff-reviewable). FastAPI does not need a Node runtime on the deploy VM.
- **Token-drift guard extends to the third surface.** `check-token-drift.mjs` already validates `design-tokens.ts ⇔ globals.css`. The extension validates `design-tokens.ts ⇔ generated CSS` as a third pair. Same Map-diff pattern. Same `prebuild` invocation.
- **Shell is hand-mirrored in Python, NOT rendered from Next.js.** `web_service/templates/shell.py` defines `header_html()` and `footer_html()` returning plain strings. The payment-flow shell is intentionally minimal — logo + footer copy, no Convert/Pricing/Quality nav. A user mid-payment doesn't need marketing nav. CI check (`check-shell-drift.mjs`) compares text content + logo SVG paths against the React components.
- **Font loading via Google Fonts CDN link** in `_base_html`. Newsreader + DM Sans + IBM Plex Mono with `display=swap`. Cheaper than self-hosting; browser cache likely warm from Next.js's `next/font` having loaded them on /pricing.

### Design

- **Trust moment on success page is fully specified in D5 of the plan.** Eyebrow ("PAYMENT CONFIRMED" in Plex Mono uppercase), Newsreader headline ("Welcome to Leafbind."), monospaced token block on muted-sand surface with forest border-left, action row with primary + ghost + link. No illustration. No big logo at the top of the body (logo lives in the shell). Don't invent your own treatment.
- **Pending animation is a pulsing eyebrow opacity, not a spinner.** D6 of the plan. CSS-only `@keyframes lb-pulse` with `prefers-reduced-motion` fallback. The eyebrow text on the pending page reads "PROCESSING"; on retry it reads "CATCHING UP". No spinner, no progress bar, no skeleton loader — those are AI-tells and explicitly out per AC #4.
- **IA per template is in D7's table.** Eyebrow → headline → body → CTA/action. Follow the table.

### Testing

- **Extend the existing harness; never write a parallel runner.** `tests/test_web_payment.py` already covers all 7 states via `fastapi.testclient.TestClient`. Add HTML assertions for new CSS classnames, response-header assertions, and the new XSS regression — all inside existing test classes or new classes within the same file.
- **Unit 6 is verification, not new test code.** It runs the screenshot script + the full test suite + compiles the PR description. The Playwright script is the only new code in Unit 6.

## AC #6: Drift-incident log (the INFRA-392 evidence path)

This is critical. While executing the work, **watch for moments where the brand pass was hard to get right without a visual spec** — a moment where you generated something off-brand and had to iterate to fix it, OR where the absence of a Figma frame meaningfully slowed you down.

If such a moment occurs, log it concretely in the PR description under a section titled "INFRA-392 drift evidence":

```
INFRA-392 drift evidence

During <unit name>, <specific generated artifact> was off-brand because <reason>.
Fix took <N> iterations / <effort>. A Figma frame would have helped by <how>.
```

If NO such moment occurs, log that too:

```
INFRA-392 drift evidence

No drift incidents observed during this work. web-aesthetics + Playwright
iteration produced on-brand output without a Figma reference. INFRA-392
stays deferred.
```

Either log is valid signal. Both are required by AC #6. Do not omit this section — it's the entire point of this ticket being the baseline test.

## When done

1. All 6 units have green test runs.
2. `web_service/static/leafbind-tokens.css` is committed.
3. The full `pytest tests/test_web_payment.py + tests/test_web_static.py + tests/test_web_shell.py` is green.
4. 14 Playwright screenshots saved under `.screenshots/eb-248/`.
5. Open a PR from `feat/EB-248-stripe-success-page` → `master`. PR description includes:
   - One-line summary
   - The 14 screenshots embedded or linked
   - The INFRA-392 drift evidence section (one of the two formats above)
   - Test results summary
6. Comment on EB-248 Jira with the PR URL and AC #6 outcome.

Hand back to the user for PR review + merge. Do not merge yourself.

## Anti-patterns (will get the PR rejected)

- Migrating `/payment/success` to Next.js (settled security decision, do not relitigate)
- Removing or modifying the `<script type="application/json">` token-injection pattern
- Dropping `_PAYMENT_HEADERS` from any template
- Hardcoding hex colors anywhere in Python string literals
- Using a CSS spinner, progress bar, skeleton loader, gradient mesh, or glassmorphism
- Writing a parallel test runner instead of extending `tests/test_web_payment.py`
- Generating `leafbind-tokens.css` at runtime instead of committing it
- Skipping the AC #6 drift-incident log
