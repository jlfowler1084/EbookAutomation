# SCRUM-62: Two-Column Academic PDF Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PyMuPDF-based column-aware text extraction for two-column academic PDFs with automatic layout detection, routing multi-column books to the new path while leaving all single-column books on the existing pdfminer/pypdf path completely unchanged.

**Architecture:** A `detect_column_layout()` function samples the PDF with PyMuPDF to classify layout; if multi-column with sufficient confidence, `extract_text_columns()` extracts text in left-then-right column order per page, emitting `<<PAGE:N>>` markers identical to the existing `extract_text()` contract. All existing downstream processing (clean_and_join, fix_ocr_artifacts, HTML formatting, etc.) runs unchanged. A `--force-columns` CLI flag overrides the confidence gate. The switch threads from CLI → process functions → extract_text_auto → extract_text.

**Tech Stack:** Python 3.8+, pymupdf (`import pymupdf`), existing pypdf/pdfminer paths untouched, PowerShell 5.1 for module integration.

---

## File Map

| File | Change |
|------|--------|
| `tools/pdf_to_balabolka.py` | Add `detect_column_layout()` after line ~303; add `extract_text_columns()` before `_extract_with_pdfminer()` (~line 574); add `force_columns` param + routing to `extract_text()`; thread `force_columns` through `extract_text_auto()`, `process_pdf()`, `process_kindle()`; add `--force-columns` argparse arg |
| `module/EbookAutomation.psm1` | Add `[switch]$ForceColumns` to `Convert-ToKindle`, `Convert-ToTTS`, `Invoke-EbookPipeline`; wire into `$pyArgs`; add AZW3→KFX chain |
| `tools/test_columns.ps1` | New: test matrix for column detection + extraction |
| `CLAUDE.md` | Add pymupdf to dependencies table, document column detection routing |

---

## Task 1: Install PyMuPDF and Verify Import

**Files:**
- No code changes — environment setup only

- [ ] **Step 1: Install pymupdf**

```powershell
python -m pip install pymupdf
```

Expected output: `Successfully installed pymupdf-X.X.X`

> **Note:** The spec references `--break-system-packages` but that flag is Linux-only (PEP 668). On Windows it causes pip to error. Use plain `python -m pip install pymupdf` on Windows.

- [ ] **Step 2: Verify import works**

```powershell
python -c "import pymupdf; print(pymupdf.__version__)"
```

Expected: version string printed without error (e.g. `1.24.x`)

---

## Task 2: Add `detect_column_layout()` to pdf_to_balabolka.py

**Files:**
- Modify: `tools/pdf_to_balabolka.py` — insert after `detect_pdf_type()` ends (~line 303)

This function ONLY classifies layout. It does not extract or modify text.

- [ ] **Step 1: Insert `detect_column_layout()` after the `detect_pdf_type()` function**

Add the following function between `detect_pdf_type()` (which ends ~line 303) and `extract_text_ocr()` (~line 306):

