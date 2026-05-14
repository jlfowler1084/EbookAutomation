[EB-230] Phase 3 Unit 6 — /convert/multi-column-pdf-kindle landing page

## Model Tier
**Sonnet** — Single new page component following a fully specified plan.

## Plan
Read the full implementation plan at: `docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md`

Implement **Unit 6 only** (the `/convert/multi-column-pdf-kindle` page). Units 0–2 are merged — Tailwind, design tokens, brand metadata, and the `/quality` page are already in `master`.

## Branch
Create a worktree branch before any file work:
```powershell
git checkout master && git pull origin master
git worktree add .worktrees/EB-230-unit6-multi-column-pdf-kindle -b worktree/EB-230-unit6-multi-column-pdf-kindle
cd .worktrees/EB-230-unit6-multi-column-pdf-kindle
```

## Execution Instructions
1. Create `web_service/frontend/app/convert/multi-column-pdf-kindle/page.tsx` per the plan's Unit 6 spec
2. Page must be >= 800 words of body copy with all 6 required sections (H1, what goes wrong with multi-column PDFs, how leafbind detects columns, document types with multi-column layouts, HowTo, FAQ)
3. Use only token-derived Tailwind classes — no raw hex values, no `slate-*`, no `indigo-*` in JSX
4. Include `metadata` export with `openGraph` and `twitter` fields per the plan's Unit 6 code block (exact values)
5. Internal cross-links: `/quality`, `/convert/academic-pdf-to-kindle`, `/convert/pdf-to-kfx`
6. The "how leafbind detects columns" section must describe the coordinate-based approach (pdfplumber x0/x1 bounding boxes, column boundary detection, per-column sequential extraction)

## Key Stop Gate
**STOP before committing** and invoke the `web-aesthetics` skill as a design QA review of the page. This is a merge requirement. Check against:
- No AI-tell patterns (generic hero copy, slate-900/indigo-600 defaults)
- At least two type sizes from the token scale; Inter for UI, Lora (or serif) for editorial/display text
- The problem description must be vivid: describe the interleaved-column read order bug concretely (sentence from col 1 line 1, col 2 line 1, col 1 line 2…)
- Cross-link to `/quality` for the visual comparison — this page's value prop needs the visual proof

## Key Constraints
- Do not touch any existing page files (`app/page.tsx`, `app/pricing/page.tsx`, `app/recover/page.tsx`, `app/status/[id]/page.tsx`, `app/quality/page.tsx`)
- Do not implement Units 3–5 — those are separate sessions
- `npm run build` must exit 0 before the PR opens
- The `/quality` page already exists with `calibre-columns.png` / `pipeline-columns.png` screenshots — reference these as visual proof of the column detection

## Invocation
```
claude --model sonnet "[EB-230] Unit 6: /convert/multi-column-pdf-kindle landing page -- Read prompts/EB-230-unit6-multi-column-pdf-kindle.md and follow the instructions"
```
