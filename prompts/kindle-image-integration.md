# EB-17: Wire PDF Image Extraction into Kindle HTML Pipeline

## Session Name
kindle-image-integration

## Claude Code Model
**Opus** — Coordinate-based image positioning, multi-file integration across Python and PowerShell, careful insertion into the paragraph assembly loop without disrupting existing heading/footnote/hyperlink logic.

## Ticket
EB-17 — Image Preservation in PDF-to-Kindle

## Problem
PDF images are never embedded in Kindle output. The function `process_kindle_html()` produces text-only HTML — it never extracts images from the source PDF and never emits `<img>` tags. The EPUB path works correctly (images are extracted via `extract_html_from_epub()` at line ~1934 and rewritten via `_rewrite_image_paths()` at line 1903), but the PDF→Kindle path has zero image handling.

The flow today:
```
PDF → process_kindle_html() → HTML (text only) → fix_engine → filter_content → Calibre → KFX
```

The flow after this ticket:
```
PDF → process_kindle_html() → extract images → HTML (with <img> tags) → fix_engine → filter_content → Calibre → KFX
```

## Objective
Extract meaningful images from source PDFs using PyMuPDF, save them alongside the HTML output, and insert `<img>` tags at the correct positions in the generated HTML so Calibre includes them in KFX output.

## Architecture

### Task 1: Create `extract_pdf_images()` function

Create a new function in `tools/pdf_to_balabolka.py`. Place it near the existing `detect_image_density()` function (line ~972).

```python
def extract_pdf_images(pdf_path, output_dir, log, min_width=100, min_height=100, min_size_kb=3):
    """Extract meaningful images from a PDF using PyMuPDF.

    Filters out:
    - Tiny icons (< min_width or < min_height pixels)
    - Very small files (< min_size_kb KB)
    - Full-page scan images (single image covering >70% of page area)
    - Duplicate images (same xref seen on multiple pages — keep first occurrence)

    Saves images to output_dir/images/ with naming: img_pageN_M.ext

    Returns:
        List of dicts: [{'page': int, 'filename': str, 'path': str,
                         'width': int, 'height': int, 'size_kb': float}]
    """
```

**Implementation notes:**
- Use `import fitz` (PyMuPDF) — already a project dependency
- Iterate all pages with `page.get_images(full=True)`
- For each image, call `doc.extract_image(xref)` to get raw bytes + metadata
- **Full-page scan detection:** If a page has exactly 1 image and that image's pixel area > 70% of the page's point area (converted), skip it — it's a scanned page, not an embedded figure
- **Dedup by xref:** Track seen xrefs; only extract first occurrence (PDFs reuse xrefs for repeated images like logos)
- **Size filtering:** Skip images where `width < min_width` OR `height < min_height` OR `len(image_bytes) / 1024 < min_size_kb`
- Save to `os.path.join(output_dir, 'images', filename)` — create the `images/` subdirectory
- Image filename format: `img_p{page}_{index}.{ext}` where ext comes from PyMuPDF's `img_meta['ext']` (png, jpeg, etc.)
- Log summary: `"  Extracted {count} images from {pages_with_images} pages (skipped {skipped_scans} scan pages, {skipped_tiny} tiny, {skipped_dupes} duplicates)"`
- Wrap the entire function in try/except — image extraction failure must NEVER block text extraction. Return empty list on any error.

### Task 2: Wire into `process_kindle_html()`

In `process_kindle_html()` (line ~9718), after text extraction completes and before the `format_paragraphs_as_html()` call (line ~10021):

1. Determine the output directory from `output_path`:
   ```python
   _output_dir = os.path.dirname(output_path) or '.'
   ```

2. Call `extract_pdf_images()`:
   ```python
   log("\n-- STEP 1b: Extracting embedded images -----------------")
   _extracted_images = extract_pdf_images(pdf_path, _output_dir, log)
   if _extracted_images:
       log(f"  {len(_extracted_images)} images will be embedded in HTML output")
   ```

3. Pass the images list to `format_paragraphs_as_html()` via a new optional parameter:
   ```python
   html = format_paragraphs_as_html(para_dicts, body_size, bookmarks, log, title=title, images=_extracted_images)
   ```

### Task 3: Insert `<img>` tags in `format_paragraphs_as_html()`

Modify `format_paragraphs_as_html()` (line ~4977) to accept and render images:

1. **Add parameter:** `images=None` to the function signature.

2. **Build page→images index** early in the function (before the main loop):
   ```python
   # Build page → images mapping for inline image insertion
   _page_images = {}
   if images:
       for img in images:
           pg = img['page']
           _page_images.setdefault(pg, []).append(img)
   ```

3. **Add CSS rules** to the embedded `<style>` block (around line 5380, after the existing rules):
   ```css
   figure { margin: 1.5em auto; text-align: center; page-break-inside: avoid; }
   figure img { max-width: 100%; height: auto; }
   figcaption { font-size: 0.85em; font-style: italic; color: #555; margin-top: 0.5em; }
   ```