```python
def detect_column_layout(pdf_path, log, sample_pages=8):
    """Detect whether a PDF uses a multi-column layout by analyzing text block positions.

    Uses PyMuPDF to extract text blocks with coordinates, then checks whether blocks
    cluster into distinct x-coordinate ranges (indicating columns).

    Returns:
        dict with keys:
            'is_multicolumn': bool
            'num_columns': int (1, 2, or 3)
            'column_boundaries': list of (x_start, x_end) tuples
            'confidence': float (0.0 to 1.0)
            'page_width': float
    """
    try:
        import pymupdf
    except ImportError:
        log("  [WARN] pymupdf not installed — column detection unavailable")
        log("  [WARN] Run: python -m pip install pymupdf")
        return {'is_multicolumn': False, 'num_columns': 1,
                'column_boundaries': [], 'confidence': 0.0, 'page_width': 0.0}

    try:
        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)

        # Skip first 5 pages (often title/TOC with different layout)
        start_page = min(5, total_pages - 1)
        n_sample = min(sample_pages, total_pages - start_page)
        if n_sample <= 0:
            doc.close()
            return {'is_multicolumn': False, 'num_columns': 1,
                    'column_boundaries': [], 'confidence': 0.0, 'page_width': 0.0}

        # Evenly sample pages from the body of the document
        sample_indices = [start_page + int(i * (total_pages - start_page) / n_sample)
                          for i in range(n_sample)]
        sample_indices = list(dict.fromkeys(sample_indices))  # deduplicate

        page_width = doc[sample_indices[0]].rect.width
        pages_with_two_clusters = 0
        column_boundaries_list = []

        for pg_idx in sample_indices:
            page = doc[pg_idx]
            blocks = page.get_text("blocks")
            # block format: (x0, y0, x1, y1, text, block_no, block_type)
            text_blocks = [b for b in blocks
                           if b[6] == 0 and len((b[4] or '').strip()) >= 50]

            if len(text_blocks) < 3:
                continue  # too few blocks to classify this page

            x0_values = [b[0] for b in text_blocks]

            # Histogram approach: divide page width into 20 bins, find the gap
            bin_width = page_width / 20
            histogram = [0] * 20
            for x0 in x0_values:
                bin_idx = min(int(x0 / bin_width), 19)
                histogram[bin_idx] += 1

            # Find the largest gap in the middle 60% of the page (columns don't
            # start at extreme edges, so skip bins 0-3 and 16-19)
            left_peak = -1
            right_peak = -1
            gap_width = 0
            gap_threshold = page_width * 0.15  # gap must be >15% of page width

            # Find left cluster (bins 1-8) and right cluster (bins 9-16)
            left_bins  = [(i, histogram[i]) for i in range(1, 9)  if histogram[i] > 0]
            right_bins = [(i, histogram[i]) for i in range(9, 17) if histogram[i] > 0]

            if left_bins and right_bins:
                left_peak_bin  = max(left_bins,  key=lambda x: x[1])[0]
                right_peak_bin = max(right_bins, key=lambda x: x[1])[0]
                gap = (right_peak_bin - left_peak_bin) * bin_width

                if gap >= gap_threshold:
                    pages_with_two_clusters += 1
                    col1_start = 0
                    col1_end   = left_peak_bin * bin_width + bin_width * 2
                    col2_start = right_peak_bin * bin_width - bin_width
                    col2_end   = page_width
                    column_boundaries_list.append(
                        [(col1_start, col1_end), (col2_start, col2_end)]
                    )

        doc.close()

        confidence = pages_with_two_clusters / len(sample_indices) if sample_indices else 0.0
        is_multicolumn = confidence >= 0.6

        # Use median column boundaries across sampled pages for consistency
        if column_boundaries_list:
            col_bounds = column_boundaries_list[len(column_boundaries_list) // 2]
        else:
            col_bounds = []

        log(f"  Column detection: {pages_with_two_clusters}/{len(sample_indices)} pages "
            f"show 2-column layout (confidence: {confidence:.0%})")

        return {
            'is_multicolumn': is_multicolumn,
            'num_columns': 2 if is_multicolumn else 1,
            'column_boundaries': col_bounds,
            'confidence': confidence,
            'page_width': page_width,
        }

    except Exception as e:
        log(f"  [WARN] Column layout detection failed: {e}")
        return {'is_multicolumn': False, 'num_columns': 1,
                'column_boundaries': [], 'confidence': 0.0, 'page_width': 0.0}
```

- [ ] **Step 2: Parse-check the file**

