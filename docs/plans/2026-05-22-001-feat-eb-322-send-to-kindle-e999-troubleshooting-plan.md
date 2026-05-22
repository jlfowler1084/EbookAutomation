---
title: "feat(EB-322): Send-to-Kindle E999 troubleshooting page"
type: feat
status: active
date: 2026-05-22
origin: docs/brainstorms/2026-05-22-eb-322-send-to-kindle-e999-troubleshooting-requirements.md
ticket: EB-322
parent: EB-303 (Phase 3b — decided first launch, 2026-05-22)
---

# feat(EB-322): Send-to-Kindle E999 troubleshooting page

## Overview

Ship a single info-led troubleshooting page at `/guides/send-to-kindle-error-e999` targeting the
~5,300/mo Send-to-Kindle error-code cluster (e999 internal error + auth-failure + silent
failures) surfaced by the EB-308 Semrush trial sprint. The page definitively explains the error
codes, walks through diagnostic fixes, and routes the unfixable subset (size cap, malformed file,
DRM) to leafbind's hosted PDF→KFX workflow as the "skip Send-to-Kindle entirely" path. This is
the **decided first Phase 3b page** (per EB-303 launch sequence, 2026-05-22), ahead of the EPUB
pillar (EB-320).

It is a near-clone of the Phase 2 Unit 2 pain-pillar architecture
(`web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx`) — same
React Server Component layout, same `buildArticleSchema` + `buildFAQPageSchema` builders, same
same-PR hygiene policy (EB-295). One PR, ~5 files.

## Problem Frame

