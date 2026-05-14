[EB-230] Phase 3 Unit 2 — /quality comparison page

## Model Tier
**Sonnet** — Single new page component following a fully specified plan; content, metadata, image layout, and web-aesthetics gate are all defined.

## Plan
Read the full implementation plan at: `docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md`

Implement **Unit 2 only** (the `/quality` page). All prior units are merged — Tailwind, design tokens, brand metadata, and the 6 comparison screenshots in `public/quality/` are already in `master`.

## Branch
Create a worktree branch before any file work:
```powershell
git checkout master && git pull origin master
git worktree add .worktrees/EB-230-unit2-quality -b worktree/EB-230-unit2-quality
cd .worktrees/EB-230-unit2-quality
```

## Execution Instructions
1. Create `web_service/frontend/app/quality/page.tsx` per the plan's Unit 2 spec
2. Use only token-derived Tailwind classes (from `design-tokens.ts`) — no raw hex values, no `slate-*`, no `indigo-*` in JSX
3. Serve comparison images as `<img>` tags with explicit `width`, `height`, and descriptive `alt` attributes (not `next/image`)
4. Include `metadata` export with `openGraph` and `twitter` fields per the plan's Unit 2 code block
5. Internal cross-links to `/convert/academic-pdf-to-kindle`, `/convert/pdf-footnotes-kindle`, `/convert/multi-column-pdf-kindle`, and `/` (upload CTA)

## Key Stop Gate
**STOP before committing** and invoke the `web-aesthetics` skill as a design QA review of the page. This is a merge requirement — the skill review must pass before the PR opens. Specifically check against:
- No AI-tell patterns (generic hero copy, slate-900/indigo-600 defaults, full-width stacked images)
- Comparison pairs use a 2-up layout (side-by-side), not vertically stacked
- At least two type sizes from the token scale; Inter for UI, Lora (or distinctive serif) for any editorial text
- Asymmetric or intentional grid (e.g. 60/40 split on comparison sections)

## Key Constraints
- Do not touch any existing page files (`app/page.tsx`, `app/pricing/page.tsx`, `app/recover/page.tsx`, `app/status/[id]/page.tsx`)
- Do not implement Units 3–6 — those are separate sessions
- `npm run build` must exit 0 before the PR opens
- All 6 comparison images are already committed at `public/quality/*.png` — reference them by those exact paths