```powershell
python -c "import ast; ast.parse(open('tools/pdf_to_balabolka.py', encoding='utf-8').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Smoke-test detect_column_layout on a two-column book**

Replace `<two-column-pdf>` with an actual path from `archive\`:
```powershell
python -c "
import sys; sys.path.insert(0, 'tools')
from pdf_to_balabolka import detect_column_layout
r = detect_column_layout(r'archive\<two-column-pdf>', print)
print(r)
"
```

Expected for a two-column academic commentary: `'is_multicolumn': True, 'confidence': >= 0.6`

- [ ] **Step 4: Smoke-test on a single-column book (regression check)**

```powershell
python -c "
import sys; sys.path.insert(0, 'tools')
from pdf_to_balabolka import detect_column_layout
r = detect_column_layout(r'archive\<single-column-pdf>', print)
print(r)
"
```

Expected: `'is_multicolumn': False, 'num_columns': 1`

---

## Task 3: Add `extract_text_columns()` to pdf_to_balabolka.py

**Files:**
- Modify: `tools/pdf_to_balabolka.py` — insert just before `_extract_with_pdfminer()` (~line 574)

This function extracts text per-page in left-then-right column order, emitting `<<PAGE:N>>\n{text}` per page — the same contract as `extract_text()`.

- [ ] **Step 1: Insert `extract_text_columns()` before `_extract_with_pdfminer()`**

```python
def extract_text_columns(pdf_path, log):
    """Extract text from a multi-column PDF using PyMuPDF, reading left column then right.

    For each page:
      1. Classify text blocks into left or right column by x-midpoint.
      2. Full-width blocks (>70% page width) are emitted at their natural y-position.
      3. Within each column, blocks are sorted top-to-bottom by y0.
      4. Output format: <<PAGE:N>>\\n{text} per page, joined with \\n — identical
         to extract_text() so all downstream processing works unchanged.
    """
    try:
        import pymupdf
    except ImportError:
        raise RuntimeError(
            "pymupdf is required for column extraction. "
            "Run: python -m pip install pymupdf"
        )

    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    log(f"  Column extraction: {total_pages} pages via PyMuPDF")

    pages_text = []

    for pg_idx in range(total_pages):
        page = doc[pg_idx]
        page_width  = page.rect.width
        page_height = page.rect.height
        midpoint    = page_width / 2.0
        footnote_y  = page_height * 0.85   # bottom 15% = footnote zone

        blocks = page.get_text("blocks")
        # block format: (x0, y0, x1, y1, text, block_no, block_type)
        text_blocks = [(b[0], b[1], b[2], b[3], (b[4] or '').strip())
                       for b in blocks if b[6] == 0 and (b[4] or '').strip()]

        left_col   = []  # (y0, text)
        right_col  = []  # (y0, text)
        full_width = []  # (y0, text) — spans both columns
        footnotes  = []  # (y0, text) — bottom 15%

        for x0, y0, x1, y1, text in text_blocks:
            if not text:
                continue
            block_width = x1 - x0

            # Footnote zone: separate regardless of column
            if y0 >= footnote_y:
                footnotes.append((y0, text))
                continue

            # Full-width: block spans more than 70% of page
            if block_width >= page_width * 0.70:
                full_width.append((y0, x0, text))
                continue

            # Column assignment by block center x
            block_center_x = (x0 + x1) / 2.0
            if block_center_x <= midpoint:
                left_col.append((y0, text))
            else:
                right_col.append((y0, text))

        # Sort each group top-to-bottom
        left_col.sort(key=lambda t: t[0])
        right_col.sort(key=lambda t: t[0])
        full_width.sort(key=lambda t: t[0])
        footnotes.sort(key=lambda t: t[0])

        # Interleave full-width blocks with column blocks in reading order:
        # full-width elements that appear ABOVE the first right-column block
        # are emitted before the left column; those in between columns are
        # emitted between; those below are emitted after.
        # Simple heuristic: emit all full-width in order, left, then right.
        # A future pass could interleave by y-position if needed.
        parts = []

        # Full-width blocks at the top (y0 before any column content)
        col_start_y = min(
            (left_col[0][0]  if left_col  else 999999),
            (right_col[0][0] if right_col else 999999)
        )
        top_full = [(y, x, t) for y, x, t in full_width if y < col_start_y]
        mid_full = [(y, x, t) for y, x, t in full_width if y >= col_start_y]

        for _, _, t in sorted(top_full, key=lambda x: x[0]):
            parts.append(t)

        for _, t in left_col:
            parts.append(t)
        for _, t in right_col:
            parts.append(t)

        for _, _, t in mid_full:
            parts.append(t)
        for _, t in footnotes:
            parts.append(t)

        if parts:
            page_text = "\n".join(parts)
            pages_text.append(f"<<PAGE:{pg_idx + 1}>>\n{page_text}")

        if (pg_idx + 1) % 50 == 0:
            log(f"  Column extraction: {pg_idx + 1}/{total_pages} pages processed...")

    doc.close()
    log(f"  Column extraction complete: {len(pages_text)} pages with text")
    return "\n".join(pages_text)
