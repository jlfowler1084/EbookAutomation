#!/usr/bin/env python3
"""
Font-Based Heading Detection Tool

Scans PDFs via PyMuPDF (fitz) to identify chapter headings by analysing
font size, weight, and position.  Outputs structured JSON (or human-readable
text) for integration with the EbookAutomation PowerShell pipeline.

Usage:
    python detect_headings_font.py --input book.pdf
    python detect_headings_font.py --input "books/*.pdf" --format text --verbose
    python detect_headings_font.py --input book.epub --epub

Requirements: pymupdf (fitz)
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ── Windows UTF-8 stdout/stderr reconfiguration ────────────────────────
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ========================================================================
#  Constants
# ========================================================================

# Font flag bit masks (fitz span flags)
FLAG_BOLD = 1 << 4       # 16
FLAG_ITALIC = 1 << 1     # 2

# Heading candidate filters
MIN_BLOCK_CHARS = 3
MAX_BLOCK_CHARS = 120

# Chapter-pattern regexes (compiled once)
CHAPTER_PATTERNS = [
    re.compile(r"^(Chapter|CHAPTER|Part|PART)\s+\d+", re.IGNORECASE),
    re.compile(r"^\d+\.\s+\w"),
    re.compile(r"^\d+\s+[A-Z]"),
    re.compile(r"^[IVXLC]+\.\s+\w"),
    re.compile(
        r"^(Introduction|Conclusion|Preface|Foreword|Epilogue|Prologue|Appendix)\b",
        re.IGNORECASE,
    ),
]

# Running header / page number filters
PAGE_NUMBER_RE = re.compile(r"^[ivxlcdm]+$|^\d{1,4}$", re.IGNORECASE)


# ========================================================================
#  Utility helpers
# ========================================================================

def _round_half(val: float) -> float:
    """Round a float to the nearest 0.5."""
    return round(val * 2) / 2


def _normalize(text: str) -> str:
    """Collapse whitespace and strip for comparison."""
    return re.sub(r"\s+", " ", text).strip()


def _is_centered(block_x0: float, block_x1: float, page_width: float,
                 tolerance: float = 0.15) -> bool:
    """Heuristic: a block is centered if its horizontal midpoint is near
    the page midpoint and it doesn't span the full width."""
    if page_width <= 0:
        return False
    block_mid = (block_x0 + block_x1) / 2
    page_mid = page_width / 2
    block_width = block_x1 - block_x0
    # Must not be a full-width paragraph
    if block_width / page_width > 0.75:
        return False
    return abs(block_mid - page_mid) / page_width < tolerance


def _word_count(text: str) -> int:
    return len(text.split())


def _matches_chapter_pattern(text: str) -> str | None:
    """Return the name of the matching chapter pattern, or None."""
    stripped = text.strip()
    for pat in CHAPTER_PATTERNS:
        if pat.search(stripped):
            # Derive a short label from the pattern
            if "Chapter|CHAPTER|Part|PART" in pat.pattern:
                return "chapter_part_keyword"
            if r"^\d+\.\s" in pat.pattern:
                return "numbered_dot_chapter"
            if r"^\d+\s+[A-Z]" in pat.pattern:
                return "numbered_chapter"
            if "IVXLC" in pat.pattern:
                return "roman_numeral_chapter"
            if "Introduction|Conclusion" in pat.pattern:
                return "section_keyword"
    return None


# ========================================================================
#  PDF font profile scanning  (Task 2)
# ========================================================================

