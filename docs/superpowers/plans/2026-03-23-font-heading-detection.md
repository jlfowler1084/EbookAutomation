# Font-Based Heading Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a font-analysis heading detector and rewrite Get-ChapterStructure so Claude receives pre-built heading candidates + better text sampling, fixing the Burge bug where only back-matter headings were found.

**Architecture:** Standalone Python CLI tool (`tools/detect_headings_font.py`) scans PDFs via PyMuPDF and EPUBs via ebooklib/BeautifulSoup. PowerShell `Get-ChapterStructure` calls the detector, builds three-zone text samples, and sends both to Claude for confirmation. `Convert-ToKindle` handles EPUB early-exit and per-heading HTML insertion.

**Tech Stack:** Python 3.8+ (PyMuPDF/fitz, ebooklib, BeautifulSoup4), PowerShell 5.1+, Claude API (claude-sonnet-4-6)

**Spec:** `docs/superpowers/specs/2026-03-23-font-heading-detection-design.md`

**Branch:** `feature/chapter-detection`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `tools/detect_headings_font.py` | Create | Standalone CLI: PDF font scanning, EPUB NCX/HTML detection, JSON output |
| `module/EbookAutomation.psm1` | Modify | `Get-ChapterStructure`: new params, three-zone sampling, font integration, Claude prompt. `Convert-ToKindle`: EPUB early-exit, per-heading insertion |

Files NOT modified: `tools/pdf_to_balabolka.py`, `tools/classify_source.py`, `tools/pattern_db.py`

---

## Task 1: Font Detector — CLI Scaffold + Glob Resolution

**Files:**
- Create: `tools/detect_headings_font.py`

This task creates the entry point with argparse, glob resolution, format auto-detection, and error JSON output. No detection logic yet — just the skeleton that routes to PDF or EPUB handlers.

- [ ] **Step 1: Create the CLI scaffold**

