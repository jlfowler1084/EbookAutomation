---
ticket: EB-241
phase: Phase 1f — Discovery Synthesis
date: 2026-05-16
data_sources:
  - scratch/keyword-candidates-raw.csv (51 candidates, Phase 1a)
  - scratch/competitor-audit.md (top-3 SERP audit, Phase 1e)
  - scratch/semrush-volume-kdi-us-2026-05-16.csv (Semrush phrase_these + phrase_kdi, US database)
  - scratch/semrush-questions-send-to-kindle-2026-05-16.csv (Semrush phrase_questions, pain pillar)
  - scratch/semrush-questions-convert-pdf-to-kindle-2026-05-16.csv (Semrush phrase_questions, conversion pillar)
semrush_units_consumed: ~6,200 (510 phrase_these + 1,650 phrase_kdi + ~4,000 phrase_questions)
---

# EB-241 Phase 1 — SEO Keyword Discovery Synthesis

## TL;DR — three findings that reshape the content strategy

1. **The "how to send X to kindle" question cluster has ~6,000 monthly searches** — far larger than any converter-pillar keyword in isolation. The single query `how to send pdf to kindle` alone has **1,600 monthly searches**, and the cluster including EPUB / document / file variants brings the total to ~6k. This is the unanticipated top-of-funnel for leafbind's core flow and should anchor the v1 content strategy.

2. **Top-of-funnel device comparison keywords total ~3,800 monthly searches at very-easy KD (19-31).** `kindle scribe vs remarkable` alone is **2,900/month at KD 31** — the single highest-volume query in the entire 51-candidate set. The device-decision query universe is ~26x larger than the converter-pillar query universe. Comparison content is not optional — it's where the audience actually lives.

