"""
SCRUM-299: A2 running-header filter — characterization tests.

Unit 1 (TDD): failing test proves the root cause before any code change.
Canary: proves the code-literal exclusion protects Python in Easy Steps.

Both tests call extract_with_pdfminer_html + format_paragraphs_as_html directly
(no subprocess / full pipeline) for speed and isolation.

Note: Atomic Habits PDF is not in archive; Python in Easy Steps (inbox/) is used
as the canary instead. Python's window.mainloop() × 6 tests the code-literal
exclusion, which is the *stricter* canary — it requires the heuristic to fire,
not just the page-count threshold.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Path resolution — handles both worktree and main-project contexts
# ---------------------------------------------------------------------------
# WORKTREE_ROOT: where the code under test lives (tools/extract_tts_text.py)
# DATA_ROOT: where archive/ and inbox/ live (may differ in a worktree)
# ---------------------------------------------------------------------------

TESTS_DIR = Path(__file__).resolve().parent
WORKTREE_ROOT = TESTS_DIR.parent  # code under test always lives here

if not (WORKTREE_ROOT / "archive").is_dir():
    # Running from a worktree (.worktrees/<branch>/); archive is in main project
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
    _mark_a2_running_headers,
)

# ---------------------------------------------------------------------------
# Known PDF paths
# ---------------------------------------------------------------------------

_DIONYSIUS_PDF = ARCHIVE_DIR / (
    "C. E. Rolt - Dionysius the Areopagite, "
    "On the Divine Names and the Mystical Theology (1992) - libgen.li.pdf"
)

_PYTHON_PDF = INBOX_DIR / "Python in easy steps, 2nd Edition - Mike McGrath.pdf"

# The exact running-header string as it appears in extracted HTML
_DIONYSIUS_HEADER = (
    "Dionysius the Areopagite: On the Divine Names and the C.E. Rolt Mystical Theology."
)

# Code literal that appears on 6+ pages in Python in Easy Steps
_PYTHON_CANARY = "window.mainloop()"


def _noop_log(msg: str) -> None:
    pass


def _extract_html(pdf_path: Path) -> str:
    """Run HTML extraction on *pdf_path* and return the full HTML string."""
    para_dicts, body_size = extract_with_pdfminer_html(str(pdf_path), _noop_log)
    result = format_paragraphs_as_html(para_dicts, body_size, bookmarks=[], log=_noop_log)
    # format_paragraphs_as_html returns (html, heading_registry)
    html = result[0] if isinstance(result, tuple) else result
    return html


def _count_standalone_p(html: str, text: str) -> int:
    """Count <p>text</p> occurrences (whitespace-tolerant, case-sensitive)."""
    escaped = re.escape(text)
    pattern = rf"<p>\s*{escaped}\s*</p>"
    return len(re.findall(pattern, html))


def _count_any_p_containing(html: str, substring: str) -> int:
    """Count <p>…</p> tags whose content includes *substring*."""
    pattern = rf"<p>[^<]*{re.escape(substring)}[^<]*</p>"
    return len(re.findall(pattern, html))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_dionysius_header_stripped():
    """
    A2 filter must produce 0 standalone running-header <p> tags for Dionysius.

    BEFORE the fix: 145 occurrences are expected → this test FAILS.
    AFTER the fix:  0 occurrences → this test PASSES.
    """
    if not _DIONYSIUS_PDF.is_file():
        import pytest
        pytest.skip(f"Dionysius PDF not found: {_DIONYSIUS_PDF}")

    html = _extract_html(_DIONYSIUS_PDF)
    count = _count_standalone_p(html, _DIONYSIUS_HEADER)
    assert count == 0, (
        f"Expected 0 standalone running-header <p> tags in Dionysius HTML, "
        f"got {count}. "
        f"Root cause: A2 filter not yet applied to HTML extraction path."
    )


def test_python_code_literal_preserved():
    """
    A2 filter must NOT strip window.mainloop() from Python in Easy Steps.

    window.mainloop() (17 chars) appears on 9 distinct pages — well above the
    >=5 threshold. Without the code-literal exclusion heuristic, A2 would mark
    all occurrences and the main loop would skip them BEFORE FIX 3 runs,
    producing count = 0.

    With the exclusion: A2 does not mark them → FIX 3 keeps at least one → count >= 1.

    Assert >= 1: verifies at least one occurrence survives. If the A2 filter
    incorrectly strips all code literals, the count becomes 0 and this test fails.

    This test PASSES on the current state and must continue to PASS after
    the A2 filter is implemented with the code-literal exclusion heuristic.
    """
    if not _PYTHON_PDF.is_file():
        import pytest
        pytest.skip(f"Python in Easy Steps PDF not found: {_PYTHON_PDF}")

    html = _extract_html(_PYTHON_PDF)
    count = _count_any_p_containing(html, _PYTHON_CANARY)
    assert count >= 1, (
        f"Expected >= 1 <p> tags containing '{_PYTHON_CANARY}' in Python HTML, "
        f"got {count}. "
        f"Code-literal exclusion has incorrectly stripped this canary line."
    )


def test_atomic_cheat_sheet_not_stripped():
    """
    Synthetic: A2 filter must NOT mark a pattern appearing on only 4 distinct pages.

    Protects the Atomic Habits cheat-sheet pattern: an 85-char mixed-case line
    repeating on exactly 4 pages in a ~300-page book (≈1.3% density). Both
    thresholds protect it independently: absolute count 4 < 5, and density
    1.3% < 10%.

    The Atomic Habits PDF is not in archive; this synthetic test directly
    exercises the ≥5 threshold without the PDF (R2 requirement).
    """
    # 85-char mixed-case line matching the Atomic Habits cheat-sheet profile
    cheat_line = (
        "The Aggregation of Marginal Gains: 1% improvements compound into remarkable results."
    )
    assert 15 <= len(cheat_line) <= 150, f"cheat_line length {len(cheat_line)} out of filter range"

    # ~300-page synthetic book: body text on every page, cheat line on 4 distinct pages
    para_dicts = []
    for page in range(1, 301):
        para_dicts.append({
            "text": f"Body content paragraph on page {page}.",
            "page_number": page,
            "is_page_marker": False,
            "heading_level": None,
        })

    cheat_pages = [10, 80, 160, 230]  # exactly 4 distinct pages
    for page in cheat_pages:
        para_dicts.append({
            "text": cheat_line,
            "page_number": page,
            "is_page_marker": False,
            "heading_level": None,
        })

    _mark_a2_running_headers(para_dicts, _noop_log)

    marked = [p for p in para_dicts if p.get("_is_a2_running_header")]
    assert len(marked) == 0, (
        f"Expected 0 marked paragraphs for 4-page pattern (absolute threshold ≥5 not met), "
        f"got {len(marked)}. "
        f"A2 filter is incorrectly stripping the Atomic Habits cheat-sheet pattern."
    )
