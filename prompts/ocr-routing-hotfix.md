# EB-83 Hotfix: Fix OCR over-routing in batch_qa

## Session Name
ocr-routing-hotfix

## Claude Code Model
Opus — subtle diagnostic issue, multi-signal classification swap, must avoid re-introducing regressions

## Problem

EB-83 (commit `7a9161a`) introduced OCR auto-routing in `batch_qa.py`. A validation batch (batch_20260405_181114) revealed **38 of 100 books** are being incorrectly routed to OCR, causing pass rate to drop from 75% → 41%.

### Root cause (two-pronged)

**Problem 1**: `detect_pdf_type()` in `pdf_to_balabolka.py` uses a chars-per-page threshold of just 50 to classify PDFs as `image` vs `structured`. But pypdf's `extract_text()` frequently returns zero or near-zero chars for digital-native PDFs with CIDFont encoding, embedded fonts, or complex layouts. This causes false positives.

**Problem 2**: The DE-4 `detect_image_density()` `likely_scan` hint in `collect_diagnostics()` pre-routes books to OCR before `detect_pdf_type()` even runs. Many digital PDFs have 1+ embedded image per page (cover art, figures, inline graphics), which triggers `likely_scan = True`.

### The damage

- **38 books** routed to `--ocr` instead of `--html-extraction`
- **ALL 38** have 0 chapters detected (OCR output = plain text, no font metadata for heading detection)
- **31 of 38** have word counts > 5,000 — clearly digital-native, not scans
- Examples: Ezekiel II (417k words), Aquinas (529k words), "America and Iran" (265k words)
- `html_extraction` path still works fine: 36/48 pass (75%)
- `pymupdf_columns` path still perfect: 5/5 pass (100%)

### The solution

Replace `detect_pdf_type()` with `classify_source.classify_pdf()` — the multi-signal classifier that already exists and uses:
- **Text density** (500 chars/page threshold for digital, not 50)
- **Image dominance** via PyMuPDF (checks actual image-to-text ratio, not just image count)
- **Producer metadata** (recognizes scan producers vs digital producers)
- Returns `flags.needs_ocr = True` ONLY for `scan_no_text` classification

Also stop trusting the DE-4 `likely_scan` hint as a pre-routing signal — it's too coarse.

## Fix — All changes in `tools/batch_qa.py`

### Phase 1: Audit the current EB-83 code

Read `run_extraction_for_book()` as it exists NOW (after EB-83 commit `7a9161a`). Confirm:
1. The `is_scan` parameter and how the DE-4 hint flows in
2. Where `detect_pdf_type()` is imported and called
3. The scan detection logic block
4. How `scan_detected` gates `--ocr` vs `--html-extraction`

Also read the DE-4 block in `collect_diagnostics()` to see how `_is_scan_hint` is set.

Report exact line numbers and current code before making changes.

### Phase 2: Replace scan detection in `run_extraction_for_book()`

Replace the `detect_pdf_type()` call with `classify_source.classify_pdf()`:

1. **Change the import** — replace:
   ```python
   from pdf_to_balabolka import detect_pdf_type
   ```
   with:
   ```python
   from classify_source import classify_pdf
   ```

2. **Replace the scan detection block** in `run_extraction_for_book()`. The new logic should be:
   ```python
   # For PDFs: use multi-signal classifier to decide OCR vs HTML extraction
   if ext in ('.pdf',):
       scan_detected = False  # Default: use html_extraction
       
       # Only auto-detect if caller didn't force a decision
       if is_scan is None:
           try:
               classification = classify_pdf(str(pdf_path))
               needs_ocr = classification.get('flags', {}).get('needs_ocr', False)
               cls_type = classification.get('classification', 'unknown')
               confidence = classification.get('confidence', 0)
               
               if needs_ocr:
                   scan_detected = True
                   text_density = classification.get('signals', {}).get('text_density_per_page', 0)
                   logger.info("Scan detected for %s: %s (confidence %.2f, %.0f chars/page) — routing to OCR",
                               pdf_path.name, cls_type, confidence, text_density)
               else:
                   logger.debug("PDF classified as %s (confidence %.2f) for %s — using html_extraction",
                                cls_type, confidence, pdf_path.name)
           except Exception as e:
               logger.debug("PDF classification failed for %s: %s — defaulting to html_extraction", 
                            pdf_path.name, e)
               scan_detected = False
       elif is_scan is True:
           scan_detected = True
       # else: is_scan is False → scan_detected stays False
       
       if scan_detected:
           cmd.append("--ocr")
       else:
           cmd.append("--html-extraction")
   ```

   **Key difference from EB-83**: Only `classify_pdf()` returning `needs_ocr: True` (which requires `scan_no_text` = text_density < 50 AND image_dominant pages) triggers OCR. The old `detect_pdf_type()` used a 50-char threshold with pypdf alone, which was unreliable.

