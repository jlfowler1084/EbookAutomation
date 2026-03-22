# SCRUM-62 Prompt 2: Two-Column PyMuPDF HTML Extraction — Design Spec

**Date:** 2026-03-21
**Revision:** 1
**Scope:** Prompt 2 — HTML/Kindle path. PyMuPDF column-aware extraction wired into the pdfminer HTML pipeline.
**Ticket:** SCRUM-62 (parent: SCRUM-5)
**Files:** `tools/pdf_to_balabolka.py`

---

## Problem

Two-column academic PDFs produce interleaved HTML when extracted through pdfminer — `extract_with_pdfminer_html()` iterates `LTTextBox` elements in document order, which mixes columns. Ezekiel II (Hermeneia) produces HTML with no usable TOC and scrambled reading order on the Kindle HTML path.

Prompt 1 (SCRUM-62) fixed the plain-text path by routing through `extract_text_columns()`. This prompt applies the same fix to the HTML path.

---

## Architecture

One new function, two routing insertions, three signature additions. Everything downstream is unchanged.

```
extract_with_pdfminer_html(pdf_path, log, force_columns=False)
    ├── NEW: column detection gate (before pdfminer imports)
    │       if multi-column → _extract_html_with_pymupdf_columns() → return early
    │       else → fall through to existing pdfminer path (zero changes)
    └── existing pdfminer extraction (untouched)

NEW: _extract_html_with_pymupdf_columns(pdf_path, log) → (para_dicts, body_size)
    placed immediately before extract_with_pdfminer_html()

force_columns threading for the HTML path:
    run_cli() → process_kindle_html() → extract_with_pdfminer_html()
```

`process_kindle_html()`, `rejoin_html_fragments()`, `format_paragraphs_as_html()`, and
`_link_endnotes()` receive the same `(para_dicts, body_size)` contract — zero changes.

---

## New function: `_extract_html_with_pymupdf_columns(pdf_path, log)`

### Signature

```python
def _extract_html_with_pymupdf_columns(pdf_path, log):
    """Extract HTML-ready paragraph dicts from a two-column PDF using PyMuPDF.

    Uses page.get_text("dict") for font metadata (size, bold, italic, superscript)
    per span. Processes blocks in two-column reading order: top headers, left column
    body, right column body, left column footnotes, right column footnotes, bottom
    footers. Footnote zone = bottom 15% of page (y0 >= page_height * 0.85).

    Returns (para_dicts, body_size) with the same schema as extract_with_pdfminer_html(),
    so all downstream processing (rejoin_html_fragments, format_paragraphs_as_html,
    _link_endnotes) works unchanged.
    """
```

### Per-page classification

```python
page_w      = page.rect.width
page_h      = page.rect.height
page_mid    = page_w / 2.0
footnote_y  = page_h * 0.85    # bottom 15% — footnote apparatus zone

# Block tuple from get_text("dict"):
# block["type"]: 0=text, 1=image
# block["bbox"]: (x0, y0, x1, y1)
# block["lines"]: list of line dicts, each with "spans" list

for block in page_dict["blocks"]:
    if block["type"] != 0:               # skip image blocks
        continue
    x0, y0, x1, y1 = block["bbox"]
    if not any span text in block:       # skip empty blocks
        continue
    span_ratio = (x1 - x0) / page_w
    x_mid = (x0 + x1) / 2.0

    if span_ratio > 0.70:
        → wide_blocks (top_wide or bottom_wide after min_col_y0 is known)
    elif y0 >= footnote_y:
        → footnote_left (x_mid < page_mid) or footnote_right (x_mid >= page_mid)
    else:
        → left_col_body (x_mid < page_mid) or right_col_body (x_mid >= page_mid)
```

### Emission order per page

```
page_marker
top_wide          wide blocks with y0 < min_col_y0, sorted by y0
left_col_body     body-column left blocks, sorted by y0
right_col_body    body-column right blocks, sorted by y0
left_col_fnotes   footnote-zone left blocks, sorted by y0
right_col_fnotes  footnote-zone right blocks, sorted by y0
bottom_wide       wide blocks with y0 >= min_col_y0, sorted by y0
```

`min_col_y0` = `min(b["bbox"][1] for b in left_col_body + right_col_body)`.
If no body-column blocks on a page, all wide blocks go to `top_wide` (full-page element,
title page, etc.).