```

- [ ] **Step 2: Parse-check**

```powershell
python -c "import ast; ast.parse(open('tools/pdf_to_balabolka.py', encoding='utf-8').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Smoke-test extract_text_columns on a two-column book**

```powershell
python -c "
import sys; sys.path.insert(0, 'tools')
from pdf_to_balabolka import extract_text_columns
text = extract_text_columns(r'archive\<two-column-pdf>', print)
pages = text.split('<<PAGE:')
for p in pages[1:4]:
    print(p[:400])
    print('---')
"
```

Expected: Text reads naturally (left column content, then right column content), `<<PAGE:N>>` markers present.

---

## Task 4: Wire Column Detection into `extract_text()` and Thread `force_columns`

**Files:**
- Modify: `tools/pdf_to_balabolka.py` — four locations

This is the routing task. The key invariant: if `detect_column_layout()` returns `is_multicolumn=False` AND `force_columns` is False, the function must execute byte-for-byte identically to before.

### 4a — Add `force_columns` parameter + routing to `extract_text()`

- [ ] **Step 1: Modify the `extract_text()` signature and add routing block at top**

Change:
```python
def extract_text(pdf_path, log):
```
To:
```python
def extract_text(pdf_path, log, force_columns=False):
```

Then insert the following block IMMEDIATELY after the docstring, **BEFORE the `try: from pypdf import PdfReader` block** (which starts at line ~414). Inserting before the pypdf import means multi-column books return early without importing pypdf at all — a minor efficiency win. If placement before the import is awkward in context, inserting immediately after it is also acceptable since the pypdf import has no side-effects:

```python
    # --- Column layout detection ---
    # Check if PDF uses multi-column layout (academic papers, commentaries).
    # detect_column_layout() swallows its own ImportError (returns is_multicolumn=False
    # when pymupdf is absent), so the except block below only catches unexpected failures
    # from extract_text_columns() or other runtime errors.
    try:
        column_info = detect_column_layout(pdf_path, log)
        if column_info['is_multicolumn'] and column_info['confidence'] >= 0.6:
            log(f"  Multi-column layout detected: {column_info['num_columns']} columns "
                f"(confidence: {column_info['confidence']:.0%})")
            return extract_text_columns(pdf_path, log)
        elif force_columns:
            log("  --force-columns set, using column extraction despite low confidence")
            return extract_text_columns(pdf_path, log)
        else:
            log("  Single-column layout detected — using standard extraction")
    except Exception as e:
        log(f"  [WARN] Column detection/extraction failed: {e} — falling back to standard extraction")
```

> **Note:** The `except ImportError` branch from the original spec has been removed. `detect_column_layout()` catches its own ImportError internally (returns `is_multicolumn=False` gracefully). `extract_text_columns()` converts its ImportError to a RuntimeError, which is caught by `except Exception`. A bare `except ImportError` here would be dead code.

The rest of `extract_text()` is completely unchanged.

> **OCR interaction:** `force_columns` is only threaded through the non-OCR branch of `process_pdf()`. If `--ocr` and `--force-columns` are both passed, OCR wins and column extraction is skipped. This is correct: OCR applies to scanned/image-only PDFs where there is no text layer for PyMuPDF to analyze. Document-this-as-intentional if asked.

> **`--html-extraction` interaction:** `force_columns` is NOT passed to `process_kindle_html()`. The `--html-extraction` path uses pdfminer font-metadata HTML extraction, which is a separate code path that doesn't go through `extract_text()`. Column detection only applies to the standard text-layer extraction path. This is intentionally out-of-scope.

### 4b — Thread `force_columns` through `extract_text_auto()`

- [ ] **Step 2: Add `force_columns=False` to `extract_text_auto()` signature and PDF dispatch**

Change:
```python
def extract_text_auto(input_path, log, calibre_path=None):
```
To:
```python
def extract_text_auto(input_path, log, calibre_path=None, force_columns=False):
```

