# Enriched Baseline Analysis — 2026-03-24

**Run ID:** `batch_20260324_224325`
**Books processed:** 50 | **Passed:** 38 | **Warnings:** 8 | **Failed:** 4 | **Errors:** 0
**Pass rate:** 76% | **Duration:** 60m 57s | **API cost:** $0.00
**Mode:** Quick (HTML extraction only) | **Workers:** 2

This is the first batch run with all six deployed tickets active: extraction cache (SCRUM-124), Re-OCR Tier 2 (SCRUM-122), Vision Tier 3 (SCRUM-123), data enrichment (SCRUM-133), TOC heading fix (SCRUM-126), and text quality scorer (SCRUM-121).

---

## Baseline Comparison

### vs. Original 25-Book Baseline (`batch_20260324_083332`)

| Metric | Original (25 books) | Enriched (50 books) | Delta |
|--------|--------------------:|--------------------:|------:|
| Pass rate | 76.0% | 76.0% | +0.0% |
| Books passed | 19 | 38 | +19 |
| Warnings | 4 | 8 | +4 |
| Failures | 2 | 4 | +2 |

Pass rate held exactly at 76% when scaling from 25 to 50 books — the new 25 books have the same quality distribution as the original set.

### vs. Post-TOC-Fix Rerun (`batch_20260324_191919`)

| Metric | Post-Fix (37 books) | Enriched (50 books) | Delta |
|--------|--------------------:|--------------------:|------:|
| Pass rate | 100.0% | 76.0% | -24.0% |
| Books passed | 37 | 38 | +1 |
| Warnings | 0 | 8 | +8 |
| Failures | 0 | 4 | +4 |

The 37-book rerun excluded the hardest books (scans, massive PDFs). The 13 additional books in the enriched run brought back all the failure modes.

---

## 4a. PDF Producer Analysis

| Producer | Total | Pass | Warn | Fail | Pass% |
|----------|------:|-----:|-----:|-----:|------:|
| **Adobe (Acrobat/InDesign)** | 17 | 14 | 3 | 0 | **82%** |
| **Internet Archive** | 6 | 3 | 1 | 2 | **50%** |
| **Calibre** | 5 | 5 | 0 | 0 | **100%** |
| **OCR Software (ABBYY/OmniPage)** | 4 | 3 | 1 | 0 | **75%** |
| **LuraDocument (recoded)** | 4 | 2 | 0 | 2 | **50%** |
| **Unknown/None** | 4 | 4 | 0 | 0 | **100%** |
| **iText** | 3 | 2 | 1 | 0 | **67%** |
| Other (7 producers, 1 each) | 7 | 5 | 2 | 0 | 71% |

### Key Findings

- **Calibre** and **Unknown/None** producers have 100% pass rate — these are clean, well-structured PDFs
- **Adobe** is the largest group (17 books, 34%) with a solid 82% pass rate. The 3 warnings are encoding issues (Shroud of Turin, Windows 365, Thirteenth Tribe)
- **Internet Archive** scans are the worst performers (50% pass). Both failures are the Shakespeare First Folios — massive image-based PDFs that time out during extraction
- **LuraDocument** (recoded PDFs) are equally bad at 50%. Both failures (Oxford Companion, Hero Tales) are large recoded PDFs where text extraction fails entirely
- **OCR Software** (ABBYY, OmniPage) performs at 75% — the single warning is a chapter detection miss

### Failure Correlation

All 4 failures share two traits:
1. **Producer is Internet Archive or LuraDocument** (PDF recoding tools, not direct publishers)
2. **File size >10MB** — these are either image-heavy scans or recoded/compressed PDFs

---

## 4b. Font Inventory Analysis

**Result: Font data was NOT captured** for any of the 50 books. All books show `total_unique: 0` and empty font name lists.

The font inventory extraction from SCRUM-133 is implemented in `pdf_to_balabolka.py` but is not wired into `batch_qa.py`'s extraction pipeline. The batch QA system calls its own extraction flow rather than going through the full `pdf_to_balabolka.py` enrichment path.

**Action needed:** Wire the font extraction from SCRUM-133 into `batch_qa.py`'s book processing function, or expose font data through the extraction cache so batch_qa can read it.

---

## 4c. Script Detection Analysis

