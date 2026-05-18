---
date: 2026-05-17
topic: eb-320-phase3-epub-pillar
status: ready-for-planning
ticket: EB-320
parent: EB-241 (Phase 2 — shipped)
inputs:
  - docs/seo/eb-241-phase2-lowfruits-triage.md (Unit 9, 2026-05-17)
  - docs/seo/eb-241-semrush-trial-sprint-2026-05.md (EB-308 Session 2, 2026-05-17)
---

# EB-320 Phase 3 — EPUB-on-Kindle Pillar Page

## Problem Frame

The EB-308 Semrush trial sprint surfaced an unmapped EPUB-direction keyword cluster
that leafbind already has the product capability to serve but currently has zero
content for. Eight informational keywords with a combined US volume of **~6,520/mo**
in a direction where leafbind has working EPUB ingestion. The cluster's CPC averages
~$7 across the eight keywords (peak **$14.12** on `does kindle support epub`) — a
useful commercial-intent indicator, though a single Semrush trial value on a
low-volume informational keyword should be treated as supporting evidence, not the
headline argument. The headline argument is the capability gap: zero content on a
direction the product already serves:

| Keyword | Vol | CPC |
|---|---|---|
| can kindle read epub | 1,300 | $8.56 |
| epub format to kindle | 1,300 | $3.54 |
| does kindle read epub | 1,000 | $8.56 |
| does kindle take epub | 880 | $8.56 |
| epub format on kindle | 880 | $3.54 |
| can kindle use epub | 720 | $8.56 |
| does kindle read epub format | 720 | $8.56 |
| does kindle support epub | 720 | $14.12 |

Phase 1's seed-based keyword research never surfaced this cluster — it was found
only by running `phrase_related` on the broader `send to kindle` anchor in EB-308
Session 2. Phase 2 shipped seven content pages on PDF-direction conversion; none
target EPUB. leafbind already accepts EPUB inputs (per the project CLAUDE.md
pipeline architecture line). The content is missing, not the capability.

Context for readers unfamiliar with the Phase 2 unit structure: EB-241 Phase 2
shipped seven content pages organized as Units 1-9. References to specific units
below mean: Unit 2 = pain pillar `/guides/send-to-kindle-not-working`, Unit 3 =
mega-guide `/guides/how-to-send-pdf-to-kindle`, Unit 4 = comparison hub
`/guides/kindle-scribe-vs-remarkable`, Unit 5 = converter pillar `/convert/pdf-to-kfx`.
Unit 9 was the LowFruits triage (`docs/seo/eb-241-phase2-lowfruits-triage.md`)
that mapped FAQ-extension candidates and the larger ~104k/mo send-to-kindle
Related cluster; EB-320 scopes only a single pillar page and defers those
follow-ups to Phase 3b+ tickets.

The cluster's intent is **5-of-8 informational** ("does/can kindle read/use/support
epub") and **3-of-8 positional** ("epub format on/to kindle"). None are action-led.
The natural shape is a single info-led pillar page under `/guides/` — mirroring
Unit 2's pain-pillar pattern (`/guides/send-to-kindle-not-working`) — with the
eight target keywords surfaced as FAQ H3 anchors so Google's intent classifier
can attribute traffic to specific phrasings.

## Requirements