In the function body, change the PDF dispatch from:
```python
    if ext == 'pdf':
        return extract_text(input_path, log)
```
To:
```python
    if ext == 'pdf':
        return extract_text(input_path, log, force_columns=force_columns)
```

(The `elif ext == 'epub'` and `elif ext in (...)` branches are unchanged — column detection only applies to PDFs.)

### 4c — Thread `force_columns` through `process_pdf()`

- [ ] **Step 3: Add `force_columns=False` to `process_pdf()` and thread to `extract_text_auto()`**

Change:
```python
def process_pdf(input_path, output_path, log, chapter_hints_path=None,
                use_ocr=None, tesseract_path=None, poppler_path=None, ocr_dpi=300,
                calibre_path=None):
```
To:
```python
def process_pdf(input_path, output_path, log, chapter_hints_path=None,
                use_ocr=None, tesseract_path=None, poppler_path=None, ocr_dpi=300,
                calibre_path=None, force_columns=False):
```

Then in the non-OCR branch (the `else:` at `raw = extract_text_auto(...)`, ~line 6076), change:
```python
        raw = extract_text_auto(input_path, log, calibre_path=calibre_path)
```
To:
```python
        raw = extract_text_auto(input_path, log, calibre_path=calibre_path,
                                force_columns=force_columns)
```

### 4d — Thread `force_columns` through `process_kindle()`

- [ ] **Step 4: Add `force_columns=False` to `process_kindle()` and thread to `extract_text_auto()`**

Change:
```python
def process_kindle(input_path, output_path, log, chapter_hints_path=None, api_key=None,
                   calibre_path=None):
```
To:
```python
def process_kindle(input_path, output_path, log, chapter_hints_path=None, api_key=None,
                   calibre_path=None, force_columns=False):
```

In the function body, change:
```python
    raw = extract_text_auto(input_path, log, calibre_path=calibre_path)
```
To:
```python
    raw = extract_text_auto(input_path, log, calibre_path=calibre_path,
                            force_columns=force_columns)
```

### 4e — Add `--force-columns` CLI argument and wire through `main()`

- [ ] **Step 5: Add argparse argument**

In the argparse block (after the last `ap.add_argument(...)` call, before `args = ap.parse_args()`), insert:

```python
    ap.add_argument("--force-columns", action="store_true",
                    help="Force PyMuPDF column-aware extraction even if detection confidence is low")
```

- [ ] **Step 6: Wire `force_columns` into the main() call sites**

In `main()`, change:
```python
        elif args.mode == "kindle":
            process_kindle(input_path, output_path, log_fn, chapter_hints_path=hints_path,
                           api_key=args.api_key, calibre_path=args.calibre_path)
```
To:
```python
        elif args.mode == "kindle":
            process_kindle(input_path, output_path, log_fn, chapter_hints_path=hints_path,
                           api_key=args.api_key, calibre_path=args.calibre_path,
                           force_columns=args.force_columns)
```

And change:
```python
            process_pdf(input_path, output_path, log_fn,
                        chapter_hints_path=hints_path,
                        use_ocr=use_ocr,
                        tesseract_path=args.tesseract_path,
                        poppler_path=args.poppler_path,
                        ocr_dpi=args.ocr_dpi,
                        calibre_path=args.calibre_path)
```
To:
```python
            process_pdf(input_path, output_path, log_fn,
                        chapter_hints_path=hints_path,
                        use_ocr=use_ocr,
                        tesseract_path=args.tesseract_path,
                        poppler_path=args.poppler_path,
                        ocr_dpi=args.ocr_dpi,
                        calibre_path=args.calibre_path,
                        force_columns=args.force_columns)
```

- [ ] **Step 7: Parse-check after all routing changes**

```powershell
python -c "import ast; ast.parse(open('tools/pdf_to_balabolka.py', encoding='utf-8').read()); print('OK')"
```

Expected: `OK`

### 4f — Regression test: single-column books must be byte-identical

- [ ] **Step 8: Run the full test suite**

```powershell
python tools/test_pipeline.py
```

Expected: All test cases pass. No regressions. Column detection should log "Single-column layout detected" for all existing single-column test books.

