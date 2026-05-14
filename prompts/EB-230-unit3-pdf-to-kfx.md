[EB-230] Phase 3 Unit 3 — /convert/pdf-to-kfx landing page

## Model Tier
**Sonnet** — Single new page component following a fully specified plan.

## Plan
Read the full implementation plan at: `docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md`

Implement **Unit 3 only** (the `/convert/pdf-to-kfx` page). Units 0–2 are merged — Tailwind, design tokens, brand metadata, and the `/quality` page are already in `master`.

## Branch
Create a worktree branch before any file work:
```powershell
git checkout master && git pull origin master
git worktree add .worktrees/EB-230-unit3-pdf-to-kfx -b worktree/EB-230-unit3-pdf-to-kfx
cd .worktrees/EB-230-unit3-pdf-to-kfx
```

## Execution Instructions
1. Create `web_service/frontend/app/convert/pdf-to-kfx/page.tsx` per the plan's Unit 3 spec
2. Page must be >= 800 words of body copy with all 7 required sections (H1, What is KFX, Why converters fail, How leafbind differs, HowTo list, FAQ, CTA)
3. Use only token-derived Tailwind classes — no raw hex values, no `slate-*`, no `indigo-*` in JSX
4. Include `metadata` export with `openGraph` and `twitter` fields per the plan's Unit 3 code block (exact values)
5. Internal cross-links: `/quality`, `/convert/academic-pdf-to-kindle`, `/pricing`
6. KFX output must be clearly stated as premium-only; link to `/pricing`

## Key Stop Gate
**STOP before committing** and invoke the `web-aesthetics` skill as a design QA review of the page. This is a merge requirement. Check against:
- No AI-tell patterns (generic hero copy, slate-900/indigo-600 defaults)
- At least two type sizes from the token scale; Inter for UI, Lora (or serif) for editorial/display text
- Clear visual hierarchy — H1/H2/H3 levels distinguishable at a glance
- Content is specific (names specific failure modes) not generic marketing copy

## Key Constraints
- Do not touch any existing page files (`app/page.tsx`, `app/pricing/page.tsx`, `app/recover/page.tsx`, `app/status/[id]/page.tsx`, `app/quality/page.tsx`)
- Do not implement Units 4–6 — those are separate sessions
- `npm run build` must exit 0 before the PR opens
- The `/quality` page already exists; cross-link to it from the "How leafbind does it differently" section

## Invocation
```
claude --model sonnet "[EB-230] Unit 3: /convert/pdf-to-kfx landing page -- Read prompts/EB-230-unit3-pdf-to-kfx.md and follow the instructions"
```
