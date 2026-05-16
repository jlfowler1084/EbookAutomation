# EB-264 — Support Inbox + On-Site Contact Form for leafbind.io
# Model: SONNET
# Justification: Multi-file implementation across 4 surfaces (Cloudflare DNS, greenfield Worker, Next.js frontend, docs/solutions) following a structured plan with concrete test scenarios. Sonnet handles structured work well; no architectural decisions remain unresolved.

## Tickets

- **Primary:** EB-264 — Add support@leafbind.io inbox + on-site contact form
- **Blocks:** None
- **Relates to:** EB-45 (Leafbind freemium web service — parent), EB-265 (analytics + GSC — complementary, will surface v2 trigger signal), EB-261 (llms.txt for AI Overview / GEO — R16 updates the same file), EB-257 (Vercel productionBranch fix — verification ritual model)

## Estimated Scope

Multi-file change across two new directory hierarchies + four existing-file modifications:

- **NEW:** `cloudflare/contact-worker/` — first Cloudflare Worker in the repo. ~9 source files (wrangler.toml, package.json, tsconfig.json, .dev.vars [gitignored], src/{index,turnstile,rate-limit,sanitize,send,types}.ts) + 4 test files.
- **NEW:** `web_service/frontend/app/(app)/contact/` — page.tsx + ContactForm.tsx.
- **NEW:** `web_service/frontend/playwright.config.ts` + `web_service/frontend/tests/contact-form.spec.ts` (first Playwright harness in the frontend).
- **NEW:** Two `docs/solutions/` entries — Workers first-deployment topology + leafbind email auth stack.
- **MODIFIED:** `web_service/frontend/lib/structured-data.ts`, `components/Footer.tsx`, `app/sitemap.ts`, `public/llms.txt`, `package.json` (add `test:e2e` script), `.gitignore` (add `cloudflare/contact-worker/.dev.vars` and `test-results/`).
- **EXTERNAL CONFIG (not in repo):** Cloudflare DNS records (MX, SPF, DKIM, DMARC, `forms.leafbind.io` A), Cloudflare Email Routing rules, Resend account + verified domain, Gmail Send-mail-as alias, `wrangler secret put` for 3 secrets, KV namespace creation, Worker route binding.

---

## Phase 0 -- Branch Setup

**Branch:** `worktree/EB-264-contact-form-and-worker`
**Base:** `master` (EbookAutomation default; NOT `main` — verify with `git branch -a | grep -E '(main|master)'`)
**Worktree Mode:** create

Before any other work:

1. `git checkout master && git pull`
2. Create worktree: `git worktree add .worktrees/EB-264-contact-form-and-worker -b worktree/EB-264-contact-form-and-worker`
3. Change to worktree directory: `cd .worktrees/EB-264-contact-form-and-worker`
4. Confirm branch: `git branch --show-current` should output `worktree/EB-264-contact-form-and-worker`
5. Confirm clean state: `git status` should show no modifications
6. Confirm `.worktrees/` is in `.gitignore` (per global CLAUDE.md): `git check-ignore .worktrees/EB-264-contact-form-and-worker` should return non-zero / silent (it's ignored)

**Do NOT use `mklink /J` junctions to give the worktree access to `archive/`, `output/`, `inbox/`, or `processing/`.** These dirs are gitignored in the main tree. Junctioning them into the worktree means a subsequent `Remove-Item -Recurse` on the worktree deletes the target contents. Per project CLAUDE.md (SCRUM-301 incident, 2026-04-22). This project's work is web-only (no PDF data dirs needed) so this is unlikely to be tempting, but flag it for awareness.

Do not proceed to Phase 1 until all checks pass.

---

## Context

Read the full implementation plan at: `docs/plans/2026-05-15-003-feat-eb264-contact-form-and-worker-plan.md`

The plan is comprehensive (1000+ lines) and was hardened through two rounds of multi-persona document-review. The following context is what a fresh implementer would otherwise have to rediscover from scratch — carry it forward.

**Design decisions made during planning:**

1. **`forms.leafbind.io` (NEW subdomain), not `api.leafbind.io`, hosts the Worker.** This is the most consequential decision in the plan and was a P0 correction during document-review. The earlier draft assumed `api.leafbind.io` was greenfield; it is not — it serves the production FastAPI conversion backend on the Hetzner VM (per `deploy/VERCEL.md`, `deploy/nginx.conf` line 3, and `web_service/frontend/next.config.js` `NEXT_PUBLIC_API_URL`). The Worker is provisioned on a fresh dedicated subdomain (`forms.leafbind.io`) with a placeholder A record (192.0.2.1, RFC 5737); the Worker route binding intercepts before any origin server is consulted.

2. **`UploadZone.tsx` is the submit-state precedent**, NOT `RecoverClient.tsx`. The origin brainstorm doc cited `RecoverClient` as the model for the "Send message → Sending…" label-swap pattern, but `RecoverClient` uses a full-page POST without React state flags. `UploadZone` has the exact `useState<boolean>` + `useState<string|null>` + ternary-label pattern. Use it as the loading-state reference. Also add the `aria-describedby` wiring that `TokenField.tsx` (the validation precedent) lacks — copying TokenField blindly reproduces an accessibility gap.

3. **One KV namespace** (`CONTACT_KV`) with key prefixes (`rl:ip:`, `rl:email:`, `ack:`), NOT three separate namespaces. Earlier plan drafts had three; document-review identified this as over-engineering for v1 volume. TTL semantics are per-key, not per-namespace; inspectability works via prefix filtering.

4. **Two consolidated `docs/solutions/` entries**, NOT four. One for "Cloudflare Workers first deployment on leafbind topology" (genuinely load-bearing — captures the `forms.leafbind.io` decision for any future Worker on this project). One for "leafbind email auth stack" (combined SPF + DKIM + DMARC + Email Routing + Resend + Gmail Send-mail-as). Turnstile and DMARC-progression are sub-sections of these, not standalone entries.

5. **DMARC follow-up Jira ticket is Unit 7 step 8 (a hard step), NOT a ship-time TODO.** Title: `feat: DMARC p=none → p=quarantine upgrade for leafbind.io`. Due 30 days after EB-264 ships. Aggregate-report mailbox: `dmarc-reports@leafbind.io` (provisioned in Unit 1 as a Cloudflare Email Routing rule). Document the data-quality gate ("review last 7 days; if no legitimate-source failures, upgrade") in the ticket description.

6. **Resend issues TWO separate credentials**: a REST API key (used by the Worker, stored via `wrangler secret put RESEND_API_KEY`) and SMTP credentials (used by Gmail Send-mail-as alias, stored in Google's account state). They have different blast radii on compromise — SMTP credential grants sending on ALL Resend-verified domains on the account, not just leafbind.io. Treat both as high-value secrets; rotate immediately if leaked.

**Options considered and rejected:**

- *Worker on `api.leafbind.io/contact` with path-pinning to share the subdomain with FastAPI:* Rejected as creating ongoing shared-surface risk — any future CORS/cache/WAF rule change to the subdomain would affect both Worker and backend. `forms.leafbind.io` gives clean isolation.
- *Next.js server action / route handler on Vercel instead of a Worker:* Rejected because Vercel middleware cannot enforce per-IP KV rate-limiting without Upstash (cost) or an external store (new dependency). The Worker also keeps Vercel execution-time free for genuine app work.
- *Three KV namespaces:* Rejected as over-engineered (see decision 3).
- *Four `docs/solutions/` entries:* Rejected as documentation tax (see decision 4).
- *Postmark over Resend:* Rejected — $15/mo above free, overkill at v1 volume. Resend free tier (100/day + 3K/month) is sufficient.
- *DMARC `p=quarantine` from day one:* Rejected — misconfigured DMARC can silently break outbound Gmail forwards. Monitor mode (`p=none`) for 30 days catches misconfigurations cheaply.
- *Honeypot returns 400 / different UI:* Rejected — that's an oracle. Honeypot returns identical 200 + success UI as a real submission (defense-in-depth, not complete defense; Turnstile + rate-limit are the load-bearing controls).

**Hidden constraints or gotchas:**

- *SPF record at the apex is a single TXT.* Cloudflare Email Routing auto-creates one in Unit 1; Unit 2 must REPLACE its value in place (not add a second TXT), otherwise mail receivers see PermError and DMARC alignment fails for outbound Resend traffic.
- *Resend free tier is 100/day AND 3,000/month — daily is the binding constraint* at 2 emails per submission (forward + auto-ack) ⇒ ~50 submissions/day. Worth knowing during the rate-limit live test in Unit 7.
- *Cloudflare Workers KV free tier is 1,000 writes/day.* Each accepted submission writes 2-3 KV keys, putting the ceiling at ~333-500 accepted submissions/day. Above Resend's daily cap which trips first, but worth knowing.
- *KV is eventually consistent (~60s globally).* Different colos can briefly bypass the bucket cap by reading stale counters. Accepted for v1 volume.
- *Fixed-window rate-limit keying* (`floor(unix/3600)`) means at the hour boundary an attacker can get 10 submissions in ~2 seconds (5 before, 5 after). Accepted for v1; upgrade to 2-bucket sliding window if abuse materializes.
- *Turnstile `remoteip` is MANDATORY for siteverify* in this plan (the brainstorm called it "optional" — closed the gap during document-review). Without it, a token harvested from one IP could be replayed from any IP within ~300s. Cloudflare enforces single-use server-side regardless, but pass `remoteip = request.headers.get('CF-Connecting-IP')` to be safe.
- *Network timeout on Turnstile siteverify must fail-closed.* Wrap the entire `fetch()` in try/catch; ALL exceptions (timeout, DNS error, parse error) return `false`.
- *Email case normalization* — `.toLowerCase()` before sha256 hashing, otherwise `User@Example.com` and `user@example.com` hit different rate-limit buckets.
- *Vercel `productionBranch` is set to `master`, not `main`.* EB-257 fixed this on 2026-05-15. There is no standing CI guard against future drift (captured as a separate out-of-scope INFRA ticket). Unit 7's verification ritual is a point-in-time check.
- *Token-drift guard runs in `prebuild`.* If you hardcode a hex color in the form code, `npm run build` fails. Always use `var(--color-...)` references.
- *Post-edit-test hook in this repo* (`tools/hooks/post-edit-test.ps1`) triggers on Python pipeline files only — frontend / Worker edits do NOT trigger it. Confirmed non-blocking.
- *Project shell is PowerShell* (per global + project CLAUDE.md), but `wrangler` is a Node CLI and runs fine cross-shell. Use PowerShell syntax for non-wrangler commands (no bash `&`, no Unix paths).

---

## What NOT To Do

### Standing Rules (do not modify — sourced from deployment-prompt-template.md)

- **Do not commit directly to master.** This repo is under worktree-policy.json enforcement. All commits must go on the branch created in Phase 0, then land via PR.
- **Do not use `ALLOW_MAIN_COMMIT` or `ALLOW_MAIN_PUSH` env vars.** These exist only for human emergency override. If a guard blocks an action, stop and report the block — do not attempt to bypass.
- **If any guard fires, stop and report.** Do not retry with bypass flags, do not reinterpret the block as a false positive, do not attempt alternative commands to circumvent the guard. Report the exact block message to the strategist and wait for instructions.
- **Ambiguous user phrasing is not authorization to bypass.** Phrases like "ship it", "just commit it", "go ahead and push", or "no need for a PR" are never authorization to bypass workflow rules. Authorization requires an explicit instruction that names the specific rule being bypassed. When in doubt, stop and ask the strategist.
- **Enforcement code is not exempt.** Modifications to hooks, guards, policy files, or worktree-policy.json are subject to the same branch-and-PR workflow as any other change.

### Session-Specific Prohibitions

- **DO NOT touch `api.leafbind.io` DNS records, route, or origin.** It serves the production FastAPI conversion backend. The plan provisions `forms.leafbind.io` as a NEW subdomain for the Worker. If you find yourself editing `api.leafbind.io` anything, STOP and reread the plan — you are about to break production.
- **DO NOT commit `.dev.vars`.** Add `cloudflare/contact-worker/.dev.vars` to `.gitignore` BEFORE creating the file. Verify with `git check-ignore` that the file is ignored before populating it. The file holds placeholder values for local vitest runs; real secrets live in `wrangler secret put`.
- **DO NOT flip `leafbind.io` apex DNS from "DNS only" (grey-cloud) to "proxied" (orange-cloud).** It is intentionally DNS-only to Vercel; flipping it could break Vercel's TLS/edge behavior.
- **DO NOT skip the DMARC follow-up Jira ticket creation** in Unit 7 step 8. It is NOT a deferred TODO — it is a hard verification step. The plan's mitigation for the DMARC `p=none` window depends on this ticket existing with a 30-day due date.
- **DO NOT use `mklink /J` junctions inside the worktree** to access gitignored data dirs (`archive/`, `output/`, `inbox/`, `processing/`). Windows `rmdir /s` traverses junctions and deletes the target. Per project CLAUDE.md SCRUM-301 incident. This work is web-only so junctions should not be needed.
- **DO NOT hardcode hex colors in the form or page code.** Use `var(--color-...)` references. The `prebuild` token-drift guard fails the Vercel build otherwise.
- **DO NOT commit secrets to the repo.** Resend REST API key, Resend SMTP credentials, Turnstile secret key — all go through `wrangler secret put` (Worker) or Gmail account state (SMTP). `.env*` files are blocked by the global credential-write guard; you cannot Write to them. Document the secret names in `.env.example` as a manual operator step.
- **DO NOT run `wrangler deploy` to a production route before Phase 1 audit is complete.** A bad Worker route binding can shadow the wrong path. Stage in `--dry-run` mode first.

---

## Phase 1 -- Audit (READ-ONLY, STOP FOR REVIEW)

Before creating any file, verify the current state of every system the plan touches.

**File-level audit:**
1. Read `web_service/frontend/components/Footer.tsx` and confirm it is currently `md:grid-cols-3` with Brand / Convert / Account columns. Note any drift from the plan's description.
2. Read `web_service/frontend/lib/structured-data.ts` and confirm the `SchemaData` union is exactly `SoftwareApplicationSchema | FAQPageSchema | HowToSchema | ArticleSchema`. Identify the pattern for the existing `buildSoftwareApplicationSchema()` helper.
3. Read `web_service/frontend/components/UploadZone.tsx` and confirm it has the `useState<boolean>` + `useState<string | null>` + label-swap pattern the plan references.
4. Read `web_service/frontend/components/TokenField.tsx` and confirm it does NOT wire `aria-describedby` between input and error (a deliberate addition for `/contact`, not a copy-paste).
5. Read `web_service/frontend/components/FormatSelector.tsx` and note the native `<select>` styling tokens (padding, borderRadius, var(--color-border)).
6. Read `web_service/frontend/app/(app)/recover/page.tsx` and confirm the `(app)` route group's container width and card pattern.
7. Read `web_service/frontend/app/sitemap.ts` and confirm the existing entry shape; identify where `/contact` should be added.
8. Read `web_service/frontend/public/llms.txt` and locate the Contact line (R16 target).
9. Confirm `web_service/frontend/package.json` has `playwright: ^1.60.x` in devDependencies and that there is NO `playwright.config.*` and NO `tests/` directory in the frontend (greenfield Playwright scaffold).
10. Confirm `cloudflare/` directory does not exist (greenfield Worker).

**Infrastructure audit (via Cloudflare MCP):**
11. Confirm `leafbind.io` zone is active (zone id `20967fb38b4e1feb6dfc01e4407d7225`).
12. Confirm Email Routing is currently `enabled: false`, `status: "unconfigured"` (drift from 2026-05-15 check would mean someone already configured it).
13. Confirm `api.leafbind.io` has an A record pointing at the Hetzner VM (5.161.228.1) and is orange-cloud (proxied). **Do NOT modify.** This is the FastAPI backend.
14. Confirm `forms.leafbind.io` does NOT have any existing A/CNAME record (greenfield subdomain).
15. List current TXT records at `leafbind.io` apex — note any pre-existing SPF or `google-site-verification` records (the GSC record `17e4Ve...HlJM` should remain untouched; do not delete it).

**Project-state audit:**
16. Confirm Vercel `productionBranch` is `master` (per EB-257 fix): `npx vercel project inspect leafbind --scope <team>` if available, or REST `GET /v9/projects/<id>`.
17. Confirm `.gitignore` includes `.worktrees/` and `.env*`.

**Success criteria:**
- All 17 audit items have explicit "confirmed" or "drift detected" outcomes.
- Any drift is reported to the strategist BEFORE creating any file.
- Particularly: any change to the api.leafbind.io DNS or Vercel `productionBranch` since this plan was authored requires re-evaluating affected phases.

**STOP.** Report findings before proceeding to Phase 2.

---

## Phase 2 -- Unit 1: Cloudflare zone foundation

Implement Unit 1 from the plan:
- Enable Cloudflare Email Routing on leafbind.io.
- Add destination `jlfowler1084@gmail.com` and verify.
- Create routing rules for `support@leafbind.io` and `dmarc-reports@leafbind.io` → forward to Gmail.
- Verify the three auto-added MX records and the SPF baseline.
- Add DMARC monitor TXT at `_dmarc.leafbind.io`.
- Provision `forms.leafbind.io` proxied subdomain (A record → 192.0.2.1, orange-cloud).
- **Do NOT extend SPF with Resend's include yet** — that happens in Unit 2 (replace-in-place).
- Run the regression check: `curl https://api.leafbind.io/health` must return 200.

**Success criteria:**
- `dig MX leafbind.io` returns the three `route{1,2,3}.mx.cloudflare.net` records.
- `dig TXT _dmarc.leafbind.io` returns the `p=none; rua=mailto:dmarc-reports@leafbind.io; pct=100` record.
- A live test email to `support@leafbind.io` arrives in operator Gmail within 60s.
- `https://forms.leafbind.io/anything` returns a Cloudflare 1000-series origin error.
- `curl https://api.leafbind.io/health` returns 200 — FastAPI backend untouched.

**STOP.** Report each `dig` output and the regression-check result before proceeding to Phase 3.

---

## Phase 3 -- Unit 2: Resend + SPF replace-in-place + Gmail Send-mail-as

Implement Unit 2 from the plan:
- Sign up Resend (free tier).
- Add `leafbind.io` as a verified domain in Resend; Resend provides DKIM TXT + an SPF `include:` token.
- Add the DKIM record at Cloudflare (new TXT at sub-selector).
- **SPF REPLACE-IN-PLACE:** Locate the existing SPF TXT created by Email Routing in Phase 2; REPLACE its value (do NOT add a second TXT) with `v=spf1 include:_spf.mx.cloudflare.net include:<resend-spf-token> -all`.
- Verify with `dig TXT leafbind.io` that exactly one `v=spf1` record exists.
- Wait for Resend domain verification (DKIM ✓ + SPF ✓).
- Issue two Resend credentials: a REST API key (sending-scoped) and SMTP credentials. Both are needed; document each is a separate compromise surface.
- Configure Gmail "Send mail as `support@leafbind.io`" via Resend SMTP relay (`smtp.resend.com`).
- Send a test reply from Gmail using the new alias; mail-tester.com score ≥ 9/10 target.
- Verify `Return-Path` in a received message is `*@resend.com`, NOT `*@gmail.com`.

**Success criteria:**
- Resend dashboard: leafbind.io verified with DKIM ✓ and SPF ✓.
- `dig TXT leafbind.io` returns exactly one record starting with `v=spf1` (no PermError).
- mail-tester.com score ≥ 9/10 with all auth passing.
- Recipient view of the test message shows `support@leafbind.io` in the From line; `jlfowler1084@gmail.com` is NOT visible anywhere.
- `dig MX leafbind.io` still returns the three CF MX records (regression).

**STOP.** Report the mail-tester score, the `Authentication-Results` header from a test message, and the Return-Path header value before proceeding to Phase 4.

---

## Phase 4 -- Unit 3: Cloudflare Worker (greenfield)

Implement Unit 3 from the plan:
- `wrangler init` as ES module Worker, TypeScript yes, no router lib, `compatibility_date ≥ 2024-09-23`.
- Configure `wrangler.toml`: name `contact-worker`, route `forms.leafbind.io/contact` (no method scope), one KV binding (`CONTACT_KV`), secret bindings (`TURNSTILE_SECRET_KEY`, `RESEND_API_KEY`, `SUPPORT_INBOX_ADDRESS`).
- `wrangler kv:namespace create CONTACT_KV`; commit ID to wrangler.toml.
- `wrangler secret put` each of the three secrets.
- Add `cloudflare/contact-worker/.dev.vars` to `.gitignore` BEFORE creating the file. Verify with `git check-ignore`. Populate with placeholders for local vitest runs.
- Implement `src/index.ts` with OPTIONS preflight handler (204 + CORS for `https://leafbind.io` and `https://www.leafbind.io`), POST handler chain, 405 for everything else.
- Implement `src/turnstile.ts` with try/catch around fetch, MANDATORY `remoteip=CF-Connecting-IP`, fail-closed on all exceptions.
- Implement `src/rate-limit.ts` with single namespace key prefixes (`rl:ip:<bucket>`, `rl:email:<sha256(lowercase)>:<bucket>`), IPv6 /64 bucketing.
- Implement `src/sanitize.ts` with HTML strip + entity-encode + CRLF reject + length caps + email lowercase normalization.
- Implement `src/send.ts` with plain-text-only Resend SDK calls; per-recipient auto-ack throttle keyed `ack:<sha256(lowercase)>`; auto-ack failure does NOT block.
- Log sanitization: never log `env`; strip `turnstile_token` and `email` from any error log.
- Write `test/*.test.ts` files using `@cloudflare/vitest-pool-workers`. Cover every test scenario from the plan's Unit 3.
- `wrangler dev` to local-test, then `wrangler deploy` to production.

**Execution note:** test-first for sanitize + rate-limit + turnstile. Write each test case (XSS, CRLF, over-cap, IPv6 /64, case-variant email, network timeout, single-use replay) before the implementation.

**Success criteria:**
- `vitest` test suite passes 100% of plan-enumerated scenarios.
- `wrangler deploy` succeeds.
- `curl -X OPTIONS https://forms.leafbind.io/contact -H "Origin: https://leafbind.io"` returns 204 with full CORS headers.
- `curl -X POST https://forms.leafbind.io/contact ...` with a valid Turnstile token returns 200 `{ok:true}`.
- `wrangler kv:key list --binding=CONTACT_KV` shows the rate-limit key written by the curl test.
- `curl https://api.leafbind.io/health` still returns 200 — regression check.

**STOP.** Report the Worker URL, the vitest output summary, and the regression-check result before proceeding to Phase 5.

---

## Phase 5 -- Unit 4: Frontend `/contact` page + Playwright harness

Implement Unit 4 from the plan:
- Create `web_service/frontend/app/(app)/contact/page.tsx` and `ContactForm.tsx`.
- Extend `web_service/frontend/lib/structured-data.ts` (single file): add `ContactPageSchema` interface, append to `SchemaData` union, add `buildContactPageSchema()` helper.
- Wire `aria-describedby` between each input and its error message — add the a11y wiring that `TokenField.tsx` is missing.
- Submit posts to `https://forms.leafbind.io/contact` (NOT `api.leafbind.io`).
- Success container: `tabIndex={-1}`, `role="status"`, `aria-live="polite"`, focus moves on success.
- sessionStorage draft preservation on input change AND before fetch fires.
- All four failure-mode error copies per R8.
- Scaffold Playwright: `playwright.config.ts`, `tests/contact-form.spec.ts`, `package.json` `test:e2e` script, `.gitignore` updates for `test-results/` and `playwright-report/`.

**Success criteria:**
- `npm run lint` and `npm run build` pass without warnings.
- `npm run check:tokens` passes (no design-token drift).
- `npm run test:e2e` runs the new Playwright suite to green against `npm run dev`.
- Google Rich Results Test on a Vercel preview of `/contact` reports zero errors and zero warnings.
- Manual keyboard-only completion + screen-reader announcement test passes.

**STOP.** Report the Playwright test output and a screenshot/description of the `/contact` page before proceeding to Phase 6.

---

## Phase 6 -- Unit 5: Footer + IA refactor

Implement Unit 5 from the plan:
- Change `web_service/frontend/components/Footer.tsx` from `md:grid-cols-3` to `md:grid-cols-4`.
- Add Support column with Contact + Recover-tokens.
- Remove Recover-tokens from Account column (Account becomes [Pricing, Quality]).
- Visual-validate at sm / md / lg breakpoints. If 4-col cramped at md (768–1023px), escalate to `sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-4`.

**Success criteria:**
- Footer renders correctly on `/`, `/pricing`, `/quality`, all `/convert/*`, `/guides/*`, the new `/contact`, `/recover`, and `/status/[id]`.
- Lighthouse on `/` shows no new accessibility or layout-shift issues.

**STOP.** Report visual rendering (screenshot or markup snippet) before proceeding to Phase 7.

---

## Phase 7 -- Unit 6: Sitemap + llms.txt

Implement Unit 6 from the plan:
- Add `/contact` entry to `app/sitemap.ts` at priority 0.5, `changeFrequency: yearly`, WITH the explanatory inline comment about the deliberate deviation from convention.
- Replace the Contact line in `public/llms.txt`:
  - OLD: `Contact: via the conversion result page (no public contact form on the marketing site as of 2026-05)`
  - NEW: `Contact: https://leafbind.io/contact`
- Confirm `app/robots.ts` requires no change (existing `allow: "/"` covers `/contact`).

**Success criteria:**
- `curl https://leafbind.io/sitemap.xml` (after Vercel deploy) returns the new entry.
- `curl https://leafbind.io/llms.txt` shows the updated Contact line.
- `npm run build` produces well-formed sitemap.xml.

**STOP.** Report the deployed sitemap.xml and llms.txt content before proceeding to Phase 8.

---

## Phase 8 -- Unit 7: End-to-end verification + docs/solutions + DMARC ticket

Run the full Unit 7 verification checklist (all 9 steps from the plan, including the DMARC follow-up ticket creation as step 8 and the `api.leafbind.io/health` regression check as step 9).

Write the two consolidated `docs/solutions/` entries:
- `docs/solutions/best-practices/cloudflare-workers-first-deployment-leafbind-2026-05-NN.md`
- `docs/solutions/best-practices/leafbind-email-auth-stack-2026-05-NN.md`

Frontmatter for each: `module`, `tags`, `problem_type`. Follow the existing `docs/solutions/` conventions in the repo.

Create the DMARC follow-up Jira ticket via the Atlassian MCP:
- Title: `feat: DMARC p=none → p=quarantine upgrade for leafbind.io`
- Due date: ship_date + 30 days
- Description: aggregate-report mailbox `dmarc-reports@leafbind.io`, data-quality gate ("review last 7 days; if no legitimate-source failures, upgrade"), link to EB-264 as `relates to`.

**Success criteria:**
- All 9 verification steps green.
- Two `docs/solutions/` files created with valid frontmatter.
- DMARC Jira ticket created with the correct due date and linked to EB-264.
- Outcome trigger criteria documented for the 30-day post-launch review (≥5 non-test inbounds; ≥1 conversion-ID inbound triggers v2).

**STOP.** Report the verification checklist results, the two docs/solutions paths, and the DMARC ticket URL before proceeding to Phase 9.

---

## Pre-Flight Environment Checks

Before Phase 0 (or as part of Phase 1 audit), confirm:

- `wrangler --version` is installed (≥ 3.x).
- Cloudflare MCP is authenticated (`leafbind.io` zone accessible via MCP tools).
- Atlassian MCP is authenticated (can create Jira tickets in EB project).
- Node version is 24.x (per `.nvmrc` if present).
- `npm install` in `web_service/frontend/` completes cleanly.
- Operator has access to Gmail account `jlfowler1084@gmail.com` (for Email Routing destination verification + Send-mail-as configuration).
- Operator can sign up for a Resend account (no existing one for leafbind.io presumed).

If any pre-flight check fails, STOP and report to the strategist.

---

## Rollback Procedures

DNS changes are the highest-risk operation in this plan. Rollback per Unit:

- **Unit 1 rollback:** In Cloudflare DNS: delete the DMARC TXT, delete the `forms.leafbind.io` A record. In Email Routing: disable the routing rules (preserves rules for re-enable). MX records persist (low risk — they only route mail TO Cloudflare).
- **Unit 2 rollback:** In Cloudflare DNS: revert the SPF record to its pre-Resend value (the Cloudflare-Email-Routing-only baseline). Delete the Resend DKIM TXT. In Gmail: remove the Send-mail-as alias. In Resend: revoke API key + SMTP credentials, delete the verified domain. **Recovery from a botched SPF replacement:** the Cloudflare Email Routing dashboard shows the recommended SPF — restore that exact value if the combined record is malformed.
- **Unit 3 rollback:** `wrangler delete contact-worker` removes the deployment. The route binding goes with it. KV namespace persists (manual delete via `wrangler kv:namespace delete CONTACT_KV` if desired). Secrets are scoped to the Worker; they go away with the deploy.
- **Unit 4-7 rollback:** Standard `git revert` on the merge commit. Vercel re-deploys.

**Hardest-to-rollback step:** SPF replace-in-place. Verify with `dig TXT leafbind.io` immediately after the change; if anything looks wrong, revert before the change propagates globally (~5 min TTL via Cloudflare).

---

## Smoke Test

End-to-end live test (Phase 8, step 4 of the Unit 7 checklist) is the integration smoke test:

1. From an external incognito browser (fresh IP), navigate to `https://leafbind.io/contact`.
2. Fill the form: Name = test, Email = a friend's address you can check, Topic = General, Message = ≥20 chars including the literal string "EB-264 smoke test".
3. Submit. Expect inline success state with echoed message text.
4. Within ~1 minute, verify:
   - The friend's inbox receives a plain-text auto-ack from `support@leafbind.io`.
   - `jlfowler1084@gmail.com` receives the forwarded support message.
   - Both messages have `Authentication-Results: spf=pass; dkim=pass; dmarc=pass` headers.
   - Reply from Gmail using the Send-mail-as alias arrives at the friend with the same auth-pass result.

Expected observable outcome: support inbox + user inbox both populated, auth passing, no `jlfowler1084@gmail.com` visible to the friend.

---

## Phase 9 -- Commit and Push

**STOP before committing.** Report all files to the strategist.

After approval:

1. Stage all created/modified files (exclude `.dev.vars`):
   ```
   git add cloudflare/contact-worker/
   git add web_service/frontend/app/(app)/contact/
   git add web_service/frontend/lib/structured-data.ts
   git add web_service/frontend/components/Footer.tsx
   git add web_service/frontend/app/sitemap.ts
   git add web_service/frontend/public/llms.txt
   git add web_service/frontend/playwright.config.ts
   git add web_service/frontend/tests/
   git add web_service/frontend/package.json
   git add web_service/frontend/.gitignore
   git add .gitignore
   git add docs/solutions/best-practices/cloudflare-workers-first-deployment-leafbind-*.md
   git add docs/solutions/best-practices/leafbind-email-auth-stack-*.md
   ```
2. Verify `git status` shows no `.dev.vars` staged: `git diff --cached --name-only | grep -i dev.vars` returns empty.
3. Commit: `git commit -m "feat(EB-264): add support@leafbind.io inbox + on-site contact form"` (squash-friendly single commit, or multiple logical commits if the implementation revealed a natural split).
4. Push: `git push -u origin worktree/EB-264-contact-form-and-worker`.
5. **STOP before opening PR.**

---

## Verification Checklist

- [ ] Branch was created via `git worktree add` and all work happened in the worktree
- [ ] No commits were made to master
- [ ] No bypass env vars were used
- [ ] Phase 1 audit was completed before any file creation
- [ ] `.dev.vars` was added to `.gitignore` BEFORE the file was created and is not staged
- [ ] No `api.leafbind.io` DNS/origin/route was modified
- [ ] `leafbind.io` apex remained DNS-only to Vercel (no orange-cloud flip)
- [ ] DMARC follow-up Jira ticket was created with 30-day due date and linked to EB-264
- [ ] Two `docs/solutions/` entries were created (NOT four)
- [ ] `forms.leafbind.io` Worker route is live; `curl https://forms.leafbind.io/contact -X OPTIONS` returns 204
- [ ] `curl https://api.leafbind.io/health` still returns 200 — FastAPI backend intact
- [ ] mail-tester.com score ≥ 9/10 (or documented Resend-shared-IP justification for lower)
- [ ] Google Rich Results Test on `/contact` reports zero errors / zero warnings
- [ ] Branch is pushed but PR is NOT yet opened

---

## Report Structure

At each STOP gate, report back with:
1. **Findings** — What was discovered or changed
2. **Assumptions changed** — Anything that contradicts the plan or this prompt
3. **Options** — If a decision point was reached, what are the alternatives
4. **Recommendation** — Your recommended path, with rationale

At final completion, also include:
5. **Commit hashes** — For each commit made
6. **Out-of-scope findings** — Anything that warrants a follow-up ticket (especially: a standing CI guard for Vercel `productionBranch`, captured as an INFRA ticket)
7. **DMARC follow-up ticket URL** — Direct link
8. **`docs/solutions/` entry URLs** — Direct links to both consolidated entries

---

## Invocation

```
claude --model sonnet "[EB-264] Support inbox + contact form -- Read prompts/EB-264-contact-form-and-worker.md and follow the instructions"
```
