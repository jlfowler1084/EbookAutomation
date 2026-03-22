# Two-Column PyMuPDF HTML Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `_extract_html_with_pymupdf_columns()` function and wire it into the `--html-extraction` Kindle path so two-column academic PDFs (Hermeneia commentaries) produce correctly ordered semantic HTML.

**Architecture:** One new function reads font metadata via `page.get_text("dict")`, classifies blocks into six zones (top-wide, left-body, right-body, left-footnotes, right-footnotes, bottom-wide), and returns `(para_dicts, body_size)` using the same schema as the existing pdfminer path. A routing gate at the top of `extract_with_pdfminer_html()` calls `detect_column_layout()` and dispatches to the new function when multi-column is detected. `force_columns` is threaded from `run_cli()` → `process_kindle_html()` → `extract_with_pdfminer_html()`.

**Tech Stack:** Python 3.8+, PyMuPDF (`pymupdf`), existing `test_pipeline.py` regression harness.

---

## File Map

| File | Change |
|---|---|
| `tools/pdf_to_balabolka.py` | Insert `_extract_html_with_pymupdf_columns()` before line 2652; modify `extract_with_pdfminer_html()` at line 2652; modify `process_kindle_html()` at line 6946; modify `run_cli()` at lines 7564–7566 and 7624 |
| `tools/test_pipeline.py` | Add Ezekiel II entry to `TEST_CASES` after line 125 |

No new files. No other files touched.

---

## Pre-flight check

**Working directory:** All Python commands assume CWD is the project root `F:\Projects\EbookAutomation\`.

- [ ] **Confirm PyMuPDF is installed:**

  ```
  python -c "import pymupdf; print(f'PyMuPDF {pymupdf.__version__} OK')"
  ```

  Expected: `PyMuPDF 1.x.y OK`. If ImportError, install: `python -m pip install pymupdf`.

- [ ] **Confirm `extract_with_pdfminer_html` signature (current):**

  Read `tools/pdf_to_balabolka.py` lines 2652–2658 and confirm:
  ```python
  def extract_with_pdfminer_html(pdf_path, log):
  ```
  (no `force_columns` parameter yet — it will be added in Task 2)

- [ ] **Confirm `process_kindle_html` signature (current):**

  Read `tools/pdf_to_balabolka.py` lines 6946–6952 and confirm:
  ```python
  def process_kindle_html(pdf_path, output_path, log, api_key=None):
  ```
  (no `force_columns` parameter yet — it will be added in Task 2)

- [ ] **Confirm `run_cli()` warning block exists at lines 7564–7566:**

  Read those lines and confirm they match:
  ```python
  if args.force_columns and args.html_extraction:
      print("[warn] --force-columns has no effect with --html-extraction "
            "(html-extraction uses pdfminer, not PyMuPDF)", file=sys.stderr)
  ```

---

## Task 1: Implement `_extract_html_with_pymupdf_columns()`

**Files:**
- Modify: `tools/pdf_to_balabolka.py` — insert new function before line 2652

### Background

This function returns `(para_dicts, body_size)` with the same schema as `extract_with_pdfminer_html()`:

```python
# Normal paragraph dict:
{
    'text':        str,   # block text, whitespace-normalized, <sup> tags for footnote refs
    'font_size':   float, # dominant font size (weighted by char count)
    'is_bold':     bool,  # >50% of chars are bold
    'is_italic':   bool,  # >50% of chars are italic
    'is_centered': bool,  # block center within 40px of page center
    'is_all_caps': bool,  # text == text.upper() and len > 3 and has alpha
    'page_number': int,   # 1-indexed
    'line_count':  int,   # number of lines in block
    'char_count':  int,   # len(text)
}

