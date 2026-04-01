# EB-62: Diagnose and Fix Heading Detection Failures — Batch QA Finding

## Session Name
heading-detection-fix

## Claude Code Model
**Opus** — Complex diagnostic work across bookmark extraction, font analysis, and text matching. Requires tracing multiple code paths and understanding why matching fails for specific books.

## Ticket
EB-62 — Heading detection fails on 80% of books despite PDF bookmarks

## Problem
Batch QA run `batch_20260329_165649` shows 12 of 15 books (80%) produce zero chapter headings (h1=0, h2=0) in HTML output, despite many having 250-572 PDF bookmarks. Only 2 books succeed:
- Oil Kings: 21 bookmarks → 7 h1 + 15 h2 (PASS)
- Mastering Windows 365: 407 bookmarks → 2 h1 + 64 h2 (PASS)

Books that fail:
- Automate Boring Stuff: 572 bookmarks, 505 pages → 0 headings
- Python Crash Course: 552 bookmarks, 548 pages → 0 headings
- Astronomy-LR: 250 bookmarks, 1197 pages → 0 headings
- By Way of Deception: 378 bookmarks, 378 pages → 0 headings
- Mastering Intune: 521 bookmarks, 823 pages → 0 headings
- Narcoland: 21 bookmarks, 457 pages → 0 headings
- And 6 more

This is the **highest-impact issue** in the pipeline — fixing it would raise the batch pass rate from 7% to ~80%.

## CRITICAL: Diagnostic-first approach

This is a DIAGNOSIS task, not a "just add code" task. You must understand WHY matching fails for each book before writing any fix. The heading detection code in `format_paragraphs_as_html()` already has extensive bookmark matching — the question is why it's not working for these specific books.

## Phase 1: Diagnostic — Trace why bookmarks don't match (READ ONLY)

### Step 1: Add diagnostic logging to `format_paragraphs_as_html()`

