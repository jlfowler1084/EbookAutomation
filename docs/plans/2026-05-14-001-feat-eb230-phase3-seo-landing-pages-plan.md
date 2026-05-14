---
title: "feat: EB-230 — Phase 3 SEO landing pages + quality comparison + structured data"
type: feat
status: active
date: 2026-05-14
ticket: EB-230
parent_ticket: EB-45
origin: docs/brainstorms/2026-05-14-eb230-phase3-seo-landing-pages-requirements.md
---

# feat: EB-230 — Phase 3: SEO Landing Pages + Quality Comparison + Structured Data

## Overview

Phase 1 and Phase 2 of the leafbind freemium web service are live. This plan implements
the traffic phase: a `/quality` comparison page, four keyword-targeted `/convert/*`
landing pages, Tailwind-based design foundations, schema.org structured data, sitemap,
and a Google Search Console submission. The goal is to surface leafbind.io in long-tail
Kindle converter searches where the quality gap is the differentiator.

(see origin: `docs/brainstorms/2026-05-14-eb230-phase3-seo-landing-pages-requirements.md`)

## Open Questions — Resolved in Plan Phase

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| Q1 | Synthetic PDF authoring tool | **LaTeX** | Most authentic academic fidelity; real multi-column LaTeX (e.g., two-column article class) stresses all four pipeline capabilities the page must demonstrate: column-aware extraction, heading disambiguation, footnote pairing, and figure captioning. Typst lacks the academic-paper feel; HTML+Paged.js cannot produce the complex footnote-across-page scenarios needed. |
| Q2 | Screenshot pipeline automation | **Manual + documented commands** | Screenshots are static comparison fixtures — they do not regenerate on every build, and they represent a deliberate authoring decision (which layout failures to highlight). Playwright automation adds CI complexity for a one-time capture. A `SCREENSHOTS.md` file documents exact `pdftoppm` / Playwright commands so any future maintainer can regenerate. |
| Q3 | JSON-LD component shape | **Single parameterized `<JsonLd schema={data} />`** | The only thing that varies between schema types is the shape of the data object. One component with TypeScript union types for `SoftwareApplication`, `FAQPage`, and `HowTo` keeps page files clean: each page imports one component and passes a typed object. Three per-type components would proliferate without adding clarity. |
| Q4 | Tailwind v3 vs v4 | **v3 (3.4.x)** | The frontend has no existing Tailwind installation. v4's CSS-first config approach diverges sharply from all reference material and introduces new PostCSS requirements. v3 is stable, widely documented, and what the `web-aesthetics` skill examples are calibrated against. Migrate to v4 in a follow-on ticket once the token system is established. |
| Q5 | `next/image` loader on self-hosted Next.js | **Default loader; quality comparison images served as `<img>` tags from `public/`** | The default `next/image` Squoosh-based loader works on self-hosted Next.js without custom configuration. Quality comparison screenshots are pre-optimized PNGs committed to `public/quality/` — serve them via standard `<img>` (not `next/image`) to bypass runtime processing and rely on Cloudflare edge caching. Use `next/image` only for the brand/product images in hero sections. |
| Q6 | Sitemap generation strategy | **`app/sitemap.ts` dynamic route** | Static `public/sitemap.xml` requires manual updates on every new page addition and would already be out-of-date. The dynamic route is ~15 lines of TypeScript, generates automatically on build, and is a stable Next.js built-in since Next 13.3. Drift risk is negligible. |
| Q7 | GSC verification status | **Not verified — prereq step added to Unit 0** | No `google-site-verification` token appears in any frontend file, no GSC-related DNS TXT record was found in the codebase, and leafbind.io was registered 2026-05-13 (one day before this plan). GSC property setup must be completed before Unit 8's sitemap submission has any effect. Unit 0 includes a prereq step: add DNS TXT verification record via the Cloudflare MCP. |

## Requirements Trace

| ID | Requirement | Unit |
|---|---|---|
| R1 | `/quality` page with side-by-side Calibre-vs-pipeline screenshots for >= 3 examples | Unit 2 |
| R2 | 4 keyword landing pages, each >= 800 words, internally cross-linked | Units 3–6 |
| R3 | JSON-LD on conversion pages: `SoftwareApplication`, `FAQPage`, `HowTo` | Unit 7 |
| R4 | Lighthouse SEO >= 95 on `/`, `/quality`, all `/convert/*` pages | Unit 9 |
| R5 | CWV: LCP < 2.5s, INP < 200ms, CLS < 0.1 on `/`, `/quality`, one `/convert/*` | Unit 9 |
| R6 | sitemap.xml lists all new routes; robots.txt allows them | Unit 8 |
| R7 | OpenGraph + Twitter Card metadata on every new page | Unit 7 |
| R8 | Brand metadata cleanup: title/description/OG reflect "leafbind" | Unit 0 |
| R9 | `design-tokens.ts` + Tailwind config; no raw Tailwind defaults in JSX | Unit 0 |
| R10 | Each new page passes web-aesthetics skill review before merge | Units 2–6 |
| R11 | Synthetic PDF committed under `test-pdfs/`; screenshots under `public/quality/` | Unit 1 |
| R12 | Sitemap submitted to GSC; indexing requested | Unit 8 |

## Scope Boundaries

### Inside Phase 3 (this ticket)

- Design tokens + Tailwind introduction (new pages only; existing pages untouched)
- `/quality` page + 4 `/convert/*` landing pages
- Single `<JsonLd />` component + schema data for each page
- OG/Twitter metadata on all new pages
- `app/sitemap.ts` + `app/robots.ts`
- Synthetic academic PDF + comparison screenshots
- Brand metadata cleanup in root `app/layout.tsx`
- Lighthouse/CWV audit and fixes
- GSC property setup + sitemap submission

### Explicitly deferred

- Refactor of existing `/`, `/pricing`, `/recover`, `/status/[id]` to use design tokens
  (Phase 3 tokens are battle-tested on 5 pages first; refactor is a follow-on ticket)
- Backlink outreach, email capture, A/B testing, blog/content marketing
- Internationalization, analytics dashboard, cookie consent

## Context

### Frontend state at plan time

