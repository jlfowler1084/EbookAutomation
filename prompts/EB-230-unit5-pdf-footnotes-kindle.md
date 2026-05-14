[EB-230] Phase 3 Unit 5 — /convert/pdf-footnotes-kindle landing page

## Model Tier
**Sonnet** — Single new page component following a fully specified plan.

## Plan
Read the full implementation plan at: `docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md`

Implement **Unit 5 only** (the `/convert/pdf-footnotes-kindle` page). Units 0–2 are merged — Tailwind, design tokens, brand metadata, and the `/quality` page are already in `master`.

## Branch
Create a worktree branch before any file work:
```powershell
git checkout master && git pull origin master
git worktree add .worktrees/EB-230-unit5-pdf-footnotes-kindle -b worktree/EB-230-unit5-pdf-footnotes-kindle
cd .worktrees/EB-230-unit5-pdf-footnotes-kindle
```

## Execution Instructions
1. Create `web_service/frontend/app/convert/pdf-footnotes-kindle/page.tsx` per the plan's Unit 5 spec
2. Page must be >= 800 words of body copy with all 6 required sections (H1, footnote problem on Kindle, how leafbind links footnotes, types of footnotes handled, HowTo, FAQ)
3. Use only token-derived Tailwind classes — no raw hex values, no `slate-*`, no `indigo-*` in JSX
4. Include `metadata` export with `openGraph` and `twitter` fields per the plan's Unit 5 code block (exact values)
5. Internal cross-links: `/quality`, `/convert/academic-pdf-to-kindle`
6. The FAQ must address: free vs. premium footnote linking, 500+ footnote count, popup behavior on device

## Key Stop Gate
**STOP before committing** and invoke the `web-aesthetics` skill as a design QA review of the page. This is a merge requirement. Check against:
- No AI-tell patterns (generic hero copy, slate-900/indigo-600 defaults)
- At least two type sizes from the token scale; Inter for UI, Lora (or serif) for editorial/display text
- The "problem" section must be concrete: describe what a broken footnote actually looks like on a Kindle (not abstract)
- Clear visual hierarchy distinguishing problem description from the pipeline solution

## Key Constraints
- Do not touch any existing page files (`app/page.tsx`, `app/pricing/page.tsx`, `app/recover/page.tsx`, `app/status/[id]/page.tsx`, `app/quality/page.tsx`)
- Do not implement Units 3, 4, or 6 — those are separate sessions
- `npm run build` must exit 0 before the PR opens
- The `/quality` page already exists; the footnote comparison screenshot (`calibre-footnotes.png` / `pipeline-footnotes.png`) lives at `/quality` — cross-link there for visual proof

## Invocation
```
claude --model sonnet "[EB-230] Unit 5: /convert/pdf-footnotes-kindle landing page -- Read prompts/EB-230-unit5-pdf-footnotes-kindle.md and follow the instructions"
```