**Page surface**
- R1. New page at `/guides/does-kindle-support-epub` — single dedicated URL, no sub-paths.
- R2. H1 directly answers the headline keyword: "Does Kindle support EPUB?" or a tight semantic equivalent.
- R3. First 300 words deliver the verified honest answer: **For most users, Send-to-Kindle is the recommended path.** STK accepts EPUB and converts it server-side to KFX (modern devices) or KF8/AZW3 (older firmware). STK launched EPUB ingestion in May 2022 (email) / November 2022 (web uploader at send.amazon.com). MOBI fully sunset Dec 20, 2023. Current STK accepts EPUB + PDF + DOC/DOCX + TXT + RTF + HTM/HTML + PNG/JPG/GIF/BMP. STK caps: 50 MB email / 200 MB web. **Important nuance:** Kindle is *not* a native EPUB reader — STK converts server-side. The page's job is to (a) explain this honestly, (b) name the cases where STK fails, and (c) honestly position leafbind as ONE alternative — without overselling capability that doesn't exist (per PL-2 plan-review verification 2026-05-17, see Dependencies / Assumptions).
- R4. CTA block (Phase 2 layout convention, Unit 2 pain pillar `/guides/send-to-kindle-not-working` canonical reference) **honestly positions leafbind as a hosted Calibre + KFX Output plugin workflow with web upload — no local install required**. This is the verified actual value prop (per the 2026-05-17 PL-2 audit against `web_service/`, `tools/`): leafbind has no EPUB-specific premium capability, but Calibre + KFX Output plugin requires non-trivial local setup, and leafbind packages that workflow as a web service with pay-per-use. The CTA pitch: when STK rejects your file (DRM, > 50 MB email cap, malformed EPUB, mixed-format archive) AND you don't want to install Calibre + the KFX Output plugin locally, leafbind runs that workflow in the browser. **The CTA must disclose leafbind's limits honestly**: free tier returns EPUB output (direct Calibre passthrough); premium returns KFX (Calibre + KFX Output plugin); 100 MB cap on premium — **smaller than STK web's 200 MB, disclose this**; no DRM stripping (same as STK and same as running Calibre yourself); standard Calibre tolerance for malformed EPUBs (no leafbind-specific repair logic). The CTA must NOT invent EPUB-specific premium magic. Each STK failure mode must be paired with a verifiable user-diagnosable signal so the CTA does not read as generic upsell. **CTA copy must not mislead about free-vs-premium output gating** — the free tier returns EPUB-to-EPUB (a no-op for users wanting KFX); KFX output requires premium credits.

**Keyword coverage**
- R5. FAQ section covers all 8 EPUB cluster keywords from the Problem Frame table as explicit H3 anchors. Each H3 contains a 2-4 sentence answer that uses the target phrasing verbatim in the first sentence.
- R6. At least two of the FAQ answers contain inline-text links **out** to existing Phase 2 pages: the PDF converter pillar (`/convert/pdf-to-kfx`) and the mega-guide (`/guides/how-to-send-pdf-to-kindle`). **Reciprocal inbound links from Unit 3 and Unit 5 are explicitly out of scope for this PR** (resolved 2026-05-17 brainstorm: three reviewers flagged in-PR Unit 3+Unit 5 edits as scope-incompatible with "single page, one PR" framing and as risking interference with active Phase 2 experiments). A separate 5-minute follow-up ticket adds the inbound links post-merge once this page's content is stable.

**Schema and metadata**
- R7. Page emits valid Article + FAQPage JSON-LD schema, validated against Google's Rich Results Test before merge.
- R8. Article schema includes the required `image` field per the EB-272 reviewer-finding policy. Image asset is a leafbind-branded illustration referenced from the existing `/quality/*.png` location pattern.
- R9. Page metadata follows the EB-275 brand-casing policy and EB-263 on-page-SEO precedent: title ≤ 60 chars, meta description 145-160 chars, OG image set, canonical URL points to the apex (`https://leafbind.io/guides/does-kindle-support-epub`).

**Phase 2 hygiene policies (inherited from EB-295)**
- R10. Sitemap entry for the new page lands in the **same PR** as the page (every-page-PR-ships-own-sitemap-entry).
- R11. `lastModified` uses the existing per-entry `new Date("YYYY-MM-DD")` literal pattern from `web_service/frontend/app/sitemap.ts` (no parameterless `new Date()`, no raw ISO string). Pick the merge-day ISO date at planning time.
- R12. `/llms.txt` updated with a new entry for the page in the same PR.
- R13. Link-check gate passes in CI.
- R14. **Site-nav inbound links updated in the same PR**: (a) `web_service/frontend/components/Footer.tsx` Guides column gains a new entry for `/guides/does-kindle-support-epub`; (b) the guides array in `web_service/frontend/app/(marketing)/guides/page.tsx` gains the new entry so the `/guides` hub lists it. Without these, the page is invisible in site navigation; the link-check gate (R13) detects only broken outbound links, not missing inbound links from footer/hub.

