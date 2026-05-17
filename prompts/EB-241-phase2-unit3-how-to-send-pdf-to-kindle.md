# [EB-241] Phase 2 Unit 3 — "How to Send PDF to Kindle" mega-guide

## Model Tier
**Sonnet 4.6** — Long-form content writing + structured-data emission following a clear plan spec. Mechanical work; no architectural reasoning needed.

## Plan
Read the full implementation plan at: `docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md`

This session executes **only Unit 3** of the plan. Do NOT execute Units 4-9 — they ship in separate PRs. Stop after Unit 3's verification step passes.

## State at start of this session

- Unit 1 (schema builders in `lib/structured-data.ts`) shipped via PR #117, merged to master at `b0b6fe4`. The new `buildArticleSchema`, `buildFAQPageSchema`, `buildHowToSchema` exports are live. **Use them — do not hand-roll schema objects.**
- Unit 2 (`/guides/send-to-kindle-not-working` pain pillar) shipped via PR #119, merged at `a1ff945`. The pain pillar page is live — internal links from Unit 3 to `/guides/send-to-kindle-not-working` will resolve.
- Unit 4 (comparison hub at `/guides/kindle-scribe-vs-remarkable`) is **not yet shipped**. If Unit 3 references it, the link will 404 briefly until Unit 4 ships. Write the link with the final URL anyway — this is the planned trade-off per the plan's "Risks & Dependencies" section.

## Phase 0 — Branch setup

Per the plan's "One worktree per PR" decision and the [`worktree-management` skill](~/.claude/skills/worktree-management/SKILL.md):

