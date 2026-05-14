---
date: 2026-05-14
topic: eb230-phase3-seo-landing-pages
status: draft
ticket: EB-230
parent_ticket: EB-45
---

# EB-230: Phase 3 — SEO Landing Pages + Quality Comparison + Structured Data

## Problem Frame

leafbind.io (EB-45 Phase 1 + Phase 2) is live: free-tier Calibre conversion,
Stripe-gated premium pipeline, Next.js frontend on the Hetzner VM. The product
works. The traffic doesn't exist.

The EB-45 brainstorm hypothesised that quality-aware long-tail keywords are
uncontested: "convert PDF to KFX", "academic PDF to Kindle converter",
"PDF footnotes Kindle", "multi-column PDF Kindle" — competitors target the
generic "PDF to Kindle" head term where they cannot win on quality. Phase 3
operationalises that hypothesis: build the landing-page surface area that
captures those queries and converts them.

The freemium model only pays off if traffic shows up. Phase 3 is the traffic
phase.

## Core Use Cases

**Primary:** A reader Googles `"convert PDF to KFX"` or
`"academic PDF to Kindle converter"`, lands on a keyword-targeted page,
sees the quality difference demonstrated visually, and either uploads a free
conversion or buys credits.

**Secondary:** A user shares `/quality` on r/kindle, r/ebooks, or an academic
forum because the before/after comparison is the clearest demonstration of why
this converter is different. The page is the link-bait that drives backlinks
and (eventually) organic authority.

**Out of scope (v1):**
- Backlink campaigns or outreach (post-launch effort)
- Paid acquisition — organic-only
- Email capture / newsletter signup — separate ticket
- Blog / content marketing beyond the 5 launch pages — separate ticket
- A/B testing or conversion-rate optimization tooling — premature for traffic
  this low

## Decisions Made in Brainstorm

### D1. Hosting: self-hosted Next.js on the Hetzner VM (`claude-dev-01`)