```python
"""Font-based heading detection for PDFs and EPUBs.

Scans the full document and identifies likely chapter headings by font size,
weight, and position. Outputs JSON for integration with Get-ChapterStructure.

Dependencies: PyMuPDF (fitz), ebooklib, beautifulsoup4 — all pre-installed.
"""
import argparse
import glob
import json
import logging
import os
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

logger = logging.getLogger(__name__)


def resolve_input_path(raw_path):
    """Resolve glob patterns in input path. Returns resolved path or exits."""
    if '*' in raw_path or '?' in raw_path:
        matches = glob.glob(raw_path)
        if not matches:
            return None, f"No files match pattern: {raw_path}"
        if len(matches) > 1:
            print(f"Warning: {len(matches)} files match pattern, using first: {matches[0]}",
                  file=sys.stderr)
        return matches[0], None
    if not os.path.isfile(raw_path):
        return None, f"File not found: {raw_path}"
    return raw_path, None


def detect_format(input_path, force_epub=False):
    """Auto-detect format from extension. Returns 'pdf' or 'epub'."""
    if force_epub:
        return 'epub'
    ext = os.path.splitext(input_path)[1].lower()
    if ext == '.epub':
        return 'epub'
    elif ext == '.pdf':
        return 'pdf'
    return None


def error_json(message):
    """Print error as JSON to stdout and exit 1."""
    json.dump({"error": message}, sys.stdout, indent=2)
    print()
    sys.exit(1)


def detect_headings_pdf(input_path, verbose=False):
    """Detect headings from PDF using font analysis. Returns result dict."""
    # Placeholder — implemented in Task 2-5
    return {
        "file": input_path,
        "format": "pdf",
        "body_font_size": None,
        "body_font_name": None,
        "total_pages": 0,
        "pages_scanned": 0,
        "heading_candidates": [],
        "font_histogram": {}
    }


def detect_headings_epub(input_path, verbose=False):
    """Detect headings from EPUB using NCX/nav + HTML parsing. Returns result dict."""
    # Placeholder — implemented in Task 7-8
    return {
        "file": input_path,
        "format": "epub",
        "body_font_size": None,
        "body_font_name": None,
        "total_pages": 0,
        "pages_scanned": 0,
        "heading_candidates": [],
        "font_histogram": {}
    }


def format_text_output(result):
    """Format result dict as human-readable text."""
    lines = []
    fname = os.path.basename(result['file'])
    body_font = result.get('body_font_name', 'unknown')
    body_size = result.get('body_font_size', 0)
    total = result.get('total_pages', 0)
    scanned = result.get('pages_scanned', 0)
    candidates = result.get('heading_candidates', [])

    lines.append(f"Font Analysis: {fname}")
    if body_font and body_size:
        hist = result.get('font_histogram', {})
        body_chars = hist.get(str(body_size), 0)
        lines.append(f"Body font: {body_font} @ {body_size}pt ({body_chars} chars)")
    lines.append(f"Pages scanned: {scanned} of {total}")
    lines.append("")
    lines.append(f"Heading Candidates ({len(candidates)} found):")
    for c in candidates:
        level = c.get('level', '??')
        page = c.get('page', '?')
        conf = c.get('confidence', 0)
        text = c.get('text', '')
        size = c.get('font_size')
        bold = " bold" if c.get('is_bold') else ""
        size_str = f" ({size}pt{bold})" if size else ""
        lines.append(f"  {level:<4}p.{page:<4} [{conf:.2f}] \"{text}\"{size_str}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Detect chapter headings from PDF/EPUB font analysis')
    parser.add_argument('--input', required=True,
                        help='Path to PDF or EPUB (supports glob patterns)')
    parser.add_argument('--epub', action='store_true',
                        help='Force EPUB parsing mode')
    parser.add_argument('--format', choices=['json', 'text'], default='json',
                        help='Output format (default: json)')
    parser.add_argument('--verbose', action='store_true',
                        help='Print diagnostic info to stderr')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format='%(levelname)s: %(message)s')
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    # Resolve glob
    input_path, err = resolve_input_path(args.input)
    if err:
        error_json(err)

    # Detect format
    fmt = detect_format(input_path, force_epub=args.epub)
    if fmt is None:
        error_json(f"Unsupported format: {os.path.splitext(input_path)[1]}")

    # Route to detector
    if fmt == 'pdf':
        result = detect_headings_pdf(input_path, verbose=args.verbose)
    else:
        result = detect_headings_epub(input_path, verbose=args.verbose)

    # Output
    if args.format == 'text':
        print(format_text_output(result))
    else:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        print()


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Verify CLI runs with --help**

Run: `python tools/detect_headings_font.py --help`
Expected: argparse help text with --input, --epub, --format, --verbose options

- [ ] **Step 3: Verify glob error handling**

Run: `python tools/detect_headings_font.py --input "F:\nonexistent\*.pdf"`
Expected: `{"error": "No files match pattern: F:\\nonexistent\\*.pdf"}` and exit code 1

- [ ] **Step 4: Verify stub runs on a real PDF**

Run: `python tools/detect_headings_font.py --input "F:\Books\Bible Study\Burge*.pdf"`
Expected: Valid JSON with empty `heading_candidates` array (stub output)

- [ ] **Step 5: Commit**

```bash
git add tools/detect_headings_font.py
git commit -m "feat: scaffold detect_headings_font.py CLI with glob resolution"
```

---

## Task 2: PDF Font Profile — Body Font Detection

**Files:**
- Modify: `tools/detect_headings_font.py` — replace `detect_headings_pdf()` stub

Implement the core font scanning: iterate all pages via fitz, build a character-count-weighted font-size histogram, identify the body font (most common size).

- [ ] **Step 1: Implement font profile scanning**

Replace `detect_headings_pdf()` with:

```python
def detect_headings_pdf(input_path, verbose=False):
    """Detect headings from PDF using font analysis."""
    try:
        import fitz
    except ImportError:
        error_json("PyMuPDF (fitz) not installed")

    try:
        doc = fitz.open(input_path)
    except Exception as e:
        error_json(f"Cannot open PDF: {e}")

    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        return _empty_pdf_result(input_path, 0, 0, warning="PDF has no pages")

    # Determine which pages to scan (skip first 2 unless short PDF)
    skip_pages = 2 if total_pages > 3 else 0
    pages_to_scan = range(skip_pages, total_pages)

    # Pass 1: Build font histogram and collect text blocks
    font_char_counts = {}   # {font_size_rounded: total_char_count}
    all_blocks = []         # [(page_num, y_pos, text, font_name, font_size, is_bold, is_italic, is_centered)]
    page_width_cache = {}

    for page_num in pages_to_scan:
        page = doc[page_num]
        page_width = page.rect.width
        page_center_x = page_width / 2
        page_width_cache[page_num] = page_width

        page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:  # text blocks only
                continue

            block_text_parts = []
            block_font_sizes = {}   # {size: char_count}
            block_font_names = {}   # {name: char_count}
            block_bold_chars = 0
            block_italic_chars = 0
            block_total_chars = 0
            block_x0 = block.get("bbox", [0])[0]
            block_x1 = block.get("bbox", [0, 0, 0])[2] if len(block.get("bbox", [])) >= 3 else page_width

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    char_count = len(text)
                    if char_count == 0:
                        continue

                    size = round(span.get("size", 0) * 2) / 2  # round to 0.5pt
                    font_name = span.get("font", "")
                    flags = span.get("flags", 0)
                    is_bold = bool(flags & (1 << 4))    # bit 4
                    is_italic = bool(flags & (1 << 1))  # bit 1

                    block_text_parts.append(text)
                    block_font_sizes[size] = block_font_sizes.get(size, 0) + char_count
                    block_font_names[font_name] = block_font_names.get(font_name, 0) + char_count
                    if is_bold:
                        block_bold_chars += char_count
                    if is_italic:
                        block_italic_chars += char_count
                    block_total_chars += char_count

                    # Global histogram
                    font_char_counts[size] = font_char_counts.get(size, 0) + char_count

            if block_total_chars == 0:
                continue

            # Dominant font for this block
            dom_size = max(block_font_sizes, key=block_font_sizes.get)
            dom_name = max(block_font_names, key=block_font_names.get)
            is_bold = block_bold_chars > block_total_chars * 0.5
            is_italic = block_italic_chars > block_total_chars * 0.5

            # Centering check: block center within 40pt of page center
            block_center = (block_x0 + block_x1) / 2
            is_centered = abs(block_center - page_center_x) < 40

            full_text = "".join(block_text_parts).strip()
            if not full_text:
                continue

            y_pos = block.get("bbox", [0, 0])[1]  # top y coordinate

            all_blocks.append({
                'page': page_num,
                'y': y_pos,
                'text': full_text,
                'font_name': dom_name,
                'font_size': dom_size,
                'is_bold': is_bold,
                'is_italic': is_italic,
                'is_centered': is_centered,
            })

    doc.close()

    # Determine body font
    if not font_char_counts:
        return _empty_pdf_result(input_path, total_pages, len(pages_to_scan),
                                 warning="PDF has no extractable text")

    body_size = max(font_char_counts, key=font_char_counts.get)

    # Find body font name from blocks at body size
    body_name_counts = {}
    for b in all_blocks:
        if b['font_size'] == body_size:
            body_name_counts[b['font_name']] = body_name_counts.get(b['font_name'], 0) + len(b['text'])
    body_name = max(body_name_counts, key=body_name_counts.get) if body_name_counts else None

    logger.debug(f"Body font: {body_name} @ {body_size}pt")
    logger.debug(f"Font histogram: {dict(sorted(font_char_counts.items()))}")

    # Store for later tasks (heading identification + noise filtering)
    # For now, return the profile with empty candidates
    result = {
        "file": input_path,
        "format": "pdf",
        "body_font_size": body_size,
        "body_font_name": body_name,
        "total_pages": total_pages,
        "pages_scanned": len(pages_to_scan),
        "heading_candidates": [],
        "font_histogram": {str(k): v for k, v in sorted(font_char_counts.items())}
    }

    # TODO: Tasks 3-5 will add candidate identification, filtering, and scoring
    # For now, pass all_blocks and body_size to those functions
    candidates = identify_heading_candidates(all_blocks, body_size)
    candidates = filter_noise(candidates, all_blocks, len(pages_to_scan))
    candidates = assign_levels_and_confidence(candidates, body_size)
    result['heading_candidates'] = candidates
    return result


def _empty_pdf_result(input_path, total_pages, pages_scanned, warning=None):
    """Return an empty result for PDFs with no usable content."""
    result = {
        "file": input_path,
        "format": "pdf",
        "body_font_size": None,
        "body_font_name": None,
        "total_pages": total_pages,
        "pages_scanned": pages_scanned,
        "heading_candidates": [],
        "font_histogram": {}
    }
    if warning:
        result["warning"] = warning
    return result


# Stubs for Tasks 3-5 (will be filled in next tasks)
def identify_heading_candidates(all_blocks, body_size):
    return []

def filter_noise(candidates, all_blocks, pages_scanned):
    return candidates

def assign_levels_and_confidence(candidates, body_size):
    return candidates
```

- [ ] **Step 2: Verify font profile on a real PDF**

Run: `python tools/detect_headings_font.py --input "F:\Books\Bible Study\Burge*.pdf" --verbose`
Expected: stderr shows body font name and size, stdout JSON has `body_font_size` and `font_histogram` populated, empty `heading_candidates`

- [ ] **Step 3: Commit**

```bash
git add tools/detect_headings_font.py
git commit -m "feat: PDF font profile scanning — body font detection + histogram"
```

---

## Task 3: PDF Heading Candidate Identification

**Files:**
- Modify: `tools/detect_headings_font.py` — implement `identify_heading_candidates()`

- [ ] **Step 1: Implement candidate identification**

```python
import re

