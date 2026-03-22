# Two-Column PDF Detection Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten `detect_column_layout()` so it reliably identifies two-column academic PDFs (Hermeneia commentaries) while ignoring footnote apparatus and full-width headers that currently skew the detection statistics.

**Architecture:** Almost everything for this feature is already in place. `extract_text_columns()` (line 705), the routing in `extract_text()` (line 517), `force_columns` threading through all four functions, and the `--force-columns` CLI flag are all fully implemented. The only missing pieces are two filter conditions inside `detect_column_layout()` and a dependency doc entry. No new functions needed.

**Tech Stack:** Python 3.8+, PyMuPDF (`pymupdf`), existing `test_pipeline.py` regression harness.

---

## File Map

| File | Change |
|---|---|
| `tools/pdf_to_balabolka.py` | Modify `detect_column_layout()` lines 353–354 — add bottom-12% and full-width-block filters |
| `EbookAutomation_Dependencies.md` | Add `pymupdf` row to the Optional packages table (line 39) |

`tools/test_pipeline.py` — no code change. Ezekiel II is validated manually (see Task 3). It cannot be added to `TEST_CASES` as a hardcoded case until Prompt 2 (HTML variant), because `run_extraction(use_pdfminer=False)` produces `.txt` output and the test runner hard-requires an HTML file to validate against.

---

## Pre-flight check

**Working directory:** All commands assume CWD is the project root `F:\Projects\EbookAutomation\`. Run `cd F:\Projects\EbookAutomation` before executing any command below.

Before touching any code, confirm the current state of the function you're about to modify:

- [ ] Read `tools/pdf_to_balabolka.py` lines 349–360 and confirm the existing block filter matches:
  ```python
  text_blocks = [b for b in blocks
                 if b[6] == 0 and len((b[4] or '').strip()) >= 50]
  ```
  If the line is different, stop and investigate before proceeding.

- [ ] Confirm PyMuPDF is installed:
  ```
  python -c "import pymupdf; print(f'PyMuPDF {pymupdf.__version__} OK')"
  ```

---

## Task 1: Add detection filters to `detect_column_layout()`

**Files:**
- Modify: `tools/pdf_to_balabolka.py:353-354`

The two new filters (detection only — not applied inside `extract_text_columns()`):
1. **Bottom 12% exclusion** — footnote apparatus in Hermeneia-style commentaries sits at the bottom of each column in smaller font. These blocks are narrow and numerous; including them inflates both left and right counts, weakening the bimodal signal.
2. **Full-width block exclusion** — page headers and cross-column section titles span >70% of the page width. They register x0 values near the left margin, falsely boosting left-column counts.

- [ ] **Step 1: Make the edit**

Replace the current two-line filter:

```python
text_blocks = [b for b in blocks
               if b[6] == 0 and len((b[4] or '').strip()) >= 50]
```

With:

```python
page_height = page.rect.height
page_width_local = page.rect.width
text_blocks = [b for b in blocks
               if b[6] == 0                                     # text blocks only
               and len((b[4] or '').strip()) >= 50              # not too short
               and b[1] / page_height <= 0.88                   # exclude bottom 12% (footnotes)
               and (b[2] - b[0]) / page_width_local <= 0.70]   # exclude full-width blocks