# Page marker dict (one per page, inserted first):
{
    'text': '', 'font_size': 0, 'is_bold': False, 'is_italic': False,
    'is_centered': False, 'is_all_caps': False, 'page_number': int,
    'line_count': 0, 'char_count': 0, 'is_page_marker': True
}
```

PyMuPDF font flag bitmask (per Artifex docs):
- `& 1` → superscript
- `& 2` → italic
- `& 16` → bold

### Steps

- [ ] **Step 1: Confirm the function does not already exist**

  ```
  python -c "
  import sys; sys.path.insert(0, 'tools')
  import pdf_to_balabolka as m
  print(hasattr(m, '_extract_html_with_pymupdf_columns'))
  "
  ```

  Expected: `False`. If `True`, the function already exists — read it and compare against the spec before overwriting.

- [ ] **Step 2: Insert the function into `tools/pdf_to_balabolka.py` immediately before `extract_with_pdfminer_html()` (line 2652)**

  Insert the following block between the blank lines before `def extract_with_pdfminer_html`:

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
      import pymupdf
      import re
      from collections import defaultdict, Counter

      doc = pymupdf.open(pdf_path)
      total_pages = len(doc)
      all_paras = []

      for pg_idx in range(total_pages):
          pg = pg_idx + 1  # 1-indexed
          page = doc[pg_idx]
          page_dict = page.get_text("dict")
          page_w = page.rect.width
          page_h = page.rect.height
          page_mid = page_w / 2.0
          footnote_y = page_h * 0.85    # bottom 15% — footnote apparatus zone

          # Insert page marker (same schema as extract_with_pdfminer_html)
          all_paras.append({
              'text': '', 'font_size': 0, 'is_bold': False, 'is_italic': False,
              'is_centered': False, 'is_all_caps': False, 'page_number': pg,
              'line_count': 0, 'char_count': 0, 'is_page_marker': True
          })

          # Classify blocks into zones
          top_wide       = []
          left_col_body  = []
          right_col_body = []
          left_col_fnotes  = []
          right_col_fnotes = []
          bottom_wide    = []
          col_blocks     = []
          wide_blocks_raw = []

          for block in page_dict["blocks"]:
              if block["type"] != 0:               # skip image blocks
                  continue
              x0, y0, x1, y1 = block["bbox"]
              has_text = any(
                  span["text"].strip()
                  for line in block["lines"]
                  for span in line["spans"]
              )
              if not has_text:
                  continue
              span_ratio = (x1 - x0) / page_w
              x_mid = (x0 + x1) / 2.0
              if span_ratio > 0.70:
                  wide_blocks_raw.append(block)
              elif y0 >= footnote_y:
                  if x_mid < page_mid:
                      left_col_fnotes.append(block)
                  else:
                      right_col_fnotes.append(block)
              else:
                  col_blocks.append(block)
                  if x_mid < page_mid:
                      left_col_body.append(block)
                  else:
                      right_col_body.append(block)

          # Partition wide blocks relative to first column content
          if col_blocks:
              min_col_y0 = min(b["bbox"][1] for b in col_blocks)
              for b in wide_blocks_raw:
                  if b["bbox"][1] < min_col_y0:
                      top_wide.append(b)
                  else:
                      bottom_wide.append(b)
          else:
              # No column blocks on this page — all wide blocks go to top_wide
              top_wide = wide_blocks_raw[:]

          # Sort each group by y0
          top_wide.sort(key=lambda b: b["bbox"][1])
          left_col_body.sort(key=lambda b: b["bbox"][1])
          right_col_body.sort(key=lambda b: b["bbox"][1])
          left_col_fnotes.sort(key=lambda b: b["bbox"][1])
          right_col_fnotes.sort(key=lambda b: b["bbox"][1])
          bottom_wide.sort(key=lambda b: b["bbox"][1])

          ordered = (top_wide + left_col_body + right_col_body
                     + left_col_fnotes + right_col_fnotes + bottom_wide)

          for block in ordered:
              x0, y0, x1, y1 = block["bbox"]

              # Step 1: compute dominant font properties (weighted by character count)
              size_weight  = defaultdict(int)
              bold_chars   = 0
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

              if total_chars == 0:
                  continue

              dominant_size = max(size_weight, key=size_weight.get, default=0.0)
              is_bold   = bold_chars   > total_chars * 0.5
              is_italic = italic_chars > total_chars * 0.5

              # Step 2: build text with <sup> tags for footnote reference numbers
              # A span is a true superscript when BOTH conditions hold:
              #   (a) superscript bit set (flags & 1)
              #   (b) noticeably smaller than dominant size (< dominant_size * 0.75)
              parts  = []
              in_sup = False
              for line in block["lines"]:
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
                  # Hyphenated line break: remove hyphen and join to next line
                  if parts and parts[-1].endswith('-') and line_text and line_text[0].islower():
                      parts[-1] = parts[-1][:-1]
                      parts.append(line_text)
                  else:
                      parts.append(line_text)

              # Step 3: normalize and finalize
              text = ' '.join(parts)
              text = re.sub(r'[\u00a0\u2000-\u200b\u2028\u2029\u202f\u205f\u3000\t]+', ' ', text)
              text = re.sub(r' +', ' ', text).strip()
              if not text:
                  continue

              is_centered = abs((x0 + x1) / 2 - page_w / 2) < 40
              is_all_caps = (text == text.upper()
                             and len(text) > 3
                             and any(c.isalpha() for c in text))

              all_paras.append({
                  'text':        text,
                  'font_size':   dominant_size,
                  'is_bold':     is_bold,
                  'is_italic':   is_italic,
                  'is_centered': is_centered,
                  'is_all_caps': is_all_caps,
                  'page_number': pg,
                  'line_count':  len(block["lines"]),
                  'char_count':  len(text),
              })

          if (pg_idx + 1) % 50 == 0:
              log(f"  PyMuPDF HTML extraction: {pg_idx + 1}/{total_pages} pages...")

      doc.close()

      # Compute body_size: most common font_size across all non-marker paragraphs
      size_counts = Counter(
          p['font_size'] for p in all_paras
          if not p.get('is_page_marker') and p['font_size'] > 0
      )
      body_size = size_counts.most_common(1)[0][0] if size_counts else 12.0

      log(f"  PyMuPDF HTML extraction: {total_pages} pages, {len(all_paras)} paragraphs")
      log(f"  Body font detected: {body_size}pt")

      return all_paras, body_size
  ```

  **Placement rule:** Insert the entire block (blank line + `def _extract_html_with_pymupdf_columns` ... through the final `return all_paras, body_size`) immediately before the existing `def extract_with_pdfminer_html(pdf_path, log):` line.

