---
title: "feat: EB-233 leafbind.io design system + custom logo"
type: feat
status: active
date: 2026-05-14
origin: https://jlfowler1084.atlassian.net/browse/EB-233
deepened: 2026-05-14
---

# feat: EB-233 leafbind.io design system + custom logo

## Overview

EB-230 Phase 3 shipped functional SEO landing pages with stock Tailwind defaults and zero brand identity. EB-232 made the site live on Vercel. This plan delivers the *brand layer* leafbind.io needs to look like a trustworthy paid product, not a generic document-conversion site.

Two intertwined deliverables: (1) a custom logo + brand asset set, and (2) a deliberate design pass that swaps the navy/burnt-orange placeholder palette for a forest-green identity derived from the chosen logo, wires fonts that currently aren't loading at all, and unifies the homepage/upload flow with the polished marketing pages.

## Problem Frame

leafbind.io is currently two sites in a trench coat. The five EB-230 marketing pages (`/quality`, four `/convert/*` slugs) use Tailwind, a navy `bg-brand` nav, and a semantic-token system. The four pre-EB-230 functional pages (`/`, `/pricing`, `/recover`, `/status/[id]`) use inline styles, hardcoded `#0070f3` Vercel-blue buttons, and **no nav or footer at all** — a visitor who lands on the homepage cannot navigate anywhere unless they upload a file.

On top of that:

- The Tailwind pages are rendering in OS-default fonts because `next/font` is never imported despite `fontFamily.sans: Inter` and `fontFamily.serif: Lora` being declared in `tailwind.config.js`.
- `web_service/frontend/design-tokens.ts` exists but is imported by zero files — palette changes today require editing both `design-tokens.ts` and `tailwind.config.js`.
- `public/` has no favicon, no logo SVG, no Open Graph image. Browser tabs show the Next.js default purple triangle; social-share previews on the conversion pages use a screenshot of the quality-comparison page instead of a branded image.
- Document-conversion competitors (Smallpdf, iLovePDF, PDFCandy and the long tail of SEO-farm clones) are dominated by ad-laden dark patterns: fake download buttons, intrusive display ads, "Your file is ready!" upsell traps, urgency timers. Users associate the entire category with malware risk before they click. leafbind monetizes via Stripe one-time unlocks; the homepage must inspire enough trust that a visitor will upload a personal ebook and enter payment details.

The product exists. The brand does not. This plan ships the brand.

## Requirements Trace

EB-233 acceptance criteria, restated as numbered requirements:

- **R1.** Custom logo SVG + multi-size PNG renders committed to `web_service/frontend/` using Next.js file-convention paths (`app/icon.svg`, `app/apple-icon.png`).
- **R2.** Favicon generated from the logo (resolves the linked favicon ticket).
- **R3.** Design tokens file refreshed with brand-specific palette + typography derived from the logo, replacing the current navy/burnt-orange placeholders.
- **R4.** All 9 EB-230 pages reviewed and updated to use the new tokens.
- **R5.** Visual review against the `web-aesthetics` skill's "AI slop" checklist passes (no gradient meshes, no generic glassmorphism, no aggressive CTAs, restrained motion).
- **R6.** No Lighthouse regressions vs. the EB-230 Unit 9 baseline (`prompts/EB-230-unit9-lighthouse-cwv.md`). The audit should *improve*, not degrade.
- **R7.** Site does not look like a malware-risk document-conversion site (Smallpdf/iLovePDF aesthetic). Target reference points: Stripe, Linear, Vercel, Notion, Anthropic landing pages. (Captured as a project-level memory in `project_leafbind_design_constraint.md`.)

## Scope Boundaries

- Logo aesthetic is **locked**: forest-green leaf with paper-curl detail + serif wordmark (top-right candidate from the 4-up Gemini concept sheet). Plan does not re-litigate logo direction.
- Light mode only this ticket — dark mode adds a token-doubling cost (every CSS variable needs a `.dark { … }` override) that belongs in a separate ticket.
- No changes to functional behavior of upload, status polling, Stripe checkout, or token recovery. Visual-only refactor of those flows.
- No JSON-LD / structured-data changes — `JsonLd` component and `lib/structured-data.ts` are preserved as-is.
- No changes to `app/sitemap.ts` or `app/robots.ts` (EB-230 Unit 8 deliverable, recently shipped).
- No new copy or content beyond what brand voice requires for the new shared shell (header nav links, footer cross-links).
- No analytics or telemetry hookups (`useReportWebVitals` deferred).

### Deferred to Separate Tasks

- **Dark mode** — defer to a follow-up ticket once the light palette is settled.
- **`useReportWebVitals` analytics endpoint** — defer until there's a destination to ship metrics to.
- **Migration of `<img>` tags to `next/image` in non-logo contexts** — orthogonal performance refactor.
- **Stripe checkout success page + post-purchase email design** — separate ticket once the design system tokens exist for it to consume.

## Context & Research

### Relevant Code and Patterns

- `web_service/frontend/package.json` — Next.js 16.2.6, React 19, Tailwind 3.4.19, TypeScript 5.
- `web_service/frontend/tailwind.config.js` — currently CJS; `corePlugins.preflight: false`; six theme color tokens that need swapping; `fontFamily.sans/serif` declared but unloaded.
- `web_service/frontend/design-tokens.ts` — orphaned `as const` exports; this plan promotes it to the documented source of truth.
- `web_service/frontend/app/globals.css` — only `@tailwind components; @tailwind utilities;`. Missing `@tailwind base;`. No font imports, no CSS variables.
- `web_service/frontend/app/layout.tsx` — root layout; metadata has `openGraph.siteName`/`url` but no `images`, `icons`, or `metadataBase`. Body uses inline styles. Zero font imports.
- `web_service/frontend/app/page.tsx`, `pricing/page.tsx`, `recover/page.tsx`, `status/[id]/page.tsx` — the four "old world" inline-style pages with `#0070f3` buttons and no nav/footer.
- `web_service/frontend/app/quality/page.tsx`, `convert/*/page.tsx` — the five Tailwind-using marketing pages, already on semantic tokens but rendering in fallback fonts.
- `web_service/frontend/components/UploadZone.tsx` — 108-line drag-drop zone, the most visually heavy component, hardcoded `#0070f3`/`#ccc`/`#fafafa`/`#f0f7ff`. This is the homepage's primary content area.
- `web_service/frontend/components/BuyButtons.tsx`, `ConversionStatus.tsx`, `FormatSelector.tsx`, `TokenField.tsx`, `TokenList.tsx`, `RecoverClient.tsx` — all contain hardcoded `#0070f3` for primary actions.
- `web_service/frontend/components/JsonLd.tsx`, `lib/structured-data.ts` — preserve untouched.
- `docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md` — predecessor plan; explicitly defers the refactor of `/`, `/pricing`, `/recover`, `/status/[id]` (this plan delivers that refactor).
- `prompts/EB-230-unit9-lighthouse-cwv.md` — Lighthouse / CWV baseline this plan must not regress.

### Institutional Learnings

- `docs/solutions/best-practices/pre-implementation-render-check-2026-04-22.md` — render every page in current state before changing a shared layer. Translated to EB-233: take a Playwright snapshot of every leafbind.io route as Unit 1, then diff against post-change snapshots in Unit 8.
- **No prior design / logo / tokens / Lighthouse / Vercel-deployment compounding entries exist.** Per global CLAUDE.md INFRA-183, EB-233 will create the institutional knowledge it needs. Budget a `ce:compound` pass at end-of-ticket (Phase 5.4 option).

### External References

