# [EB-295] EB-241 Phase 2 reviewer-finding fixes: link gate, sitemap policy, schema drift, freshness, Amazon facts

## Model Tier
**Sonnet 4.6** — Multi-file infrastructure changes with concrete acceptance criteria. Mechanical work; no architectural reasoning needed beyond the trade-offs already documented in EB-295.

## Source documents

- **Ticket:** [EB-295](https://jlfowler1084.atlassian.net/browse/EB-295) — full finding-by-finding acceptance criteria, line-anchored evidence, source URLs for Amazon-fact verification
- **Plan:** `docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md` — see the "Plan Amendments" section at line 604+
- **Parent ticket:** EB-241 — this PR unblocks further Phase 2 unit merges

## What this session ships

A single infrastructure PR addressing all 5 EB-295 findings. The PR is foundational — every Phase 2 unit after this one (Units 3-6) depends on the schema-builder fix and the new policy.

**Critical sequencing**: After this PR merges, PR #120 (Unit 3) needs revision to comply with the new policy before it merges. That revision is OUT of scope for this session — separate task once this lands.

## State at start of this session

- Master is at the commit where the plan amendment was applied (`d3a9827` or later — check `git log` for `docs(EB-295)` commit on master)
- PR #120 (Unit 3) is open but should NOT be merged before this PR ships
- Unit 1 (PR #117, merged at `b0b6fe4`) introduced `buildArticleSchema` without `mainEntityOfPage` — this is one of the things this PR fixes
- Unit 2 (PR #119, merged at `a1ff945`) shipped the live `/guides/send-to-kindle-not-working` page — this PR fixes it retroactively

## Phase 0 — Branch setup

Per the worktree-management skill:

1. Verify clean master, on `master`, up to date with origin
2. Create a worktree branch: `worktree/EB-295-infrastructure-fixes` (or whatever the worktree-management skill produces from the pattern)
3. Confirm `.worktrees/` is gitignored
4. From the worktree, run `pnpm install` in `web_service/frontend/`
5. Baseline check: `pnpm build` in `web_service/frontend/` should pass before any changes

## Execution Instructions — Findings to fix (5 total)

Read EB-295 in full for the line-anchored detail. Summary below maps each finding to the file(s) and acceptance criteria.

### Finding 1 — Link gate (HIGH)

**Problem:** `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx:491-496` links to `/guides/how-to-send-pdf-to-kindle` which doesn't exist on master (only in PR #120's worktree). Next.js does NOT fail builds on dead internal `<Link>` hrefs.

**Fix this PR:**

1. **Decide on Unit 2's dead link**: Two options, pick one:
   - **Option A (recommended):** Keep the link. PR #120 (Unit 3) is open and will ship the target page imminently. The 404 window is small and the link adds value once Unit 3 lands. Document this choice in the PR description as an acknowledged transient state.
   - **Option B:** Remove the link from Unit 2's page now, and the Unit 3 revision PR will re-add it. Cleaner from a "no live 404s" perspective but adds a small follow-up edit on Unit 2's file.
2. **Add the CI link-check gate** so this can't happen silently again:
   - Create a script (TypeScript or Node) at `web_service/frontend/tools/check-internal-links.mjs` (or follow the existing `tools/check-token-drift.mjs` pattern from the prebuild guard)
   - The script walks `web_service/frontend/app/**/*.tsx`, extracts every `<Link href="/...">` literal href, and verifies each one resolves to a corresponding `page.tsx` under `app/`
   - Wire it into `package.json`'s `prebuild` script alongside `check-token-drift.mjs`
   - The check should exit with a non-zero status on any unresolved internal link, printing the offending file + href

**Acceptance criteria (from EB-295):**
- CI link-check fails if any `<Link href="/...">` points to a path with no corresponding `page.tsx` under `app/`
- Policy documented in the plan: cross-links are only added when the target page is in the same PR or already deployed

### Finding 2 — Sitemap/llms.txt shipping policy (HIGH)

**Problem:** `web_service/frontend/app/sitemap.ts:7` has no entry for `/guides/send-to-kindle-not-working` (Unit 2's page, live). `web_service/frontend/public/llms.txt:18-20` only lists the Scribe guide under long-form guides. Plan originally batched these updates into Unit 7.

**Fix this PR:**

1. **Backfill Unit 2's entries:**
   - Add a sitemap entry for `/guides/send-to-kindle-not-working` to `app/sitemap.ts` — use the convention established by `/contact` and the Scribe guide (explicit `lastModified: new Date("2026-05-XX")` matching Unit 2's merge date, `priority: 0.9`, `changeFrequency: "monthly"`)
   - Add a llms.txt entry under the long-form guides section
2. **Reverse the batching policy in the plan:**
   - Update the Unit 7 spec in `docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md` from "batched sitemap/llms.txt for all new pages" to "retroactive cleanup only (sitemap entry for Unit 2 + audit of any other deferred entries that weren't caught up)"
   - Update Units 3, 4, 5, 6 specs to include "ship sitemap.ts entry + llms.txt entry + nav/footer link in the same PR or fail review"
3. **Plan-doc updates are committed direct to master** (docs/ is in `exempt_paths` per `.claude/worktree-policy.json`) — but for this PR include the plan edit alongside the code changes so reviewers see the full policy shift in one place. Reviewers can squash-merge; the policy change is atomic.

### Finding 3 — Amazon facts on Unit 2's page (HIGH)

**Problem:** `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx:71-72` states Send-to-Kindle accepts MOBI. Amazon dropped MOBI in late 2022. Current docs at https://www.amazon.com/sendtokindle and https://www.amazon.com/sendtokindle/email list only DOC, DOCX, HTML, TXT, RTF, JPEG, GIF, PNG, BMP, PDF, EPUB. Web uploader caps at 200 MB.

**Fix this PR:**

1. Fetch both Amazon URLs (use `WebFetch` or browser if needed) and document the current supported-format list as of today's date
2. Update the file-format claim on Unit 2's page to match
3. Update the file-size claim if 50MB is wrong (current docs say 200MB for the web uploader; email cap may differ — check carefully)
4. Add a "Sources" footer block to the page citing the canonical Amazon URLs with `last verified YYYY-MM-DD` date — this is the EB-258 E-E-A-T pattern applied for fact freshness
5. Note: Unit 3 (PR #120) has the same risk surface — Finding 3's acceptance criteria call for a "channel-specific restructure" of Unit 3, but THAT is out of scope for this session. This session only fixes Unit 2 retroactively. The Unit 3 revision is a follow-up task.

### Finding 4 — Schema drift on `mainEntityOfPage` (MEDIUM)

**Problem:** Plan line 176 required `mainEntityOfPage`. `web_service/frontend/lib/structured-data.ts:76-87` (`ArticleSchema` interface) and `lib/structured-data.ts:217-234` (`buildArticleSchema`) both omit it. Unit 2's live page is using this incomplete builder.

**Fix this PR:**

1. Add `mainEntityOfPage: { "@type": "WebPage"; "@id": string }` to the `ArticleSchema` interface in `lib/structured-data.ts`
2. Update `buildArticleSchema` to emit `mainEntityOfPage` from the existing `url` arg (the WebPage `@id` should be the canonical URL of the article)
3. Verify the change is additive — existing consumers (Unit 2's page) get the new field automatically because they already pass `url`
4. Verify Unit 2's live page now emits `mainEntityOfPage` by checking the built HTML and running Google's Rich Results Test on the live URL after deploy
5. Add a process change to the plan: a "plan-vs-implementation diff check" before any future Phase 2 unit merges (a one-liner in the plan's Verification section or a CE review gate)

### Finding 5 — Sitemap freshness (MEDIUM)

**Problem:** `web_service/frontend/app/sitemap.ts:5` declares `const now = new Date()` and reuses it for 7 of 10 entries. Every Googlebot crawl gets a fresh timestamp → Googlebot interprets as low-trust freshness → potential ranking downweight. `/contact` and the Scribe guide use explicit dates — that's the right pattern.

**Fix this PR:**

1. Remove the `const now = new Date()` declaration
2. For each entry currently using `now`, replace with an explicit `lastModified: new Date("YYYY-MM-DD")` sourced from the most recent meaningful content change on that page (use `git log` if needed — look for the last commit that materially edited the page's content, not deploy-pipeline commits)
3. Add a comment at the top of `app/sitemap.ts` documenting the convention: `// lastModified is bumped only when page content materially changes. Do not use new Date() for entries — see EB-295.`

## Verification before commit

1. `pnpm build` in `web_service/frontend/` passes with no TypeScript errors
2. `tools/check-token-drift.mjs` (prebuild) still passes
3. **New CI link-check** runs in prebuild and passes (or, if Unit 2's dead link is kept per Option A, the script reports the known transient exception with a documented escape hatch — discuss with reviewer in the PR)
4. `app/sitemap.ts` has no `new Date()` calls (use `grep -nE 'new Date\(\)' app/sitemap.ts` — should return nothing)
5. `app/sitemap.ts` has an entry for `/guides/send-to-kindle-not-working` with explicit `lastModified` date
6. `public/llms.txt` has an entry for `/guides/send-to-kindle-not-working` under the long-form guides section
7. Unit 2's live page (`app/(marketing)/guides/send-to-kindle-not-working/page.tsx`):
   - Article schema now includes `mainEntityOfPage` (verify via `pnpm build` output or by reading the built HTML)
   - File-format and file-size claims match current Amazon docs
   - "Sources" footer block present with `last verified` date
8. Plan doc updates: Unit 7 spec changed to retroactive-only, Units 3-6 specs updated to require sitemap+llms.txt+nav-link in their PRs
9. Vercel preview deployment renders Unit 2's page without visible regression
10. Rich Results Test on the Vercel preview URL for Unit 2's page now reports `mainEntityOfPage` in the Article schema

If any verification fails, STOP — do not commit. Diagnose, fix, re-verify.

## Commit + Push + PR

Once all verification passes:

1. Stage all the changes — this PR touches multiple files intentionally:
   - `web_service/frontend/lib/structured-data.ts` (Finding 4)
   - `web_service/frontend/app/sitemap.ts` (Findings 2, 5)
   - `web_service/frontend/public/llms.txt` (Finding 2)
   - `web_service/frontend/tools/check-internal-links.mjs` (new, Finding 1)
   - `web_service/frontend/package.json` (wire new check into prebuild — Finding 1)
   - `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx` (Findings 3, 4 retroactive — Amazon facts + Sources footer; passes the new `url` arg if not already)
   - `docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md` (Findings 2, 4 — Unit 7 rescope, Units 3-6 policy update, schema drift process change)
2. Commit with this message structure:
   ```
   fix(EB-295): Phase 2 reviewer findings — link gate, sitemap policy, schema, freshness, Amazon facts

   Address all 5 findings from the EB-241 Phase 2 reviewer pass:

   - Add CI link-check (web_service/frontend/tools/check-internal-links.mjs)
     wired into prebuild to fail on dead internal Link hrefs (Finding 1)
   - Reverse sitemap/llms.txt batching policy; every page PR now ships
     its own discovery entries; backfill Unit 2's entries (Finding 2)
   - Audit Unit 2's Amazon Send-to-Kindle facts against current docs;
     remove MOBI; correct file-size cap; add Sources footer with
     "last verified" date (Finding 3)
   - Add mainEntityOfPage to ArticleSchema interface and buildArticleSchema;
     Unit 2's live page now emits it (Finding 4)
   - Replace const now = new Date() with explicit per-entry lastModified
     dates in app/sitemap.ts; add convention comment (Finding 5)

   Plan-doc edits land in same commit: Unit 7 rescope, Units 3-6 policy
   update, schema drift process change.

   Unit 3 (PR #120) revision is OUT of scope for this PR — separate
   follow-up task to align it with the new policy before merge.

   Plan: docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md
   Plan-amendment commit on master: d3a9827
   ```
3. Push to `origin` and open a PR titled `fix(EB-295): Phase 2 reviewer findings — link gate, sitemap policy, schema drift, freshness, Amazon facts`
4. PR body must reference EB-295 and the parent EB-241 ticket, list the 5 findings and which files address each, and call out the "Unit 3 PR #120 needs revision before merge" follow-up explicitly
5. Post a comment to EB-295 (Atlassian MCP `addCommentToJiraIssue`, `cloudId: jlfowler1084.atlassian.net`) with the PR link
6. After merge: post a follow-up comment to EB-241 noting that Phase 2 work can resume under the new policy, and that PR #120 (Unit 3) is next for a compliance revision

## Key Constraints

- **Do NOT touch PR #120 (Unit 3) in this session** — that's a separate follow-up task. This session is foundational infrastructure only.
- **Do NOT write new content pages** — Units 4-6 wait until this PR + Unit 3 revision both land.
- **Do NOT hand-roll hex colors** anywhere (token drift guard will fail the build).
- **Do NOT bypass the new link-check gate** — if Unit 2's dead link breaks it, choose Option A (keep + document) or Option B (remove now, re-add in Unit 3 revision PR).
- **Do NOT skip Amazon-source verification** — fetch the live Amazon docs (https://www.amazon.com/sendtokindle, https://www.amazon.com/sendtokindle/email) and document what you found. Don't trust the prior content's claims; verify each one.
- **Do NOT pad the Sources footer** with secondary sources — Amazon's own docs are the only canonical source for "what file types does Send-to-Kindle accept". Primary source only.
- **Do NOT commit `.worktrees/` artifacts**.

## Stop Conditions

Stop and post a comment to EB-295 if:
- The link-check script design needs an opinion the prompt doesn't cover (e.g., does the rule also apply to `<a href="/...">` or only `<Link>` components? — recommend Link only, but ask if uncertain)
- The Amazon docs have changed materially in a way that makes the page's positioning ("here are 7 fixes") wrong (e.g., Amazon overhauled Send-to-Kindle and the structure is different) — pause and discuss before rewriting the page wholesale
- `pnpm build` baseline fails BEFORE any changes (broken master — investigate, don't fix in this PR)
- A finding has hidden coupling not anticipated (e.g., fixing the sitemap freshness reveals a bug in how Next.js generates sitemap.xml)

## Invocation

To execute in the existing warm Sonnet session (recommended — Sonnet just did the review and has full context):

> Read `prompts/EB-295-infrastructure-fixes.md` and execute the EB-295 fixes. Plan amendment was already committed to master at `d3a9827`. This PR addresses Findings 1-5 in one focused commit. Unit 3 PR #120 revision is a separate follow-up — do not touch it.

Or in a fresh session:

```bash
claude --model sonnet --prompt-file prompts/EB-295-infrastructure-fixes.md
```
