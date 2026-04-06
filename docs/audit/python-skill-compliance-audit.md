# Python Skill Compliance Audit — EbookAutomation

**Date:** 2026-04-05
**Skills:** python-core (INFRA-108), python-architecture (INFRA-109)
**Ticket:** SCRUM-269
**Auditor:** Claude (read-only scan, no files modified)

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total `.py` files scanned | 27 |
| Total lines of Python | 33,443 |
| Total functions | 729 |
| Bare `except:` (no type) | **0** |
| Silent `except Exception` (no logging) | 80 |
| `except Exception as e` (with logging) | 81 |
| Functions with type hints | 30 (4.1%) |
| Functions without type hints | 699 (95.9%) |
| Functions with docstrings | 434 (59.5%) |
| Functions without docstrings | 295 (40.5%) |
| `os.path` usages | 173 across 20 files |
| `pathlib` imports | 22 across 21 files |

**Bottom line:** The codebase has **zero bare `except:` clauses** — the highest-severity
violation category is empty. The primary finding is **80 silent `except Exception` blocks**
(pass/continue without logging), concentrated in `pdf_to_balabolka.py` (24 instances) and
`preflight_analysis.py` (9 instances). Most are in PDF-probing loops where individual
failures are expected, but ~5 are in significant contexts where logging would aid debugging.

The codebase is a mature brownfield project with consistent internal conventions. The
python-architecture skill's "Greenfield vs Brownfield" guidance applies: no architectural
restructuring is warranted. Modernization opportunities (type hints, pathlib migration) are
substantial but low-urgency and should be tackled incrementally via scoped tickets.

---

## Findings by Severity

### Violations (fix regardless of context)

**Zero bare `except:` clauses found.** All 161 exception handlers specify `Exception` or a
more specific type.

**Silent exception swallowing in significant contexts (5 instances):**

These `except Exception: pass/continue` blocks are in non-trivial contexts where a silent
failure could mask real problems. Each should add minimal logging.

| # | File | Line | Context | Impact |
|---|------|------|---------|--------|
| V1 | pdf_to_balabolka.py | 70 | `_load_api_model()` config load — silently falls back to defaults | Config errors invisible; could cause unexpected model selection |
| V2 | pdf_to_balabolka.py | 877 | Bookmark extraction loop — silently skips broken bookmarks | Missing bookmarks not diagnosed; affects chapter detection |
| V3 | pdf_to_balabolka.py | 1280 | Image format conversion — fallback chain but no logging | Debugging image extraction failures requires guesswork |
| V4 | pdf_to_balabolka.py | 1346 | Caption extraction — silently skips on failure | Non-critical, but could mask systematic parsing bugs |
| V5 | preflight_analysis.py | 157 | Text quality scoring — silently skips page score | Quality assessment silently degrades without indication |

**Recommended fix pattern:**
```python
# Before (violation):
except Exception:
    pass

# After (compliant):
except Exception as e:
    log(f"  [warn] caption extraction failed: {e}")
```

**Estimated effort:** ~1 hour. Five one-line changes + test run.

---

### Silent Exception Handlers in PDF-Probing Loops (75 instances)

These are `except Exception: pass/continue` blocks in tight loops that probe PDF internal
objects (page text extraction, annotation inspection, image stream detection). Individual
item failures are expected when traversing PDF structures. While they technically violate the
"log every exception" rule, they are **pragmatically acceptable** because:

1. The function degrades gracefully (returns partial results)
2. Logging every PDF object failure would be noisy and unhelpful
3. The pattern is universal in PDF processing libraries

**Recommendation:** Leave as-is. If debugging a specific PDF, add temporary verbose logging
rather than permanent per-item logging. Consider a debug-level logger for opt-in verbosity
in a future modernization pass.

**Breakdown by file:**

| File | Silent `except Exception` count | Context |
|------|--------------------------------|---------|
| pdf_to_balabolka.py | 24 | PDF object traversal, image extraction, bookmark parsing |
| batch_qa.py | 19 | QA metric collection, extraction fallbacks |
| preflight_analysis.py | 9 | PDF structure probing, page sampling |
| pattern_db.py | 8 | Database operations, hash computation |
| visual_qa.py | 4 | PDF rendering, bookmark detection |
| classify_source.py | 4 | PDF reader fallback chain |
| gemini_ocr.py | 2 | OCR fallback |
| send_to_kindle.py | 3 | Device detection, conversion fallback |
| detect_headings_font.py | 1 | Font analysis |
| scan-image-density.py | 1 | Image counting |

