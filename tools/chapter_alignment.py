"""
Chapter Alignment Verification — post-conversion tool that compares output HTML
headings against source PDF bookmarks using fuzzy matching.

Answers: "Did each chapter land in the right place with the right content following it?"

Usage:
    python tools/chapter_alignment.py --source "book.pdf" --output "book_kindle.html"
    python tools/chapter_alignment.py --source "book.pdf" --output "book_kindle.html" --threshold 0.6 --verbose
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from collections.abc import Callable
from typing import Any

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


# ═══════════════════════════════════════════════════════════════════════════
# Text normalization
# ═══════════════════════════════════════════════════════════════════════════

def _normalize_text(text):
    """Normalize text for fuzzy comparison.

    Strips HTML tags, collapses whitespace, lowercases,
    removes common artifacts (page numbers, footnote refs).
    """
    t = re.sub(r'<[^>]+>', '', text)       # strip HTML
    t = re.sub(r'\s+', ' ', t)             # collapse whitespace
    t = re.sub(r'\d{1,3}\s*$', '', t)      # trailing page numbers
    t = t.strip().lower()
    return t


# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Extract bookmarks from source PDF
# ═══════════════════════════════════════════════════════════════════════════

def _flatten_outline(outline_items, reader, bookmarks, level=0):
    """Recursively flatten pypdf's nested outline into a flat list."""
    if not outline_items:
        return
    for item in outline_items:
        if isinstance(item, list):
            # Nested sub-list = deeper level
            _flatten_outline(item, reader, bookmarks, level + 1)
        else:
            # It's a Destination object
            try:
                title = str(item.title) if hasattr(item, 'title') else str(item)
                page_num = reader.get_destination_page_number(item)
                bookmarks.append({
                    "title": title,
                    "page": page_num,
                    "level": level,
                })
            except Exception:
                # Skip bookmarks we can't resolve
                pass


def _extract_bookmarks(pdf_path, log):
    """Extract bookmarks with page numbers from source PDF.

    Returns list of dicts:
    [
        {"title": "Chapter 1: The Beginning", "page": 15, "level": 1},
        {"title": "Part Two", "page": 142, "level": 0},
        ...
    ]

    Only returns levels 0 and 1 (parts and chapters) for alignment purposes.
    """
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))

    if not reader.outline:
        log("  No bookmarks found in source PDF")
        return [], reader

    bookmarks = []
    _flatten_outline(reader.outline, reader, bookmarks, level=0)

    # Filter to levels 0 and 1 only (parts and chapters)
    top_level = [bm for bm in bookmarks if bm['level'] <= 1]
    log(f"  Extracted {len(top_level)} bookmarks (of {len(bookmarks)} total, levels 0-1)")
    return top_level, reader


# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Extract source snippets from bookmark pages
# ═══════════════════════════════════════════════════════════════════════════

def _extract_source_snippets(reader, bookmarks, log):
    """Extract text from the source PDF at each bookmark's page.

    Returns dict mapping bookmark index -> first ~200 chars of body text
    on that page (skipping the heading itself).
    """
    snippets = {}
    for i, bm in enumerate(bookmarks):
        page_num = bm['page']
        try:
            if page_num >= len(reader.pages):
                snippets[i] = ""
                continue
            raw_text = reader.pages[page_num].extract_text() or ""
            clean = _normalize_text(raw_text)
            # Try to skip past the bookmark title in the page text
            title_norm = _normalize_text(bm['title'])
            title_pos = clean.find(title_norm[:30]) if len(title_norm) >= 5 else -1
            if title_pos >= 0:
                start = title_pos + len(title_norm)
            else:
                start = min(50, len(clean))
            snippet = clean[start:start + 200].strip()
            snippets[i] = snippet
        except Exception:
            snippets[i] = ""
    return snippets


# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Parse output HTML headings + body text
# ═══════════════════════════════════════════════════════════════════════════

