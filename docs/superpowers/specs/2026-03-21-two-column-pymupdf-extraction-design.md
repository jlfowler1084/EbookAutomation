# SCRUM-62: Two-Column Academic PDF Extraction via PyMuPDF — Design Spec

**Date:** 2026-03-21
**Revision:** 2 (post-review fixes)
**Scope:** Prompt 1 — plain-text path only (Balabolka + Kindle TXT modes). HTML variant is a follow-up prompt.
**Ticket:** SCRUM-62 (parent: SCRUM-5 EA: PDF Text Extraction Pipeline)
**File:** `tools/pdf_to_balabolka.py`

---

## Problem

Two-column academic PDFs (Hermeneia commentaries, journal articles, dissertations) produce
interleaved text when extracted through pdfminer or pypdf: text from column A and column B
get mixed at the same reading position, producing unreadable output.

Canonical test case: *Ezekiel II* (Hermeneia series) — structured PDF, text extracts but
column ordering is wrong.

---

## Architecture (Prompt 1 scope)

### Existing infrastructure to reuse

`detect_column_layout(pdf_path, log, sample_pages=8)` **already exists** at line 306 of
`pdf_to_balabolka.py`. It uses `import pymupdf`, samples evenly-spaced body pages, builds
a 20-bin x0 histogram, detects left/right peak gap ≥ 15% of page width, and returns:

```python
{
    'is_multicolumn': bool,      # confidence >= 0.6
    'num_columns': int,          # 1 or 2
    'column_boundaries': list,   # [(x_start, x_end), ...] — median across sampled pages
    'confidence': float,
    'page_width': float,
}
```

It already filters `block_type == 0` (text only) and `len(text.strip()) >= 50`.

### Changes required

1. **Modify `detect_column_layout()`** — add two missing filters to the per-page block
   filtering step (detection only, not extraction):
   - Exclude blocks where `(b[1] / page.rect.height) > 0.88` — bottom 12% of page
     (footnote apparatus in Hermeneia-style commentaries)
   - Exclude blocks where `(b[2] - b[0]) / page.rect.width > 0.70` — full-width blocks
     (page headers, cross-column titles that span both columns)

2. **Create `_extract_with_pymupdf_columns()`** — new function that extracts text in
   correct column reading order.

3. **Modify `extract_text()`** — insert PyMuPDF routing before the existing pypdf path.

4. **Thread `force_columns=False`** through three function signatures.

5. **Add `--force-columns` CLI flag** in `run_cli()`.

---

## Modified `detect_column_layout()`

Add the two filters to the existing block-filtering line (currently line 353–354):

**Current:**
```python
text_blocks = [b for b in blocks
               if b[6] == 0 and len((b[4] or '').strip()) >= 50]
```

**Becomes:**
```python
page_height = page.rect.height
page_width_local = page.rect.width
text_blocks = [b for b in blocks
               if b[6] == 0                                    # text blocks only
               and len((b[4] or '').strip()) >= 50             # not too short
               and b[1] / page_height <= 0.88                  # exclude bottom 12% (footnotes)
               and (b[2] - b[0]) / page_width_local <= 0.70]   # exclude full-width blocks
```

No other changes to the function. Return signature unchanged.

**Existing short-PDF guard (unchanged):** The function already handles short PDFs at lines
335–338:
```python
n_sample = min(sample_pages, total_pages - start_page)
if n_sample <= 0:
    doc.close()
    return {'is_multicolumn': False, 'num_columns': 1, ...}
```
Adding the two new filters does not affect this guard. The new filter conditions are applied
inside the per-page loop, not at the sampling stage.

---

## New `_extract_with_pymupdf_columns(pdf_path, log) → str`

### Purpose

Extracts text in correct column reading order: top full-width headers → left column
top-to-bottom → right column top-to-bottom → bottom full-width footers.

Returns `"\n".join(pages)` where each page is `"<<PAGE:{n}>>\n{text}"` — identical
contract to `_extract_with_pdfminer`, drops directly into the existing `clean_and_join()`
pipeline unchanged.

### Algorithm