# Chapter heading patterns
CHAPTER_PATTERNS = [
    re.compile(r'^(?:Chapter|Part|CHAPTER|PART)\s+\d+', re.IGNORECASE),
    re.compile(r'^\d+\.\s+\w'),           # "1. Title"
    re.compile(r'^\d+\s+[A-Z]'),          # "1 Title" (dot-less)
    re.compile(r'^[IVXLC]+\.\s+\w'),      # "IV. Title"
    re.compile(r'^(?:Introduction|Conclusion|Preface|Foreword|Epilogue|Prologue|Appendix)\b', re.IGNORECASE),
]


def matches_chapter_pattern(text):
    """Check if text matches any known chapter heading pattern."""
    for pat in CHAPTER_PATTERNS:
        if pat.match(text):
            return True
    return False


def identify_heading_candidates(all_blocks, body_size):
    """Identify blocks that look like headings based on font metrics + patterns."""
    if body_size is None or body_size <= 0:
        return []

    candidates = []
    for block in all_blocks:
        size = block['font_size']
        is_bold = block['is_bold']
        text = block['text']

        # Skip blocks that are too short or too long
        if len(text) < 3 or len(text) > 120:
            continue

        # Check heading criteria (any one qualifies)
        signals = []

        # Criterion 1: Font size >= 1.5x body
        size_ratio = size / body_size if body_size > 0 else 0
        if size_ratio >= 1.5:
            signals.append(f"font_size_ratio:{size_ratio:.2f}")

        # Criterion 2: Bold AND font size >= 1.2x body
        if is_bold and size_ratio >= 1.2:
            signals.append("bold_large")

        # Criterion 3: Matches chapter pattern
        if matches_chapter_pattern(text):
            signals.append("chapter_pattern")

        if not signals:
            continue

        # Additional signals for confidence scoring later
        if is_bold and "bold_large" not in signals:
            signals.append("bold")
        if block['is_centered']:
            signals.append("centered")
        word_count = len(text.split())
        if word_count <= 10:
            signals.append("short_text")

        candidates.append({
            'text': text,
            'page': block['page'],
            'font_size': size,
            'font_name': block['font_name'],
            'is_bold': is_bold,
            'y': block['y'],
            'is_centered': block['is_centered'],
            'detection_signals': signals,
            'size_ratio': size_ratio,
        })

    return candidates
```

- [ ] **Step 2: Verify candidates found on Burge PDF**

Run: `python tools/detect_headings_font.py --input "F:\Books\Bible Study\Burge*.pdf" --format text`
Expected: Non-empty candidate list showing chapter-level headings (not just "Notes")

- [ ] **Step 3: Commit**

```bash
git add tools/detect_headings_font.py
git commit -m "feat: PDF heading candidate identification — font size, bold, patterns"
```

---

## Task 4: PDF Noise Filtering

**Files:**
- Modify: `tools/detect_headings_font.py` — implement `filter_noise()`

- [ ] **Step 1: Implement noise filters**

```python
def filter_noise(candidates, all_blocks, pages_scanned):
    """Remove headers/footers, page numbers, running headers from candidates."""
    if not candidates or pages_scanned == 0:
        return candidates

    # Build header/footer frequency map from ALL blocks (not just candidates)
    # Key: (normalized_text, rounded_y) -> set of page numbers
    position_freq = {}
    for block in all_blocks:
        norm_text = ' '.join(block['text'].lower().split())
        rounded_y = round(block['y'] / 5) * 5  # round to nearest 5pt
        key = (norm_text, rounded_y)
        if key not in position_freq:
            position_freq[key] = set()
        position_freq[key].add(block['page'])

    # Build running header frequency (all-caps text <= 5 words)
    caps_text_pages = {}  # normalized_text -> set of pages
    for block in all_blocks:
        text = block['text'].strip()
        words = text.split()
        if len(words) <= 5 and text == text.upper() and len(text) >= 3 and any(c.isalpha() for c in text):
            norm = ' '.join(text.lower().split())
            if norm not in caps_text_pages:
                caps_text_pages[norm] = set()
            caps_text_pages[norm].add(block['page'])

    filtered = []
    for c in candidates:
        text = c['text']
        norm_text = ' '.join(text.lower().split())
        rounded_y = round(c['y'] / 5) * 5

        # Filter: header/footer (same text + position on >50% of pages)
        key = (norm_text, rounded_y)
        if key in position_freq and len(position_freq[key]) > pages_scanned * 0.5:
            logger.debug(f"Filtered (header/footer): \"{text}\" on {len(position_freq[key])} pages")
            continue

        # Filter: page numbers (purely numeric or Roman numeral)
        stripped = text.strip()
        if stripped.isdigit():
            logger.debug(f"Filtered (page number): \"{text}\"")
            continue
        if re.match(r'^[IVXLC]+$', stripped) and len(stripped) <= 6:
            logger.debug(f"Filtered (Roman numeral page): \"{text}\"")
            continue

        # Filter: running headers (all-caps <= 5 words on >30% of pages)
        words = text.split()
        if len(words) <= 5 and text == text.upper() and any(c.isalpha() for c in text):
            if norm_text in caps_text_pages and len(caps_text_pages[norm_text]) > pages_scanned * 0.3:
                logger.debug(f"Filtered (running header): \"{text}\" on {len(caps_text_pages[norm_text])} pages")
                continue

        filtered.append(c)

    logger.debug(f"Noise filter: {len(candidates)} -> {len(filtered)} candidates")
    return filtered