def scan_font_profile(doc, verbose_log=None):
    """Iterate every page and build a character-count-weighted font histogram.

    Returns:
        body_font_size  (float)   – most common size by char count
        body_font_name  (str)     – font name at body size
        font_histogram  (dict)    – {size_str: char_count}
        page_blocks     (list)    – per-page list of extracted block dicts
        pages_scanned   (int)
        total_pages     (int)
    """
    total_pages = len(doc)
    # Skip first 2 pages (cover/title) unless very short document
    skip = 2 if total_pages > 3 else 0

    # char_counts: size -> total char count
    char_counts: Counter = Counter()
    # font_at_size: size -> Counter of font_name -> char_count (to pick body font name)
    font_at_size: dict[float, Counter] = defaultdict(Counter)

    page_blocks: list[list[dict]] = []  # indexed by page number (0-based)

    for page_idx in range(total_pages):
        page = doc[page_idx]
        page_width = page.rect.width
        page_height = page.rect.height
        text_dict = page.get_text("dict")

        blocks_on_page = []

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # skip image blocks
                continue

            # Collect spans to determine dominant font metrics for this block
            block_text_parts = []
            span_infos = []

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "")
                    if not txt.strip():
                        continue
                    font_name = span.get("font", "unknown")
                    font_size = _round_half(span.get("size", 0))
                    flags = span.get("flags", 0)
                    is_bold = bool(flags & FLAG_BOLD)
                    is_italic = bool(flags & FLAG_ITALIC)

                    char_count = len(txt)
                    span_infos.append({
                        "font_name": font_name,
                        "font_size": font_size,
                        "is_bold": is_bold,
                        "is_italic": is_italic,
                        "char_count": char_count,
                    })
                    block_text_parts.append(txt)

            if not span_infos:
                continue

            # Full block text
            full_text = _normalize(" ".join(block_text_parts))
            if not full_text:
                continue

            # Dominant span = span with most characters in this block
            dominant = max(span_infos, key=lambda s: s["char_count"])

            block_info = {
                "text": full_text,
                "page": page_idx,
                "font_name": dominant["font_name"],
                "font_size": dominant["font_size"],
                "is_bold": dominant["is_bold"],
                "is_italic": dominant["is_italic"],
                "x0": block["bbox"][0],
                "y0": block["bbox"][1],
                "x1": block["bbox"][2],
                "y1": block["bbox"][3],
                "page_width": page_width,
                "page_height": page_height,
            }
            blocks_on_page.append(block_info)

            # Accumulate into histogram (skip cover/title pages)
            if page_idx >= skip:
                total_chars = sum(s["char_count"] for s in span_infos)
                char_counts[dominant["font_size"]] += total_chars
                font_at_size[dominant["font_size"]][dominant["font_name"]] += total_chars

        page_blocks.append(blocks_on_page)

    # Determine body font
    if char_counts:
        body_size = char_counts.most_common(1)[0][0]
        body_name = font_at_size[body_size].most_common(1)[0][0]
    else:
        body_size = 0.0
        body_name = "unknown"

    font_histogram = {str(k): v for k, v in sorted(char_counts.items())}

    pages_scanned = total_pages - skip

    if verbose_log:
        verbose_log(f"Font histogram ({len(char_counts)} sizes): "
                    f"{dict(sorted(char_counts.items(), key=lambda x: -x[1]))}")
        verbose_log(f"Body font: {body_name} @ {body_size}pt")

    return body_size, body_name, font_histogram, page_blocks, pages_scanned, total_pages


# ========================================================================
#  Heading candidate identification  (Task 3)
# ========================================================================

def identify_heading_candidates(page_blocks, body_size, verbose_log=None):
    """Scan all blocks and return those that qualify as heading candidates.

    Qualification (ANY of):
      - font size >= 1.5x body size
      - bold AND font size >= 1.2x body size
      - matches a chapter pattern regex
    Exclusions:
      - text < 3 chars or > 120 chars
    """
    candidates = []

    for blocks in page_blocks:
        for blk in blocks:
            text = blk["text"]
            text_len = len(text.strip())

            if text_len < MIN_BLOCK_CHARS or text_len > MAX_BLOCK_CHARS:
                continue

            size = blk["font_size"]
            is_bold = blk["is_bold"]
            signals = []

            # Size ratio
            size_ratio = size / body_size if body_size > 0 else 0
            qualifies = False

            if size_ratio >= 1.5:
                qualifies = True
                signals.append(f"font_size_ratio:{size_ratio:.2f}")
            if is_bold and size_ratio >= 1.2:
                qualifies = True
                if is_bold:
                    signals.append("bold")
                if size_ratio >= 1.2:
                    signals.append(f"font_size_ratio:{size_ratio:.2f}")
            if is_bold and "bold" not in signals:
                # Record bold even if it wasn't the qualifying condition
                pass

            chapter_match = _matches_chapter_pattern(text)
            if chapter_match:
                qualifies = True
                signals.append(chapter_match)

            if not qualifies:
                continue

            # De-duplicate signals
            signals = list(dict.fromkeys(signals))

            # Add bold signal if bold but not yet recorded
            if is_bold and "bold" not in signals:
                signals.append("bold")

            candidates.append({
                "text": text,
                "page": blk["page"],
                "font_size": size,
                "font_name": blk["font_name"],
                "is_bold": is_bold,
                "x0": blk["x0"],
                "y0": blk["y0"],
                "x1": blk["x1"],
                "page_width": blk["page_width"],
                "detection_signals": signals,
            })

    if verbose_log:
        verbose_log(f"Raw heading candidates: {len(candidates)}")

    return candidates