- [ ] **Step 3: Verify the insertion landed cleanly**

  ```
  python -c "
  import sys; sys.path.insert(0, 'tools')
  import pdf_to_balabolka as m
  print('Function exists:', hasattr(m, '_extract_html_with_pymupdf_columns'))
  import inspect
  src = inspect.getsource(m._extract_html_with_pymupdf_columns)
  print('Lines:', src.count(chr(10)))
  print('Has page marker insert:', 'is_page_marker' in src)
  print('Has superscript check:', 'dominant_size * 0.75' in src)
  print('Has footnote zone:', 'footnote_y' in src)
  "
  ```

  Expected: Function exists: True, Lines >= 100, all three checks True.

- [ ] **Step 4: Smoke test — call function directly on Ezekiel II**

  ```
  python -c "
  import sys, glob; sys.path.insert(0, 'tools')
  from pdf_to_balabolka import _extract_html_with_pymupdf_columns
  pdfs = glob.glob('archive/*Ezekiel*II*.pdf')
  if not pdfs:
      print('Ezekiel II not found — skipping smoke test'); sys.exit(0)
  pdf = pdfs[0]
  print(f'Testing on: {pdf}')
  para_dicts, body_size = _extract_html_with_pymupdf_columns(pdf, print)
  non_markers = [p for p in para_dicts if not p.get('is_page_marker')]
  print(f'Total dicts: {len(para_dicts)}, Non-markers: {len(non_markers)}, body_size: {body_size}')
  assert len(non_markers) > 100, f'Too few paragraphs: {len(non_markers)}'
  assert body_size > 0, 'body_size is 0'
  # Check schema completeness on first non-marker
  p = non_markers[0]
  required = ['text','font_size','is_bold','is_italic','is_centered','is_all_caps','page_number','line_count','char_count']
  for k in required:
      assert k in p, f'Missing key: {k}'
  print('PASS: schema correct, paragraphs extracted')
  "
  ```

  Expected: PASS message. If Ezekiel II PDF is not in `archive/`, the script exits cleanly — proceed to Task 2.

---

## Task 2: Routing gate + `force_columns` threading

**Files:**
- Modify: `tools/pdf_to_balabolka.py` lines 2652, 2657, 6946, 6956, 7564–7566, 7624

### Steps

- [ ] **Step 1: Add `force_columns=False` to `extract_with_pdfminer_html()` signature**

  Current line 2652:
  ```python
  def extract_with_pdfminer_html(pdf_path, log):
  ```

  Change to:
  ```python
  def extract_with_pdfminer_html(pdf_path, log, force_columns=False):
  ```

- [ ] **Step 2: Insert routing gate at top of `extract_with_pdfminer_html()` function body**

  The first line of the function body is currently:
  ```python
      from pdfminer.high_level import extract_pages
  ```

  Insert the routing block immediately before that line (inside the function, at the same 4-space indent level):

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