- [Next.js 16 upgrade guide](https://nextjs.org/docs/app/guides/upgrading/version-16) — `params`/`id` are Promises in `opengraph-image.tsx` / `icon.tsx`; Turbopack is default builder; `images.domains` deprecated.
- [Next.js 16 release notes](https://nextjs.org/blog/next-16) — `ImageResponse` is 2-20× faster; per-slug OG generation is now cheap.
- [Next.js `next/font` API](https://github.com/vercel/next.js/blob/v16.2.2/docs/01-app/03-api-reference/02-components/font.mdx) — CSS variable pattern (`variable: '--font-inter'`) maps to Tailwind via `fontFamily.sans: ['var(--font-inter)', ...]`.
- [Next.js icon file conventions](https://github.com/vercel/next.js/blob/v16.2.2/docs/01-app/03-api-reference/03-file-conventions/01-metadata/app-icons.mdx) — `app/favicon.ico`, `app/icon.svg`, `app/apple-icon.png` auto-inject `<link>` tags. Do **not** also declare `metadata.icons` (produces duplicate tags).
- [Tailwind v3 dark mode](https://v3.tailwindcss.com/docs/dark-mode) — use `darkMode: 'selector'` (the v3.4.1+ name; `'class'` is the deprecated alias).
- [Tailwind v3 customizing colors with CSS variables](https://v3.tailwindcss.com/docs/customizing-colors) — declare `var(--color-...)` in Tailwind theme so inline-style components consume the same vars without refactor.

## Key Technical Decisions

- **Single source of truth for tokens: `design-tokens.ts`.** `tailwind.config.js` becomes `tailwind.config.ts` and imports named exports from `design-tokens.ts`. CSS variables in `globals.css :root { … }` mirror the same values by hand (size of token surface — six colors + seven type scales + eight spacing values — does not justify a build-time generator script). **Drift guard required:** a lightweight test or pre-commit grep asserts that `design-tokens.ts` and `globals.css :root` define the same key set with the same hex values. Without this, "single source of truth" is aspirational — a future contributor edits `design-tokens.ts`, Tailwind utilities update, but inline-style components reading `var(--color-*)` silently render in stale colors.
- **Inline-style components consume tokens via CSS variables, not refactor.** `<div style={{ background: 'var(--color-surface)' }} />` is acceptable; refactoring every inline-style line to Tailwind utilities is out of scope. The plan ships the *new palette* through the existing inline-style surface and the existing Tailwind surface in one move.
- **File-convention icons for the standard set; explicit declarations only where conventions don't cover.** Rely on file-convention auto-injection for `app/icon.svg`, `app/apple-icon.png`, `app/favicon.ico`, `app/opengraph-image.png`. Do **not** duplicate those entries in `metadata.icons` (Next 16 docs: declaring both produces duplicate `<link>` tags). However, `theme-color` meta (warranted by the brand-cream / forest-green identity) and Safari `mask-icon` for pinned tabs are **not** generated by file conventions — those remain candidates for explicit declaration via `metadata.themeColor` and `metadata.icons.other`. Dark-mode `<media>` icon switching is deferred with dark mode.
- **Logo: inline SVG React component, not `next/image` or sprite.** `<Logo />` renders an inline SVG with `currentColor` strokes/fills. Rejected alternatives: (a) `next/image` would force a separate network request per page and lose `currentColor` inheritance; (b) a separate SVG sprite requires sprite-loading tooling that doesn't exist in this codebase. The tradeoff accepted: ~1-2 KB added to each page's HTML payload in exchange for zero network requests, crispness at every DPR, theme-color recolorability, and direct accessibility via `<title>` / `aria-label`.
- **Font pair: starting candidate is Inter (sans) + Lora (serif), open to substitution during `frontend-design` discovery.** Both via `next/font/google` with `display: 'swap'`, `adjustFontFallback: true` (default), `variable: '--font-inter'` / `'--font-lora'`. Tailwind `fontFamily.sans/serif` maps to those variables. If `frontend-design` discovery surfaces a stronger pair (e.g. DM Serif Display, Fraunces, Source Serif 4) for the chosen logo aesthetic, the substitution is a one-line change in `app/layout.tsx`.
- **Preflight on; sweep before flip.** `corePlugins.preflight: true`, add `@tailwind base;` to `globals.css`. Sweep `<h1>`-`<h6>`, `<ul>`/`<ol>`, and `<img>` usages across all 9 pages in a dedicated unit *before* enabling preflight, so the flip is a no-visual-regression event for the already-Tailwind pages and a coordinated stylistic upgrade for the inline-style pages.
- **Per-slug dynamic OG images for `/convert/*`, static for everything else.** `ImageResponse` perf in Next 16 makes per-slug OG cheap enough to be the right choice. Static `app/opengraph-image.png` for home, `/pricing`, `/quality`, `/recover`. Dynamic `app/convert/[slug]/opengraph-image.tsx` for the four conversion pages. Mirror with `twitter-image.{png,tsx}`.
- **`metadataBase` set in `app/layout.tsx`.** Eliminates the build-time warning about relative OG URLs resolving to `localhost:3000`.
- **Codemod first.** Run `npx @next/codemod@canary upgrade latest` once in Unit 1 to catch any lingering Next 15 patterns the EB-230 upgrade may have missed (sync `params`, deprecated `middleware`, `unstable_` prefixes).
- **Worktree-first.** All work lands on a `feat/EB-233-leafbind-design-system` worktree per project policy. No direct commits to master.
- **Defer dark mode.** `darkMode: 'media'` (zero-JS OS preference) is a one-line follow-up if wanted later; full theme picker is its own ticket.

## Open Questions

### Resolved During Planning

- **Logo direction:** Forest-green leaf with paper-curl detail + serif wordmark (top-right of 4-up Gemini concept sheet). Locked by user before planning.
- **Scope:** All 9 EB-230 pages, differentiated treatment: marketing pages (`/`, `/pricing`, `/quality`, 4× `/convert/*`) get full design pass; functional pages (`/status/[id]`, `/recover`) get the shared shell + token palette but no marketing hero/CTA flourish ("lighter touch" per EB-233 description).
- **Tokens single source:** `design-tokens.ts` is promoted to source of truth. `tailwind.config.js` converts to `tailwind.config.ts` and imports from it. CSS variables in `globals.css` mirror by hand.
- **Inline-style components:** Stay inline; receive tokens via CSS variables. Not refactored to Tailwind in this ticket.
- **Dark mode:** Deferred. Light only.
- **Font self-hosting:** Use `next/font/google` (self-hosts via Vercel/Next build; no runtime call to fonts.googleapis.com).
- **Icon strategy:** File-convention (`app/icon.svg`, etc.). Do not declare `metadata.icons`.
- **OG strategy:** Static `app/opengraph-image.png` for home + 3 secondary pages; dynamic `ImageResponse` for the 4 `/convert/*` slugs.
- **Logo source:** Hand-build SVG using the chosen Gemini PNG as design reference (per EB-233 description: "may use gemini-imagegen for first pass, then hand-iterate in SVG").

### Deferred to Implementation

- **Exact color hex values** — to be derived from the final SVG logo's actual greens during `frontend-design` skill discovery. Plan commits to *forest green primary, warm cream surface, off-black ink, paper-curl accent* without locking RGB values; discovery refines.
- **Final font pair** — Lora + Inter is the starting candidate; `frontend-design` discovery may substitute (DM Serif Display, Fraunces, Source Serif 4, EB Garamond, Playfair Display) based on how the final SVG logo's wordmark weight reads.
- **Logo size/proportion in nav** — pixel-exact placement, target heights (32px? 40px? 48px?), and brand-mark-only vs full-wordmark variants in the header — discovery decision.
- **Whether the homepage `UploadZone` becomes the hero or sits below an editorial value-prop band** — `frontend-design` discovery proposal.
- **Whether to enable `html { scroll-behavior: smooth }`** — if added, also add `data-scroll-behavior="smooth"` to `<html>` to keep Next 16's pre-v16 SPA-navigation behavior. Discovery decision.

## Output Structure

New files this plan creates (paths repo-relative):

    web_service/frontend/
    ├── app/
    │   ├── favicon.ico                    [new]   leaf glyph, 32×32, multi-resolution .ico
    │   ├── icon.svg                       [new]   master logo glyph; auto-injected by Next
    │   ├── apple-icon.png                 [new]   180×180 PNG for iOS home-screen
    │   ├── opengraph-image.png            [new]   1200×630 branded OG for home/pricing/quality/recover
    │   ├── twitter-image.png              [new]   1200×600 Twitter card mirror
    │   ├── (marketing)/                   [new]   route group — wide-content marketing layout
    │   │   └── layout.tsx                 [new]   Header + max-w-7xl <main> + Footer
    │   ├── (app)/                         [new]   route group — narrow-content functional layout
    │   │   └── layout.tsx                 [new]   Header + max-w-3xl <main> + Footer
    │   └── convert/
    │       └── [slug]/
    │           ├── opengraph-image.tsx    [new]   ImageResponse: logo + slug-derived title
    │           └── twitter-image.tsx      [new]   ImageResponse mirror
    ├── components/
    │   ├── Logo.tsx                       [new]   inline SVG React component
    │   ├── Header.tsx                     [new]   shared nav, used by both route-group layouts
    │   └── Footer.tsx                     [new]   shared footer with cross-links + brand mark
    ├── tools/
    │   └── check-token-drift.mjs          [new]   drift guard — asserts design-tokens.ts ↔ globals.css :root parity
    ├── public/
    │   └── fonts/                         [new]   self-hosted .ttf/.otf buffers for ImageResponse
    │       ├── Lora-Bold.ttf
    │       └── Inter-Medium.ttf
    └── tailwind.config.ts                 [new, replaces tailwind.config.js]

Page moves (no functional change beyond restyle landing in Units 7b/7c):

    app/page.tsx                  → app/(marketing)/page.tsx
    app/pricing/page.tsx          → app/(marketing)/pricing/page.tsx
    app/quality/page.tsx          → app/(marketing)/quality/page.tsx
    app/convert/*/page.tsx        → app/(marketing)/convert/*/page.tsx     [4 files]
    app/status/[id]/page.tsx      → app/(app)/status/[id]/page.tsx
    app/recover/page.tsx          → app/(app)/recover/page.tsx

Files modified in place (no relocation):

    web_service/frontend/
    ├── design-tokens.ts                   [modified]  forest-green palette; documented source of truth
    ├── package.json                       [modified]  add check:tokens script + prebuild chain
    ├── app/
    │   ├── layout.tsx                     [modified]  next/font imports, metadataBase (no shell)
    │   └── globals.css                    [modified]  @tailwind base; CSS variables in :root
    └── components/
        ├── UploadZone.tsx                 [modified]  hex → var(--color-*) substitution     [Unit 7a]
        ├── BuyButtons.tsx                 [modified]  hex → var(--color-*)                  [Unit 7a]
        ├── FormatSelector.tsx             [modified]  hex → var(--color-*)                  [Unit 7a]
        ├── ConversionStatus.tsx           [modified]  hex → var(--color-*)                  [Unit 7a]
        ├── TokenField.tsx                 [modified]  hex → var(--color-*)                  [Unit 7a]
        ├── TokenList.tsx                  [modified]  hex → var(--color-*)                  [Unit 7a]
        └── RecoverClient.tsx              [modified]  hex → var(--color-*)                  [Unit 7a]

Untouched (preserve as-is):

    web_service/frontend/components/JsonLd.tsx, lib/structured-data.ts, lib/api.ts,
    app/sitemap.ts, app/robots.ts, app/UploadForm.tsx, next.config.js, vercel.json,
    tsconfig.json, postcss.config.js

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

### Token flow

```
design-tokens.ts (TypeScript source of truth)
    │
    ├──► tailwind.config.ts  (imports named exports, populates theme.extend)
    │           │
    │           └──► Tailwind utility classes  (bg-brand, text-accent, font-serif)
    │                       │
    │                       └──► consumed by:  /quality, 4× /convert/*, new shell components
    │
    └──► globals.css :root { --color-* }  (mirrored by hand; design-tokens.ts is canonical)
                │
                └──► CSS variable references  (var(--color-accent))
                            │
                            └──► consumed by:  inline-style pages and components
```

### Font flow

```
next/font/google (Inter, Lora)  → CSS variables (--font-inter, --font-lora) at <html>
    │
    └──► tailwind.config.ts:  fontFamily.sans  = ['var(--font-inter)', ...]
                              fontFamily.serif = ['var(--font-lora)',  ...]
            │
            └──► Tailwind utilities font-sans / font-serif resolve to brand fonts everywhere
```

### Implementation sequence (dependency graph)

```
Unit 1 (Pre-flight: codemod + baseline + Lighthouse)
    │
    ├──► Unit 2 (Brand assets: logo SVG + icons + OG + metadataBase)
    │       │
    │       └──► Unit 3 (Token system + drift guard: design-tokens.ts + CSS vars + tailwind.config.ts + check-token-drift.mjs)
    │               │
    │               ├──► Unit 4 (Typography: next/font wiring)
    │               │       │
    │               │       └──► Unit 5 (Preflight enable + base sweep)
    │               │               │
    │               │               └──► Unit 6 (Shared shell + route-group layouts)
    │               │                       │
    │               │                       ├──► Unit 7a (Component palette swap — mechanical)  ◄── may run in parallel with Unit 6
    │               │                       │       │
    │               │                       │       ├──► Unit 7b (Functional page refactor — needs route-group + 7a)
    │               │                       │       │       │
    │               │                       │       │       └──► Unit 8 (verify)
    │               │                       │       │
    │               │                       │       └──► Unit 7c (Marketing page redesign — needs route-group + 7a + fonts)
    │               │                       │               │
    │               │                       │               └──► Unit 8 (verify)
    │               │
    │               └──► [Unit 7a can start after Unit 3 alone; 7b/7c need Unit 6 too]
    │
    └──► [Units 2 and 3 may run in parallel after Unit 1, but logo discovery informs palette derivation]
```

**Parallelism opportunities:**
- After Unit 1: Units 2 and 3 in parallel (with awareness that final palette in Unit 3 needs the logo from Unit 2).
- After Unit 3: Unit 7a (component palette swap) can run in parallel with Units 4 → 5 → 6.
- After Unit 6: Units 7b and 7c run in parallel (different file sets, both depend on route-group layouts and Unit 7a).

## Implementation Units

- [ ] **Unit 1: Pre-flight & baseline capture**

**Goal:** Establish the regression baseline before any visual change, and clear any Next 16 upgrade debt.

**Requirements:** R6.

**Dependencies:** None — this is the first unit.

**Files:**
- Create: `web_service/frontend/.baselines/eb233-pre/` (gitignored directory for snapshot PNGs)
- Modify: nothing yet
- Test: `web_service/frontend/.baselines/eb233-pre/lighthouse-baseline.json` (captured Lighthouse report)

**Approach:**
- Create the `feat/EB-233-leafbind-design-system` worktree per project policy.
- Run `npx @next/codemod@canary upgrade latest` against `web_service/frontend/`. Commit any changes as a discrete codemod commit *before* design work begins; if the codemod surfaces meaningful Next 15 → 16 drift, treat that as scope-extending and report.
- Use Playwright MCP to snapshot all 9 routes at desktop (1440×900) and mobile (375×667) widths against the live production site (or a fresh `next build && next start` if local-only). Save PNGs to `.baselines/eb233-pre/`.
- Capture Lighthouse mobile audit for `/`, `/convert/pdf-to-kfx`, and `/pricing`. Save the JSON to `.baselines/eb233-pre/lighthouse-baseline.json` — this is the regression contract for Unit 8.

**Patterns to follow:**
- Pre-implementation render check discipline from `docs/solutions/best-practices/pre-implementation-render-check-2026-04-22.md`.
- Worktree creation: `~/.claude/skills/worktree-management/SKILL.md`.

**Test scenarios:**
- *Happy path:* All 9 routes snapshot successfully at both widths; Lighthouse audits complete for the three target pages; baseline JSON includes LCP, CLS, INP, TBT, performance/accessibility/SEO/best-practices scores.

**Verification:**
- `.baselines/eb233-pre/` contains 18 PNGs (9 routes × 2 widths) plus `lighthouse-baseline.json`.
- Worktree branch `feat/EB-233-leafbind-design-system` exists; `tools/verify-manifest.ps1` reports no manifest drift introduced by the codemod.

---

- [ ] **Unit 2: Brand assets — logo SVG, favicons, OG images**

**Goal:** Produce the full asset set and wire it via Next 16 file conventions.

**Requirements:** R1, R2.

**Dependencies:** Unit 1.

**Files:**
- Create: `web_service/frontend/components/Logo.tsx` (inline SVG React component)
- Create: `web_service/frontend/app/icon.svg` (master glyph)
- Create: `web_service/frontend/app/favicon.ico` (multi-resolution `.ico`)
- Create: `web_service/frontend/app/apple-icon.png` (180×180)
- Create: `web_service/frontend/app/opengraph-image.png` (1200×630, branded)
- Create: `web_service/frontend/app/twitter-image.png` (1200×600, mirrored)
- Create: `web_service/frontend/app/convert/[slug]/opengraph-image.tsx` (`ImageResponse` per slug)
- Create: `web_service/frontend/app/convert/[slug]/twitter-image.tsx` (mirror)
- Create: `web_service/frontend/public/fonts/Lora-Bold.ttf`, `Inter-Medium.ttf` (for `ImageResponse` to load via `readFile`)
- Modify: `web_service/frontend/app/layout.tsx` (add `metadataBase: new URL('https://leafbind.io')`; remove `metadata.icons` if present)

**Approach:**
- Hand-build the SVG logo using the chosen Gemini PNG (top-right of the 4-up sheet) as a design reference. Vector-trace the leaf silhouette and paper-curl detail; rebuild the wordmark in the chosen serif. Optimize via SVGO. Use `currentColor` for the fill so the logo inherits text color in headers, footers, and dark contexts.
- `Logo.tsx` renders inline SVG with `aria-label="leafbind"`, `role="img"`, optional `<title>`. Accept a `className` prop for sizing.
- `app/icon.svg` is the master glyph (leaf only, no wordmark — favicon is too small for wordmark legibility). `app/apple-icon.png` is the same glyph centered on a brand-cream background, rasterized at 180×180.
- `app/favicon.ico` is multi-resolution (16×16, 32×32, 48×48) of the glyph.
- Static OG image (`app/opengraph-image.png`): logo + tagline + brand-cream background, 1200×630. Use an external tool (Figma export, or `ImageResponse` invoked once as a build-time step) — the source asset is fine to live in `public/fonts/` font buffers + a brief generator script, or just commit the static PNG.
- Dynamic per-slug OG (`app/convert/[slug]/opengraph-image.tsx`): use `ImageResponse` with `await params`, load Lora-Bold from `public/fonts/` via `readFile`, render `{slug.replace(/-/g, ' ')}` capitalized as the headline. Twitter mirror at 1200×600.
- `metadataBase` set to `new URL('https://leafbind.io')` in `app/layout.tsx`. Sanity-check that `metadata.icons` is **not** set (Next 16 file convention auto-injects).

**Patterns to follow:**
- Next.js `ImageResponse` doc: every JSX node needs `display: 'flex'` or `'block'`; fonts loaded via `readFile` + `fonts: [...]` option.
- File-convention icons: do not also declare `metadata.icons` (produces duplicate `<link>` tags).
- Logo as inline React component: `currentColor` for recolorability; `aria-label` for screen readers.

**Test scenarios:**
- *Happy path:* `<Logo />` renders inline SVG with a `<title>` accessible; `app/icon.svg` is auto-served at `/icon.svg`; favicon tab icon is the leaf glyph (not Next.js purple triangle); `/convert/pdf-to-kfx/opengraph-image` returns a 1200×630 PNG with the slug rendered as a capitalized title; build succeeds with no `metadataBase` warning.
- *Edge case:* `<Logo />` accepts `className="h-8 w-auto text-brand"` and renders at 32px tall with brand color applied.
- *Integration:* Opening the site in Twitter card validator (or the Vercel preview share) shows the new OG image, not the old quality-page screenshot.

**Verification:**
- Browser tab shows the leaf favicon, not the Next.js default.
- `next build` completes with no `metadataBase` warning.
- `/opengraph-image` returns the static branded PNG; `/convert/pdf-to-kfx/opengraph-image` returns the dynamic per-slug PNG.
- `<Logo />` renders correctly in isolation when placed in any page.

---

- [ ] **Unit 3: Token system — design-tokens.ts + CSS variables + tailwind.config.ts**

**Goal:** Wire `design-tokens.ts` as the single source of truth; replace the navy/burnt-orange palette with the forest-green identity derived from the logo; expose all tokens as CSS variables so inline-style components can consume them.

**Requirements:** R3.

**Dependencies:** Unit 2 (logo SVG informs the forest-green hex values).

**Files:**
- Modify: `web_service/frontend/design-tokens.ts` (replace placeholder palette with forest-green identity; add header comment marking it as source of truth)
- Create: `web_service/frontend/tailwind.config.ts` (TypeScript replacement)
- Delete: `web_service/frontend/tailwind.config.js` (replaced)
- Modify: `web_service/frontend/app/globals.css` (add `:root { --color-* }` block mirroring tokens)
- Create: `web_service/frontend/tools/check-token-drift.mjs` (token drift guard — verifies `design-tokens.ts` `colors` exports and `globals.css :root` `--color-*` declarations define the same key set with matching hex values)
- Modify: `web_service/frontend/package.json` (add `"check:tokens": "node tools/check-token-drift.mjs"` script; chain into `prebuild` so CI fails on drift)

**Approach:**
- Refresh `design-tokens.ts` with forest-green palette: primary forest green, warm cream surface, off-black ink, paper-curl accent, soft border, muted text. Exact hex values derived during `frontend-design` skill discovery from the final SVG logo's actual greens. Add a header comment: `// Source of truth for visual tokens. globals.css :root mirrors these values; tailwind.config.ts imports them. Run pnpm check:tokens (or npm/yarn equivalent) before committing changes here.`
- Convert `tailwind.config.js` → `tailwind.config.ts`. Import named exports (`colors`, `type`, `space`, `shadows`, `radii`) from `./design-tokens`. Populate `theme.extend` from the imports.
- In `theme.extend.colors`, map each token to `var(--color-...)` (not the hex directly), so Tailwind utilities and inline-style components resolve through the same CSS variable.
- In `globals.css`, add a `@layer base { :root { --color-brand: #...; --color-accent: #...; ... } }` block mirroring `design-tokens.ts`.
- **Drift guard implementation (`tools/check-token-drift.mjs`):** a small Node script that (1) imports the `colors` export from `design-tokens.ts` (via `tsx`/`ts-node` or by reading the source and extracting the literal via regex — the latter avoids a runtime dependency), (2) parses the `:root { --color-* }` block out of `globals.css` with a regex, (3) asserts the two key sets are identical and the hex values match. Exit code 1 with a diff report on mismatch. Wire into `package.json` as a `check:tokens` npm script; chain into `prebuild` so `next build` fails before deployment if drift exists. Optionally add a pre-commit hook in a follow-up; CI gate via `prebuild` is sufficient for v1.
- Leave `corePlugins.preflight: false` for now — Unit 5 enables it.
- Keep `darkMode: 'selector'` ready (Tailwind 3.4.1+ name) but no dark token block this ticket.

**Patterns to follow:**
- Tailwind CSS-variable color pattern: `colors: { brand: 'var(--color-brand)', ... }` (not the hex literal).
- Token import style: named imports from `./design-tokens`, matching the existing `as const` export shape.
- Drift-guard tone: failure message points the developer at the conflicting file pair and the specific missing/divergent key, not a generic "drift detected" error.

**Test scenarios:**
- *Happy path:* `tailwind.config.ts` builds cleanly under `next build`; `bg-brand` resolves to the new forest-green; inline `style={{ color: 'var(--color-accent)' }}` renders in the same green elsewhere on the page; `npm run check:tokens` exits 0.
- *Edge case:* Tailwind utility cache is invalidated correctly when `design-tokens.ts` changes (smoke via `next build` after a one-color tweak).
- *Drift case:* Edit `design-tokens.ts` to change one hex without updating `globals.css` → `npm run check:tokens` exits 1 with a diff showing the divergent key and both values; `npm run build` fails at the `prebuild` step.

**Verification:**
- `tailwind.config.js` no longer exists; `tailwind.config.ts` is the only Tailwind config.
- `design-tokens.ts` header comment names it as source of truth and references the drift-guard script.
- `bg-brand`, `text-accent`, `bg-surface` all render in the new palette in `next dev`.
- An inline `style={{ background: 'var(--color-surface)' }}` element renders in the same warm cream as a `bg-surface` Tailwind class.
- `npm run check:tokens` exits 0 on the as-committed state.
- Drift-injection smoke test (intentionally diverge one color, confirm CI fails, revert) is captured in the Unit 8 compound entry.

---

- [ ] **Unit 4: Typography — `next/font` wiring**

**Goal:** Load Inter + Lora (or `frontend-design`-substituted equivalents) and wire them through CSS variables so existing `font-sans` / `font-serif` Tailwind utilities resolve to brand fonts everywhere.

**Requirements:** R4 (typography is part of the token system); enables R7 (Stripe/Linear-calm aesthetic requires real fonts).

**Dependencies:** Unit 3 (CSS variable plumbing must exist).

**Files:**
- Modify: `web_service/frontend/app/layout.tsx` (add `next/font/google` imports for Inter + Lora; apply `${inter.variable} ${lora.variable}` to `<html>` className)
- Modify: `web_service/frontend/tailwind.config.ts` (update `fontFamily.sans` / `fontFamily.serif` to read from `var(--font-inter)` / `var(--font-lora)`)
- Modify: `web_service/frontend/design-tokens.ts` (update `type.fontSans` / `type.fontSerif` to reference CSS variables, keeping single-source semantics)

**Approach:**
- In `app/layout.tsx`, add:
  ```ts
  import { Inter, Lora } from 'next/font/google'
  const inter = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-inter' })
  const lora  = Lora({  subsets: ['latin'], display: 'swap', variable: '--font-lora' })
  ```
- Apply both variables to `<html className={`${inter.variable} ${lora.variable}`}>`.
- In `tailwind.config.ts`, set `fontFamily.sans = ['var(--font-inter)', 'ui-sans-serif', 'system-ui', 'sans-serif']` and `fontFamily.serif = ['var(--font-lora)', 'ui-serif', 'Georgia', 'serif']`.
- Leave `adjustFontFallback: true` at default (eliminates CLS on font swap).
- Do NOT add `<link rel="preload">` manually for fonts — `next/font` handles it.
- Do NOT add `priority` to fonts (that's a `next/image` prop).
- If `frontend-design` skill discovery proposes a different serif (DM Serif Display, Fraunces, Source Serif 4, EB Garamond, Playfair Display) based on the logo aesthetic, substitute the import — the wiring above is unchanged.

**Patterns to follow:**
- `next/font` + Tailwind CSS variable pattern from the Next.js 16 docs.
- `display: 'swap'` (not `'optional'`) — paired with `adjustFontFallback` for clean Lighthouse CLS.

**Test scenarios:**
- *Happy path:* Inspecting `<html>` in DevTools shows both `--font-inter` and `--font-lora` defined; `font-sans` Tailwind utility renders Inter; `font-serif` renders Lora; hero `<h1>` on `/quality` switches from system fallback to Lora.
- *Edge case:* No double font load (only `next/font`-served files in network panel; no calls to `fonts.googleapis.com`).
- *Integration:* `useReportWebVitals` (or Lighthouse) reports CLS contribution from font swap at zero or near-zero.

**Verification:**
- DevTools Network shows two `.woff2` files served from the Next.js static asset path; zero requests to `fonts.googleapis.com` or `fonts.gstatic.com`.
- All Tailwind pages render in Inter (body) and Lora (headings), not OS fallback.
- Lighthouse CLS score does not regress vs. baseline.

---

- [ ] **Unit 5: Preflight enable + base sweep**

**Goal:** Turn on Tailwind's CSS reset and sweep the existing pages for browser-default styling that the reset will strip (heading sizes, list bullets, inline image behavior).

**Requirements:** R4.

**Dependencies:** Unit 4 (fonts must be loaded before preflight, so the sweep validates against the right type sizes).

**Files:**
- Modify: `web_service/frontend/tailwind.config.ts` (`corePlugins.preflight: true`)
- Modify: `web_service/frontend/app/globals.css` (add `@tailwind base;` at the top)
- Modify: every `.tsx` page that uses bare `<h1>`-`<h6>`, `<ul>`, `<ol>`, or `<img>` without explicit Tailwind size/list/display utilities

**Approach:**
- **Sweep first, flip second.** Before adding `@tailwind base;`, audit all 9 pages and all 8 components for:
  - Bare `<h1>` / `<h2>` / `<h3>` without `text-*` size utilities → add explicit `text-5xl font-semibold` (or similar). The five EB-230 Tailwind pages already do this; the four inline-style pages handle it via inline `style` and are unaffected.
  - Bare `<ul>` / `<ol>` that visually rely on browser-default bullets/numbers → add `list-disc list-inside` (or equivalent) explicitly. Audit shows zero existing pages use semantic lists — likely no-op.
  - Bare `<img>` without `inline` utility → audit shows raw `<img>` is only used in `/quality` for the comparison gallery (already on explicit width/height). Preflight will make `<img>` `display: block` which matches current intent.
- After sweep lands, add `@tailwind base;` to top of `globals.css` and flip `corePlugins.preflight: true` in `tailwind.config.ts`.
- Run `next dev` and visually scan every page for unexpected layout shifts. Compare against Unit 1 baseline snapshots.

**Patterns to follow:**
- Tailwind preflight docs: don't try to scope preflight to a subtree; flip it on globally.
- Avoid `prose` (typography plugin) for now — out of scope; would add a dependency this plan does not currently include.

**Test scenarios:**
- *Happy path:* All 9 pages render with no visual regression on the 5 already-Tailwind pages after preflight flip.
- *Edge case:* `/quality` comparison `<img>` tags still render at the expected layout (preflight's `display: block` is the intended behavior).
- *Integration:* Inline-style pages (`/`, `/pricing`, `/recover`, `/status/[id]`) still render — inline styles win specificity vs. preflight; the only visible changes are on bare element tags (`<h1>`, `<ul>`) which the sweep handled.

**Verification:**
- Diff Unit 1 baseline snapshots vs. current state for the 5 Tailwind pages: zero meaningful visual regression on marketing pages.
- Inline-style pages remain visually identical to baseline (preflight cannot override inline styles).

---

- [ ] **Unit 6: Shared shell — Header, Footer, route-group layouts**

**Goal:** Extract the duplicated nav from the 5 Tailwind pages into a single `<Header />`; create a `<Footer />` with brand mark + cross-links; introduce **route-group layouts** (`app/(marketing)/layout.tsx`, `app/(app)/layout.tsx`) that nest under the root layout so marketing vs. functional treatment is enforced by the router rather than a runtime prop.

**Requirements:** R4, R7.

**Dependencies:** Unit 5 (preflight + base sweep complete so shell rendering is stable).

**Files:**
- Create: `web_service/frontend/components/Header.tsx` (shared nav with `<Logo />` + page links)
- Create: `web_service/frontend/components/Footer.tsx` (cross-links + brand mark + copyright)
- Create: `web_service/frontend/app/(marketing)/layout.tsx` (wide-content marketing layout — `Header` + `<main className="max-w-7xl mx-auto">` + `Footer`)
- Create: `web_service/frontend/app/(app)/layout.tsx` (narrow-content functional layout — same `Header` + `<main className="max-w-3xl mx-auto">` + same `Footer`)
- Modify: `web_service/frontend/app/layout.tsx` (root layout stays minimal — `<html>`/`<body>` only; nested route-group layouts own the shell)
- Page moves (Units 7b and 7c land these): 5 already-Tailwind pages and 4 inline-style pages relocate under `app/(marketing)/` or `app/(app)/` per their treatment.

**Approach:**
- `<Header />`:
  - Left: `<Logo className="h-8 w-auto text-text-base" />` + wordmark.
  - Center/right: nav links to `/`, `/convert/pdf-to-kfx`, `/pricing`, `/quality`.
  - On `bg-surface` with subtle `border-b border-border`.
  - Mobile: collapse to a single hamburger or hide auxiliary links (lightest-touch responsive — full mobile nav is out of scope, but the header must not break on narrow screens).
- `<Footer />`:
  - Cross-links to all 4 `/convert/*` slugs (SEO juice), `/pricing`, `/quality`, `/recover`.
  - Small `<Logo />` + tagline.
  - Copyright + "Made with care, not ads" (or similar trust-building micro-copy — exact copy is a discovery-time decision).
- **Route groups instead of a `variant` prop:** Next.js route groups (parentheses in folder names) nest a layout without affecting URLs. `app/(marketing)/layout.tsx` wraps marketing pages with wide content; `app/(app)/layout.tsx` wraps functional pages with narrow content. Both layouts reuse the same `<Header />` and `<Footer />` components — only the `<main>` width and any treatment-specific framing differ.
- **Why not a `variant` prop on a shared `AppShell` component:** the prop form requires every page author to remember to pass the right value. A new functional page added later silently inherits the wrong treatment if the prop is omitted. Route groups make the treatment a structural property of *where the page file lives*, enforced by the router. Adding a new functional page just means dropping it into `app/(app)/`. (Rejected alternative.)
- Root `app/layout.tsx` becomes minimal — `<html>` with the font CSS variables applied to className, `<body>` with no shell wrapping. The shell now lives in the nested route-group layouts.

**Patterns to follow:**
- Server components by default; only mark `'use client'` if a hover/animation state warrants it (the header probably does not).
- Next.js route groups for layout differentiation: [Route Groups docs](https://nextjs.org/docs/app/api-reference/file-conventions/route-groups).
- Reuse `<Header />` and `<Footer />` from both route-group layouts — they are leaf components; only the `<main>` wrapper differs.

**Test scenarios:**
- *Happy path:* Every page renders the same header (with logo) and footer (with cross-links); upload flow on `/` now has a nav and footer for the first time.
- *Edge case:* Adding a page to `app/(app)/` automatically inherits the narrow-content treatment without any per-page prop.
- *Integration:* Clicking the logo in the header on `/recover` navigates to `/`; clicking a `/convert/*` link in the footer on `/status/[id]` works.

**Verification:**
- Both route-group layout files exist; root layout no longer contains a shell.
- A test page added to `app/(app)/` renders inside the narrow shell without any prop-passing.
- Mobile (375px wide) renders the header without horizontal scroll.
- Page moves themselves land in Units 7b and 7c — this unit only stands up the layouts and shell components.

---

- [ ] **Unit 7a: Component palette swap (mechanical)**

**Goal:** Swap hardcoded hex literals (`#0070f3`, `#ccc`, `#fafafa`, `#f0f7ff`) for `var(--color-*)` references across the 7 inline-styled components. Mechanical, low risk, fully delegable to an implementer subagent with grep verification.

**Requirements:** R4.

**Dependencies:** Unit 3 (CSS vars must exist) — does **not** depend on Unit 6 (shell). Can run in parallel with Unit 6 once Unit 3 lands.

**Files:**
- Modify: `web_service/frontend/components/UploadZone.tsx`, `BuyButtons.tsx`, `FormatSelector.tsx`, `ConversionStatus.tsx`, `TokenField.tsx`, `TokenList.tsx`, `RecoverClient.tsx`

**Approach:**
- Strict 1:1 substitution table:
  - `#0070f3` → `var(--color-accent)`
  - `#ccc` → `var(--color-border)`
  - `#fafafa` → `var(--color-surface)`
  - `#f0f7ff` → `var(--color-surface)` (or `--color-surface-muted` if discovery introduces a second surface tone)
- No functional changes. No layout changes. No JSX restructuring.
- One commit per component preferred; squash on merge if reviewer asks.

**Test scenarios:**
- *Happy path:* Each component renders identically to baseline except colors now match the new palette.
- *Verification:* `Select-String -Pattern '#0070f3|#ccc[^a-f0-9]|#fafafa|#f0f7ff' web_service/frontend/components/*.tsx` returns zero hits across the 7 files.

**Verification:**
- Grep returns zero hex hits in the 7 component files.
- Playwright snapshot of each component-in-context (via the page that uses it) shows no layout drift, only color drift.

---

- [ ] **Unit 7b: Functional page refactor (template, lighter touch)**

**Goal:** Refactor `/status/[id]` and `/recover` from inline styles to Tailwind utilities, drop them into the `(app)` route group's layout, and remove redundant nav/footer if present. No hero, no marketing copy, no CTA flourish — these read as calm utility pages.

**Requirements:** R4, R7.

**Dependencies:** Unit 6 (route-group layouts must exist), Unit 7a (component palette swap — these pages render `RecoverClient`, `ConversionStatus`, `TokenField`, `TokenList`).

**Files:**
- Move: `web_service/frontend/app/status/[id]/page.tsx` → `web_service/frontend/app/(app)/status/[id]/page.tsx`
- Move: `web_service/frontend/app/recover/page.tsx` → `web_service/frontend/app/(app)/recover/page.tsx`
- Modify (during move): inline `style={{...}}` → Tailwind utilities or `className`; preserve all React state, async behavior, and child component props verbatim.

**Approach:**
- Template-driven, not discovery-driven. The `(app)` layout supplies header, footer, and the narrow content width. Each page renders its own content children: a status panel for `/status/[id]`, a token recovery form for `/recover`.
- Acceptable Tailwind utilities: `bg-surface`, `text-text-base`, `text-text-muted`, `border border-border`, `rounded-lg`, `p-6` / `p-8`, `space-y-4`. Avoid any utility class that has a hex literal in `tailwind.config.ts` — everything resolves through `var(--color-*)`.
- Long error messages on `/status/[id]` and long token lists on `/recover` must wrap or scroll within their container without horizontal overflow.

**Test scenarios:**
- *Happy path:* Both pages render inside the `(app)` shell with calm spacing; functional behavior identical to baseline.
- *Edge case:* `/status/<invalid-id>` still surfaces the error state, now wrapped in the shared shell so the user can navigate away.
- *Integration:* localStorage probe on `/recover` still works; status polling on `/status/[id]` still polls; download links still work.

**Verification:**
- `Select-String -Pattern 'style=\{\{' web_service/frontend/app/(app)/**/*.tsx` returns zero hits.
- Both pages render inside the `(app)` layout's header + footer.
- Upload → status → download flow works end-to-end in `next dev`.

---

- [ ] **Unit 7c: Marketing page redesign (per-page discovery loop)**

**Goal:** Apply the `frontend-design` skill's discover → sketch → build → screenshot-verify loop to each of the 7 marketing pages. The high-judgment surface where editorial typography, generous whitespace, and trust-signal copy land.

**Requirements:** R4, R5, R7.

**Dependencies:** Unit 6 (route-group layouts), Unit 4 (fonts loaded), Unit 7a (components have new palette so screenshots reflect final colors).

**Files:**
- Move: `web_service/frontend/app/page.tsx` → `web_service/frontend/app/(marketing)/page.tsx`
- Move: `web_service/frontend/app/pricing/page.tsx` → `web_service/frontend/app/(marketing)/pricing/page.tsx`
- Move: `web_service/frontend/app/quality/page.tsx` → `web_service/frontend/app/(marketing)/quality/page.tsx`
- Move: `web_service/frontend/app/convert/{pdf-to-kfx,academic-pdf-to-kindle,pdf-footnotes-kindle,multi-column-pdf-kindle}/page.tsx` → `web_service/frontend/app/(marketing)/convert/*/page.tsx` (4 files)
- Modify (during move): each page restyled per discovery output; preserve `metadata` exports and `JsonLd` injections verbatim.

**Approach:**
- **Per-page discovery loop:** for each marketing page, take a Playwright screenshot of current state → sketch the proposed layout in prose (hero shape, content sections, CTA placement, whitespace cadence) → present sketch to user → only after approval, implement → screenshot the result → diff against sketch.
- **Page-specific shape:**
  - `/` (homepage) is the highest-judgment surface. Composition options: (a) UploadZone-as-hero with value prop directly above, (b) editorial hero band with UploadZone below the fold, (c) split layout with UploadZone right + value prop left. Discovery proposes one.
  - `/pricing` — clear tier comparison, no urgency timers, honest "what you get" framing.
  - `/quality` — preserve the existing comparison gallery; refresh typography and surrounding copy.
  - 4× `/convert/*` — already on Tailwind, palette/typography refresh + serif hero `<h1>`; preserve `JsonLd` per page.
- **Marketing aesthetic targets** (per `web-aesthetics` and the `project-leafbind-design-constraint` memory): serif `<h1>` at editorial scale (Lora); confident whitespace (Stripe/Linear cadence, not banner-ad density); one primary CTA per page; trust signals ("no tracking", "your file is never stored after conversion"); restrained motion; accent color sparingly (CTAs, focus rings, link hover).
- **AI-tell avoidance:** no gradient meshes, no glassmorphism, no autoplay anything, no overlay popups on first paint, no urgency copy, no fake download buttons.
- **One commit per page minimum** — easier reviewer mental model, easier rollback if a single page lands wrong.

**Patterns to follow:**
- `compound-engineering:frontend-design` skill: discover → sketch → build → screenshot-verify.
- `web-aesthetics` skill: avoid AI-tell patterns; prefer warm cream backgrounds, deliberate typography, restrained motion.

**Test scenarios:**
- *Happy path:* Each marketing page passes the AI-slop checklist; serif `<h1>` renders in Lora; CTA is singular and unambiguous.
- *Integration:* `JsonLd` on each `/convert/*` page still injects the correct schema after the move + refactor (verified by `view-source:` showing `<script type="application/ld+json">` in the head).
- *Integration:* `metadata` export per page still resolves correct OG image (per-slug dynamic for `/convert/*`, static for the other three).

**Verification:**
- All 7 marketing pages live under `app/(marketing)/`.
- `Select-String -Pattern '#0070f3|style=\{\{' web_service/frontend/app/(marketing)/**/*.tsx` returns zero hits.
- `JsonLd` script tags still present in `<head>` on every `/convert/*` page (view-source check).
- Each page approved via Playwright screenshot before its commit lands.

---

- [ ] **Unit 8: AI-slop checklist + Lighthouse verification + Playwright diff**

**Goal:** Validate that the redesigned site clears the AI-slop bar and does not regress Lighthouse or CWV vs. the EB-230 Unit 9 baseline.

**Requirements:** R5, R6, R7.

**Dependencies:** Unit 7 (all visual changes complete).

**Files:**
- Create: `web_service/frontend/.baselines/eb233-post/` (gitignored; post-change snapshots and Lighthouse report)
- Test: `web_service/frontend/.baselines/eb233-post/lighthouse-post.json` (post-redesign Lighthouse report)
- Test: `docs/solutions/eb233-design-system-decisions.md` (compound entry capturing palette, font, and token decisions for future redesigns)

**Approach:**
- **AI-slop checklist** (apply `web-aesthetics` skill manually):
  - [ ] No gradient meshes on hero or anywhere else
  - [ ] No glassmorphism backdrop-blur on cards
  - [ ] No generic Tailwind slate/indigo defaults survive (grep should return zero matches)
  - [ ] No autoplay anything, no overlay popups, no urgency timers, no fake CTAs
  - [ ] Primary CTA per page is singular and unambiguous (no "click here for free!" plus "limited time!" plus newsletter signup competing)
  - [ ] Whitespace is generous (Stripe cadence), not banner-ad-dense
  - [ ] Type pair feels deliberate; serif headlines + sans body have intentional contrast
  - [ ] Logo appears in header and footer; favicon visible in browser tab; OG previews render correctly in Twitter card validator / Vercel social-preview tool
- **Lighthouse verification:**
  - Run mobile Lighthouse on `/`, `/convert/pdf-to-kfx`, `/pricing` (the three pages baselined in Unit 1).
  - Save report to `.baselines/eb233-post/lighthouse-post.json`.
  - Compare to baseline: **LCP regression must be ≤ +200ms, CLS regression must be ≤ +0.02, INP regression must be ≤ +50ms**. Performance score must not drop by more than 2 points. If any threshold is breached, return to the relevant Unit (most likely Unit 4 for font loading, Unit 7 for layout).
- **Playwright diff:**
  - Snapshot all 9 routes at desktop (1440×900) and mobile (375×667) post-redesign.
  - Save to `.baselines/eb233-post/`.
  - Diff against Unit 1 pre-baselines: confirm intentional visual changes are present (palette, fonts, shell). Confirm no unintended regressions on pages outside the marketing scope.
- **Cross-browser smoke:** open the live preview in Chrome, Firefox, Safari, mobile Safari (Vercel preview deployment is the easiest path). Inspect logo crispness at 1×/2×/3× DPR.
- **Compound:** write `docs/solutions/eb233-design-system-decisions.md` capturing the palette hex values, font pair chosen, AI-slop checklist results, and any deviations from the plan. This closes the EB-230 + EB-233 compounding gap surfaced in the learnings research.

**Patterns to follow:**
- `web-aesthetics` skill AI-tell checklist.
- Lighthouse comparison methodology from EB-230 Unit 9 (`prompts/EB-230-unit9-lighthouse-cwv.md`).
- `docs/solutions/` frontmatter convention (module, tags, problem_type).

**Test scenarios:**
- *Happy path:* All 8 AI-slop checklist items pass; Lighthouse mobile performance score within 2 points of baseline; LCP/CLS/INP all within tolerance.
- *Edge case:* If Lighthouse regresses, the failure must be diagnosable from the diff (which page? which metric? which Unit owns the fix?).
- *Integration:* OG image previews correctly in Twitter card validator and Vercel social-share tool; favicon appears in browser tab; logo crisp at 3× DPR on mobile Safari.

**Verification:**
- `lighthouse-post.json` exists; comparison report shows no metric breaches.
- All 18 post-snapshot PNGs (9 routes × 2 widths) exist in `.baselines/eb233-post/`.
- `docs/solutions/eb233-design-system-decisions.md` exists with the decision record.
- AI-slop checklist signed off (commit message or PR description includes the 8 items).

---

## System-Wide Impact

- **Interaction graph:** The shared shell (Unit 6) is a new interaction point — clicking the logo in the header on any of the 9 pages now navigates to `/`. Clicking any footer cross-link navigates between pages. The pre-EB-233 inline-style pages had no such navigation; this is a net-new pattern they inherit.
- **Error propagation:** No error-handling changes. `/status/[id]` still surfaces pipeline errors from the FastAPI backend; `/recover` still shows token-not-found states. Both now do so inside the shared shell.
- **State lifecycle risks:** None. Visual refactor only; no state, persistence, or async behavior modified.
- **API surface parity:**
  - **`metadata.icons`** changes: the new file-convention icons auto-inject `<link rel="icon">` tags. Confirm no consumer (analytics, monitoring, third-party scrapers) relied on the absence of these tags.
  - **OG image URLs** change: the new static `/opengraph-image` and per-slug dynamic `/convert/[slug]/opengraph-image` change the social-share preview URLs. Existing shared links on Twitter/X/LinkedIn will continue to display the old quality-page screenshot until the platforms re-scrape; this is a one-time visual transition, not a regression.
  - **Favicon URL** changes from the Next.js default to `/favicon.ico` (file-convention).
  - **Robots / sitemap:** no changes to `app/robots.ts` or `app/sitemap.ts`; both preserved.
- **Integration coverage:**
  - The codemod in Unit 1 may surface lingering Next 15 patterns; treat any non-design-related codemod changes as scope-extending and report rather than absorb silently.
  - The font loading change (Unit 4) is the highest-risk performance change; Lighthouse verification in Unit 8 is the integration gate.
  - The preflight flip (Unit 5) is the highest-risk visual change for the already-Tailwind pages; baseline diff in Unit 8 is the gate.
- **Unchanged invariants:**
  - Upload flow behavior: drop file → POST to FastAPI backend → poll status → download. Unchanged.
  - Stripe checkout flow: BuyButtons → Stripe-hosted Checkout → success/cancel return. Unchanged.
  - Token recovery flow: localStorage probe → display tokens, or fallback to session-ID form. Unchanged.
  - JSON-LD structured data on `/quality` and all `/convert/*` pages. Unchanged.
  - Sitemap and robots routes. Unchanged.
  - All page slugs and paths. Unchanged — no SEO-impacting URL changes.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Preflight flip cascades unexpected visual regressions across already-Tailwind pages | Unit 5 sweeps explicitly before the flip; Unit 1 baseline + Unit 8 diff catch any miss |
| Font swap (FOUT) introduces measurable CLS regression | `adjustFontFallback: true` (default) generates fallback faces with `size-adjust` metrics; Unit 8 Lighthouse verification is the gate; fallback to `display: 'optional'` if CLS contribution exceeds 0.02 |
| Inline-style pages stop matching the rest of the site visually after token swap | CSS variable plumbing in Unit 3 means inline-style components consume the same `var(--color-*)` as Tailwind utilities; this is by design, not a risk to fight |
| Hand-built SVG logo doesn't match the Gemini concept aesthetically | Iterate via the `frontend-design` skill in Unit 2; Playwright screenshot the logo at multiple sizes (16px favicon, 32px header, 180px apple-icon, 1200px OG); user approves before commit |
| `ImageResponse` per-slug OG images add cold-start latency or bundle bloat | Static OG for 5 of 9 pages; dynamic only for the 4 `/convert/*` slugs. Vercel CDN-caches after first render. Smoke test cold-start latency in Unit 2 verification |
| Next 16 codemod surfaces unrelated upgrade debt that bloats this ticket | Commit codemod changes in Unit 1 as a separate commit; if non-trivial drift surfaces, file a follow-up ticket and absorb only design-related codemod changes |
| `frontend-design` skill discovery proposes a layout the user dislikes mid-plan | Discovery presents Playwright screenshots before each marketing page lands; explicit approval per page before commit |
| Logo prompt-set / source-of-truth disappears after this ticket (future redesigns can't reproduce) | Unit 8 compound entry captures the Gemini prompts used + the final SVG source; logo source committed to repo means future iteration starts from real ground truth |
| Vercel ghost-deploy bug (per `vercel-deploy-verification` skill) lets the PR look merged while production stays stale | After PR merge, verify production alias serves the new fonts and logo before declaring done; use `vercel inspect` and `vercel ls` per the skill |

## Documentation / Operational Notes

- **`docs/solutions/eb233-design-system-decisions.md`** (Unit 8) becomes the canonical record of palette hex values, font pair, AI-slop checklist outcome, and Lighthouse before/after numbers. Future redesigns start from this record, not from scratch.
- **`web_service/frontend/design-tokens.ts`** gets a header comment marking it source of truth — this is the in-code documentation for token consumers.
- **`CLAUDE.md` Visual QA / Frontend section**: consider adding a one-paragraph note that the leafbind frontend uses a `design-tokens.ts` → `tailwind.config.ts` + `globals.css :root` mirror pattern, with the rationale. Deferred to Phase 5.4 post-plan option.
- **Production verification post-merge**: per `vercel-deploy-verification` skill, do not declare EB-233 done until the production alias (`leafbind.io`) serves the new fonts (DevTools Network shows `.woff2` files) and the new favicon (browser tab shows the leaf, not the Next.js triangle).

## Parallelization Map

Per global `CLAUDE.md` INFRA-216 / INFRA-220, plans intended for subagent-swarm execution must include a Parallelization Map. EB-233 will run through the swarm pilot.

### Intent summary (premise-drift defense)

The brief — the one sentence each subagent must not contradict in its checkpoint diff:

> **Deliver a brand layer (logo + tokens + fonts + shared shell + per-page restyle) that makes leafbind.io look like a calm, trustworthy paid product — Stripe/Linear/Vercel-adjacent — without regressing Lighthouse, breaking any flow, or touching JSON-LD / sitemap / robots / upload-Stripe-recovery functional behavior.**

If a subagent's checkpoint diff includes changes to functional behavior, structured data, sitemap, robots, or anything outside its declared file set, the coordinator rejects the checkpoint and re-tasks.

### Shared interfaces frozen before spawn

These must land first (sequentially, on master or on a coordinator-controlled branch) before any parallel stream begins:

1. **Token CSS-variable names** — the set of `--color-*`, `--font-*`, `--space-*`, `--radius-*` CSS variable names exposed by `globals.css :root`. Frozen in Unit 3. Subagents in 7a/7b/7c consume these names; renaming a variable mid-stream breaks every dependent stream.
2. **Route-group structure** — `app/(marketing)/` and `app/(app)/` directory names and the layouts at their roots. Frozen in Unit 6. Page moves in 7b and 7c target these paths.
3. **`<Header />` and `<Footer />` component public API** — the props they accept (likely none — they read no state and are server components). Frozen in Unit 6.
4. **`<Logo />` component public API** — `className` prop, `currentColor` inheritance, `aria-label` default. Frozen in Unit 2.

### Per-stream definition

| Stream | Worktree branch | Unit(s) | Subagent type | Files-touched (declared, no overlap) | Depends on | Blocks |
|---|---|---|---|---|---|---|
| **A** | `feat/EB-233-assets` | Unit 1, Unit 2 | implementer | `web_service/frontend/.baselines/eb233-pre/**`, `web_service/frontend/components/Logo.tsx`, `web_service/frontend/app/{icon.svg,favicon.ico,apple-icon.png,opengraph-image.png,twitter-image.png}`, `web_service/frontend/app/convert/[slug]/{opengraph-image.tsx,twitter-image.tsx}`, `web_service/frontend/public/fonts/**`, `web_service/frontend/app/layout.tsx` (metadataBase line only) | — | B, C |
| **B** | `feat/EB-233-tokens` | Unit 3, Unit 4, Unit 5 | implementer | `web_service/frontend/design-tokens.ts`, `web_service/frontend/tailwind.config.ts` (new), `web_service/frontend/tailwind.config.js` (delete), `web_service/frontend/app/globals.css`, `web_service/frontend/app/layout.tsx` (font imports + className only), `web_service/frontend/tools/check-token-drift.mjs`, `web_service/frontend/package.json` (script + prebuild only) | A (logo informs palette greens) | C, D, E, F |
| **C** | `feat/EB-233-shell` | Unit 6 | implementer | `web_service/frontend/components/{Header,Footer}.tsx`, `web_service/frontend/app/(marketing)/layout.tsx`, `web_service/frontend/app/(app)/layout.tsx` | A (Logo), B (token CSS vars) | E, F |
| **D** | `feat/EB-233-component-swap` | Unit 7a | implementer | `web_service/frontend/components/{UploadZone,BuyButtons,FormatSelector,ConversionStatus,TokenField,TokenList,RecoverClient}.tsx` (hex→var edits only — no JSX/state changes) | B (CSS vars) | E, F |
| **E** | `feat/EB-233-functional-pages` | Unit 7b | implementer | Page moves: `app/status/[id]/page.tsx` → `app/(app)/status/[id]/page.tsx`, `app/recover/page.tsx` → `app/(app)/recover/page.tsx`. In-file edits: inline-style → Tailwind utilities. | C (route group), D (components have new palette) | G |
| **F** | `feat/EB-233-marketing-pages` | Unit 7c | implementer (with `compound-engineering:frontend-design` skill per page) | Page moves: `app/{page,pricing/page,quality/page}.tsx` and 4× `app/convert/*/page.tsx` → `app/(marketing)/...`. In-file edits: restyle per discovery output. | C (route group), D (components have new palette) | G |
| **G** | `feat/EB-233-verify` | Unit 8 | qa-agent | `web_service/frontend/.baselines/eb233-post/**`, `docs/solutions/eb233-design-system-decisions.md` | E, F | — (final) |

### Pre-spawn overlap check

Before spawning Streams A-G, the coordinator runs `git diff --name-only origin/master..HEAD` for each declared file set and asserts:

1. No two stream file sets intersect (declared-file overlap = re-design the streams).
2. Files appearing in the "frozen interface" list (token CSS variable names, route group paths, component public APIs) are *not* in any stream's mutable file list — they are read-only contracts.
3. The `app/layout.tsx` file is mutated by two streams (A for `metadataBase`, B for font imports). This is the **one declared exception** — coordinator must serialize these two edits on the same branch before spawning C/D, OR split `layout.tsx` edits into a coordinator-applied prep commit.

### Runtime overlap check

After each subagent's checkpoint commit, the coordinator runs:

    git diff --name-only <stream-base>..<stream-tip>

and asserts the changed-file set is a subset of the stream's declared files. Any file outside the declaration is a checkpoint rejection.

### Checkpoint commit definition

A valid checkpoint commit is one that:

1. Modifies only files in the stream's declared list (plus the stream's own `docs/solutions/` or `.baselines/` artifacts).
2. Compiles cleanly under `next build` (verified by the subagent before commit).
3. Includes a one-line intent reference: `feat(EB-233-stream-<X>): <unit-title> — checkpoint <N>/<total>`.
4. For visual streams (E, F): includes a Playwright screenshot artifact at `.baselines/eb233-stream-<X>/checkpoint-<N>.png`.

### Merge order and gate

Merge order (after all streams complete):

    A → master  →  B → master  →  C → master  →  D → master  →  (E, F in parallel) → master  →  G → master

Merge gate (applied to each stream's PR before squash to master):

- All declared-file diffs present; no out-of-declaration changes.
- `next build` passes on the stream tip.
- `npm run check:tokens` passes (post-Stream-B).
- Stream-G adds the final regression gate: Lighthouse comparison report and Playwright diff report attached to the PR.

### Failure modes the map defends against

- **Premise drift:** subagent re-interprets the brief and refactors unrelated functional behavior. Defense: intent summary + declared file set + runtime overlap check.
- **Shared-interface mid-stream churn:** subagent renames a CSS variable that another stream depends on. Defense: frozen-interface list pre-spawn, plus the drift guard (Unit 3) which fails CI if `globals.css` and `design-tokens.ts` diverge.
- **Hidden coupling via `layout.tsx`:** two streams want to edit the same root layout. Defense: declared exception with coordinator-serialized prep commit.
- **Per-page judgment drift in Stream F:** marketing redesign goes AI-slop. Defense: per-page Playwright screenshot checkpoint + AI-slop checklist applied at every commit, not just at Unit 8.

## Sources & References

- **Origin document:** [EB-233 Jira ticket](https://jlfowler1084.atlassian.net/browse/EB-233)
- **Predecessor plan:** [`docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md`](2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md)
- **Lighthouse baseline reference:** [`prompts/EB-230-unit9-lighthouse-cwv.md`](../../prompts/EB-230-unit9-lighthouse-cwv.md)
- **Design constraint memory:** [`C:\Users\Joe\.claude\projects\f--Projects-EbookAutomation\memory\project_leafbind_design_constraint.md`](file-link)
- **Skills referenced:**
  - `compound-engineering:frontend-design` — execution skill for marketing-page discovery + sketch + verify loop
  - `web-aesthetics` — AI-tell checklist + typography/color guidance
  - `compound-engineering:gemini-imagegen` — logo concept reference source (already used)
  - `vercel-deploy-verification` — post-merge production verification protocol
  - `worktree-management` — branch isolation for visual refactor
- **External docs:**
  - [Next.js 16 upgrade guide](https://nextjs.org/docs/app/guides/upgrading/version-16)
  - [Next.js 16 release notes](https://nextjs.org/blog/next-16)
  - [`next/font` API](https://github.com/vercel/next.js/blob/v16.2.2/docs/01-app/03-api-reference/02-components/font.mdx)
  - [Icon file conventions](https://github.com/vercel/next.js/blob/v16.2.2/docs/01-app/03-api-reference/03-file-conventions/01-metadata/app-icons.mdx)
  - [`ImageResponse` API](https://github.com/vercel/next.js/blob/v16.2.2/docs/01-app/03-api-reference/04-functions/image-response.mdx)
  - [Tailwind v3 dark mode (`selector` strategy)](https://v3.tailwindcss.com/docs/dark-mode)
  - [Tailwind v3 CSS variable colors](https://v3.tailwindcss.com/docs/customizing-colors)
  - [Tailwind v3 preflight](https://v3.tailwindcss.com/docs/preflight)