| File | Relevant state |
|---|---|
| `app/layout.tsx` | Title is `"EbookAutomation — Ebook Converter"` — the only field needing brand cleanup. No CSS imports; body uses a single inline `style` attribute. |
| `app/page.tsx` | Upload form, inline styles only |
| `app/pricing/page.tsx` | Already uses `"Pricing — Leafbind"` in its own metadata export — brand cleanup applies only to the root layout default |
| `package.json` | Next.js 15.1.0, React 19, TypeScript 5, no CSS framework |
| `next.config.js` | Minimal; no image optimizer override; `NEXT_PUBLIC_API_URL` env var |
| `public/` | Does not exist yet — must be created in Unit 1 before any static asset commits |

### Key cross-phase invariants

- Phase 1 + Phase 2 are live and serving production traffic. Every Unit in Phase 3 must ship
  without breaking `/`, `/pricing`, `/recover`, and `/status/[id]`.
- The Hetzner VM (`claude-dev-01`) runs `next start` directly — no Vercel edge functions.
  Cloudflare is the CDN layer. `next build` runs on the VM at deploy time.
- Tailwind's CSS reset (`@tailwind base` / Preflight) MUST be disabled in `tailwind.config.js`
  via `corePlugins: { preflight: false }`. All existing pages use only inline styles — a
  Preflight reset would change browser defaults (margin, font inheritance, element sizing) for
  every existing page. With Preflight disabled, Tailwind utilities work on new pages and
  existing pages are completely unaffected.

## System-Wide Impact

| Area | Impact | Mitigation |
|---|---|---|
| `app/layout.tsx` | Brand metadata change touches the production SSR root layout | Change is a pure string swap in the `metadata` export — zero runtime code path. Verify `next build` completes clean before deploying. |
| Tailwind introduction | Adding `globals.css` + PostCSS config affects `next build` output for all pages | Disable Preflight (`corePlugins: { preflight: false }`). Tailwind JIT scans only files in `content` config; unused utilities are not emitted. CSS bundle delta is ~10–15 KB minified. |
| `next build` memory on VM | Adding 5 new pages + Tailwind JIT compilation on the shared Hetzner VM | Tailwind JIT at this scale is well under 512 MB. The larger build memory risk is if quality comparison images (large PNGs) are accidentally included in `content` glob rather than served from `public/`. Keep images in `public/`; keep `content` glob to `app/**/*.tsx` + `components/**/*.tsx`. |
| sitemap.ts | Adds a new build-time route; must include all existing routes | Cross-check against `app/` directory structure before merging Unit 8. Routes to include: `/`, `/pricing`, `/recover`, `/quality`, `/convert/pdf-to-kfx`, `/convert/academic-pdf-to-kindle`, `/convert/pdf-footnotes-kindle`, `/convert/multi-column-pdf-kindle`. Exclude: `/status/[id]` (dynamic, not indexable). |

## Output Structure

```
web_service/
├── test-pdfs/
│   ├── leafbind-demo.tex          # Synthetic academic PDF source (LaTeX)
│   ├── leafbind-demo.pdf          # Compiled output (committed binary)
│   └── SCREENSHOTS.md             # How to regenerate comparison screenshots
└── frontend/
    ├── design-tokens.ts           # Typography, color, spacing, shadows, radii
    ├── tailwind.config.js         # Pulls from design-tokens.ts; preflight disabled
    ├── postcss.config.js          # tailwindcss + autoprefixer
    ├── package.json               # + tailwindcss, autoprefixer, postcss
    ├── app/
    │   ├── globals.css            # @tailwind components; @tailwind utilities (no base)
    │   ├── layout.tsx             # Brand metadata cleanup; globals.css import
    │   ├── sitemap.ts             # Dynamic sitemap route
    │   ├── robots.ts              # robots.txt route
    │   ├── quality/
    │   │   └── page.tsx           # /quality — comparison page (canary)
    │   └── convert/
    │       ├── pdf-to-kfx/
    │       │   └── page.tsx
    │       ├── academic-pdf-to-kindle/
    │       │   └── page.tsx
    │       ├── pdf-footnotes-kindle/
    │       │   └── page.tsx
    │       └── multi-column-pdf-kindle/
    │           └── page.tsx
    ├── components/
    │   └── JsonLd.tsx             # <JsonLd schema={data} /> with TS types
    ├── lib/
    │   └── structured-data.ts     # Schema builder functions + TypeScript types
    └── public/
        └── quality/
            ├── calibre-column-1.png
            ├── pipeline-column-1.png
            ├── calibre-footnotes-1.png
            ├── pipeline-footnotes-1.png
            ├── calibre-headings-1.png
            └── pipeline-headings-1.png
```

---

## Implementation Units

- [ ] **Unit 0: Design foundations + Tailwind setup + brand metadata cleanup + GSC prereq**

**Goal:** Install Tailwind v3, wire design tokens, import globals.css in the root layout,
clean up brand metadata, and verify or establish the GSC property for leafbind.io.
This unit is the foundation every subsequent unit builds on. No page content is written here.

**Requirements satisfied:** R8, R9

**Dependencies:** None

**Files:**
- Modify: `web_service/frontend/package.json`
- Create: `web_service/frontend/tailwind.config.js`
- Create: `web_service/frontend/postcss.config.js`
- Create: `web_service/frontend/design-tokens.ts`
- Create: `web_service/frontend/app/globals.css`
- Modify: `web_service/frontend/app/layout.tsx`

**Steps:**

1. Install Tailwind v3 and PostCSS:
   ```powershell
   cd web_service\frontend
   npm install -D tailwindcss@^3.4 autoprefixer postcss
   ```

2. Create `web_service/frontend/postcss.config.js`:
   ```js
   module.exports = {
     plugins: { tailwindcss: {}, autoprefixer: {} },
   };
   ```