Page markers use the same schema as `extract_with_pdfminer_html()`:
```python
{'text': '', 'font_size': 0, 'is_bold': False, 'is_italic': False,
 'is_centered': False, 'is_all_caps': False, 'page_number': pg,
 'line_count': 0, 'char_count': 0, 'is_page_marker': True}
```

### Per-block para_dict construction

PyMuPDF flag bitmask (per Artifex documentation):
- bit 0 (`& 1`): superscript
- bit 1 (`& 2`): italic
- bit 4 (`& 16`): bold
- bit 5 (`& 32`): monospace

**Step 1 — compute dominant font properties:**
```python
# Weight each span's size by character count (strip whitespace)
size_weight = defaultdict(int)
bold_chars  = 0
italic_chars = 0
total_chars  = 0

for line in block["lines"]:
    for span in line["spans"]:
        n = len(span["text"].strip())
        if n == 0:
            continue
        size_weight[round(span["size"] * 2) / 2] += n   # round to 0.5pt
        if span["flags"] & 16:
            bold_chars += n
        if span["flags"] & 2:
            italic_chars += n
        total_chars += n

dominant_size = max(size_weight, key=size_weight.get, default=0.0)
is_bold   = bold_chars   > total_chars * 0.5
is_italic = italic_chars > total_chars * 0.5
```

**Step 2 — build text with `<sup>` tags:**

A span is a true superscript when BOTH conditions hold:
1. `span["flags"] & 1` (superscript bit set)
2. `span["size"] < dominant_size * 0.75` (noticeably smaller)

Cross-checking both flag and size avoids false positives from small decorative text.

```python
parts = []
in_sup = False
for line_idx, line in enumerate(block["lines"]):
    line_parts = []
    for span in line["spans"]:
        text = span["text"]
        if not text:
            continue
        is_sup = (span["flags"] & 1) and (span["size"] < dominant_size * 0.75)
        if is_sup and not in_sup:
            line_parts.append('<sup>')
            in_sup = True
        elif not is_sup and in_sup:
            line_parts.append('</sup>')
            in_sup = False
        line_parts.append(text)
    if in_sup:
        line_parts.append('</sup>')
        in_sup = False
    line_text = ''.join(line_parts).strip()
    if not line_text:
        continue
    # Hyphenated line break: if previous line ends with '-' and this starts lowercase
    if parts and parts[-1].endswith('-') and line_text and line_text[0].islower():
        parts[-1] = parts[-1][:-1]  # remove hyphen
        parts.append(line_text)
    else:
        parts.append(line_text)
```

**Step 3 — normalize and finalize:**
```python
text = ' '.join(parts)
text = re.sub(r'[\u00a0\u2000-\u200b\u2028\u2029\u202f\u205f\u3000\t]+', ' ', text)
text = re.sub(r' +', ' ', text).strip()
if not text:
    continue  # skip entirely empty blocks

is_centered = abs((x0 + x1) / 2 - page_w / 2) < 40
is_all_caps  = text == text.upper() and len(text) > 3 and any(c.isalpha() for c in text)

para_dict = {
    'text':        text,
    'font_size':   dominant_size,
    'is_bold':     is_bold,
    'is_italic':   is_italic,
    'is_centered': is_centered,
    'is_all_caps': is_all_caps,
    'page_number': pg,
    'line_count':  len(block["lines"]),
    'char_count':  len(text),
}
```

### body_size computation

After all pages are processed, compute body_size from the full para_dicts list:
```python
from collections import Counter
size_counts = Counter(
    p['font_size'] for p in all_paras
    if not p.get('is_page_marker') and p['font_size'] > 0
)
body_size = size_counts.most_common(1)[0][0] if size_counts else 12.0
```

Log the font distribution (same format as `extract_with_pdfminer_html()`):
```python
log(f"  PyMuPDF HTML extraction: {total_pages} pages, {len(all_paras)} paragraphs")
log(f"  Body font detected: {body_size}pt")
```

### Placement

Insert this function immediately before `extract_with_pdfminer_html()` (currently at
line 2652). It will land at approximately line 2652, pushing `extract_with_pdfminer_html`
down by the length of the new function.

---

## Routing in `extract_with_pdfminer_html()`

Insert at the top of the function body, before `from pdfminer.high_level import ...`:

```python
# ── PyMuPDF column detection gate ─────────────────────────────────────────
# detect_column_layout() handles its own ImportError and returns is_multicolumn=False
# if pymupdf is not installed — no outer ImportError guard needed here.
try:
    col_info = detect_column_layout(pdf_path, log)
    if col_info['is_multicolumn'] or force_columns:
        reason = "forced" if force_columns else f"confidence {col_info['confidence']:.2f}"
        log(f"  Multi-column layout detected ({reason}) — using PyMuPDF HTML extraction")
        try:
            para_dicts, body_size = _extract_html_with_pymupdf_columns(pdf_path, log)
            if any(not p.get('is_page_marker') for p in para_dicts):
                return para_dicts, body_size
            log("  [WARN] PyMuPDF HTML extraction returned empty — falling back to pdfminer")
        except Exception as e:
            log(f"  [WARN] PyMuPDF HTML extraction failed: {e} — falling back to pdfminer")
    else:
        log(f"  Single-column layout (confidence {col_info['confidence']:.2f}) — using pdfminer")
except Exception as e:
    log(f"  [WARN] Column detection error: {e} — using pdfminer")
# ── existing pdfminer extraction (UNCHANGED below) ────────────────────────
```

**Validity check:** `if any(not p.get('is_page_marker') for p in para_dicts):` — requires
at least one non-marker paragraph. A list containing only page-marker dicts is truthy but
useless; this check correctly falls through to pdfminer in that case.

---

## `force_columns` threading for the HTML path

**Signature changes** (add `force_columns=False` as keyword arg, default `False`):

| Function | Change |
|---|---|
| `extract_with_pdfminer_html(pdf_path, log)` | Add `force_columns=False` |
| `process_kindle_html(pdf_path, output_path, log, api_key=None)` | Add `force_columns=False`; pass to `extract_with_pdfminer_html()` call |

**In `run_cli()`:**
1. Remove the warning block (lines 7557–7559):
   ```python
   if args.force_columns and args.html_extraction:
       print("[warn] --force-columns has no effect with --html-extraction ...", ...)
   ```
2. Add `force_columns=args.force_columns` to the `process_kindle_html()` call site.

All existing callers of `extract_with_pdfminer_html()` and `process_kindle_html()` pass
no `force_columns` argument and get `False` by default — no breakage.

---

## Test coverage

### Ezekiel II in `TEST_CASES`

With Prompt 2 complete, `run_extraction(use_pdfminer=True)` on Ezekiel II runs
`--mode kindle --html-extraction`, which calls `process_kindle_html()` →
`extract_with_pdfminer_html()` → column detection → `_extract_html_with_pymupdf_columns()`
→ HTML output. The test runner can now validate HTML.

Add to `TEST_CASES` in `tools/test_pipeline.py` (after the Dionysius entry):

```python
"Ezekiel II": {
    "pdf_pattern": "*Ezekiel*II*",
    "pdf_exclude": None,
    "use_pdfminer": True,   # --html-extraction → routes to PyMuPDF for multi-column
    "expected": {
        "kfx_produced": False,   # skip KFX step; validate HTML only
        "min_h2": 8,             # commentary chapters on Ezekiel 25-48
        "no_standalone_page_numbers": True,
    }
}
```

`kfx_produced: False` skips the PowerShell KFX conversion step. `min_h2: 8` is a
conservative floor — Ezekiel chapters 25–48 should produce well over 20 chapter headings
once font-size-based heading detection is working correctly with PyMuPDF metadata.

### Regression gate

The existing five TEST_CASES (Oil Kings, Genesis, Mexico, Brother of Jesus, Dionysius)
must pass unchanged. Each is a single-column PDF. For each:
1. `detect_column_layout()` returns `confidence < 0.6` (confirmed in Prompt 1 regression run)
2. Routing block is skipped; pdfminer extraction runs exactly as before

---

## Out of scope

- Hebrew font encoding (separate ticket)
- Orphaned paragraph fragments at column breaks (handled by existing `rejoin_html_fragments`)
- GUI exposure of `--force-columns`
- AZW3→KFX re-conversion chain

## Known limitations

**`is_centered` for column-body blocks:** The formula `abs((x0 + x1) / 2 - page_w / 2) < 40`
measures centering against the full page midpoint, so a heading centered within a single column
will never be detected as centered. For Ezekiel II this is acceptable: chapter headings are
full-width wide blocks (correctly classified), and in-column subheadings are identified by
`font_size` and `is_bold`. Correct column-relative centering detection is deferred to a
future refinement ticket.