```

- [ ] **Step 2: Verify filtering removes running headers**

Run: `python tools/detect_headings_font.py --input "F:\Books\Bible Study\Burge*.pdf" --verbose --format text`
Expected: stderr shows "Filtered (running header/footer)" messages, candidate list is cleaner

- [ ] **Step 3: Commit**

```bash
git add tools/detect_headings_font.py
git commit -m "feat: PDF noise filtering — headers, footers, page numbers, running headers"
```

---

## Task 5: Level Assignment + Confidence Scoring

**Files:**
- Modify: `tools/detect_headings_font.py` — implement `assign_levels_and_confidence()`

- [ ] **Step 1: Implement level assignment and confidence scoring**

```python
def assign_levels_and_confidence(candidates, body_size):
    """Assign h1/h2/h3 levels and confidence scores to candidates."""
    if not candidates:
        return []

    # Find distinct font sizes among candidates (sorted descending)
    font_sizes = sorted(set(c['font_size'] for c in candidates), reverse=True)

    # Map font sizes to levels
    size_to_level = {}
    if len(font_sizes) >= 1:
        size_to_level[font_sizes[0]] = 'h1'
    if len(font_sizes) >= 2:
        size_to_level[font_sizes[1]] = 'h2'
    if len(font_sizes) >= 3:
        for s in font_sizes[2:]:
            size_to_level[s] = 'h3'

    result = []
    for c in candidates:
        signals = c['detection_signals']

        # Level assignment: pattern match overrides size-based
        if any('chapter_pattern' in s for s in signals):
            text = c['text']
            if re.match(r'^(?:Part|PART)\s+', text, re.IGNORECASE):
                level = 'h1'
            elif re.match(r'^(?:Chapter|CHAPTER)\s+', text, re.IGNORECASE):
                level = 'h1'
            else:
                level = size_to_level.get(c['font_size'], 'h2')
        else:
            level = size_to_level.get(c['font_size'], 'h2')

        # Confidence scoring: base 0.3, additive, capped at 0.99
        conf = 0.3
        if c['size_ratio'] >= 1.5:
            conf += 0.3
        if c['is_bold']:
            conf += 0.2
        if any('chapter_pattern' in s for s in signals):
            conf += 0.3
        if c['is_centered']:
            conf += 0.1
        if len(c['text'].split()) <= 10:
            conf += 0.1
        conf = min(conf, 0.99)

        result.append({
            'text': c['text'],
            'page': c['page'],
            'y': c['y'],
            'level': level,
            'font_size': c['font_size'],
            'font_name': c['font_name'],
            'is_bold': c['is_bold'],
            'confidence': round(conf, 2),
            'detection_signals': signals,
        })

    # Sort by page number, then y-position (reading order)
    result.sort(key=lambda x: (x['page'], x.get('y', 0)))

    # Strip internal y field from output (not part of JSON schema)
    for r in result:
        r.pop('y', None)
    return result
```

- [ ] **Step 2: Verify full PDF pipeline on Burge**

Run: `python tools/detect_headings_font.py --input "F:\Books\Bible Study\Burge*.pdf" --format text`
Expected: Heading candidates with h1/h2/h3 levels and confidence scores. Chapter headings like "1 Promised land..." should appear as h1 with confidence >= 0.7.

- [ ] **Step 3: Verify JSON output is valid and parseable by PowerShell**

Run: `python tools/detect_headings_font.py --input "F:\Books\Bible Study\Burge*.pdf" | powershell -Command "$j = [Console]::In.ReadToEnd() | ConvertFrom-Json; Write-Host ('Candidates: ' + $j.heading_candidates.Count)"`
Expected: `Candidates: N` where N > 0

- [ ] **Step 4: Commit**

```bash
git add tools/detect_headings_font.py
git commit -m "feat: PDF heading level assignment + confidence scoring"
```

---

## Task 6: EPUB Detection — NCX/Nav Extraction

**Files:**
- Modify: `tools/detect_headings_font.py` — implement first half of `detect_headings_epub()`

- [ ] **Step 1: Implement NCX/nav TOC extraction**

```python
def detect_headings_epub(input_path, verbose=False):
    """Detect headings from EPUB using NCX/nav + HTML parsing."""
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except ImportError as e:
        error_json(f"Missing dependency: {e}")

    try:
        book = epub.read_epub(input_path, options={'ignore_ncx': False})
    except Exception as e:
        error_json(f"Cannot open EPUB: {e}")

    candidates = []
    spine_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    spine_ids = [item_id for item_id, _ in book.spine] if book.spine else []

    # Build spine index map: item id/href -> spine position
    spine_index = {}
    for idx, item in enumerate(spine_items):
        spine_index[item.get_id()] = idx
        spine_index[item.get_name()] = idx

    # Step 1: NCX / nav extraction
    ncx_candidates = _extract_ncx_candidates(book, spine_index)

    if ncx_candidates:
        logger.debug(f"NCX/nav: found {len(ncx_candidates)} TOC entries")
        candidates.extend(ncx_candidates)

    # Step 2: HTML parsing supplement (Task 8)
    html_candidates = _extract_html_heading_candidates(book, spine_items, spine_index)
    # Dedup against NCX
    html_candidates = _dedup_against_ncx(html_candidates, ncx_candidates)
    candidates.extend(html_candidates)

    # Sort by page (spine index)
    candidates.sort(key=lambda x: (x.get('page', 0), x.get('confidence', 0)))

    return {
        "file": input_path,
        "format": "epub",
        "body_font_size": None,
        "body_font_name": None,
        "total_pages": len(spine_items),
        "pages_scanned": len(spine_items),
        "heading_candidates": candidates,
        "font_histogram": {}
    }


def _extract_ncx_candidates(book, spine_index):
    """Extract heading candidates from EPUB NCX table of contents."""
    candidates = []
    toc = book.toc
    if not toc:
        return candidates

    def process_toc_items(items, depth=0):
        for item in items:
            if isinstance(item, tuple):
                # Nested section: (Section, [children])
                section, children = item
                title = section.title.strip() if section.title else ''
                href = section.href.split('#')[0] if section.href else ''
                if title and len(title) >= 3:
                    level = 'h1' if depth == 0 else ('h2' if depth == 1 else 'h3')
                    page = spine_index.get(href, 0)
                    candidates.append({
                        'text': title,
                        'page': page,
                        'level': level,
                        'font_size': None,
                        'font_name': None,
                        'is_bold': None,
                        'confidence': 0.95,
                        'detection_signals': ['ncx_toc'],
                    })
                if children:
                    process_toc_items(children, depth + 1)
            else:
                # ebooklib.epub.Link
                title = item.title.strip() if item.title else ''
                href = item.href.split('#')[0] if item.href else ''
                if title and len(title) >= 3:
                    level = 'h1' if depth == 0 else ('h2' if depth == 1 else 'h3')
                    page = spine_index.get(href, 0)
                    candidates.append({
                        'text': title,
                        'page': page,
                        'level': level,
                        'font_size': None,
                        'font_name': None,
                        'is_bold': None,
                        'confidence': 0.95,
                        'detection_signals': ['ncx_toc'],
                    })

    process_toc_items(toc, depth=0)

    # Flat NCX heuristic: if ALL entries are depth 0 and >5, they're chapters not parts
    if candidates and all(c['level'] == 'h1' for c in candidates) and len(candidates) > 5:
        logger.debug(f"Flat NCX detected ({len(candidates)} top-level entries) -- downgrading to h2")
        for c in candidates:
            c['level'] = 'h2'

    return candidates


def _normalize_for_dedup(text):
    """Normalize text for deduplication: strip numbering, lowercase, collapse whitespace."""
    text = text.strip().lower()
    # Strip leading numbering: "1. ", "1 ", "I. ", "Chapter 1: ", etc.
    text = re.sub(r'^(?:chapter|part)?\s*[\dIVXLC]+[\.\):]?\s*', '', text, flags=re.IGNORECASE)
    text = ' '.join(text.split())
    return text


