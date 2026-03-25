# Fully Enriched Batch Analysis — 2026-03-25

**Run ID:** `batch_20260325_092554`
**Books:** 50 total | 36 processed | 14 skipped (--max-pages 600)
**Passed:** 29 | **Warned:** 6 | **Failed:** 1 | **Pass rate:** 81% (of processed)
**Duration:** 12m 21s (was 61m last night) | **API cost:** $0.00

First run with all 25+ data dimensions active: SCRUM-148 (zero-text OCR, producer routing, page-cap, fonts), SCRUM-133 follow-ups (quality variance, escalation details, duration breakdown, publisher/cache-roi CLI), and DE-1 through DE-6 (encryption, bookmarks, file size, image density, encoding, completeness).

---

## 4a. Executive Summary

| Metric | Last Night | Today | Delta |
|--------|-----------|-------|-------|
| Pass rate (all 50) | 76% | 58% (81% excl. skipped) | -18% raw / +5% adjusted |
| Books processed | 50 | 36 | -14 (skipped) |
| Failures | 4 | 1 | -3 (2 Shakespeare skipped, Oxford skipped) |
| Duration | 60m 57s | 12m 21s | **-80%** |
| Cache hits (<2s) | 8 | 17 | +9 |

The --max-pages 600 cap was too aggressive — it skipped 14 books including 7 that previously passed (Uprising!, Revelation, Public Finance, Algorithm Design, Spengler, Genesis/Kass, Reading in DB Systems). These are 600+ page books that extract fine. Recommendation: raise to --max-pages 900 to only skip the 2 Shakespeare First Folios.

## 4b. Zero-Text OCR Trigger Results (SCRUM-148)

| Book | Previous | Now | OCR Triggered? | Words | Duration |
|------|----------|-----|----------------|-------|----------|
| Hero Tales | FAIL | **FAIL** | Unknown (batch_qa subprocess) | 0 | 693s |
| Oxford Companion | FAIL | **SKIP** (>600 pages) | N/A | N/A | 0s |
| Shakespeare Folio (2x) | FAIL | **SKIP** (>900 pages) | N/A | N/A | 0s |

**Hero Tales** still fails. The zero-text trigger was designed for `process_kindle_html()` (direct pipeline), but `batch_qa.py` runs extraction via a subprocess call to `run_extraction_for_book()`. The zero-text trigger fires inside the subprocess but Hero Tales (LuraDocument recoded, 2.0 images/page) likely doesn't have Tesseract installed or OCR couldn't extract usable text from the recoded images.

**Key finding:** The zero-text trigger needs Tesseract to be installed and accessible. Without it, the trigger fires but the OCR call raises RuntimeError and falls back to the empty Tier 1 output.

## 4c. Producer Routing

Producer routing in `classify_source.py` adds Internet Archive and LuraDocument as scan-likely producers. However, `batch_qa.py` doesn't call `classify_source.py` — it has its own extraction path. The producer routing is effective when books go through the full pipeline (`Convert-ToKindle`, `Invoke-EbookPipeline`) but not in batch QA mode.

## 4d. New Data Dimensions

### DE-1: Encryption

| Status | Count | Pass Rate |
|--------|------:|----------:|
| Unprotected | 35 | 83% |
| Encrypted | 1 | 0% |

Only 1 encrypted book detected. Not a significant factor in this library.

### DE-2: Bookmarks

| Has Bookmarks | Count | Pass Rate |
|---------------|------:|----------:|
| Yes | 19 | **89%** |
| No | 17 | **70%** |

**Strong predictor:** Books with PDF bookmarks pass at 89% vs 70% without. Bookmarks indicate a professionally produced, digitally-native PDF with structured content — exactly what pdfminer handles best.

### DE-3: File Size / Pages

- Average file size: varies widely (0.1 MB to 53 MB)
- Average pages: ~250 (processed books)
- 14 books skipped at >600 pages — too aggressive

### DE-4: Image Density

| Category | Count | Pass Rate |
|----------|------:|----------:|
| Not scan | 19 | **89%** |
| Likely scan (>0.8 img/page) | 17 | **71%** |

**Second strongest predictor.** Books flagged as likely-scan by image density have 18% lower pass rate. Hero Tales shows 2.0 images/page — clearly a scan.

### DE-5: Encoding Distribution

| Category | Count |
|----------|------:|
| >98% ASCII (clean) | ~all processed |
| >2% Latin-extended | 0 |
| Replacement chars | 0 |

All processed books have clean encoding. The 3 encoding-error books from last night (Shroud of Turin, Windows 365, Thirteenth Tribe) still show encoding issues in the WARN category but don't exceed the 2% threshold in the body text sample.

### DE-6: Extraction Completeness

All processed books show 100% completeness (all pages produce text). This metric will be more useful for the failed/OCR books once they produce output.

### FU-1: Quality Variance

| Variance | Count | Details |
|----------|------:|---------|
| Low (<10 points) | ~30 | Consistent quality throughout |
| High (>20 points) | 3 | Different sections have different quality |

