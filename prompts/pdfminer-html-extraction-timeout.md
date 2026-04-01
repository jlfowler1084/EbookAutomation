# EB-70: pdfminer HTML Extraction Timeout Protection

## Session Name
Pdfminer HTML Extraction Timeout

## Claude Code Model
Sonnet — well-scoped single-function changes with clear existing patterns (threading already imported, PyMuPDF fallback exists)

## Context

Hero Tales flipped from PASS (125s cached) to FAIL (680s timeout) on a fresh-cache batch run. The root cause: `extract_with_pdfminer_html()` at line ~4439 in `tools/pdf_to_balabolka.py` has **no internal timeout mechanism**. The `extract_pages()` generator iterates page-by-page with no time budget. When pdfminer hangs on a problematic page (complex fonts, embedded objects, malformed streams), the entire process stalls until `batch_qa.py`'s 600s subprocess timeout kills it — losing ALL extraction work.

EB-65 previously added PyMuPDF fallback for the *text* extraction path, but the HTML extraction path (used by `--mode kindle --html-extraction`) has no equivalent protection.

The `threading` module is already imported at line 26.

## Ticket
EB-70

## Changes Required — pdf_to_balabolka.py ONLY

### Step 1: Add a per-page timeout wrapper function

Add this BEFORE `extract_with_pdfminer_html()` (around line ~4435):

```python
def _extract_page_with_timeout(page_layout, timeout_seconds=30):
    """Run pdfminer page layout iteration with a time budget.
    
    Returns the page_layout elements if completed within budget, or None if timed out.
    Uses a thread to run the layout iteration and joins with timeout.
    """
    result = {'elements': None, 'error': None}
    
    def _iterate():
        try:
            # Force pdfminer to fully resolve the page layout by iterating elements.
            # extract_pages() is lazy — the actual PDF parsing happens when you
            # iterate the page_layout's children, not when the generator yields.
            elements = []
            for element in page_layout:
                elements.append(element)
            result['elements'] = elements
        except Exception as e:
            result['error'] = e
    
    thread = threading.Thread(target=_iterate, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    
    if thread.is_alive():
        # Thread is still running — page timed out
        # Daemon thread will be cleaned up when process exits
        return None
    
    if result['error']:
        raise result['error']
    
    return result['elements']
```

### Step 2: Add time budget tracking to `extract_with_pdfminer_html()`

Inside `extract_with_pdfminer_html()`, right after the `all_paras = []` initialization (~line 4475), add:

```python
    extraction_start = time.time()
    OVERALL_BUDGET_SECONDS = 480  # leave 120s headroom for post-processing
    PER_PAGE_BUDGET_SECONDS = 30
    pages_skipped = 0
    budget_exhausted = False
```

### Step 3: Replace the page iteration loop

The current loop at ~line 4479 is:
```python
    for page_num, page_layout in enumerate(extract_pages(pdf_path, laparams=laparams)):
        total_pages += 1
        pg = page_num + 1  # 1-indexed
        page_width = page_layout.width
        
        # Insert page marker
        all_paras.append({...})
        
        # Collect all text lines on this page with font metadata
        page_lines = []
        for element in page_layout:
            if not isinstance(element, LTTextBox):
                continue
```

Replace the **outer `for` loop start** and the **inner `for element in page_layout`** with timeout-aware versions. The structure becomes:

```python
    for page_num, page_layout in enumerate(extract_pages(pdf_path, laparams=laparams)):
        total_pages += 1
        pg = page_num + 1  # 1-indexed
        
        # ── Overall budget check ──────────────────────────────────────
        elapsed = time.time() - extraction_start
        if elapsed > OVERALL_BUDGET_SECONDS:
            log(f"  [WARN] Overall extraction budget exhausted ({elapsed:.0f}s > {OVERALL_BUDGET_SECONDS}s) "
                f"after {pg - 1} pages — stopping early")
            budget_exhausted = True
            break
        
        # ── Per-page timeout ──────────────────────────────────────────
        page_start = time.time()
        elements = _extract_page_with_timeout(page_layout, PER_PAGE_BUDGET_SECONDS)
        page_elapsed = time.time() - page_start
        
        if elements is None:
            pages_skipped += 1
            log(f"  [WARN] Page {pg} timed out after {page_elapsed:.1f}s — skipping")
            # Still insert page marker so page numbering stays correct
            all_paras.append({
                'text': '', 'font_size': 0, 'is_bold': False, 'is_italic': False,
                'is_centered': False, 'is_all_caps': False, 'page_number': pg,
                'line_count': 0, 'char_count': 0, 'is_page_marker': True,
            })
            continue
        
        page_width = page_layout.width

        # Insert page marker
        all_paras.append({
            'text': '', 'font_size': 0, 'is_bold': False, 'is_italic': False,
            'is_centered': False, 'is_all_caps': False, 'page_number': pg,
            'line_count': 0, 'char_count': 0, 'is_page_marker': True,
        })

        # Collect all text lines on this page with font metadata
        page_lines = []
        for element in elements:  # <-- iterate pre-resolved elements, NOT page_layout
            if not isinstance(element, LTTextBox):
                continue
```

**IMPORTANT**: The rest of the inner loop body (lines, chars, font detection, etc.) stays exactly the same — only the `for element in page_layout:` changes to `for element in elements:`.

### Step 4: Add summary logging after the extraction loop

Right after the extraction loop ends (after the existing `if pg % 50 == 0:` progress log, before the `# Log font summary` section), add:

```python
    if pages_skipped > 0:
        log(f"  [WARN] Extraction completed with {pages_skipped} page(s) skipped due to timeout")
    if budget_exhausted:
        log(f"  [WARN] Extracted {total_pages} of unknown total pages before budget exhaustion")
```

### Step 5: PyMuPDF fallback on budget exhaustion

After the summary logging from Step 4, if budget was exhausted AND we got very few paragraphs, attempt PyMuPDF recovery:

```python
    # ── PyMuPDF fallback on budget exhaustion ─────────────────────────
    content_paras = [p for p in all_paras if not p.get('is_page_marker') and p.get('text', '').strip()]
    if budget_exhausted and len(content_paras) < 50:
        log(f"  [WARN] Only {len(content_paras)} content paragraphs from pdfminer before timeout")
        log(f"  Attempting PyMuPDF HTML fallback...")
        try:
            pymupdf_paras, pymupdf_body_size = _extract_html_with_pymupdf_columns(pdf_path, log)
            pymupdf_content = [p for p in pymupdf_paras if not p.get('is_page_marker') and p.get('text', '').strip()]
            if len(pymupdf_content) > len(content_paras):
                log(f"  PyMuPDF fallback recovered {len(pymupdf_content)} paragraphs (vs {len(content_paras)} from pdfminer)")
                return pymupdf_paras, pymupdf_body_size
            else:
                log(f"  PyMuPDF fallback got {len(pymupdf_content)} paragraphs — keeping pdfminer result")
        except Exception as e:
            log(f"  [WARN] PyMuPDF fallback failed: {e} — keeping partial pdfminer result")
```

**Place this BEFORE the `# Log font summary` section** so the fallback can short-circuit the return.

## Verification — MANDATORY

Run these checks and report exact numbers:

### Check 1: Hero Tales extraction
```
cd F:\Projects\EbookAutomation
python tools/pdf_to_balabolka.py --input "C:\Users\Joe\Downloads\Hero Tales.pdf" --mode kindle --html-extraction --output-dir temp_hero_test 2>&1 | findstr /i "page timeout budget skip warn extract"
```
**Report**: Total extraction time, pages skipped (if any), whether it completed without subprocess timeout.

### Check 2: Oil Kings regression canary
```
python tools/test_pipeline.py --quick --filter "Oil Kings"
```
**Must be**: 17/17 PASS

### Check 3: Full test suite
```
python tools/test_pipeline.py --quick
```
**Must be**: 41/41 PASS

### Check 4: Verify timeout mechanism works
If Hero Tales completes too fast to test the timeout, add a temporary 1-second per-page budget, run against a large book, confirm pages get skipped in the log, then restore to 30s.

## Git
```
git add -A
git commit -m "fix: EB-70 — add per-page and overall time budget to pdfminer HTML extraction"
git push origin master
```
