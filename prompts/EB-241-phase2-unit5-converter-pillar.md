# [EB-241] Phase 2 Unit 5 — Enhance `/convert/pdf-to-kfx` with direction-explicit pillar content

## Model Tier
**Sonnet 4.6** — Long-form content writing + schema additions + careful preservation of an existing live page with payment infrastructure. The work is mechanical but the regression risk surface is the highest of any unit in Phase 2 (Stripe checkout, PDF upload, existing schema stack).

## Plan
Read the full implementation plan at: `docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md` — specifically the Unit 5 spec and the EB-295 plan amendments section (line 604+).

This session executes **only Unit 5** of the plan. Do NOT execute Unit 6, 7, 8, or 9. Stop after Unit 5's verification step passes.

## State at start of this session

- All 4 prior content units shipped (Units 1, 2, 3, 4 at PRs #117, #119, #120, #121)
- **EB-295 infrastructure PR merged** (PR #122 at master `5e6777b`) — this is the foundational policy fix that everything in this session depends on:
  - `tools/check-internal-links.mjs` is wired into `prebuild` — dead internal `<Link>` hrefs now fail the build
  - `buildArticleSchema` in `lib/structured-data.ts` now auto-emits `mainEntityOfPage` from the `url` arg
  - `app/sitemap.ts` has explicit `lastModified` dates for all entries (NO `const now = new Date()`)
  - `public/llms.txt` lists Units 2, 3, 4 under long-form guides
  - All 4 guide pages have Sources footer blocks with `last verified 2026-05-17` dates
- The new EB-295 shipping policy applies: **every page PR ships its own sitemap entry, llms.txt entry, and at least one nav/footer link in the same PR**

Internal links from Unit 5 to other Phase 2 pages will all resolve at PR merge time:
- `/guides/send-to-kindle-not-working` — Unit 2 ✓
- `/guides/how-to-send-pdf-to-kindle` — Unit 3 ✓
- `/guides/kindle-scribe-vs-remarkable` — Unit 4 ✓
- `/guides/pdf-to-kfx-for-kindle-scribe` — long-shipped Scribe guide ✓

## Phase 0 — Branch setup and pre-flight smoke

Per the worktree-management skill:

1. Verify clean master, on `master`, up to date with origin (should be at `5e6777b` or later — look for `fix(EB-295)` commit)
2. Create a worktree branch following the worktree-management skill pattern (matches Units 2-4 convention with `unit5-converter-pillar` slug)
3. Confirm `.worktrees/` is gitignored
4. From the worktree, run `pnpm install` in `web_service/frontend/`
5. **Baseline build check**: `pnpm build` in `web_service/frontend/` must pass before any changes — including the new `check-internal-links.mjs` gate from EB-295

**Phase 0 pre-flight smoke test** (NEW for Unit 5 — required because of regression risk):

6. Run `pnpm dev` and navigate to `http://localhost:3000/convert/pdf-to-kfx`
7. Verify the existing converter widget loads — PDF upload field, file size copy, "Convert" or "Checkout" button visible
8. Spot-check the rendered HTML for the existing schema stack:
   - `grep -oE '"@type":"[^"]*"' .next/server/app/convert/pdf-to-kfx/*.html | sort -u` should return at minimum `"@type":"SoftwareApplication"`, `"@type":"Product"`, `"@type":"FAQPage"`, `"@type":"Question"`
   - The `@id` `https://leafbind.io/#software` MUST be present (this is `SOFTWARE_APP_ID`, the canonical SoftwareApplication entity per EB-272)
   - The `Product` schema MUST have an `image` field (per EB-272 fix)
9. Verify the page's lead paragraph word count BEFORE changes — record the number; Unit 5 should not change this paragraph except to add direction-explicit language if needed
10. Record the existing FAQ item count — Unit 5 extends this; it should not remove or modify existing FAQ entries

**If any pre-flight step fails, STOP** — broken master before any Unit 5 changes is a different problem. Investigate but do not fix in this PR.

## Execution Instructions

1. **Read the current `web_service/frontend/app/convert/pdf-to-kfx/page.tsx`** carefully end-to-end before writing anything. This is an existing live page with payment infrastructure. The Unit 5 work is **additive content + schema** below the existing converter widget. Do NOT restructure the existing converter widget, the existing checkout flow, or the existing schema initialization.

2. **Unit 5 spec from the plan** (line 269+ of the plan doc, search for "Unit 5: Enhance existing"):

   - **Goal**: Capture `convert pdf to kindle format` (720/mo) + `how to convert pdf to kindle format` (260/mo) — combined ~1,000/mo addressable. Page becomes "the canonical place" for both the tool and the comprehensive how-to.
   - **Length**: Add ~2000-3000 words BELOW the existing converter widget. Total page word count after = existing + new.
   - **Target keywords**: `convert pdf to kindle format`, `how to convert pdf to kindle format`. Combined ~1,000 monthly addressable.

3. **Direction-explicit copy is load-bearing** (per Phase 1 discovery — the converter SERP is ~45% bidirectionally contaminated with Kindle→PDF intent):

   - **`<title>`**: Update to declare direction explicitly. Current: "Convert PDF to Kindle (KFX) — Online & Free Tier" (or similar). Change to: "Convert PDF to Kindle Format (KFX): Online Converter for Academic & Multi-Column PDFs" (or your own variant that includes "PDF to Kindle Format" as the key phrase)
   - **H1**: Must include "PDF to Kindle" or "PDF to Kindle Format" — direction stated
   - **Lead paragraph (40-60 words, EB-281 GEO pattern)**: First sentence must declare direction explicitly. Example shape: "leafbind converts PDFs to Kindle format (KFX) online — built for academic papers, footnotes, and multi-column layouts that Send-to-Kindle and Calibre struggle with. This guide explains the conversion process, formats supported, and what to do if you wanted to go the other direction (Kindle → PDF)."
   - **Eat-the-bounce paragraph** (within first 300 words): A short standalone paragraph addressing reverse-direction visitors. Example: "Looking to go the other direction (convert a Kindle book to PDF)? leafbind doesn't do that — try [Calibre with DeDRM](external link with `rel="noopener nofollow"`) for that workflow."

4. **Pillar content structure** (add as new H2 sections below the existing converter widget):

   - H2: How PDF→KFX conversion works (the leafbind pipeline at a high level — extraction, structure detection, KFX assembly)
   - H2: File formats leafbind accepts (PDF, EPUB, DOCX, etc. — verify against your current pipeline support, not against assumptions)
   - H2: What about multi-column PDFs? **Cite the Calibre manual on multi-column-unsupported as the gold-standard E-E-A-T differentiation per [eb258-seo-phase1-patterns.md](docs/solutions/eb258-seo-phase1-patterns.md)**. This is the load-bearing competitor-quote section.
   - H2: What about academic papers with footnotes? (showcase leafbind's footnote preservation; reference the EB-241 Phase 1 positioning)
   - H2: Why not just use Calibre? (honest comparison — leafbind is the easier path, Calibre is the power-user path)
   - H2: Why not just Send-to-Kindle? (file size limits, formatting losses) — internal link to Unit 3 mega-guide
   - H2: Common Send-to-Kindle failures (internal link to Unit 2 pain pillar)
   - FAQ extension: PRESERVE existing FAQ items unchanged; ADD 3-5 new ones targeting direction-explicit queries ("Can I convert PDF to Kindle for free?", "Does this work on Mac?", "What's the difference between KFX and AZW3?", etc.)

5. **Schema preservation + Article addition**:

   - **PRESERVE** existing `SoftwareApplication` schema unchanged. Must keep `@id: SOFTWARE_APP_ID`. Do NOT introduce a duplicate SoftwareApplication.
   - **PRESERVE** existing `Product` schema unchanged. Must keep `image` field (per EB-272).
   - **EXTEND** existing `FAQPage` schema — append new FAQ items to the existing array. Do not refactor the FAQ pattern.
   - **ADD** new `Article` schema via `buildArticleSchema(...)` from the post-EB-295 builder. Pass the canonical URL as `url` so `mainEntityOfPage` emits. The `headline` is the page's H1; `datePublished` is today; `dateModified` is today; `author` is leafbind; `publisher` is leafbind (use `SOFTWARE_APP_ID` for the entity reference if applicable).
   - **Schema rendering**: stack `<JsonLd schema={...} />` components in the same order as existing pages (look at Unit 2's pattern for reference, post-EB-295 patched version).

6. **EB-295 policy compliance (REQUIRED, same-PR shipping)**:

   - **Bump `app/sitemap.ts`**: the `/convert/pdf-to-kfx` entry already exists. Update its `lastModified` to today's date (`new Date("2026-05-17")` or whatever today is — explicit date, NO `new Date()`). Bump the `priority` if appropriate (current is probably 0.9; leave at 0.9 unless there's a strong reason to change).
   - **Update `public/llms.txt`**: the `/convert/pdf-to-kfx` entry already exists. Update its one-line description if the page's positioning has materially changed (e.g., it's no longer "converter landing only" but "converter + pillar guide"). Do NOT add a duplicate entry.
   - **CI link-check (`tools/check-internal-links.mjs`)**: must pass — verify each new internal `<Link href="/...">` you add resolves to a real `page.tsx`. All 4 prior content units are live + indexed, so Pain/Mega/Comparison/Scribe links will all pass.
   - **Sources footer** required for any Calibre or Amazon claims you make in the new content. Cite canonical sources (calibre-ebook.com/manual for the multi-column quote, amazon.com/sendtokindle for Send-to-Kindle facts) with `last verified YYYY-MM-DD` date.

7. **Reference templates** (post-EB-295 patched versions on master):
   - `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx` — Unit 2 with Sources footer + mainEntityOfPage. Closest schema profile (Article + FAQPage) for the patterns Unit 5 will add.
   - `web_service/frontend/app/(marketing)/guides/how-to-send-pdf-to-kindle/page.tsx` — Unit 3 with mega-guide structure (similar word count target as Unit 5's additions).
   - `web_service/frontend/app/(marketing)/guides/kindle-scribe-vs-remarkable/page.tsx` — Unit 4 with restrained tone and Sources footer.

8. **Design system** (unchanged from prior units):
   - `font-serif` (Newsreader) for H1/H2/H3, `font-sans` (DM Sans) body, `font-mono` (IBM Plex Mono) eyebrow
   - Brand-green palette only via tokens — token drift guard runs in `prebuild` and will fail on hand-rolled hex
   - AI-slop checklist: no gradient-mesh, no glassmorphism, no slate/indigo/zinc, no urgency copy, single primary CTA (the existing converter widget is the CTA — don't add another)

## Verification Before Commit (heavier than prior units)

### Standard EB-295 policy gates (same as Units 2-4 would be under new policy)

1. `pnpm build` in `web_service/frontend/` passes with no TypeScript errors
2. `tools/check-token-drift.mjs` (prebuild) passes — no hand-rolled hex colors
3. `tools/check-internal-links.mjs` (prebuild) passes — no dead internal `<Link>` hrefs
4. Lead paragraph word count 40-60
5. FAQ item count: existing count + 3-5 new (not less, not modifying existing)
6. New Article schema's `mainEntityOfPage` present in built HTML
7. Sources footer present for any Calibre/Amazon claims with explicit `last verified YYYY-MM-DD`
8. `app/sitemap.ts` `/convert/pdf-to-kfx` `lastModified` bumped to today
9. `public/llms.txt` `/convert/pdf-to-kfx` description updated if positioning changed

### Direction-explicit copy gates (Unit 5 specific)

10. **H1, `<title>`, and lead paragraph all contain "PDF to Kindle" or "PDF to Kindle Format"** — grep check: `grep -nE 'PDF to Kindle' page.tsx` should match at least these three locations
11. **Eat-the-bounce paragraph present within first ~300 words** — short paragraph addressing reverse-direction visitors with `rel="noopener nofollow"` external link to Calibre+DeDRM

### Schema preservation gates (Unit 5 specific — REGRESSION RISK)

12. **`SoftwareApplication` schema unchanged**: `@id: SOFTWARE_APP_ID` present, all existing fields intact. Diff the schema object before/after to confirm no fields were lost or modified.
13. **`Product` schema unchanged**: `image` field present (per EB-272), all existing fields intact. Diff before/after.
14. **`FAQPage` schema extended, not replaced**: existing FAQ items preserved in `mainEntity` array; new items appended. Count must equal old count + new count.
15. **New `Article` schema added** via `buildArticleSchema()` — confirms `mainEntityOfPage` auto-emits.
16. **Schema render order in JSX**: existing JsonLd render order unchanged; new Article JsonLd appended (do not insert in the middle of the existing stack).

### Live converter regression gates (Unit 5 specific — REGRESSION RISK)

17. Run `pnpm dev` and load `http://localhost:3000/convert/pdf-to-kfx`
18. **PDF upload widget still renders and accepts a file** (drag-and-drop or click-to-select — pick whichever the existing UI supports, verify it works)
19. **Checkout button still present** and routes to the Stripe checkout session creation endpoint (do NOT actually pay — verify the route by looking at the button's `onClick` handler, `formAction`, or network request after click)
20. **Page renders without console errors** — open DevTools, check for React errors, hydration errors, or 404 network requests
21. **Mobile rendering** at viewport 375px — converter widget still functional, new content readable

### Plan-vs-implementation diff check (Unit 5 specific — Finding 4 process gate)

22. Compare the implemented page against the plan's Unit 5 spec (line 269+):
    - All required H2 sections present?
    - Word count target met (~2000-3000 added)?
    - All required internal links present?
    - Calibre manual quote present in the "multi-column PDFs" section?
    - Eat-the-bounce paragraph present?
    - Direction-explicit copy in H1, title, lede?

If verification fails on ANY gate, STOP — do not commit. Diagnose, fix, re-verify.

## Commit + Push + PR

After verification passes:

1. Stage the files this PR touches:
   - `web_service/frontend/app/convert/pdf-to-kfx/page.tsx` (main content + schema additions)
   - `web_service/frontend/app/sitemap.ts` (lastModified bump)
   - `web_service/frontend/public/llms.txt` (description update if applicable)
2. Commit with this message structure:
   ```
   feat(EB-241): Phase 2 Unit 5 — direction-explicit pillar content on /convert/pdf-to-kfx

   Enhances the live /convert/pdf-to-kfx converter page with ~2,500 words
   of pillar content + new Article schema. Targets convert pdf to kindle
   format (720/mo) and how to convert pdf to kindle format (260/mo) —
   combined ~1,000/mo addressable.

   Direction-explicit copy in title, H1, and lead paragraph addresses
   the ~45% bidirectional intent contamination identified in Phase 1.
   Eat-the-bounce paragraph in first 300 words redirects Kindle->PDF
   visitors to Calibre+DeDRM (we don't do that direction).

   New content (below existing converter widget):
   - How PDF->KFX conversion works (leafbind pipeline at high level)
   - File formats supported
   - Multi-column PDFs (Calibre manual quote — EB-258 E-E-A-T pattern)
   - Academic papers + footnotes
   - Why not Calibre / Send-to-Kindle (honest comparison + internal links)
   - FAQ extension: existing items preserved + 4 new direction-explicit
     items appended

   Schemas: SoftwareApplication (@id SOFTWARE_APP_ID) PRESERVED unchanged.
   Product (with EB-272 image field) PRESERVED unchanged. FAQPage extended
   (existing items preserved, new items appended). New Article schema added
   via buildArticleSchema (auto-emits mainEntityOfPage per EB-295).

   Ships under post-EB-295 policy: sitemap.ts lastModified bumped, llms.txt
   description updated, CI link-check passes, Sources footer for Calibre
   and Amazon claims with last-verified date.

   Existing converter widget functionality preserved — PDF upload, Stripe
   checkout, KFX download flow unchanged. Pre-flight smoke and post-change
   smoke both clean.

   Plan: docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md
   ```
3. Push to `origin` and open a PR titled `feat(EB-241): Phase 2 Unit 5 — direction-explicit pillar content on /convert/pdf-to-kfx`
4. PR body must include:
   - Plan path reference
   - EB-241 ticket link
   - Vercel preview URL once available
   - Explicit "Regression smoke test" section confirming PDF upload + Stripe checkout route still work (so reviewers can see you tested this)
5. After merge: post a comment to EB-241 (Atlassian MCP `addCommentToJiraIssue`, `cloudId: jlfowler1084.atlassian.net`) with the PR link and Unit 5 completion status

## Key Constraints (post-EB-295 policy)

- **Do NOT modify the existing converter widget UI** (PDF upload, Stripe checkout button, KFX download flow) — additive content only
- **Do NOT modify the existing `SoftwareApplication` or `Product` schema objects** — preserve them byte-for-byte unless you have a specific reason documented in the PR
- **Do NOT change the `SOFTWARE_APP_ID` value** — `https://leafbind.io/#software` is canonical per EB-272
- **Do NOT remove or modify existing FAQ items** — extend only
- **Do NOT change the existing checkout route or Stripe integration** — additive content only
- **Do NOT write any other content pages** (Unit 6 update, Unit 7 batched fixes, etc.)
- **Do NOT skip the eat-the-bounce paragraph** — it's the load-bearing mitigation for the bidirectional intent contamination
- **Do NOT skip the Calibre manual quote** — it's the gold-standard E-E-A-T differentiator per EB-258
- **Do NOT use `const now = new Date()`** in sitemap.ts — explicit dates only (EB-295 Finding 5)
- **Do NOT skip the Sources footer** for Calibre and Amazon claims
- **Do NOT hand-roll hex colors** — brand tokens only (token drift guard will fail the build)
- **Do NOT pad word count** to 2,000-3,000 — write what the content needs. If the natural addition is 1,800 words and complete, ship it; if it's 3,200, ship it.
- **Do NOT add a second primary CTA** — the existing converter widget IS the CTA; new content links to internal pages or external sources as supporting context
- **Do NOT commit `.worktrees/` artifacts**

## Stop Conditions

Stop and post a comment to EB-241 explaining the blocker if:
- **Pre-flight smoke fails on master before any changes** — broken master is a separate problem; investigate but do not fix in this PR
- **The existing `SoftwareApplication` or `Product` schema diverges from EB-272 expectations** (e.g., `image` field missing on Product, `@id` not `SOFTWARE_APP_ID` on SoftwareApplication) — this would be a separate bug to fix
- **The existing converter widget functionality breaks during dev testing** — back out the change, diagnose; do NOT ship a PR that breaks Stripe checkout
- **The plan's Unit 5 spec contradicts the existing converter page structure** in a way that makes additive content impossible without restructuring (e.g., the existing schema is hand-rolled in a way that conflicts with buildArticleSchema) — pause and ask
- **Calibre manual structure has changed** since the EB-258 reference (multi-column section moved, quote text different) — find the current canonical source and cite that instead
- **Word count target is impossible to hit** without padding (the natural content is much shorter or much longer than 2,000-3,000) — ship the natural length and note in the PR description; the target is a range, not a quota

## Invocation

To execute in a fresh Sonnet session:

```bash
claude --model sonnet --prompt-file prompts/EB-241-phase2-unit5-converter-pillar.md
```

Or in the existing warm Sonnet session:

> Unit 5 is next. Read `prompts/EB-241-phase2-unit5-converter-pillar.md` and execute. EB-295 infrastructure merged at `5e6777b`. This is the highest-regression-risk unit — the prompt has extra verification gates for the live `/convert/pdf-to-kfx` page (Stripe checkout + PDF upload). Pre-flight smoke is required before any changes. The work is additive content + Article schema only — preserve the existing converter widget byte-for-byte.
