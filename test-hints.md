# Test Hints — EbookAutomation

## How to Use
1. Read the Discord update for the Jira ticket ID (project key: `EB`)
2. Look up the ticket in Jira for full context (site: `jlfowler1084.atlassian.net`)
3. Find the matching feature area below
4. Follow the verification steps
5. Report results back to the project Discord channel

## Access
- Project files: `F:\Projects\EbookAutomation\` (or via VMware Shared Folders at `/Volumes/VMware Shared Folders/Projects/EbookAutomation/`)
- Python: `C:\Users\Joe\AppData\Local\Programs\Python\Python312\python.exe`
- Jira project: `EB` on `jlfowler1084.atlassian.net` (cloud ID: `24efad1f-45cf-4e98-a2f1-f3c25e0b8cd0`)

## Prerequisites
- Python 3.12 installed with pdfminer.six, PyMuPDF, pdfplumber, ebooklib, beautifulsoup4
- Calibre installed at `C:\Program Files\Calibre2\`
- Tesseract 5.5.0 at `C:\Program Files\Tesseract-OCR\tesseract.exe`
- Working directory: `F:\Projects\EbookAutomation\`

---

## Features

### 1. Pipeline Regression Test Suite (PRIMARY — run after ANY code change)

The 41-test regression suite is the single most important gate. Oil Kings is the primary canary with 17 hardcoded checks.

**Quick mode (HTML only, ~30-60s):**
```powershell
cd F:\Projects\EbookAutomation
python tools/test_pipeline.py --quick
```

**Full mode (HTML + KFX conversion):**
```powershell
python tools/test_pipeline.py
```

**Single book:**
```powershell
python tools/test_pipeline.py "Oil Kings"
```

**List available tests:**
```powershell
python tools/test_pipeline.py --list
```

**Expected results:**
- 41/41 tests should pass (exit code 0 for all-pass, 1 if any failures)
- Exit code 1 alone is NOT a regression signal — check the specific failure count
- Oil Kings must pass all 17 checks: h1/h2/h3 counts, heading content, blockquotes, em tags, ligature splits, front matter detection
- Core regression books: Oil Kings, Mexico Illicit, Ezekiel II, Burge, Genesis, Fruchtenbaum

**What to report:**
- Total pass/fail count (e.g., "41/41 passed" or "39/41 — 2 failures")
- Names of any failing books
- Specific failing checks (the test output prints `FAIL: <check description>`)

---

### 2. Voice Tag Tests

75 tests covering TTS voice tags, scene breaks, emphatic closers, chapter/part silence, and inline SAPI XML.

**Run:**
```powershell
cd F:\Projects\EbookAutomation
python -m pytest tools/test_voice_tags.py -v
```

**Expected:** 75/75 passing

**Key areas tested:**
- Scene break detection (asterisks, hashes, dashes, em-dashes, asterism unicode)
- Emphatic closer detection (exclamation marks at paragraph end)
- Chapter and part silence insertion (2000ms chapter, 3000ms part)
- Scene break silence (1500ms)
- Inline silence tags (must be inline with text, NOT standalone — balcon ignores standalone SAPI XML)
- Em dash pause injection (200ms)
- Rate adjustment for emphatic closers

**What to report:**
- Pass/fail count
- Any failing test names

---

### 3. Batch QA System

Processes folders of ebooks through the pipeline, collects diagnostics, detects failure patterns, generates HTML dashboard with SVG charts and trend heatmaps.

**Quick batch run (HTML only):**
```powershell
python tools/batch_qa.py "F:\Books" --quick --limit 10
```

**Full batch with KFX:**
```powershell
python tools/batch_qa.py "F:\Books" --full --limit 10
```

**With Visual QA (costs ~$0.04/book via Claude API):**
```powershell
python tools/batch_qa.py "F:\Books" --full --vqa --limit 5
```

**List past batch runs:**
```powershell
python tools/batch_qa.py list
```

**Compare two runs:**
```powershell
python tools/batch_qa.py compare <run_id_1> <run_id_2>
```

**Expected results:**
- Reports generated in `data/batch_reports/` (JSON + MD + HTML dashboard)
- Current batch pass rate: ~70-75%
- Each book gets PASS / WARN / FAIL / ERROR status
- HTML dashboard should render with SVG charts and trend heatmap

**What to report:**
- Total books processed, pass/warn/fail/error counts
- Any ERROR-status books (pipeline crashes)
- Pass rate percentage
- New failure patterns not seen before

---

### 4. Column Detection

Tests PyMuPDF column-aware extraction for double-column academic PDFs.

**Run column detection test:**
```powershell
powershell -File tools/test_columns.ps1
```

**Expected:**
- Ezekiel II routes to `pymupdf_columns` extraction path
- 25/28 books should correctly route to `pymupdf_columns` when applicable
- Three borderline cases (NIPS AlexNet 40%, Four_Wave_Mixing 50%, Galactic_Constellations 50%) are known and accepted

**What to report:**
- Number of books correctly routing
- Any books that changed routing since last run

---

### 5. Preflight Analysis Tests

Tests the recommendation engine that analyzes PDFs and suggests extraction strategies.

**Run:**
```powershell
python -m pytest tools/test_preflight.py -v
```

**Expected:** All tests pass (12+ tests covering classification, text quality, chapter assessment, confidence calculation, graceful failure)

**What to report:**
- Pass/fail count
- Any failures in confidence calculation or strategy recommendation

---

### 6. Chapter Alignment Tests

Verifies bookmark-to-heading matching for Kindle TOC generation.

**Run:**
```powershell
python -m pytest tools/test_chapter_alignment.py -v
```

**Expected:** All tests pass (heading extraction, ordered matching, non-PDF skip)

**What to report:**
- Pass/fail count

---

### 7. Content Filter Tests

Tests front/back matter removal, TOC stripping, and content classification.

**Run:**
```powershell
python -m pytest tools/test_filter_content.py -v
```

**Expected:** All tests pass

---

### 8. Metadata Tests

Tests pattern_db metadata storage/retrieval and email_to_kindle metadata injection.

**Run:**
```powershell
python -m pytest tools/test_metadata.py -v
```

**Expected:** All tests pass

---

### 9. Single Book End-to-End (Kindle path)

Verifies that a PDF converts through the full pipeline to KFX.

**Run (using Oil Kings as the canonical test):**
```powershell
Import-Module F:\Projects\EbookAutomation\module\EbookAutomation.psm1 -Force
Convert-ToKindle -InputFile "F:\Projects\EbookAutomation\archive\The_Oil_Kings_by_Andrew_Scott_Cooper.pdf" -UsePdfminer
```

**Expected:**
- KFX file produced in `output/kindle/`
- Log entries show extraction path (pdfminer), heading detection, chapter hints
- No Python exceptions in the log
- Output file > 100 KB

**What to report:**
- Whether KFX was produced
- File size
- Any errors or warnings in the log

---

### 10. Single Book End-to-End (TTS/Balabolka path)

Verifies TTS text output with voice tags and silence markers.

**Run:**
```powershell
Import-Module F:\Projects\EbookAutomation\module\EbookAutomation.psm1 -Force
Convert-ToTTS -InputFile "F:\Projects\EbookAutomation\archive\The_Oil_Kings_by_Andrew_Scott_Cooper.pdf"
```

**Expected:**
- TXT file produced in `output/tts/`
- ALL-CAPS chapter headings present
- Silence tags present between chapters (look for `<silence msec=`)
- Voice tags present if applicable
- No standalone SAPI XML tags (must be inline with adjacent text)

**What to report:**
- Whether TXT was produced
- Presence of chapter headings, silence tags, voice tags
- Any encoding artifacts or garbled text

---

### 11. Extraction Cache (Smart Cache)

Verifies SHA-256 extraction cache with pipeline version tracking.

**Verify cache is functional:**
```powershell
python tools/extract_tts_text.py --input "F:\Projects\EbookAutomation\archive\The_Oil_Kings_by_Andrew_Scott_Cooper.pdf" --mode kindle --html-extraction
```

**Run a second time — should hit cache:**
```powershell
python tools/extract_tts_text.py --input "F:\Projects\EbookAutomation\archive\The_Oil_Kings_by_Andrew_Scott_Cooper.pdf" --mode kindle --html-extraction
```

**Expected:**
- First run: extracts from PDF (slower)
- Second run: loads from cache (faster, should see "Using cached extraction" in output)
- If pipeline code changed between runs, cache should be invalidated (pipeline_version mismatch)
- Cache includes `image_count` column (EB-79)

**What to report:**
- Whether cache hit occurred on second run
- Whether stale cache auto-rebuilds after code changes

---

### 12. Pattern Database Health

Verifies the SQLite pattern database schema and tables.

**Run health check:**
```powershell
python tools/pattern_db.py health-check
```

**Expected:**
- All required tables exist (book_overrides, extraction_cache, batch_runs, batch_results, book_metadata, conversion_history)
- No schema errors
- `image_count` column present in extraction_cache

---

### 13. Merge-ToKindle (Multi-file output)

Verifies the merge functionality that combines multiple output files (EB-76).

**Run:**
```powershell
Import-Module F:\Projects\EbookAutomation\module\EbookAutomation.psm1 -Force
# Merge-ToKindle is available as an exported function
Get-Command Merge-ToKindle
```

**Expected:**
- Function exists and is exported from the module
- Should combine chapter files into single output when applicable

---

## Quick Smoke Test (run all critical checks in ~2 minutes)

For a fast post-change validation, run these three commands in sequence:

```powershell
cd F:\Projects\EbookAutomation

