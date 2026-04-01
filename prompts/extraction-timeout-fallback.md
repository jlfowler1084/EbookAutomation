# EB-65: Extraction Timeout Fallback — 3 Books Hang at 600s With Zero Content

## Session Name
Extraction Timeout Fallback

## Claude Code Model
**Opus** — threading-based timeout on Windows, multi-file integration, fallback logic

## Context

Batch QA found 3 academic books that hang during pdfminer HTML extraction with zero content:

| Book | Duration | Issue |
|------|----------|-------|
| Didache (SBL Press) | 600s timeout | pdfminer hangs |
| Origen On First Principles vol 1 (OUP 2017) | 600s timeout | pdfminer hangs |
| Origen On First Principles vol 2 (OUP 2018) | 600s timeout | pdfminer hangs |

The hang occurs in `extract_with_pdfminer_html()` in `tools/pdf_to_balabolka.py`. The function calls pdfminer's `extract_pages()` generator (around line 4481) which processes pages one at a time and never returns for these PDFs.

### Current behavior:
- **Batch (batch_qa.py):** subprocess timeout at 600s → returns zero content → book marked FAIL
- **Interactive (Convert-ToKindle):** no timeout → hangs indefinitely → user must Ctrl+C

### Test books (in `C:\Users\Joe\Downloads\`):
1. `[Early Christianity and Its Literature (Book 14)] Jonathan A. Draper*Didache*.pdf`
2. `[Oxford Early Christian Texts] Origenes*On First Principles 2*.pdf`
3. `[Oxford early christian texts] Origenes*On First Principles 1*.pdf`

---

## Phase 1: Quick Diagnostic

Before building any timeout mechanism, check if these books are fundamentally extractable.

### Step 1a: File properties
For each of the 3 books, check:
```python
import fitz  # PyMuPDF
doc = fitz.open(pdf_path)
print(f"Pages: {len(doc)}")
print(f"File size: {os.path.getsize(pdf_path) / 1024 / 1024:.1f} MB")
# Try extracting text from just page 1 with PyMuPDF (fast, no pdfminer)
page = doc[0]
text = page.get_text()
print(f"Page 1 text length: {len(text)} chars")
print(f"Page 1 first 200 chars: {text[:200]}")
```

This tells us: are these huge files? Can PyMuPDF extract text at all? Is the text layer present?

### Step 1b: Identify where pdfminer hangs
Try extracting page-by-page with pdfminer, with a per-page timeout:

```python
from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams
import time

laparams = LAParams(word_margin=0.05)
for i, page_layout in enumerate(extract_pages(pdf_path, laparams=laparams)):
    t0 = time.time()
    # Just iterate — don't process
    elapsed = time.time() - t0
    print(f"Page {i}: {elapsed:.1f}s")
    if elapsed > 30:
        print(f"  SLOW PAGE DETECTED: page {i} took {elapsed:.1f}s")
    if i >= 20:
        print("  (stopped at page 20)")
        break
```

Run this on ONE of the timeout books (e.g., Didache — likely smallest). Use a 5-minute overall cap. This reveals whether pdfminer hangs on a specific page or just gets progressively slower.

**IMPORTANT:** Run this diagnostic in a separate Python process with a subprocess timeout so it doesn't hang your Claude Code session:
```powershell
# Save diagnostic as temp script, run with timeout
python -c "..." 
# Or use Start-Process with a timeout
```

### Step 1c: Document findings
After the diagnostic, document:
- File sizes and page counts for all 3 books
- Whether PyMuPDF can extract text (confirms text layer exists)
- Where pdfminer hangs (specific page? progressive slowdown? immediate hang?)

---

## Phase 2: Implement Fixes

Based on Phase 1 findings, implement TWO layers of protection:

### Fix 1: Per-page timeout in `extract_with_pdfminer_html()` (PRIMARY)

Add a timeout wrapper around the `extract_pages()` generator loop in `extract_with_pdfminer_html()`. Use `concurrent.futures.ThreadPoolExecutor` since `signal.alarm()` doesn't work on Windows:

```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
import time

# Inside the for page_num, page_layout loop:
# Wrap each page iteration in a thread timeout
# If a single page takes >60s, skip it and log a warning
# If total extraction exceeds 300s (5 min), stop and return what we have so far
```

Key design decisions:
- **Per-page timeout:** 60 seconds per page. Most pages take <1s; anything >60s is hung.
- **Total timeout:** 300 seconds (5 min). Even at 60s/page, 300s = at most 5 slow pages before giving up.
- **On timeout: return partial results.** Whatever pages extracted successfully become the output. This is better than zero content.
- **Log clearly:** `"[WARN] pdfminer timeout on page {N} after 60s — skipping"` and `"[WARN] Extraction timeout ({elapsed}s) — returning {N} of {total} pages"`

