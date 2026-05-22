# [EB-322] Build the Send-to-Kindle E999 troubleshooting page

**Model:** SONNET — bounded "THINK + DO" frontend feature (single Next.js marketing page, strong existing pattern). Do NOT run this in an Opus planning session.
**Plan:** `docs/plans/2026-05-22-001-feat-eb-322-send-to-kindle-e999-troubleshooting-plan.md`
**Origin requirements:** `docs/brainstorms/2026-05-22-eb-322-send-to-kindle-e999-troubleshooting-requirements.md`
**Ticket:** EB-322 (parent EB-303 Phase 3b) — primary
**Related:** EB-303 (Phase 3 sequencing), EB-295 (same-PR hygiene), EB-292 (attribution rail), EB-320 (sibling EPUB pillar — do NOT block on it; see below)

---

## ⚠️ HUMAN PRE-WORK (Joe — not the implementer's task)

These are manual web-UI / billing actions the coding agent cannot perform. Do them independently of this build:

1. **Cancel the Semrush trial before 2026-05-23.** Cancel the *subscription* (let it lapse to free tier) — **do NOT delete the account**, or the Position Tracking baseline is lost.
2. **After cancelling, add two Position Tracking keywords** in the Semrush web UI (fills the free-tier slot to 10/10): `e999 - send to kindle internal error` and `does kindle support epub`.

The implementer should NOT attempt either action. They are recorded here so the handoff is self-contained.

---

## ⚠️ SUPERSESSION — execute EB-322 FIRST (do not wait on EB-320)

EB-322's Jira **description still contains older dependency language saying "ship EB-320 first."** That is **superseded** by the EB-303 Phase 3b launch sequence decided 2026-05-22.

**Authoritative direction:** EB-322 is the **decided first Phase 3b page** — the wedge page. Build and ship it now. Do **NOT** wait on EB-320 (the EPUB pillar). Authoritative sources: the EB-303 description "Phase 3 build sequence — DECIDED 2026-05-22" section and its decision comment of the same date. If you notice the contradiction in the EB-322 description, that is expected — follow this prompt and EB-303, not the stale EB-322 dependency note.

---

## Scope (hard-pinned — do not deviate)

1. **Branch / worktree:** `feat/EB-322-send-to-kindle-error-e999` (worktree at `.worktrees/feat-EB-322-send-to-kindle-error-e999`). Verify `.worktrees/` is gitignored before creating.
2. **URL / slug:** `/guides/send-to-kindle-error-e999` (error-code-anchored — do not rename to `-troubleshooting` or `-not-working-e999`).
3. **Clone the Unit 2 RSC page structure** at `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx`. **NO shared template extraction** — this is page #6 in the pattern; copy the structure inline, do not refactor the existing pages into a shared template.
4. **Reuse the existing OG image** (`/quality/pipeline-headings.png`, as Unit 2 does). **No screenshot dependency** — this is text/diagnostic content; do not produce or wire custom images.
5. **Touch exactly these 5 surfaces** (same-PR EB-295 hygiene), no more:
   - Create: `web_service/frontend/app/(marketing)/guides/send-to-kindle-error-e999/page.tsx`
   - Modify: `web_service/frontend/app/sitemap.ts`
   - Modify: `web_service/frontend/public/llms.txt`
   - Modify: `web_service/frontend/components/Footer.tsx`
   - Modify: `web_service/frontend/app/(marketing)/guides/page.tsx` (guides hub card)
6. **Validation:** run the **two-layer schema validation** (per `docs/solutions/best-practices/schema-validator-playwright-headless-quirk-2026-05-14.md`) **plus link-check** before declaring done.

---

## Context (carried from planning)

