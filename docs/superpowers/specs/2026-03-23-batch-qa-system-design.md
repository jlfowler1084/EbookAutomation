# Batch QA System Design Specification

**Project:** EbookAutomation
**Author:** Joe / Claude
**Created:** 2026-03-23
**Status:** Implemented (Phase 1 + Phase 2)
**Jira:** SCRUM-87

---

## Problem Statement

EbookAutomation processes books one at a time. When issues are found (chapter detection failures, quality regressions, encoding errors), they're debugged individually. No visibility into whether a bug affects 2 books or 20. Prioritization is based on "what broke last" rather than "what impacts the most books." Pattern detection is entirely manual.

## Solution

New `tools/batch_qa.py` orchestrator that processes a folder of books, collects structured per-book diagnostics, detects failure patterns across the batch, and produces an actionable report (JSON + Markdown).

PowerShell wrapper `Invoke-BatchQA` in the module provides the same interface pattern as other exported functions.

## Key Design Decisions

- **Explicit folder path required** - never touches inbox, completely separate from normal pipeline
- **Quick mode is default** - no API costs, no VQA. Just local processing
- **VQA requires `--vqa` flag** - never runs without explicit user approval
- **Concurrent processing** via `--parallel N` using ThreadPoolExecutor
- **Resume support** via `--resume <run_id>` - checks DB for completed books, skips them
- **Compare command** - `batch_qa.py compare <run1> <run2>` for tracking progress over time
- **Reports** written to `data/batch_reports/` as `.json` and `.md`

## Architecture

```
Batch QA Orchestrator (batch_qa.py)
  |
  +-- Scanner (scan_folder) --> Per-Book Pipeline Runner --> Diagnostics Collector
  |                                                              |
  |                                                              v
  +-- pattern_db (SQLite)                              Pattern Analyzer
  |                                                    (cluster & classify)
  |                                                              |
  |                                                              v
  |                                                    Report Generator
  |                                                    (.md + .json)
```

Calls `pdf_to_balabolka.py` directly (Python-to-Python subprocess) for text extraction, uses `test_pipeline.py`'s `extract_baseline_from_html()` for structural metrics, and optionally calls `visual_qa.py` for VQA scoring.

## Per-Book Diagnostics Schema

Each book produces a structured diagnostics record with sections:
- `source_classification` - source type, confidence, strategy selected
- `extraction` - success, path used, duration, errors, warnings
- `structure` - chapter/heading counts, word count, TOC presence
- `text_quality` - ligature splits, double spaces, encoding errors, footnotes
- `kindle_conversion` - attempted, success, KFX size, duration
- `visual_qa` - score, category scores, API cost, pass/fail
- `issues` - list of detected failure patterns
- `overall_status` - PASS / WARN / FAIL / ERROR

## Failure Pattern Detection

11 pre-defined failure patterns with lambda conditions:
- CHAPTER_DETECTION_ZERO, CHAPTER_DETECTION_BACKMATTER_ONLY
- LIGATURE_SPLITS_HIGH, FOOTNOTES_UNLINKED
- VQA_SCORE_LOW, ENCODING_ERRORS, EXTRACTION_FAILED
- KFX_FAILED, PAGE_NUMBERS_PRESENT, NO_FORMATTING_PRESERVED, DOUBLE_SPACES

Patterns are clustered by severity and cross-referenced with source metadata for correlation detection.

## CLI Interface

```
python tools/batch_qa.py <folder>                    # quick mode (HTML only)
python tools/batch_qa.py <folder> --vqa              # include visual QA scoring
python tools/batch_qa.py <folder> --limit 10         # first N books only
python tools/batch_qa.py <folder> --parallel 3       # concurrent processing
python tools/batch_qa.py <folder> --resume <run_id>  # resume interrupted batch
python tools/batch_qa.py list                        # list past batch runs
python tools/batch_qa.py compare <run1> <run2>       # diff two batch runs
python tools/batch_qa.py report <run_id>             # regenerate report from DB
```

## PowerShell Wrapper

```powershell
Invoke-BatchQA -FolderPath "F:\TestBooks"
Invoke-BatchQA -FolderPath "F:\TestBooks" -Quick -Limit 10
Invoke-BatchQA -FolderPath "F:\TestBooks" -Full -IncludeVQA
Invoke-BatchQA -FolderPath "F:\TestBooks" -Parallel 3
```

## Database Schema

New tables added to `ebook_patterns.db`:
- `batch_runs` - run_id, folder_path, summary stats, report paths, timestamps
- `batch_book_results` - per-book results linked to batch run

## Cost

| Mode | Per-Book | 50-Book Batch |
|------|----------|---------------|
| Quick (HTML only) | $0.00 | $0.00 |
| Full (HTML + KFX) | $0.00 | $0.00 |
| With VQA | ~$0.04 | ~$2.00 |

## Implementation Status

### Phase 1 - Core Batch Runner (Complete)
- [x] Folder scanning and format filtering
- [x] Per-book pipeline execution with try/catch isolation
- [x] Diagnostics collection (structured per-book JSON schema)
- [x] Results written to pattern_db via existing APIs
- [x] batch_runs table added to schema
- [x] JSON report output
- [x] Markdown summary report output
- [x] --quick mode (HTML only, no KFX/VQA)
- [x] --limit N for testing
- [x] --parallel N concurrent processing
- [x] --resume for interrupted batches
- [x] PowerShell Invoke-BatchQA wrapper
- [x] compare subcommand for diffing two batch runs

### Phase 2 - Pattern Analysis (Complete)
- [x] Rule-based FAILURE_PATTERNS detection (11 patterns)
- [x] Cluster aggregation and sorting
- [x] Correlation detection (source type, file size, VQA distribution)
- [x] Enhanced markdown report with failure clusters and observations
- [x] compare subcommand

### Phase 3 - Auto-Remediation (Future)
- [ ] Retry strategies per failure pattern
- [ ] Track retry outcomes (iteration > 1)
- [ ] "auto-fixed" vs "needs manual review" categories

### Phase 4 - Continuous QA Branch (Future)
- [ ] Git branch automation
- [ ] Proposed code fixes for known patterns
- [ ] Auto-generated PR descriptions
