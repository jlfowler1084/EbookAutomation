# EB-230 — Phase 3: SEO landing pages — plan phase handoff

**Model:** SONNET
**Justification:** Plan-drafting task with bounded decision space. The brainstorm is complete and lists 7 specific open questions to resolve; this session picks a defensible answer for each, structures the implementation into ordered units, and writes the plan doc. No code is written. Sonnet's THINK + DO profile fits — Opus would be over-spec for a plan derived from an already-thorough brainstorm.

## Tickets

- **Primary:** EB-230 — Phase 3: SEO landing pages + quality comparison + structured data (leafbind.io)
- **Parent:** EB-45 — Freemium web service (Phase 1 + Phase 2 already shipped)
- **Related:**
  - INFRA-371 — Build SEO skill for Claude Code (To Do; provides the per-page review rubric)
  - INFRA-393 — Build web-aesthetics skill (Done; design QA rubric)

## What to Do

1. **Read the brainstorm doc** at:
   `docs/brainstorms/2026-05-14-eb230-phase3-seo-landing-pages-requirements.md`

   Treat its decisions (D1–D5) as locked. Do not re-litigate hosting, CSS approach,
   `/quality` source material, brand cleanup scope, or sequencing.

2. **Resolve the 7 open questions** the brainstorm flagged for plan phase. Each
   gets a one-sentence decision and a one-sentence rationale in the plan doc:
   - Q1: Synthetic PDF authoring tool (LaTeX vs Typst vs HTML + Paged.js)
   - Q2: Screenshot pipeline (manual vs Playwright-automated)
   - Q3: JSON-LD component shape (single parameterized vs one-per-schema-type)
   - Q4: Tailwind v3 vs v4
   - Q5: `next/image` loader on self-hosted Next.js (default vs custom)
   - Q6: sitemap.xml strategy (static file vs `app/sitemap.ts` dynamic route)
   - Q7: GSC verification status — investigate (check DNS TXT records via the
     Cloudflare MCP, or check `.env` / past commits for evidence) and either
     mark verified or add a prereq step to the plan

3. **Structure the implementation into ordered units** matching the brainstorm's
   /quality-first sequencing (D5):
   - Unit 0: Design tokens + Tailwind setup + brand metadata cleanup (foundations)
   - Unit 1: Synthetic academic PDF authored + screenshots generated
   - Unit 2: `/quality` page (canary)
   - Unit 3: `/convert/pdf-to-kfx` (first landing page)
   - Unit 4: `/convert/academic-pdf-to-kindle`
   - Unit 5: `/convert/pdf-footnotes-kindle`
   - Unit 6: `/convert/multi-column-pdf-kindle`
   - Unit 7: JSON-LD components + OG/Twitter metadata helpers (applied to all
     pages — likely split per page or done as one sweep, plan decides)
   - Unit 8: sitemap.xml + robots.txt + GSC submission
   - Unit 9: Lighthouse + CWV audit + fixes

   For each unit list: files touched, the AC it satisfies, dependencies on prior
   units, rough complexity. Use the project's existing plan format (see
   `docs/plans/2026-05-13-001-feat-eb45-freemium-web-service-plan.md` for the
   reference shape — frontmatter, requirements trace, scope boundaries, units,
   then per-unit detail).

4. **Identify per-unit gotchas**. Phase 1 + Phase 2 are deployed; this plan must
   not break what's live. Specifically flag:
   - The brand metadata change touches `app/layout.tsx` which currently runs
     in production — verify no SSR break
   - `tailwind.config.js` introduction affects ALL existing pages (`/`,
     `/pricing`, `/recover`, `/status/[id]`) — confirm the brainstorm's
     deferral to "tokens applied only to new pages" is mechanically achievable
     without a global stylesheet collision
   - The Hetzner VM is a shared box (sb-chat, batch workers per memory) —
     adding a heavier `next build` pipeline must not OOM on deploys

5. **Write the plan doc** at:
   `docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md`

   Use frontmatter:
   ```
   ---
   title: "feat: EB-230 — Phase 3 SEO landing pages + quality comparison + structured data"
   type: feat
   status: active
   date: 2026-05-14
   ticket: EB-230
   parent_ticket: EB-45
   origin: docs/brainstorms/2026-05-14-eb230-phase3-seo-landing-pages-requirements.md
   ---
   ```

6. **Update the auto-memory pending items** (optional but encouraged): the
   `auto_pending_*` files in `~/.claude/projects/F--Projects-EbookAutomation/memory/`
   include many EB-45-era items. Phase 3 supersedes the SEO-related ones. Don't
   delete them; just flag in the plan's "Open Questions for Implementation" section
   which auto_pending items Phase 3 resolves.

## What NOT to Do

- Do not write any code, JSX, CSS, or config.
- Do not run `npm install` or any build commands.
- Do not modify `package.json`, `tailwind.config.js`, or any frontend source.
- Do not create the synthetic PDF.
- Do not transition EB-230 in Jira — it stays "To Do" until task #3 starts.
- Do not invoke a worktree — planning is a docs/plans/ commit; that path is
  exempt per `.claude/worktree-policy.json`.

## Stop Gate

After committing the plan doc to master and pushing, STOP. The next session
(separate handoff, separate model — likely Sonnet again for Unit 0 + Unit 1
foundations) picks up at task #3 of the task list.

Final action of this session: post a comment on EB-230 in Jira linking to the
plan commit SHA. Use the Atlassian MCP `addCommentToJiraIssue` tool.

## Critical Context

- **Project shell:** PowerShell (not bash). Don't write bash-style commands in
  the plan doc.
- **Worktree policy:** `docs/**` is in `exempt_paths`, so plan commits go direct
  to master. No worktree needed for THIS session's output.
- **Branding:** Brand is **leafbind**. Domain is leafbind.io. The repo is named
  "EbookAutomation" for historical reasons; the public product is leafbind.
- **No emojis** in plan doc or commit messages — project convention.

## References

- Brainstorm: `docs/brainstorms/2026-05-14-eb230-phase3-seo-landing-pages-requirements.md`
- EB-45 plan (reference shape only): `docs/plans/2026-05-13-001-feat-eb45-freemium-web-service-plan.md`
- EB-45 brainstorm (SEO Strategy section): `docs/brainstorms/2026-05-13-freemium-web-service-requirements.md`
- web-aesthetics skill (apply as design QA rubric): listed in available skills
- Frontend codebase: `web_service/frontend/` (Next.js 15 App Router, React 19,
  no CSS framework currently)
- Production URL: https://leafbind.io
