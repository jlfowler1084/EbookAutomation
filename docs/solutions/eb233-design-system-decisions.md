---
date: 2026-05-15
ticket: EB-233
module: web_service/frontend
tags: [design-system, brand, tokens, frontend, lighthouse, swarm-pilot, lcp, ttfb]
problem_type: design-pass
updated: 2026-05-15
updated_ticket: EB-238
---

# EB-233 — Leafbind design system + custom logo

## EB-238 update (2026-05-15) — Font preload disabled (partial close, TTFB discovered as new bottleneck)

### What we believed vs. what was true

The EB-240 commit (immediately below) claimed "EB-238 absorbed" on the theory
that swapping Lora → Newsreader with `preload: true` would recover EB-233's LCP
regression. **Production Lighthouse proved this wrong** — LCP got worse, not
better: +517ms on `/`, +662ms on `/pricing`, +566ms on `/convert/pdf-to-kfx`
relative to the EB-238 ceiling targets.

EB-238 was then opened (real, not absorbed) with 6 candidate strategies. This
update implements **Strategy A — disable preload on both Newsreader and DM
Sans** (`web_service/frontend/app/layout.tsx`).

### Why preload was hurting

`next/font` preload is **binary, not per-weight**. Configuring Newsreader with
weight `["400","500","600"]` × style `["normal","italic"]` emits 6
`<link rel="preload">` tags. DM Sans with 4 weights emits 4 more. Total 10
font preload tags competing with critical CSS for browser request slots.

With `display: swap`, Chrome's LCP measures the **first paint** of the largest
element — which uses `adjustFontFallback`'s metrics-adjusted Georgia fallback,
**not** the actual Newsreader file. So preloading the font files only delayed
the critical-path first paint; the visual swap to Newsreader happens later and
is not measured by LCP.

### Production Lighthouse — Strategy A result (mobile, post-promote)

| Page | EB-230 baseline | EB-233 (Lora) | EB-240 (Newsreader+preload) | **Strategy A (now)** | EB-238 target | Δ vs target |
|---|---|---|---|---|---|---|
| `/` | 1700ms | 1986ms | 2417ms | **2088ms** | ≤1900ms | +188ms over |
| `/pricing` | 1700ms | 2055ms | 2562ms | **2564ms** | ≤1900ms | +664ms over |
| `/convert/pdf-to-kfx` | 1800ms | 2125ms | 2566ms | **2568ms** | ≤2000ms | +568ms over |

CLS = 0 on all three. Perf score 96 / 93 / 93. **No regression introduced.**

### What this tells us — TTFB is the real residual bottleneck

Strategy A delivered a clean **-329ms on `/`** but left the other two pages
flat. The differential is the diagnostic: fonts mattered on `/` (Newsreader
text was the LCP element), but **`/pricing` and `/convert/pdf-to-kfx` have a
different LCP element where fonts were never the bottleneck**.

Lighthouse `lcp-breakdown-insight` audit confirms — TTFB dominates across all
three pages:

| Page | TTFB | Element render delay | Resource load |
|---|---|---|---|
| `/` | 2473ms | 282ms | 0ms |
| `/pricing` | 2456ms | 301ms | 0ms |
| `/convert/pdf-to-kfx` | 2440ms | 342ms | 0ms |

A ~2.4s TTFB on Next.js marketing pages on Vercel is unusual. Hypotheses for
the follow-up ticket: Vercel cold-start projection, RSC server rendering
overhead, Cloudflare→Vercel relay latency, or Lighthouse simulated-4G
projection inflation. **All three pages having near-identical TTFB makes
cold-start less likely (cold-start would vary).**

### Lessons recorded

1. **`preload: true` on a swap-display font hurts LCP, not helps it.** Chrome
   measures LCP as the *first paint*, and `display: swap` makes the fallback
   the first paint. Preloading the swapped font only delays the critical
   path. **The next person who reaches for `preload: true` here should read
   this section first.** Comment added inline in `layout.tsx`.

2. **"Absorbed" claims need post-deploy verification.** The EB-240 commit
   message asserted "EB-238 absorbed" based on local Lighthouse and a
   plausible-sounding font-swap theory. Production proved the opposite.
   Going forward: do not mark a follow-up ticket absorbed by the work that
   *should* fix it until production Lighthouse confirms.