| Script Profile | Count | % |
|---------------|------:|--:|
| Latin only | 39 | 78% |
| Multi-script (trace amounts) | 7 | 14% |
| No data (extraction failed) | 4 | 8% |

### Multi-Script Books Detected

| Book | Non-Latin Scripts | Status |
|------|-------------------|--------|
| Renz - Rhetorical Function of Ezekiel | Greek (trace) | PASS |
| Nicolotti - Shroud of Turin | Greek 0.3%, Other 0.1% | WARN |
| Heiser - Demons | Other 0.2% | PASS |
| Kolb - Weimar Republic | Other 0.2% | PASS |
| Kleppmann - Designing Data-Intensive Apps | Greek (trace) | PASS |
| Skiena - Algorithm Design Manual | Greek (trace), Other 0.3% | PASS |
| Moore - Formation of Persecuting Society | Other 0.2% | PASS |

**No books have >5% non-Latin content.** All multi-script detections are trace amounts (Greek letters in academic texts, mathematical symbols). The Ezekiel commentary (Zimmerli) — expected to have Hebrew — was routed through multi-column extraction which may not have captured script distribution.

**Vision extraction candidates:** None identified from script detection alone. The Ezekiel II commentary may still benefit from Vision extraction for Hebrew passages, but the script detector didn't flag it — likely because the Hebrew text is in image form (scanned pages) rather than Unicode text.

---

## 4d. Extraction Timing & Cache Analysis

| Speed Tier | Count | Description |
|-----------|------:|-------------|
| **Instant (<2s)** | 8 | Likely cache hits |
| Fast (2-30s) | 15 | Small/simple PDFs |
| Normal (30-120s) | 19 | Standard extraction |
| Slow (>120s) | 8 | Large/complex PDFs |

### Cache Hits (Instant Extractions)

| Book | Time | Notes |
|------|-----:|-------|
| Ezekiel II (Zimmerli) | 0.7s | Multi-column, previously extracted |
| Oil Kings (Cooper) | 0.4s | Previously extracted in test suite |
| Mexico's Illicit Drug Networks | 0.3s | Previously extracted in test suite |
| Most Dangerous Book (Bain) | 0.3s | Previously extracted |
| Scytl Election Results | 1.4s | Very small PDF |
| Codex Magica (Marrs) | 0.5s | Previously extracted in test suite |
| Hindu Pantheon | 1.4s | Scan, no text to extract |
| Origen - On First Principles | 1.0s | Cache or minimal text |

**Estimated time saved:** The 8 cache-hit books completed in ~6s total vs. an estimated ~400s if freshly extracted = **~6.5 minutes saved**.

### Slowest Books

| Book | Time | Reason |
|------|-----:|--------|
| Shakespeare First Folio (compressed) | 1566s | 900+ page image PDF, extraction timeout |
| Shakespeare First Folio (full) | 1568s | Same content, different scan |
| Oxford Companion to Bible | 855s | 900+ page reference work |
| Hero Tales from American History | 602s | Recoded PDF, extraction struggles |
| Decline of the West (Spengler) | 275s | 600+ page dense text |

---

## 4e. Text Quality Tier Analysis

| Tier | Count | Description |
|------|------:|-------------|
| **Tier 1** (score 85-100, accept) | 42 | Good text, no re-OCR needed |
| **Tier 2** (score 50-84, try re-OCR) | 1 | Borderline, may benefit from Tesseract |
| **No score** (extraction failed) | 7 | Couldn't score — extraction failed or scan-only |

### Tier 2 Candidate (OCR Auto-Escalation)

- **Coulter - Occult Holidays** — score 68, recommendation `try_reocr`. This book passed overall but has a degraded text layer that Tesseract might improve.

### No-Score Books (Tier None)

These 7 books either failed extraction entirely (4 FAILs) or had so little extractable text that scoring wasn't meaningful (3 WARNs — scans or chapter-detection-zero).

**OCR auto-escalation from SCRUM-122 did NOT trigger** for any book in this run. The auto-escalation requires the extraction to succeed first and then evaluate text quality. The 4 failures never produced extractable text, so there was nothing to score/escalate. The single Tier 2 candidate (Coulter) was identified but not auto-escalated during this quick-mode run.

---

## 4f. Failure Pattern Clusters

### Critical: Text Extraction Failed (4 books)