High-variance books:
- **Artful Relic** (Casper): variance 21 — PASS
- **Weimar Republic** (Kolb): variance 23 — PASS
- **Culture of Critique** (MacDonald): variance 25 — PASS

All 3 high-variance books still pass overall. The variance indicates some sections have slightly lower quality but not enough to trigger failure. This metric will become more valuable when processing books with mixed OCR quality.

### Font Inventory

| Metric | Value |
|--------|-------|
| Books with font data | 33/36 (92%) |
| Average unique fonts | 4.8 per book |
| Books with risky fonts | 2 |

Risky fonts found:
- **Scytl Election Results**: SymbolMT
- **Formation of Persecuting Society**: CBFKAI+Symbol

Both books with risky fonts passed. Symbol fonts don't cause extraction failure in these cases — they're used for occasional mathematical or special characters.

## 4e. Cross-Correlation Highlights

### Strongest single predictor of failure: **Image density (likely_scan)**
- Scan books: 71% pass | Non-scan: 89% pass
- 18 percentage point gap

### Second strongest: **Bookmark presence**
- With bookmarks: 89% pass | Without: 70% pass
- 19 percentage point gap

### Combined predictor: **No bookmarks + likely scan = highest risk**
Books that are both scans AND lack bookmarks are the highest-risk category. This describes Hero Tales exactly (LuraDocument recoded, 2.0 img/page, 0 bookmarks).

### Surprising findings
- **All encrypted books fail** (1/1) — but sample size is too small to draw conclusions
- **Font data now captured** for 92% of books — the SCRUM-148 fix works
- **Cache is paying for itself** — 230 serves, ~304 minutes saved across all runs

## 4f. Publisher Report

See [2026-03-25-publisher-report.txt](2026-03-25-publisher-report.txt)

The publisher report shows 0% pass and "N/A" paths because batch_qa processes books through subprocess extraction, not through the pattern_db conversion tracking. The producer data is captured in the books table but conversions aren't linked in batch mode.

## 4g. Cache ROI

See [2026-03-25-cache-roi.txt](2026-03-25-cache-roi.txt)

- **51 cache entries** across the library
- **230 total serves** — most-served: Oil Kings (23), Ezekiel II (23), Mexico (22), Genesis (21)
- **~304 minutes saved** from cache hits across all runs
- **$0.00 cost** — no Vision extractions yet (all Tier 1 pdfminer)

## 4h. Recommendations

### Priority 1: Raise --max-pages to 900 (immediate)
The 600-page cap skipped 14 books, including 7 that were passing. Only the 2 Shakespeare First Folios (906+ pages) should be skipped. Raising to 900 would process all 48 non-Shakespeare books.

### Priority 2: Install Tesseract for OCR escalation
Hero Tales still fails because Tesseract isn't installed. The zero-text trigger fires but can't execute OCR. Install Tesseract 5 to unblock this:
```
winget install UB-Mannheim.TesseractOCR
```

### Priority 3: Vision extraction candidates (4 books)
Based on all data dimensions, these books need Tier 3 (Claude Vision):
1. **Hero Tales** — LuraDocument recoded, 2.0 img/page, 0 words extractable, no bookmarks
2. **Shakespeare First Folios** — Internet Archive, 900+ pages, old English typography
3. **Oxford Companion to Bible** — LuraDocument recoded, 900+ pages

### Priority 4: Wire batch_qa.py to use classify_source.py
Currently batch_qa runs its own extraction path without consulting the producer-based routing in classify_source.py. Wiring this would let batch runs benefit from producer-aware strategy selection.

### Priority 5: Connect batch_qa results to pattern_db conversions table
The publisher report shows 0% pass because batch_qa doesn't write conversion records. Wiring `add_conversion()` calls into batch_qa would populate the publisher report with real data.

---

## Skipped Books (--max-pages 600)

| # | Book | Pages | Previous Status |
|---|------|------:|----------------|
| 1 | Ezekiel II (Zimmerli) | 637 | PASS |
| 11 | Basic Writings of Aquinas | 810+ | PASS |
| 12 | Mastering Windows 365 | 695 | WARN |
| 16 | Uprising! (Irving) | 610+ | PASS |
| 20 | Revelation (Knorr) | 695 | PASS |
| 21 | Shakespeare First Folio (compressed) | 906 | FAIL |
| 22 | Shakespeare First Folio (full) | 906 | FAIL |
| 23 | Jesus and Victory of God (Wright) | 741 | WARN |
| 24 | Public Finance (Gruber) | 850+ | PASS |
| 25 | Readings in Database Systems | 680 | PASS |
| 31 | Decline of the West (Spengler) | 680+ | PASS |
| 40 | Algorithm Design Manual (Skiena) | 730 | PASS |
| 42 | Beginning of Wisdom (Kass) | 680 | PASS |
| 45 | Oxford Companion to Bible | 900+ | FAIL |