1. Verify clean master (`git status` clean, on `master`, up to date with origin — note Unit 2's merge means master is at `a1ff945`)
2. Create a worktree branch following the worktree-management skill conventions (Unit 2's PR used `worktree-feat+EB-241-phase2-unit2-...` — follow the same pattern with `unit3-how-to-send-pdf-to-kindle`)
3. Confirm `.worktrees/` is gitignored
4. From the worktree, run `pnpm install` in `web_service/frontend/`
5. Baseline check: `pnpm build` in `web_service/frontend/` should pass before any changes

## Execution Instructions

1. Read the full plan, then re-read **Unit 3** specifically. Key Unit 3 specs:

   - **Slug**: `how-to-send-pdf-to-kindle` (matches the 1,600/mo crown-jewel query)
   - **Title**: "How to Send PDFs (and EPUBs, Docs, MOBI) to Kindle: Every Method"
   - **Target keywords**: `how to send pdf to kindle` (1,600), `how to send epub to kindle` (1,000), + 10 variants — combined ~6,000 monthly addressable
   - **Length**: 3,000-4,000 words (mega-guide — needs depth to outrank Reddit + Amazon)
   - **Lead paragraph (40-60 words, EB-281 GEO pattern)**: direct-answer covering the four main methods (Send-to-Kindle Email, USB cable, Amazon mobile app, leafbind), with named-alternatives pattern
   - **Structure (one H2 per method, multiple H3s per file type)**:
     - H1 + lead paragraph
     - "Which method should you use?" decision table — file type × method matrix
     - H2: Method 1 — Send-to-Kindle Email (H3s for PDF, EPUB, documents, MOBI)
     - H2: Method 2 — Send-to-Kindle App
     - H2: Method 3 — USB cable transfer
     - H2: Method 4 — Convert and sideload via leafbind (commercial-intent funnel)
     - H2: Common failures and fixes (internal link to `/guides/send-to-kindle-not-working` — Unit 2, shipped)
     - FAQ section (≥7 questions)
   - **Schemas**: Article + FAQPage + HowTo. The HowTo schema describes the Send-to-Kindle Email workflow as the canonical "how to" (5-7 steps). **Use the merged builders from Unit 1** — `buildArticleSchema`, `buildFAQPageSchema`, `buildHowToSchema` from `lib/structured-data.ts`.
   - **Internal links** (minimum 3): `/guides/send-to-kindle-not-working` (pain pillar, shipped), `/guides/kindle-scribe-vs-remarkable` (comparison hub, ships in Unit 4 — link will 404 briefly), `/convert/pdf-to-kfx` (commercial intent funnel, exists), `/guides/pdf-to-kfx-for-kindle-scribe` (existing Scribe guide)
   - **External links** (minimum 1 primary source): Amazon Send-to-Kindle help docs, Amazon-approved file types reference
   - **File**: `web_service/frontend/app/(marketing)/guides/how-to-send-pdf-to-kindle/page.tsx`

2. **Reference templates to copy from**:
   - `web_service/frontend/app/(marketing)/guides/pdf-to-kfx-for-kindle-scribe/page.tsx` — the reference guide template (image manifest header, `PUBLISHED`/`SLUG`/`CANONICAL` consts, schema stack, FAQ-array-once pattern, "Related" pill row)
   - `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx` — Unit 2's just-shipped pain pillar. Copy its structure for any patterns Unit 2 established that aren't in the Scribe guide.

3. **GEO / AI Overview citation pattern** (from EB-281 + EB-258):
   - Lead paragraph must be 40-60 words with direct-answer + named alternatives in the first sentence
   - Include at least one standalone 134-167-word passage block — a self-contained answer that an AI Overview could lift verbatim. The "Which method should you use?" decision table section is a natural place for this.
   - Cite competitor docs directly (e.g., quote Amazon's Send-to-Kindle help page for the 50MB file size limit, or the official file format support list). This is the gold-standard E-E-A-T differentiation per EB-258.

4. **Design system constraints** (from EB-233):
   - Typography: `font-serif` (Newsreader) for H1/H2/H3, `font-sans` (DM Sans) body, `font-mono` (IBM Plex Mono) eyebrow
   - Colors: brand-green palette only (`bg-brand`, `text-text-base`, `text-text-muted`, `text-accent`, `border-border`, `bg-surface`). **No hand-rolled hex** — token drift guard runs in `prebuild` and will fail the build.
   - AI-slop checklist: no gradient-mesh, no glassmorphism, no slate/indigo/zinc, no urgency copy, single primary CTA per page
   - Use established class patterns from the Scribe guide (eyebrow, H1, H2, H3, body, section divider, primary CTA, pill link — all documented in the plan's "Context & Research" → "Relevant Code and Patterns" section)

5. **The decision table is the page's centerpiece** — file type × method matrix. Suggested columns: file type (PDF, EPUB, DOC/DOCX, MOBI, AZW3, TXT). Suggested rows: Send-to-Kindle Email, Send-to-Kindle App, USB cable, leafbind conversion. Cells: ✓ supported, ⚠ supported with caveat, ✗ not supported. This is the table users will reference repeatedly — make it scannable, mobile-responsive, and accurate against current Amazon documentation.

## Verification Before Commit

Per the plan's Unit 3 Verification section + the schema-verification gotcha from `docs/solutions/best-practices/jsonld-script-tag-count-build-instability-2026-05-14.md`:

1. `pnpm build` in `web_service/frontend/` passes with no TypeScript errors
2. `tools/check-token-drift.mjs` (runs in `prebuild`) still passes — no hand-rolled hex colors
3. Page renders at `http://localhost:3000/guides/how-to-send-pdf-to-kindle` (run `pnpm dev` and verify visually)
4. **Schema validation**: count `@type` occurrences with `grep -oE '"@type":"[^"]*"' | sort -u` (NOT `<script>` tag count — Next.js 16 + Turbopack collapses them into one tag). Expect at least: `"@type":"Article"`, `"@type":"FAQPage"`, `"@type":"HowTo"`, `"@type":"Question"` (within FAQPage), `"@type":"HowToStep"` (within HowTo).
5. Lead paragraph word count is 40-60 (mechanically count or eyeball — don't pad to hit the range)
6. FAQ items ≥7
7. HowTo schema has ≥5 steps
8. Internal links resolve (or are intentional 404s with a TODO note — only for the Unit 4 comparison hub link, which is the documented exception)
9. External links use `rel="noopener"` (and `rel="nofollow"` for retail product pages if any)
10. Comparison table renders mobile (test at viewport ≤375px)
11. Visual smoke: page passes AI-slop checklist; uses brand-green + cream tokens; Newsreader for H1/H2; DM Sans body; Plex Mono eyebrow

If verification fails, STOP — do not commit. Diagnose, fix, re-verify.

## Commit + Push + PR

After verification passes:

1. Stage only the changes for Unit 3 — `web_service/frontend/app/(marketing)/guides/how-to-send-pdf-to-kindle/page.tsx`. Do NOT update `sitemap.ts` or `llms.txt` in this PR (per the plan, those are batched in Unit 7).
2. Commit with this message structure:
   ```
   feat(EB-241): Phase 2 Unit 3 — how-to-send-pdf-to-kindle mega-guide

   New guide page at /guides/how-to-send-pdf-to-kindle anchoring the
   ~6,000/mo question cluster identified in Phase 1 discovery. Crown-jewel
   query "how to send pdf to kindle" is 1,600/mo on its own.

   Structure: decision table + 4-method walkthrough (Send-to-Kindle Email,
   App, USB, leafbind) + common-failures section + FAQ. Schema stack:
   Article + FAQPage + HowTo, all using the Unit 1 builders. Lead paragraph
   follows EB-281 GEO citation pattern (40-60 words, direct-answer + named
   alternatives).

   Internal links: pain pillar (Unit 2, shipped), comparison hub (Unit 4,
   pending — link will 404 briefly until Unit 4 ships per the documented
   trade-off), converter pillar, existing Scribe guide.

   sitemap.ts and llms.txt entries are batched into Unit 7 per the plan.

   Plan: docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md
   ```
3. Push to `origin` and open a PR titled `feat(EB-241): Phase 2 Unit 3 — how-to-send-pdf-to-kindle mega-guide`
4. PR body must reference the plan path, the EB-241 ticket, and the Vercel preview URL once available
5. After merge: post a comment to EB-241 (Atlassian MCP `addCommentToJiraIssue`) with the PR link and Unit 3 completion status. Use `cloudId: jlfowler1084.atlassian.net`.

## Key Constraints (from plan)

- **Do NOT write any other content pages** (Units 4, 5, 6) in this session
- **Do NOT touch `sitemap.ts` or `public/llms.txt`** — batched in Unit 7
- **Do NOT touch `lib/structured-data.ts`** — Unit 1 is done; just import the builders
- **Do NOT touch `components/Footer.tsx`** — Unit 8 handles the Guides column
- **Do NOT hand-roll schema objects** — use the Unit 1 builders
- **Do NOT hand-roll hex colors** — use brand tokens (token drift guard will fail the build)
- **Do NOT pad word count** to hit 3,000-4,000 — write what the content needs. The plan target is a range, not a quota. If the page is naturally 2,800 words and complete, ship it; if it needs 4,200, ship it.
- **Do NOT add device pricing in dollars** to any comparison content (per plan's Unit 4 rule — but applies here too if you mention leafbind pricing). Link to the pricing page instead.
- **Do NOT commit `.worktrees/` artifacts** — verify gitignore before commit

## Stop Conditions

Stop and post a comment to EB-241 explaining the blocker if:
- Unit 1's schema builders don't behave as documented (signature mismatch, missing field, etc.)
- Amazon's documented file-size limit or format list has changed materially since the plan was written (Amazon docs are the source of truth; the plan may be slightly stale)
- The Scribe guide template referenced in the plan has been refactored in a way that breaks the "copy this structure" pattern
- `pnpm build` baseline fails BEFORE you make any changes (broken master — investigate, don't fix in this PR)

## Invocation

To start the execution session:

```bash
claude --model sonnet --prompt-file prompts/EB-241-phase2-unit3-how-to-send-pdf-to-kindle.md
```

or:

```bash
claude --model sonnet "[EB-241] Phase 2 Unit 3 mega-guide — Read prompts/EB-241-phase2-unit3-how-to-send-pdf-to-kindle.md and follow the instructions"
```