---

### Modernization Opportunities (planned effort)

These are improvements that would bring the codebase closer to python-core standards but
are **not violations**. Each is a separate, scoped effort — not drive-by work.

#### M1. Type Hints — 699 functions (95.9%) lack annotations

| File | Functions | With Hints | Without |
|------|-----------|------------|---------|
| pdf_to_balabolka.py | 91 | 0 | 91 |
| pattern_db.py | 77 | 0 | 77 |
| batch_qa.py | 31 | 0 | 31 |
| test_pipeline.py | 57 | 0 | 57 |
| detect_headings_font.py | 13 | ~2 | ~11 |
| preflight_analysis.py | 20 | 0 | 20 |
| email_to_kindle.py | 15 | ~5 | ~10 |
| fix_engine.py | 12 | 0 | 12 |
| visual_qa.py | 14 | 0 | 14 |
| foh_scraper.py | 12 | 0 | 12 |
| chapter_alignment.py | 8 | 0 | 8 |
| classify_source.py | 8 | 0 | 8 |
| filter_content.py | 10 | 0 | 10 |
| foh_parser.py | 6 | 0 | 6 |
| gemini_ocr.py | 4 | 0 | 4 |
| Other test/utility files | ~351 | ~23 | ~328 |

**Estimated effort:** 3–5 sessions. Start with public API functions (those imported by
other modules) for maximum value. Use `mypy --strict` on individual files.

**Recommended batch order:**
1. Shared utilities first: `classify_source.py`, `filter_content.py`, `chapter_alignment.py`
2. Core engine: `pdf_to_balabolka.py` (public functions only — internal helpers later)
3. QA tooling: `batch_qa.py`, `test_pipeline.py`, `visual_qa.py`
4. Feature modules: `email_to_kindle.py`, `gemini_ocr.py`, `send_to_kindle.py`

#### M2. Path Handling — 173 `os.path` usages across 20 files

Most files already import `pathlib` (21 of 27 files) but continue using `os.path` for
legacy operations. This creates inconsistency but is **not a functional problem**.

| File | os.path count | Also uses pathlib? |
|------|---------------|-------------------|
| pdf_to_balabolka.py | 49 | Yes |
| email_to_kindle.py | 38 | Yes |
| batch_qa.py | 17 | Yes |
| test_pipeline.py | 17 | Yes |
| pattern_db.py | 14 | Yes |
| test_metadata.py | 12 | Yes |
| visual_qa.py | 8 | Yes |
| Other files | 18 | Mixed |

**Estimated effort:** 2–3 sessions. Mechanical replacement but requires testing each file.
Lower priority than type hints — `os.path` works fine.

#### M3. Docstrings — 295 functions (40.5%) lack docstrings

434 functions already have docstrings (59.5%), which is reasonable for a brownfield project.
Missing docstrings are concentrated in:

- Internal helper functions (prefixed with `_`)
- Test functions (purpose is clear from test names)
- Small utility functions with self-evident behavior

**Estimated effort:** 2 sessions. Focus on public functions and functions with
non-obvious behavior. Skip test functions and trivial helpers.

#### M4. Oversized Functions — 4 functions exceed 200 lines

| File | Function | Lines | Phases |
|------|----------|-------|--------|
| pdf_to_balabolka.py | `fix_ocr_artifacts()` | ~1,775 | 9 distinct phases |
| pdf_to_balabolka.py | `format_paragraphs_as_html()` | ~1,273 | 20+ formatting phases |
| pdf_to_balabolka.py | `process_kindle_html()` | ~690 | Extraction, HTML gen, conversion |
| batch_qa.py | `run_batch()` | ~216 | Scan, process, analyze, report |

**Estimated effort:** 2–3 sessions. Extract phases into named helper functions.
High regression risk — requires careful testing after each extraction.

**Recommendation:** Tackle only when a bug fix or feature requires touching these functions.
Don't refactor speculatively.

#### M5. Data Structures — plain dicts as data containers

Several functions return or pass plain dicts with implicit schemas:

- `pdf_to_balabolka.py`: Extraction results, PDF analysis, page metadata
- `batch_qa.py`: QA metrics, book results, report data
- `preflight_analysis.py`: Analysis results, viability assessments

**Estimated effort:** 2 sessions. Define `@dataclass` types for major return values.
Moderate regression risk — all consumers must be updated.

**Recommendation:** Introduce dataclasses when writing new modules or when a refactoring
ticket targets a specific return type. Don't convert working dicts in unrelated work.

#### M6. Unused Logger Import — 1 instance