## Success Criteria

- **Indexing.** Page is indexed by Google within 14 days of merge (confirmed via Search Console URL Inspection).
- **Rich results.** Article and FAQPage rich results both pass Google's Rich Results Test on day-of-merge.
- **Ranking gate, primary (60 days post-merge).** Page ranks in the **top 50 for at least 3 of the 8 target keywords**. This is the indexed-and-discoverable bar — realistic for a 2-month-old domain (leafbind.io registered 2026-05-13) competing on $5+ CPC commercial keywords against entrenched competitors (Amazon help documentation and incumbent SEO sites).
- **Ranking gate, stretch (120 days post-merge).** Page ranks in the **top 20 for at least 3 of the 8 target keywords**. This is the original target deferred to the 120-day window where it is achievable rather than aspirational.
- **Conversion attribution is a bonus, not the primary bar.** Per user-supplied product context (2026-05-17), this page targets EPUB-seekers who mostly do NOT have a leafbind-fit problem — Calibre and STK handle their case natively. The conversion thesis is not "this EPUB user buys credits" but **brand recognition for their eventual PDF problem**. Interpret EB-292 attribution accordingly:
  - **Direct EPUB-page conversions (60 days)** — expected near-zero. Non-zero is a bonus signal that the honest framing surfaced a leafbind-fit case correctly.
  - **Delayed PDF cross-sell (120-180 days)** — the real hypothesis: returning visitors who first landed via `/guides/does-kindle-support-epub` and later convert on a `/convert/pdf-to-kfx` job. Requires referrer-chain analysis beyond simple last-touch attribution; flag as a Phase 3b analytics question if EB-292 instrumentation doesn't support it natively.
- **Failure mode named in advance.** If the page indexes but ranks below top-50 on all 8 keywords at 60 days, the most likely cause is SERP saturation by Amazon help documentation and incumbent sites — not page quality. The post-mortem must distinguish "bar was wrong" from "page was wrong" before pulling forward into Phase 3b planning. **Zero direct conversions in 60 days is NOT a failure signal** — it is the expected outcome given the honest informational framing. The real failure signal would be zero downstream PDF conversions from EPUB-page referrers over a longer window (120-180 days).

## Scope Boundaries

Each non-goal below is a deliberate exclusion, not an oversight:

- **No Phase 3a LowFruits re-run.** The send-to-kindle Related cluster (~104k/mo) discovery from Unit 9 is real but requires a 30-minute manual LowFruits browser session + SERP-scoring before page-targeting decisions can be made. Deferred to a future Phase 3b ticket.
- **No FAQ extensions to other Phase 2 pages.** The Unit 3 mega-guide, Unit 5 converter pillar, and Unit 2 pain pillar all have FAQ-extension candidates identified in the Unit 9 LowFruits triage doc. All deferred.
- **No new pages other than the EPUB pillar.** Specifically excluded: `/guides/can-kindle-read-pdf` (1,030/mo), `/convert/epub-to-kfx` (50+/mo), the kindle-scribe-academic-papers cluster (~40/mo). All defensible Phase 3b candidates.
- **No Phase 2 audit work.** Unit 5 eat-the-bounce position audit, Unit 5 content-depth audit vs pdf2kindle.com, Unit 3 lexical-variant audit against `phrase-questions-pdf-to-kindle.csv` — all flagged in EB-308 but deferred. Each warrants its own follow-up ticket.
- **No Semrush Position Tracking setup.** Manual Joe action (~10 min in Semrush web UI), tracked separately. Not blocking for the page build.
- **No backlink outreach.** Phase 4 territory (EB-309 future scope).
- **No reverse-direction (Kindle → EPUB) content.** Out of leafbind's core direction. The 2,900/mo `epub to epub converter` Related keyword is similarly out of scope.

