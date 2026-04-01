# EB-10 — Internal Links and Footnote Extraction (Gap Fill)

## Session Name
internal-links-gap-fill

## Claude Code Model
**Opus** — Coordinate geometry for internal link mapping, integration with existing extraction flow, heading anchor generation.

## Ticket
EB-10 — Phase 2: Internal links and footnote extraction

## Context — What's Already Done

Codebase audit shows most of EB-10 was shipped across prior tickets:

| Goal | Status | Shipped In |
|---|---|---|
| Footnote superscripts from font size | Done | pdfminer char loop, `sup_threshold` |
| `<sup><a href="#noteN">N</a></sup>` links | Done | `_link_endnotes()` |
| Collected endnotes (3 strategies) | Done | `_link_endnotes_collected()`, `_link_per_page_footnotes()` |
| URL hyperlinks as `<a>` tags | Done | EB-70 (`extract_pdf_links()`) |
| **Internal PDF cross-references** | **NOT DONE** | — |
| **Heading anchor IDs in HTML** | **NOT DONE** | — |
| **Tesseract hOCR structural extraction** | **DEFERRED** | See note below |

**hOCR deferral**: The existing tiered extraction (pdfminer → Tesseract OCR → Gemini Flash → Claude Vision) handles scanned PDFs well. Tesseract hOCR would provide bounding-box heading detection, but our font-based detection (`detect_headings_font.py`) and Claude-based detection (`Get-ChapterStructure`) are both higher quality. hOCR adds complexity without proportional quality gain. If needed later, create a dedicated ticket.

## What Remains — Two Tasks

### Task 1: Add Heading Anchor IDs to HTML Output

Currently `format_paragraphs_as_html()` generates headings like `<h1>Chapter Title</h1>` with no `id` attribute. Internal cross-references and any future TOC linking require heading anchors.

**Find** `format_paragraphs_as_html()` using `grep -n "def format_paragraphs_as_html" tools/pdf_to_balabolka.py`.

In the function, find where heading tags are emitted (search for `<h1>`, `<h2>`, `<h3>` in that function). At each heading emission point, generate a stable ID and add it:

```python
def _heading_id(text, counter):
    """Generate a stable, unique heading anchor ID."""
    # Slugify: lowercase, strip non-alphanum, collapse hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower().strip()).strip('-')
    slug = slug[:60]  # cap length
    counter[0] += 1
    return f"heading_{counter[0]}_{slug}" if slug else f"heading_{counter[0]}"
```

Emit headings as: `<h2 id="heading_5_chapter-three">Chapter Three</h2>`

The counter ensures uniqueness even if two headings have the same text.

**Also apply to `format_kindle_html()`** — search for it with `grep -n "def format_kindle_html"`. This is the separate Kindle HTML formatter that also emits `<h1>/<h2>/<h3>` tags. It needs the same treatment.

### Task 2: Internal PDF Cross-Reference Links

**Extend** the existing `extract_pdf_links()` function (added in EB-70, find with `grep -n "def extract_pdf_links"`) to also capture internal /GoTo links.

PyMuPDF link types:
- `kind == 2` (LINK_URI) — external URLs — **already handled**
- `kind == 1` (LINK_GOTO) — internal page jump — **needs adding**

For `kind == 1` links, PyMuPDF provides:
```python
link = page.get_links()[i]
# link['kind'] == 1
# link['page'] — target page number (0-based)
# link['to'] — pymupdf.Point(x, y) target coordinates on that page
# link['from'] — pymupdf.Rect(x0, y0, x1, y1) source bounding box
```

**Algorithm**:

1. In `extract_pdf_links()`, also collect `kind == 1` links into a separate dict:
   ```python
   internal_links[page_num] = [
       {'target_page': link['page'] + 1,  # convert to 1-based
        'target_point': (link['to'].x, link['to'].y),
        'rect': (x0, y0, x1, y1)}  # source bounding box, already converted to pdfminer coords
   ]
   ```

2. Create a new function `_resolve_internal_links(internal_links, heading_registry)` that maps each internal link's target page to the nearest heading anchor ID:
   - Build `heading_registry` during `format_paragraphs_as_html()` as headings are emitted: `{page_number: [(y_position, heading_id), ...]}`
   - For each internal link, find the heading on `target_page` whose y-position is closest to `target_point.y` (within a tolerance of ~50 points)
   - If no heading match, try the first heading on that page
   - If still no match, skip this link (don't inject an `<a>` tag for unresolvable targets)

3. In the pdfminer character loop (where EB-70 injects `<a href="URL">` for external links), also inject `<a href="#heading_id">` for internal links using the same coordinate-overlap mechanism.

**Key constraint**: Internal links are only useful in HTML/Kindle output, not TTS. The `format_paragraphs_as_html` path (which produces Kindle HTML) is the only path that needs this. The legacy pypdf path and TTS path don't need internal link handling.

**Important**: The heading registry must be built DURING heading emission (Task 1), then passed to the internal link resolver. This means Task 1 must produce a side-effect data structure that Task 2 consumes. Design the data flow carefully:

```python
# In format_paragraphs_as_html:
heading_registry = {}  # page_number → [(y0, heading_id)]
# ... when emitting a heading:
heading_id = _heading_id(text, counter)
page_num = para.get('page_number', 0)
heading_registry.setdefault(page_num, []).append((y0_approx, heading_id))
# ... return heading_registry along with html
```

This means `format_paragraphs_as_html` needs to return both the HTML string AND the heading registry. Update the return value and all callers (find with `grep -n "format_paragraphs_as_html(" tools/pdf_to_balabolka.py`).

### Edge Cases

1. **Links spanning column boundaries** — Internal links in two-column PDFs won't work (out of scope — same as EB-70 for external links).

2. **Self-referencing links** — A link pointing to a heading on the same page. These should work naturally — the heading ID is available regardless of page distance.

3. **Links to non-heading targets** — Some PDFs have links pointing to arbitrary text (not headings). These can't be resolved to an anchor. Skip them with a log message.

4. **Books with no internal links** — Many books have zero /GoTo links. The output should be identical to before — no behavioral change.

### Logging

Add summary logging:
```
  Internal links: found 15, resolved 12 to heading anchors (3 unresolvable)
  Heading anchors: 24 IDs generated across 18 pages
```

---

## What NOT to Do
- Do NOT modify the existing endnote linking system (`_link_endnotes` etc.)
- Do NOT modify the TTS/Balabolka text output path
- Do NOT implement hOCR — that's deferred
- Do NOT change the external URL hyperlink behavior from EB-70
- Do NOT change the PyMuPDF column-aware extraction path

---

## Verification

1. Run `python tools/test_pipeline.py --quick` — all tests pass (41/41)
2. Run `powershell -File tools\verify-manifest.ps1` — manifest verification passes
3. Verify HTML output contains heading `id=` attributes (grep the output file)
4. Verify books without internal links produce functionally identical output
5. Git commit: `feat: EB-10 — heading anchor IDs + internal PDF cross-reference links`
6. Git push
7. Transition EB-10 to Done (transition ID 31) via Atlassian MCP
8. Add completion comment noting: items completed, items previously shipped (footnotes, endnotes, external links), hOCR deferred