def _dedup_against_ncx(html_candidates, ncx_candidates):
    """Remove HTML candidates that duplicate NCX entries."""
    if not ncx_candidates:
        return html_candidates

    ncx_normalized = {_normalize_for_dedup(c['text']) for c in ncx_candidates}
    deduped = []
    for c in html_candidates:
        if _normalize_for_dedup(c['text']) not in ncx_normalized:
            deduped.append(c)
        else:
            logger.debug(f"Dedup: \"{c['text']}\" matches NCX entry")
    return deduped


# Stub for Task 8
def _extract_html_heading_candidates(book, spine_items, spine_index):
    return []
```

- [ ] **Step 2: Test on an EPUB with NCX**

Run: `python tools/detect_headings_font.py --input "C:\Users\Joe\Downloads\Jesus Victory of God V2*.epub" --format text`
Expected: NCX TOC entries as heading candidates with confidence 0.95 and `ncx_toc` signal

- [ ] **Step 3: Commit**

```bash
git add tools/detect_headings_font.py
git commit -m "feat: EPUB NCX/nav TOC extraction for heading detection"
```

---

## Task 7: EPUB Detection — HTML Heading Parsing + Dedup

**Files:**
- Modify: `tools/detect_headings_font.py` — implement `_extract_html_heading_candidates()`

- [ ] **Step 1: Implement HTML heading extraction**

```python
def _extract_html_heading_candidates(book, spine_items, spine_index):
    """Extract heading candidates from EPUB HTML content."""
    from bs4 import BeautifulSoup
    candidates = []
    heading_class_patterns = re.compile(r'chapter|heading|title|part|section', re.IGNORECASE)

    for item in spine_items:
        page = spine_index.get(item.get_id(), spine_index.get(item.get_name(), 0))
        try:
            content = item.get_content().decode('utf-8', errors='replace')
        except Exception:
            continue

        soup = BeautifulSoup(content, 'html.parser')

        # 1. Semantic headings: h1, h2, h3
        for tag_name in ['h1', 'h2', 'h3']:
            for tag in soup.find_all(tag_name):
                text = tag.get_text(strip=True)
                if text and 3 <= len(text) <= 120:
                    candidates.append({
                        'text': text,
                        'page': page,
                        'level': tag_name,
                        'font_size': None,
                        'font_name': None,
                        'is_bold': None,
                        'confidence': 0.95,
                        'detection_signals': [f'semantic_{tag_name}'],
                    })

        # 2. Class-styled headings
        for el in soup.find_all(attrs={'class': heading_class_patterns}):
            # Skip if already captured as semantic heading
            if el.name in ('h1', 'h2', 'h3'):
                continue
            text = el.get_text(strip=True)
            if text and 3 <= len(text) <= 120:
                class_str = ' '.join(el.get('class', []))
                # Infer level from class name
                if re.search(r'part', class_str, re.IGNORECASE):
                    level = 'h1'
                elif re.search(r'chapter|title', class_str, re.IGNORECASE):
                    level = 'h1'
                elif re.search(r'section', class_str, re.IGNORECASE):
                    level = 'h2'
                else:
                    level = 'h2'
                candidates.append({
                    'text': text,
                    'page': page,
                    'level': level,
                    'font_size': None,
                    'font_name': None,
                    'is_bold': None,
                    'confidence': 0.85,
                    'detection_signals': [f'css_class:{class_str[:30]}'],
                })

        # 3. Inline-styled headings (font-size or font-weight in style attr)
        for el in soup.find_all(['div', 'p', 'span']):
            if el.name in ('h1', 'h2', 'h3'):
                continue
            if el.get('class') and heading_class_patterns.search(' '.join(el.get('class', []))):
                continue
            style = el.get('style', '')
            if not style:
                continue
            text = el.get_text(strip=True)
            if not text or len(text) < 3 or len(text) > 120:
                continue
            # Check for large font-size or bold weight
            has_large_font = bool(re.search(r'font-size\s*:\s*(\d+)', style) and
                                  int(re.search(r'font-size\s*:\s*(\d+)', style).group(1)) >= 16)
            has_bold = bool(re.search(r'font-weight\s*:\s*bold', style, re.IGNORECASE))
            if has_large_font or (has_bold and len(text.split()) <= 15):
                candidates.append({
                    'text': text,
                    'page': page,
                    'level': 'h2',
                    'font_size': None,
                    'font_name': None,
                    'is_bold': has_bold,
                    'confidence': 0.75,
                    'detection_signals': ['inline_style'],
                })

        # 4. Structural patterns in div/p elements
        for el in soup.find_all(['div', 'p']):
            # Skip if already captured
            if el.name in ('h1', 'h2', 'h3'):
                continue
            if el.get('class') and heading_class_patterns.search(' '.join(el.get('class', []))):
                continue
            text = el.get_text(strip=True)
            if text and 3 <= len(text) <= 120 and matches_chapter_pattern(text):
                candidates.append({
                    'text': text,
                    'page': page,
                    'level': 'h2',
                    'font_size': None,
                    'font_name': None,
                    'is_bold': None,
                    'confidence': 0.70,
                    'detection_signals': ['structural_pattern'],
                })

    return candidates