TEMPORARILY add debug logging (you'll remove it later) to trace the matching pipeline. Add these AFTER the bookmarks are loaded and bm_map is built (after line ~5067, before `def _match_bookmark`):

```python
# DIAGNOSTIC: log bookmark map
log(f"  DIAG: bm_map has {len(bm_map)} entries")
for bm_norm, level in list(bm_map.items())[:10]:
    log(f"  DIAG:   bm_map['{bm_norm}'] = level {level}")
log(f"  DIAG: bm_page_level has {len(bm_page_level)} page entries")
```

And inside `_match_bookmark()`, add at the TOP:
```python
if len(text.strip()) < 120:
    log(f"  DIAG_MATCH: testing '{text.strip()[:60]}' (len={len(text.strip())})")
```

And at the BOTTOM (before `return None`):
```python
# Only log for short text that could be headings
if len(text.strip()) < 120:
    log(f"  DIAG_MATCH: NO MATCH for '{text.strip()[:60]}'")
```

### Step 2: Run diagnostic on 3 books

Run the extraction on these 3 specific books (1 pass, 2 fail) with logging visible:

```python
# In tools/pdf_to_balabolka.py, find process_kindle_html and add diagnostic output
# Test with:
python tools/pdf_to_balabolka.py --input "F:\Projects\EbookAutomation\test_images\Cooper, Andrew Scott - The Oil Kings_ How the U (2011, Simon & Schuster) - libgen.li.pdf" --mode kindle --output-dir F:\Projects\EbookAutomation\processing\diag_oilkings 2>&1 | Select-String "DIAG" | Select-Object -First 30

python tools/pdf_to_balabolka.py --input "F:\Projects\EbookAutomation\test_images\Astronomy-LR.pdf" --mode kindle --output-dir F:\Projects\EbookAutomation\processing\diag_astronomy 2>&1 | Select-String "DIAG" | Select-Object -First 30

python tools/pdf_to_balabolka.py --input "F:\Projects\EbookAutomation\test_images\Eric Matthes - Python Crash Course_ A Hands-On, Project-Based Introduction to Programming-No Starch Press (2019).pdf" --mode kindle --output-dir F:\Projects\EbookAutomation\processing\diag_python 2>&1 | Select-String "DIAG" | Select-Object -First 30
```

### Step 3: Analyze the diagnostic output

For each failing book, determine:
1. **Does `bm_map` have entries?** If it's empty, bookmarks aren't being passed to the function.
2. **Does `bm_page_level` have entries?** If empty, bookmarks lack page numbers.
3. **Are bookmark titles matching paragraph text?** Compare the first 10 `bm_map` entries against the first few `DIAG_MATCH` "testing" lines.
4. **Is `_match_bookmark()` being called?** If no DIAG_MATCH lines appear, the function isn't being called (font size gate at line ~5496).
5. **What's the body_size?** If body_size is wrong, the `size >= body_size - 0.5` gate (line 5496) could be filtering everything out.

### Step 4: Check if bookmarks are reaching `format_paragraphs_as_html()`

Trace the call chain:
```
process_kindle_html() → format_paragraphs_as_html(para_dicts, body_size, bookmarks, ...)
```
Use `grep -n "bookmarks" tools/pdf_to_balabolka.py` near the `format_paragraphs_as_html()` call to verify bookmarks are passed.

Also check: Is `extract_bookmarks()` returning bookmarks with page numbers? Some PDFs have bookmarks without destination pages — those would produce an empty `bm_page_level`.

## Phase 2: Document the specific root cause(s)

Write down:
- For each of the 3 test books: why matching fails
- Whether the issue is in bookmark extraction, text matching, font-size gating, or guard clauses
- What the fix strategy should be

## Phase 3: Implement fix

Based on Phase 1 findings, here are likely fix strategies (implement whichever applies):

### Strategy A: Bookmark-only heading promotion (if bookmarks exist but don't match text)
If a book has bookmarks with page numbers but `_match_bookmark()` never matches, add a fallback:
- After the main heading detection loop, if ZERO headings were detected and bookmarks exist, do a second pass
- In the second pass, for each bookmark with a page number, find the FIRST paragraph on that page and promote it to a heading
- This is aggressive but better than zero headings

### Strategy B: Relax font-size gate (if headings are at body size)
The pre-pass at line 5396-5416 requires `sz > body_size`. If headings are at body size (just bold), they fail this gate. Relax to `sz >= body_size - 0.5` or remove the font-size requirement when bookmarks point to the page.

### Strategy C: Fix bookmark page number extraction (if pages are missing)
If `extract_bookmarks()` returns bookmarks without page numbers, the page-based fallback can't work. Check how page numbers are resolved from PDF destinations.

### Strategy D: Fuzzy text matching improvement (if bookmark text differs from paragraph text)
If bookmark titles are truncated or have different formatting than the visible text, the matching fails. Add more normalization (strip HTML entities, handle line breaks, partial prefix matching).

### Strategy E: Pattern-based fallback (if no bookmarks at all)
Some books have zero bookmarks (Amazing Facts, Shroud of Turin, Esoteric Origins). For these, strengthen the pattern-based heading detection:
- "Chapter X", "Part X" patterns already work (line 5558)
- Add: ALL CAPS lines under 80 chars that are preceded by a page break
- Add: Numbered sections like "1.1", "2.3" for textbook structure

## Phase 4: Remove diagnostic logging

After implementing the fix, REMOVE all `DIAG` logging lines. These are for diagnosis only, not production.

## Phase 5: Verify with batch QA

Re-run the same batch:
```powershell
python tools/batch_qa.py run "F:\Projects\EbookAutomation\test_images" --format pdf
```

Compare results with the original run:
```powershell
python tools/batch_qa.py compare batch_20260329_165649 <new_run_id>
```

### Required proof:
- [ ] At least 8 of 15 books now have chapters detected (was 2/15)
- [ ] Oil Kings still passes (no regression)
- [ ] Astronomy-LR has chapters (was 0, has 250 bookmarks)
- [ ] Python Crash Course has chapters (was 0, has 552 bookmarks)
- [ ] 39/41 tests still pass
- [ ] Batch pass rate > 50% (was 7%)

## Phase 6: Commit and push
```
git add -A
git commit -m "fix: EB-62 — improve heading detection to use bookmarks as fallback, fix 80% failure rate"
git push
```

## Phase 7: Jira
- Transition EB-62 to Done (transition ID 31) via Atlassian MCP
- Add completion comment with: root cause per book category, before/after batch pass rates, specific heading counts for key books

## Test corpus
All 15 books are in `F:\Projects\EbookAutomation\test_images\`. The batch results are in `data\batch_reports\batch_20260329_165649.json`.

## Key files
- `tools/pdf_to_balabolka.py` — `format_paragraphs_as_html()` (line ~4977), `_match_bookmark()` (line ~5068), `extract_bookmarks()` (find with grep)
- `tools/batch_qa.py` — batch runner
- `data/batch_reports/batch_20260329_165649.json` — baseline results

## Reminders
- Use `grep -n` for all line lookups — never trust hardcoded line numbers
- Do NOT modify any function logic until Phase 1 diagnosis is complete
- The fix must not regress Oil Kings (the one passing book)
- Bookmarks come from `extract_bookmarks()` which uses pypdf — check if it returns page numbers
- `body_size` is computed from font-size frequency analysis — log it in diagnostics
- Watch out for the running header detection (line 5466) — it could be stripping headings that repeat across pages
