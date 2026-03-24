# 50-Book Clean Baseline + WARN/FAIL Diagnosis

**Date:** 2026-03-24
**Batch 1 run_id:** `batch_20260324_083332` (25 books)
**Batch 2 run_id:** `batch_20260324_091457` (25 books)
**Original run_ids:** `batch_20260323_224547` (batch 1), `batch_20260323_231114` (batch 2)

---

## Clean Baseline Results (50 books)

| Metric | Original (pre-fix) | Clean Baseline | Delta |
|--------|-------------------|----------------|-------|
| Pass | 18 (36%) | 37 (74%) | +19 (+38pp) |
| Warn | 4 (8%) | 9 (18%) | +5 |
| Fail | 28 (56%) | 4 (8%) | -24 |
| Error | 0 | 0 | -- |

The original 36% pass rate was a **false baseline** caused by a glob pattern mismatch in `batch_qa.py`'s output file detection. 28 books were reported as EXTRACTION_FAILED when they actually extracted fine but the output file couldn't be found. The glob fix (`4c324a1`) resolved this entirely.

### Batch 1 (25 books)
- **Before:** 10 pass (40%), 1 warn, 14 fail
- **After:** 19 pass (76%), 4 warn, 2 fail
- **Status changes:** 12 books improved (10 FAIL->PASS, 2 FAIL->WARN)

### Batch 2 (25 books)
- **Before:** 8 pass (32%), 3 warn, 14 fail
- **After:** 18 pass (72%), 5 warn, 2 fail
- **Status changes:** 12 books improved (10 FAIL->PASS, 2 FAIL->WARN)

---

## Top Failure Clusters (across all 50 books)

| Cluster | Books | Severity | Notes |
|---------|-------|----------|-------|
| `footnotes_unlinked` | 11 | medium | Footnotes present but not hyperlinked; publisher-specific patterns |
| `no_formatting_preserved` | 9 | medium | No bold/italic in output despite likely presence in source |
| `chapter_detection_zero` | 5 | high | Zero h1/h2 chapters detected |
| `double_spaces` | 4 | low | Minor text quality issue |
| `encoding_errors` | 3 | high | Replacement chars in output |
| `likely_scan_no_ocr` | 2 | medium | Scanned PDFs with no text layer |
| `ligature_splits_high` | 1 | medium | Excessive ligature artifacts |
| `chapter_detection_backmatter_only` | 1 | high | Only appendix/index headings detected |

---

## Diagnosis: Every Non-Passing Book

### FAIL Books (4)

| # | Book | Size | Root Cause | Details | Fixable Now? |
|---|------|------|------------|---------|-------------|
| 1 | First Folio of Shakespeare (Compressed) | 116.6 MB | SCAN_TIMEOUT | 968-page facsimile. Garbled OCR text ("Abittea tei itgtete"). Timed out at 1566s. | No -- scanned facsimile, needs OCR or is inherently unextractable |
| 2 | First Folio of Shakespeare (Full) | 116.9 MB | SCAN_TIMEOUT | Same book, different copy. Identical issue. Duplicate of #1. | No -- same as above |
| 3 | Oxford Companion to the Bible | 45.5 MB | SCAN_TIMEOUT | 936 pages, garbled OCR text. Timed out at 855s. | No -- scanned reference book with poor OCR layer |
| 4 | Hero Tales from American History | 15.3 MB | SCAN_TIMEOUT | 364 pages (PyMuPDF). Garbled OCR, corrupt PDF structure ("syntax error: expected object number"). Timed out at 600s. | No -- corrupt PDF + poor OCR |

**All 4 FAIL books are scanned PDFs with garbled or absent OCR text layers.** The extraction runs to timeout because pdfminer spends minutes processing pages that yield almost no usable text. These cannot be fixed without an OCR pipeline (e.g., Tesseract/ABBYY integration).

### WARN Books (9)

