# EB-11 — Image Extraction and Embedding in Kindle Output

## Session Name
pdf-image-extraction

## Claude Code Model
**Opus** — Coordinate geometry for image positioning, multi-system integration (PyMuPDF image extraction + pdfminer text flow), careful insertion into the existing HTML pipeline.

## Ticket
EB-11 — Phase 2: Image extraction and embedding

## Context

PDF books containing figures, charts, maps, and illustrations currently lose all images during text extraction. The Kindle HTML output is text-only. Calibre preserves `<img>` tags with relative paths during KFX/EPUB conversion, so if we extract images and insert `<img>` tags at the correct positions in the HTML, they'll appear in the final Kindle output.

The EPUB path already extracts images (see `extract_html_from_epub()` around line 1976) — it saves them to an `images/` subfolder and rewrites `<img src>` paths. We follow the same pattern for PDF.

**Scope**: pdfminer HTML extraction path only (same scope as EB-70 hyperlinks and EB-10 internal links). Not the legacy pypdf path, not the OCR paths, not the TTS output.

---

## Task 1: Extract Images from PDF via PyMuPDF

Create a new function near the existing `extract_pdf_links()` and `extract_cover_image()`:

```python
def extract_pdf_images(pdf_path, output_dir, log, min_width=100, min_height=100,
                       skip_full_page=True):
    """Extract embedded images from a PDF, saving to output_dir/images/.
    
    Uses PyMuPDF for reliable image extraction with bounding box positions.
    Filters out tiny decorative images, page-spanning scan images, and
    duplicate images (same xref appearing on multiple pages).
    
    Args:
        pdf_path: Path to the source PDF
        output_dir: Directory where images/ subfolder will be created
        log: Logging function
        min_width: Minimum image width in pixels to include (skip icons/bullets)
        min_height: Minimum image height in pixels to include
        skip_full_page: If True, skip images that span >90% of page dimensions
                        (these are full-page scans, not content images)
    
    Returns:
        dict mapping page_number (1-based) to list of image dicts:
        {1: [{'path': 'images/img_001.jpg', 'rect': (x0, y0, x1, y1),
              'width': 400, 'height': 300}]}
        Coordinates are in pdfminer coordinate space (bottom-left origin, y-up).
    """
```

### Implementation details:

1. **Use PyMuPDF** (already a project dependency):
   ```python
   import pymupdf
   doc = pymupdf.open(pdf_path)
   for page_num, page in enumerate(doc):
       image_list = page.get_images(full=True)
       for img_index, img_info in enumerate(image_list):
           xref = img_info[0]  # image xref number
           # Extract raw image data
           base_image = doc.extract_image(xref)
           image_bytes = base_image["image"]
           image_ext = base_image["ext"]  # 'png', 'jpeg', etc.
           # Get bounding box on page
           rects = page.get_image_rects(img_info)
   ```

2. **Coordinate conversion**: PyMuPDF uses top-left origin (y down), pdfminer uses bottom-left origin (y up). Convert exactly like EB-70:
   ```python
   page_height = page.rect.height
   pdfminer_y0 = page_height - pymupdf_rect.y1
   pdfminer_y1 = page_height - pymupdf_rect.y0
   ```

3. **Filtering**:
   - Skip images smaller than `min_width × min_height` (icons, bullets, decorative elements)
   - Skip images that span >90% of page width AND height (`skip_full_page=True`) — these are full-page scans in image-based PDFs. Our pipeline handles those via OCR, not image embedding.
   - Skip duplicate xrefs (same image used on multiple pages — e.g., publisher logos). Track seen xrefs in a set. Exception: if the same xref appears on different pages at different sizes, it might be a legitimately reused figure — include it.

4. **Naming**: `img_{page:03d}_{index:02d}.{ext}` — e.g., `img_005_01.jpg`

5. **Output directory**: `os.path.join(output_dir, 'images')` — create with `os.makedirs(exist_ok=True)`

6. **Graceful fallback**: If PyMuPDF isn't installed, return empty dict and log warning.

---

## Task 2: Insert `<img>` Tags in HTML Output

Integrate image placement into `format_paragraphs_as_html()`.

### Approach:

The para_dicts already carry `page_number` for each paragraph. Images have `page_number` and `rect` (y-position). Insert each image between the two paragraphs that bracket its vertical position on the page.

1. **Pass the image map** from Task 1 into `format_paragraphs_as_html()` as a new optional parameter:
   ```python
   def format_paragraphs_as_html(para_dicts, body_size, bookmarks, log, 
                                  title='Untitled', page_images=None):
   ```

