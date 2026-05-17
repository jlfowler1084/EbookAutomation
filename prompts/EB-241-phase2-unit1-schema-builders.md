# [EB-241] Phase 2 Unit 1 — Extend `lib/structured-data.ts` with schema builders

## Model Tier
**Sonnet 4.6** — Mechanical TypeScript scaffolding following a clear plan spec. No architectural reasoning needed; the plan encodes the interface, file location, patterns, and test scenarios.

## Plan
Read the full implementation plan at: `docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md`

This session executes **only Unit 1** of the plan. Do NOT execute Units 2-9 — they ship in separate PRs. Stop after Unit 1's verification step passes.

## Phase 0 — Branch setup

Per the plan's "One worktree per PR" decision and the `worktree-management` skill at `~/.claude/skills/worktree-management/SKILL.md`:

1. Verify you're starting from a clean master (`git status` clean, on `master`, up to date with origin)
2. Create a worktree branch: `feat/EB-241-phase2-unit1-schema-builders`
3. Worktree directory: `.worktrees/feat-EB-241-phase2-unit1-schema-builders` (slashes → hyphens)
4. Confirm `.worktrees/` is gitignored before creating
5. From the worktree, run `pnpm install` in `web_service/frontend/` (or whichever package manager the frontend uses — `pnpm-lock.yaml` is the source of truth)
6. Baseline check: `pnpm build` in `web_service/frontend/` should pass before any changes

## Execution Instructions

1. Read the full plan, then re-read **Unit 1** specifically. It has:
   - **Goal**: typed builder functions for Article, FAQPage, HowTo
   - **Files**: modify `web_service/frontend/lib/structured-data.ts`; optionally create `web_service/frontend/lib/__tests__/structured-data.test.ts` if the test infra supports it
   - **Approach**: match the existing builder style — `buildSoftwareApplicationSchema`, `buildPricingProductSchema`, `buildContactPageSchema` are the templates. Interface-typed input, returns the schema object, no rendering, no side effects.
   - **Test scenarios**: 5 enumerated scenarios (happy paths + edge cases). Implement these as tests if a test runner exists in `web_service/frontend/` (check `package.json` for `vitest`, `jest`, etc.). If no test runner, defer to per-page schema-validity verification in subsequent units and note this in the PR description.
2. Reuse `SOFTWARE_APP_ID = "https://leafbind.io/#software"` for any `publisher` or `provider` references (per EB-272 entity-merge decision documented in the plan).
3. Match the existing interfaces in the file — `ArticleSchema`, `FAQPageSchema`, `HowToSchema` already exist as TypeScript types. The builders accept structured input and return objects matching these interfaces.

## Verification Before Commit

Per the plan's Unit 1 Verification section:
1. `pnpm build` in `web_service/frontend/` passes with no TypeScript errors
2. `tools/check-token-drift.mjs` (runs in `prebuild`) still passes
3. If tests added: `pnpm test` (or equivalent) passes for the new builder tests
4. No regressions: existing builder exports are unchanged in signature

If verification fails, STOP — do not commit. Diagnose, fix, re-verify.

## Commit + Push + PR

After verification passes:

1. Stage only the changes for Unit 1 (`lib/structured-data.ts` + optionally `lib/__tests__/structured-data.test.ts`). Do not stage unrelated changes.
2. Commit with this message structure:
   ```
   feat(EB-241): Phase 2 Unit 1 — add Article/FAQPage/HowTo schema builders

   Extends web_service/frontend/lib/structured-data.ts with three builder
   functions used by the upcoming Phase 2 content pages (Units 2-6).
   Builders match the existing buildSoftwareApplicationSchema /
   buildPricingProductSchema interface-typed style; SoftwareApplication
   entity references use the existing SOFTWARE_APP_ID @id per EB-272.

   Foundation only — no pages added in this PR. Pages ship in subsequent
   Unit 2-6 PRs per the plan.

   Plan: docs/plans/2026-05-16-002-feat-eb-241-phase2-leafbind-seo-content-build-plan.md
   ```
3. Push to `origin` and open a PR titled `feat(EB-241): Phase 2 Unit 1 — schema builders for content pages`
4. PR body must reference the plan path and the EB-241 ticket
5. Post a comment to EB-241 (Atlassian MCP `addCommentToJiraIssue`) with the PR link

## Key Constraints (from plan)

- **Do NOT write content pages in this session** — Unit 1 is foundation only. Pages ship in Units 2-6 PRs in subsequent Sonnet sessions.
- **Do NOT refactor existing builders** in `lib/structured-data.ts`. Additive only.
- **Do NOT touch `SOFTWARE_APP_ID` value** — it's the canonical `@id` per EB-272 and is wired into Google's entity merge.
- **Do NOT create new converter pages or marketing pages** — out of scope for Unit 1.
- **Do NOT commit `.worktrees/` artifacts** — verify gitignore before commit.
- **If you discover a test infra ambiguity** (e.g., no test runner configured), note it in the PR description and ship without tests. The plan explicitly defers test addition to "if testing infra exists."

## Stop Conditions

Stop and ask the strategist if:
- The existing `lib/structured-data.ts` style differs significantly from what the plan describes (e.g., builders use a different return shape than expected)
- The token drift guard fails for reasons unrelated to your changes
- The `pnpm build` baseline fails BEFORE you make any changes (broken master — investigate, don't fix in this PR)
- The Unit 1 spec in the plan contradicts something you observe in the codebase (the plan is wrong about a file path, an existing builder, etc.)

In any of these cases, post a comment to EB-241 explaining the blocker before halting.

## Invocation

To start the execution session:

```bash
claude --model sonnet --prompt-file prompts/EB-241-phase2-unit1-schema-builders.md
```

or:

```bash
claude --model sonnet "[EB-241] Phase 2 Unit 1 schema builders — Read prompts/EB-241-phase2-unit1-schema-builders.md and follow the instructions"
```