- [ ] **Step 3: Add `force_columns=False` to `process_kindle_html()` signature**

  Current line 6946:
  ```python
  def process_kindle_html(pdf_path, output_path, log, api_key=None):
  ```

  Change to:
  ```python
  def process_kindle_html(pdf_path, output_path, log, api_key=None, force_columns=False):
  ```

- [ ] **Step 4: Pass `force_columns` to `extract_with_pdfminer_html()` inside `process_kindle_html()`**

  Find the call inside `process_kindle_html()` (currently around line 6956):
  ```python
      para_dicts, body_size = extract_with_pdfminer_html(pdf_path, log)
  ```

  Change to:
  ```python
      para_dicts, body_size = extract_with_pdfminer_html(pdf_path, log, force_columns=force_columns)
  ```

- [ ] **Step 5: Remove the `--force-columns` warning block from `run_cli()`**

  Remove lines 7564–7566 exactly:
  ```python
      if args.force_columns and args.html_extraction:
          print("[warn] --force-columns has no effect with --html-extraction "
                "(html-extraction uses pdfminer, not PyMuPDF)", file=sys.stderr)
  ```

  The three lines (and the blank line after, if any) should be deleted entirely.

- [ ] **Step 6: Add `force_columns=args.force_columns` to the `process_kindle_html()` call in `run_cli()`**

  Find the call at approximately line 7624 (after the removals, the line number shifts slightly):
  ```python
              process_kindle_html(input_path, html_output, log_fn, api_key=args.api_key)
  ```

  Change to:
  ```python
              process_kindle_html(input_path, html_output, log_fn, api_key=args.api_key,
                                  force_columns=args.force_columns)
  ```

- [ ] **Step 7: Smoke test — single-column PDF should NOT use PyMuPDF path**

  Run on any single-column PDF already processed (Oil Kings, Genesis, etc.):

  ```
  python -c "
  import sys, glob; sys.path.insert(0, 'tools')
  from pdf_to_balabolka import extract_with_pdfminer_html
  pdfs = (glob.glob('archive/*Oil*Kings*.pdf') +
          glob.glob('archive/*Genesis*.pdf') +
          glob.glob('archive/*Mexico*.pdf'))
  if not pdfs:
      print('No single-column PDF found — skip'); sys.exit(0)
  pdf = pdfs[0]
  print(f'Testing on: {pdf}')
  messages = []
  para_dicts, body_size = extract_with_pdfminer_html(pdf, messages.append)
  for m in messages[:10]:
      print(m)
  assert not any('PyMuPDF HTML extraction' in m for m in messages), \
      'FAIL: single-column PDF incorrectly routed to PyMuPDF'
  assert any('pdfminer' in m.lower() or 'single-column' in m.lower() for m in messages), \
      'FAIL: no pdfminer/single-column log message found'
  print('PASS: single-column PDF correctly uses pdfminer path')
  "
  ```

  Expected: PASS. The log messages should show `Single-column layout ... — using pdfminer`, not `Multi-column layout detected`.

- [ ] **Step 8: Smoke test — Ezekiel II should use PyMuPDF path via `extract_with_pdfminer_html()`**

  ```
  python -c "
  import sys, glob; sys.path.insert(0, 'tools')
  from pdf_to_balabolka import extract_with_pdfminer_html
  pdfs = glob.glob('archive/*Ezekiel*II*.pdf')
  if not pdfs:
      print('Ezekiel II not found — skipping'); sys.exit(0)
  pdf = pdfs[0]
  print(f'Testing on: {pdf}')
  messages = []
  para_dicts, body_size = extract_with_pdfminer_html(pdf, messages.append)
  for m in messages[:10]:
      print(m)
  assert any('PyMuPDF HTML extraction' in m for m in messages), \
      'FAIL: Ezekiel II not routed to PyMuPDF'
  non_markers = [p for p in para_dicts if not p.get('is_page_marker')]
  assert len(non_markers) > 100, f'Too few paragraphs: {len(non_markers)}'
  print(f'PASS: PyMuPDF path used, {len(non_markers)} paragraphs, body_size={body_size}pt')
  "
  ```

  Expected: PASS, log shows `Multi-column layout detected`, paragraph count > 100.