# ========================================================================
#  Noise filtering  (Task 4)
# ========================================================================

def filter_noise(candidates, page_blocks, total_pages, verbose_log=None):
    """Remove headers, footers, page numbers, and running headers.

    Filters:
      1. Headers/footers: same normalised text at same y-coord (+-5pt) on >50% of pages
      2. Page numbers: purely numeric or short Roman numerals
      3. Running headers: all-caps text <=5 words on >30% of pages
    """
    # --- Build frequency maps from ALL blocks (not just candidates) ---
    # Map: (normalised_text, rounded_y) -> set of page numbers
    text_y_pages: dict[tuple[str, float], set[int]] = defaultdict(set)
    # Map: normalised_text -> set of page numbers (for running-header detection)
    text_pages: dict[str, set[int]] = defaultdict(set)

    for blocks in page_blocks:
        for blk in blocks:
            norm = _normalize(blk["text"]).lower()
            rounded_y = round(blk["y0"] / 5) * 5  # round to nearest 5pt
            text_y_pages[(norm, rounded_y)].add(blk["page"])
            text_pages[norm].add(blk["page"])

    # Pre-compute sets for fast lookup
    header_footer_texts = set()
    for (norm, ry), pages_set in text_y_pages.items():
        if len(pages_set) > total_pages * 0.5:
            header_footer_texts.add(norm)

    running_header_texts = set()
    for norm, pages_set in text_pages.items():
        words = norm.split()
        if (len(words) <= 5
                and norm == norm.upper()      # all-caps check (on lowered text is always true, so re-check original)
                and len(pages_set) > total_pages * 0.3):
            running_header_texts.add(norm)

    # We need original-case all-caps check; rebuild with original case
    running_header_texts_orig: set[str] = set()
    text_pages_orig: dict[str, set[int]] = defaultdict(set)
    for blocks in page_blocks:
        for blk in blocks:
            norm_orig = _normalize(blk["text"])
            text_pages_orig[norm_orig].add(blk["page"])

    for norm_orig, pages_set in text_pages_orig.items():
        words = norm_orig.split()
        if (len(words) <= 5
                and norm_orig == norm_orig.upper()
                and len(pages_set) > total_pages * 0.3):
            running_header_texts_orig.add(_normalize(norm_orig).lower())

    filtered = []
    removed_count = 0

    for cand in candidates:
        text = cand["text"]
        norm = _normalize(text).lower()
        rounded_y = round(cand["y0"] / 5) * 5

        # Filter 1: header/footer (repeated at same position)
        if norm in header_footer_texts:
            # Double-check y-position frequency
            if len(text_y_pages.get((norm, rounded_y), set())) > total_pages * 0.5:
                if verbose_log:
                    verbose_log(f"  Filtered (header/footer): \"{text}\"")
                removed_count += 1
                continue

        # Filter 2: page numbers
        stripped = text.strip()
        if PAGE_NUMBER_RE.fullmatch(stripped):
            if verbose_log:
                verbose_log(f"  Filtered (page number): \"{text}\"")
            removed_count += 1
            continue

        # Filter 3: running headers (all-caps, <=5 words, on >30% pages)
        if norm in running_header_texts_orig:
            if verbose_log:
                verbose_log(f"  Filtered (running header): \"{text}\"")
            removed_count += 1
            continue

        filtered.append(cand)

    if verbose_log:
        verbose_log(f"Noise filtering removed {removed_count} candidates, {len(filtered)} remain")

    return filtered


# ========================================================================
#  Level assignment + confidence scoring  (Task 5)
# ========================================================================

