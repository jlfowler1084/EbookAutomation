[EB-230] Phase 3 Unit 7 — JSON-LD structured data sweep

## Model Tier
**Sonnet** — Creates 2 new files and surgically modifies 5 existing page files.
Content for FAQPage and HowTo schemas must be derived from already-written page copy.

## Plan
Read the full implementation plan at: `docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md`

Implement **Unit 7 only**. Units 0–6 are merged — all 5 pages exist in `master`.

## Branch
Create a worktree branch before any file work:
```powershell
git checkout master && git pull origin master
git worktree add .worktrees/EB-230-unit7-json-ld -b worktree/EB-230-unit7-json-ld
cd .worktrees/EB-230-unit7-json-ld
```

## Execution Instructions

### Step 1 — Create the two new files

Create `web_service/frontend/lib/structured-data.ts` using the **exact code** from the
plan's Unit 7 `lib/structured-data.ts` code block — TypeScript interfaces, `SchemaData`
union type, and `buildSoftwareApplicationSchema()` builder function.

Create `web_service/frontend/components/JsonLd.tsx` using the **exact code** from the
plan's Unit 7 `components/JsonLd.tsx` code block. `dangerouslySetInnerHTML` on a
TypeScript-constructed schema object is correct and safe — do not remove it.

### Step 2 — Read existing pages before modifying them

Before touching any page file, read it to understand the exact FAQ items and HowTo
steps it contains. The FAQPage and HowTo schema objects must match the page's existing
copy — do not invent new Q&As or steps.

Pages to read:
- `web_service/frontend/app/quality/page.tsx` — needs `SoftwareApplication` only (no FAQ/HowTo)
- `web_service/frontend/app/convert/pdf-to-kfx/page.tsx` — needs all 3 schemas
- `web_service/frontend/app/convert/academic-pdf-to-kindle/page.tsx` — needs all 3 schemas
- `web_service/frontend/app/convert/pdf-footnotes-kindle/page.tsx` — needs all 3 schemas
- `web_service/frontend/app/convert/multi-column-pdf-kindle/page.tsx` — needs all 3 schemas

### Step 3 — Modify each page

For the `/quality` page:
- Add `import JsonLd from "../../components/JsonLd"` 
- Add `import { buildSoftwareApplicationSchema } from "../../lib/structured-data"`
- Render `<JsonLd schema={buildSoftwareApplicationSchema()} />` as the **first child**
  inside the outermost `<div>` wrapper

For each `/convert/*` page:
- Add the two imports above (adjust relative path depth: `../../../components/JsonLd`,
  `../../../lib/structured-data`)
- Build inline schema data objects for `FAQPage` and `HowTo` derived from the page's
  existing FAQ items array and HowTo steps (read the page first — see Step 2)
- Render three `<JsonLd />` calls as the **first children** inside the outermost `<div>`:
  ```tsx
  <JsonLd schema={buildSoftwareApplicationSchema()} />
  <JsonLd schema={faqSchema} />
  <JsonLd schema={howToSchema} />
  ```
- The FAQPage schema `mainEntity` array must match the actual `faqItems` data in the page
- The HowTo schema `step` array must match the actual numbered steps in the page

### Step 4 — Verify build

Run `npm run build` from `web_service/frontend/` inside the worktree. Must exit 0.

### Step 5 — OG image sweep

Check each `/convert/*` page's `metadata.openGraph` export. If any page is missing an
`openGraph.images` field, add one pointing to `/quality/pipeline-columns.png` as a
fallback (this image already exists in `public/quality/`). The `/quality` page's
metadata already specifies an OG image — do not modify it.

## Key Constraints
- Do NOT add FAQ/HowTo schema to the `/quality` page — it is a comparison page, not
  a conversion CTA page. `SoftwareApplication` only.
- The `JsonLd` component import path from `/quality/page.tsx` is `../../components/JsonLd`
  (two levels up). From `/convert/*/page.tsx` it is `../../../components/JsonLd` (three
  levels up). Get the relative paths right — a wrong import path will fail TypeScript
  compilation at build time.
- Do NOT change any page's visible JSX content, CSS classes, or metadata strings. This
  unit adds schema markup only.
- `npm run build` must exit 0 before the PR opens

## Invocation
```
claude --model sonnet "[EB-230] Unit 7: JSON-LD structured data sweep -- Read prompts/EB-230-unit7-json-ld-sweep.md and follow the instructions"
```