3. Create `web_service/frontend/design-tokens.ts`. Keep the system small — only tokens
   that at least two new pages will use:
   ```ts
   export const colors = {
     brand:    "#1a1a2e",
     accent:   "#e8642c",
     muted:    "#6b7280",
     surface:  "#f9f7f4",
     border:   "#e5e7eb",
     textBase: "#1f2937",
   } as const;

   export const type = {
     fontSans: '"Inter", ui-sans-serif, system-ui, sans-serif',
     fontSerif: '"Lora", ui-serif, Georgia, serif',
     // Modular scale: 12/14/16/20/24/32/48
     scaleXs:  "0.75rem",
     scaleSm:  "0.875rem",
     scaleMd:  "1rem",
     scaleLg:  "1.25rem",
     scaleXl:  "1.5rem",
     scale2Xl: "2rem",
     scale3Xl: "3rem",
   } as const;

   export const space = {
     // 4-point base: 4/8/12/16/24/32/48/64
     1: "0.25rem", 2: "0.5rem", 3: "0.75rem",
     4: "1rem",   6: "1.5rem", 8: "2rem",
     12: "3rem",  16: "4rem",
   } as const;

   export const shadows = {
     sm:  "0 1px 3px 0 rgb(0 0 0 / 0.08)",
     md:  "0 4px 12px 0 rgb(0 0 0 / 0.10)",
     lg:  "0 8px 24px 0 rgb(0 0 0 / 0.12)",
   } as const;

   export const radii = {
     sm: "0.25rem",
     md: "0.5rem",
   } as const;
   ```

4. Create `web_service/frontend/tailwind.config.js`. Pull token values from
   `design-tokens.ts`. Disable Preflight to protect existing inline-styled pages.
   ```js
   const { colors, type, space, shadows, radii } = require("./design-tokens");

   /** @type {import('tailwindcss').Config} */
   module.exports = {
     content: [
       "./app/**/*.{ts,tsx}",
       "./components/**/*.{ts,tsx}",
     ],
     corePlugins: {
       preflight: false,   // CRITICAL: existing pages use inline styles only
     },
     theme: {
       extend: {
         colors: {
           brand:   colors.brand,
           accent:  colors.accent,
           muted:   colors.muted,
           surface: colors.surface,
           border:  colors.border,
           "text-base": colors.textBase,
         },
         fontFamily: {
           sans:  [type.fontSans],
           serif: [type.fontSerif],
         },
         boxShadow: shadows,
         borderRadius: {
           sm: radii.sm,
           md: radii.md,
         },
       },
     },
     plugins: [],
   };
   ```

5. Create `web_service/frontend/app/globals.css`. Omit `@tailwind base` (that's
   Preflight — already disabled in config, but belt-and-suspenders):
   ```css
   @tailwind components;
   @tailwind utilities;
   ```

6. Edit `web_service/frontend/app/layout.tsx` to import globals.css and update
   brand metadata:
   ```tsx
   import "./globals.css";
   import { type Metadata } from "next";

   export const metadata: Metadata = {
     title: "leafbind — PDF to Kindle Converter",
     description:
       "Convert PDFs to Kindle KFX with smart heading detection, footnote linking, " +
       "and multi-column layout support. Free tier available.",
     openGraph: {
       siteName: "leafbind",
       url: "https://leafbind.io",
     },
   };

   export default function RootLayout({ children }: { children: React.ReactNode }) {
     return (
       <html lang="en">
         <body style={{ margin: 0, background: "#fff", color: "#111" }}>
           {children}
         </body>
       </html>
     );
   }
   ```
   The body `style` attribute is intentionally preserved — it is the existing
   production baseline for all existing pages.

7. Run `next build` from `web_service/frontend/` and verify: no TypeScript errors,
   no missing module warnings, and the bundle output lists no unexpected large CSS chunk.
   Expected: Tailwind CSS chunk < 30 KB gzipped for this token set.

8. **GSC prereq — verify or establish the leafbind.io property:**
   - Open Google Search Console at https://search.google.com/search-console
   - Check whether `https://leafbind.io` already exists as a verified property.
   - If NOT verified: choose "DNS record" verification method. GSC will provide a
     `google-site-verification=...` TXT record value.
   - Add the TXT record via the Cloudflare MCP:
     ```
     zone: leafbind.io
     type: TXT
     name: @
     content: google-site-verification=<value from GSC>
     ttl: 300
     ```
   - Click "Verify" in GSC after the TXT propagates (~5–10 min at Cloudflare).
   - Record the verified status; Unit 8 will submit the sitemap to this property.

**Complexity:** Medium (Tailwind install + config is straightforward; GSC DNS step
is manual but well-defined)

**Gotchas:**
- `tailwind.config.js` must use `require("./design-tokens")` — NOT `import`. Tailwind
  config runs in CommonJS context, not ESM.
- `content` glob must match the exact paths used by new page files or Tailwind JIT
  will not emit the utility classes used by those pages.
- `postcss.config.js` must exist in `web_service/frontend/` (Next.js detects PostCSS
  config in the project root, which for the frontend build is this directory).
- `tailwind.config.js` — the `design-tokens.ts` TypeScript file must be required as
  CommonJS. If TypeScript compilation conflicts arise, copy the token values inline
  into the Tailwind config (duplication acceptable here; the TS file is the SST for
  the implementation).

---

- [ ] **Unit 1: Synthetic academic PDF + comparison screenshots**

**Goal:** Author a synthetic LaTeX academic paper that deliberately exhibits the four
failure modes Calibre raw conversion struggles with. Compile it to PDF. Convert it
through both the free tier (Calibre only) and the premium pipeline. Capture side-by-side
screenshots for >= 3 comparison examples. Commit all artifacts.

**Requirements satisfied:** R11

**Dependencies:** Unit 0 (directory structure exists; `public/` must be created)

**Files:**
- Create: `web_service/test-pdfs/leafbind-demo.tex`
- Create: `web_service/test-pdfs/leafbind-demo.pdf` (compiled binary)
- Create: `web_service/frontend/public/quality/` (directory + screenshots)
- Create: `web_service/test-pdfs/SCREENSHOTS.md`

**Synthetic PDF specification:**

The LaTeX document must include all four target failure modes:
1. **Two-column layout** — use `\documentclass[twocolumn]{article}`. Calibre's raw
   text extraction will concatenate columns in reading order, producing garbled text.
   The pipeline's column-aware extraction will preserve column boundaries.
2. **Footnotes with backreferences** — at least 5 footnotes using `\footnote{}`, two
   of which must be on the same page, one spanning a page boundary. Calibre's EPUB
   output loses footnote-body associations; the pipeline links them.
