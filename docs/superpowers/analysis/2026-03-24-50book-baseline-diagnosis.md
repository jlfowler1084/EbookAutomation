# 50-Book Clean Baseline + WARN/FAIL Diagnosis

**Date:** 2026-03-24
**Runs:** `batch_20260324_083332` (batch 1), `batch_20260324_091457` (batch 2)

## Clean Baseline Results

| Metric | Original (pre-fix) | Clean Baseline | Delta |
|--------|-------------------|----------------|-------|
| Total books | 50 | 50 | -- |
| Pass | 18 (36%) | 37 (74%) | +19 |
| Warn | 4 (8%) | 9 (18%) | +5 |
| Fail | 28 (56%) | 4 (8%) | -24 |
| Error | 0 | 0 | -- |

The original 36% pass rate was a **false baseline** caused by a glob mismatch bug in `batch_qa.py` that couldn't find output HTML files after extraction. The glob fix (`4c324a1`), along with timeout scaling, scan detection, and DRM detection, raised the true pass rate to **74%**.

### Batch 1 Comparison (batch_20260323_224547 -> batch_20260324_083332)

- Pass rate: 40% -> 76% (+36%)
- 12 books changed status: 9 FAIL->PASS, 3 FAIL->WARN
- Extraction failures dropped from 14 to 2 (both Shakespeare Folios)

### Batch 2 Comparison (batch_20260323_231114 -> batch_20260324_091457)

- Pass rate: 32% -> 72% (+40%)
- 12 books changed status: 10 FAIL->PASS, 2 FAIL->WARN
- Extraction failures dropped from 14 to 2 (Oxford Companion, Hero Tales)

## Top Failure Clusters (across 50 books)

| Pattern | Books | Severity |
|---------|-------|----------|
| footnotes_unlinked | 11 | medium |
| no_formatting_preserved | 9 | medium |
| chapter_detection_zero | 5 | high |
| double_spaces | 4 | low |
| encoding_errors | 3 | high |
| likely_scan_no_ocr | 2 | medium |
| chapter_detection_backmatter_only | 1 | high |
| ligature_splits_high | 1 | medium |

Note: `footnotes_unlinked` and `no_formatting_preserved` affect many PASS books too (they're medium-severity, don't trigger WARN by themselves).

## WARN/FAIL Diagnosis Table

| # | Book | Status | Root Cause | Key Metrics | Fixable Now? |
|---|------|--------|------------|-------------|--------------|
| 1 | First Folio of Shakespeare (Compressed) | FAIL | SCAN_TIMEOUT | 116.6 MB, 968 pages, facsimile scans (2 images/page), garbled OCR text, timed out at 1566s | No |
| 2 | First Folio of Shakespeare (Full) | FAIL | SCAN_TIMEOUT | 116.9 MB, 968 pages, duplicate of #1 (different source), timed out at 1568s | No |
| 3 | Oxford Companion to the Bible | FAIL | SCAN_TIMEOUT | 45.5 MB, 936 pages, scanned (87 chars page 1, 2 images/page), timed out at 855s | No |
| 4 | Hero Tales from American History | FAIL | CORRUPT_PDF | 15.3 MB, corrupt object tree (PyMuPDF: "syntax error", "non-page object"), minimal text, timed out at 600s | No |
| 5 | Andrea Nicolotti - Shroud of Turin | WARN | ENCODING_MINOR | 12.4 MB, 209K words, 2582 italics, 1118 linked footnotes. Only 2 encoding errors. Near-PASS. | No (source encoding) |
| 6 | Christiaan Brinkhoff - Windows 365 | WARN | ENCODING_HEAVY | 83 MB, 93K words, 5799 encoding errors (clustered, likely from embedded screenshots/diagrams in tech book) | No (source encoding) |
| 7 | N.T. Wright - Jesus and Victory of God | WARN | SCAN_NO_TEXT | 72.6 MB, 88 words extracted, classified as scan. Image-only PDF. | No (needs OCR) |
| 8 | Manly Hall - Secret Destiny of America | WARN | CHAPTER_DETECTION | 2.7 MB, 33K words, 461 paragraphs. H3 has only title page text. Numbered chapter headings ("1. THE ORIGIN OF THE DEMOCRATIC IDEAL") are plain text, not detected as headings. | Maybe (chapter detection fix) |
| 9 | Hindu Pantheon - Edward Moor | WARN | SCAN_NO_TEXT | 23.4 MB, 84 words extracted, classified as scan. Image-only PDF. | No (needs OCR) |
| 10 | Thirteenth Tribe - Arthur Koestler | WARN | ENCODING_MINOR | 2.1 MB, 72K words, 15 chapters, 475 italics. Only 1 encoding error. Also 536 unlinked footnotes. Near-PASS. | No (source encoding) |
| 11 | The Tempest FAX | WARN | OCR_GARBLED | 2.3 MB, 17K words from garbled OCR ("Bore-fwaine", "Mogghde TEMPEST"). No bold/italic. H3 headings are OCR artifacts. | No (source quality) |
| 12 | Origen - On First Principles | WARN | SCAN_NO_TEXT | 2.9 MB, 276 pages, 0 text on page 1, 1 image/page. Pure image PDF. | No (needs OCR) |
| 13 | Wall Street and Rise of Hitler - Sutton | WARN | CHAPTER_DETECTION_BACKMATTER | 0.6 MB, 55K words, 1249 paragraphs, 606 italics. Real chapter headings ("Chapter Four", "Chapter Five") at h3 level; only appendices promoted to h2. All h2 headings are backmatter. | Maybe (chapter detection fix) |