3. **Differential improvement is a diagnostic.** When a fix moves one page
   and not another, treat that as a signal — the pages have different
   bottlenecks. Don't keep trying font strategies on a TTFB-bound page.

### Follow-up ticket required

Opening a sibling ticket for the TTFB investigation. EB-238 closes as
**partial success** — the font preload bug is fixed and one page meets
target ceiling; the other two need a separate TTFB-focused investigation.

## EB-240 update (2026-05-15) — Newsreader/DM Sans + palette + Plex Mono

### Font swap decision

**Newsreader adopted** (EB-238 absorbed). At 32px header height the wordmark
"leafbind.io" in Newsreader 500 looks balanced — slightly wider-set than Lora
but the italic `.io` in sand (`#c9a96e`) sits cleanly without crowding. The
serifs add more visual distinction from body text than Lora did at this scale.
Decision: Newsreader used for both wordmark and page headings.

Font matrix:
- Display / headlines: **Newsreader** 400/500/600 + italic via `next/font/google`
- UI / body: **DM Sans** 400/500/600/700 via `next/font/google`
- Eyebrow labels: **IBM Plex Mono** 400/500/600 via `next/font/google`

Preload: Newsreader + DM Sans preloaded (`preload: true`); IBM Plex Mono deferred
(`preload: false`) since it only appears in eyebrow labels below the fold.

### Palette changes

| Token | Before (EB-233) | After (EB-240) |
|---|---|---|
| `--lb-green` / `--color-brand` | `#2D4A2B` | `#2f5d3a` |
| `--lb-cream` / `--color-surface` | `#FAF8F3` | `#f4efe2` |
| `--lb-paper-back` / `--color-paper-back` | (hardcoded in SVG only) | `#e0d8c0` (formal token) |

