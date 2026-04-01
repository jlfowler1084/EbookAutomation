# EB-61: Astronomy-LR TOC Starts at Chapter 4 — Diagnostic & Fix

## Session Name
Astronomy TOC Chapter Skip Fix

## Claude Code Model
Opus — subtle heading detection bug across multiple interacting systems (bookmark extraction, front matter classification, TOC region skipping, running header dedup, heading dedup). Requires careful diagnosis before any code changes.

## Problem

Astronomy-LR.pdf (1,197 pages, 30 chapters + 14 appendices) generates a Kindle TOC that starts at Chapter 4. Chapters 1-3 exist in the book content but are not tagged as `<h1>` in the output HTML, so Calibre's TOC builder skips them.

**Test file:** `C:\Users\Joe\Downloads\Astronomy-LR.pdf`

## Phase 1: Diagnosis (MANDATORY — do NOT skip)

Run all 5 diagnostic steps and report findings BEFORE making any code changes.

### Diagnostic 1: Bookmark extraction
Check if chapters 1-3 have bookmarks at all:
```python
import sys
sys.path.insert(0, 'tools')
from pdf_to_balabolka import extract_bookmarks

def log(msg): print(msg)
bookmarks = extract_bookmarks(r"C:\Users\Joe\Downloads\Astronomy-LR.pdf", log)
print(f"\nTotal bookmarks: {len(bookmarks)}")
print("\nFirst 15 bookmarks:")
for i, bm in enumerate(bookmarks[:15]):
    print(f"  {i}: L{bm['level']} page={bm['page']} fm={bm.get('front_matter',False)} "
          f"bm={bm.get('back_matter',False)} title='{bm['title'][:80]}'")
```

**Report:** Are bookmarks for chapters 1, 2, 3 present? What level are they? What pages?

### Diagnostic 2: HTML output heading check
Extract just the first ~50 headings from the output HTML:
```bash
cd F:\Projects\EbookAutomation
python tools/pdf_to_balabolka.py --input "C:\Users\Joe\Downloads\Astronomy-LR.pdf" --mode kindle --html-extraction --output temp_astronomy_test.html 2>nul
```

Then inspect headings:
```python
import re
with open('temp_astronomy_test.html', 'r', encoding='utf-8') as f:
    html = f.read()

headings = re.findall(r'<(h[123])\b[^>]*>(.*?)</\1>', html)
print(f"Total headings: {len(headings)}")
print("\nFirst 50 headings:")
for i, (tag, text) in enumerate(headings[:50]):
    print(f"  {i}: <{tag}> {text[:80]}")
```

**Report:** Do h1 tags exist for chapters 1, 2, 3? Are they tagged as h2 (front matter) or h3 (demoted) instead? Are they missing entirely?

### Diagnostic 3: TOC region detection
Check if the TOC section detection is swallowing early chapter pages. Search the extraction log output for TOC-related messages:
```bash
python tools/pdf_to_balabolka.py --input "C:\Users\Joe\Downloads\Astronomy-LR.pdf" --mode kindle --html-extraction --output temp_astronomy_test.html 2>&1 | findstr /i "toc skip contents"
```

**Report:** What pages are detected as TOC? Do any chapter 1-3 pages fall within the TOC region?

### Diagnostic 4: Running header / heading dedup
Check if chapters 1-3 text is being stripped by running header detection (FIX 3) or heading dedup. Search for dedup/strip messages:
```bash
python tools/pdf_to_balabolka.py --input "C:\Users\Joe\Downloads\Astronomy-LR.pdf" --mode kindle --html-extraction --output temp_astronomy_test.html 2>&1 | findstr /i "running header dedup skip strip"
```

**Report:** Is any chapter 1-3 heading text being stripped as a running header or deduplicated?

### Diagnostic 5: Front matter classification
Check if chapters 1-3 bookmarks are being classified as front matter (which would make them h2 instead of h1):
```python
import sys
sys.path.insert(0, 'tools')
from pdf_to_balabolka import extract_bookmarks

def log(msg): print(msg)
bookmarks = extract_bookmarks(r"C:\Users\Joe\Downloads\Astronomy-LR.pdf", log)

# Check front matter flags on first 15 bookmarks
for i, bm in enumerate(bookmarks[:15]):
    if bm.get('front_matter'):
        print(f"  FRONT MATTER: L{bm['level']} page={bm['page']} '{bm['title'][:60]}'")
```