- Frontend already runs as `next start` on the VM behind nginx
- Cloudflare in front handles caching, minification, and DDoS protection
- No Vercel; no edge functions
- CWV strategy: static-first marketing pages (no client-side data fetching on
  /quality or any /convert/* page), nginx + Cloudflare cache layers, image
  optimization via `next/image` with a self-hosted loader

### D2. CSS approach: Tailwind + a custom `design-tokens.ts` + Refactoring-UI / web-aesthetics rubric

- Tailwind as the utility engine; not Tailwind defaults
- A `design-tokens.ts` file defines: typography scale, color palette, spacing
  ramp, shadow ramp, radii. `tailwind.config.js` pulls from this file —
  Tailwind utilities only express tokens that are in the design system
- The `web-aesthetics` skill (INFRA-393) is the design QA rubric every page
  passes before merge. Anti-patterns from the skill (slate-900, indigo-600,
  generic SaaS hero patterns, AI tells) are explicit acceptance-criteria gates
- No component library (shadcn/ui etc.) — marketing pages don't benefit from
  product-UI primitives

### D3. /quality source material: self-authored synthetic academic PDF

- Build one synthetic academic-style PDF explicitly to showcase the pipeline:
  - Multi-column layout
  - Footnotes / endnotes with backreferences
  - Complex heading hierarchy (Part / Chapter / Section / Subsection)
  - A figure with caption
  - A bibliography
- Zero copyright exposure
- Total control over what the comparison demonstrates
- Source file checked in under `web_service/test-pdfs/leafbind-demo.tex` (or
  similar); generated PDF + screenshots checked in under `web_service/frontend/public/quality/`
- Decision in plan phase: LaTeX vs. Typst vs. hand-rolled HTML-to-PDF for
  authoring the synthetic doc

### D4. Brand metadata cleanup is in scope for EB-230

- Current `app/layout.tsx` metadata title is `"EbookAutomation — Ebook Converter"`
  — the operational brand is **leafbind**; site title should reflect that
- Same commit: update root `<title>`, default `description`, OpenGraph site name,
  Twitter `@site` handle (if one exists)
- This is brand-keyword alignment, foundational SEO; lives in EB-230 not a
  separate ticket

### D5. Sequencing: /quality first as the canary

- Ship /quality before any /convert/* landing page
  - It exercises the new design-tokens system on real content
  - It exercises the synthetic-PDF + screenshot pipeline
  - It surfaces CWV problems on the largest, image-heaviest page first
  - It's the most-shared single page; getting it right has the highest leverage
- Then ship the 4 /convert/* pages in priority order:
  1. `/convert/pdf-to-kfx` — lowest competition, best brand fit
  2. `/convert/academic-pdf-to-kindle` — primary persona match
  3. `/convert/pdf-footnotes-kindle` — narrowest niche, easiest to rank
  4. `/convert/multi-column-pdf-kindle` — supports the academic use case
- One PR per page (5 PRs total under EB-230) keeps reviews bounded and lets
  CWV regressions be caught one page at a time

## Requirements Trace

| ID | Requirement | Source |
|---|---|---|
| R1 | `/quality` page with side-by-side Calibre-vs-pipeline screenshots for >= 3 conversion examples (all from the synthetic PDF) | EB-45 brainstorm § SEO Strategy; EB-230 description |
| R2 | 4 keyword-targeted landing pages: `/convert/pdf-to-kfx`, `/convert/academic-pdf-to-kindle`, `/convert/pdf-footnotes-kindle`, `/convert/multi-column-pdf-kindle`. Each >= 800 words, internally cross-linked | EB-45 brainstorm § SEO Strategy |
| R3 | schema.org JSON-LD on conversion pages: `SoftwareApplication` (root), `FAQPage` (per landing page), `HowTo` (per landing page) — validates in Google Rich Results Test | EB-230 description |
| R4 | Lighthouse SEO score >= 95 on `/`, `/quality`, and all 4 `/convert/*` pages | EB-230 description |
| R5 | Lighthouse CWV: LCP < 2.5s, INP < 200ms, CLS < 0.1 on `/`, `/quality`, and at least one `/convert/*` page | EB-230 description |
| R6 | sitemap.xml lists all new routes; robots.txt allows them; both are served at the canonical leafbind.io URLs | EB-230 description |
| R7 | OpenGraph + Twitter Card metadata on every new page (image, title, description) | EB-230 description |
| R8 | Brand metadata cleanup: root `<title>`, `<meta description>`, OG site name reflect "leafbind" not "EbookAutomation" | D4 |
| R9 | Design tokens file (`design-tokens.ts`) + Tailwind config that pulls only from it; no raw Tailwind defaults in JSX outside the tokens layer | D2 |
| R10 | Each new page passes the `web-aesthetics` skill review before merge (no AI-tell patterns, distinctive typography, intentional grid, no slate-900/indigo-600 defaults) | D2 |
| R11 | Synthetic academic PDF authored, generated, and committed under `web_service/test-pdfs/`; converted output via free + premium pipelines committed under `web_service/frontend/public/quality/` for use as comparison screenshots | D3 |
| R12 | Sitemap submitted to Google Search Console; indexing requested for all new routes | EB-230 description |

## Scope Boundaries

### Inside Phase 3 (this ticket)

- 5 new Next.js pages (/quality + 4 /convert/* routes)
- Tailwind + design tokens introduction
- schema.org JSON-LD component(s) — reusable, declarative
- OG/Twitter metadata helpers
- sitemap.xml + robots.txt updates
- Synthetic academic PDF + screenshot fixtures
- Brand metadata cleanup (root layout)
- Lighthouse + CWV pass on new pages
- Google Search Console submission

### Explicitly deferred (separate tickets after Phase 3 lands)

- Backlink outreach campaign
- Email capture / newsletter signup
- Blog / ongoing content marketing
- A/B testing infrastructure
- Internationalization (English-only for v1)
- Analytics dashboard beyond what's already wired
- Privacy / cookie consent banner if EU traffic shows up (revisit when data
  shows EU visitors; for now Cloudflare-level Do Not Track is enough)
- Refactor of existing `/`, `/pricing`, `/recover`, `/status/[id]` pages to use
  the new design tokens — Phase 3 introduces the tokens but only applies them
  to the *new* pages. Refactor of existing pages becomes a follow-on ticket once
  the tokens have been battle-tested on 5 marketing pages.

## Open Questions for Plan Phase

These are explicit deferrals to `ce:plan` — not decisions, but flags to handle
before implementation starts:

1. **Synthetic PDF authoring tool.** LaTeX (most authentic academic look,
   highest setup cost) vs. Typst (modern, simpler, less "academic feel") vs.
   hand-rolled HTML + Paged.js → PDF (zero new tools but lowest fidelity).
   Plan phase decides.
2. **Screenshot pipeline automation.** Manual one-time screenshots checked
   into `public/quality/`, or scripted regeneration via Playwright + the
   synthetic PDF in the test corpus? Manual is faster; scripted is regression-
   proof for future ticket updates.
3. **JSON-LD component shape.** A single `<JsonLd schema={...} />` component
   parameterized by schema type, or one component per schema type
   (`<SoftwareApplicationSchema />`, `<FaqSchema />`, etc.). Plan decides
   based on readability of the resulting page files.
4. **Tailwind v3 vs v4.** v4 (released 2025) has a different config approach
   (CSS-first). Stability vs. modernness. Default to v4 unless a real
   incompatibility surfaces in plan.
5. **Image optimization on self-hosted Next.js.** `next/image` defaults to
   the Squoosh-based loader; self-hosted needs verification that this works
   correctly behind nginx + Cloudflare. May need a custom loader.
6. **Sitemap.xml generation strategy.** Static file checked into `public/`
   vs. dynamic Next.js route (`app/sitemap.ts`). Dynamic is more
   maintainable; static is one less surface to break.
7. **GSC verification status.** Has leafbind.io been verified in Google
   Search Console yet? If not, that's a prereq step in the plan.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Phase 3 reads as "AI SaaS slop" — copy and design feel generic — and the
  quality-aware audience that the brand targets bounces immediately | Treat
  `web-aesthetics` skill review as a gate per page; require explicit reference
  to the skill's AI-tell inventory in every page PR description |
| The synthetic academic PDF doesn't visually showcase the pipeline because
  it's too clean | Author the synthetic PDF to deliberately include the
  failure modes Calibre struggles with: multi-column body wrap, footnote
  pairing across pages, h2 vs h3 disambiguation via font size, an OCR-style
  ligature artifact. Iterate the synthetic PDF until raw Calibre output is
  visibly worse on >= 3 dimensions |
| CWV regresses on the Hetzner VM under load because nginx + `next start` is
  not as optimized as Vercel edge | Run Lighthouse from a clean Cloudflare
  cache miss before declaring CWV pass; document the cache-miss vs. cache-hit
  numbers separately; tune nginx static-asset caching headers |
| Google indexes the new pages but they don't rank because the long-tail
  keyword hypothesis is wrong | Accept this as a real outcome. Phase 3
  validates or invalidates the EB-45 keyword hypothesis. If indexed-but-
  not-ranking after 60 days, that's a signal to revisit positioning, not to
  ship more pages |
| The design tokens layer is over-engineered for 5 pages and slows down
  iteration | Keep `design-tokens.ts` small — typography scale (5 sizes),
  color palette (8 colors max), spacing ramp (Tailwind-style 4/8/12/16/24/
  32/48/64), shadow ramp (3 levels), radii (2 values). Resist adding tokens
  until the second page needs them |

## References

- **EB-230** — this ticket
- **EB-45** — parent ticket (Phase 1 + Phase 2 already shipped)
- **EB-45 brainstorm** — `docs/brainstorms/2026-05-13-freemium-web-service-requirements.md` § SEO Strategy
- **EB-45 plan** — `docs/plans/2026-05-13-001-feat-eb45-freemium-web-service-plan.md`
- **INFRA-371** — Build SEO skill for Claude Code (To Do — Phase 3 may unblock or be unblocked by this)
- **INFRA-393** — web-aesthetics skill (Done — design QA rubric for this ticket)
- **Frontend codebase** — `web_service/frontend/` (Next.js 15, App Router, React 19, no CSS framework currently)
- **Production** — https://leafbind.io
- **Brand domain memory** — `project-leafbind-domain` in auto-memory: leafbind.io registered 2026-05-13 at Cloudflare Registrar, points to Hetzner VM claude-dev-01 (5.161.228.1)
