---
title: "feat(EB-320): EPUB-on-Kindle pillar page"
type: feat
status: active
date: 2026-05-17
origin: docs/brainstorms/2026-05-17-eb-320-phase3-epub-pillar-requirements.md
ticket: EB-320
parent: EB-241 (Phase 2 — shipped)
---

# feat(EB-320): EPUB-on-Kindle pillar page

## Overview

Ship a single info-led pillar page at `/guides/does-kindle-support-epub` on leafbind.io that targets the 8-keyword EPUB-direction informational cluster (~6,520/mo combined US volume) surfaced by the EB-308 Semrush trial sprint. The page answers the user's headline question honestly (Send-to-Kindle accepts EPUB and server-side-converts it to KFX/AZW3) and **honestly positions leafbind as a hosted Calibre + KFX Output plugin workflow with web upload, no local install required** — useful when STK rejects the user's file AND they don't want to install Calibre locally.

**Important repositioning (post-PL-2 audit, 2026-05-17, with user-supplied product-context clarification):** The original plan framed leafbind as the path for STK-rejected EPUBs. The PL-2 product-lens audit verified against `web_service/`, `tools/`, and `web_service/config.py` that leafbind has no EPUB-specific premium capability — every advertised premium value prop is PDF-shaped. **The user's own product-context clarification then sharpened this further: EPUB conversion is *not* a leafbind selling point at all. Calibre handles EPUB→KFX natively without issue; STK handles EPUB→Kindle server-side without issue; EPUB and other non-PDF inputs are convenience features in the pipeline, not the marketed value prop.** leafbind's actual selling point is **PDF conversion for users whose PDFs failed in other tools** — the PDF-shaped premium value props (column-aware extraction, font-size heading detection, footnote linking, Gemini OCR remediation) genuinely solve a problem the user has personally hit many times.

This page is therefore best framed as **an honest informational page with brand-building and cross-sell-to-PDF value, not a primary EPUB conversion play**. Users finding the page via EPUB queries will learn that STK/Calibre handle their case fine; they leave with the honest answer plus an introduction to leafbind as a helpful brand. The conversion path is *not* "this EPUB user buys premium credits" but "this user remembers leafbind when their next PDF conversion fails." Success Criteria are calibrated accordingly. A separate customer-facing bug (EB-321) tracks the unrelated issue that premium EPUB output is structurally worse than free for the same input.

Single new page, one PR (touches 5 files: page, sitemap, llms.txt, Footer, guides hub). Inherits all Phase 2 reviewer-pass infrastructure (EB-295) and hygiene policies. Reciprocal inbound links from Unit 3 and Unit 5 are explicitly out of scope for this PR and ship in a separate follow-up ticket.

## Problem Frame

EB-308 Semrush research found that leafbind has the product capability to serve EPUB→Kindle traffic but zero content targeting that direction. Eight informational keywords with confirmed US volume (top: `can kindle read epub` 1,300/mo, `epub format to kindle` 1,300/mo, `does kindle read epub` 1,000/mo) and high CPC variance (peak $14.12 on `does kindle support epub` — supporting evidence, not the headline argument). The headline argument is the capability gap.

The cluster's intent is 5-of-8 informational ("does/can kindle read/use/support epub") and 3-of-8 positional ("epub format on/to kindle"). None are action-led. The natural shape is a single info-led pillar page under `/guides/` (mirroring Unit 2's pain-pillar pattern at `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/`), with the 8 target keywords surfaced as FAQ H3 anchors so Google's intent classifier can attribute traffic to specific phrasings.

Primary-source verification (2026-05-17): Send-to-Kindle EPUB ingestion launched May 2022 (email path) and November 2022 (web uploader at send.amazon.com). MOBI was fully sunset December 20, 2023. Current STK accepts EPUB + PDF + DOC/DOCX + TXT + RTF + HTM/HTML + PNG/JPG/GIF/BMP. Size caps: 50 MB (email) / 200 MB (web). DRM-protected files are rejected (STK does not strip DRM). Malformed EPUBs are rejected by STK's strict XHTML/manifest/encoding validation (the existence of the community "Kindle EPUB Fix" tool is direct evidence of this failure class). EPUB is server-side-converted to KFX (modern) or KF8/AZW3 (older firmware); Kindle is *not* a native EPUB reader. *(See origin: `docs/brainstorms/2026-05-17-eb-320-phase3-epub-pillar-requirements.md` Dependencies/Assumptions block.)*

## Requirements Trace

Carried forward from the origin document. R-IDs preserved for traceability.