**IMPORTANT implementation detail:** pdfminer's `extract_pages()` is a generator. You can't easily timeout a generator mid-iteration. The approach is:
1. Run the generator in a worker thread
2. Use a Queue to pass page layouts back to the main thread
3. If the worker thread doesn't produce a new page within 60s, consider it hung
4. Return whatever pages were collected so far

Alternatively, a simpler approach: use `concurrent.futures.ThreadPoolExecutor.submit()` to run the ENTIRE extraction function and `.result(timeout=300)`. If it times out, you get nothing from pdfminer but can fall through to the fallback.

**Choose whichever approach is more reliable on Windows.** The simpler total-timeout approach is acceptable if it triggers the OCR fallback properly.

### Fix 2: Fallback path in `process_kindle_html()` 

In `process_kindle_html()`, after the pdfminer call (around the line `para_dicts, body_size = extract_with_pdfminer_html(...)`):

If extraction returned zero content (empty para_dicts or timeout), automatically escalate to:
1. **PyMuPDF text extraction** — fast, produces plain text, no font metadata
2. **Tesseract OCR (Tier 2)** — `extract_text_ocr()` already exists

The existing OCR escalation code (around "STEP 1d: Zero-text OCR escalation") already handles the case where Tier 1 produces very little text. The fix may be as simple as ensuring pdfminer timeout → para_dicts is empty → the existing escalation triggers naturally.

Check the existing escalation logic (grep for "STEP 1d" or "OCR escalation" or "zero-text") and verify it handles the timeout case. If not, wire it in.

### Fix 3: Batch QA retry (OPTIONAL — only if Fix 1+2 don't solve it)

In `batch_qa.py` `run_extraction_for_book()`, after the `TimeoutExpired` catch:
```python
except subprocess.TimeoutExpired:
    # Retry without --html-extraction (legacy TXT path)
    log(f"HTML extraction timed out — retrying with TXT extraction")
    cmd_fallback = [c for c in cmd if c != '--html-extraction']
    try:
        result = subprocess.run(cmd_fallback, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=600)
        # ... find output files
    except subprocess.TimeoutExpired:
        return None, None, "", "TIMEOUT: both HTML and TXT extraction exceeded 600s", -1
```

This gives batch runs a second chance with the simpler extraction path.

### CRITICAL constraints:
- **Do NOT change the timeout in batch_qa.py from 600s** — that's a reasonable cap for a single book
- **Do NOT add external dependencies** — use stdlib threading/concurrent.futures only
- **Oil Kings and regression books must not regress** — the timeout should never trigger on normal books
- **The timeout must work on Windows** — no signal.alarm(), no Unix-specific APIs

---

## Phase 3: Verify

### Step 3a: Test on one timeout book
Run the Didache through `Convert-ToKindle` (the interactive path):
```powershell
Import-Module .\module\EbookAutomation.psd1 -Force
Convert-ToKindle -InputFile "C:\Users\Joe\Downloads\[Early Christianity and Its Literature (Book 14)] Jonathan A. Draper*Didache*.pdf"
```

It should either:
- Complete successfully (pdfminer with per-page timeout skipping problematic pages), OR
- Fall back to OCR and produce content

Report:
```
Didache:
  Extraction method: [pdfminer partial / PyMuPDF fallback / OCR fallback]
  Words extracted: [count]
  Duration: [seconds]
  Chapters detected: [count]
```

### Step 3b: Test regression
```powershell
python tools/test_pipeline.py --quick
```
Target: 39/41+

### Step 3c: Verify timeout doesn't trigger on normal books
Run Oil Kings (regression book) and verify it completes normally with NO timeout warnings in the log:
```powershell
Convert-ToKindle -InputFile "inbox\*Oil*Kings*" -NoCache
```

### Success criteria:
- Didache produces >0 words (was 0)
- Oil Kings completes with no timeout warnings and no regression
- 39/41+ tests pass

If Didache still produces zero, investigate whether the PyMuPDF text extraction works for it and wire that as the fallback instead of OCR.

---

## Phase 4: Commit & Push

```powershell
cd F:\Projects\EbookAutomation
git add -A
git commit -m "EB-65: Extraction timeout fallback - pdfminer timeout + OCR escalation

- Added [per-page/total] timeout to extract_with_pdfminer_html() via [approach]
- Timeout triggers OCR fallback for books where pdfminer hangs
- [Optional: batch_qa.py retry with TXT on HTML timeout]
- Didache: 0 words → [count] words via [fallback method]
- Oil Kings: no regression, no timeout warnings
- Tests: [X]/41 pass"
git push origin master
```

---

## Phase 5: Jira

Add a comment to EB-65 via MCP:
```
EB-65 complete ([commit hash]).
Root cause: pdfminer extract_pages() hangs on complex academic PDFs (Didache, Origen).
Fix: [describe timeout mechanism and fallback]
Results: Didache [0 → X words], Oil Kings [no regression]
Tests: [X]/41 pass.
```

Transition EB-65 to Done (transition ID 31).
