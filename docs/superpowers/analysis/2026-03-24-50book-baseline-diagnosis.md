# 50-Book Clean Baseline + WARN/FAIL Diagnosis

**Date:** 2026-03-24
**Run IDs:** `batch_20260324_083332` (batch 1), `batch_20260324_091457` (batch 2)
**Original Run IDs:** `batch_20260323_224547` (batch 1), `batch_20260323_231114` (batch 2)

## Clean Baseline Results

| Metric | Original (broken glob) | Clean Baseline | Delta |
|--------|----------------------|----------------|-------|
| Total books | 50 | 50 | -- |
| PASS | 18 (36%) | 37 (74%) | +19 |
| WARN | 4 (8%) | 9 (18%) | +5 |
| FAIL | 28 (56%) | 4 (8%) | -24 |
| ERROR | 0 | 0 | -- |
| **Pass rate** | **36%** | **74%** | **+38pp** |

The original 36% pass rate was an artifact of the glob mismatch bug -- extraction succeeded but batch_qa couldn't find the output files. After the glob fix, timeout scaling, scan detection, and DRM detection, 24 previously-failing books now pass or warn correctly.

### Batch 1 Comparison (batch_20260323_224547 -> batch_20260324_083332)

- Pass rate: 40% -> 76% (+36pp)
- 12 books changed status: 9 FAIL->PASS, 3 FAIL->WARN
- Extraction failures: 14 -> 2 (-12)

### Batch 2 Comparison (batch_20260323_231114 -> batch_20260324_091457)

- Pass rate: 32% -> 72% (+40pp)
- 12 books changed status: 10 FAIL->PASS, 2 FAIL->WARN
- Extraction failures: 14 -> 2 (-12)

## Top Failure Clusters (combined 50 books)

| Pattern | Books | Severity |
|---------|-------|----------|
| Footnotes not linked | 11 | medium |
| No bold/italic formatting preserved | 9 | medium |
| No chapters detected | 5 | high |
| Excessive double spaces (>20) | 4 | low |
| Encoding errors in extracted text | 3 | high |
| Likely scanned PDF without OCR | 2 | medium |
| Excessive ligature splits (>20) | 1 | medium |
| Only back-matter headings detected | 1 | high |