def assign_levels_and_confidence(candidates, body_size, verbose_log=None):
    """Assign heading levels (h1/h2/h3) and confidence scores.

    Level rules:
      h1 = largest font size OR Chapter/Part pattern
      h2 = second-largest size OR bold at body+2pt
      h3 = third-largest or bold at body size

    Confidence:
      base 0.30
      +0.30 if size >= 1.5x body
      +0.20 if bold
      +0.30 if chapter pattern match
      +0.10 if centered
      +0.10 if short text (<= 10 words)
      cap at 0.99
    """
    if not candidates:
        return candidates

    # Collect distinct sizes among candidates
    distinct_sizes = sorted(set(c["font_size"] for c in candidates), reverse=True)

    largest = distinct_sizes[0] if len(distinct_sizes) >= 1 else None
    second = distinct_sizes[1] if len(distinct_sizes) >= 2 else None
    third = distinct_sizes[2] if len(distinct_sizes) >= 3 else None

    result = []

    for cand in candidates:
        size = cand["font_size"]
        is_bold = cand["is_bold"]
        signals = cand["detection_signals"]
        text = cand["text"]

        # --- Level assignment ---
        has_chapter_pattern = any(
            s in ("chapter_part_keyword", "numbered_dot_chapter",
                  "numbered_chapter", "roman_numeral_chapter", "section_keyword")
            for s in signals
        )

        if size == largest or has_chapter_pattern:
            level = "h1"
        elif size == second or (is_bold and body_size > 0 and abs(size - (body_size + 2)) < 0.6):
            level = "h2"
        elif size == third or (is_bold and body_size > 0 and abs(size - body_size) < 0.6):
            level = "h3"
        else:
            level = "h2"  # fallback

        # --- Confidence scoring ---
        conf = 0.30
        size_ratio = size / body_size if body_size > 0 else 0

        if size_ratio >= 1.5:
            conf += 0.30
        if is_bold:
            conf += 0.20
        if has_chapter_pattern:
            conf += 0.30
        if _is_centered(cand["x0"], cand["x1"], cand["page_width"]):
            conf += 0.10
            if "centered" not in signals:
                signals.append("centered")
        if _word_count(text) <= 10:
            conf += 0.10
            if "short_text" not in signals:
                signals.append("short_text")

        conf = min(conf, 0.99)
        conf = round(conf, 2)

        result.append({
            "text": text,
            "page": cand["page"] + 1,  # 1-based page number for output
            "level": level,
            "font_size": size,
            "font_name": cand["font_name"],
            "is_bold": is_bold,
            "confidence": conf,
            "detection_signals": signals,
            "_y0": cand["y0"],  # kept for sorting, stripped before output
        })

    # Sort by page then y-position
    result.sort(key=lambda c: (c["page"], c["_y0"]))

    if verbose_log:
        level_counts = Counter(c["level"] for c in result)
        verbose_log(f"Level assignment: {dict(level_counts)}")

    return result


# ========================================================================
#  EPUB heading detection  (Tasks 6-7)
# ========================================================================

def detect_headings_epub(epub_path, verbose_log=None):
    """Detect headings in an EPUB by combining NCX/nav TOC data with HTML
    heading-tag analysis.

    Returns a result dict matching the JSON output schema used by the PDF path.
    The 'page' field for EPUB candidates represents the spine index (0-based
    reading order position), mapped to 1-based in the final output.
    """
    try:
        from ebooklib import epub
        from bs4 import BeautifulSoup  # noqa: F401 — used in sub-functions
    except ImportError:
        return {
            "error": "ebooklib and/or beautifulsoup4 not installed. "
                     "Run: python -m pip install ebooklib beautifulsoup4"
        }

    epub_path = str(epub_path)

    if verbose_log:
        verbose_log(f"Opening EPUB: {epub_path}")

    try:
        book = epub.read_epub(epub_path, options={"ignore_ncx": False})
    except Exception as exc:
        return {"error": f"Failed to open EPUB: {exc}"}

    # Build spine item list and index map (item_id/href -> spine position)
    spine_items = []
    spine_index: dict[str, int] = {}  # href (filename only) -> index

    for idx, item in enumerate(book.spine):
        item_id = item[0] if isinstance(item, tuple) else item
        spine_items.append(item_id)
        # Resolve href from item id
        doc_item = book.get_item_with_id(item_id)
        if doc_item is not None:
            href = doc_item.get_name()
            # Store both full path and basename for flexible lookup
            spine_index[href] = idx
            basename = href.rsplit("/", 1)[-1] if "/" in href else href
            if basename not in spine_index:
                spine_index[basename] = idx
            # Also map by item id
            spine_index[item_id] = idx

    total_pages = len(spine_items)

    if verbose_log:
        verbose_log(f"Spine items: {total_pages}")

    # Task 6: Extract NCX/nav candidates
    ncx_candidates = _extract_ncx_candidates(book, spine_index, verbose_log)

    # Task 7: Extract HTML heading candidates from spine documents
    html_candidates = _extract_html_heading_candidates(
        book, spine_items, spine_index, verbose_log
    )

    # Dedup HTML candidates against NCX entries
    html_unique = _dedup_against_ncx(html_candidates, ncx_candidates, verbose_log)

    # Merge: NCX candidates first (higher trust), then unique HTML candidates
    all_candidates = list(ncx_candidates) + list(html_unique)

    # Sort by (page, confidence descending) — so within same page, highest
    # confidence comes first
    all_candidates.sort(key=lambda c: (c["page"], -c["confidence"]))

    # Convert page to 1-based for output
    for c in all_candidates:
        c["page"] = c["page"] + 1

    if verbose_log:
        verbose_log(f"Total EPUB heading candidates: {len(all_candidates)}")

    return {
        "file": epub_path,
        "format": "epub",
        "body_font_size": None,
        "body_font_name": None,
        "total_pages": total_pages,
        "pages_scanned": total_pages,
        "heading_candidates": all_candidates,
        "font_histogram": {},
    }