**Design decisions:**
- **Error-code-organized, not symptom-organized.** Three H2 sections by error class — E999 internal error / authentication failure / silent "doesn't work" failures — each with diagnostic H3 sub-anchors. This is what makes the page non-duplicate vs Unit 2 (which is symptom-category + numbered fixes). Confirmed Unit 2 has zero `e999` coverage.
- **`faqItems` single-source-of-truth:** one array feeds both the rendered FAQ section and `buildFAQPageSchema` — prevents schema/visible drift (Unit 2 pattern).
- **Two JSON-LD `<script>` tags** (Article via `buildArticleSchema`, FAQPage via `buildFAQPageSchema`), matching Unit 2 exactly — per `docs/solutions/best-practices/jsonld-script-tag-count-build-instability-2026-05-14.md` (mismatched tag count causes build instability).
- **Honest CTA (R4 discipline):** route fixable cases to the fixes first (most users don't need leafbind); route only the **unfixable subset** (size cap, malformed file, DRM rejection) to `/convert/pdf-to-kfx` as the "skip Send-to-Kindle entirely" path. No overselling.
- **Title/H1 foregrounds "E999 / internal error"** (Amazon's authority is weakest on the error-code SERP). Title ≤ 60 chars.

**Options rejected:**
- Expanding Unit 2 in place (rejected — dilutes its symptom focus, mixes two SERP intents, shares ranking signal with the 260/mo page).
- `send-to-kindle-troubleshooting` / `send-to-kindle-not-working-e999` slugs (rejected — too broad / too close to Unit 2's stem → near-duplicate risk).

**Hidden constraints / gotchas:**
- **`send to kindle doesn't work` (480/mo) is a secondary H3 anchor only** — Amazon's STK landing ranks #3 on that SERP; do NOT foreground it in title/H1.
- **The auth-failure keyword `an authentication failure occured send to kindle app` is KD=0 (no SERP signal).** Include the auth-failure section for topical completeness, but it is NOT a ranking target.
- **Do NOT modify Unit 2 in this PR** (explicit non-goal). The new page links *to* Unit 2; the reciprocal Unit 2 → new-page link is a deferred follow-up.
- **No DRM stripping/removal instructions** — describe Amazon's rejection behavior only (legal-sensitivity boundary).
- **No Amazon-account-recovery copy** — don't scope leafbind into Amazon-account troubleshooting.

---

## Standing rules (always apply)

- Work on the pinned worktree branch — never commit to `master` directly. Use the `safe-commit` workflow before committing.
- Run the project test/validation gates and report actual output before declaring any unit done. Never claim "passing" without running it.
- Follow the EB-295 same-PR hygiene policy: the page and all four discovery surfaces ship in the SAME PR.
- Match the surrounding code's conventions (Tailwind classes, serif/sans/mono usage, `JsonLd` import depth) from the Unit 2 page.
- Repo-relative paths only.

### Session-specific prohibitions (what NOT to do)
- Do NOT extract a shared page template or refactor the existing 5 guide pages.
- Do NOT create or wire custom screenshots/images.
- Do NOT touch any file outside the 5 pinned surfaces.
- Do NOT edit Unit 2 (`send-to-kindle-not-working/page.tsx`).
- Do NOT add or change Position Tracking config in code (manual human action).
- Do NOT wait on or reference EB-320 as a blocker.

---

## Phases

### Phase 0 — Worktree setup
- Confirm `.worktrees/` is gitignored.
- Create worktree `.worktrees/feat-EB-322-send-to-kindle-error-e999` on branch `feat/EB-322-send-to-kindle-error-e999` from `master`.
- Install deps if needed; run a clean baseline build/lint to confirm a green starting point.

### Phase 1 — Read-only audit (no edits)
- Read the plan, the origin requirements doc, and the Unit 2 page in full.
- Confirm the 5 target surfaces and the `buildArticleSchema` / `buildFAQPageSchema` signatures in `web_service/frontend/lib/structured-data.ts`.
- Note the existing guide entries in `sitemap.ts`, `llms.txt`, `Footer.tsx`, and the guides hub so the new entries match format exactly.

### Phase 2 — Unit 1: Page component + schema
- Implement `send-to-kindle-error-e999/page.tsx` per plan Unit 1 (metadata, lede ≥300 words, three error-class H2s + diagnostic H3s, honest CTA, `faqItems` → rendered FAQ + FAQPage schema, Article schema, Sources block, author byline, cross-link to Unit 2).
- Verify: route renders; title ≤60 chars; canonical correct; two `<JsonLd>` tags; FAQ/schema parity.

### Phase 3 — Unit 2: Same-PR discoverability hygiene
- Add the new URL to `sitemap.ts` (realistic lastmod/priority matching peers), `public/llms.txt`, a `Footer.tsx` Guides-column link, and a guides-hub card in `guides/page.tsx`.

### Phase 4 — Unit 3: Gates
- Pre-merge: run the two-layer schema validator + link-check; confirm production build is green. Fix any failures before proceeding.
- Capture the validator + link-check output in your report.

### Phase 5 — Commit, push, PR
- `safe-commit` the work on the worktree branch; push; open a PR referencing EB-322.
- Post-merge verification (note in the PR / report for the human to run or confirm): curl-verify the live path (`docs/solutions/eb252-next-plausible-next16-compat.md`), confirm the Vercel production alias updated (`docs/solutions/best-practices/vercel-production-branch-misconfiguration-2026-05-15.md`), and run the EB-292 attribution smoke confirming `referrer` captures `/guides/send-to-kindle-error-e999`.

---

## Report structure (end of session)
1. **What shipped** — files created/modified (should be exactly the 5 surfaces).
2. **Gate output** — schema validator + link-check + build results (actual output, not "passed").
3. **Deviations** — anything that differed from the plan and why.
4. **Deferred / follow-ups** — reciprocal Unit 2 link, auth-failure manual SERP review, the human Position Tracking + trial-cancel actions.
5. **PR link.**

---

## Invocation

```
claude --model sonnet "[EB-322] Build Send-to-Kindle E999 troubleshooting page -- Read prompts/EB-322-send-to-kindle-error-e999.md and follow the instructions"
```
or:
```
claude --model sonnet --prompt-file prompts/EB-322-send-to-kindle-error-e999.md
```