- [ ] **Step 9: Smoke test — `--force-columns` no longer prints warning**

  ```
  python tools/pdf_to_balabolka.py --input "archive/<any_pdf>.pdf" --mode kindle --html-extraction --force-columns 2>&1 | head -5
  ```

  Expected: No `[warn] --force-columns has no effect` line in output. The pipeline runs normally.

  If no PDF is conveniently at hand, test the flag parsing alone:
  ```
  python -c "
  import subprocess, sys
  # Just test that the warning is gone — use --help to trigger arg parse without a file
  result = subprocess.run(
      [sys.executable, 'tools/pdf_to_balabolka.py', '--help'],
      capture_output=True, text=True)
  assert '--force-columns' in result.stdout, 'FAIL: --force-columns flag missing from help'
  print('PASS: --force-columns still present in help')
  "
  ```

---

## Task 3: Add Ezekiel II to TEST_CASES and run regression

**Files:**
- Modify: `tools/test_pipeline.py` — add entry after line 125 (after the closing `}` of the Dionysius entry)

### Steps

- [ ] **Step 1: Add Ezekiel II entry to `TEST_CASES`**

  Read `tools/test_pipeline.py` lines 115–127 to confirm the Dionysius entry ends at line 125 with `}` followed by `}` (closing the dict) at line 126. Then insert the Ezekiel II entry between those two closing braces:

  Find this exact text:
  ```python
      "Dionysius": {
          "pdf_pattern": "*Dionysius*",
          "pdf_exclude": None,
          "use_pdfminer": True,
          "expected": {
              "kfx_produced": True,
              "min_h2": 20,
              "min_blockquotes": 10,
              "min_h3": 20,
          }
      },
  }
  ```

  Replace with:
  ```python
      "Dionysius": {
          "pdf_pattern": "*Dionysius*",
          "pdf_exclude": None,
          "use_pdfminer": True,
          "expected": {
              "kfx_produced": True,
              "min_h2": 20,
              "min_blockquotes": 10,
              "min_h3": 20,
          }
      },
      "Ezekiel II": {
          "pdf_pattern": "*Ezekiel*II*",
          "pdf_exclude": None,
          "use_pdfminer": True,   # --html-extraction → routes to PyMuPDF for multi-column
          "expected": {
              "kfx_produced": False,   # skip KFX step; validate HTML only
              "min_h2": 8,             # conservative floor; Ezekiel 25-48 chapters
              "no_standalone_page_numbers": True,
          }
      },
  }
  ```

- [ ] **Step 2: Run the full regression suite (quick mode)**

  ```
  python tools/test_pipeline.py --quick
  ```

  Expected: All six test cases PASS — Oil Kings, Genesis, Mexico, Brother of Jesus, Dionysius, Ezekiel II. The first five must produce the same output as before. Ezekiel II must produce an HTML file with at least 8 `<h2>` tags.

  If Ezekiel II PDF is not in the archive, the test runner will skip or report "PDF not found" — this is acceptable. The five existing test cases must still pass.

- [ ] **Step 3: If any of the five existing test cases fail — investigate before reverting**

  Run detection on the failing book to check it isn't being incorrectly flagged as multi-column:

  ```
  python -c "
  import sys, glob; sys.path.insert(0, 'tools')
  from pdf_to_balabolka import detect_column_layout
  pdf = glob.glob('archive/*<BookName>*.pdf')[0]
  result = detect_column_layout(pdf, print)
  print(result)
  "
  ```

  For a single-column book, `confidence` should be below 0.6 and `is_multicolumn` should be False.

- [ ] **Step 4: If Ezekiel II test fails with fewer than 8 h2 tags — check heading detection**

  Run extraction and inspect the heading count:

  ```
  python -c "
  import sys, glob, re; sys.path.insert(0, 'tools')
  pdfs = glob.glob('archive/*Ezekiel*II*.pdf')
  if not pdfs: print('PDF not found'); sys.exit(0)
  # Find the output HTML
  html_files = glob.glob('output/kindle/*Ezekiel*II*.html')
  if not html_files: print('HTML output not found — run extraction first'); sys.exit(1)
  html = open(html_files[0], encoding='utf-8').read()
  h2s = re.findall(r'<h2>(.*?)</h2>', html)
  print(f'h2 count: {len(h2s)}')
  for h in h2s[:10]:
      print(' ', h[:80])
  "
  ```

  If count is 0, the heading detection may not be recognizing the font-size-based chapter headings. Check that `dominant_size` values for heading blocks are significantly larger than `body_size`.

---

## Pre-flight check (read this before Task 1)

**No git repo in this project** — commit steps are omitted. The project is tracked as SCRUM-18 for git initialization. Do not run `git` commands.

**Regression test is the quality gate.** After Task 3, the test suite must show all existing cases passing before this work is considered complete.