## Root Cause Summary

| Root Cause | Count | Books | Action |
|------------|-------|-------|--------|
| SCAN_TIMEOUT | 3 | Shakespeare Folio x2, Oxford Companion | Needs OCR path or skip (huge facsimiles) |
| SCAN_NO_TEXT | 3 | N.T. Wright, Hindu Pantheon, Origen | Needs OCR path |
| CORRUPT_PDF | 1 | Hero Tales | Manual intervention or skip |
| ENCODING_HEAVY | 1 | Windows 365 | Source encoding issue (tech book diagrams) |
| ENCODING_MINOR | 2 | Shroud of Turin, Thirteenth Tribe | Near-PASS; only 1-2 errors each |
| CHAPTER_DETECTION | 1 | Manly Hall | Numbered headings in plain text not detected |
| CHAPTER_DETECTION_BACKMATTER | 1 | Wall Street/Sutton | Real chapters at h3, backmatter at h2 |
| OCR_GARBLED | 1 | Tempest FAX | Source is garbled OCR facsimile |

## Books Fixed by Extraction Path Switch

**0** -- No books benefited from extraction path switching. All non-passing issues are upstream of the extraction path:
- Scanned PDFs produce no text regardless of extraction method
- Encoding errors originate in the source PDF
- Chapter detection runs after extraction (detection logic issue, not extraction issue)

## Recommended Next Priorities

1. **OCR fallback path** (6 books = +12% potential pass rate): Auto-detect scanned PDFs (already done via `source_classification`) and route them to an OCR extraction path (Tesseract or similar). Would fix N.T. Wright, Hindu Pantheon, Origen, and potentially the Shakespeare Folios and Oxford Companion.

2. **Chapter detection for plain-text headings** (2 books = +4%): Manly Hall has numbered chapter headings as regular text ("1. THE ORIGIN..."). Wall Street/Sutton has real chapters at h3 but only backmatter at h2. Fix: improve heading promotion logic to recognize numbered chapter patterns and prioritize content headings over backmatter.

3. **Encoding normalization** (1 book with real impact): Windows 365 has 5799 encoding errors from embedded content. A pre-extraction encoding normalization step could help. The other 2 encoding WARN books (Shroud of Turin, Thirteenth Tribe) are near-PASS with only 1-2 errors each.

4. **Duplicate detection** (1 book): Shakespeare Folio appears twice (compressed and full versions). Consider deduplication or marking one as skip.

## If All Fixable Issues Were Resolved

| Scenario | Pass Rate |
|----------|-----------|
| Current baseline | 74% (37/50) |
| + OCR path (6 scans pass) | 86% (43/50) |
| + Chapter detection fix (2 books) | 90% (45/50) |
| + Encoding normalization (1 book) | 92% (46/50) |
| Remaining unfixable | 4 books: corrupt PDF, garbled OCR source, 2 near-PASS encoding |
