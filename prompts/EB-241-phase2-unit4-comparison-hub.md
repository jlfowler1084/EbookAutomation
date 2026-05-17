# [EB-241] Phase 2 Unit 4 — "Kindle Scribe vs reMarkable vs iPad vs Paperwhite" comparison hub

## Model Tier
**Sonnet 4.6** — Long-form content writing + structured-data emission + accurate device-specification research, all following a clear plan spec. Mechanical work with one research step (verify current device specs against vendor pages).

## Plan
Read the full implementation plan at: `docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md`

This session executes **only Unit 4** of the plan. Do NOT execute Units 5-9 — they ship in separate PRs. Stop after Unit 4's verification step passes.

## State at start of this session

- Unit 1 (schema builders) ✓ shipped via PR #117, merged at `b0b6fe4`. Builders live in `web_service/frontend/lib/structured-data.ts`.
- Unit 2 (pain pillar `/guides/send-to-kindle-not-working`) ✓ shipped via PR #119, merged at `a1ff945`.
- Unit 3 (mega-guide `/guides/how-to-send-pdf-to-kindle`) ✓ shipped via PR #120 (verify merge state at session start — if still open, merge it before starting Unit 4 work so the internal link from Unit 4 resolves cleanly). Merge command: `gh pr merge 120 --squash --delete-branch`.

This page references all three prior units as internal links:
- Pain pillar (`/guides/send-to-kindle-not-working`) — confirmed shipped
- Mega-guide (`/guides/how-to-send-pdf-to-kindle`) — confirmed shipped or merging now
- Scribe guide (`/guides/pdf-to-kfx-for-kindle-scribe`) — long-shipped reference

All three internal links should resolve at PR merge time. No documented-404 exceptions for this page.

## Phase 0 — Branch setup

Per the plan's "One worktree per PR" decision and the [`worktree-management` skill](~/.claude/skills/worktree-management/SKILL.md):

1. Verify clean master, on `master`, up to date with origin
2. If PR #120 is still open at session start: `gh pr merge 120 --squash --delete-branch`, then `git pull origin master`
3. Create a worktree branch following the worktree-management skill (matches the pattern from Units 2 and 3, with `unit4-comparison-hub` or `unit4-kindle-scribe-vs-remarkable` slug)
4. Confirm `.worktrees/` is gitignored
5. From the worktree, run `pnpm install` in `web_service/frontend/`
6. Baseline check: `pnpm build` in `web_service/frontend/` should pass before any changes

## Execution Instructions

1. Read the full plan, then re-read **Unit 4** specifically. Key Unit 4 specs:

   - **Slug**: `kindle-scribe-vs-remarkable` (matches the 2,900/mo crown-jewel query — also the largest single keyword in the entire Phase 2 set)
   - **Title**: "Kindle Scribe vs reMarkable vs iPad vs Paperwhite: Which Is Best for Reading PDFs?"
   - **Target keywords**: `kindle scribe vs remarkable` (2,900), `kindle scribe vs ipad` (590), `kindle scribe vs paperwhite` (320). Combined ~3,810 monthly addressable.
   - **Length**: 3,000-4,500 words (centerpiece is a detailed comparison table; surrounding prose explains use-case-specific tradeoffs)
   - **Lead paragraph (40-60 words, EB-281 GEO pattern)**: direct-answer (best for academic PDFs vs. best for marginalia vs. best for general reading), named devices, with leafbind positioning as device-agnostic
   - **Structure**:
     - H1 + lead paragraph
     - **TL;DR** — 3-bullet verdict ("If you want X, get Y")
     - **Comparison table** — 5-7 columns × 5 device rows. Columns: Display, Note-taking, PDF readability, Price tier (NOT $-pricing), Battery, Ecosystem lock-in, File format support. Rows: Kindle Scribe, Kindle Paperwhite, Kindle Scribe Colorsoft, reMarkable Paper Pro, iPad (10th gen + Pro).
     - H2: For reading academic PDFs (the leafbind sweet spot)
     - H2: For marginalia / note-taking
     - H2: For general fiction / book reading
     - H2: For multi-column PDFs (where Scribe + Calibre fails — leafbind angle)
     - H2: **The PDF problem affects all of these devices** (positioning leafbind as the answer regardless of device choice — this is the load-bearing section)
     - FAQ (≥5: "Can the Scribe handle multi-column PDFs?", "Is the iPad worth it just for PDFs?", "Does the reMarkable work with Kindle's ecosystem?", "Will my PDFs look good on a 6-inch Paperwhite?", etc.)
   - **Schemas**: `buildArticleSchema(...)` + `buildFAQPageSchema(...)`. **No HowTo** (comparison pages don't fit HowTo). **No Product** (devices aren't leafbind's products — emitting Product schema for Amazon/Apple/reMarkable hardware would be misleading and could trigger Google's misleading-content signal).
   - **Internal links** (minimum 3): `/convert/pdf-to-kfx` (commercial intent funnel), `/guides/how-to-send-pdf-to-kindle` (Unit 3, shipped), `/guides/pdf-to-kfx-for-kindle-scribe` (Scribe guide). Optional: `/guides/send-to-kindle-not-working` (Unit 2) if pain-pillar mention fits naturally.
   - **External links** (minimum 1 per device discussed): Amazon Scribe product page, Amazon Paperwhite product page, reMarkable Paper Pro product page, Apple iPad page. **All external retail links MUST use `rel="noopener nofollow"`** — this is different from prior units where external links were primary sources (Amazon help docs, Calibre manual). For retail product pages we explicitly don't want to pass PageRank or implicitly endorse competitor purchase paths.
   - **File**: `web_service/frontend/app/(marketing)/guides/kindle-scribe-vs-remarkable/page.tsx`