```python
def _extract_with_pymupdf_columns(pdf_path, log):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    all_pages = []

    for pg_idx in range(total_pages):
        page = doc[pg_idx]
        page_w = page.rect.width
        page_mid = page_w / 2.0
        blocks = page.get_text("blocks")

        top_wide = []
        left_col = []
        right_col = []
        bottom_wide = []

        # Classify all text blocks
        col_blocks = []
        wide_blocks = []
        for b in blocks:
            if b[6] != 0:                         # skip image/non-text blocks
                continue
            text = (b[4] or '').strip()
            if not text:
                continue
            span_ratio = (b[2] - b[0]) / page_w
            if span_ratio > 0.70:
                wide_blocks.append(b)
            else:
                col_blocks.append(b)

        # Find y-position where column content begins
        if col_blocks:
            min_col_y0 = min(b[1] for b in col_blocks)
        else:
            # No column blocks on this page (full-page element, blank page, etc.)
            # Treat all wide blocks as top_wide and emit in y0 order
            all_wide_sorted = sorted(wide_blocks, key=lambda b: b[1])
            page_text = "\n".join((b[4] or '').strip() for b in all_wide_sorted if (b[4] or '').strip())
            if page_text:
                all_pages.append(f"<<PAGE:{pg_idx + 1}>>\n{page_text}")
            continue

        # Partition wide blocks relative to where column content starts.
        # top_wide: wide blocks ABOVE the first column line (page headers, cross-column
        #   titles at top of page).
        # bottom_wide: wide blocks AT OR BELOW the first column line — this includes
        #   footnote apparatus AND mid-page cross-column headings whose y0 >= min_col_y0.
        # Known limitation: a cross-column heading that appears mid-page (y0 > min_col_y0)
        # will be emitted after both columns in bottom_wide. For Balabolka/TTS this is
        # acceptable since clean_and_join() handles heading detection independently of
        # position. This edge case is deferred to the HTML variant (Prompt 2) where
        # correct heading placement in the output structure matters.
        for b in wide_blocks:
            if b[1] < min_col_y0:
                top_wide.append(b)
            else:
                bottom_wide.append(b)

        # Assign column blocks to left or right
        for b in col_blocks:
            x_mid = (b[0] + b[2]) / 2.0
            if x_mid < page_mid:
                left_col.append(b)
            else:
                right_col.append(b)

        # Sort each group by y0
        top_wide.sort(key=lambda b: b[1])
        left_col.sort(key=lambda b: b[1])
        right_col.sort(key=lambda b: b[1])
        bottom_wide.sort(key=lambda b: b[1])

        # Emit in reading order
        ordered = top_wide + left_col + right_col + bottom_wide
        page_text = "\n".join((b[4] or '').strip() for b in ordered if (b[4] or '').strip())
        if page_text:
            all_pages.append(f"<<PAGE:{pg_idx + 1}>>\n{page_text}")

        if (pg_idx + 1) % 50 == 0:
            log(f"  Extracted {pg_idx + 1}/{total_pages} pages (PyMuPDF columns)...")

    doc.close()
    log(f"  PyMuPDF column extraction complete: {len(all_pages)} pages with content")
    return "\n".join(all_pages)
```

### Placement

Insert this function immediately after `detect_column_layout()` (before `extract_text_ocr()`
at line 416).

---

## Routing in `extract_text()`

Inserted **before** `reader = PdfReader(pdf_path)` — i.e., before the existing pypdf path
begins. The existing pypdf quality check and pdfminer fallback are **completely unchanged**
after this block.

```python
# ── PyMuPDF column detection (inserted before pypdf path) ──────────────
try:
    import pymupdf  # noqa: F401 — presence check; actual use is inside called functions
    col_info = detect_column_layout(pdf_path, log)
    if col_info['is_multicolumn'] or force_columns:
        reason = "forced" if force_columns else f"confidence {col_info['confidence']:.2f}"
        log(f"  Multi-column layout detected ({reason}) — using PyMuPDF column extraction")
        try:
            text = _extract_with_pymupdf_columns(pdf_path, log)
            if text and len(text.split()) > 100:
                return text
            log("  [WARN] PyMuPDF column extraction returned empty — falling back to standard path")
        except Exception as e:
            log(f"  [WARN] PyMuPDF extraction failed: {e} — falling back to standard path")
    else:
        log(f"  Single-column layout (confidence {col_info['confidence']:.2f}) — using standard extraction")
except ImportError:
    log("  [INFO] pymupdf not installed — skipping column detection, using standard extraction")
except Exception as e:
    log(f"  [WARN] Column detection error: {e} — using standard extraction")
# ── existing pypdf quality check → pdfminer fallback (UNCHANGED below) ──
```