| File | Line | Issue |
|------|------|-------|
| batch_qa.py | ~25,76 | Imports `logging` and creates `logger = logging.getLogger("batch_qa")` but never calls it |

**Fix:** Either remove the unused import or adopt `logger.warning()` for non-interactive
error output. Trivial change.

#### M7. Hardcoded Path — 1 instance

| File | Line | Issue |
|------|------|-------|
| visual_qa.py | ~721 | `r"C:\Program Files\Calibre2\ebook-convert.exe"` hardcoded |

**Fix:** Move to `settings.json` or use dynamic lookup. Low priority — only affects
machines where Calibre is installed in a non-default location.

---

### Recognized Patterns (leave alone)

These are documented in the python-core skill's "Recognized Legacy Patterns" table and are
intentional design choices for this codebase.

| Pattern | Files | Count | Notes |
|---------|-------|-------|-------|
| `log=print` callback parameter | 5 | 8 | Routes output flexibly for CLI/GUI dual use |
| `HAS_MODULE` feature flags | 2 | 17 | `batch_qa.py`, `test_pipeline.py` — optional dependency handling |
| `sys.path.insert(0, ...)` | 15 | 23 | Sibling imports in flat project structure |
| `sys.stdout.reconfigure(encoding='utf-8')` | 18 | 36 | Windows console encoding compatibility |
| `settings.json` config loading | 6 | ~10 | Simple JSON config pattern — works fine |
| `print()` in CLI tools | 20+ | ~100+ | User-facing interactive output — not debug spew |
| `except Exception` with logging in fallback chains | 14 | 81 | Deliberate graceful degradation — all log the error |
| `os.path` in existing code | 20 | 173 | Works fine; migration is opt-in modernization |
| No type hints on existing functions | 27 | 699 | Retroactive annotation is a separate effort |
| Plain dicts as data containers | 10+ | widespread | Works fine; introduce dataclasses only in new code |

---

## Per-File Summary

| File | Lines | Funcs | Violations | Silent Except | Modernization | Recognized | Score |
|------|-------|-------|------------|---------------|---------------|------------|-------|
| pdf_to_balabolka.py | 13,791 | 91 | 4 | 24 | Type hints, pathlib, docstrings, oversized funcs, dataclasses | log callback, sys.path, UTF-8, fallback chains, print CLI | C+ |
| pattern_db.py | 3,494 | 77 | 0 | 8 | Type hints, docstrings, parameter overload | sys.path, UTF-8, settings.json, HAS_MODULE | B |
| batch_qa.py | 3,005 | 31 | 0 | 19 | Type hints, docstrings, oversized func, unused logger | sys.path, UTF-8, settings.json, HAS_MODULE, print CLI | B |
| test_pipeline.py | 1,686 | 57 | 0 | 4 | Type hints, docstrings | sys.path, UTF-8, HAS_MODULE, print CLI | B |
| detect_headings_font.py | 1,146 | 13 | 0 | 1 | Type hints, docstrings, magic numbers | log callback, UTF-8, print CLI | B+ |
| preflight_analysis.py | 1,124 | 20 | 1 | 9 | Type hints, docstrings | sys.path, UTF-8, settings.json, fallback chains | B- |
| email_to_kindle.py | 928 | 15 | 0 | 2 | Type hints (partial), pathlib | UTF-8, print CLI | B+ |
| fix_engine.py | 882 | 12 | 0 | 0 | Type hints, docstrings | log callback, UTF-8 | A- |
| visual_qa.py | 871 | 14 | 0 | 4 | Type hints, hardcoded path | UTF-8, settings.json, fallback chains | B |
| foh_scraper.py | 651 | 12 | 0 | 2 | Type hints, pathlib | UTF-8, fallback chains, print CLI | B+ |
| test_voice_tags.py | 605 | 20 | 0 | 0 | Type hints | log callback, sys.path | A- |
| test_metadata.py | 531 | 16 | 0 | 0 | Type hints | sys.path | A- |
| test_preflight.py | 499 | 20 | 0 | 0 | Type hints | sys.path, UTF-8 | A- |
| classify_source.py | 489 | 8 | 0 | 4 | Type hints, pathlib | UTF-8, fallback chains | B |
| chapter_alignment.py | 480 | 8 | 0 | 2 | Type hints, docstrings | log callback, UTF-8 | B+ |
| filter_content.py | 431 | 10 | 0 | 0 | Type hints | UTF-8 | A- |
| foh_parser.py | 356 | 6 | 0 | 0 | Type hints, docstrings | print CLI | B+ |
| gemini_ocr.py | 353 | 4 | 0 | 2 | Type hints | UTF-8, fallback chains | B+ |
| validate_against_baseline.py | 332 | 5 | 0 | 0 | Type hints | sys.path, UTF-8 | A- |
| test_chapter_alignment.py | 300 | 12 | 0 | 0 | Type hints | sys.path, UTF-8 | A- |
| send_to_kindle.py | 256 | 3 | 0 | 3 | Type hints | fallback chains | B |
| scan-image-density.py | 226 | 2 | 0 | 1 | Type hints, pathlib | UTF-8, print CLI | B+ |
| import_vqa_reports.py | 226 | 4 | 0 | 0 | Type hints | sys.path, UTF-8 | A- |
| debug_diagnostic.py | 225 | 5 | 0 | 0 | Type hints | print CLI | B+ |
| test_filter_content.py | 217 | 11 | 0 | 0 | Type hints | sys.path | A- |
| recapture_baselines.py | 193 | 2 | 0 | 0 | Type hints | sys.path, UTF-8 | A- |
| test_footnotes.py | 171 | 7 | 0 | 0 | Type hints | sys.path | A- |