Note: "Footnotes not linked" and "No formatting preserved" appear in passing books too (they are medium-severity issues that don't block PASS status alone). The 5 chapter detection and 3 encoding error issues are what drive the WARN statuses.

## Full Diagnosis Table

| # | Book | Status | Root Cause | Details | Fixable Now? |
|---|------|--------|------------|---------|--------------|
| 1 | Andrea Nicolotti - Shroud of Turin | WARN | ENCODING_ERRORS | 2 U+FFFD from decorative DejaVuSans font glyphs in a Latin footnote. Cosmetic only. | No (cosmetic) |
| 2 | Christiaan Brinkhoff - Mastering Windows 365 | WARN | ENCODING_ERRORS | 5,799 U+FFFD. CrimsonPro-SemiBold font has broken CMap: period (0x2E) maps to U+FFFD. All TOC dot-leaders and bold periods corrupted. Packt Publishing PDF authoring defect. | Maybe (post-processing) |
| 3 | First Folio of Shakespeare (Compressed) | FAIL | TIMEOUT/SCAN | 117MB JBIG2 scan, 968 pages. Column detector routes to PyMuPDF at 1.9s/page = 31 min, exceeding 26-min budget. Duplicate of #4. | No (needs JBIG2 pre-flight) |
| 4 | First Folio of Shakespeare (Anna's Archive) | FAIL | TIMEOUT/SCAN | Identical content to #3 in different PDF wrapper. Same timeout behavior. | No (duplicate, remove one) |
| 5 | Jesus and the Victory of God - N.T. Wright | WARN | SCAN_NO_TEXT | 73MB JPEG2000 scan, 765 pages. Adobe "Image Conversion Plug-in" origin. Zero text layer. | No (needs Tesseract OCR) |
| 6 | Manly P. Hall - Secret Destiny of America | WARN | CHAPTER_DETECTION | 33K words extracted fine. 20 chapters exist as numbered `<p>` tags (e.g. "1. THE ORIGIN OF THE DEMOCRATIC IDEAL") but never got heading tags because PDF has no font-size differentiation. | Maybe (pattern promotion rule) |
| 7 | The Hindu Pantheon - Edward Moor | WARN | SCAN_NO_TEXT | 23MB CCITTFax bitonal scan, 480 pages. 19th century book. ScanFix/tiff2pdf origin. Zero text layer. | No (needs OCR, hard job) |
| 8 | The Oxford Companion to the Bible | FAIL | TIMEOUT/SCAN | 46MB JBIG2 scan, 936 pages. 2-column layout routes to PyMuPDF, times out at 855s. | No (needs JBIG2 pre-flight) |
| 9 | The Thirteenth Tribe | WARN | ENCODING_ERRORS | 1 U+FFFD from Wingdings separator glyph in a comparison table. Cosmetic only. | No (cosmetic) |
| 10 | The_Tempest_FAX | WARN | CHAPTER_DETECTION | FAX scan of 1623 First Folio. 17K words extracted but severely garbled OCR. 13 "headings" are running headers/scanner noise. No chapter structure exists in Shakespeare folio plays. | No (poor scan, no chapters) |
| 11 | Hero Tales From American History | FAIL | TIMEOUT | 15MB JBIG2 scan, 79 pages. pdfminer hangs indefinitely on page 42 (JBIG2 decode loop without jbig2dec binary). | No (needs jbig2dec install) |
| 12 | Origenes - On First Principles 1 | WARN | SCAN_NO_TEXT | 3MB JBIG2 copier scan, 276 pages. Konica Minolta office scanner origin. Zero text layer. Modern typography would OCR well. | No (needs OCR) |
| 13 | Wall Street and The Rise of Hitler - Sutton | WARN | CHAPTER_DETECTION_BACKMATTER | Extraction is actually excellent: 12 chapters tagged h3, 606 italic tags, 8 blockquotes. Issue is batch_qa counting bug: `chapter_count = h1 + h2` excludes h3. The 4 counted h2 are Appendix C/D entries. | Yes (batch_qa logic fix) |

## Root Cause Summary

| Root Cause | Books | Fixable Now? | Action |
|------------|-------|--------------|--------|
| TIMEOUT (JBIG2 scans) | 4 (incl. 1 duplicate) | No | Need JBIG2 pre-flight detector to skip/route before extraction. Overrides recorded. |
| SCAN_NO_TEXT | 3 | No | Pure image scans need Tesseract OCR integration. Overrides recorded as `ocr_required`. |
| ENCODING_ERRORS | 3 | Partially | 2 are cosmetic (1-2 chars). Windows 365 (5,799 FFFD from broken font CMap) could benefit from FFFD post-processing pass. |
| CHAPTER_DETECTION | 2 | Partially | Hall: numbered paragraph pattern not promoted to headings. Tempest FAX: correct (no chapters exist). |
| CHAPTER_DETECTION_BACKMATTER | 1 | Yes | Sutton book is actually well-extracted. batch_qa.py counts h1+h2 only, but Sutton's 12 chapters are h3. Fix the counting logic. |

## Book Overrides Recorded

7 overrides added to `book_overrides` table in `data/ebook_patterns.db`:

| Override ID | Book | Extraction Path | Notes |
|-------------|------|-----------------|-------|
| 2 | First Folio (Compressed) | skip | JBIG2 scan, duplicate |
| 3 | First Folio (Anna's Archive) | skip | JBIG2 scan, duplicate |
| 4 | Oxford Companion to the Bible | skip | JBIG2 scan, 2-column timeout |
| 5 | Hero Tales From American History | skip | JBIG2 pdfminer hang |
| 6 | Jesus and the Victory of God | ocr_required | JPEG2000 scan, no text |
| 7 | The Hindu Pantheon | ocr_required | CCITTFax bitonal scan |
| 8 | Origenes - On First Principles 1 | ocr_required | JBIG2 copier scan |

## Recommended Next Priorities

1. **JBIG2 pre-flight detector** -- Add a pre-extraction check counting `/JBIG2Decode` in the first 64KB of each PDF. If count >= 5, classify as `scan` and either skip or queue for OCR. This prevents 4 timeout failures (8% of corpus) from burning 10+ minutes each.

2. **Tesseract OCR integration** -- 3 books (6%) are pure image scans with no text layer. An auto-OCR fallback for classified scans would recover these. Priority order by difficulty: Origenes (easiest, modern type), Wright/N.T. Wright (medium, colour scans), Hindu Pantheon (hardest, 19th century bitonal).

3. **batch_qa chapter counting for h3-only books** -- The Sutton book is well-extracted but WARN'd because batch_qa.py excludes h3 from chapter count. When h1+h2 == 0 but h3 > 0, h3 should count as chapters. Fixes 1 book immediately, likely more in future batches.

4. **U+FFFD post-processing** -- For Packt Publishing books (CrimsonPro-SemiBold broken CMap), a targeted pass replacing FFFD runs >= 5 with space and isolated FFFD with `.` would fix TOC readability and bold period corruption. Low effort, moderate impact.

5. **Numbered paragraph heading promotion** -- Books like Hall (1944) use `<p>1. ALL-CAPS TITLE</p>` for chapters without font-size distinction. A regex pattern promoting these to `<h2>` would recover chapter detection for this class of books.

6. **Duplicate detection** -- The two Shakespeare Folios are identical content in different PDF wrappers. A file-hash or content-hash dedup step would flag these before wasting extraction time.