---

## Task 5: PowerShell Integration — Convert-ToKindle

**Files:**
- Modify: `module/EbookAutomation.psm1` — Convert-ToKindle function (~line 474)

### 5a — Add `-ForceColumns` switch to Convert-ToKindle

- [ ] **Step 1: Add `[switch]$ForceColumns` to the Convert-ToKindle param block**

The param block currently ends at line ~528 (after `[string]$ChapterHintsFile`). Add the new parameter:

```powershell
        [string]$ChapterHintsFile

        # New: force PyMuPDF column-aware extraction
        [switch]$ForceColumns
    )
```

- [ ] **Step 2: Wire `--force-columns` into `$pyArgs` building**

After the block that adds `--html-extraction` (~line 616-617), add:

```powershell
                # Add force-columns flag if requested
                if ($ForceColumns) {
                    $pyArgs += " --force-columns"
                }
```

### 5b — Add `-ForceColumns` switch to Convert-ToTTS

- [ ] **Step 3: Add `[switch]$ForceColumns` to the Convert-ToTTS param block**

The param block (~line 236) currently ends with `[switch]$UseOCR`. Add:

```powershell
        [switch]$UseOCR
        [switch]$ForceColumns
    )
```

- [ ] **Step 4: Wire `--force-columns` into TTS Python args**

In Convert-ToTTS, after the block that adds `--calibre-path` (~line 313), add:

```powershell
        if ($ForceColumns) {
            $ocrArgs += ' --force-columns'
        }
```

### 5c — Add `-ForceColumns` switch to Invoke-EbookPipeline and thread through

- [ ] **Step 5: Add `[switch]$ForceColumns` to Invoke-EbookPipeline param block**

The param block (~line 1246) currently ends with `[switch]$UseOCR`. Add:

```powershell
        [switch]$UseOCR
        [switch]$ForceColumns
    )
```

- [ ] **Step 6: Log ForceColumns in the pipeline header**

After the `if ($UseOCR)` log line (~line 1272), add:

```powershell
    if ($ForceColumns) { Write-EbookLog "  Column extraction: FORCED (--force-columns)" }
```

- [ ] **Step 7: Thread ForceColumns through Convert-ToTTS call (~line 1360)**

Change:
```powershell
$ttsOk = Convert-ToTTS -InputFile $workCopy -OutputDir $ttsOutDir -UseClaudeChapters:$UseClaudeChapters -UseOCR:$UseOCR
```
To:
```powershell
$ttsOk = Convert-ToTTS -InputFile $workCopy -OutputDir $ttsOutDir -UseClaudeChapters:$UseClaudeChapters -UseOCR:$UseOCR -ForceColumns:$ForceColumns
```

- [ ] **Step 8: Thread ForceColumns through Convert-ToKindle call (~line 1433)**

Change:
```powershell
$kindleOk = Convert-ToKindle -InputFile $workCopy -OutputDir $kindleDir -UseClaudeChapters:$UseClaudeChapters
```
To:
```powershell
$kindleOk = Convert-ToKindle -InputFile $workCopy -OutputDir $kindleDir -UseClaudeChapters:$UseClaudeChapters -ForceColumns:$ForceColumns
```

### 5d — Optional: AZW3→KFX chain (Prompt 4, optional second conversion step)

> **Note:** The spec describes this as an "optional second conversion step" in the AZW3 fallback section. Implement only if the AZW3 fallback is producing results but KFX would be preferred.

- [ ] **Step 9: Add AZW3→KFX re-conversion attempt after AZW3 fallback succeeds**

In the AZW3 fallback section (~line 1100-1113), after `$outFile = $azw3OutFile`, insert:

```powershell
            # Optional: attempt AZW3 → KFX for better typography
            if ($outFmt -eq 'kfx') {
                $kfxFromAzw3 = [IO.Path]::ChangeExtension($azw3OutFile, '.kfx')
                $kfxArgs = "`"$azw3OutFile`" `"$kfxFromAzw3`""
                if ($cfg.kindle.calibre_options) { $kfxArgs += " $($cfg.kindle.calibre_options)" }
                Write-EbookLog "Kindle: attempting AZW3 -> KFX conversion for better typography..."
                $stopwatch.Restart()
                $proc3 = Start-Process -FilePath $calibre `
                                       -ArgumentList $kfxArgs `
                                       -PassThru -NoNewWindow `
                                       -RedirectStandardOutput $outLog `
                                       -RedirectStandardError $errFile
                while (-not $proc3.HasExited) {
                    Start-Sleep -Seconds 3
                    Write-EbookLog "Kindle: AZW3->KFX converting... ($([math]::Round($stopwatch.Elapsed.TotalSeconds, 0))s elapsed)"
                }
                $proc3.WaitForExit()
                if (($proc3.ExitCode -eq 0 -or $null -eq $proc3.ExitCode) -and (Test-Path $kfxFromAzw3)) {
                    Write-EbookLog "Kindle: AZW3->KFX succeeded — using KFX output" -Level SUCCESS
                    Remove-Item $azw3OutFile -Force -ErrorAction SilentlyContinue
                    $outFile = $kfxFromAzw3
                } else {
                    Write-EbookLog "Kindle: AZW3->KFX failed — keeping AZW3 output" -Level WARN
                }
            }
```

- [ ] **Step 10: Verify the module loads without syntax errors**

```powershell
Import-Module .\module\EbookAutomation.psm1 -Force
Get-Command -Module EbookAutomation
```

Expected: Module imports cleanly; `Convert-ToKindle`, `Convert-ToTTS`, `Invoke-EbookPipeline` all listed.

---

## Task 6: Create Test Script tools/test_columns.ps1

**Files:**
- Create: `tools/test_columns.ps1`

- [ ] **Step 1: Create the test script**

```powershell
<#
.SYNOPSIS
    Test matrix for two-column PDF detection and extraction (SCRUM-62).
    Run from the project root: .\tools\test_columns.ps1
#>

Import-Module .\module\EbookAutomation.psm1 -Force -ErrorAction Stop

$cfg    = Get-EbookConfig
$python = $cfg.paths.python

# --- Test cases ---
# Pattern matches against archive\ filenames (case-insensitive partial match)
$tests = @(
    @{ Name = "Ezekiel II (two-column commentary)"; Pattern = "*Ezekiel*"; ExpectColumns = $true  }
    @{ Name = "Oil Kings (single-column history)";  Pattern = "*Oil*Kings*"; ExpectColumns = $false }
    @{ Name = "Brother of Jesus (single-column)";   Pattern = "*Brother*Jesus*"; ExpectColumns = $false }
    @{ Name = "Mexico (single-column history)";      Pattern = "*Mexico*"; ExpectColumns = $false }
)

$pass = 0
$fail = 0
$skip = 0

foreach ($test in $tests) {
    $file = Get-ChildItem archive -Filter $test.Pattern -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in '.pdf', '.epub', '.mobi', '.azw', '.azw3' } |
            Select-Object -First 1

    if (-not $file) {
        Write-Host "`nSKIP: $($test.Name) — file not found in archive\" -ForegroundColor Yellow
        $skip++
        continue
    }

    Write-Host "`n=== $($test.Name) ===" -ForegroundColor Cyan
    Write-Host "    File: $($file.Name)"

    # Run column detection via Python
    $detectScript = @"
