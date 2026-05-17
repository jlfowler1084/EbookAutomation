# [EB-241] Phase 2 Unit 6 — Update `/guides/pdf-to-kfx-for-kindle-scribe` with transfer-flow expansion

## Model Tier
**Sonnet 4.6** — Small additive edit to an existing well-structured guide. Lowest-risk content unit of Phase 2.

## Plan
Read the Unit 6 spec at `docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md` (search for "Unit 6: Update existing"). Also read the EB-295 plan amendment section (line 604+).

This session executes **only Unit 6**. Stop after Unit 6's verification step passes. Do NOT start Unit 7 or Unit 9.

## State at start of this session

The remaining-Phase-2 picture has shifted since the plan was written. Current shipped state on master:

- **Unit 1** (schema builders) ✓ merged PR #117, then revised in EB-295 PR #122 to add `mainEntityOfPage`
- **Unit 2** (pain pillar `/guides/send-to-kindle-not-working`) ✓ merged PR #119, then patched in EB-295 PR #122 (Sources footer + Amazon facts)
- **Unit 3** (mega-guide `/guides/how-to-send-pdf-to-kindle`) ✓ merged PR #120, then patched in EB-295 PR #122
- **Unit 4** (comparison hub `/guides/kindle-scribe-vs-remarkable`) ✓ merged PR #121, then patched in EB-295 PR #122
- **EB-295 infrastructure** ✓ merged PR #122 (CI link-check gate, `mainEntityOfPage` in builder, sitemap freshness fix, etc.)
- **Unit 5** (converter pillar enhancement on `/convert/pdf-to-kfx`) ✓ merged PR #127 at `d8c37f8`
- **Unit 8 equivalent shipped under EB-296** PR #126 — added `/guides` hub page + footer Guides column. Unit 8 in the plan is effectively complete; do NOT re-do this work.
- **EB-299** PR #125 anchored homepage upload widget at `/#convert`. Affects internal-link targets if the new Unit 6 sections reference the homepage CTA.

Internal links from Unit 6 to other Phase 2 pages will all resolve at PR merge time:
- `/guides/send-to-kindle-not-working` — Unit 2 ✓
- `/guides/how-to-send-pdf-to-kindle` — Unit 3 ✓
- `/guides/kindle-scribe-vs-remarkable` — Unit 4 ✓
- `/convert/pdf-to-kfx` — Unit 5 (now also a pillar) ✓
- `/guides` — new hub page from EB-296 ✓

## What this session ships

Update the existing `web_service/frontend/app/(marketing)/guides/pdf-to-kfx-for-kindle-scribe/page.tsx` to:

1. Add a new H2 section covering the transfer-flow workflow (downloading the converted KFX and getting it onto the Scribe device)
2. Add 2-3 new FAQ items targeting the Scribe-specific transfer queries
3. Update the "Related" pill row at the bottom to include all 4 Phase 2 sibling pages (pain pillar, mega-guide, comparison hub, converter pillar) + the new `/guides` hub
4. Bump `PUBLISHED` const + `dateModified` schema property to today's date
5. Update `app/sitemap.ts` to bump the Scribe guide's `lastModified` to today

**This is an additive, low-risk update**. The Scribe guide has been touched twice recently:
- EB-281 extended the lead paragraph from 32 → 55 words (PRESERVE this)
- EB-295 PR #122 added `mainEntityOfPage` to the hand-rolled ArticleSchema + added a Sources footer with `last verified 2026-05-17` (PRESERVE both)

## Phase 0 — Branch setup

Per the worktree-management skill:

1. Verify clean master, on `master`, up to date with origin (HEAD should be at `d8c37f8` or later — look for `feat(EB-241): Phase 2 Unit 5` commit)
2. Create a worktree branch following the worktree-management skill pattern with `unit6-scribe-guide-update` slug
3. Confirm `.worktrees/` is gitignored
4. From the worktree, run `pnpm install` in `web_service/frontend/`
5. Baseline check: `pnpm build` in `web_service/frontend/` passes — including the EB-295 `check-internal-links.mjs` gate

## Execution Instructions

### Target keywords

- `send pdf to kindle scribe` (110/mo, KD 47 — hardest in the Phase 2 set; Amazon dominates the SERP)
- `how to send pdf to kindle scribe` (70/mo, KD 25)

Combined ~180/mo addressable. Smaller volume than other units, but this completes the Scribe-specific intent funnel from "convert" → "transfer to device".

### 1. Read the existing file end-to-end first

Open `web_service/frontend/app/(marketing)/guides/pdf-to-kfx-for-kindle-scribe/page.tsx`. The file is structured as: image manifest comment header → `PUBLISHED`/`SLUG`/`CANONICAL` consts → schema objects → FAQ items array → JSX render. Identify:

- Where the existing H2 sections end (so you know where to insert the new transfer-flow H2)
- The exact FAQ array shape (so new items match)
- The existing "Related" pill row (so the update is surgical)
- The schema objects' existing structure (so the additions to HowTo `step` array and FAQPage `mainEntity` array match the existing pattern)
- The current `PUBLISHED` value (so you can bump it correctly)