All 4 failures are PDFs where extraction timed out or produced zero text:
- **2x Shakespeare First Folio** — Internet Archive scans, 900+ pages of image-only content
- **Oxford Companion to Bible** — LuraDocument recoded, 900+ pages
- **Hero Tales from American History** — LuraDocument recoded, extraction timeout

**Common traits:** All >10MB, all from PDF recoding tools (Internet Archive, LuraDocument), all lack a usable text layer.

### High: No Chapters Detected (9 books)

Includes the 4 failures above plus 5 books that extracted text but found zero chapters:
- **Jesus and the Victory of God** (N.T. Wright) — scan, no OCR layer
- **Hindu Pantheon** — TIFF conversion, scan-only
- **Manly P. Hall - Secret Destiny of America** — ABBYY OCR but poor text quality
- **Tempest FAX** — Internet Archive scan
- **Origen - On First Principles** — iText, possibly DRM or encoding issue

**Key insight:** Chapter detection failing correlates 100% with either (a) extraction failure or (b) scan-only PDFs. It is not a chapter detection algorithm problem — it's an input quality problem.

### High: Encoding Errors (3 books)

Non-UTF8 content causing garbled characters in:
- Shroud of Turin (PyPDF2 producer — unusual)
- Mastering Windows 365 (Adobe PDF Library)
- Thirteenth Tribe (old Acrobat PDFWriter 4.05)

**Pattern:** These are all older or non-standard PDF producers. The PDFWriter 4.05 producer is from the late 1990s.

---

## 4g. Recommendations

### Priority 1: LuraDocument/Internet Archive Extraction Failures (Impact: 4 books → +8% pass rate)

All 4 failures are from PDF recoding tools. These PDFs are image-based or have corrupted text layers. **Action:** Add a file-size-to-text-ratio check. If a >10MB PDF produces <1KB of text, auto-escalate to OCR (Tier 2) or flag as needing Vision (Tier 3). This would rescue the Oxford Companion and Hero Tales; the Shakespeare First Folios may need a page-count limit or chunked extraction.

### Priority 2: Wire Font Inventory into batch_qa.py (Impact: data quality)

Font data was not captured because batch_qa.py doesn't call the SCRUM-133 enrichment functions. Either:
- Call `extract_pdf_metadata()` and `extract_font_inventory()` from batch_qa.py's per-book processing, or
- Read font data from the extraction cache if the book was previously processed through pdf_to_balabolka.py

### Priority 3: Encoding Normalization Pre-Pass (Impact: 3 books → +6% pass rate)

The 3 encoding-error books are all from older PDF producers. Adding a UTF-8 normalization step before text analysis (using `ftfy` or similar) would clean these up. This is a low-risk, high-reward fix.

### Priority 4: Scan Detection + Auto-OCR for Warned Books (Impact: 2-5 books)

The 2 "likely scan" books (N.T. Wright, Hindu Pantheon) should be auto-routed to Tier 2 OCR. Currently they extract zero text and get WARN status. Auto-OCR would either rescue them or confirm they need Vision.

### Priority 5: Vision Extraction Candidates

Based on this run, the strongest Vision candidates are:
1. **Ezekiel II** (Zimmerli) — multi-column commentary with Hebrew passages in image form
2. **Hindu Pantheon** — scan-only, likely contains Devanagari/Sanskrit
3. **Shakespeare First Folios** — old English typography, image-only
4. **N.T. Wright - Jesus and Victory of God** — scan without OCR

These 4 books would need Tier 3 (Vision) extraction because they either have no text layer or contain non-Latin scripts in image form.

### What the Next Batch Run Should Focus On

