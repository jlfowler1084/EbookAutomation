# EB-67: Ezekiel II Heading Explosion — 514 Chapters from Font-Size Gate

## Session Name
Ezekiel Heading Explosion Fix

## Claude Code Model
Opus — subtle interaction between font-size clustering, bookmark matching, and heading promotion in commentary-format PDFs. Requires careful diagnosis of which code path is producing 509 false h1 tags.

## Problem

Ezekiel II (Hermeneia commentary series, Walther Zimmerli, Fortress Press 1988) produces **514 chapters (509 h1 tags)** on fresh extraction after EB-66 cache invalidation. This was masked by stale cached HTML that showed only 3 chapters. A 514-entry Kindle TOC is completely unusable.

The EB-62 fix relaxed the `bm_page_best_para` font-size gate from `sz > body_size` to `sz >= body_size - 0.5`. This was necessary to catch borderline headings in most books (raised batch pass rate 7%→73%), but it's too aggressive for commentary-format books like Ezekiel II which have hundreds of bold sub-section headings (verse references like "25:1-7", "The Oracle Against Ammon") at near-body font size.

**Test file:** `C:\Users\Joe\Downloads\(Hermeneia) Walther Zimmerli - Ezekiel II_ A Commentary on the Book of the Prophet Ezekiel Chapters 25-48-Fortress Press (1988).pdf`

**Expected:** ~3-10 chapter-level headings (the actual structural divisions of the commentary)
**Actual:** 514 headings, 509 of which are h1

## Phase 1: Diagnosis (MANDATORY — do NOT skip)

Run all diagnostics and report findings BEFORE making any code changes.

### Diagnostic 1: Bookmark inventory
```python
import sys
sys.path.insert(0, 'tools')
from pdf_to_balabolka import extract_bookmarks

def log(msg): print(msg)
bookmarks = extract_bookmarks(
    r"C:\Users\Joe\Downloads\(Hermeneia) Walther Zimmerli - Ezekiel II_ A Commentary on the Book of the Prophet Ezekiel Chapters 25-48-Fortress Press (1988).pdf",
    log)
print(f"\nTotal bookmarks: {len(bookmarks)}")
for i, bm in enumerate(bookmarks[:20]):
    print(f"  {i}: L{bm['level']} page={bm['page']} fm={bm.get('front_matter',False)} "
          f"bm={bm.get('back_matter',False)} '{bm['title'][:60]}'")
if len(bookmarks) > 20:
    print(f"  ... and {len(bookmarks)-20} more")
```

**Report:** How many bookmarks? What level? Are there only 3 structural bookmarks, or hundreds?

### Diagnostic 2: Font-size distribution
Extract the HTML and analyze what font sizes the h1/h2/h3 tags correspond to:
```bash
cd F:\Projects\EbookAutomation
python tools/pdf_to_balabolka.py --input "C:\Users\Joe\Downloads\(Hermeneia) Walther Zimmerli - Ezekiel II_ A Commentary on the Book of the Prophet Ezekiel Chapters 25-48-Fortress Press (1988).pdf" --mode kindle --html-extraction --output temp_ezekiel_diag.html 2>&1 | findstr /i "body cluster h1_size heading font"
```

**Report:** What is `body_size`? What is `h1_size`? What is the gap between them? Is the `bm_page_best_para` gate (`sz >= body_size - 0.5`) letting through subheadings?

### Diagnostic 3: Heading tag source analysis
Parse the output HTML to see what the 509 h1 tags actually contain:
```python
import re
with open('temp_ezekiel_diag.html', 'r', encoding='utf-8') as f:
    html = f.read()

h1s = re.findall(r'<h1[^>]*>(.*?)</h1>', html)
h2s = re.findall(r'<h2[^>]*>(.*?)</h2>', html)
h3s = re.findall(r'<h3[^>]*>(.*?)</h3>', html)
print(f"h1: {len(h1s)}, h2: {len(h2s)}, h3: {len(h3s)}")

# Show sample of h1 content to understand what's being promoted
print("\nFirst 20 h1 tags:")
for i, h in enumerate(h1s[:20]):
    clean = re.sub(r'<[^>]+>', '', h)
    print(f"  {i}: {clean[:80]}")

print(f"\nLast 10 h1 tags:")
for i, h in enumerate(h1s[-10:]):
    clean = re.sub(r'<[^>]+>', '', h)
    print(f"  {len(h1s)-10+i}: {clean[:80]}")

# Categorize h1 content patterns
verse_refs = sum(1 for h in h1s if re.search(r'\d+:\d+', re.sub(r'<[^>]+>', '', h)))
chapter_like = sum(1 for h in h1s if re.search(r'chapter|part|introduction|conclusion', re.sub(r'<[^>]+>', '', h), re.I))
short = sum(1 for h in h1s if len(re.sub(r'<[^>]+>', '', h)) < 30)
print(f"\nH1 content patterns:")
print(f"  Verse references (N:N): {verse_refs}")
print(f"  Chapter-like keywords: {chapter_like}")
print(f"  Short (<30 chars): {short}")
```

**Report:** Are the false h1s verse references? Bold section titles? What pattern are they?

