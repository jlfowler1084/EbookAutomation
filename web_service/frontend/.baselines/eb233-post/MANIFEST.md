# EB-233 Post-Redesign Baseline Manifest

## Capture Metadata

| Field | Value |
|-------|-------|
| Captured | 2026-05-15 |
| Ticket | EB-233 (Unit 8 — Stream G verification) |
| Target URL | http://localhost:3001 (next build + next start, PORT=3001) |
| Source SHA | ecf9e0c (feat/EB-233-stream-F, post all 6 streams merged to master) |
| Playwright version | (via package.json playwright dependency) |
| Lighthouse version | 13.3.0 (global npx) |
| Note | Production site (leafbind.io) not yet serving EB-233 — Vercel deployments are all "Preview" environment; production env not triggered. Local build used for audit. |

## Playwright Snapshots (18 files)

Captured at viewport sizes: desktop (1440x900) and mobile (375x667).
All snapshots are viewport-height screenshots (not full-page), `deviceScaleFactor=1`.

| Route | Desktop (1440x900) | Mobile (375x667) |
|-------|--------------------|------------------|
| `/` (home) | home-1440x900.png | home-375x667.png |
| `/pricing` | pricing-1440x900.png | pricing-375x667.png |
| `/quality` | quality-1440x900.png | quality-375x667.png |
| `/recover` | recover-1440x900.png | recover-375x667.png |
| `/status/test-id-12345` | status-test-id-1440x900.png | status-test-id-375x667.png |
| `/convert/pdf-to-kfx` | convert-pdf-to-kfx-1440x900.png | convert-pdf-to-kfx-375x667.png |
| `/convert/academic-pdf-to-kindle` | convert-academic-pdf-to-kindle-1440x900.png | convert-academic-pdf-to-kindle-375x667.png |
| `/convert/pdf-footnotes-kindle` | convert-pdf-footnotes-kindle-1440x900.png | convert-pdf-footnotes-kindle-375x667.png |
| `/convert/multi-column-pdf-kindle` | convert-multi-column-pdf-kindle-1440x900.png | convert-multi-column-pdf-kindle-375x667.png |

**Total: 18 PNG files** — gitignored (binary artifacts), not committed to repo.
All 18 captured successfully (0 failures). New design confirmed: Header + nav + Footer visible
on all routes, Lora/Inter fonts loading, forest-green palette applied.

## Lighthouse Mobile Audit (Post-Redesign)

Run with `--form-factor=mobile`, `--chrome-flags="--headless --no-sandbox"`.
All three JSON files saved under `.baselines/eb233-post/` (gitignored).
Two runs performed on home page to validate consistency.

| Route | Perf | A11y | Best-Practices | SEO | LCP | CLS | TBT |
|-------|------|------|----------------|-----|-----|-----|-----|
| `/` (run 1) | 95 | 100 | 100 | 100 | 2.63 s | 0.00013 | 8.5 ms |
| `/` (run 2) | 93 | 100 | 100 | 100 | 2.94 s | 0 | 15 ms |
| `/convert/pdf-to-kfx` | 92 | 100 | 100 | 100 | 3.01 s | 0 | 9.0 ms |
| `/pricing` | 97 | 100 | 100 | 100 | 2.10 s | 0 | 13 ms |

## Regression Contract Assessment

| Page | Metric | Baseline | Post | Delta | Contract | Status |
|------|--------|----------|------|-------|----------|--------|
| `/` | Perf score | 98 | 94 avg | -4 | ≤ -2 | **FAIL** |
| `/` | LCP | 1.7 s | 2.79 s avg | +1.09 s | ≤ +200ms | **FAIL** |
| `/` | CLS | 0 | 0.00013 | +0.00013 | ≤ +0.02 | PASS |
| `/` | INP | — | — | — | ≤ +50ms | PASS (TBT proxy: 8.5–15ms) |
| `/convert/pdf-to-kfx` | Perf score | 98 | 92 | -6 | ≤ -2 | **FAIL** |
| `/convert/pdf-to-kfx` | LCP | 1.8 s | 3.01 s | +1.21 s | ≤ +200ms | **FAIL** |
| `/convert/pdf-to-kfx` | CLS | 0 | 0 | 0 | ≤ +0.02 | PASS |
| `/pricing` | Perf score | 98 | 97 | -1 | ≤ -2 | PASS |
| `/pricing` | LCP | 1.7 s | 2.10 s | +0.40 s | ≤ +200ms | **FAIL** |
| `/pricing` | CLS | 0 | 0 | 0 | ≤ +0.02 | PASS |

**Regression verdict: REGRESSIONS DETECTED.** LCP degraded on all 3 pages;
Performance score degraded on 2 of 3 pages (home and /convert/*). These are above
the plan's Unit 8 regression contract thresholds. Coordinator decision required.

### Likely Root Cause

The LCP regression is consistent with the addition of:
- Lora + Inter fonts loaded via `next/font/google` (even with `display: 'swap'` and
  `adjustFontFallback: true`, self-hosted font files add to FCP/LCP path on mobile).
- Header SVG logo (inline SVG React component) adding DOM weight.
- The local build + localhost measurement vs. production CDN — Vercel CDN delivers
  assets faster than localhost. The baseline was captured against `https://leafbind.io`
  production; this post-redesign audit is localhost. Some delta is measurement artifact.

Coordinator should rerun against a Vercel Preview URL for the most accurate comparison,
or trigger a production deployment and re-audit.

## OG Endpoints

| Endpoint | Status | Notes |
|----------|--------|-------|
| `/opengraph-image.png` | 200 image/png | Static file — Next.js file convention |
| `/opengraph-image` | 404 | Expected: static OG images serve as `.png`, not bare path |
| `/convert/pdf-to-kfx/opengraph-image` | 200 image/png | Dynamic ImageResponse — correct |

## Notes

- All 18 Playwright snapshots captured with new design (Header + nav + Footer confirmed).
- Binary PNG and JSON files are gitignored per project policy.
- Only this MANIFEST.md and `.gitkeep` are committed.