def _normalize_for_dedup(text: str) -> str:
    """Normalize text for dedup comparison: strip leading numbering,
    lowercase, collapse whitespace."""
    # Strip leading chapter/part numbering like "Chapter 1:", "1.", "IV.", "PART TWO"
    stripped = re.sub(
        r"^(chapter|part|section)\s+[\divxlc]+[.:)]*\s*",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    stripped = re.sub(r"^\d+[.:)]\s*", "", stripped)
    stripped = re.sub(r"^[IVXLC]+[.:)]\s*", "", stripped)
    return re.sub(r"\s+", " ", stripped).strip().lower()


def _extract_ncx_candidates(book, spine_index, verbose_log=None):
    """Extract heading candidates from the EPUB's NCX/nav table of contents.

    Walks ``book.toc`` recursively.  ebooklib returns a list where each
    element is either:
      - an ``epub.Link`` object  (leaf entry)
      - a ``(Section, [children])`` tuple  (nested group)

    Returns a list of candidate dicts (0-based page index).
    """
    from ebooklib import epub

    candidates: list[dict] = []

    def _walk_toc(entries, depth=0):
        for entry in entries:
            if isinstance(entry, tuple) and len(entry) == 2:
                # (Section, [children]) — Section has title attribute
                section, children = entry
                title = getattr(section, "title", None) or str(section)
                title = _normalize(title)
                href = getattr(section, "href", "") or ""

                if title and MIN_BLOCK_CHARS <= len(title) <= MAX_BLOCK_CHARS:
                    page = _resolve_spine_page(href, spine_index)
                    level = _depth_to_level(depth)
                    candidates.append({
                        "text": title,
                        "page": page,
                        "level": level,
                        "font_size": None,
                        "font_name": None,
                        "is_bold": False,
                        "confidence": 0.95,
                        "detection_signals": ["ncx_toc"],
                    })

                # Recurse into children
                if children:
                    _walk_toc(children, depth + 1)

            elif isinstance(entry, epub.Link):
                title = _normalize(entry.title or "")
                href = entry.href or ""

                if title and MIN_BLOCK_CHARS <= len(title) <= MAX_BLOCK_CHARS:
                    page = _resolve_spine_page(href, spine_index)
                    level = _depth_to_level(depth)
                    candidates.append({
                        "text": title,
                        "page": page,
                        "level": level,
                        "font_size": None,
                        "font_name": None,
                        "is_bold": False,
                        "confidence": 0.95,
                        "detection_signals": ["ncx_toc"],
                    })

    def _resolve_spine_page(href: str, spine_idx: dict) -> int:
        """Map a TOC href to a spine index.  Returns 0 if not found."""
        if not href:
            return 0
        # Strip fragment (#section-id)
        base_href = href.split("#")[0]
        # Try full path, then basename
        if base_href in spine_idx:
            return spine_idx[base_href]
        basename = base_href.rsplit("/", 1)[-1] if "/" in base_href else base_href
        if basename in spine_idx:
            return spine_idx[basename]
        return 0

    def _depth_to_level(depth: int) -> str:
        if depth == 0:
            return "h1"
        elif depth == 1:
            return "h2"
        else:
            return "h3"

    toc = book.toc
    if not toc:
        if verbose_log:
            verbose_log("No TOC found in EPUB")
        return []

    _walk_toc(toc, depth=0)

    # Flat NCX heuristic: if ALL entries are h1 AND count > 5, they are
    # chapters (not parts) — downgrade all to h2
    if candidates:
        all_h1 = all(c["level"] == "h1" for c in candidates)
        if all_h1 and len(candidates) > 5:
            if verbose_log:
                verbose_log(
                    f"Flat NCX heuristic: {len(candidates)} h1 entries, "
                    "downgrading all to h2"
                )
            for c in candidates:
                c["level"] = "h2"

    if verbose_log:
        verbose_log(f"NCX candidates extracted: {len(candidates)}")

    return candidates


def _extract_html_heading_candidates(book, spine_items, spine_index, verbose_log=None):
    """Extract heading candidates from EPUB HTML content documents.

    Parses each spine item's HTML and looks for four layers of heading
    signals, in priority order:

    1. **Semantic headings** — ``<h1>`` through ``<h3>`` tags
    2. **Class-styled headings** — elements whose CSS class matches
       chapter/heading/title/part/section keywords
    3. **Inline-styled headings** — elements with large font-size or
       bold font-weight in a ``style`` attribute (<=15 words)
    4. **Structural patterns** — ``<div>``/``<p>`` whose text matches
       ``_matches_chapter_pattern()``

    Returns a list of candidate dicts (0-based page index).
    """
    from ebooklib import epub
    from bs4 import BeautifulSoup

    CLASS_HEADING_RE = re.compile(
        r"chapter|heading|title|part|section", re.IGNORECASE
    )
    FONT_SIZE_RE = re.compile(r"font-size\s*:\s*([\d.]+)\s*(px|pt|em|rem)", re.IGNORECASE)
    FONT_WEIGHT_RE = re.compile(r"font-weight\s*:\s*(bold|[7-9]\d\d)", re.IGNORECASE)

    candidates: list[dict] = []

    for item_id in spine_items:
        doc_item = book.get_item_with_id(item_id)
        if doc_item is None:
            continue
        # Only process HTML/XHTML documents
        if not isinstance(doc_item, epub.EpubHtml):
            continue

        content = doc_item.get_content()
        if not content:
            continue

        try:
            soup = BeautifulSoup(content, "html.parser")
        except Exception:
            continue

        # Determine spine index for this item
        href = doc_item.get_name()
        page = spine_index.get(href, 0)
        basename = href.rsplit("/", 1)[-1] if "/" in href else href
        if href not in spine_index:
            page = spine_index.get(basename, 0)

        # Track elements already captured to avoid duplicates across layers
        seen_texts: set[str] = set()  # normalized text keys
        seen_elements: set[int] = set()  # element id()s

        def _already_seen(elem, text_norm: str) -> bool:
            return id(elem) in seen_elements or text_norm in seen_texts

        def _mark_seen(elem, text_norm: str):
            seen_elements.add(id(elem))
            seen_texts.add(text_norm)

        # ── Layer 1: Semantic headings (h1/h2/h3) ───────────────────
        for tag_name in ("h1", "h2", "h3"):
            for elem in soup.find_all(tag_name):
                text = _normalize(elem.get_text())
                if not text or not (MIN_BLOCK_CHARS <= len(text) <= MAX_BLOCK_CHARS):
                    continue
                text_norm = text.lower()
                if _already_seen(elem, text_norm):
                    continue
                _mark_seen(elem, text_norm)
                candidates.append({
                    "text": text,
                    "page": page,
                    "level": tag_name,
                    "font_size": None,
                    "font_name": None,
                    "is_bold": False,
                    "confidence": 0.95,
                    "detection_signals": [f"semantic_{tag_name}"],
                })

        # ── Layer 2: Class-styled headings ───────────────────────────
        for elem in soup.find_all(attrs={"class": True}):
            classes = " ".join(elem.get("class", []))
            if not CLASS_HEADING_RE.search(classes):
                continue
            text = _normalize(elem.get_text())
            if not text or not (MIN_BLOCK_CHARS <= len(text) <= MAX_BLOCK_CHARS):
                continue
            text_norm = text.lower()
            if _already_seen(elem, text_norm):
                continue
            _mark_seen(elem, text_norm)

            # Infer level from class name
            classes_lower = classes.lower()
            if "part" in classes_lower:
                level = "h1"
            elif "chapter" in classes_lower or "title" in classes_lower:
                level = "h1"
            elif "section" in classes_lower:
                level = "h2"
            else:
                level = "h2"

            candidates.append({
                "text": text,
                "page": page,
                "level": level,
                "font_size": None,
                "font_name": None,
                "is_bold": False,
                "confidence": 0.85,
                "detection_signals": ["class_styled"],
            })

        # ── Layer 3: Inline-styled headings ──────────────────────────
        for elem in soup.find_all(attrs={"style": True}):
            style = elem.get("style", "")
            if not style:
                continue

            is_large_font = False
            is_bold_style = False

            size_match = FONT_SIZE_RE.search(style)
            if size_match:
                size_val = float(size_match.group(1))
                unit = size_match.group(2).lower()
                # Normalize to approximate pt: px*0.75, em*12, rem*12
                if unit == "px":
                    size_pt = size_val * 0.75
                elif unit in ("em", "rem"):
                    size_pt = size_val * 12
                else:
                    size_pt = size_val
                if size_pt >= 16:
                    is_large_font = True

            if FONT_WEIGHT_RE.search(style):
                is_bold_style = True

            if not (is_large_font or is_bold_style):
                continue

            text = _normalize(elem.get_text())
            if not text or not (MIN_BLOCK_CHARS <= len(text) <= MAX_BLOCK_CHARS):
                continue
            if _word_count(text) > 15:
                continue
            text_norm = text.lower()
            if _already_seen(elem, text_norm):
                continue
            _mark_seen(elem, text_norm)

            candidates.append({
                "text": text,
                "page": page,
                "level": "h2",
                "font_size": None,
                "font_name": None,
                "is_bold": is_bold_style,
                "confidence": 0.75,
                "detection_signals": ["inline_style"],
            })

        # ── Layer 4: Structural patterns (div/p matching chapter regex) ─
        for elem in soup.find_all(["div", "p"]):
            text = _normalize(elem.get_text())
            if not text or not (MIN_BLOCK_CHARS <= len(text) <= MAX_BLOCK_CHARS):
                continue
            text_norm = text.lower()
            if _already_seen(elem, text_norm):
                continue

            pattern_name = _matches_chapter_pattern(text)
            if not pattern_name:
                continue

            _mark_seen(elem, text_norm)
            candidates.append({
                "text": text,
                "page": page,
                "level": "h1",
                "font_size": None,
                "font_name": None,
                "is_bold": False,
                "confidence": 0.70,
                "detection_signals": ["structural_pattern", pattern_name],
            })

    if verbose_log:
        verbose_log(f"HTML heading candidates extracted: {len(candidates)}")

    return candidates


def _dedup_against_ncx(html_candidates, ncx_candidates, verbose_log=None):
    """Remove HTML candidates that duplicate NCX entries.

    Builds a normalized set from NCX candidate texts and filters out any
    HTML candidate whose normalized text matches.  Returns the list of
    HTML candidates that are NOT already covered by the NCX.
    """
    ncx_normalized = set()
    for c in ncx_candidates:
        ncx_normalized.add(_normalize_for_dedup(c["text"]))

    unique = []
    dup_count = 0
    for c in html_candidates:
        norm = _normalize_for_dedup(c["text"])
        if norm in ncx_normalized:
            dup_count += 1
            continue
        unique.append(c)

    if verbose_log:
        verbose_log(
            f"Dedup: {dup_count} HTML candidates matched NCX, "
            f"{len(unique)} unique HTML candidates remain"
        )

    return unique


# ========================================================================
#  Main PDF detection pipeline
# ========================================================================

def detect_headings_pdf(pdf_path, verbose=False):
    """Full detection pipeline for a single PDF file.

    Returns a result dict matching the JSON output schema.
    """
    try:
        import fitz
    except ImportError:
        return {"error": "PyMuPDF (fitz) is not installed. Run: python -m pip install pymupdf"}

    verbose_log = (lambda msg: print(msg, file=sys.stderr)) if verbose else None

    pdf_path = str(pdf_path)

    if verbose_log:
        verbose_log(f"Opening: {pdf_path}")

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        return {"error": f"Failed to open PDF: {exc}"}

    # Task 2: font profile scan
    body_size, body_name, font_histogram, page_blocks, pages_scanned, total_pages = \
        scan_font_profile(doc, verbose_log)

    # Check for empty / image-only PDF
    total_chars = sum(font_histogram.values()) if font_histogram else 0
    if total_chars == 0:
        doc.close()
        return {
            "file": pdf_path,
            "format": "pdf",
            "body_font_size": 0.0,
            "body_font_name": "unknown",
            "total_pages": total_pages,
            "pages_scanned": pages_scanned,
            "heading_candidates": [],
            "font_histogram": {},
            "warning": "PDF contains no extractable text (scanned/image-only?).",
        }

    # Task 3: identify candidates
    candidates = identify_heading_candidates(page_blocks, body_size, verbose_log)

    # Task 4: noise filtering
    candidates = filter_noise(candidates, page_blocks, total_pages, verbose_log)

    # Task 5: level + confidence
    candidates = assign_levels_and_confidence(candidates, body_size, verbose_log)

    # Strip internal _y0 field from output
    for c in candidates:
        c.pop("_y0", None)

    doc.close()

    return {
        "file": pdf_path,
        "format": "pdf",
        "body_font_size": body_size,
        "body_font_name": body_name,
        "total_pages": total_pages,
        "pages_scanned": pages_scanned,
        "heading_candidates": candidates,
        "font_histogram": font_histogram,
    }


# ========================================================================
#  Text output formatter
# ========================================================================

def format_text_output(result: dict) -> str:
    """Render the result dict as human-readable text."""
    lines = []

    if "error" in result:
        lines.append(f"ERROR: {result['error']}")
        return "\n".join(lines)

    filename = Path(result.get("file", "unknown")).name
    lines.append(f"Font Analysis: {filename}")
    lines.append(
        f"Body font: {result['body_font_name']} @ {result['body_font_size']}pt "
        f"({sum(result.get('font_histogram', {}).values())} chars)"
    )
    lines.append(
        f"Pages scanned: {result['pages_scanned']} of {result['total_pages']}"
    )

    if result.get("warning"):
        lines.append(f"WARNING: {result['warning']}")

    candidates = result.get("heading_candidates", [])
    lines.append(f"\nHeading Candidates ({len(candidates)} found):")

    if not candidates:
        lines.append("  (none)")
    else:
        for c in candidates:
            bold_str = " bold" if c["is_bold"] else ""
            lines.append(
                f"  {c['level']:3s}  p.{c['page']:<4d} [{c['confidence']:.2f}] "
                f"\"{c['text']}\" ({c['font_size']}pt{bold_str})"
            )

    return "\n".join(lines)


# ========================================================================
#  CLI entry point
# ========================================================================

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Detect chapter headings in PDFs/EPUBs by font analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python detect_headings_font.py --input book.pdf\n"
            "  python detect_headings_font.py --input \"books/*.pdf\" --format text\n"
            "  python detect_headings_font.py --input book.epub --epub --verbose\n"
        ),
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to PDF/EPUB file (supports glob patterns, e.g. \"books/*.pdf\")",
    )
    parser.add_argument(
        "--epub", action="store_true", default=False,
        help="Force EPUB processing mode (auto-detected from .epub extension)",
    )
    parser.add_argument(
        "--format", choices=["json", "text"], default="json",
        help="Output format: json (default, PowerShell-parseable) or text",
    )
    parser.add_argument(
        "--verbose", action="store_true", default=False,
        help="Print diagnostic info to stderr",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    verbose_log = (lambda msg: print(msg, file=sys.stderr)) if args.verbose else None

    # Resolve glob
    matches = glob.glob(args.input)
    if not matches:
        error_result = {"error": f"No files matched: {args.input}"}
        print(json.dumps(error_result, indent=2))
        sys.exit(1)

    input_path = Path(matches[0])

    if len(matches) > 1 and verbose_log:
        verbose_log(f"Multiple matches ({len(matches)}), processing first: {input_path}")

    if not input_path.exists():
        error_result = {"error": f"File not found: {input_path}"}
        print(json.dumps(error_result, indent=2))
        sys.exit(1)

    # Determine format
    ext = input_path.suffix.lower()
    is_epub = args.epub or ext == ".epub"

    if is_epub:
        result = detect_headings_epub(str(input_path), verbose_log)
    elif ext == ".pdf":
        result = detect_headings_pdf(str(input_path), verbose=args.verbose)
    else:
        error_result = {"error": f"Unsupported format: {ext} (supported: .pdf, .epub)"}
        print(json.dumps(error_result, indent=2))
        sys.exit(1)

    # Check for error in result
    if "error" in result:
        print(json.dumps(result, indent=2))
        sys.exit(1)

    # Output
    if args.format == "text":
        print(format_text_output(result))
    else:
        print(json.dumps(result, indent=2))

    sys.exit(0)


if __name__ == "__main__":
    main()
