# EB-17 FIX: Debug and Fix PDF Image Extraction — Images Not Appearing

## Session Name
kindle-image-debug

## Claude Code Model
**Opus** — Debugging a multi-file integration issue across Python and PowerShell. Requires tracing actual execution paths, not guessing.

## Ticket
EB-17 — Image Preservation in PDF-to-Kindle (reopened — feature not working)

## Problem
EB-17 was marked complete (commit `60a5bfa`) but **images are NOT appearing in Kindle output**. Specifically:
- No `images/` subdirectory is created alongside the HTML output
- No `<figure>` or `<img>` tags appear in the intermediate HTML
- The intermediate HTML file itself is not easily locatable after conversion
- The quality report JSON has no mention of image extraction at all

This means either:
1. `extract_pdf_images()` is never being called
2. It's being called but the output directory is wrong (temp dir that gets cleaned up?)
3. It's being called but returning empty (filtering too aggressively?)
4. The images list is extracted but never passed to `format_paragraphs_as_html()`
5. The `format_paragraphs_as_html()` changes weren't actually applied

## CRITICAL INSTRUCTION: Debug-First Approach

**DO NOT** make speculative fixes. **DO NOT** claim the issue is fixed without proof.

Follow this exact sequence:

### Phase 1: Trace the actual code path (READ ONLY — no edits yet)

1. **Find `extract_pdf_images()`** — Use `grep -n "def extract_pdf_images"` in `tools/pdf_to_balabolka.py`. Read the full function. Does it exist? What are its parameters? What does it return?

2. **Find where it's called** — Use `grep -n "extract_pdf_images"` across all files. Is it called from `process_kindle_html()`? Is it called from anywhere?

3. **Check `process_kindle_html()` for image handling** — Read the function from its `def` line through the `format_paragraphs_as_html()` call and the HTML write. Look for ANY image-related code. If there is none, that's the bug.

4. **Check `format_paragraphs_as_html()` signature** — Does it accept an `images` parameter? Read the first 5 lines of the function definition.

5. **Check the main loop in `format_paragraphs_as_html()`** — Search for `figure`, `img`, `_page_images`, or any image insertion logic in the page_marker handling block.

6. **Check where the HTML output goes** — In `process_kindle_html()`, what directory does the HTML get written to? Is it a temp dir that gets deleted? Trace the `output_path` variable from the function parameter back to where the PSM1 calls it.

7. **Check the PSM1 temp dir lifecycle** — In `EbookAutomation.psm1`, find where the Kindle temp directory is created (`ebook_kindle_*`) and where it's cleaned up. Does the cleanup delete the images directory?

### Phase 2: Document findings

Before making ANY code changes, write a comment to yourself documenting:
- Whether `extract_pdf_images()` exists and where
- Whether it's called from `process_kindle_html()` 
- Whether `format_paragraphs_as_html()` accepts images
- Whether images are inserted in the HTML generation loop
- What the output directory path is and whether it survives cleanup
- The SPECIFIC root cause(s)

### Phase 3: Fix the root cause(s)

Based on your Phase 1 findings, implement the actual fix. Common scenarios:

**If `extract_pdf_images()` exists but is never called from `process_kindle_html()`:**
- Wire it in. Call it after text extraction, before `format_paragraphs_as_html()`.
- Pass the results to `format_paragraphs_as_html()` via an `images` parameter.

**If `format_paragraphs_as_html()` doesn't accept or use images:**
- Add the `images=None` parameter
- Build `_page_images` dict mapping page numbers to image lists
- In the main loop's page_marker handling, emit `<figure><img>` tags at page transitions
- Add final flush after loop for last page's images
- Add CSS rules for `figure`, `figure img`, `figcaption`

**If the output directory is a temp dir that gets cleaned up:**
- The `images/` subdirectory must be created relative to where the final HTML lands, NOT in the temp dir
- OR the cleanup must preserve the images directory
- Trace the PSM1 code to see where temp files get copied to output and ensure images/ gets copied too

**If `extract_pdf_images()` is filtering too aggressively:**
- Add debug logging: `log(f"  Page {page+1}: found {len(image_list)} raw images, {meaningful_count} after filtering")`
- Temporarily lower thresholds to see if images appear
- Check that the full-page scan detection isn't triggering on textbook pages that happen to have a large illustration

### Phase 4: Verify WITH PROOF

After implementing fixes:

1. **Run a test conversion and check the actual output:**
```powershell
Import-Module .\module\EbookAutomation.psd1 -Force
Convert-ToKindle -InputFile "C:\Users\Joe\Downloads\Astronomy-LR.pdf"
```

2. **Verify images directory exists:**
```powershell
# Find the output HTML
Get-ChildItem -Path "F:\Projects\EbookAutomation\output" -Recurse -Filter "Astronomy*" | Format-Table FullName, Length
# Check for images subdirectory
Get-ChildItem -Path "F:\Projects\EbookAutomation\output" -Recurse -Directory -Filter "images" | Format-Table FullName
```

3. **Verify HTML contains image tags:**
```powershell
# Count image tags in HTML
$html = Get-Content (Get-ChildItem -Path "F:\Projects\EbookAutomation\output" -Recurse -Filter "Astronomy*.html" | Select-Object -First 1).FullName -Raw
($html | Select-String -Pattern '<figure>' -AllMatches).Matches.Count
($html | Select-String -Pattern '<img ' -AllMatches).Matches.Count
```

4. **Report concrete numbers:**
   - How many images were extracted?
   - How many `<figure>` tags are in the HTML?
   - What is the `images/` directory path and how many files are in it?
   - What does the conversion log say about image extraction?

**DO NOT mark this task as complete unless you can report specific numbers proving images exist in the output.** "0 images" or inability to find the output means the fix didn't work — keep debugging.

### Phase 5: Run test suite
```
python tools/test_pipeline.py --quick
```
All 41 tests must still pass.

### Phase 6: Commit and push
```
git add -A
git commit -m "fix: EB-17 — debug and fix image extraction not wired into Kindle pipeline"
git push
```

### Phase 7: Jira
- Add completion comment to EB-17 with the SPECIFIC root cause found and the concrete image counts from verification
- Do NOT transition status (already Done — this is a fix commit on the same ticket)

## Test file
```
C:\Users\Joe\Downloads\Astronomy-LR.pdf
```
This book has 331 meaningful embedded images per the scan-image-density.py analysis. If the fix is working, we should see a significant number (not necessarily all 331 due to filtering, but definitely dozens).

## Reminder
- Use `grep -n` for all line lookups — never trust hardcoded line numbers
- Image extraction failure must never block text extraction
- PyMuPDF page indexing is 0-based; para_dict page_number is 1-based
- The `images/` directory must survive the PSM1 temp dir cleanup and be accessible alongside the final HTML that Calibre receives