| # | Book | Words | Root Cause | Details | Fixable Now? |
|---|------|-------|------------|---------|-------------|
| 5 | Shroud of Turin (Nicolotti) | 209,958 | ENCODING_MINOR | Only 2 replacement chars in 209K words. 1,118 linked footnotes, 2,582 italics. Near-PASS quality. | Near-PASS -- could adjust encoding_errors threshold |
| 6 | Windows 365 (Brinkhoff) | 93,445 | ENCODING_HEAVY | 5,799 replacement chars. Tech book with embedded screenshots causing binary leakage into text stream. | No -- source encoding issue |
| 7 | Jesus and the Victory of God (N.T. Wright) | 88 | SCAN_NO_TEXT | 72.6 MB, only 88 words extracted. Pure scanned PDF. | No -- needs OCR |
| 8 | Secret Destiny of America (Manly Hall) | 33,128 | CHAPTER_DETECTION | 0 h1/h2 headings. 5 h3 headings are all title-page text ("THE SECRET DESTINY OE AMERICA", "BY MANLY PALMER HALL"). Real chapter headers (numbered "1. THE ORIGIN OF THE DEMOCRATIC IDEAL") not detected as headings. | Maybe -- heading detection improvement needed |
| 9 | Hindu Pantheon (Edward Moor) | 84 | SCAN_NO_TEXT | 23.4 MB, only 84 words. Scanned plates/images. | No -- needs OCR |
| 10 | Thirteenth Tribe (Arthur Koestler) | 72,919 | ENCODING_MINOR | Only 1 replacement char. 15 chapters detected. 536 unlinked footnotes. Near-PASS quality. | Near-PASS -- minimal encoding error |
| 11 | The Tempest (FAX) | 17,326 | OCR_GARBLED | Facsimile with garbled OCR ("Mogghde TEMPEST", "Bore-fwaine"). No bold/italic. | No -- source quality issue |
| 12 | On First Principles (Origen) | 85 | LOW_TEXT_YIELD | 2.9 MB, 276 pages, 0 text on page 1, 1 image per page. Image-only PDF with no text layer. | No -- needs OCR |
| 13 | Wall Street and Rise of Hitler (Sutton) | 55,647 | CHAPTER_DETECTION_BACKMATTER | 115 h3 headings include all real chapters ("CHAPTER ONE", "CHAPTER TWO"...). But only 4 h2 headings exist (all appendices), triggering backmatter-only detection. | Maybe -- heading level assignment issue |

---

## Root Cause Summary

| Root Cause | Count | Books | Action |
|-----------|-------|-------|--------|
| SCAN_TIMEOUT | 4 | Shakespeare Folio x2, Oxford Companion, Hero Tales | No fix available -- needs OCR pipeline |
| SCAN_NO_TEXT | 3 | N.T. Wright, Hindu Pantheon, Origen | No fix available -- needs OCR pipeline |
| ENCODING_HEAVY | 1 | Windows 365 | No fix available -- source binary leakage |
| ENCODING_MINOR | 2 | Shroud of Turin, Thirteenth Tribe | Near-PASS -- consider relaxing threshold (1-2 errors in 200K+ words) |
| CHAPTER_DETECTION | 1 | Manly Hall | Needs heading detection improvement -- numbered chapters not recognized |
| CHAPTER_DETECTION_BACKMATTER | 1 | Wall Street/Sutton | Needs heading level assignment fix -- real chapters at h3, only appendices at h2 |
| OCR_GARBLED | 1 | Tempest FAX | No fix available -- garbled facsimile OCR |

---

## What Was Fixed / Could Be Fixed

### Already Fixed (this session)
- **Glob pattern mismatch** (`4c324a1`): Fixed output file detection. 24 books recovered from false FAIL to PASS/WARN.
- **Scaled timeouts**: Large PDFs now get proportionally more time. Still not enough for 900+ page scanned PDFs, but prevents false timeouts on legitimate large books.
- **Scan detection**: Books with <100 words and >5MB now flagged as likely scans.
- **DRM detection**: Encrypted PDFs now detected and flagged.

### Fixable with Future Work
1. **Encoding threshold relaxation** (2 books: Shroud, Thirteenth Tribe): 1-2 replacement chars in 70-200K words should not trigger WARN. Adjust `encoding_errors > 0` to `encoding_errors > 10` or scale by word count.
2. **Chapter detection for numbered chapters** (1 book: Manly Hall): Headings like "1. THE ORIGIN OF THE DEMOCRATIC IDEAL" should be detected even without font-size differentiation.
3. **Heading level assignment** (1 book: Wall Street/Sutton): When all h2 headings are backmatter, promote h3 chapter-pattern headings to h2.

### Not Fixable Without OCR Pipeline
- 7 books (Shakespeare x2, Oxford Companion, Hero Tales, N.T. Wright, Hindu Pantheon, Origen) are scanned/image-only PDFs
- 1 book (Tempest FAX) has garbled facsimile OCR
- 1 book (Windows 365) has source encoding issues from embedded screenshots

---

## Recommended Next Priorities

1. **Relax encoding_errors threshold** -- 2 books would immediately move from WARN to PASS. Low risk, high impact.
2. **Add OCR fallback pipeline** -- 7 books (14% of corpus) are blocked on this. Tesseract integration would unlock the most books.
3. **Improve heading detection for numbered chapters** -- would fix Manly Hall and similar books with "Chapter N" patterns.
4. **Fix heading level assignment** for backmatter-only h2 -- would fix Wall Street/Sutton pattern.
5. **Early-exit for detected scans** -- instead of running pdfminer to timeout on 900+ page scans, detect scans early and skip or route to OCR.

---

## Pass Rate Projection

| Scenario | Pass Rate | Delta |
|----------|-----------|-------|
| Current clean baseline | 74% (37/50) | -- |
| + Relax encoding threshold | 78% (39/50) | +4pp |
| + Fix chapter detection (both issues) | 82% (41/50) | +4pp |
| + OCR pipeline for scans | 96% (48/50) | +14pp |
| Theoretical max (fix everything) | 98% (49/50) | +24pp |

The 1 book that would remain at WARN even with all fixes is Windows 365 (5,799 encoding errors from binary screenshot leakage -- a source quality issue).
