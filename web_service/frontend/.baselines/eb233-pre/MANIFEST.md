# EB-233 Pre-Redesign Baseline Manifest

## Capture Metadata

| Field | Value |
|-------|-------|
| Captured | 2026-05-14 |
| Ticket | EB-233 (Unit 1 — Pre-flight & baseline capture) |
| Target URL | https://leafbind.io (production) |
| Production HEAD SHA | 8f0c7a06d6b96d5148d69b49f8ac38a14db606fe |
| Playwright version | 1.60.0 |
| Lighthouse version | global install (npx lighthouse) |
| Codemod | `npx @next/codemod@canary upgrade latest` — already at v16.2.6, no changes |

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

**Total: 18 PNG files** — gitignored (see root `.gitignore`), not committed to repo.

## Lighthouse Mobile Baselines (3 files)

Run with `--form-factor=mobile`, `--chrome-flags="--headless"`.
Three separate JSON files saved. Format: `lighthouse-baseline-<slug>.json`.

| Route | File | Perf | A11y | Best-Practices | SEO | LCP | CLS | TBT | Speed Index |
|-------|------|------|------|----------------|-----|-----|-----|-----|-------------|
| `/` | lighthouse-baseline-home.json | 98 | 100 | 100 | 100 | 1.7 s | 0 | 30 ms | 4.1 s |
| `/convert/pdf-to-kfx` | lighthouse-baseline-convert-pdf-to-kfx.json | 98 | 95 | 100 | 100 | 1.8 s | 0 | 20 ms | 3.9 s |
| `/pricing` | lighthouse-baseline-pricing.json | 98 | 96 | 100 | 100 | 1.7 s | 0 | 20 ms | 3.9 s |

**These scores are the regression contract for Unit 8.** EB-233 must not degrade any score.

## Codemod Summary

`npx @next/codemod@canary upgrade latest` run against `web_service/frontend/`.

Result: `Current Next.js version is already on the target version "v16.2.6"` — no changes made, no commit needed.

## Notes

- `status/test-id-12345` renders an error/not-found state — this is expected and is the correct baseline for that route.
- The `.baselines/` directory itself is gitignored; only this `MANIFEST.md` and `.gitkeep` are committed.
- Binary PNG and JSON files are gitignored per project policy (large artifacts).