Also check: are the early bookmarks at level 2 while later ones are level 1? That could cause the `bm_front_matter` set to include them.

**Report:** Which bookmarks have `front_matter=True`? Does the front matter detection end before Chapter 1?

### Diagnostic 6: bm_page_best_para matching
If diagnostics 1-5 don't reveal the cause, the issue may be in `bm_page_best_para` — the pre-pass that identifies which paragraph on a bookmark's page is the "best" heading candidate. Check if chapters 1-3 pages have a best_para match:
```python
# After running extraction, check the log for lines about bookmark-paragraph matching
# Look for: "bm_page_best_para" or "Placed X bookmarks"
```

## Phase 2: Fix

Based on diagnostic findings, implement the fix. The most likely causes in order of probability:

1. **Front matter over-classification** — The `extract_bookmarks()` function marks early bookmarks as `front_matter=True` based on heuristics (before the first "Chapter" or "Part" bookmark). If chapters 1-3 use titles like "Science and the Universe: A Brief Tour" instead of "Chapter 1: ...", they could be misclassified as front matter → tagged h2 → invisible to Calibre TOC.

2. **TOC region swallowing chapter pages** — If the printed TOC in the PDF spans many pages and the last TOC page overlaps with Chapter 1's start page, the `in_toc_region` flag would suppress those paragraphs.

3. **Running header dedup** — If "Chapter 1" text appears as a running header on multiple pages, FIX 3 would strip all but the first occurrence. If the first occurrence is in the TOC region (suppressed), the actual chapter heading would also be suppressed.

4. **Heading dedup** — The `heading_seen_pages` tracker skips headings whose lowercase text matches a previously-seen heading. If the TOC lists "1 Science and the Universe" and the actual chapter heading is also "1 Science and the Universe", the second occurrence would be deduplicated.

5. **`bm_page_best_para` gate** — The pre-pass requires `sz > body_size` (relaxed to `sz >= body_size - 0.5` in EB-62). If chapters 1-3 have a different font size than later chapters (e.g., textbook uses a larger decorative font for Part I but standard heading font for chapters within it), they might not pass the gate.

### Fix principles
- Fix must not regress the 5-book test suite (Oil Kings, Genesis, Dionysius, Brother of Jesus, Mexico)
- Fix must not regress the EB-62 heading detection improvements (73% batch pass rate)
- If the root cause affects only this specific book's structure, prefer a targeted fix over a broad behavioral change
- Log a clear message when the fix activates so batch runs can track it

## Verification

### Test 1: Astronomy heading count
```bash
python tools/pdf_to_balabolka.py --input "C:\Users\Joe\Downloads\Astronomy-LR.pdf" --mode kindle --html-extraction --output temp_astronomy_verify.html 2>nul
```
```python
import re
with open('temp_astronomy_verify.html', 'r', encoding='utf-8') as f:
    html = f.read()
h1s = re.findall(r'<h1[^>]*>(.*?)</h1>', html)
print(f"Total h1 headings: {len(h1s)}")
print("\nFirst 10 h1s:")
for i, h in enumerate(h1s[:10]):
    print(f"  {i}: {h[:80]}")
```
**Expected:** h1 headings include chapters 1, 2, and 3 (whatever their actual titles are).

### Test 2: Regression suite
```bash
python tools/test_pipeline.py
```
**Expected:** 39/41 pass (same 2 pre-existing Mexico failures). No regression.

### Test 3: Verify no heading count regression on batch test books
```bash
python tools/test_pipeline.py "Oil Kings"
```
**Expected:** 17/17 pass, chapter count unchanged.

## Cleanup
```bash
del temp_astronomy_test.html temp_astronomy_verify.html 2>nul
```

## Commit
```bash
git add tools/pdf_to_balabolka.py
git commit -m "EB-61: Fix TOC skipping early chapters in large textbooks (Astronomy-LR)

- [ROOT CAUSE from diagnostic — fill in after Phase 1]
- [FIX DESCRIPTION — fill in after Phase 2]
- Astronomy-LR: chapters 1-3 now appear in TOC
- Regression suite: 39/41 (no change)"
git push origin master
```

## What NOT to Change
- Do NOT modify bookmark extraction for other books — this fix targets the specific pattern causing chapters 1-3 to be missed
- Do NOT change the TOC region detection boundaries without testing against books with very long printed TOCs
- Do NOT disable running header dedup globally — it's critical for clean output on most books
- Do NOT change heading font-size clustering thresholds without batch testing
