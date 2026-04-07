# EB-83: Auto-route scanned PDFs to OCR in batch_qa

## Session Name
ocr-auto-routing

## Claude Code Model
Sonnet — single-file change in batch_qa.py with clear diagnostic routing logic

## Problem

Scanned PDFs hit the 600s timeout in batch_qa because `run_extraction_for_book()` always passes `--html-extraction` for PDFs (as of EB-82's format-aware routing). This routes through `process_html_extraction()` — a path with **no scan detection or OCR escalation**. pdfminer spends up to 10 minutes trying to extract text from image-only pages before timing out.

The pipeline already has working OCR infrastructure:
- `detect_pdf_type()` in `pdf_to_balabolka.py` — checks chars/page to classify as `text`/`image`/`mixed`
- `detect_image_density()` in `pdf_to_balabolka.py` — checks images/page for scan likelihood  
- `extract_text_ocr()` — Tesseract-based OCR extraction
- `--ocr` CLI flag — forces OCR path in `pdf_to_balabolka.py`
- `classify_source.classify_pdf()` — comprehensive classification with `needs_ocr` flag

But `batch_qa.py` bypasses all of this by calling `pdf_to_balabolka.py` directly with `--html-extraction`.

### Evidence from batch_20260403_231239

| Book | Size | Scan signal | Result |
|------|------|-------------|--------|
| AnnalsoftheFowlerFamily | 14 MB | 5.2 images/page, likely_scan=True | TIMEOUT 601s |
| Budd Hopkins Missing Time | 11.8 MB | 1.0 images/page | TIMEOUT 601s |
| Aquinas Basic Writings | 39.3 MB | not scan — just huge | TIMEOUT 831s |

batch_qa **already detects** these as scans via `detect_image_density()` in the DE-4 diagnostic step — it just doesn't act on the information when building the subprocess command.

## Fix — All changes in `tools/batch_qa.py`

### Phase 1: Audit current code paths

Before making changes, verify the current state of `run_extraction_for_book()` and `collect_diagnostics()`:

1. Read `run_extraction_for_book()` — confirm EB-82's format-aware routing is in place (PDF → `--html-extraction`, EPUB → `--epub-html`, MOBI/AZW3 → no flag + `--calibre-path`)
2. Read `collect_diagnostics()` — confirm DE-4 runs `detect_image_density()` before calling `run_extraction_for_book()`
3. Note the exact line numbers and current imports

Report what you find before proceeding.

### Phase 2: Add scan detection to `run_extraction_for_book()`

**Goal**: For PDF files, detect scans before launching the subprocess and route to `--ocr` instead of `--html-extraction`.

1. Add import at top of file (near existing pdf_to_balabolka imports):
   ```python
   # Add to the existing imports from pdf_to_balabolka
   from pdf_to_balabolka import detect_pdf_type
   ```

2. Add a new parameter `is_scan=None` to `run_extraction_for_book()`:
   ```python
   def run_extraction_for_book(pdf_path, output_dir, quick=True, is_scan=None):
   ```

3. In the PDF branch of the format-aware routing (where `--html-extraction` is currently added), add scan detection:
   ```python
   # For PDFs: check if scanned before choosing extraction strategy
   if ext in ('.pdf',):
       scan_detected = is_scan  # Use caller's hint if provided
       if scan_detected is None:
           # Auto-detect: quick check using detect_pdf_type
           try:
               detection = detect_pdf_type(str(pdf_path), lambda msg: None)
               scan_detected = (detection.get('pdf_type') == 'image')
               if scan_detected:
                   logger.info("Scan detected for %s (avg %.0f chars/page) — routing to OCR",
                               pdf_path.name, detection.get('avg_chars_per_page', 0))
           except Exception as e:
               logger.debug("Scan detection failed for %s: %s", pdf_path.name, e)
               scan_detected = False
       
       if scan_detected:
           cmd.append("--ocr")
       else:
           cmd.append("--html-extraction")
   ```

4. Ensure `--tesseract-path` and `--poppler-path` are passed (these should already be present from EB-82, but verify they're included for the OCR path too — OCR needs both).

5. **Timeout scaling for OCR mode**: OCR is inherently slower. Update the timeout calculation:
   ```python
   # Scale timeout: 
   # - Standard: base 600s + 10s per MB over 20MB
   # - OCR: base 1200s + 15s per MB over 20MB (OCR renders every page as image)
   file_size_mb = os.path.getsize(str(pdf_path)) / (1024 * 1024)
   if scan_detected:
       timeout = max(1200, 1200 + int((file_size_mb - 20) * 15)) if file_size_mb > 20 else 1200
   else:
       timeout = max(600, 600 + int((file_size_mb - 20) * 10)) if file_size_mb > 20 else 600
   ```
   **Important**: The `scan_detected` variable must be available at this point. Make sure the timeout calculation happens AFTER scan detection, not before.

### Phase 3: Pass scan hint from collect_diagnostics()

In `collect_diagnostics()`, the DE-4 step already computes `detect_image_density()` and stores the result. Pass this as a hint to `run_extraction_for_book()` to avoid duplicate detection work:

1. After the DE-4 block, extract the scan signal:
   ```python
   # After DE-4 image density detection
   _is_scan_hint = None
   if diag["metadata"].get("image_density", {}).get("likely_scan"):
       _is_scan_hint = True
   ```

2. Pass it to the extraction call:
   ```python
   html_path, txt_path, stdout, stderr, exit_code = \
       run_extraction_for_book(file_path, output_dir, quick, is_scan=_is_scan_hint)
   ```

### Phase 4: Update extraction_path metadata

The batch report should correctly reflect when OCR was used. In `collect_diagnostics()`, after extraction completes:

1. Find where `strategy_selected` and `extraction_path` are set (EB-82 added format-aware values here)
2. Add OCR detection: if `_is_scan_hint` was True OR stdout contains OCR indicators, set:
   ```python
   if _is_scan_hint or (stdout and '--ocr' in ' '.join(cmd_used if 'cmd_used' in dir() else [])):
       diag["extraction"]["extraction_path"] = "ocr"
       diag["extraction"]["strategy_selected"] = "ocr"
   ```
   
   **Alternative approach** (simpler): Check the stdout/stderr from the subprocess for OCR indicators:
   ```python
   combined_output = (stdout or '') + (stderr or '')
   if 'OCR:' in combined_output or 'extract_text_ocr' in combined_output:
       diag["extraction"]["extraction_path"] = "ocr"
       diag["extraction"]["strategy_selected"] = "ocr"
   ```
   
   Use whichever approach is cleaner given the actual code structure. The key requirement is that the batch JSON shows `extraction_path: "ocr"` for scanned books.

### Phase 5: Bump timeout factor for large non-scan PDFs

The Aquinas Basic Writings (39.3 MB) timed out at 831s against a 790s budget. The current formula is `600 + (mb - 20) * 10`. For 39.3 MB: `600 + (19.3 * 10) = 793s`. Actual time was 831s.

Bump the per-MB factor from 10 to 15 for non-OCR PDFs as well:
```python
# Before (may have been set in EB-79):
timeout = max(600, 600 + int((file_size_mb - 20) * 10)) if file_size_mb > 20 else 600

# After:
timeout = max(600, 600 + int((file_size_mb - 20) * 15)) if file_size_mb > 20 else 600
```

This gives Aquinas: `600 + (19.3 * 15) = 890s` — enough headroom.

### Phase 6: Run tests and verify

```
python tools/test_pipeline.py --quick
python tools/test_voice_tags.py
```

**Expected**: 41/41 pipeline, 75/75 voice tags. No regressions — the change only affects the subprocess command for scanned PDFs.

### Verification checklist

Report these specific findings:
1. **Imports**: Confirm `detect_pdf_type` is imported from `pdf_to_balabolka`
2. **Scan detection**: Show the exact code block that decides `--ocr` vs `--html-extraction`
3. **Timeout scaling**: Show the OCR timeout formula (should be 1200s base)
4. **Non-OCR timeout**: Show the bumped factor (should be 15s/MB, not 10)
5. **Metadata**: Show how `extraction_path` is set to `"ocr"` for scanned books
6. **Scan hint passthrough**: Show `is_scan=_is_scan_hint` in the `run_extraction_for_book()` call
7. **Test results**: 41/41 pipeline, 75/75 voice tags

## Post-change

Commit and push:
```
git add tools/batch_qa.py
git commit -m "EB-83: Auto-route scanned PDFs to OCR in batch_qa

- detect_pdf_type() check before subprocess launch
- Scans get --ocr flag instead of --html-extraction
- OCR timeout: 1200s base + 15s/MB (vs 600s for standard)
- Non-OCR timeout bumped to 15s/MB for large PDFs (Aquinas fix)
- Scan hint passthrough from DE-4 density check
- extraction_path metadata reports 'ocr' for scanned books
- 41/41 pipeline, 75/75 voice tags"
git push origin master
```

## What NOT to change

- Do NOT modify `pdf_to_balabolka.py` — the OCR infrastructure there is working correctly
- Do NOT modify `classify_source.py` — it's not involved in this fix
- Do NOT modify `test_pipeline.py` — the test suite doesn't test scanned PDFs (no scanned test fixtures)
- Do NOT add new dependencies
- Do NOT change the EPUB or MOBI/AZW3 routing from EB-82