### Diagnostic 4: Code path identification
Search the extraction log for which code path is assigning the h1 tags. The key question: are the 509 h1s coming from:
- (a) **Bookmark matching** via `bm_page_best_para` (the EB-62 relaxed gate)
- (b) **Font-cluster detection** (`h1_size is not None and abs(size - h1_size) <= 0.5`)
- (c) **Pattern-based promotion** (chapter keyword regex)

To determine this, add temporary debug logging in `format_paragraphs_as_html()`. Before the `tag = 'h1'` lines, add a counter for each path. Or check the log output for bookmark vs font-cluster messages.

```bash
python tools/pdf_to_balabolka.py --input "C:\Users\Joe\Downloads\(Hermeneia) Walther Zimmerli - Ezekiel II_ A Commentary on the Book of the Prophet Ezekiel Chapters 25-48-Fortress Press (1988).pdf" --mode kindle --html-extraction --output temp_ezekiel_diag.html 2>&1 | findstr /i "Placed bookmark bm_page whitelist FIX"
```

**Report:** Which heading assignment path is responsible for the 509 h1 tags?

## Phase 2: Fix

Based on diagnostic findings, implement a safeguard. Here are the likely fix strategies ranked by preference:

### Strategy A: Heading density cap (PREFERRED)
After the font-size clustering and heading assignment loop, count how many paragraphs were tagged as h1. If the count exceeds a reasonable threshold relative to the book's page count (e.g., more than 1 heading per 3 pages would mean >100 for a 300-page book), the font-size gap is too small for this book. Re-run the assignment with a tighter gate.

Implementation sketch:
```python
# After heading assignment, check for heading explosion
h1_count = sum(1 for p in html_parts if '<h1' in p)
pages = max(1, total_pages)
if h1_count > max(50, pages // 3):
    log(f"  [WARN] Heading explosion detected: {h1_count} h1 tags for {pages} pages")
    log(f"  Re-running with stricter font-size gate (sz > body_size + 0.5)")
    # Re-run the heading assignment with tighter threshold
    ...
```

### Strategy B: Bookmark-only mode for books with bookmarks
If a book has PDF bookmarks, trust ONLY bookmark-matched headings for h1/h2. Don't let font-cluster detection produce additional h1 tags beyond what the bookmarks identify. Non-bookmark headings stay at h3.

This is simpler but might under-detect headings in books where some chapters have bookmarks and others don't.

### Strategy C: Two-pass font clustering
First pass with the relaxed gate. Count candidates. If the count is suspiciously high (>80), do a second pass with only explicitly bookmark-matched paragraphs as h1/h2. Everything else becomes h3.

### Fix principles
- The EB-62 relaxation (`sz >= body_size - 0.5`) MUST be preserved for the general case — it raised batch pass rate from 7% to 73%
- The fix must only activate when heading count is clearly excessive
- Bookmark-matched headings should NEVER be demoted by this fix
- Log clearly when the safeguard activates

## Verification

### Test 1: Ezekiel chapter count
```python
import re
with open('temp_ezekiel_verify.html', 'r', encoding='utf-8') as f:
    html = f.read()
h1s = re.findall(r'<h1[^>]*>(.*?)</h1>', html)
h2s = re.findall(r'<h2[^>]*>(.*?)</h2>', html)
print(f"h1: {len(h1s)}, h2: {len(h2s)}")
# Should be ~3-10 h1/h2 total, NOT 500+
```

### Test 2: Full regression suite
```bash
python tools/test_pipeline.py
```
**Expected:** 39/41 pass (same 2 pre-existing Mexico failures). If the baseline has shifted to 36/41 from the EB-61 session, investigate the 3 new failures separately — this fix should not add more.

### Test 3: Oil Kings (heading detection canary)
```bash
python tools/test_pipeline.py "Oil Kings"
```
**Expected:** 17/17 pass, chapter count unchanged (22 chapters).

### Test 4: Verify EB-62 gains preserved
The fix must NOT regress heading detection on other batch books. Spot-check a few:
```bash
python tools/pdf_to_balabolka.py --input "C:\Users\Joe\Downloads\Al Sweigart - Automate the Boring Stuff*" --mode kindle --html-extraction --output temp_automate_check.html 2>&1 | findstr /i "Placed heading chapter"
```
Should still detect 95 chapters (or close to it).

## Cleanup
```bash
del temp_ezekiel_diag.html temp_ezekiel_verify.html temp_automate_check.html 2>nul
```

## Commit
```bash
git add tools/pdf_to_balabolka.py
git commit -m "EB-67: Fix heading explosion on commentary-format books (Ezekiel II)

- [ROOT CAUSE from diagnostic — fill in]
- [SAFEGUARD DESCRIPTION — fill in]
- Ezekiel II: 514 chapters → ~3-10 (correct structural divisions)
- EB-62 relaxed gate preserved for general case
- Regression suite: no change"
git push origin master
```

## What NOT to Change
- Do NOT revert the EB-62 `sz >= body_size - 0.5` relaxation globally — it's critical for 73% batch pass rate
- Do NOT change bookmark extraction logic
- Do NOT modify the font-cluster detection algorithm itself — just add a post-hoc safeguard
- Do NOT hardcode book-specific overrides — the fix must be generic enough to catch similar commentary formats