**Page surface**
- R1. New page at `/guides/does-kindle-support-epub` — single dedicated URL, no sub-paths.
- R2. H1 directly answers the headline keyword: "Does Kindle support EPUB?" or a tight semantic equivalent.
- R3. First 300 words deliver the verified honest answer: **for most users, Send-to-Kindle is the recommended path** (STK accepts EPUB since May 2022; MOBI fully sunset Dec 20, 2023; STK converts EPUB → KFX/AZW3 server-side; Kindle is *not* a native EPUB reader; STK caps 50 MB email / 200 MB web). The page's job is to (a) explain this honestly, (b) name STK failure cases, (c) position leafbind as ONE alternative without overselling.
- R4. CTA block (Phase 2 layout convention; Unit 2 pain-pillar precedent) **is informational + cross-sell, not a primary EPUB conversion pitch**. The page tells users the honest answer about EPUB on Kindle (STK works for most cases; Calibre + KFX plugin works locally; leafbind also handles EPUB but doesn't outperform either tool for EPUB-source jobs). The CTA's primary purpose is **brand introduction with a cross-sell soft-pitch to leafbind's actual differentiator: PDF conversion that succeeds where other tools fail** — column-aware extraction for multi-column PDFs, smart heading detection via font-size classification, bidirectional footnote linking, Gemini OCR remediation for scanned PDFs. The CTA copy should: (a) acknowledge STK/Calibre as legitimate paths for clean EPUBs, (b) mention leafbind as one option for the small STK-failure subset (oversize, malformed) if the user prefers a hosted web tool over installing Calibre locally, (c) introduce leafbind's real strength briefly: "We're built for PDF→Kindle conversions where other tools fail — try us when your next PDF won't behave." This makes the page useful to honest EPUB-seekers AND plants brand recognition for the user's eventual PDF problem. The CTA must NOT invent EPUB-specific premium magic. Each STK failure mode paired with a verifiable user-diagnosable signal.

**Keyword coverage**
- R5. FAQ section covers all 8 EPUB cluster keywords as explicit H3 anchors. Each H3 contains a 2-4 sentence answer using the target phrasing verbatim in the first sentence. *(See Key Technical Decisions for word count + ordering.)*
- R5a. **(Amendment 2026-05-18, post-EB-308 Day 3 sweep Finding J — the broader EPUB question cluster is ~18,350/mo across 50 question variants, not 6,520/mo across 8.)** Beyond the 8 FAQ H3 anchors, the page includes **2-4 additional H2 sections** providing lightweight verb-family + capability-nuance coverage. **Strategic intent (per Joe 2026-05-18):** keep the page's sharp "Does Kindle support EPUB?" core intent. Do NOT restructure as a 4-bucket pillar; do NOT add a full "how to {verb} EPUB to Kindle" workflow tutorial (deferred to a separate ticket). The new H2 sections are short framing/contextual sections (~150 words each), not standalone keyword-targeted pages. Section candidates (final 2-4 picked during Unit 2 authoring):
    - "Can you send an EPUB to Kindle?" (lexical-variant of the headline; ~720/mo `how to send an epub to kindle` + 1,000/mo `how to send epub to kindle`)
    - "Can you upload an EPUB to Kindle?" (~320/mo `how to upload epub to kindle`)
    - "Why Kindle does not open EPUB directly" (capability-nuance framing; reinforces the server-side-conversion honesty in R3)
    - "Best options if your EPUB will not send" (failure-mode bridge — natural lead-in to the CTA per R4; complements but does not duplicate the failure-mode list in the lede)
- R5b. **(Amendment 2026-05-18, post-EB-308 Day 3 sweep Finding H — AI Overviews and People Also Ask are present on 8/8 tracked Phase 2 keywords; the EPUB SERP almost certainly inherits this.)** Each FAQ H3 answer (per R5) and each H2 contextual section (per R5a) is structured for **AIO citation eligibility**: definitive first sentence answering the H3/H2 question using the target phrasing verbatim, followed by 2-3 sentences of supporting context using verifiable facts (Amazon STK help page nodeId G5WYD9SAF7PGXRNA per R3). Per the existing `docs/solutions/eb258-seo-phase1-patterns.md` learning, target 134-167 words per FAQ standalone passage. Each FAQ is wrapped in `FAQPage` JSON-LD (per R7) so PAA capture is also eligible. **Authoring discipline:** treat ~30-40% of expected click flow as AIO/PAA, not 100% position #1 — copy must be standalone-citable, not dependent on surrounding context.
- R6. At least two FAQ answers contain inline-text links **out** to `/convert/pdf-to-kfx` and `/guides/how-to-send-pdf-to-kindle`. Reciprocal inbound links are deferred to a follow-up ticket *(see origin)*.

**Schema and metadata**
- R7. Article + FAQPage JSON-LD via the existing `JsonLd` component (EB-230 precedent); validated against Google's Rich Results Test before merge.
- R8. Article schema includes the required `image` field. Hero image lives at `web_service/frontend/public/guides/does-kindle-support-epub/hero.jpg` per `docs/solutions/best-practices/pillar-page-screenshots-2026-05-15.md` convention (JPG quality 90, Next.js `Image` handles optimization).
- R9. Title ≤ 60 chars, meta description 145-160 chars, OG image set, canonical URL points to the apex (`https://leafbind.io/guides/does-kindle-support-epub`). Brand casing per EB-275.

**Phase 2 hygiene policies (inherited from EB-295)**
- R10. Sitemap entry for the new page lands in the same PR (`web_service/frontend/app/sitemap.ts`).
- R11. `lastModified` uses the existing per-entry `new Date("YYYY-MM-DD")` pattern from `web_service/frontend/app/sitemap.ts` (no parameterless `new Date()`, no raw ISO string). Use the merge-day ISO date.
- R12. `/llms.txt` updated with a new entry for the page in the same PR.
- R13. Link-check gate (`web_service/frontend/tools/check-internal-links.mjs`) passes in CI.
- R14. Site-nav inbound links updated in the same PR: (a) `web_service/frontend/components/Footer.tsx` Guides column gains a new entry; (b) the guides array in `web_service/frontend/app/(marketing)/guides/page.tsx` gains the new entry so the `/guides` hub lists it.

## Scope Boundaries

- **No new pages other than `/guides/does-kindle-support-epub`.** Specifically excluded: `/guides/can-kindle-read-pdf` (1,030/mo), `/convert/epub-to-kfx` (50+/mo), the kindle-scribe-academic-papers cluster (~40/mo). All defensible Phase 3b candidates.
- **No FAQ extensions to other Phase 2 pages.** Unit 2/3/4/5 FAQ-extension candidates from the Unit 9 LowFruits triage are deferred.
- **No Phase 2 audit work.** Unit 5 eat-the-bounce position audit, Unit 5 content-depth audit vs pdf2kindle.com, Unit 3 lexical-variant audit are flagged but deferred to separate tickets.
- **No Semrush Position Tracking setup.** Manual Joe action in Semrush web UI, tracked separately.
- **No backlink outreach.** Phase 4 territory.
- **No reverse-direction (Kindle → EPUB) content.** Out of leafbind's core direction.
- **No DRM advisory or DRM-stripping copy.** Legally sensitive; the page describes STK's behavior (rejects DRM-protected files) without instructing users on DRM removal.

### Deferred to Separate Tasks

- **Reciprocal inbound links from Unit 3 + Unit 5 to the new page**: ~5-min follow-up ticket filed in Unit 6 post-merge. Splits R6 to keep this PR at "single new page" scope and avoid interfering with active Phase 2 measurement windows.
- **Phase 3a LowFruits re-run on the 104k/mo `send to kindle` Related cluster**: separate Phase 3b ticket. Trigger condition: within 14 days of EB-320 merge regardless of ranking outcome.
- **`ce:compound` entries for sitemap.ts / llms.txt / Footer.tsx / guides-hub IA conventions**: separate ticket post-merge — these patterns are empirically established across 8 Phase 2 PRs but uncompounded (per learnings-researcher gap analysis).
- **R8 hero asset replacement (if stopgap is used in this PR)**: separate ticket to swap a temporary asset for a brand-illustration commission.

## Context & Research

### Relevant Code and Patterns

- **Phase 2 page precedent (canonical CTA layout reference)**: `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx` (Unit 2 pain pillar). Border-b section dividers, 2-column symptom cards, numbered ordered lists. CTA at the bottom — the brainstorm's "above the fold" phrasing was intent guidance, not layout prescription.
- **Mega-guide depth precedent**: `web_service/frontend/app/(marketing)/guides/how-to-send-pdf-to-kindle/page.tsx` (Unit 3). TOC pattern + internal-link density.
- **Converter pillar (R6 outbound link target)**: `web_service/frontend/app/(marketing)/convert/pdf-to-kfx/page.tsx` (Unit 5).
- **Comparison hub (FAQ inheritance precedent)**: `web_service/frontend/app/(marketing)/guides/kindle-scribe-vs-remarkable/page.tsx` (Unit 4).
- **JsonLd injection component**: existing `JsonLd` React component from EB-230 work. Article + FAQPage schemas already used on multiple Phase 2 pages.
- **Sitemap pattern**: `web_service/frontend/app/sitemap.ts` uses per-entry `new Date("YYYY-MM-DD")` literal (no parameterless `new Date()` — convention from EB-295).
- **llms.txt**: presumed to live at `web_service/frontend/public/llms.txt` based on Next.js public-asset convention; resolve exact path during Unit 4.
- **Footer Guides column**: `web_service/frontend/components/Footer.tsx` hardcodes the guides array.
- **Guides hub**: `web_service/frontend/app/(marketing)/guides/page.tsx` hardcodes a guides array.
- **Link-check gate**: `web_service/frontend/tools/check-internal-links.mjs` (PR #122 / commit `5e6777b`). Validates `<Link href="/...">` resolves to a `page.tsx` — catches broken outbound links, does NOT catch missing inbound links from footer/hub. R14 closes that gap.
- **UploadZone (downstream from CTA)**: `web_service/frontend/components/UploadZone.tsx` already accepts `.epub` in the file picker.
- **FormatSelector**: defaults to `epub` output. EPUB-input users who don't change output get an EPUB→EPUB no-op. R4 CTA copy must not mislead about this.
- **EB-292 recovery-rail attribution**: instrumentation live since PR #113 (2026-05-16) — captures attributed conversions per page.

### Institutional Learnings (`docs/solutions/`)

- **`docs/solutions/best-practices/jsonld-script-tag-count-build-instability-2026-05-14.md`** — Critical for Unit 5. Next.js 16 + Turbopack may combine Article + FAQPage into a **single `<script type="application/ld+json">`** tag. Assert on `@type` occurrences via `grep -oE '"@type":"[^"]*"' | sort -u`, never on `<script>` tag counts.
- **`docs/solutions/best-practices/schema-validator-playwright-headless-quirk-2026-05-14.md`** — Use the 2-layer schema validation pattern in Unit 5: one Playwright screenshot for the first page as visual proof, then HTTP fetch + `JSON.parse` for remaining `@type` validation. Validator silently renders blank on repeat headless loads — single-pattern verification will produce false-negative panic.
- **`docs/solutions/best-practices/pillar-page-screenshots-2026-05-15.md`** — R8 image asset convention locked: `web_service/frontend/public/guides/<slug>/`, JPG quality 90, Next.js `Image` handles optimization. Mix phone shots (reading experience) + desktop captures (TOC panels) for in-body imagery. For schema `image` field, a single hero shot is sufficient.
- **`docs/solutions/eb258-seo-phase1-patterns.md`** — Content angle: **quote competitors' own docs as the highest-leverage citation**. Amazon's STK help page documenting the 50MB/200MB caps and DRM rejection IS the strongest possible E-E-A-T citation; lead with it in R3's body. Also: AI Overview eligibility prefers **134-167-word standalone FAQ passages** — this calibrates per-FAQ length. MobileRead > Reddit for verbatim Kindle-user vocabulary.
- **`docs/solutions/eb252-next-plausible-next16-compat.md`** — Unit 6 post-deploy check: `curl https://leafbind.io/guides/does-kindle-support-epub` must confirm (a) 200, (b) `@type` set contains Article + FAQPage, (c) Plausible script tag present. Analytics + JSON-LD can both look fine in source but ship broken — curl-verify or it didn't happen.
- **`docs/solutions/best-practices/vercel-production-branch-misconfiguration-2026-05-15.md`** — Unit 6 post-merge: `npx vercel ls leafbind` confirms Production row exists; `npx vercel inspect <prod-url>` confirms the alias moved. Do not trust "Vercel: success" as a green PR check (the doc-review pass already flagged this from a prior incident).
- **`docs/solutions/best-practices/nextjs-16-turbopack-render-blocking-css-2026-05-14.md`** — Unit 5 Lighthouse expectation: Performance 71-79, LCP 2.5-3.0s is documented Turbopack baseline. Stop-the-line only at Performance < 60 or LCP > 5s. Do not chase a Turbopack CSS-chunk gap on this PR.
- **`docs/solutions/eb249-ttfb-diagnosis-2026-05-15.md`** — Companion to the Turbopack doc: ~2.4s simulated TTFB on leafbind marketing pages is Lighthouse-modeled-slow-4G; actual server response 18-22ms. Do not file a perf regression on Lighthouse TTFB alone.
- **`docs/solutions/eb233-design-system-decisions.md`** — Background: design tokens, Newsreader/DM Sans, font-preload decisions. Relevant if R8's hero image becomes the LCP element (it might — above-the-fold imagery).

### Gaps to compound after merge

The learnings-researcher confirmed there are **no `docs/solutions/` entries** for: sitemap.ts update conventions, llms.txt update conventions, Footer.tsx + guides-hub IA conventions, or EB-295 reviewer-pass infrastructure lessons. Patterns are established empirically across 8 Phase 2 PRs but uncompounded. Unit 6 files a follow-up ticket to compound them.

## Key Technical Decisions

- **Word count: ~2,000-2,400 words total, with hard floors.** **(Revised 2026-05-18 to accommodate R5a additions.)** Per the AI Overview eligibility heuristic from `eb258-seo-phase1-patterns.md`, each FAQ + each R5a H2 targets 150 ± 15 words (within the 134-167 AI-Overview band). 8 FAQs × 150 = ~1,200 words FAQ floor; R3 mandates a 300-word lede floor; 2-4 R5a H2 sections × 150 = ~300-600 words; ~200-400 words of body between lede and FAQ → total range ~2,000-2,400. **Hard floors are R3 (300-word lede), AI-Overview FAQ length (134 × 8 = 1,072 floor), and R5a minimum (134 × 2 = 268 floor for the 2 mandatory verb-family/nuance H2s).** Pages reaching the upper end of this range remain under the helpful-content filler threshold the adversarial review flagged at 2,500 — the band is intentionally tight, not loose. **Anti-pattern guard (Joe 2026-05-18):** do NOT bloat past 2,400 words by adding workflow-tutorial content for each verb in the broader 18,350/mo cluster. That work belongs in a deferred follow-up ticket so the page's sharp "Does Kindle support EPUB?" intent is preserved. *(See origin Deferred to Planning item 3 + 2026-05-18 EB-308 Day 3 sweep findings.)*
- **FAQ ordering: intent grouping.** Does-form first (`does kindle support epub`, `does kindle read epub`, `does kindle take epub`, `does kindle read epub format`), can-form second (`can kindle read epub`, `can kindle use epub`), positional last (`epub format to kindle`, `epub format on kindle`). Reinforces honest-answer framing; the most-common question intent surfaces immediately after the lede. *(See origin Deferred to Planning item 4.)*
- **R5a H2 placement: between the lede and the FAQ section.** The new H2 sections (R5a) sit between R3's 300-word lede and the 8-keyword FAQ block. Order them by intent flow: capability-nuance H2 first ("Why Kindle does not open EPUB directly" — reinforces lede honesty), verb-family H2s second ("Can you send/upload an EPUB to Kindle?" — bridges to FAQ), troubleshooting H2 last ("Best options if your EPUB will not send" — natural lead-in to R4 CTA mid-page placement). 2-4 H2s only; 4 is the upper bound to preserve the page's tight scope.
- **CTA copy: explicit free-vs-premium framing using canonical leafbind copy.** Mirror the existing production framing at `web_service/frontend/app/(marketing)/convert/pdf-to-kfx/page.tsx` (FAQ section): "Free tier converts up to 3 files per day with a 20 MB file size cap, producing EPUB output. KFX — enhanced typography, tappable footnotes, better heading navigation — is a premium feature." This is factually accurate to the actual pricing model in `web_service/frontend/app/(marketing)/pricing/page.tsx` (3 conversions/day, 20 MB free / 100 MB premium, EPUB free / KFX premium). **There is no per-page free-tier gating** — earlier draft copy ("free for 5 pages or less") was factually incorrect and was corrected during plan review (PL-1, product-lens, conf 0.97). The CTA must NOT invent a page-count limit. *(See origin R4.)*
- **R4 failure-mode language uses verified STK error signals.** DRM rejection: "Files protected by DRM cannot be sent to your Kindle via personal document services." Size cap: STK email rejects > 50 MB; web uploader (send.amazon.com) rejects > 200 MB. Malformed: STK's strict XHTML/manifest/encoding validation produces a conversion-error response (the existence of the community "Kindle EPUB Fix" tool is direct evidence). *(See origin Deferred to Planning item 5.)*
- **Hero image: phone shot of EPUB→KFX in Kindle library** at `web_service/frontend/public/guides/does-kindle-support-epub/hero.jpg`. Captures the actual end-user experience the page describes. **Path-location supersedes the origin doc's R8 reference to `/quality/*.png`** — the canonical convention is per `docs/solutions/best-practices/pillar-page-screenshots-2026-05-15.md`: pillar-page screenshots live at `web_service/frontend/public/guides/<slug>/`, JPG quality 90, Next.js `Image` handles optimization. The `/quality/` directory contains only PDF-pipeline-themed assets and has no EPUB-on-Kindle precedent. *(See origin R8 — supersession noted during plan review, coherence F1, conf 0.92.)* If a phone shot is unavailable at Unit 1 capture time, **do NOT use a screenshot of `send.amazon.com`** (positions leafbind below Amazon's UI rather than alongside it — PL-5 product-lens finding, conf 0.74). Instead, reuse an existing leafbind-branded illustration from the design system as the stopgap, and file the follow-up ticket to replace with the phone shot post-merge.
- **CTA layout: Unit 2 pain-pillar pattern.** CTA at bottom of page, with one inline CTA mid-page near FAQ start (mirrors Unit 2). The brainstorm's "above the fold" phrasing is reinterpreted: the page leads with the honest answer (E-E-A-T integrity), and the CTA appears at the natural conversion moment after the user has read the failure-mode enumeration.
- **Reciprocal links deferred.** R6 outbound links ship in this PR; inbound from Unit 3 + Unit 5 ship in a separate ~5-min follow-up ticket filed in Unit 6. Avoids interfering with active EB-292 recovery-rail measurement windows on the Phase 2 pages.
- **No Parallelization Map.** Single-stream build; INFRA-216 pilot scope explicitly requires the Map only for plans that execute through the subagent swarm, which a single-page build does not need.

## Open Questions

### Resolved During Planning

- Word count → 1,400-1,700 (intent-driven, not precedent-driven).
- FAQ ordering → intent grouping.
- CTA copy approach → explicit free-vs-premium.
- R4 verifiable signals → use Amazon's STK error message strings.
- Hero image → phone shot of EPUB→KFX in Kindle library; stopgap-then-replace if not capturable in Unit 1.

### Deferred to Implementation

- **Exact slug ordering in sitemap.ts and llms.txt.** Resolve by reading the most recent Phase 2 PR diff that added a guide — match the existing convention (alphabetical or chronological by `lastModified`).
- **Exact anchor text for R6 outbound links from the new page to Unit 3 + Unit 5.** Pick during page-writing to optimize for organic click signal in the surrounding sentence context.
- **Exact LCP element** (likely the hero image — set `priority` on `Image` if so).
- **15-min Top-3 SERP read** (Unit 1 pre-flight) — calibrates whether to push the page closer to 1,400 or 1,700 words based on incumbent depth on `can kindle read epub` and `epub format to kindle`.

## Implementation Units

- [ ] **Unit 1: Pre-flight research and hero asset**

**Goal:** Ground content-depth calibration with a 15-min Top-3 SERP read; secure R8 hero image before page writing begins.

**Requirements:** R8 (asset), supports R3/R5 (depth calibration).

**Dependencies:** None.

**Files:**
- Create: `web_service/frontend/public/guides/does-kindle-support-epub/hero.jpg` (JPG, quality 90, target dimensions match Phase 2 hero precedent — check `pillar-page-screenshots-2026-05-15.md`).
- Reference (read-only): `https://www.amazon.com/sendtokindle`, top-3 SERP for `can kindle read epub` / `epub format to kindle` / `does kindle read epub`.

**Approach:**
- 15-min SERP read on the 3 highest-volume target keywords. Note top-3 ranking competitors, their word counts, and whether Amazon help docs saturate the top 5 (the latter is the primary risk to the 60-day ranking gate per origin Success Criteria).
- Capture hero image: phone screenshot of a converted EPUB sitting in a Kindle library, OR desktop screenshot of send.amazon.com upload page. Phone shot is preferred; stopgap to desktop if not capturable in this session.
- Notes documented in `scratch/eb-320-preflight-2026-05-17.md` (gitignored).

**Patterns to follow:** `docs/solutions/best-practices/pillar-page-screenshots-2026-05-15.md` (path convention, quality level).

**Test scenarios:**
- Test expectation: none — pre-flight research + asset prep; no behavioral code.

**Verification:**
- Hero JPG exists at expected path with appropriate dimensions.
- SERP-read notes captured so Unit 2 word-count decision is grounded.
- If a stopgap asset was used, a follow-up ticket is queued for Unit 6 to file.

---

- [ ] **Unit 2: New page implementation**

**Goal:** Ship the new page at `/guides/does-kindle-support-epub` with verified-honest content, intent-grouped FAQ, Article + FAQPage schema, and explicit free-vs-premium CTA framing.

**Requirements:** R1, R2, R3, R4, R5, R5a, R5b, R6 (outbound only), R7, R8, R9.

**Dependencies:** Unit 1 (hero image).

**Files:**
- Create: `web_service/frontend/app/(marketing)/guides/does-kindle-support-epub/page.tsx`
- Reference (read-only): `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx` (canonical CTA layout), `web_service/frontend/app/(marketing)/guides/how-to-send-pdf-to-kindle/page.tsx` (depth precedent).

**Approach:**
- H1: "Does Kindle Support EPUB?" or tight semantic equivalent (≤ 60 chars total page title for meta).
- Lede (first 300 words): honest answer per R3 using verified facts. Cite Amazon's official STK help page (nodeId G5WYD9SAF7PGXRNA) inline. Reframe the user's mental model: "Kindle accepts EPUB via STK and server-side-converts to KFX" — Kindle is *not* a native EPUB reader. **For most users, STK is the recommended path** — say so explicitly. This is the E-E-A-T integrity move.
- **R5a verb-family/nuance H2 sections (2-4 of them, between lede and FAQ):** pick from the candidate list in R5a per Key Technical Decisions ordering. Each section is ~150 words (R5b AIO-eligibility band 134-167), opens with a definitive first sentence using the target phrasing verbatim, and routes the reader to the correct downstream resource (STK for clean-EPUB cases, Calibre for power users, the FAQ section below for capability-question specifics, the CTA for STK-failure subset). **These are framing sections, not workflow tutorials** — do not add step-by-step verb workflows here; that scope belongs to the deferred "How to put EPUB on Kindle" follow-up ticket.
- FAQ section: 8 H3 anchors in intent-grouped order (see Key Technical Decisions). Each H3 answer is 134-167 words (AI Overview eligibility per `eb258-seo-phase1-patterns.md` + R5b) using the target phrasing verbatim in the first sentence. Answers should be genuinely helpful to EPUB-seekers — accurate, complete, and pointing to the right tool for the user's situation (often STK or Calibre, not leafbind).
- 2 of the 8 FAQ answers contain inline outbound links: one to `/convert/pdf-to-kfx`, one to `/guides/how-to-send-pdf-to-kindle`. **Anchor text frames the link as cross-sell to leafbind's actual strength (PDF conversion that succeeds where other tools fail), not as in-page EPUB conversion.** Natural sentence context, not keyword-stuffed.
- CTA block (positioned per Unit 2 pattern — bottom of page + one inline mid-page near FAQ start): **informational + brand-cross-sell, NOT a primary EPUB conversion pitch**. The CTA should:
  1. Acknowledge STK/Calibre as legitimate paths for clean EPUB-to-Kindle workflows (no FUD, no overselling).
  2. Briefly mention leafbind as one option for the small STK-failure subset (oversize, malformed) for users who prefer a hosted web tool over installing Calibre locally — honest about the 100 MB cap, no DRM stripping, standard Calibre tolerance.
  3. Plant the brand soft-pitch: "We're built for PDF→Kindle conversions where other tools fail — column-aware extraction, heading detection, footnote linking. Try us when your next PDF won't behave." This is the cross-sell into leafbind's actual product-market fit.
  - CTA copy MUST NOT invent EPUB-specific premium magic. The page's job is brand integrity + introduction, not EPUB-segment conversion.
- JsonLd injection: Article + FAQPage via existing `JsonLd` component; Article schema includes `image` field pointing at hero.jpg.
- Metadata: title ≤ 60 chars, meta description 145-160 chars, canonical to apex URL, og:image = hero.jpg, og:type = article.
- Hero image rendered via `next/image` with `priority` if it's the LCP element.

**Execution note:** Drafting order is content-first, then schema. Write the 8 FAQ answers in raw prose against the verified STK facts BEFORE wiring JsonLd, so schema doesn't ossify drafts mid-edit.

**Patterns to follow:**
- Unit 2 pain pillar (canonical CTA + section dividers).
- JsonLd component usage from any existing Phase 2 page (e.g., `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx`).
- EB-269 a11y baseline: 44px touch targets, focus order, aria-labels, skip-link inheritance.

**Test scenarios:**
- *Happy path:* Page renders at `/guides/does-kindle-support-epub` with title, lede, 8 FAQs visible; Article + FAQPage JSON-LD parse to valid objects (Article has `image`, `headline`, `datePublished`, `mainEntityOfPage`; FAQPage has `mainEntity` array with 8 Question/Answer pairs).
- *Edge case:* With JavaScript disabled, page content and JSON-LD blocks remain visible (SSR / static rendering — Next.js App Router default).
- *Integration:* Outbound inline link to `/convert/pdf-to-kfx` resolves to active converter page (200 response); outbound link to `/guides/how-to-send-pdf-to-kindle` resolves to active mega-guide (200 response).
- *Accessibility (EB-269 baseline):* Interactive elements ≥ 44px touch target on mobile breakpoint; focus order follows visual reading order (skip-link → H1 → lede → FAQ H3s in order → CTA → footer); CTA button has accessible label; FAQ H3 anchors are natively focusable; meta `<title>` ≤ 60 chars and meta description 145-160 chars (snapshot test).
- *Error path:* If hero.jpg is missing at build, the build fails fast (do not ship a page with a broken `image` field in Article schema).

**Verification:**
- Page renders locally via `npm run dev` at the expected URL.
- Visual approval against Unit 2 (`send-to-kindle-not-working`) layout precedent — section dividers, CTA placement, FAQ spacing.
- Inline `JSON.parse()` on each `<script type="application/ld+json">` block succeeds with no exceptions.

---

- [ ] **Unit 3: Site-navigation IA updates (R14)**

**Goal:** Make the new page discoverable from the Footer Guides column and the `/guides` hub. Without these, the page is invisible in site nav and the link-check gate (R13) cannot catch the gap.

**Requirements:** R14.

**Dependencies:** Unit 2 (the page must exist for the link target to resolve).

**Files:**
- Modify: `web_service/frontend/components/Footer.tsx` — add entry to Guides column array.
- Modify: `web_service/frontend/app/(marketing)/guides/page.tsx` — add entry to the guides array so the hub lists it.

**Approach:**
- Inspect the most recent Phase 2 PR that added a guide (PR #126 / EB-296 is a strong candidate — added the /guides hub and footer Guides column). Match the data shape (title, href, optional description).
- Insertion position: match the existing ordering convention. If alphabetical by title, insert at correct alphabetical position. If chronological by `lastModified` (more likely given the existing Phase 2 release order), insert at the head.

**Patterns to follow:** PR #126 diff for Footer.tsx and `web_service/frontend/app/(marketing)/guides/page.tsx`.

**Test scenarios:**
- *Happy path:* Footer Guides column on any rendered page shows the new entry with correct href `/guides/does-kindle-support-epub`. `/guides` hub lists the new entry with title + description.
- *Edge case:* New entry preserves the existing alphabetical or chronological ordering convention (snapshot or regex check on the array order).
- *Integration:* `web_service/frontend/tools/check-internal-links.mjs` passes — the href resolves to the newly created page.tsx.

**Verification:**
- Visual confirmation on `/guides` hub page that the new entry is listed.
- Visual confirmation in the footer of any page that the Guides column includes the new entry.
- Link-check CI passes on the PR.

---

- [ ] **Unit 4: Same-PR hygiene wiring (sitemap, llms.txt)**

**Goal:** Ship the sitemap entry and `/llms.txt` entry alongside the page per EB-295 same-PR policy.

**Requirements:** R10, R11, R12, R13.

**Dependencies:** Unit 2 (page must exist for sitemap.ts to reference a real path).

**Files:**
- Modify: `web_service/frontend/app/sitemap.ts` — add new entry following the `new Date("YYYY-MM-DD")` literal pattern, using the merge-day ISO date.
- Modify: `web_service/frontend/public/llms.txt` (resolve exact path during implementation — likely under `public/`).

**Approach:**
- sitemap.ts: Add entry block matching the existing per-entry style. Path `/guides/does-kindle-support-epub`. `lastModified: new Date("2026-05-17")` (or merge-day date). `changeFrequency` + `priority` per Phase 2 precedent values for guide pages.
- llms.txt: Add a single line (or block, depending on existing format) describing the new page. Ordering convention from existing entries.
- Ordering in both files: alphabetical or chronological — match the convention of the most recent Phase 2 PR that added a guide.

**Patterns to follow:**
- The most recent Phase 2 PR that added a guide entry to sitemap.ts + llms.txt (likely PR #126).
- `web_service/frontend/app/sitemap.ts` header comment block (EB-295 codified the no-`new Date()` convention there).

**Test scenarios:**
- *Happy path:* `grep "does-kindle-support-epub" web_service/frontend/app/sitemap.ts` returns the new entry. `grep "does-kindle-support-epub" web_service/frontend/public/llms.txt` returns the new entry.
- *Edge case:* `sitemap.ts` still type-checks (Next.js `MetadataRoute.Sitemap` type expects `Date | string` for `lastModified` — `new Date("2026-05-17")` is `Date`).
- *Integration:* Link-check gate (R13 / `web_service/frontend/tools/check-internal-links.mjs`) passes — confirms the sitemap href and the new page both exist.

**Verification:**
- Both files contain new entries; greps return hits.
- `npm run build` succeeds with the updated sitemap.ts.
- Link-check CI passes.

---

- [ ] **Unit 5: Pre-merge verification gates**

**Goal:** Validate the page ships clean before merge. Catch the Next.js 16 + Turbopack JSON-LD script-tag merging gotcha and the schema-validator Playwright headless quirk before they cause a phantom rollback.

**Requirements:** Indexing (Success Criteria primary), Rich Results, R13, accessibility.

**Dependencies:** Units 2, 3, 4.

**Files:**
- Reference (read-only): `web_service/frontend/tools/check-internal-links.mjs`.
- Reference (read-only): `docs/solutions/best-practices/jsonld-script-tag-count-build-instability-2026-05-14.md`, `docs/solutions/best-practices/schema-validator-playwright-headless-quirk-2026-05-14.md`.

**Approach:**
- **Schema validation (2-layer pattern per `schema-validator-playwright-headless-quirk` solution):**
  - Layer 1: Single Playwright capture of Google Rich Results Test result for `https://leafbind.io/guides/does-kindle-support-epub` (will be a preview URL pre-merge — use the Vercel preview deployment) as visual proof.
  - Layer 2: HTTP fetch the page, extract every `<script type="application/ld+json">` block, run `JSON.parse` inline, assert exactly one Article and one FAQPage are present in the parsed schema set.
- **`@type` assertion (per `jsonld-script-tag-count-build-instability` solution):** Use `grep -oE '"@type":"[^"]*"' | sort -u` against the rendered HTML — assert that the set contains both `"@type":"Article"` and `"@type":"FAQPage"`. Do NOT assert on the count of `<script>` tags (Next.js 16 + Turbopack may combine them).
- **Link-check:** Run `web_service/frontend/tools/check-internal-links.mjs` on the preview deployment to confirm R13.
- **Local Lighthouse smoke:** `lighthouse https://<preview>/guides/does-kindle-support-epub --output html`. Expected baseline: Performance 71-79, LCP 2.5-3.0s (per `nextjs-16-turbopack-render-blocking-css` + `eb249-ttfb-diagnosis`). Stop-the-line only if Performance < 60 or LCP > 5s.
- **PR-checklist items** (since R10/R11/R12/R14 are reviewer-enforced, not CI-gated — per `docs/solutions/best-practices/...` gap analysis): explicit checkboxes in PR description for "sitemap.ts entry added", "lastModified uses `new Date(\"YYYY-MM-DD\")` literal", "/llms.txt entry added", "Footer.tsx + guides hub entries added".

**Patterns to follow:** the two solution docs cited above are load-bearing for this unit.

**Test scenarios:**
- *Happy path:* `@type` grep returns the set containing Article + FAQPage; Layer-2 HTTP fetch + `JSON.parse` succeeds for both; Playwright screenshot of Rich Results Test shows valid result with no errors.
- *Error path:* If `@type` grep is missing either Article or FAQPage, fail merge — investigate whether Turbopack stripped one schema. If `JSON.parse` throws, fail merge — there is a malformed JSON-LD block.
- *Edge case:* Lighthouse Performance 71-79 / LCP 2.5-3.0s is acceptable per documented Turbopack baseline; only Performance < 60 or LCP > 5s blocks merge.
- *Integration:* `web_service/frontend/tools/check-internal-links.mjs` exits 0 against the preview URL.

**Verification:**
- All assertions in the 2-layer schema validation pattern pass.
- `@type` grep contains both Article and FAQPage.
- Link-check CI green.
- Lighthouse Performance ≥ 60 and LCP ≤ 5s (Turbopack-aware bar).
- PR-checklist all checked for R10/R11/R12/R14.

---

- [ ] **Unit 6: Post-merge verification + follow-up filing**

**Goal:** Confirm production state, file the deferred follow-up tickets, and capture institutional learnings in `docs/solutions/`.

**Requirements:** Conversion attribution wiring (EB-292 captures referrers from `/guides/does-kindle-support-epub`); successor work routed.

**Dependencies:** Unit 5 (PR merged to master and Vercel production alias updated).

**Files:**
- Create: `docs/solutions/best-practices/eb-320-epub-pillar-shipped-2026-05-XX.md` (compound learnings — STK behavior verification methodology, intent-grouped FAQ pattern, free-vs-premium CTA framing).
- Create: `docs/solutions/best-practices/sitemap-llms-footer-conventions-2026-05-XX.md` (fill the gap surfaced by learnings-researcher — capture the empirically-established Phase 2 patterns for sitemap.ts / llms.txt / Footer.tsx / guides-hub IA updates).
- Reference (read-only): `docs/solutions/eb252-next-plausible-next16-compat.md`, `docs/solutions/best-practices/vercel-production-branch-misconfiguration-2026-05-15.md`.

**Approach:**
- **Post-merge production curl-check** per `eb252-next-plausible-next16-compat.md`: `curl https://leafbind.io/guides/does-kindle-support-epub` must return 200; `@type` grep against the response body must contain Article + FAQPage; Plausible analytics script tag must be present in the HTML.
- **Vercel alias confirmation** per `vercel-production-branch-misconfiguration-2026-05-15.md`: `npx vercel ls leafbind` shows a Production row; `npx vercel inspect <prod-url>` confirms the alias moved to the new deployment.
- **EB-292 attribution smoke**: tail the SQLite jobs table or visit a synthetic referrer to confirm `referrer` field captures `/guides/does-kindle-support-epub` correctly.
- **File follow-up tickets** (via Atlassian MCP):
  - `EB-XXX (reciprocal-link follow-up)`: ~5-min ticket to add inbound links from Unit 3 mega-guide and Unit 5 converter pillar to the new page (per origin R6 split decision). Includes anchor-text decisions deferred from EB-320.
  - `EB-XXX (R8 hero replacement)`: only if Unit 1 used a stopgap — ticket to commission/capture the brand illustration.
  - `EB-XXX (sitemap/llms.txt/Footer convention compounding)`: capture the patterns that learnings-researcher flagged as empirically-established but uncompounded.
  - `EB-XXX (Phase 3a LowFruits re-run)`: trigger condition fired — within 14 days of EB-320 merge regardless of ranking outcome, per origin Scope Boundaries deferral.
- **`ce:compound` write the two solution docs** filling the documented gaps.

**Patterns to follow:** `eb252-next-plausible-next16-compat.md` curl recipe; `vercel-production-branch-misconfiguration-2026-05-15.md` alias-check recipe.

**Test scenarios:**
- Test expectation: verification + administrative — no new behavioral code.

**Verification:**
- Production curl returns 200, schema, and Plausible.
- `vercel ls leafbind` shows Production row pointing at the merged commit.
- All four follow-up tickets filed and linked back to EB-320 ("Relates" or "Follows").
- Both compound solution docs landed in `docs/solutions/`.

## System-Wide Impact

- **Interaction graph.** The new page links out to `/convert/pdf-to-kfx` and `/guides/how-to-send-pdf-to-kindle`. No callbacks, middleware, or runtime observers. The Footer + guides-hub edits propagate the new entry to every rendered page (small surface, low risk).
- **Error propagation.** N/A — static page, no runtime errors to propagate beyond build-time schema/link-check failures (handled in Unit 5 gates).
- **State lifecycle risks.** The hero image is a static asset; sitemap.ts uses static `Date("YYYY-MM-DD")` literal so build outputs are deterministic across builds (no `new Date()` non-determinism per EB-295).
- **API surface parity.** This is a content surface, not an API surface. No public type or endpoint changes.
- **Integration coverage.** Cross-layer scenarios unit tests will not prove on their own: (a) JsonLd component injection into App Router `<head>` actually renders parseable JSON-LD in the final HTML — covered by Unit 5 Layer-2 HTTP fetch + JSON.parse; (b) EB-292 recovery-rail referrer capture for `/guides/*` URLs — covered by Unit 6 attribution smoke.
- **Unchanged invariants.** Phase 2 pages (Unit 2/3/4/5) are NOT modified by this PR. R6 inbound links are deferred to a follow-up ticket precisely to preserve those pages' content stability during any in-flight Phase 2 measurement windows. The converter UI (`UploadZone`, `FormatSelector`) is NOT modified — the free-tier EPUB→EPUB no-op behavior is unchanged; the CTA copy honestly discloses it so users land in the converter with correct expectations.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Top-50 ranking gate at 60 days not met because Amazon help docs saturate the SERP | Unit 1 SERP read identifies this risk pre-write; origin Success Criteria names this exact failure mode for honest post-mortem. Stretch gate at 120 days. |
| Hero image not capturable in Unit 1 (no Kindle device available, etc.) | Stopgap with desktop screenshot of `send.amazon.com`; file replacement ticket in Unit 6. |
| Free-tier EPUB→EPUB user-trap if CTA copy isn't explicit enough | R4 + Key Technical Decisions mandate explicit free-vs-premium copy. Unit 5 PR-checklist confirms the copy mentions both tiers. |
| Next.js 16 + Turbopack merges Article + FAQPage into a single `<script>` tag, breaking naive count-based schema assertions | Unit 5 uses `@type` occurrence grep, not `<script>` count, per `jsonld-script-tag-count-build-instability-2026-05-14.md`. |
| Schema-validator Playwright headless quirk produces false-negative panic mid-Unit-5 | Unit 5 uses the 2-layer pattern: single Playwright capture + HTTP fetch + JSON.parse for the rest, per `schema-validator-playwright-headless-quirk-2026-05-14.md`. |
| `npm run build` failure on Vercel preview from missing hero.jpg or stale image reference | Unit 1 captures the image before Unit 2 begins; build-time check on `image` field is implicit. |
| EB-292 recovery-rail attribution is path-scoped and misses `/guides/*` referrers | Unit 6 attribution smoke explicitly verifies referrer capture for the new path. If it fails, file a fix ticket on EB-292 instrumentation before Phase 3b decisions rely on the data. |
| Footer/guides-hub array ordering breaks an unstated convention | Unit 3 inspects the most recent Phase 2 PR (likely PR #126) for the convention before inserting. |
| `lastModified` non-determinism if the implementer uses `new Date()` instead of `new Date("YYYY-MM-DD")` | R11 is explicit; Unit 5 PR-checklist requires confirmation. |

## Documentation / Operational Notes

- **Pre-deploy:** Unit 5 PR description must list R10/R11/R12/R14 as explicit checkboxes since these are reviewer-enforced policies, not CI-gated (per gap surfaced by document-review).
- **Post-deploy:** Unit 6 runs curl-verify + vercel alias-check before declaring shipped. Do not trust the green PR check alone.
- **Phase 3a trigger:** Phase 3a LowFruits re-run on the 104k/mo `send to kindle` Related cluster fires within 14 days of EB-320 merge regardless of EB-320 ranking outcome (per origin Scope Boundaries deferral).
- **Compound after merge:** Two new `docs/solutions/` entries land in Unit 6 to fill the gaps surfaced by learnings-researcher (sitemap/llms.txt/Footer conventions + EB-320 STK-verification methodology).

## Sources & References

- **Origin document:** `docs/brainstorms/2026-05-17-eb-320-phase3-epub-pillar-requirements.md`
- **Parent ticket:** EB-241 (Phase 2 — shipped); **This ticket:** EB-320
- **Primary input docs:**
  - `docs/seo/eb-241-phase2-lowfruits-triage.md` (Unit 9 LowFruits triage)
  - `docs/seo/eb-241-semrush-trial-sprint-2026-05.md` (EB-308 Session 2 — EPUB cluster discovery)
- **Phase 2 page precedents:**
  - `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx` (Unit 2 pain pillar — canonical CTA layout)
  - `web_service/frontend/app/(marketing)/guides/how-to-send-pdf-to-kindle/page.tsx` (Unit 3 mega-guide — depth)
  - `web_service/frontend/app/(marketing)/convert/pdf-to-kfx/page.tsx` (Unit 5 converter pillar — R6 outbound target)
  - `web_service/frontend/app/(marketing)/guides/kindle-scribe-vs-remarkable/page.tsx` (Unit 4 comparison hub — FAQ precedent)
- **Hygiene infrastructure:**
  - `web_service/frontend/app/sitemap.ts` (EB-295 `new Date("YYYY-MM-DD")` convention)
  - `web_service/frontend/components/Footer.tsx` (Guides column)
  - `web_service/frontend/app/(marketing)/guides/page.tsx` (guides hub)
  - `web_service/frontend/tools/check-internal-links.mjs` (link-check CI gate — PR #122 / commit `5e6777b`)
- **Institutional learnings (load-bearing):**
  - `docs/solutions/best-practices/jsonld-script-tag-count-build-instability-2026-05-14.md`
  - `docs/solutions/best-practices/schema-validator-playwright-headless-quirk-2026-05-14.md`
  - `docs/solutions/best-practices/pillar-page-screenshots-2026-05-15.md`
  - `docs/solutions/eb258-seo-phase1-patterns.md`
  - `docs/solutions/eb252-next-plausible-next16-compat.md`
  - `docs/solutions/best-practices/vercel-production-branch-misconfiguration-2026-05-15.md`
  - `docs/solutions/best-practices/nextjs-16-turbopack-render-blocking-css-2026-05-14.md`
  - `docs/solutions/eb249-ttfb-diagnosis-2026-05-15.md`
  - `docs/solutions/eb233-design-system-decisions.md`
- **External (verified primary source for R3 content):** Amazon "Send PDF, EPUB and Other Files to Your Kindle" help article (nodeId G5WYD9SAF7PGXRNA), accessed 2026-05-17 via the brainstorm-phase fact-check agent.
- **Recent related PRs:** #117, #119, #120, #121, #122 (EB-295 reviewer-fix infrastructure), #126 (EB-296 footer/guides-hub precedent), #127, #129.