3. **Heading disambiguation by font size** — use `\section{}`, `\subsection{}`, and
   `\subsubsection{}` for at least 6 headings. Calibre detects none; the pipeline
   classifies them by rendered font size.
4. **Figure with caption** — one `\begin{figure}` with `\caption{}`. Calibre's EPUB
   may lose the figure-caption relationship.

Structure: "The Epistemology of Computational Systems" — a plausible academic paper
title that avoids real intellectual content concerns. Include an abstract, 3 sections
with subsections, a bibliography (`\bibliography{}`), and 2–3 inline citations. Use
Latin placeholder body text (`\usepackage{lipsum}`, `\lipsum[1-3]`) so the paper looks
real without needing actual academic writing.

**Screenshot capture steps:**

After compiling the LaTeX to PDF:
1. Convert via free tier:
   ```powershell
   # On the VM (claude-dev-01):
   ebook-convert leafbind-demo.pdf leafbind-demo-calibre.epub
   ```
2. Convert via premium pipeline:
   ```powershell
   python tools/pdf_to_balabolka.py --cli --input web_service/test-pdfs/leafbind-demo.pdf
   ```
3. Open both outputs in a Kindle simulator or ebook viewer. Capture screenshots of:
   - The two-column page (Calibre: garbled; pipeline: clean)
   - A footnoted page (Calibre: footnote lost; pipeline: linked)
   - A heading-heavy page (Calibre: headings as plain text; pipeline: h2/h3 hierarchy)

Screenshot file naming convention:
```
public/quality/
  calibre-columns.png       # Calibre output of the two-column page
  pipeline-columns.png      # Pipeline output
  calibre-footnotes.png
  pipeline-footnotes.png
  calibre-headings.png
  pipeline-headings.png
```

All PNGs should be cropped to the relevant region (not full-screen), approximately
800×600px each, exported as PNG-24 for maximum fidelity. Total expected size: 500 KB–2 MB
for all 6 images combined.

**SCREENSHOTS.md contents:**

Document: (a) the LaTeX compilation command; (b) the exact `ebook-convert` command used
for the free tier; (c) the `pdf_to_balabolka.py --cli` invocation used for the premium
tier; (d) the ebook viewer + screenshot tool used; (e) the exact crop dimensions. This
ensures any future maintainer can regenerate identical fixtures.

**Complexity:** High (LaTeX authoring + multi-step pipeline run + manual visual judgment)

**Gotchas:**
- LaTeX requires `pdflatex` or `xelatex` installed. On Windows desktop, install
  MiKTeX (`winget install MiKTeX.MiKTeX`). On the VM, install `texlive-latex-recommended`.
- `lipsum` package must be installed (`\usepackage{lipsum}`); available in MiKTeX/TeX Live.
- The two-column layout in LaTeX uses `\documentclass[twocolumn]{article}`. Verify the
  compiled PDF actually renders in two columns before running conversions.
- The premium pipeline (Unit 2 of Phase 1 plan) requires the VM to be running and the
  pipeline to be deployed. If running on the desktop, run the pipeline locally via
  `python tools/pdf_to_balabolka.py` with local Calibre.
- Binary files (PDF, PNG) should be committed with an explicit `git add --no-ignore-removal`
  to avoid `.gitignore` exclusions on `*.pdf` if any exist.

---

- [ ] **Unit 2: /quality page (canary)**

**Goal:** Build the `/quality` comparison page. This is the most image-heavy page and the
most-shared single page. It ships first to surface any CWV or design issues before the
landing pages are built on the same foundation. Must pass the `web-aesthetics` skill review.

**Requirements satisfied:** R1, R7, R10 (design review gate)

**Dependencies:** Unit 0 (Tailwind + tokens), Unit 1 (screenshots in `public/quality/`)

**Files:**
- Create: `web_service/frontend/app/quality/page.tsx`

**Page content requirements:**

The page must satisfy the `web-aesthetics` skill review (INFRA-393). Key criteria:
- No `slate-900`, no `indigo-600`, no default Tailwind color names in JSX
- No generic SaaS hero pattern ("Convert your ebooks today!")
- Typography: at least two type sizes from the scale; Inter for UI, Lora (or a
  distinctive serif) for any editorial text
- Grid: at least one meaningful asymmetric layout (e.g., 60/40 split for the
  comparison pairs, not just full-width stacked images)
- Comparison pairs use a real 2-up layout, not just two images stacked vertically
- Explanatory copy calls out the specific failure the pipeline fixes, not generic
  marketing copy

Suggested structure:
```
<h1> Why leafbind converts academic PDFs better than Calibre </h1>
<p class="lead"> Brief explanation of the three problems shown below </p>

Section 1: Two-column layout
  <h2> Multi-column PDFs </h2>
  <p> 1–2 sentences: what Calibre does wrong, why it happens, what the pipeline does </p>
  [side-by-side comparison: calibre-columns.png vs pipeline-columns.png]

Section 2: Footnotes
  [same structure]

Section 3: Heading detection
  [same structure]

CTA: Upload your own PDF → links to / (the upload page)
Internal links: to /convert/academic-pdf-to-kindle, /convert/pdf-footnotes-kindle,
  /convert/multi-column-pdf-kindle
```

**Metadata export (in `quality/page.tsx`):**
```tsx
export const metadata: Metadata = {
  title: "PDF to Kindle Quality Comparison — leafbind",
  description:
    "See how leafbind converts multi-column layouts, footnotes, and academic heading " +
    "structures that Calibre gets wrong. Side-by-side before/after screenshots.",
  openGraph: {
    title: "PDF to Kindle Quality Comparison — leafbind",
    description: "Side-by-side comparison: Calibre vs. leafbind on multi-column academic PDFs.",
    images: [{ url: "/quality/pipeline-columns.png", width: 800, height: 600 }],
    type: "website",
    url: "https://leafbind.io/quality",
  },
  twitter: {
    card: "summary_large_image",
    title: "PDF to Kindle Quality Comparison — leafbind",
    description: "Side-by-side comparison: Calibre vs. leafbind on multi-column academic PDFs.",
    images: ["/quality/pipeline-columns.png"],
  },
};
```