## Key Decisions

- **`/guides/` URL prefix over `/convert/`.** Keyword intent is informational (5-of-8 are Q-form, "does/can kindle..."). The pain-pillar pattern (Unit 2 `/guides/send-to-kindle-not-working`) is the closest semantic precedent.
- **Single page over a cluster of mini-pages.** Per the Unit 3 mega-guide precedent and the EB-308 methodology learning (lexical-variant diversity rewards depth, not multiplication of thin pages), one pillar with FAQ H3 anchors per keyword is the higher-EV shape.
- **Informational + brand cross-sell framing, not an EPUB-conversion pitch.** Final repositioning (2026-05-17, after user-supplied product context). The PL-2 codebase audit established that leafbind has no EPUB-specific premium capability. The user's clarification then went further: **EPUB conversion is not even a leafbind selling point** — Calibre handles EPUB→KFX natively without issue, STK handles EPUB→Kindle server-side without issue, and EPUB and other non-PDF inputs are convenience features in the pipeline rather than the marketed value prop. **leafbind's actual selling point is PDF conversion for users whose PDFs failed in other tools** (column-aware extraction, font-size heading detection, footnote linking, Gemini OCR remediation — all PDF-shaped because PDF→KFX is the genuinely hard problem). The EB-320 page therefore exists as **honest informational content with brand-introduction + cross-sell-to-PDF-flow value**, not as a primary EPUB conversion play. Users finding the page learn the honest STK/Calibre answer for their EPUB question, and leave with leafbind planted as a helpful brand to remember for their next PDF problem. E-E-A-T integrity > conversion-rate aspiration; brand-building > one-shot conversion.
- **Tight scope, single page.** Per user direction (2026-05-17 brainstorm): defer Phase 3a re-run, audits, and FAQ extensions to subsequent Phase 3b+ tickets so the parallel EB-45 analytics workstream can advance.

## Dependencies / Assumptions