```

- [ ] **Step 2: Test EPUB HTML parsing supplements NCX**

Run: `python tools/detect_headings_font.py --input "C:\Users\Joe\Downloads\Jesus Victory of God V2*.epub" --verbose --format text`
Expected: NCX entries as primary candidates, any HTML-only headings added with lower confidence, dedup messages in stderr

- [ ] **Step 3: Commit**

```bash
git add tools/detect_headings_font.py
git commit -m "feat: EPUB HTML heading detection with NCX deduplication"
```

---

## Task 8: Get-ChapterStructure — Three-Zone Sampling + New Params

**Files:**
- Modify: `module/EbookAutomation.psm1:2974-3062` — rewrite `Get-ChapterStructure`

- [ ] **Step 1: Rewrite Get-ChapterStructure with new parameters and sampling**

Replace the function at lines 2974-3062 with:

```powershell
function Get-ChapterStructure {
    <#
    .SYNOPSIS  Use Claude to identify chapter/part titles with font-based pre-analysis.
    .DESCRIPTION
        Runs font-based heading detection on the source file, then sends three-zone
        text samples + font candidates to Claude for chapter confirmation.

        Three-zone sampling:
          Zone 1: First 3000 words (front matter, TOC)
          Zone 2: 8 x 500-word body samples at 10%-80% through the book
          Zone 3: Last 2000 words (back matter)

        If font detection finds heading candidates, they're included in the Claude
        prompt so Claude confirms/ranks instead of searching blind.
    .PARAMETER TextContent
        The full extracted text of a book (from pdf_to_balabolka.py or similar).
    .PARAMETER InputFile
        Path to the source PDF/EPUB. Required for font-based detection.
        If omitted, falls back to text-only sampling (no font candidates).
    .OUTPUTS
        An array of objects with 'level' and 'title' properties, or $null on failure.
    .EXAMPLE
        $chapters = Get-ChapterStructure -TextContent $text -InputFile "book.pdf"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$TextContent,
        [string]$InputFile
    )

    # -- Step 1: Run font-based heading detection (if source file provided)
    $fontCandidatesSection = ""
    if ($InputFile -and (Test-Path $InputFile)) {
        $cfg    = Get-EbookConfig
        $python = $cfg.paths.python
        $detectScript = Join-Path $script:ModuleRoot 'tools\detect_headings_font.py'

        if (Test-Path $detectScript) {
            Write-EbookLog "Chapter detection: running font-based heading analysis..."
            try {
                $fontJsonRaw = & $python $detectScript --input "$InputFile" --format json 2>$null
                $fontJson = if ($fontJsonRaw -is [array]) { $fontJsonRaw -join "`n" } else { $fontJsonRaw }
                if ($fontJson) {
                    $fontResult = $fontJson | ConvertFrom-Json
                    $candidates = $fontResult.heading_candidates
                    if ($candidates -and $candidates.Count -gt 0) {
                        Write-EbookLog "Chapter detection: font analysis found $($candidates.Count) heading candidates"
                        $lines = @()
                        $lines += "=== FONT-DETECTED HEADING CANDIDATES ==="
                        $lines += "The following headings were detected from font analysis of the full document."
                        $lines += "Confirm which are real chapter/section headings, flag false positives, and note any chapters in the text samples not in this list."
                        $lines += ""
                        foreach ($c in $candidates) {
                            $sizeStr = if ($c.font_size) { "$($c.font_size)pt" } else { "" }
                            $boldStr = if ($c.is_bold) { " bold" } else { "" }
                            $detail  = if ($sizeStr) { " ($sizeStr$boldStr)" } else { "" }
                            $lines += "  $($c.level)  p.$($c.page)  [$($c.confidence)] `"$($c.text)`"$detail"
                        }
                        $fontCandidatesSection = $lines -join "`n"
                    } else {
                        Write-EbookLog "Chapter detection: font analysis found 0 candidates -- Claude will search text only"
                    }
                }
            } catch {
                Write-EbookLog "Chapter detection: font analysis failed ($_) -- continuing without font candidates" -Level WARN
            }
        }
    }

    # -- Step 2: Build three-zone text samples
    $words = $TextContent -split '\s+'
    $totalWords = $words.Count

    if ($totalWords -lt 9000) {
        # Short book: send everything
        $sample = $TextContent
        Write-EbookLog "Chapter detection: short book ($totalWords words) -- sending full text to Claude"
    } else {
        $sampleParts = [System.Collections.Generic.List[string]]::new()

        # Zone 1: Front matter (first 3000 words)
        $zone1 = ($words[0..2999]) -join ' '
        $sampleParts.Add("=== FRONT MATTER (first 3000 words) ===`n$zone1")

        # Zone 2: 8 body samples at 10%-80%
        for ($i = 0; $i -lt 8; $i++) {
            $pct = 0.10 + $i * 0.10
            $startWord = [Math]::Floor($totalWords * $pct)
            $endWord = [Math]::Min($startWord + 499, $totalWords - 1)
            $pageEstimate = [Math]::Floor($pct * 100)
            $chunk = ($words[$startWord..$endWord]) -join ' '
            $sampleParts.Add("=== BODY SAMPLE $($i + 1) (~${pageEstimate}% through book) ===`n$chunk")
        }

        # Zone 3: Back matter (last 2000 words)
        $backStart = [Math]::Max(0, $totalWords - 2000)
        $zone3 = ($words[$backStart..($totalWords - 1)]) -join ' '
        $sampleParts.Add("=== BACK MATTER (last 2000 words) ===`n$zone3")

        $sample = $sampleParts -join "`n`n"
        Write-EbookLog "Chapter detection: three-zone sampling ($totalWords words total) -- sending ~9000 words to Claude"
    }

    # -- Step 3: Build Claude prompt
    $systemPrompt = @"
You are analyzing an ebook to build its table of contents. Identify the CHAPTER STRUCTURE.

PRIORITY ORDER:
1. MAIN CHAPTERS - numbered or titled divisions of core content
2. MAJOR SECTIONS - Parts containing chapters
3. FRONT MATTER - Preface, Foreword, Introduction, Acknowledgments
4. BACK MATTER - Notes, Bibliography, Index, Appendix (mark is_back_matter: true)

DO NOT treat as chapter headings:
- Running headers/footers repeated on every page
- Section sub-headings within a chapter
- Decorative text, epigraphs, pull quotes
- List items or numbered points within body text

Respond with a raw JSON array (no markdown fences). Each entry:
{"title": "exact heading text", "level": 1, "is_back_matter": false, "page_estimate": 45, "confidence": 0.95, "notes": "optional"}

Rules:
- level 1 = Part, Book, or Volume headings (top-level divisions containing chapters)
- level 2 = Chapters, Prologue, Epilogue, Introduction, Foreword, Preface, Afterword, Conclusion, Appendix
- level 3 = Sub-sections within a chapter (only include if clearly structured)
- Most books have 0-5 level-1 entries and 5-30 level-2 entries
- A book with 10 chapters should have >= 10 level-2 entries
- If the book has no Parts/Volumes, use level 2 for all chapter headings (no level 1)
- Preserve exact capitalization and numbering from the source
- If font candidates are provided below, use them as the primary guide and ADD any chapters you find in the text that the font analysis missed
- If no font candidates are provided, identify headings from the text samples only
- Mark back matter sections (Notes, Bibliography, Index, Appendix) with is_back_matter: true
"@

    $userContent = ""
    if ($fontCandidatesSection) {
        $userContent += "$fontCandidatesSection`n`n"
    }
    $userContent += "TEXT SAMPLES:`n`n$sample"

    Write-EbookLog "Chapter detection: sending to Claude API..."
    $raw = Send-ToClaudeAPI -SystemPrompt $systemPrompt -UserMessage $userContent

    if ($null -eq $raw) {
        Write-EbookLog 'Chapter detection: API call failed -- returning null' -Level ERROR
        return $null
    }

    # -- Step 4: Parse JSON response
    $json = $raw -replace '(?s)^```(?:json)?\s*', '' -replace '\s*```\s*$', ''
    $json = $json.Trim()

    try {
        $chapters = $json | ConvertFrom-Json
        Write-EbookLog "Chapter detection: found $($chapters.Count) heading(s)" -Level SUCCESS
        return $chapters
    } catch {
        Write-EbookLog "Chapter detection: failed to parse JSON response -- $_" -Level ERROR
        Write-EbookLog "Chapter detection: raw response was: $($json.Substring(0, [Math]::Min(200, $json.Length)))" -Level ERROR
        return $null
    }
}
```

- [ ] **Step 2: Verify the module loads without errors**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psd1 -Force; Get-Command Get-ChapterStructure | Format-List"`
Expected: Shows the function with both `TextContent` and `InputFile` parameters