**Score guide:** A = fully compliant for new code standards; B = working brownfield code
with modernization opportunities; C = has violations that should be addressed.

---

## Recommendations

### Batch 1: Fix Violations (1 session, ~1 hour)
**Ticket scope:** Add logging to 5 silent exception handlers in significant contexts.
- `pdf_to_balabolka.py`: lines 70, 877, 1280, 1346
- `preflight_analysis.py`: line 157
- **Risk:** Minimal — adds logging only, no logic changes.
- **Dependencies:** None.
- **Test plan:** Run `test_pipeline.py` against all test cases.

### Batch 2: Type Hints for Shared Utilities (2–3 sessions)
**Ticket scope:** Add type annotations to public API functions in shared modules.
- Priority files: `classify_source.py`, `filter_content.py`, `chapter_alignment.py`,
  `gemini_ocr.py`, `send_to_kindle.py`
- ~40 functions total, all under 500 lines.
- **Risk:** Low — type hints don't change runtime behavior.
- **Dependencies:** None.

### Batch 3: Type Hints for Core Engine (2–3 sessions)
**Ticket scope:** Add type annotations to public functions in `pdf_to_balabolka.py`.
- ~20 public functions (skip internal `_` helpers initially).
- **Risk:** Low — annotations only.
- **Dependencies:** Batch 2 recommended first (establishes patterns).

### Batch 4: Pathlib Migration (2–3 sessions)
**Ticket scope:** Replace `os.path` with `pathlib.Path` in files that already import pathlib.
- Start with smaller files (< 500 lines) to establish patterns.
- **Risk:** Medium — path handling changes can affect file operations.
- **Dependencies:** Batches 2–3 recommended first.
- **Test plan:** Full regression suite after each file.

### Batch 5: Oversized Function Decomposition (3–4 sessions)
**Ticket scope:** Extract phases from oversized functions in `pdf_to_balabolka.py`.
- `fix_ocr_artifacts()` → 9 helper functions
- `format_paragraphs_as_html()` → 10+ helper functions
- **Risk:** HIGH — these are the most regression-sensitive functions in the codebase.
- **Dependencies:** Type hints on these functions (Batch 3) recommended first.
- **Recommendation:** Only tackle when a bug fix or feature requires touching these functions.

### Not Recommended
- Full codebase restructuring to src/ layout (working flat structure is fine)
- Migrating settings.json to pydantic-settings (existing config works)
- Adding dataclasses to existing dict-based return values (introduce only in new code)
- Converting print() to logging in CLI tools (print is intentional for user output)

---

## Architecture Assessment (python-architecture skill)

The EbookAutomation project is a **brownfield CLI automation suite** with a flat project
structure. Per the python-architecture skill's "Greenfield vs Brownfield" guidance:

- **No restructuring warranted.** The flat layout with `tools/`, `tests/`, and
  `processing/` directories is functional and well-understood.
- **No architectural patterns needed.** Repository pattern, service layers, and domain
  modeling are designed for application servers — not CLI pipeline tools.
- **Configuration via settings.json is fine.** No need to migrate to pydantic-settings.
- **Test organization is adequate.** Tests live alongside tools with clear naming.

The project correctly uses the patterns appropriate for its nature: a PowerShell + Python
automation suite, not a web application or microservice.

---

*Report generated by Claude (read-only audit). No files were modified.*