### 2. Add the new H2 section

Suggested heading: **"How to actually send your converted KFX to the Kindle Scribe"** (or your own variant that targets the transfer-flow keywords without keyword-stuffing).

Suggested content (~300-500 words):

- H3: Method 1 — Send-to-Kindle Email (the Amazon-native path)
  - Drop the KFX into the Send-to-Kindle email (your `kindle.com` address)
  - Mention the 200 MB cap (verified in EB-295 — same as the cap on Unit 3's mega-guide)
  - Wait for the email confirmation; file appears in your Kindle library
- H3: Method 2 — USB cable transfer (the deterministic path)
  - Plug Scribe into computer, mount as drive, copy KFX into the `documents/` folder
  - Eject, unplug, file appears in Kindle library
- H3: Common transfer failures
  - File doesn't appear — check approved-sender list (link to Unit 2 pain pillar)
  - File appears but won't open — usually a KFX vs AZW3 mismatch; leafbind exports KFX which works
  - Email never confirms — Amazon server issue; try USB fallback or re-send

Include at least one internal link to:
- Unit 2 pain pillar (`/guides/send-to-kindle-not-working`) — for the "common failures" subsection
- Unit 3 mega-guide (`/guides/how-to-send-pdf-to-kindle`) — for "all methods for all file types"
- Unit 4 comparison hub (`/guides/kindle-scribe-vs-remarkable`) — if the section mentions device choice
- Unit 5 converter pillar (`/convert/pdf-to-kfx`) — if it isn't already linked elsewhere in the guide

### 3. Extend the FAQ array

Add 2-3 new FAQ items targeting Scribe-transfer-specific queries. Suggestions (use these or write your own):

- "How do I send a PDF to my Kindle Scribe?" → directs to the transfer-flow section
- "Why does my PDF look wrong on the Kindle Scribe after sending?" → leafbind angle: PDFs sent without conversion lose formatting; convert with leafbind first
- "Can I send a large PDF to the Kindle Scribe?" → 200 MB cap, leafbind premium tier handles 100 MB conversions

PRESERVE existing FAQ items unchanged. Append new ones to the array.

### 4. Update the "Related" pill row

The existing Related pill row at the bottom of the guide currently links to `/convert/*`, `/quality`, `/pricing` (per the repo audit done during planning). Update it to include all 4 Phase 2 sibling pages plus the new `/guides` hub from EB-296:

- `/guides/send-to-kindle-not-working` (Unit 2)
- `/guides/how-to-send-pdf-to-kindle` (Unit 3)
- `/guides/kindle-scribe-vs-remarkable` (Unit 4)
- `/convert/pdf-to-kfx` (Unit 5 — converter pillar, already-existing target)
- `/guides` (EB-296 hub page)

Keep the existing `/quality` and `/pricing` links if they're there. Use the existing pill styling (border + rounded-sm + brand tokens) — don't invent a new component.

### 5. Bump dates

- Update `PUBLISHED` const to today (`"2026-05-17"` or whatever today is — check)
- Update the Article schema's `dateModified` to today (it's hand-rolled; find the assignment line)
- Update `app/sitemap.ts`: bump the `/guides/pdf-to-kfx-for-kindle-scribe` entry's `lastModified` to today (explicit `new Date("YYYY-MM-DD")` — NO `new Date()`)

### 6. EB-295 policy compliance (post-PR #122)

- **Sources footer block** — already exists from PR #122 (`last verified 2026-05-17`). If you make any new third-party claims (Amazon 200 MB cap, etc.) that aren't already cited, extend the Sources footer with the canonical URL. Don't introduce a parallel/duplicate Sources block.
- **CI link-check** — will automatically run in prebuild. All your new internal `<Link>` hrefs should resolve since all 4 Phase 2 pages + `/guides` are live.
- **`mainEntityOfPage`** — already present on the existing ArticleSchema from PR #122. Preserve.

## Verification Before Commit

### Standard EB-295 policy gates

1. `pnpm build` in `web_service/frontend/` passes with no TypeScript errors
2. `tools/check-token-drift.mjs` (prebuild) passes
3. `tools/check-internal-links.mjs` (prebuild) passes — verify new internal links resolve
4. `app/sitemap.ts` `/guides/pdf-to-kfx-for-kindle-scribe` `lastModified` updated to today (explicit date)
5. No new `const now = new Date()` patterns introduced anywhere

### Unit 6 specific gates