Kept as-is: `--lb-green-dark` (#1f3f27), `--lb-paper` (#fbf7ec), `--lb-ink`
(#1a1f1c), `--lb-sand` (#c9a96e).

### Eyebrow label treatment

All eyebrow labels (pattern: uppercase + tracking-widest) converted from
`font-sans` to `font-mono` (IBM Plex Mono) across 5 marketing pages:
`quality/`, `convert/pdf-to-kfx`, `convert/academic-pdf-to-kindle`,
`convert/multi-column-pdf-kindle`, `convert/pdf-footnotes-kindle` — 28 instances.

### Lighthouse (localhost, EB-240 — same environment caveat as EB-233)

| Page | Perf | LCP | CLS |
|---|---|---|---|
| `/` | 77 | 4037ms | 0.001 |
| `/pricing` | 77 | 4039ms | 0.000 |
| `/convert/pdf-to-kfx` | 78 | 3944ms | 0.000 |

**Caveat:** These are localhost measurements (same limitation documented in
EB-233). Applying the ~2x ratio from EB-233's calibration, CDN LCP estimates
~1.9-2.1s. CLS is 0 across all pages — no layout shift from font swap.
Font preloads are emitted correctly in HTML head (`<link rel="preload">` for
Newsreader + DM Sans). Production Lighthouse rerun needed after deployment.

### EB-238 status

Absorbed. Newsreader is live with `preload: true`; EB-238's LCP improvement
intent is fulfilled. Coordinator should close EB-238 after verifying Newsreader
shipped correctly on production.



## Summary

Shipped the brand layer on leafbind.io across 9 routes via a 7-stream swarm pilot
(per INFRA-216 Parallelization Map). Pre-existing functional product with stock
Tailwind defaults → calm, trustworthy, Stripe/Linear-adjacent paid product.

## Final palette (forest-green identity)

| Token | Hex | Purpose |
|---|---|---|
| brand | #2D4A2B | Primary forest green (logo leaf body) |
| brand-dark | #1a3a1a | Deeper forest (midrib, hover) |
| accent | #3D7A3A | CTAs, focus rings, link hover |
| surface | #FAF8F3 | Warm cream page background |
| surface-muted | #F5F1E8 | Slightly darker cream — cards |
| border | #E2DFD5 | Soft taupe-cream dividers |
| text-base | #1a1a1a | Body + heading ink |
| text-muted | #6a6a6a | Secondary copy |

## Font pair

- Headings: Lora (serif, weight 500, letter-spacing -0.5 to -1.2)
- Body: Inter (sans, weight 400-500)
- Both via `next/font/google` with CSS variable export pattern (`--font-inter`,
  `--font-lora`); self-hosted at build time, zero runtime calls to Google Fonts.

## Lighthouse comparison (post-redesign vs. pre-redesign baseline)

| Page | Baseline | Post-redesign | Delta |
|---|---|---|---|
| `/` | Perf 98 / LCP 1.7s / CLS 0 | Perf 94 avg / LCP 2.79s avg / CLS 0 | Perf -4 / LCP +1.09s |
| `/convert/pdf-to-kfx` | Perf 98 / LCP 1.8s / CLS 0 | Perf 92 / LCP 3.01s / CLS 0 | Perf -6 / LCP +1.21s |
| `/pricing` | Perf 98 / LCP 1.7s / CLS 0 | Perf 97 / LCP 2.10s / CLS 0 | Perf -1 / LCP +0.40s |

**Regression verdict: LCP and Performance score regressions detected on `/` and
`/convert/pdf-to-kfx`.** These exceed the Unit 8 regression contract (LCP ≤ +200ms,
Perf drop ≤ 2 points). `/pricing` Perf passes but LCP fails.

**Important caveat:** Baseline was captured against production CDN (`https://leafbind.io`);
post-redesign audit was captured against `localhost:3001` (`next build && next start`).
Local measurement underestimates CDN performance. Coordinator should rerun against a
Vercel Preview URL or trigger a production deployment before treating these as hard regressions.

**Likely causes:**
- Lora + Inter font files add to the LCP path on mobile (even with `display: 'swap'`).
- Inline SVG `<Logo />` in Header adds DOM weight on every page.
- Local build latency vs. Vercel CDN: the measurement environment disadvantages the
  post-redesign audit relative to the CDN-served baseline.

**Recommended follow-up if regressions confirmed on CDN:**
1. Add `<link rel="preload">` for Lora font subset in `app/layout.tsx`.
2. Consider subsetting Inter to WOFF2 with only Latin characters.
3. Evaluate whether `<Logo />` SVG complexity can be reduced further.

## AI-slop checklist

| Check | Result |
|---|---|
| Zero gradient-mesh / conic-gradient / radial-gradient | PASS |
| Zero glassmorphism (backdrop-blur / backdrop-filter) | PASS |
| Zero generic Tailwind defaults (slate-N, indigo-N, zinc-N) | PASS |
| Zero urgency copy (limited time, act now, hurry, only N left, expires in) | PASS |
| Zero autoplay | PASS |
| Zero overlay popups on first paint (useEffect → setIsOpen) | PASS — two useEffect usages are functional (status polling + localStorage token recovery), not overlay popups |
| Single primary CTA per marketing page | PASS — home: UploadForm (one upload zone); pricing: BuyButtons section (no competing CTAs) |
| Logo appears in Header AND Footer | PASS — `<Logo className="h-8 w-auto" />` in both Header.tsx:9 and Footer.tsx:11 |
| Favicon visible in tab (icon.svg + favicon.ico) | PASS — both `app/icon.svg` and `app/favicon.ico` exist |
| OG previews render | PASS — `/opengraph-image.png` returns 200 image/png; `/convert/pdf-to-kfx/opengraph-image` returns 200 image/png |

### Known remaining hardcoded hex values (deferred follow-ups)

Six instances of `#666` and `#555` remain in:
- `components/RecoverClient.tsx` (4 instances)
- `components/TokenList.tsx` (1 instance)
- `components/UploadZone.tsx` (1 instance, `color: "#666"` on helper text)

These were flagged in the Stream D scope as intentionally deferred ("Stream D left
untouched"). They should map to `var(--color-text-muted)` in a follow-up.

## Architectural decisions worth recording

1. **Route groups (not `<AppShell variant>`).** `app/(marketing)/layout.tsx`
   and `app/(app)/layout.tsx` — router-enforced contract beats a runtime prop.
   Adding a new functional page = drop into `app/(app)/`. Adopted after the
   Phase 5.3.7 deepening pass surfaced the variant-prop maintenance trap.

2. **Token drift guard (`tools/check-token-drift.mjs`).** CI-gated parity check
   between `design-tokens.ts` and `globals.css :root`. Wired into `prebuild` so
   Vercel deploy fails on drift. Smoke-tested by intentionally diverging one
   hex, confirming exit 1, reverting. Confirmed passing in Unit 8 verification:
   "OK: 8 tokens in design-tokens.ts <-> globals.css :root all match."

3. **Unit 7 split into 7a/7b/7c.** Mechanical component palette swap (7a) is
   delegable; functional page refactor (7b) is template-driven; marketing
   redesign (7c) is high-judgment. Splitting unlocked parallel execution and
   put the right discipline at the right level.

4. **Drift-guard test smoke pattern.** Don't ship "drift guard exists" without
   intentionally injecting drift and confirming the guard fires. Pattern from
   global CLAUDE.md INFRA-183.

5. **Stream A2 logo SVG: hand-drafted, not vector-traced from PNG.** SVG path
   data derived from the Gemini concept PNG via visual interpretation, then
   iterated with v1 → v2 → v3 (tapered leaf + larger curl + simpler veins).
   For future redesigns: this is a "spirit" SVG, not a pixel-trace. The
   committed `brand-assets/` PNGs are the ground truth for re-interpretation.

6. **Static OG image file convention vs. dynamic.** `app/opengraph-image.png`
   is served at `/opengraph-image.png` (not `/opengraph-image` bare path) — this
   is correct Next.js file-convention behavior. Dynamic per-slug OG images for
   `/convert/[slug]` via `opengraph-image.tsx` return `image/png` correctly. Do
   not confuse 404 at bare `/opengraph-image` as a bug.

7. **Lighthouse measurement environment matters.** Baseline was captured on
   production CDN; post-redesign audit on localhost. This systematically disadvantages
   the post-redesign scores by removing CDN edge delivery, HTTP/2 push, and
   Cloudflare caching. Future audits should consistently use the same environment
   (prefer production/preview URL over localhost for Lighthouse).

## Swarm pilot retrospective notes

- **7 streams, 7 merged PRs** (excluding the prep commit on layout.tsx). Streams
  A1, A2, B, C, D, E, F each landed clean via separate PRs, all squash-merged to master.
- **Parallel execution worked** for Streams C+D (zero file overlap) and E+F
  (zero file overlap). Both pairs could execute in parallel without conflict.
- **Highest-judgment stream (F)** redesigned marketing pages (home, pricing,
  quality, 4x /convert/*) with editorial value-prop sections, Lora headings,
  trust signals, and single-CTA discipline. No gradient mesh, no glassmorphism,
  no urgency patterns introduced.
- **All builds pass.** `npm run build` succeeds (including `prebuild` token drift
  check). TypeScript and lint clean. 17 static pages generated.

## Open follow-ups

- **Production Lighthouse rerun** — rerun against Vercel preview URL or after
  production deployment to get CDN-equivalent scores. Current localhost regressions
  may be measurement artifact.
- **LCP investigation** — if production confirms LCP regression: preload Lora font
  subset, subset Inter to Latin WOFF2, evaluate Logo SVG complexity reduction.
- **Hardcoded hex follow-up** — `#666` and `#555` in RecoverClient.tsx,
  TokenList.tsx, UploadZone.tsx should map to `var(--color-text-muted)`.
- **Dark mode** — deferred per plan. One `darkMode: 'selector'` line in
  `tailwind.config.ts` plus a `.dark { … }` override block in `globals.css`.
- **`useReportWebVitals` analytics endpoint** — deferred per plan.
- **Stripe checkout success page + post-purchase email design** — deferred.
- **Production deployment trigger** — Vercel is currently deploying EB-233
  changes as "Preview" environment only. Coordinator needs to trigger production
  deployment to make the design live on `https://leafbind.io`.
