"""EB-374: running-header bleed with ROMAN-NUMERAL page numbers.

EB-367 strips welded running-header prefixes only when the adjacent page number
is arabic (\\d). Front-matter pages numbered with roman numerals (viii, XXIV, …)
slipped through, so the running header welded into / survived as body paragraphs
(found on On First Principles, 36 welds, all roman-prefixed front matter).

Extraction side (_mark_a2_running_headers):
  - roman-prefixed standalone headers must be marked (so they're stripped)
  - roman page numbers welded around a confirmed header must be stripped
  - NEGATIVE: roman-looking real content (varying remainder, one-offs) must not
    be marked or stripped

Detector side (check_header_bleed):
  - a roman page-number adjacent to a candidate must classify the paragraph as a
    standalone header repeat, not a body weld (severity accuracy, finding #2)
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TESTS_DIR = Path(__file__).resolve().parent
WORKTREE_ROOT = TESTS_DIR.parent
TOOLS_DIR = WORKTREE_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from extract_tts_text import _mark_a2_running_headers  # noqa: E402
import check_header_bleed  # noqa: E402

_ROMANS = ["viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii",
           "xviii", "xix", "xx", "xxi", "xxii", "xxiii", "xxiv", "xxv", "xxvi",
           "xxvii", "xxviii", "xxix", "xxx", "xxxi", "xxxii"]


def _noop_log(_):
    pass


# --- Extraction: positive ---------------------------------------------------

def test_roman_prefixed_standalone_header_marked():
    """Standalone '<roman> ON FIRST PRINCIPLES' paragraphs (varying roman page
    numbers) must be recognized as one running header and marked."""
    para_dicts = []
    for i, rom in enumerate(_ROMANS):
        para_dicts.append({"text": f"{rom} ON FIRST PRINCIPLES", "page_number": i + 1,
                           "is_page_marker": False, "heading_level": None,
                           "_margin_zone": True})
    # body filler to set total_pages ~ 100 (25 headers / 100 = 25% density)
    para_dicts += [{"text": f"ordinary body content paragraph number {pg} here", "page_number": pg,
                    "is_page_marker": False, "heading_level": None}
                   for pg in range(1, 101)]
    _mark_a2_running_headers(para_dicts, _noop_log)
    marked = sum(1 for p in para_dicts
                 if "ON FIRST PRINCIPLES" in p["text"] and p.get("_is_a2_running_header"))
    assert marked == len(_ROMANS), f"expected all {len(_ROMANS)} roman headers marked, got {marked}"


def test_roman_welded_prefix_stripped():
    """Roman page number welded around a CONFIRMED header is stripped from body."""
    para_dicts = [{"text": f"{rom} ON FIRST PRINCIPLES", "page_number": i + 1,
                   "is_page_marker": False, "heading_level": None, "_margin_zone": True}
                  for i, rom in enumerate(_ROMANS)]
    para_dicts += [{"text": f"ordinary body content paragraph number {pg} here", "page_number": pg,
                    "is_page_marker": False, "heading_level": None}
                   for pg in range(1, 101)]
    trailing = {"text": "ON FIRST PRINCIPLES iv clusively a great deal more body text follows here.",
                "page_number": 60, "is_page_marker": False, "heading_level": None}
    leading = {"text": "xl ON FIRST PRINCIPLES but the argument continues at length in this paragraph.",
               "page_number": 61, "is_page_marker": False, "heading_level": None}
    para_dicts += [trailing, leading]
    _mark_a2_running_headers(para_dicts, _noop_log)
    assert "ON FIRST PRINCIPLES" not in trailing["text"], "trailing-roman weld not stripped"
    assert "ON FIRST PRINCIPLES" not in leading["text"], "leading-roman weld not stripped"


# --- Extraction: negative guards --------------------------------------------

def test_roman_numbered_list_varying_content_not_marked():
    """Roman-numbered list items with DIFFERENT content per page must not group/mark."""
    para_dicts = [{"text": f"{rom} a distinct discussion point number {i} about the topic",
                   "page_number": i + 1, "is_page_marker": False, "heading_level": None,
                   "_margin_zone": True}
                  for i, rom in enumerate(_ROMANS)]
    para_dicts += [{"text": f"ordinary body content paragraph number {pg} here", "page_number": pg,
                    "is_page_marker": False, "heading_level": None}
                   for pg in range(1, 101)]
    _mark_a2_running_headers(para_dicts, _noop_log)
    marked = sum(1 for p in para_dicts
                 if "discussion point" in p["text"] and p.get("_is_a2_running_header"))
    assert marked == 0, f"roman-numbered varying list wrongly marked ({marked})"


def test_roman_lookalike_word_oneoff_not_stripped():
    """A one-off body sentence opening with a roman-lookalike word is untouched."""
    para_dicts = [{"text": f"{rom} ON FIRST PRINCIPLES", "page_number": i + 1,
                   "is_page_marker": False, "heading_level": None, "_margin_zone": True}
                  for i, rom in enumerate(_ROMANS)]
    para_dicts += [{"text": f"ordinary body content paragraph number {pg} here", "page_number": pg,
                    "is_page_marker": False, "heading_level": None}
                   for pg in range(1, 101)]
    mix = {"text": "MIX MASTER techniques appear only once in this particular chapter here.",
           "page_number": 70, "is_page_marker": False, "heading_level": None}
    para_dicts.append(mix)
    _mark_a2_running_headers(para_dicts, _noop_log)
    assert mix["text"].startswith("MIX MASTER"), "one-off roman-lookalike sentence wrongly stripped"
    assert not mix.get("_is_a2_running_header"), "one-off sentence wrongly marked"


# --- Detector: severity accuracy (finding #2) -------------------------------

def test_detector_roman_prefixed_is_standalone_not_weld():
    """'<p>viii ON FIRST PRINCIPLES</p>' is a standalone header repeat, not a body weld."""
    parts = []
    for i, rom in enumerate(_ROMANS[:12]):
        parts.append(f'<a id="page_{i+1}"></a><p>{rom} ON FIRST PRINCIPLES</p>')
    html = "\n".join(parts)
    r = check_header_bleed.detect(html)
    assert r.weld_total == 0, f"roman-prefixed standalone headers misreported as {r.weld_total} welds"
    norms = [f.normalized for f in r.standalone_repeats]
    assert "on first principles" in norms, f"expected standalone_repeats to include the header, got {norms}"


def test_detector_roman_welded_into_prose_still_flagged():
    """A roman page number followed by header AND trailing prose is still a weld."""
    parts = []
    for i, rom in enumerate(_ROMANS[:12]):
        parts.append(
            f'<a id="page_{i+1}"></a>'
            f'<p>{rom} ON FIRST PRINCIPLES and then the body argument continues here at length.</p>')
    html = "\n".join(parts)
    r = check_header_bleed.detect(html)
    assert r.weld_total > 0, "roman-prefixed header welded into real prose should still be a weld"