- [ ] **Step 3: Commit**

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: rewrite Get-ChapterStructure — three-zone sampling + font integration"
```

---

## Task 9: Convert-ToKindle — Pass InputFile + EPUB Chapter Detection Block

**Files:**
- Modify: `module/EbookAutomation.psm1` — three locations

**Critical architecture note:** The existing Claude chapter detection (lines 820-935) is inside the `if ($ext -eq 'pdf')` block (line 723). EPUBs never reach this code. For EPUB chapter detection, we need a NEW block placed AFTER the EPUB extraction block (after line ~1016), where `$convertInput` points to the extracted HTML file.

- [ ] **Step 1: Pass InputFile to existing PDF Get-ChapterStructure calls**

At line 864, change:
```powershell
$chapters = Get-ChapterStructure -TextContent $combinedText
```
to:
```powershell
$chapters = Get-ChapterStructure -TextContent $combinedText -InputFile $InputFile
```

At line 868, change:
```powershell
$chapters = Get-ChapterStructure -TextContent $cleanedText
```
to:
```powershell
$chapters = Get-ChapterStructure -TextContent $cleanedText -InputFile $InputFile
```

- [ ] **Step 2: Add EPUB chapter detection block after EPUB extraction**

Find the end of the EPUB extraction block (around line 1016, after `if ($ext -eq 'epub' -and -not $DirectConversion) { ... }`). Add a new block AFTER it:

```powershell
    # EPUB chapter detection: run after EPUB HTML extraction when $convertInput is the extracted HTML
    if ($ext -eq 'epub' -and ($UseClaudeChapters -or $ChapterHintsFile) -and $convertInput -and (Test-Path $convertInput) -and $convertInput -like '*.html') {
        $cfg    = Get-EbookConfig
        $python = $cfg.paths.python

        # Early-exit: skip Claude if HTML already has sufficient chapter headings
        $epubHtml = Get-Content $convertInput -Raw -Encoding UTF8
        $existingH1 = [regex]::Matches($epubHtml, '(?s)<h1[^>]*>(.+?)</h1>')
        $backMatterKeywords = @('Notes','Bibliography','Index','Appendix','Glossary',
                                'References','Further Reading','Works Cited')
        $nonBackMatter = @($existingH1 | Where-Object {
            $text = $_.Groups[1].Value
            $isBM = $false
            foreach ($kw in $backMatterKeywords) {
                if ($text -match "^$kw$") { $isBM = $true; break }
            }
            -not $isBM
        })

        if ($nonBackMatter.Count -ge 5) {
            Write-EbookLog "Kindle: EPUB has $($nonBackMatter.Count) non-back-matter h1 headings -- skipping Claude chapter detection"
        } else {
            Write-EbookLog "Kindle: EPUB needs chapter detection ($($nonBackMatter.Count) non-back-matter h1 found)..."
            $epubText = Get-Content $convertInput -Raw -Encoding UTF8
            $chapters = Get-ChapterStructure -TextContent $epubText -InputFile $InputFile

            if ($chapters -and $chapters.Count -gt 0) {
                # Per-heading insertion (same logic as Task 10 for PDF HTML path)
                $htmlContent = Get-Content $convertInput -Raw -Encoding UTF8
                $insertedCount = 0
                $skippedCount  = 0

                foreach ($ch in $chapters) {
                    $title = $ch.title.Trim()
                    $level = $ch.level
                    $tag   = switch ($level) {
                        1 { 'h1' }
                        2 { 'h2' }
                        3 { 'h3' }
                        default { 'h2' }
                    }

                    $escapedTitle = [regex]::Escape($title)
                    if ($htmlContent -match "<h[123][^>]*>\s*$escapedTitle\s*</h[123]>") {
                        $skippedCount++
                        continue
                    }

                    # First-match-only replacement using [regex]::Replace with count=1
                    $pattern = "(<(?:p|div)[^>]*>)\s*$escapedTitle\s*(</(?:p|div)>)"
                    $rx = [regex]::new($pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
                    if ($rx.IsMatch($htmlContent)) {
                        $htmlContent = $rx.Replace($htmlContent, "<$tag>$title</$tag>", 1)
                        $insertedCount++
                        continue
                    }

                    # Fuzzy match: first 5+ words
                    $words = $title -split '\s+'
                    if ($words.Count -ge 5) {
                        $fuzzyPrefix = [regex]::Escape(($words[0..4]) -join ' ')
                        $fuzzyPattern = "(<(?:p|div)[^>]*>)\s*($fuzzyPrefix[^<]*)\s*(</(?:p|div)>)"
                        $rxFuzzy = [regex]::new($fuzzyPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
                        if ($rxFuzzy.IsMatch($htmlContent)) {
                            $htmlContent = $rxFuzzy.Replace($htmlContent, "<$tag>$title</$tag>", 1)
                            $insertedCount++
                            continue
                        }
                    }

                    Write-EbookLog "Kindle: heading not found in HTML: `"$title`"" -Level WARN
                }

                if ($insertedCount -gt 0) {
                    Set-Content $convertInput -Value $htmlContent -Encoding UTF8
                    Write-EbookLog "Kindle: inserted $insertedCount heading(s), skipped $skippedCount already present" -Level SUCCESS
                } else {
                    Write-EbookLog "Kindle: all $($chapters.Count) headings already present in EPUB HTML"
                }
            } else {
                Write-EbookLog 'Kindle: Claude returned no chapters for EPUB -- keeping extracted HTML' -Level WARN
            }
        }
    }
```

- [ ] **Step 3: Verify module still loads**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psd1 -Force; Write-Host 'OK'"`
Expected: `OK` with no errors

- [ ] **Step 4: Commit**

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: EPUB chapter detection block + pass InputFile to Get-ChapterStructure"
```

---

## Task 10: Convert-ToKindle — Per-Heading HTML Insertion

**Files:**
- Modify: `module/EbookAutomation.psm1:871-897` — replace all-or-nothing check with per-heading insertion

Currently, the code checks if ALL Claude headings are present and skips pass 2 if so. Replace with per-heading HTML insertion for the HTML output path.

- [ ] **Step 1: Replace the all-or-nothing heading check**

Find the block at lines 871-900 (starting with `if ($chapters -and $chapters.Count -gt 0)`). Replace the entire block with:

```powershell
                    if ($chapters -and $chapters.Count -gt 0) {
                        # Per-heading insertion for HTML output
                        if ($convertInput -like '*.html') {
                            $htmlContent = Get-Content $convertInput -Raw -Encoding UTF8
                            $insertedCount = 0
                            $skippedCount  = 0

                            foreach ($ch in $chapters) {
                                $title = $ch.title.Trim()
                                $level = $ch.level
                                $tag   = switch ($level) {
                                    1 { 'h1' }
                                    2 { 'h2' }
                                    3 { 'h3' }
                                    default { 'h2' }
                                }

                                # Check if heading already exists as h1/h2/h3
                                $escapedTitle = [regex]::Escape($title)
                                if ($htmlContent -match "<h[123][^>]*>\s*$escapedTitle\s*</h[123]>") {
                                    $skippedCount++
                                    continue
                                }

                                # Try exact match in <p> or <div> — first match only
                                $pattern = "(<(?:p|div)[^>]*>)\s*$escapedTitle\s*(</(?:p|div)>)"
                                $rx = [regex]::new($pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
                                if ($rx.IsMatch($htmlContent)) {
                                    $htmlContent = $rx.Replace($htmlContent, "<$tag>$title</$tag>", 1)
                                    $insertedCount++
                                    continue
                                }

                                # Fuzzy match: first 5+ words — first match only
                                $words = $title -split '\s+'
                                if ($words.Count -ge 5) {
                                    $fuzzyPrefix = [regex]::Escape(($words[0..4]) -join ' ')
                                    $fuzzyPattern = "(<(?:p|div)[^>]*>)\s*($fuzzyPrefix[^<]*)\s*(</(?:p|div)>)"
                                    $rxFuzzy = [regex]::new($fuzzyPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
                                    if ($rxFuzzy.IsMatch($htmlContent)) {
                                        $htmlContent = $rxFuzzy.Replace($htmlContent, "<$tag>$title</$tag>", 1)
                                        $insertedCount++
                                        continue
                                    }
                                }

                                Write-EbookLog "Kindle: heading not found in HTML: `"$title`"" -Level WARN
                            }

                            if ($insertedCount -gt 0) {
                                Set-Content $convertInput -Value $htmlContent -Encoding UTF8
                                Write-EbookLog "Kindle: inserted $insertedCount heading(s), skipped $skippedCount already present" -Level SUCCESS
                            } else {
                                Write-EbookLog "Kindle: all $($chapters.Count) headings already present in HTML"
                            }
                        }
                        else {
                            # TXT output: use existing hints JSON path for pass 2 re-extraction
                            if (-not $cleanedText) { $cleanedText = Get-Content $convertInput -Raw -Encoding UTF8 }
                            $cleanedUpper = ($cleanedText -split "`r?`n" | ForEach-Object { $_.Trim().ToUpper() }) -join "`n"
                            $missingCount = 0
                            foreach ($ch in $chapters) {
                                $titleUpper = $ch.title.Trim().ToUpper()
                                if ($cleanedUpper -notmatch [regex]::Escape($titleUpper)) {
                                    $missingCount++
                                }
                            }

                            if ($missingCount -gt 0) {
                                $hintsJson = Join-Path $env:TEMP ('kindle_hints_{0}.json' -f [System.IO.Path]::GetRandomFileName())
                                $chapters | ConvertTo-Json -Depth 3 | Set-Content $hintsJson -Encoding UTF8
                                Write-EbookLog "Kindle: $missingCount of $($chapters.Count) headings missing -- writing hints for pass 2"
                            } else {
                                Write-EbookLog "Kindle: all $($chapters.Count) Claude chapters already present -- no re-run needed"
                            }
                        }
                    } else {
                        Write-EbookLog 'Kindle: Claude returned no chapters -- keeping pass 1 output' -Level WARN
                    }
```

- [ ] **Step 2: Verify module loads and function signatures intact**

Run: `powershell -Command "Import-Module .\module\EbookAutomation.psd1 -Force; Write-Host 'OK'"`
Expected: `OK` with no errors

- [ ] **Step 3: Commit**

```bash
git add module/EbookAutomation.psm1
git commit -m "feat: per-heading HTML insertion replacing all-or-nothing check"
```

---

## Task 11: Regression Testing

**Files:**
- No files modified — testing only

Run the full test suite to verify no regressions in the existing 5-book pipeline.

- [ ] **Step 1: Run the font detector on available test books**

Run each test PDF through the detector:
```
python tools/detect_headings_font.py --input "<path-to-test-book>" --format text
```

For each of the test books that are PDFs, verify:
- JSON output is valid
- Body font detected correctly
- Heading candidates look reasonable (not all noise)
- No crashes or error JSON

- [ ] **Step 2: Run the full pipeline regression**

Run: `python tools/test_pipeline.py`
Expected: All 5 test books pass. No regressions in heading count, footnote links, etc.

**If any test fails:** Stop and diagnose before proceeding. Check:
- Did the `Get-ChapterStructure` rewrite change the heading format in a way that breaks `apply_chapter_hints()`?
- Did the EPUB early-exit incorrectly skip detection?
- Did per-heading insertion modify HTML in a way that breaks downstream parsing?

- [ ] **Step 3: Commit test results (if test_cases.json updated)**

```bash
git add tools/test_cases.json
git commit -m "test: update baselines after chapter detection rewrite"
```

---

## Task 12: Manual Validation on Target Books

**Files:**
- No files modified — validation only

Test the specific books that motivated this feature.

- [ ] **Step 1: Validate Burge (the original failure case)**

Run:
```
python tools/detect_headings_font.py --input "F:\Books\Bible Study\Burge, Gary M. - Jesus and the Land*.pdf" --verbose --format text
```

Verify: Output shows numbered chapter headings (not just "Notes" / "Further Reading"). Look for chapters like "1 Promised land in the Old Testament", "4 The Fourth Gospel and the land", etc.

- [ ] **Step 2: Validate Fruchtenbaum (scanned OCR PDF)**

Run:
```
python tools/detect_headings_font.py --input "F:\Books\Bible Study\Fruchtenbaum*.pdf" --verbose --format text
```

Verify: Despite being OCR, font metrics still detect heading structure.

- [ ] **Step 3: Validate Wright EPUB**

Run:
```
python tools/detect_headings_font.py --input "C:\Users\Joe\Downloads\Jesus Victory of God V2*.epub" --format text
```

Verify: NCX TOC entries extracted as primary candidates with Parts and Chapters.

- [ ] **Step 4: Document results**

Record which books passed/failed and any adjustments needed. If all pass, the feature is complete.

---

## Summary

| Task | Component | What It Does |
|---|---|---|
| 1 | `detect_headings_font.py` | CLI scaffold, glob, error handling |
| 2 | `detect_headings_font.py` | PDF font profile + body font detection |
| 3 | `detect_headings_font.py` | PDF heading candidate identification |
| 4 | `detect_headings_font.py` | PDF noise filtering |
| 5 | `detect_headings_font.py` | Level assignment + confidence scoring |
| 6 | `detect_headings_font.py` | EPUB NCX/nav extraction |
| 7 | `detect_headings_font.py` | EPUB HTML heading detection + dedup |
| 8 | `EbookAutomation.psm1` | Get-ChapterStructure rewrite |
| 9 | `EbookAutomation.psm1` | EPUB early-exit + InputFile param |
| 10 | `EbookAutomation.psm1` | Per-heading HTML insertion |
| 11 | Testing | Regression suite |
| 12 | Testing | Manual validation on target books |
