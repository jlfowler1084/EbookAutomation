# Rescue Run Analysis — 2026-03-25

**Run ID:** `batch_20260325_103520`
**Books:** 12 target | 10 processed | 2 skipped (Shakespeare Folios >950 pages)
**Results:** 0 passed, 8 warned, 2 failed | **Duration:** 26m 54s

## Results Table

| Book | Pages | Size | Previous | Rescue | Words | Ch | Time | Outcome |
|------|------:|-----:|----------|--------|------:|---:|-----:|---------|
| Hero Tales | 335 | 50MB | FAIL | **FAIL** | 0 | 0 | 680s | NEEDS GEMINI |
| Oxford Companion | 919 | 75MB | FAIL | **FAIL** | 0 | 0 | 856s | NEEDS GEMINI |
| Shakespeare (compressed) | 968 | 208MB | FAIL | **SKIP** | - | - | - | TOO LARGE |
| Shakespeare (full) | 968 | 418MB | FAIL | **SKIP** | - | - | - | TOO LARGE |
| Origen - First Principles | 463 | 39MB | WARN | **WARN** | 85 | 0 | 1s | UNCHANGED |
| Shroud of Turin | 449 | 156MB | WARN | **WARN** | 210K | 1 | 1s | UNCHANGED |
| Mastering Windows 365 | 695 | 56MB | WARN | **WARN** | 94K | 66 | 4s | UNCHANGED |
| N.T. Wright - Jesus/Victory | 741 | 93MB | WARN | **WARN** | 88 | 0 | 6s | NEEDS GEMINI |
| Secret Destiny (Hall) | 115 | 12MB | WARN | **WARN** | 33K | 0 | 7s | UNCHANGED |
| Hindu Pantheon | 467 | 156MB | WARN | **WARN** | 84 | 0 | 2s | NEEDS GEMINI |
| Thirteenth Tribe | 223 | 5MB | WARN | **WARN** | 73K | 9 | 0s | UNCHANGED |
| Tempest FAX | 109 | 20MB | WARN | **WARN** | 17K | 0 | 5s | UNCHANGED |

## Key Finding: Zero-Text OCR Trigger Did NOT Rescue Any Books

The zero-text trigger (SCRUM-148) fires correctly for Hero Tales and Oxford Companion (both >5MB with <200 words), but the Tesseract OCR step itself produces zero usable text from these PDFs.

**Root cause:** These LuraDocument-recoded PDFs embed page images in a format that Tesseract can't extract. The page images may be in an unusual colorspace, resolution, or format that pdf2image can't render properly for OCR input.

## Outcome Classification

| Category | Count | Books |
|----------|------:|-------|
| **NEEDS GEMINI** | 4 | Hero Tales, Oxford Companion, N.T. Wright, Hindu Pantheon |
| **UNCHANGED** | 6 | Origen, Shroud, Windows 365, Hall, Thirteenth Tribe, Tempest |
| **TOO LARGE** | 2 | Shakespeare First Folios (968 pages each) |
| **RESCUED** | 0 | None |

## Warned Book Analysis

The 8 warned books fall into two distinct categories:

### Category A: Encoding issues (3 books — text exists, quality low)
- **Shroud of Turin** (210K words, 1 chapter) — encoding garble, text is mostly readable
- **Windows 365** (94K words, 66 chapters) — encoding garble, text is mostly readable
- **Thirteenth Tribe** (73K words, 9 chapters) — encoding garble, text is mostly readable

These books have good word counts and chapter detection. The WARN is from encoding artifacts, not extraction failure. **Fix path:** encoding normalization pre-pass (ftfy or similar).

### Category B: Near-zero text (5 books — scan or encrypted, no usable text layer)
- **Origen** (85 words) — likely DRM or unusual encoding
- **N.T. Wright** (88 words) — scan without OCR layer
- **Hindu Pantheon** (84 words) — TIFF-converted scan
- **Manly Hall** (33K words) — has text but no chapter detection (ABBYY OCR quality)
- **Tempest FAX** (17K words) — Internet Archive scan, has some OCR text

Origen, Wright, and Hindu Pantheon are true zero-text books where Tesseract couldn't help. Hall and Tempest have text but chapter detection fails — these are chapter detection issues, not extraction issues.

## Recommendations

1. **Install google-genai and test Gemini** on the 4 NEEDS GEMINI books — these are the strongest candidates for Tier 2.5
2. **Encoding normalization** for the 3 encoding-issue books — `ftfy` package could clean these up
3. **Chapter detection improvement** for Hall and Tempest — they have extracted text but the chapter detector finds nothing
4. **Shakespeare Folios** need Gemini or Vision — 968 pages each, too large for Tesseract batch OCR