**Image rendering:** Serve comparison screenshots as standard `<img>` (not `next/image`)
with explicit `width`, `height`, and `alt` attributes. Example:
```tsx
<img
  src="/quality/calibre-columns.png"
  alt="Calibre output showing garbled two-column text merged into a single run-on paragraph"
  width={800}
  height={600}
  style={{ width: "100%", height: "auto", display: "block" }}
/>
```
The `width`/`height` attributes prevent CLS (Cumulative Layout Shift) by reserving space
before the image loads. The `style` makes them responsive.

**Verification:**
- `next build` completes without errors
- Manual browser check: page renders correctly at 1440px, 1024px, 768px, 375px
- All 6 comparison images load
- Internal links to `/convert/*` pages work (those pages exist after Units 3–6)
- Run `web-aesthetics` skill review as a gate before merging this unit's PR

**Complexity:** Medium-High (design judgment required; web-aesthetics gate)

**Gotchas:**
- Images in `public/quality/` are served from `https://leafbind.io/quality/*.png` —
  verify the paths match the filenames committed in Unit 1.
- The comparison layout must NOT just be two vertically-stacked images — that fails
  the web-aesthetics grid criterion. Use CSS Grid or Flexbox for a 2-up layout.
- The `openGraph.images` URL in metadata must be an absolute URL or a path that
  resolves correctly from the OG crawler. Use an absolute URL with `https://leafbind.io`.

---

- [ ] **Unit 3: /convert/pdf-to-kfx landing page**

**Goal:** Build the first keyword-targeted landing page: `/convert/pdf-to-kfx`. This is
the lowest-competition, best-brand-fit keyword ("convert PDF to KFX" — no other tool
markets this term explicitly). The page demonstrates the tool's unique capability.

**Requirements satisfied:** R2, R7, R10

**Dependencies:** Unit 0 (Tailwind), Unit 2 (cross-link from /quality page)

**Files:**
- Create: `web_service/frontend/app/convert/pdf-to-kfx/page.tsx`

**Page content requirements (>= 800 words):**

Required sections:
1. **H1:** "Convert PDF to KFX for Kindle — Smart Formatting Preserved"
2. **What is KFX?** (~150 words): explain KFX as the native Kindle format, why it
   renders better than EPUB/MOBI (reflow, typography, custom fonts)
3. **Why most converters fail on PDF → KFX** (~150 words): explain the two-step
   chain (PDF → EPUB → KFX), how Calibre loses heading structure and footnotes in
   the PDF-to-EPUB step, and how that compounds in KFX
4. **How leafbind does it differently** (~150 words): heading detection, footnote
   linking, column-aware extraction — the pipeline advantages. Link to `/quality`
   for visual proof.
5. **How to convert** (~100 words): a numbered HowTo list:
   1. Upload your PDF
   2. Select KFX as output format (premium)
   3. Download and send to your Kindle
6. **FAQ** (~200 words): 3–4 questions/answers:
   - "Is KFX available in the free tier?" (No — premium only; link to /pricing)
   - "What PDF types work best?" (text-based academic, technical, non-fiction)
   - "Will my footnotes survive?" (Yes, with the premium pipeline)
   - "What Kindle models support KFX?" (Kindle Paperwhite, Kindle, Kindle Scribe — all post-2018)
7. **CTA:** Link to the upload page at `/`

Internal cross-links: `/quality`, `/convert/academic-pdf-to-kindle`, `/pricing`

**Metadata export:**
```tsx
export const metadata: Metadata = {
  title: "Convert PDF to KFX for Kindle — leafbind",
  description:
    "Convert PDF to KFX Kindle format with smart heading detection, footnote linking, " +
    "and multi-column layout support. Premium pipeline. No account required.",
  openGraph: {
    title: "Convert PDF to KFX for Kindle — leafbind",
    description:
      "Smart PDF to KFX conversion for Kindle — heading structure, footnotes, and " +
      "multi-column layouts handled correctly.",
    type: "website",
    url: "https://leafbind.io/convert/pdf-to-kfx",
  },
  twitter: {
    card: "summary",
    title: "Convert PDF to KFX for Kindle — leafbind",
    description: "Smart PDF to KFX conversion for Kindle.",
  },
};
```

**Complexity:** Medium (content + Tailwind layout; web-aesthetics gate)

**Gotchas:**
- The page must cross-link to `/quality` for visual proof of quality claims — without
  this link, the content reads as unsupported marketing copy.
- KFX output requires premium tier — the page must clearly state this and link to `/pricing`.
  Do not imply free-tier KFX output.

---

- [ ] **Unit 4: /convert/academic-pdf-to-kindle**

**Goal:** Build the second landing page: `/convert/academic-pdf-to-kindle`. This targets
the primary user persona — academic or technical readers converting research papers,
textbooks, and conference proceedings. This page explains the specific challenges of
academic PDF layout (double-column, numbered sections, footnotes, citations, figures
with captions) and how the pipeline handles them.

**Requirements satisfied:** R2, R7, R10

**Dependencies:** Unit 0, Unit 2 (cross-link)

**Files:**
- Create: `web_service/frontend/app/convert/academic-pdf-to-kindle/page.tsx`

**Page content requirements (>= 800 words):**

Required sections:
1. **H1:** "Convert Academic PDFs to Kindle — Columns, Footnotes, and Headings Preserved"
2. **The academic PDF problem** (~150 words): IEEE/ACM double-column layout, numbered
   headings (1.1, 1.2.1), footnotes with journal-style positioning, inline citations
   (Author, Year), and figure captions — all of which Calibre's raw conversion breaks.
3. **What the pipeline preserves** (~200 words): detail each of the four pipeline
   capabilities relevant to academic PDFs. Link to `/quality` for visual proof.
4. **Supported document types** (~100 words): IEEE papers, arXiv preprints, ACM
   proceedings, university theses, textbooks, technical manuals. Not: scanned PDFs
   (OCR limitations), PDFs with complex equations (math rendering is outside scope for v1).
5. **HowTo** (~100 words): numbered steps as above.
6. **FAQ** (~200 words):
   - "Does it work on scanned academic PDFs?" (Limited — OCR fallback exists but
     complex math and diagrams are not reconstructed)
   - "Will chapter numbers survive?" (Yes — numbered headings (1.1, 1.2) are detected)
   - "What about inline citations?" ([1], (Author, 2022) — treated as body text, not
     stripped)
   - "Is there a file size limit?" (20MB free, 100MB premium)