3. **Keep the timeout scaling** from EB-83 — it's correct:
   ```python
   if scan_detected:
       timeout = max(1200, 1200 + int((file_size_mb - 20) * 15)) if file_size_mb > 20 else 1200
   else:
       timeout = max(600, 600 + int((file_size_mb - 20) * 15)) if file_size_mb > 20 else 600
   ```

### Phase 3: Fix the DE-4 hint passthrough in `collect_diagnostics()`

The DE-4 `likely_scan` hint from `detect_image_density()` is too coarse to use as a pre-routing signal. Change the hint logic to be much more conservative:

Find the block after DE-4 that sets `_is_scan_hint`. Replace:
```python
# After DE-4 image density detection
_is_scan_hint = None
if diag["metadata"].get("image_density", {}).get("likely_scan"):
    _is_scan_hint = True
```

With:
```python
# After DE-4 image density detection
# Don't pre-route based on image density alone — let classify_pdf() decide.
# The DE-4 data is still recorded in diagnostics for reporting.
_is_scan_hint = None
```

This means `is_scan` is always `None` when `run_extraction_for_book()` is called, so `classify_pdf()` always runs. The DE-4 density data is still captured in the diagnostics JSON for analysis — we just don't use it as a routing signal anymore.

### Phase 4: Update extraction_path metadata

The existing OCR detection in the metadata section should still work (it checks stdout/stderr for OCR indicators). Verify that when `classify_pdf()` routes to OCR, the batch JSON correctly reports `extraction_path: "ocr"`. No changes should be needed here, but confirm.

### Phase 5: Run tests and verify

```
python tools/test_pipeline.py --quick
python tools/test_voice_tags.py
```

**Expected**: 41/41 pipeline, 75/75 voice tags. The test suite doesn't include scanned PDF fixtures, so all tests should route through `--html-extraction` as before.

### Verification checklist

Report these specific findings:
1. **Import**: Confirm `classify_pdf` is imported from `classify_source` (not `detect_pdf_type` from `pdf_to_balabolka`)
2. **Classification call**: Show the `classify_pdf()` call and `needs_ocr` check
3. **Fallback behavior**: When classification fails, confirm it defaults to `--html-extraction` (not OCR)
4. **DE-4 hint**: Confirm `_is_scan_hint` is always `None` (no pre-routing)
5. **Timeout scaling**: Confirm OCR timeout (1200s) and non-OCR timeout (600s + 15s/MB) are preserved
6. **Test results**: 41/41 pipeline, 75/75 voice tags

## Post-change

Commit and push:
```
git add tools/batch_qa.py
git commit -m "EB-83 hotfix: fix OCR over-routing — switch to classify_pdf()

Regression: detect_pdf_type() over-routed 38/100 books to OCR (75%→41% pass).
Root cause: pypdf returns near-zero chars for many digital PDFs (CIDFont
encoding) + DE-4 likely_scan hint too coarse.

Fix:
- Replace detect_pdf_type() with classify_source.classify_pdf() (multi-signal)
- Only route to OCR when needs_ocr=True (scan_no_text classification)
- Remove DE-4 likely_scan as pre-routing hint (too many false positives)
- classify_pdf uses text density + image dominance + producer metadata
- html_extraction path unchanged (75% pass rate preserved)
- 41/41 pipeline, 75/75 voice tags"
git push origin master
```

## What NOT to change

- Do NOT modify `pdf_to_balabolka.py` — its internal `detect_pdf_type()` + zero-text escalation work correctly for single-book runs
- Do NOT modify `classify_source.py` — its thresholds and multi-signal logic are well-calibrated
- Do NOT modify `test_pipeline.py` — just fixed in EB-80
- Do NOT remove the DE-4 `detect_image_density()` call from `collect_diagnostics()` — the data is still valuable for diagnostics, just don't use it for routing
- Do NOT change EPUB/MOBI/AZW3 routing from EB-82
- Do NOT change the timeout scaling from EB-83