def _extract_output_headings(html_path, log):
    """Parse output HTML and extract headings with following body text.

    Returns list of dicts:
    [
        {
            "tag": "h2",
            "title": "Chapter 1: The Beginning",
            "body_snippet": "first 200 chars of body text after this heading...",
            "position": 1452
        },
        ...
    ]
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    headings = []
    for m in re.finditer(r'<(h[123])>(.*?)</\1>', html):
        tag = m.group(1)
        title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        position = m.start()

        # Extract body text after this heading (paragraphs until next heading)
        after = html[m.end():]
        body_parts = []
        for p_match in re.finditer(r'<p>(.*?)</p>', after):
            # Stop if we hit the next heading before this paragraph
            between = after[:p_match.start()]
            if re.search(r'<h[123]>', between):
                break
            text = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
            if text:
                body_parts.append(text)
                if sum(len(t) for t in body_parts) >= 200:
                    break
        body_snippet = ' '.join(body_parts)[:200]

        headings.append({
            "tag": tag,
            "title": title,
            "body_snippet": body_snippet,
            "position": position,
        })

    log(f"  Found {len(headings)} headings in output HTML")
    return headings


# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Match bookmarks to output headings by title similarity
# ═══════════════════════════════════════════════════════════════════════════

def _match_bookmarks_to_headings(bookmarks, output_headings, log):
    """Match each bookmark to its corresponding output heading.

    Uses title similarity (difflib.SequenceMatcher) to find the best match.
    Returns list of (bookmark_idx, heading_idx, title_similarity) tuples.
    Unmatched bookmarks get heading_idx = None.
    """
    matches = []
    used_headings = set()

    for bm_idx, bm in enumerate(bookmarks):
        bm_title = _normalize_text(bm['title'])
        best_match = None
        best_score = 0.0

        for h_idx, heading in enumerate(output_headings):
            if h_idx in used_headings:
                continue
            h_title = _normalize_text(heading['title'])
            score = SequenceMatcher(None, bm_title, h_title).ratio()
            if score > best_score:
                best_score = score
                best_match = h_idx

        # Accept match if title similarity >= 0.5
        if best_match is not None and best_score >= 0.5:
            matches.append((bm_idx, best_match, best_score))
            used_headings.add(best_match)
        else:
            matches.append((bm_idx, None, 0.0))

    matched = sum(1 for _, h, _ in matches if h is not None)
    log(f"  Matched {matched}/{len(bookmarks)} bookmarks to output headings")
    return matches


# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Compare body text snippets
# ═══════════════════════════════════════════════════════════════════════════

def _compare_body_snippets(matches, source_snippets, output_headings, threshold, log):
    """Compare body text after each matched heading.

    Returns per-chapter alignment results.
    """
    results = []
    for bm_idx, h_idx, title_score in matches:
        if h_idx is None:
            results.append({
                "bookmark_idx": bm_idx,
                "status": "unmatched",
                "title_score": 0.0,
                "body_score": 0.0,
                "combined_score": 0.0,
                "detail": "No matching heading found in output",
            })
            continue

        source_snippet = _normalize_text(source_snippets.get(bm_idx, ""))
        output_snippet = _normalize_text(output_headings[h_idx]['body_snippet'])

        if not source_snippet or not output_snippet:
            body_score = 0.0
            detail = "Insufficient text for body comparison"
        else:
            body_score = SequenceMatcher(
                None, source_snippet[:150], output_snippet[:150]
            ).ratio()
            detail = ""

        # Combined score: 40% title match + 60% body match
        combined = title_score * 0.4 + body_score * 0.6

        if combined >= threshold:
            status = "aligned"
        elif title_score >= 0.7:
            status = "title_only"  # heading found but body text doesn't match
            detail = detail or "Heading present but body text may be from wrong section"
        else:
            status = "misaligned"
            detail = detail or "Title and body text both diverge from source"

        results.append({
            "bookmark_idx": bm_idx,
            "heading_idx": h_idx,
            "status": status,
            "title_score": round(title_score, 3),
            "body_score": round(body_score, 3),
            "combined_score": round(combined, 3),
            "detail": detail,
        })

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Step 6: Generate alignment report (main entry point)
# ═══════════════════════════════════════════════════════════════════════════

def verify_chapter_alignment(source_pdf_path: str | Path, output_html_path: str | Path, threshold: float = 0.6, log: Callable[..., None] | None = None) -> dict[str, Any]:
    """Main entry point. Returns alignment report dict.

    Args:
        source_pdf_path: Path to the source PDF file.
        output_html_path: Path to the output HTML file.
        threshold: Combined score threshold for 'aligned' status (default 0.6).
        log: Logging callback. Defaults to printing to stderr.

    Returns:
        dict with alignment report including per-chapter results.
    """
    if log is None:
        log = lambda msg: print(msg, file=sys.stderr)

    source_pdf_path = Path(source_pdf_path)
    output_html_path = Path(output_html_path)

    # Guard: non-PDF source
    if source_pdf_path.suffix.lower() != '.pdf':
        return {
            "source_file": str(source_pdf_path),
            "output_file": str(output_html_path),
            "skipped": True,
            "reason": f"{source_pdf_path.suffix.upper()} — no PDF bookmarks for comparison",
            "alignment_score": None,
        }

    # Guard: files exist
    if not source_pdf_path.is_file():
        return {
            "source_file": str(source_pdf_path),
            "output_file": str(output_html_path),
            "error": f"Source PDF not found: {source_pdf_path}",
            "alignment_score": None,
        }
    if not output_html_path.is_file():
        return {
            "source_file": str(source_pdf_path),
            "output_file": str(output_html_path),
            "error": f"Output HTML not found: {output_html_path}",
            "alignment_score": None,
        }

    try:
        # Step 1: Extract bookmarks
        bookmarks, reader = _extract_bookmarks(source_pdf_path, log)

        if not bookmarks:
            return {
                "source_file": str(source_pdf_path),
                "output_file": str(output_html_path),
                "total_bookmarks": 0,
                "total_output_headings": 0,
                "alignment_score": None,
                "note": "No bookmarks found in source PDF — alignment verification not possible",
                "summary": {"aligned": 0, "title_only": 0, "misaligned": 0, "unmatched": 0},
                "threshold": threshold,
                "chapters": [],
            }

        # Step 2: Extract source snippets
        source_snippets = _extract_source_snippets(reader, bookmarks, log)

        # Step 3: Parse output HTML
        output_headings = _extract_output_headings(output_html_path, log)

        if not output_headings:
            return {
                "source_file": str(source_pdf_path),
                "output_file": str(output_html_path),
                "total_bookmarks": len(bookmarks),
                "total_output_headings": 0,
                "alignment_score": 0,
                "summary": {
                    "aligned": 0,
                    "title_only": 0,
                    "misaligned": 0,
                    "unmatched": len(bookmarks),
                },
                "threshold": threshold,
                "chapters": [
                    {
                        "bookmark_title": bm['title'],
                        "bookmark_page": bm['page'],
                        "bookmark_idx": i,
                        "status": "unmatched",
                        "title_score": 0.0,
                        "body_score": 0.0,
                        "combined_score": 0.0,
                        "detail": "No headings in output HTML",
                    }
                    for i, bm in enumerate(bookmarks)
                ],
            }

        # Step 4: Match bookmarks to output headings
        matches = _match_bookmarks_to_headings(bookmarks, output_headings, log)

        # Step 5: Compare body text snippets
        results = _compare_body_snippets(
            matches, source_snippets, output_headings, threshold, log
        )

        # Step 6: Assemble report
        aligned = sum(1 for r in results if r['status'] == 'aligned')
        title_only = sum(1 for r in results if r['status'] == 'title_only')
        misaligned = sum(1 for r in results if r['status'] == 'misaligned')
        unmatched = sum(1 for r in results if r['status'] == 'unmatched')
        total = len(results)

        alignment_score = round(aligned / max(total, 1) * 100)

        report = {
            "source_file": str(source_pdf_path),
            "output_file": str(output_html_path),
            "total_bookmarks": len(bookmarks),
            "total_output_headings": len(output_headings),
            "alignment_score": alignment_score,
            "summary": {
                "aligned": aligned,
                "title_only": title_only,
                "misaligned": misaligned,
                "unmatched": unmatched,
            },
            "threshold": threshold,
            "chapters": [],
        }

        for result in results:
            bm = bookmarks[result['bookmark_idx']]
            chapter_detail = {
                "bookmark_title": bm['title'],
                "bookmark_page": bm['page'],
                **result,
            }
            if result.get('heading_idx') is not None:
                chapter_detail["output_heading"] = output_headings[result['heading_idx']]['title']
            report["chapters"].append(chapter_detail)

        log(f"  Alignment score: {alignment_score}% "
            f"({aligned} aligned, {title_only} title_only, "
            f"{misaligned} misaligned, {unmatched} unmatched)")

        return report

    except Exception as e:
        return {
            "source_file": str(source_pdf_path),
            "output_file": str(output_html_path),
            "error": str(e),
            "alignment_score": None,
        }


# ═══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chapter alignment verification: compare output HTML headings "
                    "against source PDF bookmarks using fuzzy matching."
    )
    parser.add_argument("--source", required=True,
                        help="Path to the source PDF file")
    parser.add_argument("--output", required=True,
                        help="Path to the output HTML file")
    parser.add_argument("--threshold", type=float, default=0.6,
                        help="Combined score threshold for 'aligned' status (default: 0.6)")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose diagnostic output to stderr")
    args = parser.parse_args()

    import logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    logger = logging.getLogger("chapter_alignment")

    def log(msg):
        logger.info(msg)

    report = verify_chapter_alignment(args.source, args.output, args.threshold, log)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