Internal cross-links: `/quality`, `/convert/pdf-to-kfx`, `/convert/pdf-footnotes-kindle`

**Metadata:**
```tsx
export const metadata: Metadata = {
  title: "Convert Academic PDFs to Kindle — leafbind",
  description:
    "Academic PDF to Kindle converter that preserves double-column layouts, " +
    "footnotes, section numbering, and figure captions. Free and premium tiers.",
  openGraph: {
    title: "Convert Academic PDFs to Kindle — leafbind",
    description: "Preserves double-column layouts, footnotes, and section numbering.",
    type: "website",
    url: "https://leafbind.io/convert/academic-pdf-to-kindle",
  },
  twitter: {
    card: "summary",
    title: "Convert Academic PDFs to Kindle — leafbind",
    description: "Academic PDF to Kindle: columns, footnotes, and numbering preserved.",
  },
};
```

**Complexity:** Medium

---

- [ ] **Unit 5: /convert/pdf-footnotes-kindle**

**Goal:** Build the third landing page: `/convert/pdf-footnotes-kindle`. This is the
narrowest niche and easiest to rank — "PDF footnotes Kindle" is a very specific query
that signals high purchase intent (the user has already failed with another converter
and is searching for a specific fix).

**Requirements satisfied:** R2, R7, R10

**Dependencies:** Unit 0, Unit 2 (cross-link)

**Files:**
- Create: `web_service/frontend/app/convert/pdf-footnotes-kindle/page.tsx`

**Page content requirements (>= 800 words):**

Required sections:
1. **H1:** "PDF Footnotes on Kindle — Keep Them Linked and Readable"
2. **The footnote problem on Kindle** (~150 words): explain how Calibre and most converters
   strip footnote backreferences, making footnoted books unreadable on Kindle (foot of page
   is not a concept in ebook reflow — footnotes must become inline popups via `<aside>`
   or endnote links). Explain what a broken footnote looks like on device.
3. **How leafbind links footnotes** (~200 words): the pipeline detects footnote markers
   (superscript numbers, symbols), extracts the footnote body text, and generates linked
   `<a>` pairs in the EPUB/KFX output. Jump-to-footnote, jump-back-to-text.
4. **Types of footnotes handled** (~100 words): numeric superscripts (¹), symbolic (*, †),
   inline parenthetical notes, endnotes at chapter end. Note: footnotes in scanned PDFs
   (image-only) are outside scope.
5. **HowTo** steps.
6. **FAQ** (~200 words):
   - "Will footnotes work in the free tier?" (Basic linking — yes; full endnote
     backreference generation — premium only)
   - "What about books with 500+ footnotes?" (No limit on footnote count; tested on
     Decline of the West with multi-chapter footnote sequences)
   - "Do footnotes become popups on Kindle?" (Yes, on Kindle Paperwhite/Scribe with
     KFX format; EPUB footnotes open as linked pages on older Kindles)

Internal cross-links: `/quality`, `/convert/academic-pdf-to-kindle`

**Metadata:**
```tsx
export const metadata: Metadata = {
  title: "PDF Footnotes on Kindle — Keep Them Linked | leafbind",
  description:
    "Convert PDFs with footnotes to Kindle EPUB or KFX. leafbind links footnote " +
    "markers to footnote text so you can jump back and forth on device.",
  openGraph: {
    title: "PDF Footnotes on Kindle — Keep Them Linked | leafbind",
    description: "Footnote markers and text are linked — not stripped — in the Kindle output.",
    type: "website",
    url: "https://leafbind.io/convert/pdf-footnotes-kindle",
  },
  twitter: {
    card: "summary",
    title: "PDF Footnotes on Kindle — Keep Them Linked | leafbind",
    description: "Convert PDFs with footnotes to Kindle. Backreferences preserved.",
  },
};
```

**Complexity:** Medium

---

- [ ] **Unit 6: /convert/multi-column-pdf-kindle**

**Goal:** Build the fourth landing page: `/convert/multi-column-pdf-kindle`. This supports
the academic use case and targets users who have already tried Calibre and gotten garbled
column-merged output. The target query is someone who Googled "convert multi-column PDF
to Kindle" after a bad experience.

**Requirements satisfied:** R2, R7, R10

**Dependencies:** Unit 0, Unit 2 (cross-link), Unit 3 (cross-link to /convert/pdf-to-kfx)

**Files:**
- Create: `web_service/frontend/app/convert/multi-column-pdf-kindle/page.tsx`

**Page content requirements (>= 800 words):**

Required sections:
1. **H1:** "Convert Multi-Column PDFs to Kindle — Columns Read in the Right Order"
2. **What goes wrong with multi-column PDFs** (~150 words): explain the column-merge bug
   — most converters extract text left-to-right across the full page width, which
   interleaves the two columns. The result: sentence from column 1 line 1, sentence from
   column 2 line 1, column 1 line 2, column 2 line 2 — unreadable.
3. **How leafbind detects columns** (~200 words): describe the coordinate-based column
   detection (pdfplumber x0/x1 bounding boxes, column boundary identification, per-column
   sequential extraction). Reference the comparison images on `/quality`.
4. **What document types have multi-column layouts** (~100 words): IEEE/ACM papers,
   newspaper archives, some medical journals, legal documents, historical texts.
5. **HowTo** steps.
6. **FAQ** (~200 words):
   - "Does it work on 3-column layouts?" (Yes — the column detector handles 2–3 columns;
     4+ is uncommon and may fall back to single-column extraction)
   - "What about mixed layouts (some single-column pages, some double)?" (Handled — each
     page is analyzed independently)
   - "Will tables survive multi-column detection?" (Tables are extracted as-is; complex
     tables that span columns may need manual verification)

Internal cross-links: `/quality`, `/convert/academic-pdf-to-kindle`, `/convert/pdf-to-kfx`