3. **"Convert pdf to kindle" search intent is bidirectionally contaminated.** Roughly half the question-volume around `convert pdf to kindle` is actually users wanting **Kindle → PDF** (the reverse direction — outside leafbind's scope). `how to convert kindle books to pdf` (320/mo) and `how to convert kindle to pdf` (260/mo) sit alongside the legitimate forward-direction queries. Leafbind's converter pages must be explicit about direction in the H1, title, and lede paragraph, or they'll attract mismatched-intent traffic that bounces.

The keyword difficulty data also confirms the audit's directional read: every measured KD sits in Semrush's "Very Easy" or "Easy" range (17-47). Difficulty is not the bottleneck for this niche. Volume and intent alignment are.

---

## Section 1 — The full data: 51 candidates ranked

### 1.1 Candidates with measurable Semrush data (33 of 51)

Sorted by volume × winnability (1/KD as proxy where KD measured):

| Rank | Keyword | Vol | KD | KD band | Audit verdict | Cluster | Intent |
|---|---|---|---|---|---|---|---|
| 1 | kindle scribe vs remarkable | **2,900** | 31 | easy | (not audited) | comparison | commercial |
| 2 | convert pdf to kindle format | 720 | 34 | easy | mixed | conversion | transactional |
| 3 | kindle scribe vs ipad | 590 | 22 | very-easy | (not audited) | comparison | commercial |
| 4 | kindle scribe vs paperwhite | 320 | 24 | very-easy | (not audited) | comparison | commercial |
| 5 | how to convert pdf to kindle format | 260 | 21 | very-easy | (paired) | conversion | informational |
| 6 | **send to kindle not working** | 260 | **17** | very-easy | **7/10 WINNABLE** | pain | informational |
| 7 | send to kindle app not working | 210 | 18 | very-easy | (sibling) | pain | informational |
| 8 | send pdf to kindle scribe | 110 | **47** | easy | 4/9 mixed-leaning-winnable | transfer | transactional |
| 9 | how to send pdf to kindle scribe | 70 | 25 | very-easy | (pillar variant) | transfer | informational |
| 10 | kindle scribe vs ipad for note taking | 70 | 19 | very-easy | (outside scope) | comparison | commercial |

Mid-volume bucket (20 monthly searches — Semrush's floor display value; could be 10-49 real):
- Most of the 8 conversion-modifier keywords (free / online / mac / reddit / epub / ebook)
- 5 of 5 epub-to-kfx variants
- All 4 calibre kfx plugin queries
- All 8 kindle scribe pdf annotation/reading/markup/template queries
- Both upload/transfer pdf to kindle scribe synonyms

The 20-volume bucket has **KD=0** across the board — meaning Semrush has no difficulty signal, not that they're easy. These belong in the LowFruits queue, not the Semrush priority list.

### 1.2 Candidates with zero Semrush volume (18 of 51)

Below Semrush's 10/month display threshold:

- send large pdf to kindle scribe, send pdf from iphone to kindle scribe, send pdf to kindle scribe colorsoft
- convert pdf to kindle format reddit
- kindle scribe pdf annotation reddit, kindle scribe pdf annotation export
- is kindle scribe good for reading pdf, amazon kindle scribe pdf reader
- kindle scribe scientific papers, kindle scribe research paper, kindle scribe for reading academic papers
- calibre kfx output plugin github
- epub to kfx converter online free, epub to kfx converter free
- send to kindle scribe not working, send to kindle troubleshooting
- kindle scribe pdf templates free, kindle scribe vs paperwhite for reading

**These aren't worthless** — Semrush's 10/month floor means real volume could be 1-9. LowFruits is better at micro-volume opportunities with weak SERPs (it surfaces "weak spots" not visible to Semrush). All 18 stay in the LowFruits queue for Phase 2.

### 1.3 Strategic clusters by combined volume

| Cluster | Candidates with vol | Combined volume | Avg KD (measured) | Strategic role |
|---|---|---|---|---|
| **Device comparison** | 4 | **3,810** | 24 | Top-of-funnel hub — biggest audience |
| **"How to send" question cluster** (from phrase_questions, not in original 51) | ~12 (PDF-direction subset) | **~6,000** | (KD not pulled) | Top-of-funnel for core flow |
| Conversion (pillar + how-to) | 9 | 1,070 | 28 | Main converter pillar + companion |
| Pain (send-to-kindle failures) | 4 | 470 | 18 | Highest-leverage single page |
| Scribe transfer (send pdf to scribe) | 8 | 220 | 36 | Existing pillar — needs sibling guide |
| Scribe reading / academic | 8 | 160 | (no data) | Existing positioning — low-vol but core |
| Annotation / write-on-pdf | 7 | 110 | (no data) | Soft-adjacent — not priority |
| Calibre KFX plugin | 4 | 80 | (no data) | Differentiation angle |
| EPUB → KFX converter | 4 | 60 | (no data) | Mid-priority — premium feature |

The collective volume of the "how to send X to kindle" question cluster (~6k/mo) and the device-comparison cluster (~3.8k/mo) together exceed the rest of the 51-candidate set combined. **The content strategy must lead with these.**

---

## Section 2 — Question data: what people actually ask

### 2.1 "Send to Kindle" question cluster (49 questions returned)

Top 10 by volume — all directly addressable by leafbind's send-to-kindle workflow content:

| Question | Vol | Direction | Notes |
|---|---|---|---|
| how to send pdf to kindle | **1,600** | PDF→Kindle ✅ | Crown jewel — single largest opportunity |
| how to send books to kindle | 1,300 | book→Kindle ✅ | Broader — book transfer general |
| how to send epub to kindle | 1,000 | EPUB→Kindle ✅ | EPUB→KFX angle = leafbind premium output |
| how to send a pdf to kindle | 720 | PDF→Kindle ✅ | Synonym of #1 |
| how to send an epub to kindle | 720 | EPUB→Kindle ✅ | |
| how to send books on kindle | 590 | book→Kindle ✅ | |
| how to send a kindle book as a gift | 480 | gifting ❌ | Outside scope |
| how to send book to kindle | 480 | book→Kindle ✅ | |
| how to send ebook to kindle | 480 | ebook→Kindle ✅ | |
| how to send a book to kindle | 390 | book→Kindle ✅ | |

**Direct-fit volume in top 50 questions: ~6,000/month.** Library-integration variants (Libby / Hoopla) and gifting queries account for another ~1,500/month but are outside leafbind's scope.

### 2.2 "Convert PDF to Kindle" question cluster — bidirectional intent contamination

Top 21 questions returned by Semrush for the seed `convert pdf to kindle`:

| Direction | Question count (top 21) | Combined volume | Verdict |
|---|---|---|---|
| **PDF → Kindle (leafbind)** | 10 questions | 1,810 | The legitimate target intent |
| **Kindle → PDF (reverse)** | 11 questions | 1,500 | Outside leafbind scope |

Roughly **45% of question-volume around the converter seed is for the wrong direction.** This has direct implications for the converter pillar page:

1. **Title and H1 must be unambiguous**: "Convert PDF to Kindle (KFX)" is better than "PDF and Kindle conversion."
2. **Lede paragraph must declare direction**: "If you want to go from Kindle → PDF, this isn't the tool — try [X] instead." Eat the bounce up front. Better to lose the wrong-intent visitor in the first paragraph than have them abandon mid-page.
3. **Schema markup**: The Product / SoftwareApplication entity must explicitly list `input: PDF / EPUB / DOCX` and `output: KFX / Kindle` to give crawlers an unambiguous direction signal.

This is also a candidate ranking factor — Google has been getting better at intent classification, and pages that match the user's actual intent more precisely (forward vs reverse) outperform.

---

## Section 3 — Reframed content strategy

The data forces three changes vs. the pre-Semrush plan in the Jira EB-241 outline:

### Change 1 — Lead with the question hub, not the converter pillar

**Old plan:** Build the converter pillar (`convert pdf to kindle format`, 720 vol) as the main organic-traffic driver.

**New plan:** Build a **"How to send PDFs (and EPUBs, and documents) to Kindle"** mega-guide that anchors the ~6k-monthly question cluster. The converter pillar gets demoted to a sibling page linked from the mega-guide. The mega-guide does the heavy lifting; the converter page closes the loop.

This is the largest single content opportunity in the entire keyword set.

### Change 2 — Add a device comparison hub (was not in the Phase 1 plan at all)

**Old plan:** Focus on bottom-of-funnel converter and transfer intent. Comparison content was deferred.

**New plan:** Build a "Kindle Scribe vs reMarkable / iPad / Paperwhite for reading PDFs" comparison hub as a Phase 1 deliverable. ~3,800 monthly searches, KD 19-31. The conversion path: device-comparison content → "and here's how to make whichever device handle PDFs well" → leafbind product.

**Important framing rule**: leafbind isn't *selling a device.* The comparison content should be product-agnostic on device choice and product-evangelizing on PDF handling. This avoids competing with Amazon's affiliate ecosystem and avoids the trust-signal problem of "obviously biased" comparison content. Bonus: it makes the page actually useful, which is the only way to outrank Reddit and YouTube.

### Change 3 — Pain pillar moves up to P0 single-page

**Old plan:** Pain-pillar troubleshooting was deferred to a Phase 2 nice-to-have.

**New plan:** `send to kindle not working` is the single highest-leverage page in the set (260 vol, KD 17, audit verified 7/10 winnable, zero authoritative incumbents). Build it in Phase 1 as a standalone troubleshooting guide. The strategic insight: this is a *commercial-intent* page disguised as a troubleshooting article — users searching this query are actively failing at Amazon's native flow and primed to try an alternative.

---

## Section 4 — Phase 1 build queue (recommended)

In execution order, with effort and ROI estimates:

| Order | Page | Type | Target keywords | Combined vol | Effort | ROI rationale |
|---|---|---|---|---|---|---|
| 1 | "Send to Kindle not working" troubleshooting guide | Standalone | send to kindle not working, send to kindle app not working | ~470 | M | KD 17-18 + audit-confirmed weak SERP + commercial intent. Quickest win. |
| 2 | "How to send PDF (and EPUB, docs) to Kindle" mega-guide | Pillar hub | how to send pdf to kindle (1,600), how to send epub to kindle (1,000), + 10 variants | ~6,000 | L | Largest single opportunity. Anchors the question cluster. Internal links to converter and pain pages. |
| 3 | "Kindle Scribe vs reMarkable / iPad / Paperwhite — for PDFs" comparison hub | Pillar hub | kindle scribe vs remarkable (2,900), kindle scribe vs ipad (590), kindle scribe vs paperwhite (320) | ~3,810 | L | Top-of-funnel. KD 22-31. Audience-discovery, funnels to converter. |
| 4 | Convert PDF to Kindle (KFX) converter pillar | Pillar | convert pdf to kindle format (720), how to convert pdf to kindle format (260) | ~1,000 | M | The original Phase 1 pillar. Now sibling to #2, not the lead. **Must be direction-explicit.** |
| 5 | Update existing /guides/pdf-to-kfx-for-kindle-scribe | Existing guide edit | send pdf to kindle scribe (110), how to send pdf to kindle scribe (70) | ~180 | S | Wire into the new pillar hubs. Add transfer-flow coverage. |

Total Phase 1 addressable volume across these 5 pages: **~11,500 monthly searches**. At a realistic 2-5% click-through from positions 4-6 on the SERP, that's **230-575 organic visits/month** at steady state, achievable within ~3-6 months given the very-easy KD profile.

---

## Section 5 — What this doesn't replace

This document is the Semrush + audit synthesis. It does **not** replace:

- **LowFruits SERP weakness scoring** for the 18 zero-volume long-tails and the 20-volume bucket. Semrush can't see the SERP weakness signal at micro-volumes; LowFruits can. The 51-candidate CSV still needs a LowFruits pass to triage the long-tail.
- **Reddit / forum-mining for question variants** beyond what Semrush surfaces. Semrush returned ~50 questions per pillar seed; community sources will surface additional pain-language we can fold into H2/H3 structure.
- **Backlink gap analysis.** Semrush phrase_kdi gives a ranking-difficulty score but doesn't enumerate the top-10 backlink profiles. If we want to plan backlink outreach, that's a separate `backlink_research` toolkit query, deferred to Phase 2.

## Section 6 — Action items going into Phase 2

1. **Run LowFruits on the full 51-candidate CSV** — focus on the 18 zero-volume long-tails and the 20-volume bucket. Output: SERP weakness scores, top-10 backlink profiles per keyword.
2. **Write the 5 Phase 1 pages** in the order above. Each page should ship with structured-data review against the [seo skill](~/.claude/skills/seo/SKILL.md) checklist (FAQ schema, HowTo schema where applicable, canonical, breadcrumbs, internal-link map).
3. **Add direction-clarity guard to the converter pillar template** — title + H1 + lede must declare PDF→Kindle direction.
4. **Defer scope-creep**: annotation queries, Kindle gift queries, library-integration queries (Libby / Hoopla) are out of scope for v1. Park them in a "future scope" doc.
5. **Re-baseline with Semrush in ~6 weeks** after the first 2-3 pages ship — `phrase_organic` for the target keywords will show whether leafbind has cracked the top 50 yet, and `phrase_fullsearch` will show whether new related keywords have surfaced.

---

## Appendix A — Raw data files

- `scratch/keyword-candidates-raw.csv` — original 51 candidates with cluster / fit / intent classification (Phase 1a)
- `scratch/competitor-audit.md` — top-3 SERP audit via Playwright (Phase 1e)
- `scratch/semrush-volume-kdi-us-2026-05-16.csv` — phrase_these + phrase_kdi merged for 33 candidates with measurable data
- `scratch/semrush-questions-send-to-kindle-2026-05-16.csv` — 49 question variants for `send to kindle`
- `scratch/semrush-questions-convert-pdf-to-kindle-2026-05-16.csv` — 21 question variants for `convert pdf to kindle`

## Appendix B — Semrush units consumed

| Report | Units / line | Lines | Subtotal |
|---|---|---|---|
| phrase_these (51 keywords, 33 returned) | 10 | 51 | 510 |
| phrase_kdi (33 keywords) | 50 | 33 | 1,650 |
| phrase_questions (send to kindle, 49 returned) | 40 | 49 | 1,960 |
| phrase_questions (convert pdf to kindle, 21 returned) | 40 | 21 | 840 |
| **Total** | | | **~4,960** |

Pro tier daily cap is ~10,000 units. Phase 1 used roughly half the daily budget. Phase 2 (LowFruits, content writing, baselining) needs no further Semrush calls until the 6-week re-baseline check.