# 1. Pipeline regression (quick mode)
python tools/test_pipeline.py --quick

# 2. Voice tag tests
python -m pytest tools/test_voice_tags.py -v --tb=short

# 3. Pattern DB health
python tools/pattern_db.py health-check
```

**Pass criteria:** 41/41 pipeline, 75/75 voice tags, healthy DB = green light.

---

## What NOT to Test Automatically

- **Visual QA (VQA):** Costs ~$0.04/book via Claude API. Only run for major milestones or explicit requests. Never auto-include `--vqa` in batch runs.
- **Full KFX conversion:** Slower (~60s/book via Calibre). Use `--quick` for routine checks.
- **NKJV Study Bible stress test:** 2,266 pages, 222 MB — only for major chunking or memory changes.
- **Gemini Flash OCR:** Paid tier (~$0.50/book). Explicit opt-in only.

---

## Interpreting Results

| Signal | Meaning |
|--------|---------|
| 41/41 pipeline + 75/75 voice tags | Safe to merge |
| Pipeline exit code 1 | Check failure count — may be pre-existing |
| Oil Kings fails any check | Likely regression — investigate immediately |
| Batch pass rate drops below 65% | Significant regression in extraction quality |
| New ERROR-status books in batch | Pipeline crash — needs a bug ticket |
| Cache not invalidating after code change | Check SHA-256 pipeline_version in extraction_cache |

---

## Ticket Cross-Reference

Recent shipped tickets that affect test expectations:
- **EB-74:** Large PDF chunking (200-page chunks)
- **EB-76:** Merge-ToKindle
- **EB-77:** Em dash pauses in TTS
- **EB-78:** Voice diagnostics
- **EB-79:** Smart cache with image_count column
- **EB-81:** Inline silence tags (standalone SAPI XML fix)