```

The `page_height` and `page_width_local` variables are computed once per page, immediately before the list comprehension. The loop variable `page` is already in scope (it's the page object from `for pg_idx in sample_indices: page = doc[pg_idx]`).

- [ ] **Step 2: Verify the edit landed cleanly — read back lines 348–368**

Confirm:
- `page_height = page.rect.height` and `page_width_local = page.rect.width` appear before the list comprehension
- The four filter conditions are all present
- The indentation matches the surrounding code (4-space indent)
- No other lines in the function were accidentally changed

- [ ] **Step 3: Quick smoke test — single-column PDF detection**

Run detection on any single-column PDF already in the archive (Oil Kings, Genesis, etc.):

```
python -c "
import sys; sys.path.insert(0, 'tools')
from pdf_to_balabolka import detect_column_layout
import glob
pdf = glob.glob('archive/*Oil*Kings*.pdf')[0]
result = detect_column_layout(pdf, print)
print(result)
assert result['is_multicolumn'] == False, 'FAIL: single-column book incorrectly detected as multi-column'
print('PASS: single-column detection correct')
"
```

Expected output includes:
- Log line showing detection counts and confidence
- `is_multicolumn: False`
- `PASS` message

If the assertion fails, the new filters are incorrectly excluding too many blocks from a single-column page. Check that `page_width_local` is computed from the right object.

- [ ] **Step 4: Commit**

```
git add tools/pdf_to_balabolka.py
git commit -m "fix(SCRUM-62): tighten detect_column_layout filters to exclude footnotes and full-width headers"
```

---

## Task 2: Update `EbookAutomation_Dependencies.md`

**Files:**
- Modify: `EbookAutomation_Dependencies.md:38` (end of Optional table)

- [ ] **Step 1: Add the pymupdf row**

In the Optional packages table (after the `tkinter` row at line 38), add:

```
| **PyMuPDF** | `pymupdf` | Two-column PDF layout detection and column-ordered text extraction | `pdf_to_balabolka.py` → `detect_column_layout()`, `extract_text_columns()` | `pip install pymupdf` |
```

Also update the `Last updated` date at the top of the file to `2026-03-21`.

- [ ] **Step 2: Commit**

```
git add EbookAutomation_Dependencies.md
git commit -m "docs: add pymupdf to optional dependencies"
```

---

## Task 3: Validate against Ezekiel II (manual)

This is a verification step, not an automated test. The test harness requires HTML output; Ezekiel II with the PyMuPDF column path produces `.txt` and cannot be added to `TEST_CASES` until Prompt 2.

- [ ] **Step 1: Confirm Ezekiel II PDF is in the archive**

```
python -c "import glob; print(glob.glob('archive/*Ezekiel*II*.pdf') or 'NOT FOUND')"
```

If not found, skip the remaining steps in this task and note "Ezekiel II PDF not in archive — manual validation deferred."

- [ ] **Step 2: Run detection only — check confidence**

```
python -c "
import sys; sys.path.insert(0, 'tools')
from pdf_to_balabolka import detect_column_layout
import glob
pdf = glob.glob('archive/*Ezekiel*II*.pdf')[0]
result = detect_column_layout(pdf, print)
print(result)
print('Confidence:', result['confidence'])
print('Is multicolumn:', result['is_multicolumn'])
"
```

Expected: `is_multicolumn: True`, `confidence >= 0.6`. If confidence is below 0.6, the filters may still be too permissive — check the detection log line for the page-by-page breakdown.

- [ ] **Step 3: Run full extraction — Kindle plain-text mode**

```
python tools/pdf_to_balabolka.py --input "archive/<Ezekiel II filename>.pdf" --mode kindle
```

(Substitute the actual filename from Step 1.)

Expected: extraction completes, a `.txt` file appears in `output/kindle/`.

- [ ] **Step 4: Spot-check column ordering**

Open the output `.txt` file. Find a page with both columns of body commentary. Verify:
- The left column text appears before the right column text on the same page
- No interleaving (e.g., a line from column A, then a line from column B, then back to A)
- Hebrew text or transliteration blocks (if any) appear in correct position relative to surrounding commentary

If ordering looks correct: this task is done. If ordering is wrong, check the `is_multicolumn` result from Step 2 — if detection is failing, try re-running with `--force-columns`.

---

## Task 4: Regression tests

- [ ] **Step 1: Run full regression suite — all existing test cases**

```
python tools/test_pipeline.py --quick
```

Expected: Oil Kings, Genesis, Mexico, Brother of Jesus, Dionysius all PASS. None of these books should trigger the PyMuPDF column path — if the detection log shows "Multi-column layout detected" for any single-column book, there is a regression in the filter change.

- [ ] **Step 2: If any test fails — investigate before reverting**

Do not revert the filter change without understanding the failure. Run detection on the failing book:

```
python -c "
import sys; sys.path.insert(0, 'tools')
from pdf_to_balabolka import detect_column_layout
import glob
pdf = glob.glob('archive/*<BookName>*.pdf')[0]
result = detect_column_layout(pdf, print)
print(result)
"
```

If confidence is suspiciously high (> 0.4) for a known single-column book, the `page_width_local` variable may be referencing the wrong scope. Check that it is reassigned at the start of each page's loop iteration.

- [ ] **Step 3: Final commit (if any debug changes were made)**

If no changes were made in Task 4, no commit needed. If you fixed a bug found during testing, commit with:

```
git add tools/pdf_to_balabolka.py
git commit -m "fix: correct detection filter scope issue found in regression"
```