- **Verified.** leafbind accepts EPUB inputs in production (project CLAUDE.md, pipeline architecture line: `inbox → ... → KFX output`). The Sherlock Holmes / Doyle baseline (EB-217) is an EPUB regression anchor in the test corpus.
- **Verified.** EB-292 recovery-rail measurement instrumentation is live (PR #113, merged 2026-05-16).
- **Verified, with caveat.** EB-272 `image` field policy and EB-295 same-PR sitemap policy are enforced by reviewer-pass discipline plus the dead-link check in `tools/check-internal-links.mjs` (PR #122 / commit `5e6777b`). Caveat: nothing currently CI-fails a `page.tsx` that ships without a matching sitemap entry — the policy is a human gate, not a build gate. The plan must restate the sitemap/llms.txt entries as explicit PR-checklist items so the merge gate is not silently weaker than the policy language implies.
- **Assumption (unverified).** Semrush trial volumes (~6,520/mo cluster total) and the $14.12 CPC peak have not been triangulated against a second source. Semrush CPC on low-volume informational queries is known to be noisy. Before locking the word-count and ranking-gate targets at planning time, spot-check 2-3 of the 8 keywords in LowFruits or Google Keyword Planner, and inspect the live SERP for organic-vs-paid intent split (especially: does Amazon's own help documentation already saturate the top 5 for `does kindle support epub`?).
- **Verified (2026-05-17 brainstorm — fact-check agent against Amazon help + secondary sources).** Send-to-Kindle EPUB ingestion launched May 2022 (email path) and November 2022 (web uploader). MOBI fully sunset December 20, 2023. Current STK accepted set: EPUB, PDF, DOC, DOCX, TXT, RTF, HTM, HTML, PNG, GIF, JPG, JPEG, BMP. Size cap: 50 MB (email) / 200 MB (web). DRM-protected files are rejected (no DRM stripping). Malformed EPUBs are rejected by STK's strict XHTML/manifest/encoding validation. EPUB is converted server-side to KFX (modern) or KF8/AZW3 (older firmware); Kindle is *not* a native EPUB reader. The original R3 phrasing "Kindle natively supports EPUB" was technically inaccurate and has been corrected. Primary source: Amazon's "Send PDF, EPUB and Other Files to Your Kindle" help article (nodeId G5WYD9SAF7PGXRNA).
- **Verified (2026-05-17 ce:plan PL-2 audit — codebase verification agent against `web_service/`, `tools/`).** leafbind has no EPUB-source-specific premium capability. (a) Premium file-size cap is 100 MB (`web_service/config.py:178`) — *smaller* than STK web's 200 MB. (b) Every premium value prop advertised on `web_service/frontend/app/(marketing)/pricing/page.tsx:49-56` is PDF-shaped (column-aware extraction, font-size heading detection, footnote linking, Gemini OCR remediation). (c) There is no DRM detection in `web_service/validation.py`; DRM-protected EPUBs fail silently via Calibre 0-byte output. (d) Premium routes EPUB inputs through `pdf_to_balabolka.py --mode kindle` (`pipeline_runner.py:363-376`), which calls `extract_text_from_epub()` (`pdf_to_balabolka.py:3279`) — flattens EPUB HTML to plain text before Calibre rebuilds structure. Free tier (`run_free` line 250-323) is a direct Calibre passthrough. **Free likely produces structurally better EPUB→KFX output than premium.** Customer-facing bug filed as a separate EB ticket (premium-degrades-EPUB-vs-free). The honest leafbind value for EPUB-input users is "hosted Calibre + KFX Output plugin + web upload + pay-per-use, no install." The page is repositioned around this honest framing.
- **Assumption (revised).** Page write time is ~2-4 days for a solo author given (a) primary-source verification (already done — see verified STK facts above), (b) competitor depth audit on top-3 SERP keywords, (c) 8 distinct FAQ answers without keyword-stuffed phrasing, (d) brand-asset illustration sourcing for R8 (no existing EPUB-themed asset), and (e) Footer/guides-hub edits per R14. Phase 2's 1-2 day velocity precedent assumed templated PDF-direction content with reusable schema, which does not transfer 1:1 to this scope. Mid-write daily checkpoint: day 2 — if primary-source-confirmed outline + R8 asset chosen, on track; otherwise replan.

## Outstanding Questions

### Resolve Before Planning

(none — all product decisions resolved in brainstorm)

### Deferred to Planning

- ~~[Affects R3][Needs research] What is the exact, verified date and current behavior of Amazon's Send-to-Kindle EPUB ingestion?~~ **Resolved 2026-05-17** — see Dependencies / Assumptions block. R3 has been revised with verified facts.
- [Affects R8][Pre-work] Choose or create the leafbind-branded EPUB-on-Kindle illustration **before** writing the page metadata block. This is a brand-asset task, not a copy task, and can slip past the 1-2 day write estimate. Existing `/quality/*.png` is the precedent location but contains only PDF-pipeline-themed assets (pipeline-headings, pipeline-columns, etc.) — no EPUB-on-Kindle asset exists. The plan must add this as an explicit sub-task with its own time box, or pick a stopgap from the existing set and flag the asset-replacement follow-up.
- [Affects R5][Technical] Final word count target — 1,800-2,500 (mega-guide depth) vs 1,200-1,500 (comparison-hub depth). Plan should pick based on competitor depth audit at planning time.
- [Affects R5][Technical] FAQ ordering — by descending volume, by descending CPC, or by intent grouping (does-form first, can-form second, positional last). Pick during planning based on readability.
- ~~[Affects R6][Technical] Specific anchor text for the inbound links from Unit 3 and Unit 5~~ **Moved to a separate follow-up ticket** — reciprocal-link work is out of scope for this PR (resolved 2026-05-17 brainstorm). Anchor-text decisions move to that follow-up ticket.

## Next Steps

→ `/ce:plan EB-320` for structured implementation planning. This is a single-stream build (one page, one PR), so the INFRA-216 Parallelization Map will be lightweight — the Map is required only for plans that execute through the subagent swarm pilot, which a single-page build does not need.