4. **Emit `<img>` tags in the main loop** (line ~5427). When we encounter a page marker and transition to a new page, check if the PREVIOUS page had images and emit them:
   ```python
   # Inside the main for loop, in the page_marker handling block:
   if p.get('is_page_marker'):
       # Before updating current_page, emit images from the page we just finished
       if current_page in _page_images:
           for img_info in _page_images[current_page]:
               _img_src = f"images/{img_info['filename']}"
               html_parts.append(f'<figure><img src="{_img_src}" alt=""/></figure>\n')
       current_page = p['page_number']
       # ... rest of existing page marker handling
   ```

   **CRITICAL:** This insertion must happen BEFORE the existing `current_page = p['page_number']` assignment and the `html_parts.append(f'<a id="page_{current_page}"></a>\n')` line. The order is:
   1. Emit images for the page we just finished
   2. Update `current_page`
   3. Emit the page anchor

   Also add a final flush after the main loop ends — the last page's images won't get a page marker transition:
   ```python
   # After the main for loop completes, flush remaining images
   if _page_images and current_page in _page_images:
       for img_info in _page_images[current_page]:
           _img_src = f"images/{img_info['filename']}"
           html_parts.append(f'<figure><img src="{_img_src}" alt=""/></figure>\n')
   ```

### Task 4: Caption detection (best-effort)

In `extract_pdf_images()`, after extracting an image, check the next paragraph on the same page for caption-like text. A caption heuristic:
- Short text (< 200 chars)
- Starts with common caption prefixes: "Figure", "Fig.", "Table", "Chart", "Map", "Plate", "Photo", "Illustration"
- OR is italic and short (< 150 chars)

If a caption is detected, include it in the image dict as `'caption': text` and render it in the `<figcaption>` tag:
```python
if img_info.get('caption'):
    _caption_html = html_escape(img_info['caption'])
    html_parts.append(f'<figure><img src="{_img_src}" alt="{_caption_html}"/><figcaption>{_caption_html}</figcaption></figure>\n')
else:
    html_parts.append(f'<figure><img src="{_img_src}" alt=""/></figure>\n')
```

**Important:** Caption detection is best-effort. If the heuristic misidentifies body text as a caption, the text will appear twice (as caption and as paragraph). This is acceptable for v1 — better to include a caption and have a minor dupe than to strip body text. Do NOT remove paragraphs that match as captions.

### Task 5: Update manifest and exports

1. Add `extract_pdf_images` to `feature-manifest.json` under `python_cli_modes` or a new `python_functions` section if one exists.
2. Verify the `--no-images` / `-NoImages` path still works: `filter_content.py`'s `_strip_images()` function (line 204) already removes `<img>` tags from HTML, so the strip path is already built. Just verify it works on HTML with `<figure>` wrappers too — if it only strips `<img>` and leaves orphan `<figure><figcaption>`, fix `_strip_images()` to also remove `<figure>` and `<figcaption>` elements.

## Files to modify
- `tools/pdf_to_balabolka.py` — new `extract_pdf_images()` function + modifications to `process_kindle_html()` and `format_paragraphs_as_html()`
- `tools/filter_content.py` — verify/fix `_strip_images()` handles `<figure>` wrappers
- `feature-manifest.json` — update

## What NOT to change
- Do NOT modify the EPUB image path — it already works
- Do NOT modify `format_kindle_html()` — that's the older formatter; `format_paragraphs_as_html()` is the active one
- Do NOT add new Python dependencies — PyMuPDF (fitz) is already installed
- Do NOT modify settings.json schema
- Do NOT touch the TTS/Balabolka output path — images are Kindle-only

## Testing

### Automated
1. Run `python tools/test_pipeline.py --quick` — all 41 tests must pass
2. Verify: `Import-Module .\module\EbookAutomation.psd1 -Force` loads without errors

### Manual spot-check (document in Jira comment)
Convert these 3 books and verify images appear in intermediate HTML (open in browser):
```powershell
# Book 1: Heavy images — 331 meaningful images
Convert-ToKindle -InputFile "C:\Users\Joe\Downloads\Astronomy-LR.pdf"

# Book 2: Moderate images — 27 historical photos/maps
Convert-ToKindle -InputFile "C:\Users\Joe\Downloads\All the Shah's Men _ An American Coup and the Roots of -- Stephen Kinzer -- John Wiley & Sons, Inc_ (trade), Hoboken, N_J_, 2003 -- John Wiley & Sons, -- 9780470581032 -- 558289301bae9aa82f7c36bbb2d5bcc8 -- Anna's Archive.pdf"

# Book 3: Dense ratio — 104 archival images in 388 pages
Convert-ToKindle -InputFile "C:\Users\Joe\Downloads\AnnalsoftheFowlerFamily_10313122.pdf"
```

For each book, verify:
- [ ] `images/` subdirectory created alongside HTML output
- [ ] `<figure><img ...>` tags present in HTML
- [ ] Images render when HTML is opened in browser
- [ ] No full-page scans included (especially check Astronomy-LR)
- [ ] KFX file contains images when opened on Kindle or Kindle Previewer

Also verify the strip path:
```powershell
Convert-ToKindle -InputFile "C:\Users\Joe\Downloads\Astronomy-LR.pdf" -NoImages
# Verify: no <img> tags in output HTML
```

## Commit
```
git add -A
git commit -m "feat: EB-17 — wire PDF image extraction into Kindle HTML pipeline"
git push
```

## Jira
- Transition EB-17 to Done (transition ID 31) via Atlassian MCP
- Add completion comment listing: number of images extracted per test book, any issues found, confirmation that `-NoImages` strip path works

## Important reminders
- Use `grep -n` for all line number lookups — the line numbers in this prompt are from a project snapshot and may have drifted
- Image extraction failure must NEVER block the text pipeline — always wrap in try/except and return empty list
- The `images/` subdirectory must be relative to the HTML file so Calibre can resolve the paths during conversion
- PyMuPDF page indexing is 0-based; para_dict page_number is 1-based — convert appropriately
