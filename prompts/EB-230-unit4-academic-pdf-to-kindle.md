[EB-230] Phase 3 Unit 4 — /convert/academic-pdf-to-kindle landing page

## Model Tier
**Sonnet** — Single new page component following a fully specified plan.

## Plan
Read the full implementation plan at: `docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md`

Implement **Unit 4 only** (the `/convert/academic-pdf-to-kindle` page). Units 0–2 are merged — Tailwind, design tokens, brand metadata, and the `/quality` page are already in `master`.

## Branch
Create a worktree branch before any file work:
```powershell
git checkout master && git pull origin master
git worktree add .worktrees/EB-230-unit4-academic-pdf-to-kindle -b worktree/EB-230-unit4-academic-pdf-to-kindle
cd .worktrees/EB-230-unit4-academic-pdf-to-kindle
```

## Execution Instructions
1. Create `web_service/frontend/app/convert/academic-pdf-to-kindle/page.tsx` per the plan's Unit 4 spec
2. Page must be >= 800 words of body copy with all 6 required sections (H1, academic PDF problem, what the pipeline preserves, supported document types, HowTo, FAQ)
3. Use only token-derived Tailwind classes — no raw hex values, no `slate-*`, no `indigo-*` in JSX
4. Include `metadata` export with `openGraph` and `twitter` fields per the plan's Unit 4 code block (exact values)
5. Internal cross-links: `/quality`, `/convert/pdf-to-kfx`, `/convert/pdf-footnotes-kindle`
6. The FAQ must include the scanned-PDF limitation and the numbered-heading question

## Key Stop Gate
**STOP before committing** and invoke the `web-aesthetics` skill as a design QA review of the page. This is a merge requirement. Check against:
- No AI-tell patterns (generic hero copy, slate-900/indigo-600 defaults)
- At least two type sizes from the token scale; Inter for UI, Lora (or serif) for editorial/display text
- Content is specific to academic PDFs (IEEE/ACM layouts, numbered sections, inline citations) — not generic
- Clear visual hierarchy distinguishing the problem/solution structure

## Key Constraints
- Do not touch any existing page files (`app/page.tsx`, `app/pricing/page.tsx`, `app/recover/page.tsx`, `app/status/[id]/page.tsx`, `app/quality/page.tsx`)
- Do not implement Units 3, 5, or 6 — those are separate sessions
- `npm run build` must exit 0 before the PR opens
- The `/quality` page already exists; cross-link to it from the "what the pipeline preserves" section

## Invocation
```
claude --model sonnet "[EB-230] Unit 4: /convert/academic-pdf-to-kindle landing page -- Read prompts/EB-230-unit4-academic-pdf-to-kindle.md and follow the instructions"
```