2. **During paragraph emission**, at each page boundary (when `page_number` changes) or when a paragraph's y-position crosses an image's y-position:
   - Check if any images on the current page haven't been emitted yet
   - Find the right insertion point: the image goes AFTER the paragraph whose y0 is above the image rect and BEFORE the paragraph whose y0 is below it
   - Emit: `<div class="book-image"><img src="images/img_005_01.jpg" alt="" /></div>`

3. **Simpler fallback** (if precise positioning proves too complex): Insert all images for a page at the END of that page's paragraphs, just before the next page's content. This is less precise but still gets images near their original location and is much simpler to implement. **Start with this approach** and only move to precise y-positioning if the results are poor.

4. **CSS class**: Add to the theme CSS in `format_kindle_html()`:
   ```css
   .book-image {
       text-align: center;
       margin: 1em 0;
       page-break-inside: avoid;
   }
   .book-image img {
       max-width: 100%;
       height: auto;
   }
   ```

### Caption detection (best-effort):

After inserting an image, check if the next paragraph is a short (<100 chars), italic or smaller-font-size line — this is likely a caption. If so, wrap it:
```html
<div class="book-image">
    <img src="images/img_005_01.jpg" alt="" />
    <p class="caption">Figure 3.1: Distribution of oil reserves by region</p>
</div>
```

Add `.caption` CSS:
```css
.caption {
    font-size: 0.85em;
    font-style: italic;
    text-align: center;
    margin-top: 0.3em;
    color: #555;
}
```

Caption detection is best-effort — if there's no obvious caption, just emit the image without one.

---

## Task 3: Wire Into `process_kindle_html()`

In `process_kindle_html()` (find with `grep -n "def process_kindle_html"`), add image extraction BEFORE `format_paragraphs_as_html()` is called:

```python
# ── Image extraction ──
page_images = {}
if not args.get('no_images'):  # respect the --no-images / -NoImages flag
    try:
        html_dir = os.path.dirname(html_path)
        page_images = extract_pdf_images(pdf_path, html_dir, log)
    except Exception as e:
        log(f"  Image extraction failed (non-blocking): {e}")
        page_images = {}

# ... then pass to format_paragraphs_as_html:
html = format_paragraphs_as_html(para_dicts, body_size, bookmarks, log,
                                  title=title, page_images=page_images)
```

### CLI flag:
Add `--no-images` argument to the argparse setup (find with `grep -n "add_argument" tools/pdf_to_balabolka.py | grep -i "image\|no.image"`). This maps to the existing `-NoImages` switch on `Convert-ToKindle` in the PSM1.

Check if `-NoImages` is already wired through by searching: `grep -n "NoImages\|no.images\|no_images" module/EbookAutomation.psm1`. If the switch exists but isn't passed to the Python script, wire it through by adding `--no-images` to the Python args when `-NoImages` is set.

---

## Task 4: Update Manifest and Documentation

1. Update `feature-manifest.json` — add the new `--no-images` CLI flag to the kindle mode entry
2. No new exported functions needed — image extraction is internal to the pipeline

---

## Scope Boundaries

**In scope:**
- pdfminer HTML extraction path for PDF input
- EPUB already handles images (existing code) — no changes needed

**Out of scope:**
- TTS/Balabolka output (images aren't relevant for audio)
- Legacy pypdf path (text-only)
- OCR paths (scanned PDFs are full-page images, not embedded figures)
- Claude API alt-text generation (ticket mentions "consider" — defer to follow-up)
- PyMuPDF column-aware path (separate follow-up if needed)

---

## What NOT to Do
- Do NOT modify the EPUB image extraction code (it already works)
- Do NOT modify TTS output or the Balabolka text path
- Do NOT add Claude API calls for alt-text (potential future ticket)
- Do NOT change settings.json schema
- Do NOT change the cover image extraction (already working separately)

---

## Verification

1. Run `python tools/test_pipeline.py --quick` — all tests pass (41/41)
2. Run `powershell -File tools\verify-manifest.ps1` — manifest verification passes
3. Test with a PDF that contains figures (Oil Kings has some inline images)
4. Verify `images/` directory is created alongside the HTML output
5. Verify `<img src="images/...">` tags appear in HTML output
6. Verify a PDF with no images produces identical output to before
7. Verify `--no-images` flag suppresses image extraction
8. Git commit: `feat: EB-11 — PDF image extraction and embedding in Kindle HTML output`
9. Git push
10. Transition EB-11 to Done (transition ID 31) via Atlassian MCP
11. Add completion comment with: images extracted count from test book, formats handled