import sys
sys.path.insert(0, 'tools')
from pdf_to_balabolka import detect_column_layout
result = detect_column_layout(r'$($file.FullName.Replace("'", "\\'"))', print)
print(f"RESULT: columns={result['num_columns']} confidence={result['confidence']:.0%} multicolumn={result['is_multicolumn']}")
"@

    $output = & $python -c $detectScript 2>&1
    foreach ($line in $output) { Write-Host "  $line" }

    $resultLine = $output | Where-Object { $_ -match '^RESULT:' } | Select-Object -Last 1
    $detected   = $resultLine -match "multicolumn=True"

    if ($detected -eq $test.ExpectColumns) {
        Write-Host "  PASS: detection=$detected, expected=$($test.ExpectColumns)" -ForegroundColor Green
        $pass++
    } else {
        Write-Host "  FAIL: detection=$detected, expected=$($test.ExpectColumns)" -ForegroundColor Red
        $fail++
    }

    # For expected multi-column, also do a full extraction smoke test
    if ($test.ExpectColumns -and $detected) {
        Write-Host "  Running full column extraction..."
        $extractScript = @"
import sys
sys.path.insert(0, 'tools')
from pdf_to_balabolka import extract_text_columns
text = extract_text_columns(r'$($file.FullName.Replace("'", "\\'"))', print)
pages = text.split('<<PAGE:')
print(f"EXTRACT_RESULT: {len(pages)-1} pages extracted")
for p in pages[1:4]:
    print('--- Page ---')
    print(p[:300])
"@
        $extractOut = & $python -c $extractScript 2>&1
        foreach ($line in $extractOut) { Write-Host "  $line" }
    }
}

Write-Host "`n===========================" -ForegroundColor Cyan
Write-Host "Results: PASS=$pass  FAIL=$fail  SKIP=$skip"
if ($fail -eq 0) {
    Write-Host "All tests passed." -ForegroundColor Green
} else {
    Write-Host "$fail test(s) FAILED." -ForegroundColor Red
}
```

- [ ] **Step 2: Run the test script**

```powershell
.\tools\test_columns.ps1
```

Expected:
- Ezekiel (if present): PASS with `multicolumn=True`
- Oil Kings, Brother of Jesus, Mexico: PASS with `multicolumn=False`
- Any "SKIP" lines are acceptable (file not in archive)

---

## Task 7: Regression Test — Full Test Suite

- [ ] **Step 1: Run the full pipeline test suite**

```powershell
python tools/test_pipeline.py
```

Expected: All existing test cases pass. Zero regressions.

- [ ] **Step 2: Spot-check a known-good single-column conversion**

Check the column detection log line appears and says "Single-column layout detected":

```powershell
python tools/pdf_to_balabolka.py --input archive\<single-column-book>.pdf --mode kindle --output-dir output\kindle
```

Look for:
```
  Single-column layout detected — using standard extraction
```
in the output.

---

## Task 8: Update CLAUDE.md Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add pymupdf to the External Dependencies table**

In the "External Dependencies" section, add a new row after the pypdf row:

```markdown
| pymupdf | pip package | Two-column PDF layout detection and column-aware text extraction |
```

- [ ] **Step 2: Add column detection routing to the Pipeline Architecture section**

In "Pipeline Architecture", after the two existing extraction paths, add:

```markdown
**Column detection gate (runs before both paths for PDFs):**
`detect_column_layout()` (PyMuPDF) → if multi-column + confidence ≥ 60%: `extract_text_columns()` → joins with `<<PAGE:N>>` markers; downstream unchanged
Single-column PDFs skip this gate entirely and follow path 1 or 2 as before.
CLI flag `--force-columns` bypasses the confidence threshold.
```

- [ ] **Step 3: Note the new `--force-columns` CLI flag in pdf_to_balabolka.py section**

In the "pdf_to_balabolka.py — Modes" table, update the Kindle CLI row:

```markdown
| Kindle CLI | `--input book.pdf --mode kindle` | ... same as before ... |
| Kindle CLI (columns) | `--input book.pdf --mode kindle --force-columns` | Forces PyMuPDF column-aware extraction |
```

---

## Completion Checklist

Before calling this done:

- [ ] `python -c "import pymupdf"` succeeds
- [ ] `detect_column_layout()` returns `is_multicolumn=True` for a known two-column PDF
- [ ] `detect_column_layout()` returns `is_multicolumn=False` for single-column books
- [ ] `extract_text_columns()` output contains `<<PAGE:N>>` markers and readable text
- [ ] `python tools/test_pipeline.py` passes all existing test cases (zero regressions)
- [ ] `Import-Module .\module\EbookAutomation.psm1 -Force` loads without errors
- [ ] `Convert-ToKindle -ForceColumns` passes `--force-columns` to Python
- [ ] `.\tools\test_columns.ps1` runs and all present test books pass
- [ ] CLAUDE.md updated with pymupdf dependency and column detection routing