2. **Reference templates from prior shipped units**:
   - `web_service/frontend/app/(marketing)/guides/pdf-to-kfx-for-kindle-scribe/page.tsx` — original reference (image manifest, consts, schemas, FAQ pattern)
   - `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx` — Unit 2 (Article + FAQPage stack, no HowTo — matches Unit 4's schema profile)
   - `web_service/frontend/app/(marketing)/guides/how-to-send-pdf-to-kindle/page.tsx` — Unit 3 (long-form mega-guide structure — Unit 4 is similar in length but different in shape since it has a table-centric layout instead of method-step layout)

   **Unit 4 is most structurally similar to Unit 2** in schema profile (Article + FAQPage, no HowTo), but most similar to Unit 3 in length and depth.

3. **The framing rule is load-bearing** (from Phase 1 discovery doc):
   > "leafbind isn't selling a device. The comparison content should be product-agnostic on device choice and product-evangelizing on PDF handling. This avoids competing with Amazon's affiliate ecosystem and avoids the trust-signal problem of 'obviously biased' comparison content."

   This means:
   - Don't pick a "winner" device — pick a winner for each use case (academic / marginalia / general reading / multi-column)
   - Don't dismiss any device — every device has a legitimate use case for some audience
   - Be honest about Scribe's weaknesses (multi-column PDFs, e-ink refresh rate) and reMarkable's weaknesses (no Kindle ecosystem, smaller library), iPad's weaknesses (glossy screen for long reading, battery, weight), Paperwhite's weaknesses (no note-taking, smaller screen)
   - The bias is toward "whatever device you pick, leafbind helps with the PDF part" — that's the angle the "The PDF problem affects all of these devices" H2 makes concrete

4. **GEO / AI Overview citation pattern** (from EB-281 + EB-258):
   - Lead paragraph 40-60 words with direct-answer + named devices in the first sentence
   - Include at least one standalone 134-167-word passage block — natural location is the "For reading academic PDFs" section or the "PDF problem affects all of these" section
   - Quote primary sources where possible (Amazon's Scribe product specs page, reMarkable's documentation on PDF support)

5. **Comparison table is the centerpiece** — invest care in:
   - Mobile responsiveness (test at viewport ≤375px — the table is the FIRST thing that breaks on mobile)
   - Accurate specs (verify current Amazon Scribe page, reMarkable Paper Pro page, etc. — device specs change; the plan was written 2026-05-16 and may already be slightly stale)
   - Use brand tokens for cell colors (no hand-rolled hex)
   - Headers use `font-mono text-sm font-medium text-text-muted uppercase tracking-widest` (eyebrow pattern) OR `font-serif` for column headers — match an existing pattern, don't invent
   - Symbols for table cells: ✓ supported, ⚠ supported-with-caveat, ✗ not-supported, or use brief text — pick one convention and stick to it

6. **Design system constraints** (from EB-233):
   - Typography: `font-serif` (Newsreader) for H1/H2/H3, `font-sans` (DM Sans) body, `font-mono` (IBM Plex Mono) eyebrow
   - Colors: brand-green palette only — `bg-brand`, `text-text-base`, `text-text-muted`, `text-accent`, `border-border`, `bg-surface`
   - AI-slop checklist: no gradient-mesh, no glassmorphism, no slate/indigo/zinc, no urgency copy, single primary CTA
   - Token drift guard runs in `prebuild` — will fail the build on hand-rolled hex

## Verification Before Commit

1. `pnpm build` in `web_service/frontend/` passes with no TypeScript errors
2. `tools/check-token-drift.mjs` (runs in `prebuild`) still passes
3. Page renders at `http://localhost:3000/guides/kindle-scribe-vs-remarkable` (run `pnpm dev`, verify visually — especially the comparison table at mobile widths)
4. **Schema validation**: count `@type` occurrences with `grep -oE '"@type":"[^"]*"' | sort -u` (per the JSON-LD Turbopack collapse gotcha). Expect: `"@type":"Article"`, `"@type":"FAQPage"`, `"@type":"Question"` (within FAQPage). **Do NOT expect HowTo** — this page intentionally omits HowTo schema.
5. Lead paragraph word count 40-60
6. FAQ items ≥5
7. **All external retail product links use `rel="noopener nofollow"`** — grep the file to confirm: `grep -oE 'rel="[^"]*"' page.tsx | sort -u`. The `nofollow` qualifier is the load-bearing difference from prior units.
8. **No $ pricing in copy** — `grep -E '\$[0-9]' page.tsx` should return nothing
9. **Internal links resolve** — verify each `Link href="/guides/..."` and `Link href="/convert/..."` target exists in the current codebase (Unit 3's mega-guide is the most recent — ensure its slug matches `how-to-send-pdf-to-kindle`)
10. Comparison table mobile-responsive (test at 320px, 375px, 414px)
11. Visual smoke: AI-slop checklist passes; brand tokens used; Newsreader for H1/H2

If verification fails, STOP — do not commit. Diagnose, fix, re-verify.

## Commit + Push + PR

After verification passes:

1. Stage only the new page file. Do NOT update `sitemap.ts` or `llms.txt` (batched in Unit 7).
2. Commit with this message structure:
   ```
   feat(EB-241): Phase 2 Unit 4 — kindle-scribe-vs-remarkable comparison hub

   New guide page at /guides/kindle-scribe-vs-remarkable anchoring the
   top-of-funnel device-comparison cluster identified in Phase 1
   discovery. Crown-jewel query "kindle scribe vs remarkable" is 2,900/mo
   (largest single keyword in entire Phase 2 set). Combined cluster:
   ~3,810/mo across Scribe vs reMarkable, vs iPad, vs Paperwhite.

   Centerpiece: 5-device comparison table covering Display, Note-taking,
   PDF readability, Price tier (no dollar amounts), Battery, Ecosystem,
   File format support. Structure: TL;DR + table + use-case H2s
   (academic, marginalia, general reading, multi-column) + "PDF problem
   affects all devices" leafbind-positioning section + FAQ.

   Schema stack: Article + FAQPage. No HowTo (comparison pages don't fit).
   No Product (devices aren't leafbind's products — would be misleading).

   External retail links use rel="noopener nofollow" (different from
   prior units — we're not endorsing competitor purchase paths).

   Framing rule per Phase 1 discovery: device-agnostic, evangelize PDF
   handling not device choice. Pick winners per use case, not overall.

   sitemap.ts and llms.txt entries batched into Unit 7 per the plan.

   Plan: docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md
   ```
3. Push to `origin` and open a PR titled `feat(EB-241): Phase 2 Unit 4 — kindle-scribe-vs-remarkable comparison hub`
4. PR body must reference the plan path, the EB-241 ticket, and the Vercel preview URL once available
5. After merge: post a comment to EB-241 (Atlassian MCP `addCommentToJiraIssue`, `cloudId: jlfowler1084.atlassian.net`) with the PR link and Unit 4 completion status

## Key Constraints (from plan)

- **Do NOT write any other content pages** (Units 5, 6) in this session
- **Do NOT touch `sitemap.ts` or `public/llms.txt`** — batched in Unit 7
- **Do NOT touch `lib/structured-data.ts`** — Unit 1's builders are sufficient
- **Do NOT touch `components/Footer.tsx`** — Unit 8 handles the Guides column
- **Do NOT emit Product schema** for any device (would be misleading; Google's structured-data guidelines explicitly require Product to be your own product, not a comparison subject)
- **Do NOT emit HowTo schema** — comparison pages don't fit the HowTo model
- **Do NOT include $ pricing** in the comparison table or anywhere on the page (pricing dates fast; link to vendor product pages for current prices). Use price *tier* language instead ("entry-level", "mid-range", "premium").
- **Do NOT skip `rel="noopener nofollow"`** on retail product links — this is the load-bearing difference from prior units where external links were primary sources
- **Do NOT pick a single "winner" device** — pick a winner per use case, framed device-agnostically
- **Do NOT use the affiliate-content tone** (urgency, exclusive deals, "best of 2026", "you NEED this") — Google's affiliate-content suspicion is real and this page is the most exposed to it
- **Do NOT hand-roll hex colors** — brand tokens only
- **Do NOT pad word count** — write what the content needs, 3,000-4,500 is a range not a quota
- **Do NOT commit `.worktrees/` artifacts**

## Stop Conditions

Stop and post a comment to EB-241 explaining the blocker if:
- Current device specs from Amazon/reMarkable/Apple have changed materially since the plan was written 2026-05-16 (a model has been discontinued, a feature added that changes the comparison materially, etc.) — note the divergence and ship the page with current data, but flag it
- Internal link to Unit 3's `/guides/how-to-send-pdf-to-kindle` doesn't resolve (Unit 3 may not have merged at session start — merge it first per Phase 0 step 2)
- `pnpm build` baseline fails BEFORE you make any changes (broken master — investigate, don't fix in this PR)
- The comparison table breaks at mobile widths in ways you can't fix without inventing new components (the plan didn't anticipate a need for new components — if the table genuinely doesn't fit established patterns, halt and ask)

## Invocation

To start the execution session:

```bash
claude --model sonnet --prompt-file prompts/EB-241-phase2-unit4-comparison-hub.md
```

or:

```bash
claude --model sonnet "[EB-241] Phase 2 Unit 4 comparison hub — Read prompts/EB-241-phase2-unit4-comparison-hub.md and follow the instructions"
```
