# EB-63: Footnote Linking Overhaul — 10K Unlinked Across 13 Books

## Session Name
Footnote Linking Overhaul

## Claude Code Model
**Opus** — multi-strategy pattern matching across diverse publisher formats, diagnostic-first debugging

## Context

Batch QA (60 books, batch_20260330_122744) found **10,090 unlinked footnotes** across 13 books. The 3-strategy footnote linking system in `_link_endnotes()` (pdf_to_balabolka.py) achieves 0-2% link rate on most academic books despite working at 87% on one control book (Wilkinson).

### Current strategies (in `_link_endnotes()`):
1. **Collected endnotes** — finds a `<h[12]>` heading containing "Notes|Endnotes|NOTES|ENDNOTES", parses `<p>N. text` entries below it
2. **Per-chapter endnotes** — splits at chapter headings, finds `<p>N. ` clusters of 3+ sequential numbers per section
3. **Per-page footnotes** — matches `<p><sup>N</sup>` or `<p><em><sup>N</sup>` paragraph starts, pairs body refs within 5000-char window

### Test books (available in `C:\Users\Joe\Downloads\`):

| # | Book | Unlinked | Linked | Rate | Why it matters |
|---|------|----------|--------|------|----------------|
| 1 | `(Princeton Legacy Library_ 2019) Arthur S. Link - Wilson, Volume*.pdf` | 2,105 | 4 | 0% | Highest count, Princeton UP |
| 2 | `(New International Commentary on the Old Testament) Daniel I. Block*Ezekiel*25-48*.pdf` | 1,837 | 12 | 1% | Eerdmans academic (Ezekiel II regression book) |
| 3 | `[The Biblical Resource Series] John Joseph Collins - The Apocalyptic Imagination*.pdf` | 987 | 0 | 0% | Eerdmans, 131 chapters detected |
| 4 | `(German and European Studies, 35) Javier Samper Vendrell*.pdf` | 719 | 0 | 0% | U of Toronto Press |
| 5 | `[Studies in the History of Christian Thought] Wilkinson*.pdf` | 82 | 544 | 87% | **CONTROL** — must not regress |

---

## Phase 1: Diagnostic (READ ONLY — no edits yet)

### Step 1a: Understand the code
Use `grep -n` to locate these functions in `tools/pdf_to_balabolka.py`:
- `_link_endnotes()` — the main dispatcher
- `_link_endnotes_collected()` — Strategy 1+2
- `_link_per_page_footnotes()` — Strategy 3

Read each function completely. Note the exact regex patterns used for:
- Notes heading detection
- Endnote entry parsing (`<p>N. text`)
- Chapter heading pattern (`_chapter_pat`)
- Per-page footnote paragraph detection
- The 5000-char proximity window in Strategy 3

### Step 1b: Extract and convert each test book
Run each of the 5 test books through extraction to produce intermediate HTML. Use the Python extraction directly to get the HTML without Calibre:

```powershell
# For each test book, run extraction to get HTML
# Use Convert-ToKindle which now defaults to HTML extraction for PDFs
Import-Module .\module\EbookAutomation.psd1 -Force

# Book 1: Wilson
Convert-ToKindle -InputFile "C:\Users\Joe\Downloads\(Princeton Legacy Library_ 2019) Arthur S. Link - Wilson, Volume*.pdf"

# Continue for each book...
```

If conversion takes too long (>5 minutes per book), use the Python extractor directly:
```powershell
python tools/pdf_to_balabolka.py "C:\Users\Joe\Downloads\BOOKFILE.pdf" --output-dir output\debug_footnotes --html-extraction --skip-tts --skip-footnotes
```

The `--skip-footnotes` flag skips the linking step so we get the raw HTML with unlinked `<sup>` tags.

### Step 1c: Dump footnote-area HTML for each failing book

For each of the 4 failing books, write a diagnostic script that:

1. **Counts `<sup>N</sup>` tags** — total raw superscripts in the HTML
2. **Finds any "Notes/Endnotes/Footnotes" headings** — search for `<h[123456]>` tags containing note-related words (case-insensitive). Print the heading text and surrounding 500 chars.
3. **Dumps 20 sample endnote paragraphs** — find `<p>` tags that start with a number (any format: `<p>1. `, `<p>1 `, `<p>[1]`, `<p><sup>1</sup>`, `<p>1)`, etc.). Print the first 200 chars of each.
4. **Dumps 10 sample body `<sup>` contexts** — for 10 random `<sup>N</sup>` tags, print 300 chars of surrounding HTML to see what the body references look like.
5. **Checks for `<p><sup>N</sup>` footnote paragraphs** — count paragraphs starting with `<sup>` (Strategy 3's target).

Create this as a temporary script `tools/debug_footnotes.py` that takes an HTML file path and prints the diagnostic output. Run it on all 5 books (including Wilkinson as the control).

### Step 1d: Compare failing patterns vs working patterns

After running diagnostics on all 5 books, document:
- What does Wilkinson's note markup look like? (it works at 87%)
- What do the failing books' note markup look like?
- Where exactly does each strategy fail for each book?

---

## Phase 2: Document Root Causes

Before writing any fixes, write a summary documenting:

1. **Per-book failure mode** — for each of the 4 failing books, state which strategy was attempted and exactly why it failed (specific regex that didn't match, heading text that wasn't recognized, note format that wasn't parsed, etc.)

2. **Pattern categories** — group the failures into categories:
   - "Notes heading not recognized" (what heading text did they use?)
   - "Note entry format not matched" (what format: `N. text`, `N text`, `[N]`, etc.?)
   - "Chapter pattern too restrictive" (what chapter headings exist?)
   - "Proximity window too small" (for Strategy 3)
   - Other findings

3. **Fix plan** — for each category, what regex/logic change would fix it

Print this summary to the console. Do NOT proceed to Phase 3 until findings are documented.

---

## Phase 3: Fix

Based on Phase 2 findings, implement fixes. Likely areas (but let the diagnostic drive the actual changes):

### Strategy 1 expansion:
- Expand the Notes heading regex to match: "Footnotes", "Notes to Chapter", "BIBLIOGRAPHY AND NOTES", "Notes and References", "End Notes", case-insensitive
- Expand endnote entry parsing to match more formats: `<p>N text` (no period), `<p>[N] text`, `<p>N) text`, `<p><sup>N</sup> text`

### Strategy 2 expansion:
- If the `_chapter_pat` is too restrictive, relax it or add fallback to split on ALL `<h1>`/`<h2>` tags
- Reduce the minimum cluster size from 3 to 2 if needed
- Handle note numbering that doesn't restart per chapter

### Strategy 3 expansion:
- Increase the 5000-char proximity window if diagnostics show footnotes are further from their references
- Handle additional footnote paragraph formats

### New Strategy 4 (if needed):
- If some books have notes that don't match any structural pattern, consider a "brute force" approach: find all `<sup>N</sup>` tags, find all `<p>` tags starting with matching numbers, and pair them by number (global, not positional)

### CRITICAL constraints:
- **Do NOT break Wilkinson** — run the control book after every change
- **Do NOT modify any code outside of the footnote linking functions** unless absolutely necessary
- **Keep the strategy cascade** — try the most precise strategy first, fall through to broader ones

---

## Phase 4: Verify with Proof

After implementing fixes, re-run all 5 test books through the full pipeline (WITH footnote linking this time — no `--skip-footnotes`).

For each book, count and report:
```
Book: [title]
Total <sup>N</sup> before linking: [count]
Total <sup>N</sup> after linking (unlinked): [count]  
Linked: [count] ([percentage]%)
Strategy used: [1/2/3/4]
```

### Success criteria:
- Wilson: >40% linked (was 0%)
- NICOT Daniel: >40% linked (was 1%)
- Collins: >40% linked (was 0%)
- Vendrell: >40% linked (was 0%)
- Wilkinson: ≥85% linked (was 87% — NO regression)

If ANY book is still below 40%, go back to Phase 1c and diagnose that specific book's remaining failures. Do NOT report "done" until the targets are met.

---

## Phase 5: Test Suite

Run the full test suite:
```powershell
python tools/test_pipeline.py --quick
```

Target: 39/41+ (same baseline — the 2 Mexico double-space failures are pre-existing).

---

## Phase 6: Cleanup

- Delete `tools/debug_footnotes.py` (temporary diagnostic script)
- Remove any temporary debug logging added in Phase 1

---

## Phase 7: Commit & Push

```powershell
cd F:\Projects\EbookAutomation
git add -A
git commit -m "EB-63: Footnote linking overhaul - expanded strategies for academic publishers

- [describe specific fixes based on findings]
- [list strategy expansions]
- Batch footnote linking: [before] -> [after] on 5-book test set
- Wilkinson control: [X]% (no regression from 87%)
- Tests: [X]/41 pass"
git push origin master
```

---

## Phase 8: Jira

Add a comment to EB-63 via MCP:
```
EB-63 complete ([commit hash]).
Root causes: [list per-book failure modes found in Phase 2]
Fixes: [list strategy expansions]
Results: [per-book before/after linking rates]
Tests: [X]/41 pass.
```

Transition EB-63 to Done (transition ID 31).
