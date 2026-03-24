# Batch QA Failure Triage — 2026-03-23

## Summary

50 books processed across 2 batch runs. 28 reported as FAIL. After deep investigation, the **true failure count is 6** — the remaining 22 were false failures caused by a filename sanitization bug in `batch_qa.py`.

## Root Cause: Filename Sanitization Mismatch

**The #1 issue is NOT extraction failure — it's a detection bug in `batch_qa.py`.**

`batch_qa.py` line 337 uses:
```python
safe_stem = re.sub(r'[^\w\-.]', '_', stem)  # replaces , ( ) etc. with _
```

`pdf_to_balabolka.py` line 8821 uses:
```python
safe_stem = re.sub(r"[^\w\s\-]", "", stem).strip().replace(" ", "_")  # REMOVES , ( ) etc.
```

Result: `"Cooper, Andrew"` becomes `Cooper__Andrew` in batch_qa but `Cooper_Andrew` in p2b. The glob pattern `*Cooper__Andrew*` never matches the output file `Cooper_Andrew_..._kindle.html`.

**Correlation: 100%** — every PASS/WARN has matching stems, every FAIL has mismatched stems (except 4 timeouts).

## Revised Classification (28 reported failures)

| Bucket | Count | Description |
|--------|-------|-------------|
| **GLOB_BUG** | 22 | Extraction succeeded but output file not found due to filename mismatch |
| **TIMEOUT** | 4 | Extraction exceeded 600s limit (very large PDFs, 45-117MB) |
| **TRUE_SCAN** | 2 | Genuinely image-only PDFs with zero extractable text |

### GLOB_BUG (22 books) — extraction worked, detection failed

All 22 have extractable text confirmed via direct pypdf/pdfminer probing of body pages. The pipeline produced output files but `batch_qa.py` couldn't find them.

| # | Book | Size | Pages | Body Text (pdfminer p5) |
|---|------|------|-------|------------------------|
| 1 | Ezekiel II (Zimmerli) | 53.3 MB | 637 | 3,883 chars |
| 2 | Python in easy steps | 8.1 MB | 297 | 1,577 chars |
| 3 | Rhetorical Function of Ezekiel | 17.6 MB | 318 | 1,446 chars |
| 4 | Artful Relic (Casper) | 32.4 MB | 216 | 1,428 chars |
| 5 | Mastering Windows 365 | 83.0 MB | 663 | 1,819 chars |
| 6 | Kabbalah (Ginsburg) | 7.4 MB | 171 | 3,008 chars |
| 7 | Oil Kings (Cooper) | 4.2 MB | 406 | 3,410 chars |
| 8 | Occult Holidays (Coulter) | 4.9 MB | 368 | 3,304 chars |
| 9 | Uprising! (Irving) [DRM] | 2.5 MB | 751 | 2,636 chars |
| 10 | First Folio (Compressed) | 116.6 MB | 968 | 376 chars |
| 11 | First Folio (Full) | 116.9 MB | 968 | 376 chars |
| 12 | Database Systems (Hellerstein) | 40.3 MB | 879 | 3,687 chars |
| 13 | Secret Destiny (Hall) | 2.7 MB | 54 | 5,485 chars |
| 14 | Mexico Illicit (Jones) | 2.1 MB | 209 | 127 chars |
| 15 | Talmud Unmasked (Pranaitis) | 1.0 MB | 96 | 1,960 chars |
| 16 | Exile, Incorporated (Liebermann) | 20.1 MB | 241 | 1,840 chars |
| 17 | Most Dangerous Book (Bain) [DRM] | 7.2 MB | 374 | 5,080 chars |
| 18 | Disclosure (Greer) | 12.1 MB | 560 | 3,262 chars |
| 19 | Algorithm Design (Skiena) | 3.9 MB | 739 | 2,764 chars |
| 20 | Into the Fringe (Turner) | 19.5 MB | 261 | 852 chars |
| 21 | Return of the Gods (Cahn) | 1.6 MB | 289 | 1,695 chars |
| 22 | Wall St & Hitler (Sutton) | 0.6 MB | 148 | 3,353 chars |

Note: 2 of these (Irving, Bain) are also DRM-encrypted. They may fail even after the glob fix, but they have extractable text via empty-password decryption.

### TIMEOUT (4 books)

These exceeded the 600-second extraction limit. They also have the glob bug, so it's unclear if they would have produced output within the limit.

| # | Book | Size | Pages | Body Text |
|---|------|------|-------|-----------|
| 1 | First Folio (Compressed) | 116.6 MB | 968 | 376 chars |
| 2 | First Folio (Full) | 116.9 MB | 968 | 266 chars (cover) |
| 3 | Oxford Companion to Bible | 45.5 MB | 936 | 3,890 chars |
| 4 | Hero Tales (Lodge/Roosevelt) | 15.3 MB | 79 | 650 chars |

Note: First Folio books overlap with GLOB_BUG (they timed out AND have the glob bug). Hero Tales at 15MB/79 pages = 0.194 MB/page — possibly image-heavy scanned pages.

### TRUE_SCAN (2 books)

Genuinely image-only PDFs. Zero extractable text on pages 3, 5, and 10 from both pypdf and pdfminer.

| # | Book | Size | Pages | MB/page |
|---|------|------|-------|---------|
| 1 | Jesus and the Victory of God (N.T. Wright) | 72.6 MB | 765 | 0.095 |
| 2 | On First Principles (Origen) | 2.9 MB | 276 | 0.011 |

## Recommendations

### Priority 1: Fix the glob bug in `batch_qa.py` (fixes 22/28 failures)

Align the `safe_stem` in `run_extraction_for_book()` with `pdf_to_balabolka.py`:
```python
# Line 337 — change from:
safe_stem = re.sub(r'[^\w\-.]', '_', stem)
# To:
safe_stem = re.sub(r"[^\w\s\-]", "", stem).strip().replace(" ", "_")
```

Or better: have `pdf_to_balabolka.py` print the output path to stdout and parse it in `batch_qa.py` instead of re-deriving it.

**This single fix would raise the pass rate from 36% to ~88%.**

### Priority 2: Increase timeout for large books (fixes 2-4 more)

The 600s timeout is too short for 100MB+ PDFs. Consider:
- Scaling timeout by file size (e.g., 600s base + 10s per MB)
- Or raising to 1200s for files > 50MB

### Priority 3: OCR fallback (fixes 2 books)

Only 2 books are truly scanned. An auto-OCR fallback would help but is low-priority given the small count.

### Priority 4: DRM handling (2 books)

Irving and Bain are encrypted but decryptable with empty password. The pipeline could try `reader.decrypt('')` before extraction.

## Corrected Pass Rate

After fixing the glob bug alone:
- **Actual pass rate: ~88%** (44/50), not 36% as reported
- True failures: 2 scan + 2 DRM + 2-4 timeout = 6-8 books