6. **EB-281 extended lead paragraph (55 words) preserved unchanged** — `grep -c "^.* leafbind" page.tsx` should match the lede in the same position
7. **EB-295 Sources footer preserved** — confirm the `last verified 2026-05-17` block is still in the file. If you added a new Amazon claim, extend the footer; do not replace it.
8. **EB-295 `mainEntityOfPage` preserved** in the Article schema
9. **FAQ count = existing + 2-3 new** (do not remove or modify existing items)
10. **New H2 section present** below the existing content (not inserted between existing sections in a way that disrupts the narrative)
11. **Related pill row updated** to include all 4 Phase 2 siblings + `/guides`
12. **`PUBLISHED` const + Article schema `dateModified` both bumped to today**
13. **Schema validation**: `grep -oE '"@type":"[^"]*"' .next/server/.../page.html | sort -u` shows the existing stack (Article, FAQPage, HowTo, Question, HowToStep, WebPage from mainEntityOfPage) — no new `@type`s introduced
14. **HowTo `step` array unchanged in length** (if you didn't add a new HowToStep) OR **HowTo step count = existing + new** if you added transfer-flow steps to it

### Plan-vs-implementation check (EB-295 Finding 4 process gate)

15. The plan's Unit 6 spec says "Add a new H2 section" + "2-3 new FAQ items" + "update Related pill row" + "bump PUBLISHED + dateModified". Verify all four are done.

If verification fails on any gate, STOP — do not commit. Diagnose, fix, re-verify.

## Commit + Push + PR

After verification passes:

1. Stage the files this PR touches:
   - `web_service/frontend/app/(marketing)/guides/pdf-to-kfx-for-kindle-scribe/page.tsx`
   - `web_service/frontend/app/sitemap.ts`
2. Commit with this message structure:
   ```
   feat(EB-241): Phase 2 Unit 6 — Scribe guide transfer-flow expansion

   Extends the existing /guides/pdf-to-kfx-for-kindle-scribe guide with
   a transfer-flow section covering Send-to-Kindle Email + USB cable
   paths from converted KFX to the Scribe device. Targets send pdf to
   kindle scribe (110/mo) + how to send pdf to kindle scribe (70/mo).

   Changes:
   - New H2 section "How to actually send your converted KFX to the
     Kindle Scribe" with 3 H3 subsections (email path, USB path,
     common failures)
   - FAQ array extended with 3 new transfer-specific items; existing
     items preserved unchanged
   - Related pill row updated to include all 4 Phase 2 siblings
     (pain pillar, mega-guide, comparison hub, converter pillar) plus
     the EB-296 /guides hub
   - PUBLISHED const + Article schema dateModified bumped to today
   - sitemap.ts lastModified bumped

   Preserved (do not regress):
   - EB-281 55-word extended lead paragraph
   - EB-295 Sources footer block (last verified 2026-05-17)
   - EB-295 mainEntityOfPage on Article schema
   - All existing schema entities and FAQ items

   Plan: docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md
   ```
3. Push to `origin` and open a PR titled `feat(EB-241): Phase 2 Unit 6 — Scribe guide transfer-flow expansion`
4. PR body must reference the plan, the EB-241 ticket, and the Vercel preview URL
5. After merge: post a comment to EB-241 (Atlassian MCP `addCommentToJiraIssue`, `cloudId: jlfowler1084.atlassian.net`) with the PR link and Unit 6 completion status

## Key Constraints

- **Do NOT modify the existing EB-281 extended lead paragraph** (preserve the 55-word version)
- **Do NOT modify the existing EB-295 Sources footer** (preserve it; extend only if new claims warrant it)
- **Do NOT remove or modify existing FAQ items, HowTo steps, or schema entities** — additive only
- **Do NOT restructure the existing page** — append the new H2 in a coherent position (likely near the end of the body content, before the FAQ section or before the "Related" pills)
- **Do NOT use `const now = new Date()`** in sitemap.ts
- **Do NOT add new schema entities** — extend existing Article/FAQPage/HowTo by adding to their arrays
- **Do NOT hand-roll hex colors**
- **Do NOT pad word count** — the natural addition is ~300-500 words; if it's slightly shorter or longer, that's fine
- **Do NOT touch other guide pages, the converter page, or shared components**
- **Do NOT start Unit 7 or Unit 9** in this session

## Stop Conditions

Stop and post a comment to EB-241 if:
- The Scribe guide structure has changed significantly since the planning (e.g., a recent PR refactored the FAQ pattern or schema initialization)
- The EB-281 extended lead paragraph is no longer 55 words on master (someone bumped it; preserve whatever is there)
- The EB-295 Sources footer is missing on master (a regression — flag it and pause)
- Amazon's 200 MB cap claim has changed (verify against amazon.com/sendtokindle if you cite it)
- `pnpm build` baseline fails before any changes

## Invocation

In a fresh Sonnet session:

```bash
claude --model sonnet --prompt-file prompts/EB-241-phase2-unit6-scribe-guide-update.md
```

Or to the warm Sonnet session:

> Unit 6 is next. Read `prompts/EB-241-phase2-unit6-scribe-guide-update.md` and execute. Unit 5 merged at `d8c37f8`. This is the smallest content unit — a transfer-flow addition to the existing Scribe guide. Preserve the EB-281 lede, the EB-295 Sources footer, and all existing FAQ/HowTo items. Append only.