**Metadata:**
```tsx
export const metadata: Metadata = {
  title: "Convert Multi-Column PDFs to Kindle — leafbind",
  description:
    "Multi-column PDF to Kindle converter. leafbind reads each column independently " +
    "so the text flows correctly on Kindle — not interleaved across columns.",
  openGraph: {
    title: "Convert Multi-Column PDFs to Kindle — leafbind",
    description:
      "Reads each column independently. Text flows correctly on Kindle, not merged.",
    type: "website",
    url: "https://leafbind.io/convert/multi-column-pdf-kindle",
  },
  twitter: {
    card: "summary",
    title: "Convert Multi-Column PDFs to Kindle — leafbind",
    description: "Multi-column PDF to Kindle: each column read in order.",
  },
};
```

**Complexity:** Medium

---

- [ ] **Unit 7: JSON-LD structured data + OG/Twitter metadata sweep**

**Goal:** Build the `<JsonLd />` component and apply `SoftwareApplication`, `FAQPage`,
and `HowTo` schema to all 5 pages. Verify metadata is complete on all pages.

**Requirements satisfied:** R3, R7

**Dependencies:** Units 2–6 (all pages must exist)

**Files:**
- Create: `web_service/frontend/lib/structured-data.ts`
- Create: `web_service/frontend/components/JsonLd.tsx`
- Modify: `web_service/frontend/app/quality/page.tsx` (add `SoftwareApplication` + `/quality` schemas)
- Modify: `web_service/frontend/app/convert/pdf-to-kfx/page.tsx` (add all 3 schemas)
- Modify: `web_service/frontend/app/convert/academic-pdf-to-kindle/page.tsx`
- Modify: `web_service/frontend/app/convert/pdf-footnotes-kindle/page.tsx`
- Modify: `web_service/frontend/app/convert/multi-column-pdf-kindle/page.tsx`

**`lib/structured-data.ts`** — TypeScript types + builder functions:

```ts
export interface SoftwareApplicationSchema {
  "@context": "https://schema.org";
  "@type": "SoftwareApplication";
  name: string;
  applicationCategory: string;
  operatingSystem: string;
  offers: { "@type": "Offer"; price: string; priceCurrency: string };
  url: string;
  description: string;
}

export interface FAQPageSchema {
  "@context": "https://schema.org";
  "@type": "FAQPage";
  mainEntity: Array<{
    "@type": "Question";
    name: string;
    acceptedAnswer: { "@type": "Answer"; text: string };
  }>;
}

export interface HowToSchema {
  "@context": "https://schema.org";
  "@type": "HowTo";
  name: string;
  step: Array<{ "@type": "HowToStep"; name: string; text: string }>;
}

export type SchemaData = SoftwareApplicationSchema | FAQPageSchema | HowToSchema;

export function buildSoftwareApplicationSchema(): SoftwareApplicationSchema {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "leafbind PDF to Kindle Converter",
    applicationCategory: "UtilitiesApplication",
    operatingSystem: "Web",
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
    url: "https://leafbind.io",
    description:
      "Convert PDFs to Kindle KFX with smart heading detection, footnote linking, " +
      "and multi-column layout support.",
  };
}
```

**`components/JsonLd.tsx`:**

```tsx
import type { SchemaData } from "../lib/structured-data";

export default function JsonLd({ schema }: { schema: SchemaData }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
```

`dangerouslySetInnerHTML` is the correct and standard pattern for JSON-LD injection in
React/Next.js. The schema data is constructed in TypeScript (not user-controlled), so
there is no XSS risk.

**Per-page schema data:** Each `/convert/*` page needs all 3 schemas:
- `SoftwareApplication`: same for all pages (use `buildSoftwareApplicationSchema()`)
- `FAQPage`: derived from the FAQ section already written in the page (Unit 3–6 copy)
- `HowTo`: derived from the HowTo steps section (same 3-step sequence for all pages)

The `/quality` page needs only `SoftwareApplication` (no FAQ or HowTo — it's a
comparison page, not a conversion CTA page).

**Usage in a page file:**
```tsx
import JsonLd from "../../components/JsonLd";
import { buildSoftwareApplicationSchema } from "../../lib/structured-data";

// In the page component:
<>
  <JsonLd schema={buildSoftwareApplicationSchema()} />
  <JsonLd schema={faqData} />
  <JsonLd schema={howToData} />
  {/* ... page content ... */}
</>
```