A user mid-failure pastes `E999 internal error` (or an auth failure, or "send to kindle doesn't
work") into Google looking for an immediate fix. The e999 SERP is the most wide-open opportunity
in the entire trial: zero authoritative sources in the top 20 (Amazon UK Help at #15 only),
13 forum/Q&A results, 5 ad-monetized troubleshooting blogs, and zero conversion-tool competitors
(EB-308 Finding R). Peak commercial intent — a failed Send-to-Kindle is exactly when a user reaches
for a third-party tool. (see origin: `docs/brainstorms/2026-05-22-eb-322-send-to-kindle-e999-troubleshooting-requirements.md`)

## Requirements Trace

- R1. New page at `/guides/send-to-kindle-error-e999` — single dedicated URL, error-code-anchored title/H1.
- R2. Lede (≥300 words) defining E999, auth-failure, and silent-failure meanings, citing Amazon's official STK help.
- R3. Three error-class H2 sections with diagnostic H3 sub-anchors (E999 / authentication failure / silent "doesn't work").
- R4. Honest CTA (R4 discipline): route fixable cases to fixes; route unfixable subset to leafbind PDF→KFX. No overselling.
- R5. Article + FAQPage JSON-LD via the shared builders; AIO/PAA-friendly answer formatting (first-line definitive answers).
- R6. Same-PR discoverability hygiene (EB-295): sitemap entry + llms.txt entry + Footer Guides link + guides hub card.
- R7. Inbound internal cross-link FROM the new page TO Unit 2 (`/guides/send-to-kindle-not-working`).
- R8. Pre-merge gates green: link-check CI, 2-layer schema validation. Post-merge: indexed ≤14 days; EB-292 attribution smoke.

## Scope Boundaries

- No expansion of Unit 2 (`/guides/send-to-kindle-not-working`) in this PR — its content stays untouched.
- No DRM stripping/removal instructions — describe Amazon's rejection behavior only (legal-sensitivity boundary, same as EB-320).
- No Amazon-account-recovery copy — do not scope leafbind into Amazon-account troubleshooting.
- No Position Tracking reconfiguration in code — adding the e999 keyword is a manual Joe action in the Semrush web UI.
- Title/H1 must NOT foreground `send to kindle doesn't work` — Amazon's STK landing ranks #3 on that SERP (Finding AA); it is a secondary H3 anchor only.

### Deferred to Separate Tasks

- Reciprocal internal link Unit 2 → this page: separate follow-up PR (keeps this PR scoped per EB-322 non-goal).
- Manual SERP review of `an authentication failure occured send to kindle app` (KD=0) to decide a future ranking target.
- Position Tracking keyword add (`e999 - send to kindle internal error`): manual Joe web-UI action, fills free-tier slot to 10/10.

## Context & Research

### Relevant Code and Patterns

- **Canonical pattern (clone this):** `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx` — RSC pain-pillar layout: `<JsonLd>` schema injection, `faqItems` as single source of truth feeding both rendered FAQ and `buildFAQPageSchema`, `PUBLISHED`/`SLUG`/`CANONICAL` consts, "What's not working?" category grid, numbered fix sections, leafbind backup section, Sources block with last-verified dates, author byline.
- **Schema builders:** `web_service/frontend/lib/structured-data.ts` — `buildArticleSchema` (line 228, sets `mainEntityOfPage` automatically) and `buildFAQPageSchema` (line 206).
- **JsonLd component:** `web_service/frontend/components/JsonLd.tsx` (imported as `../../../../components/JsonLd` from a guides page).
- **Sibling plan (architecture inheritance):** `docs/plans/2026-05-17-001-feat-eb-320-epub-on-kindle-pillar-plan.md`.
- **Same-PR hygiene surfaces:** `web_service/frontend/app/sitemap.ts`, `web_service/frontend/public/llms.txt`, `web_service/frontend/components/Footer.tsx`, `web_service/frontend/app/(marketing)/guides/page.tsx` (guides hub).

### Institutional Learnings

- `docs/solutions/best-practices/jsonld-script-tag-count-build-instability-2026-05-14.md` — keep JSON-LD `<script>` tag count stable; build instability if mismatched. Two schema objects → two `<JsonLd>` tags, matching Unit 2 exactly.
- `docs/solutions/best-practices/schema-validator-playwright-headless-quirk-2026-05-14.md` — 2-layer schema validation pattern (the pre-merge gate).
- `docs/solutions/best-practices/vercel-production-branch-misconfiguration-2026-05-15.md` — post-merge Vercel alias confirmation.
- `docs/solutions/eb252-next-plausible-next16-compat.md` — post-merge curl-verify pattern.

### External References

- None required — strong local pattern (Unit 2 is a direct example; EB-320 is a sibling plan). External research skipped per ce:plan §1.2.
- Primary-source facts (Amazon STK behavior) carried from the EB-320 plan's verified block; re-confirm STK size caps / DRM behavior at authoring time.

## Key Technical Decisions

- **Clone Unit 2's RSC structure, not a new abstraction.** Five Phase 2/3 guides already share this shape; consistency aids the schema validator and reviewer familiarity. (No shared template extraction — that would be premature for page #6.)
- **Error-code-organized, not symptom-organized.** Three H2s by error class (E999 / auth-failure / silent failure), each with diagnostic H3s — distinct from Unit 2's symptom-category + numbered-fix shape. This is what makes the two pages non-duplicate to Google.
- **`faqItems` single-source-of-truth.** FAQ array feeds both the rendered FAQ section and `buildFAQPageSchema`, exactly as Unit 2 does — prevents schema/visible drift.
- **Two JSON-LD script tags** (Article + FAQPage), matching Unit 2, to respect the script-tag-count build-stability learning.

## Open Questions

### Resolved During Planning

- Page architecture (separate page vs Unit 2 expansion): **separate page** (brainstorm).
- Slug: **`send-to-kindle-error-e999`** (brainstorm).
- Auth-failure keyword treatment: **include section, exclude from ranking gate** (KD=0).
- Image strategy: **no custom screenshots required** — error-code troubleshooting is text/diagnostic; reuse the existing OG image (`/quality/pipeline-headings.png`) as Unit 2 does. (Avoids the screenshot-production dependency the Scribe guide had.)

### Deferred to Implementation

- Exact FAQ question set and count — author from the cluster phrasings at write time (target the e999 + auth + silent-failure variants); final wording is execution-time.
- Exact lede prose and per-section copy — content authoring, not a planning decision.
- Whether any H3 needs a small diagnostic table (e.g., error → likely cause) — decide while drafting; low-cost either way.

## Implementation Units

- [ ] **Unit 1: Troubleshooting page component + schema**

**Goal:** The full page at `/guides/send-to-kindle-error-e999` — content sections, metadata, and Article + FAQPage JSON-LD.

**Requirements:** R1, R2, R3, R4, R5, R7

**Dependencies:** None (clones existing pattern).

**Files:**
- Create: `web_service/frontend/app/(marketing)/guides/send-to-kindle-error-e999/page.tsx`

**Approach:**
- Clone the Unit 2 page scaffold: `PUBLISHED`/`SLUG = "send-to-kindle-error-e999"`/`CANONICAL` consts, `metadata` export (title ≤60 chars foregrounding "E999 internal error"; canonical; OG + Twitter; reuse `/quality/pipeline-headings.png`).
- Body: error-code-anchored H1; ≥300-word lede (E999 = Amazon's generic internal-error for oversize/malformed/DRM/transient; auth-failure; silent failures), citing Amazon STK help.
- Three H2 sections with diagnostic H3s per the brainstorm content structure (E999 / Authentication failure / "Doesn't work" silent failures).
- Honest CTA section routing unfixable cases to `/convert/pdf-to-kfx`; inline cross-link to `/guides/send-to-kindle-not-working` (R7) framed as "general Send-to-Kindle fixes."
- `faqItems` array (single source of truth) → rendered FAQ + `buildFAQPageSchema`; `buildArticleSchema` for the Article. Two `<JsonLd>` tags. First line of each FAQ answer is a definitive standalone statement (AIO/PAA).
- Sources block with Amazon STK help URLs + last-verified date; author byline.

**Patterns to follow:**
- `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx` (structure, schema wiring, Sources/byline).
- `web_service/frontend/lib/structured-data.ts` builders.

**Test scenarios:**
- Happy path: route renders without RSC/build errors; H1 + three error-class H2s present.
- Happy path: `metadata.title` ≤ 60 chars and contains "E999"/"internal error"; `alternates.canonical` = `https://leafbind.io/guides/send-to-kindle-error-e999`.
- Schema: Article + FAQPage JSON-LD validate against Google Rich Results Test (and the 2-layer schema validator); exactly two `<JsonLd>` script tags rendered.
- Integration: every `faqItems` entry renders in the FAQ section AND appears in the FAQPage schema (no drift).
- Edge case: internal links resolve — `/guides/send-to-kindle-not-working`, `/convert/pdf-to-kfx`, `/pricing` (link-check CI).

**Verification:** Page builds, renders at the route, both schemas validate, FAQ/schema parity holds, internal links resolve.

- [ ] **Unit 2: Same-PR discoverability hygiene (EB-295)**

**Goal:** Wire the new URL into every discovery surface in the same PR.

**Requirements:** R6

**Dependencies:** Unit 1 (route must exist).

**Files:**
- Modify: `web_service/frontend/app/sitemap.ts`
- Modify: `web_service/frontend/public/llms.txt`
- Modify: `web_service/frontend/components/Footer.tsx`
- Modify: `web_service/frontend/app/(marketing)/guides/page.tsx`

**Approach:**
- Add the new URL to `sitemap.ts` with a realistic `lastmod` and a priority consistent with the other Phase 2/3 guides.
- Add a `llms.txt` entry describing the page (mirror the existing guide entries' format).
- Add a Footer "Guides" column link to the new page.
- Add a guides hub card on `guides/page.tsx` matching the existing card pattern.

**Patterns to follow:** Existing guide entries in each of the four files (e.g., the `send-to-kindle-not-working` rows already present).

**Test scenarios:**
- Happy path: `sitemap.ts` output includes the new URL with valid lastmod/priority.
- Happy path: `public/llms.txt` lists the new page.
- Happy path: Footer renders the new Guides link; guides hub renders the new card; both resolve (link-check CI).

**Verification:** All four surfaces reference the new URL; link-check CI green.

- [ ] **Unit 3: Pre-merge gate pass + post-merge verification**

**Goal:** Confirm the page clears the established gates before and after merge.

**Requirements:** R8

**Dependencies:** Units 1–2.

**Files:**
- Test: existing CI link-check + schema validator (no new test files; marketing pages are validated by the gate suite, not per-page unit tests).

**Approach:**
- Pre-merge: run the 2-layer schema validator (per `schema-validator-playwright-headless-quirk` solution) and link-check CI; confirm build is green.
- Post-merge: curl-verify the live path (per `eb252-next-plausible-next16-compat`); confirm Vercel production alias updated (per `vercel-production-branch-misconfiguration`); run the EB-292 attribution smoke to confirm `referrer` captures `/guides/send-to-kindle-error-e999`.

**Test scenarios:**
- Pre-merge: schema validator passes on the new page; link-check reports zero broken links; production build succeeds.
- Post-merge: `curl` of the live URL returns 200 with the expected canonical; attribution smoke shows the new path in `referrer`.
- Edge case: Rich Results Test shows both Article and FAQPage detected with no errors.

**Verification:** Green CI pre-merge; live page indexed-eligible and attribution-instrumented post-merge.

## System-Wide Impact

- **Interaction graph:** New leaf route under `app/(marketing)/guides/`; no shared component or API changes. Footer + guides hub + sitemap + llms.txt gain one entry each.
- **Error propagation:** None — static RSC content page, no runtime data fetching.
- **State lifecycle risks:** None.
- **API surface parity:** None — no backend/API touched.
- **Integration coverage:** FAQ/schema parity (Unit 1) and link resolution (Unit 2) are the cross-surface checks.
- **Unchanged invariants:** Unit 2 page content is explicitly unchanged; the JSON-LD script-tag count convention (2 tags) is preserved; no change to the convert flow or pricing.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Page reads as near-duplicate of Unit 2 to Google | Error-code-organized structure + distinct slug + distinct title; cross-link declares the relationship. Confirmed Unit 2 has zero e999 coverage. |
| JSON-LD script-tag-count build instability | Match Unit 2 exactly: two `<JsonLd>` tags (Article + FAQPage). Per the documented solution. |
| Overselling leafbind for fixable STK cases (E-E-A-T / honesty) | R4 CTA discipline — route fixable cases to fixes first; leafbind only for the unfixable subset. |
| Counting the KD=0 auth-failure keyword as a launch target | Excluded from the ranking gate; included only for topical completeness pending manual SERP review. |
| DRM-removal legal sensitivity | Describe Amazon's rejection behavior only; no removal instructions (explicit non-goal). |

## Documentation / Operational Notes

- No docs beyond the page itself. Post-merge, note the live URL on EB-322 and (when the reciprocal-link follow-up is filed) reference it from Unit 2.
- Manual follow-ups for Joe: add the e999 Position Tracking keyword (web UI); file the reciprocal Unit 2 → e999 link follow-up.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-05-22-eb-322-send-to-kindle-e999-troubleshooting-requirements.md](docs/brainstorms/2026-05-22-eb-322-send-to-kindle-e999-troubleshooting-requirements.md)
- Pattern page: `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx`
- Schema builders: `web_service/frontend/lib/structured-data.ts`
- Sibling plan: `docs/plans/2026-05-17-001-feat-eb-320-epub-on-kindle-pillar-plan.md`
- Trial synthesis: `docs/seo/eb-241-semrush-trial-sprint-2026-05.md` (Findings L, Q, R, Z, AA)
- Solutions: `docs/solutions/best-practices/{jsonld-script-tag-count-build-instability,schema-validator-playwright-headless-quirk,vercel-production-branch-misconfiguration}-2026-05-*.md`, `docs/solutions/eb252-next-plausible-next16-compat.md`
