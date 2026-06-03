"""
EB-367: Running-header bleed on the single-column HTML extraction path.

Root cause (see EB-367 diagnosis): short ALL-CAPS title headers
("PILGRIM PEOPLE 73") are not marked by the A2 frequency filter (each full
string is unique due to the trailing page number; the number-stripped form
"PILGRIM PEOPLE" is 14 chars, below A2's >=15-char floor). Unmarked, the
page-boundary rejoin pass welds the header into adjacent body paragraphs —
sometimes mid-word. Once embedded, no downstream filter can remove it.

The fix adds position-based running-header detection to the single-column
pdfminer path (top-margin zone, repeated across pages), mirroring the existing
bottom-zone footnote detection, so headers are isolated and stripped before
rejoin welds them into prose.

Repro book: Pilgrim People (Lebeson, 1950) — scan_with_text, single-column,
HTML path. PDF text layer literally begins each page with "PILGRIM PEOPLE <n>".

Mirrors tests/test_scrum_299_running_header_a2.py structure (worktree-aware
paths; direct extract + format, no subprocess; page-range slice for speed).
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Path resolution — handles both worktree and main-project contexts
# ---------------------------------------------------------------------------
TESTS_DIR = Path(__file__).resolve().parent
WORKTREE_ROOT = TESTS_DIR.parent  # code under test always lives here

if not (WORKTREE_ROOT / "archive").is_dir():
    # Running from a worktree (.worktrees/<branch>/); data is in main project
    DATA_ROOT = WORKTREE_ROOT.parent.parent  # F:/Projects/EbookAutomation/
else:
    DATA_ROOT = WORKTREE_ROOT

TOOLS_DIR = WORKTREE_ROOT / "tools"  # import modified code from THIS worktree
ARCHIVE_DIR = DATA_ROOT / "archive"
INBOX_DIR = DATA_ROOT / "inbox"

sys.path.insert(0, str(TOOLS_DIR))

from extract_tts_text import (  # noqa: E402
    extract_with_pdfminer_html,
    format_paragraphs_as_html,
    _fix_word_merges_html,
    _mark_a2_running_headers,
    rejoin_html_fragments,
)

_PILGRIM_NAME = "Pilgrim People - Anita Libman Lebeson (1950).pdf"
# Durable home is archive/ (matches the SCRUM-299 anchor convention); fall back
# to inbox/ if the book has not yet been moved to archive.
_PILGRIM_PDF = ARCHIVE_DIR / _PILGRIM_NAME
if not _PILGRIM_PDF.is_file() and (INBOX_DIR / _PILGRIM_NAME).is_file():
    _PILGRIM_PDF = INBOX_DIR / _PILGRIM_NAME

# The running header as it appears in the source text layer (book title, caps).
_PILGRIM_HEADER = "PILGRIM PEOPLE"

# 0-indexed page slice (pdfminer page_numbers). Pages ~5-60 carry the
# "PILGRIM PEOPLE [n]" running header densely. With the real preprocessing
# order (mark -> rejoin -> format), this slice welds ~28 headers into body
# paragraphs pre-fix; the title-page h3 (page 1) is a heading, not a <p>, so
# it is not counted by the body matcher.
_PAGE_RANGE = (0, 60)


def _noop_log(msg: str) -> None:
    pass


def _extract_html(pdf_path: Path, page_range) -> str:
    """Run extraction + the welding-relevant preprocessing, then format.

    CRITICAL (EB-367): the full pipeline (process_kindle_html) runs
    _mark_a2_running_headers() then rejoin_html_fragments() BEFORE
    format_paragraphs_as_html(). The rejoin pass is what welds unmarked
    running headers into adjacent body paragraphs. A test that calls
    extract -> format directly SKIPS rejoin and does NOT reproduce the bug.
    This helper replicates the real STEP 1a/1a2/1b order so the test
    characterizes the actual defect surface.
    """
    para_dicts, body_size = extract_with_pdfminer_html(
        str(pdf_path), _noop_log, page_range=page_range
    )
    _fix_word_merges_html(para_dicts, _noop_log)          # STEP 1a
    _mark_a2_running_headers(para_dicts, _noop_log)       # STEP 1a2 (must mark headers)
    para_dicts = rejoin_html_fragments(para_dicts, body_size, _noop_log)  # STEP 1b (welds if unmarked)
    result = format_paragraphs_as_html(para_dicts, body_size, bookmarks=[], log=_noop_log)
    return result[0] if isinstance(result, tuple) else result


def _count_header_in_body_paragraphs(html: str, header_text: str) -> int:
    """Count <p> paragraphs (not headings) whose text contains *header_text*.

    Tolerant of inline tags (<sup>, <em>, <a>) inside the paragraph: matches on
    any line that opens a <p> tag and contains the header substring. Heading
    tags (<h1>-<h6>) are intentionally NOT counted — a legitimate chapter title
    rendered as a heading is acceptable; the bug is the header welded into body
    <p> text.
    """
    count = 0
    for line in html.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("<p>") and header_text in line:
            count += 1
    return count


def test_pilgrim_running_header_not_welded_into_body():
    """Running header 'PILGRIM PEOPLE' must not appear inside body <p> paragraphs.

    BEFORE the fix: the header is welded into many body paragraphs across the
    slice -> count is large -> this test FAILS.
    AFTER the fix:  position-based detection isolates+strips the header before
    rejoin -> count == 0 -> this test PASSES.
    """
    if not _PILGRIM_PDF.is_file():
        import pytest
        pytest.skip(f"Pilgrim People PDF not found: {_PILGRIM_PDF}")

    html = _extract_html(_PILGRIM_PDF, _PAGE_RANGE)
    count = _count_header_in_body_paragraphs(html, _PILGRIM_HEADER)
    assert count == 0, (
        f"Expected 0 body <p> paragraphs containing the running header "
        f"'{_PILGRIM_HEADER}', got {count}. The header is being welded into "
        f"body text by the page-boundary rejoin pass (EB-367)."
    )