**Verification:**
- Run each page URL through the Google Rich Results Test after deployment
  (https://search.google.com/test/rich-results)
- Expected: FAQPage and HowTo schemas pass validation; SoftwareApplication may show
  as "detected but not eligible for rich results" — this is acceptable
- No "Missing required field" errors in the test output

**OG/Twitter sweep:** Confirm that every new page has `metadata.openGraph.images`
pointing to a real image URL. For pages without a dedicated OG image, use the
leafbind logo at `/logo.png` (to be created or confirmed as existing in Unit 1/0).
If no logo exists in `public/`, add a 1200×630 placeholder in this unit.

**Complexity:** Medium (TypeScript typing + per-page sweep)

---

- [ ] **Unit 8: sitemap.xml + robots.txt + GSC submission**

**Goal:** Generate a correct sitemap listing all indexable pages, verify robots.txt
allows them, and submit to Google Search Console.

**Requirements satisfied:** R6, R12

**Dependencies:** Units 2–7 (all new routes must exist before sitemap is finalized)

**Files:**
- Create: `web_service/frontend/app/sitemap.ts`
- Create: `web_service/frontend/app/robots.ts`

**`app/sitemap.ts`:**

```ts
import { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://leafbind.io";
  const now = new Date();

  return [
    { url: `${base}/`,                                  lastModified: now, changeFrequency: "weekly",  priority: 1.0 },
    { url: `${base}/pricing`,                           lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/quality`,                           lastModified: now, changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/convert/pdf-to-kfx`,                lastModified: now, changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/convert/academic-pdf-to-kindle`,    lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/convert/pdf-footnotes-kindle`,      lastModified: now, changeFrequency: "monthly", priority: 0.7 },
    { url: `${base}/convert/multi-column-pdf-kindle`,   lastModified: now, changeFrequency: "monthly", priority: 0.7 },
  ];
  // Excluded: /recover (utility page, low SEO value), /status/[id] (dynamic, non-indexable)
}
```

**`app/robots.ts`:**

```ts
import { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/status/", "/api/"],
      },
    ],
    sitemap: "https://leafbind.io/sitemap.xml",
  };
}
```

**GSC submission steps:**
1. Navigate to https://search.google.com/search-console and select the leafbind.io property
   (verified in Unit 0)
2. Open Sitemaps → Add a new sitemap → Enter `sitemap.xml`
3. Submit. GSC will crawl and report the number of URLs discovered.
4. Open URL Inspection for each of the 5 new pages. Request indexing.
5. Record the submission date. Expect indexing within 1–7 days.

**Verification:**
- `curl https://leafbind.io/sitemap.xml` returns XML with all 7 URLs
- `curl https://leafbind.io/robots.txt` returns the allow/disallow rules
- GSC Sitemaps dashboard shows "Success" with 7 URLs submitted

**Complexity:** Low (mostly configuration; GSC submission is manual)

**Gotchas:**
- `app/sitemap.ts` must be placed in the `app/` root (not in a subdirectory) for
  Next.js to generate the `/sitemap.xml` route automatically.
- `lastModified: new Date()` generates the current date at build time, not at request
  time, because sitemap.ts is a static-generation route. This is correct behavior.
- Verify that `/recover` is deliberately excluded from the sitemap — it is a utility
  page for token recovery, not a discovery target.

---

- [ ] **Unit 9: Lighthouse + Core Web Vitals audit + fixes**

**Goal:** Run Lighthouse against `/`, `/quality`, and at least one `/convert/*` page
on the production deployment. Achieve Lighthouse SEO >= 95 and CWV targets. Document
cache-miss vs. cache-hit numbers separately — the acceptance criteria are based on
cache-miss numbers (worst-case cold load).

**Requirements satisfied:** R4, R5

**Dependencies:** Units 0–8 (all pages deployed to production)

**Files:** Potentially modify any page file if a CWV or SEO issue requires a fix.

**Lighthouse run procedure:**

Run from a clean Cloudflare cache miss (bypass cache with `Cache-Control: no-cache`
or use Lighthouse's "Network throttling: Fast 3G" mode from an incognito window):

```
Tested pages:
  https://leafbind.io/           (existing — verify no regression)
  https://leafbind.io/quality    (canary — most image-heavy)
  https://leafbind.io/convert/pdf-to-kfx  (representative landing page)
```

**Acceptance criteria:**

| Metric | Target | Notes |
|--------|--------|-------|
| SEO score | >= 95 | All three pages |
| LCP | < 2.5s | On cache miss, Fast 3G |
| INP | < 200ms | Interaction to Next Paint |
| CLS | < 0.1 | All pages |
| Performance | >= 80 | Not a hard gate but track it |

**Common fixes to anticipate:**

| Issue | Fix |
|-------|-----|
| Missing `alt` on images | Add descriptive `alt` text to all `<img>` tags in Unit 2–6 pages |
| CLS from images without explicit `width`/`height` | Add `width` and `height` attributes to all `<img>` tags |
| LCP from unoptimized hero images | Convert large PNGs to WebP; add `loading="eager"` and `fetchpriority="high"` to the LCP image |
| Missing `meta description` on any page | Verify metadata exports in each page file |
| Links not crawlable | Verify all internal `<a href>` links use `href`, not `onClick` navigation |
| Duplicate title tags | Verify no page inherits the root layout title without overriding it |

**Document results in the PR description** for Unit 9: paste the Lighthouse scores for
all three pages (cache miss and cache hit), note any fixes applied and which unit they
belong to. This is the evidence for R4 and R5 acceptance.

**Complexity:** Medium (diagnostic + targeted fixes; may require touching multiple files)

---

## Delivery Sequence

Each unit ships as a separate PR on a worktree branch. The sequence is ordered by
dependency: Unit 0 must merge before any other unit begins.

```
Unit 0 → Unit 1 → Unit 2 → Unit 3 → Unit 4 → Unit 5 → Unit 6 → Unit 7 → Unit 8 → Unit 9
                     ↑ canary: surface CWV/design issues before landing pages
```

Units 3–6 can be worked in parallel (each is a standalone page file) after Unit 2 merges
and no CWV/design issues were found in the canary.

## Open Questions for Implementation

The following `auto_pending_*` memory items from the EB-45 era are resolved or superseded
by Phase 3:

| auto_pending item | Resolution |
|---|---|
| `auto_pending_*_ac0f3ad0` — Select specific web stack | Resolved in Phase 1: Next.js App Router + FastAPI |
| `auto_pending_*_89636305` — Begin web service interface implementation | Resolved in Phase 1 |
| `auto_pending_*_5758d9bd` — Finalize Phase 1 technical plan | Resolved: Phase 1 plan shipped |
| `auto_pending_*_ca768d14` — Define free tier limits | Resolved in Phase 2: 20MB/3/day free, 100MB premium |
| `auto_pending_*_41dfc245` — Finalize pricing structure | Resolved in Phase 2: Starter/Standard/Power packs |
| `auto_pending_*_720e9117` — Develop the web service frontend and API | Phases 1+2 resolved; Phase 3 completes the SEO surface |

The following items are NOT resolved by Phase 3 and remain open:
- `auto_pending_*_56e87e65` — Implement restricted Stripe MCP server integration (EB-228 work)
- `auto_pending_*_2d39467c` — Verify webhook signature verification logic (EB-227 work)
- `auto_pending_*_388b1753` — Design job isolation mechanism for the VM (Phase 4)
- `auto_pending_*_c99c08f2` — Address EB-224 cover extraction error handling on Linux

## Sources & References

- **Brainstorm:** `docs/brainstorms/2026-05-14-eb230-phase3-seo-landing-pages-requirements.md`
- **Phase 1 reference plan:** `docs/plans/2026-05-13-001-feat-eb45-freemium-web-service-plan.md`
- **web-aesthetics skill:** INFRA-393 (available as a skill in this session)
- **SEO skill:** INFRA-371 (To Do — Phase 3 implementation may produce the initial INFRA-371 rubric)
- **Frontend codebase:** `web_service/frontend/` (Next.js 15.1.0, React 19, TypeScript 5)
- **Production URL:** https://leafbind.io
- **Jira ticket:** https://jlfowler1084.atlassian.net/browse/EB-230