1. **Re-run with font extraction wired in** to capture the missing font inventory data
2. **Add OCR auto-escalation for extraction failures** (the current auto-escalation only fires when extraction succeeds but quality is low — it doesn't fire when extraction fails entirely)
3. **Test encoding normalization** on the 3 encoding-error books
4. **Consider excluding the 2 Shakespeare First Folios** from routine batch runs (they each take 26 minutes and always fail — they need a dedicated handling path)

---

## Raw Results Summary

### PASS (38 books)

| # | Book | Chapters | Issues | Time |
|---|------|:--------:|:------:|-----:|
| 1 | Ezekiel II (Zimmerli) | 3 | 2 | 1s |
| 2 | Python in Easy Steps | 93 | 1 | 31s |
| 3 | Rhetorical Function of Ezekiel (Renz) | 50 | 2 | 52s |
| 5 | England's Jewish Solution (Mundill) | 4 | 3 | 50s |
| 7 | Wall Street and Rise of Hitler (Sutton) | 26 | 0 | 13s |
| 8 | Adult Children of Alcoholics (Kritsberg) | 4 | 1 | 15s |
| 10 | Artful Relic (Casper) | 1 | 1 | 20s |
| 11 | Basic Writings of Aquinas | 6 | 1 | 161s |
| 13 | Kabbalah (Ginsburg) | 1 | 0 | 45s |
| 14 | Oil Kings (Cooper) | 22 | 0 | 0s |
| 15 | Occult Holidays (Coulter) | 9 | 1 | 33s |
| 16 | Uprising! (Irving) | 101 | 1 | 59s |
| 17 | Demons (Heiser) | 97 | 0 | 44s |
| 18 | PowerShell Scripting (Jones/Hicks) | 225 | 0 | 29s |
| 19 | Weimar Republic (Kolb) | 7 | 0 | 28s |
| 20 | Revelation and Bible Prophecy (Knorr) | 20 | 0 | 72s |
| 24 | Public Finance (Gruber) | 203 | 1 | 153s |
| 25 | Readings in Database Systems | 17 | 1 | 62s |
| 26 | Culture of Critique (MacDonald) | 43 | 0 | 44s |
| 28 | Designing Data-Intensive Apps (Kleppmann) | 163 | 1 | 39s |
| 29 | Prompt Engineering (Tabatabaian) | 107 | 0 | 11s |
| 30 | Mexico's Illicit Drug Networks (Jones) | 12 | 1 | 0s |
| 31 | Decline of the West (Spengler) | 19 | 1 | 275s |
| 32 | Unholy Alliance (Levenda) | 3 | 0 | 46s |
| 33 | Talmud Unmasked (Pranaitis) | 9 | 1 | 6s |
| 34 | Qabbalah (Myer) | 1 | 1 | 64s |
| 35 | Inside the Kingdom (Lacey) | 19 | 1 | 29s |
| 36 | Exile, Incorporated (Liebermann) | 35 | 0 | 31s |
| 37 | Most Dangerous Book (Bain) | 76 | 1 | 0s |
| 38 | Scytl Election Results User Guide | 1 | 0 | 1s |
| 39 | Disclosure (Greer) | 1 | 1 | 60s |
| 40 | Algorithm Design Manual (Skiena) | 123 | 1 | 67s |
| 41 | Codex Magica (Marrs) | 18 | 2 | 0s |
| 42 | Beginning of Wisdom (Kass) | 3 | 0 | 102s |
| 43 | Formation of Persecuting Society (Moore) | 14 | 0 | 28s |
| 46 | Return of the Gods (Cahn) | 56 | 0 | 16s |
| 47 | The Tempest (Penguin) | 2 | 1 | 10s |
| 50 | Into the Fringe (Turner) | 19 | 0 | 16s |

### WARN (8 books)

| # | Book | Reason |
|---|------|--------|
| 6 | Origen - On First Principles | No chapters detected |
| 9 | Shroud of Turin (Nicolotti) | Encoding errors |
| 12 | Mastering Windows 365 | Encoding errors |
| 23 | Jesus and Victory of God (Wright) | Scan, no chapters |
| 27 | Secret Destiny of America (Hall) | No chapters detected |
| 44 | Hindu Pantheon (Moor) | Scan, no chapters |
| 48 | Thirteenth Tribe (Koestler) | Encoding errors |
| 49 | Tempest FAX | Scan, no chapters |

### FAIL (4 books)

| # | Book | Producer | Time | Reason |
|---|------|----------|-----:|--------|
| 4 | Hero Tales from American History | LuraDocument v2.28 | 602s | Extraction failed |
| 21 | First Folio of Shakespeare (compressed) | Internet Archive | 1566s | Extraction failed |
| 22 | First Folio of Shakespeare (full) | Internet Archive | 1568s | Extraction failed |
| 45 | Oxford Companion to the Bible | LuraDocument v2.68 | 855s | Extraction failed |