Note: `detect_column_layout` already handles `ImportError` and exceptions internally and
returns a safe default. The outer `try/except ImportError` in `extract_text` guards the
initial `import pymupdf` check so the function gracefully falls through on systems without
PyMuPDF installed.

---

## `--force-columns` flag threading

**Full call chain** (each function must accept and forward the parameter):

```
run_cli()
  → process_pdf(..., force_columns=args.force_columns)
      → extract_text_auto(..., force_columns=force_columns)
          → extract_text(..., force_columns=force_columns)   ← routing logic lives here
```

**Signature changes** (add `force_columns=False` as keyword arg, default `False`):

| Function | Change |
|---|---|
| `extract_text(pdf_path, log)` → | `extract_text(pdf_path, log, force_columns=False)` |
| `extract_text_auto(input_path, log, calibre_path=None)` → | add `force_columns=False`; pass `force_columns=force_columns` to `extract_text()` at the PDF branch |
| `process_pdf(input_path, output_path, log, ...)` → | add `force_columns=False`; pass to `extract_text_auto()` call |

In `run_cli()`: add `ap.add_argument("--force-columns", action="store_true",
help="Force PyMuPDF column extraction even when auto-detection confidence is low")` and
pass `force_columns=args.force_columns` to `process_pdf()`.

All existing callers pass no `force_columns` argument and get `False` by default — no
breakage.

**Non-PDF branches:** `extract_text_auto()` also handles EPUB (→ `extract_text_from_epub`)
and MOBI/AZW/AZW3/DJVU (→ `extract_text_via_calibre`). For these branches, `force_columns`
is accepted as a parameter but **not forwarded** — it is silently ignored. Column detection
is PDF-only; the parameter is present only to keep the signature consistent.

---

## Test coverage

### test_pipeline.py — Ezekiel II test case

The existing test harness's `run_extraction()` uses `--mode kindle` and looks for an HTML
output file. When `use_pdfminer=False` (no `--html-extraction`), the pipeline runs
`process_kindle()` which produces `.txt` output, not `.html`. The current `validate_html()`
function cannot validate this output.

For Prompt 1, the Ezekiel II test is therefore a **manual validation** entry in `TEST_CASES`
with no automated assertions against the output file:

```python
"Ezekiel II": {
    "pdf_pattern": "*Ezekiel*II*",
    "pdf_exclude": None,
    "use_pdfminer": False,   # plain-text Kindle path → triggers PyMuPDF column extraction
    "expected": {
        # NOTE: test harness validates HTML output; this case produces TXT only.
        # Automated content checks deferred to Prompt 2 (HTML variant).
        # Manual validation: open output TXT, confirm chapters are not interleaved.
        "kfx_produced": False,   # skip KFX step for this case
    }
}
```

The test runner will still invoke `run_extraction()` and report whether it completed
without error. Content validation is manual until the HTML variant lands in Prompt 2.

### Regression gate

The existing test cases (Oil Kings, Mexico, Brother of Jesus, Genesis, Dionysius) must
produce identical results. These are all single-column PDFs. For each:
1. `detect_column_layout()` will return `confidence < 0.6` (tested with the new filters
   in place — full-width and bottom-12% filters should not affect single-column detection).
2. The PyMuPDF routing block is skipped entirely.
3. Extraction falls through to the existing pypdf → pdfminer chain unchanged.

---

## Dependency update

Add to `EbookAutomation_Dependencies.md` under **Optional**:

| Package | PyPI Name | Purpose | Used By | Install |
|---|---|---|---|---|
| **PyMuPDF** | `pymupdf` | Fast PDF text extraction with layout analysis; enables two-column detection and column-ordered extraction | `pdf_to_balabolka.py` → `detect_column_layout()`, `_extract_with_pymupdf_columns()` | `pip install pymupdf` |

Graceful degradation: if not installed, `ImportError` is caught in `extract_text()` and the
standard pypdf → pdfminer chain runs unchanged. `detect_column_layout()` also handles its
own `ImportError` internally.

---

## Out of scope (Prompt 2)

- PyMuPDF HTML variant (`extract_with_pdfminer_html` routing)
- Automated content assertions for Ezekiel II in the test harness
- AZW3→KFX re-conversion chain mentioned in SCRUM-62 description
- GUI mode exposure of `--force-columns`
