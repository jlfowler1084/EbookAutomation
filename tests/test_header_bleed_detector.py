"""Unit tests for check_header_bleed.py (EB-370).

Covers: happy paths, density gate, glue-position classification, heading
bucket, edge cases (curly apostrophe, non-page_ anchors, total_pages
fallback), exit-code helper, and CLI integration (including invalid-args
exit 3 requirement).

Test-first: written before the detector implementation.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path resolution — handles both worktree and main-project contexts
# ---------------------------------------------------------------------------
TESTS_DIR = Path(__file__).resolve().parent
WORKTREE_ROOT = TESTS_DIR.parent

if not (WORKTREE_ROOT / "archive").is_dir():
    DATA_ROOT = WORKTREE_ROOT.parent.parent
else:
    DATA_ROOT = WORKTREE_ROOT

TOOLS_DIR = WORKTREE_ROOT / "tools"
FIXTURES_DIR = TESTS_DIR / "fixtures"

sys.path.insert(0, str(TOOLS_DIR))

from check_header_bleed import (  # noqa: E402
    BookResult,
    DetectorParams,
    _compute_exit_code,
    detect,
    detect_file,
)

WELD_FIXTURE = FIXTURES_DIR / "header_bleed_pilgrim_prefix.html"
CLEAN_FIXTURE = FIXTURES_DIR / "header_bleed_clean.html"

# ---------------------------------------------------------------------------
# HTML builder helper
# ---------------------------------------------------------------------------

def _make_html(pages: list[tuple[int, str]], total: int = 0) -> str:
    """Build minimal _kindle.html for inline tests.

    pages: (page_number, paragraph_text) tuples — page anchors are emitted
    once per unique page_number (in the order first seen).
    total: if >0, append empty anchor pages up to this number to set total_pages.
    """
    parts: list[str] = ["<html><body>"]
    seen: set[int] = set()
    for page_num, text in pages:
        if page_num not in seen:
            parts.append(f'<a id="page_{page_num}"></a>')
            seen.add(page_num)
        parts.append(f"<p>{text}</p>")
    # Pad remaining pages to establish total_pages
    for pg in range(1, total + 1):
        if pg not in seen:
            parts.append(f'<a id="page_{pg}"></a>')
            seen.add(pg)
    parts.append("</body></html>")
    return "\n".join(parts)


def _weld_html(total: int = 50, weld_pages: list[int] | None = None) -> str:
    """Build HTML with 'PILGRIM PEOPLE N' welded as glued-start on weld_pages."""
    if weld_pages is None:
        weld_pages = [1, 4, 7, 10, 13, 16]
    weld_set = set(weld_pages)
    pages = []
    for pg in range(1, total + 1):
        if pg in weld_set:
            pages.append((pg, f"PILGRIM PEOPLE {pg} continues with body text after the header here."))
        else:
            pages.append((pg, f"Normal body text on page {pg} with no unusual content."))
    return _make_html(pages)


# ---------------------------------------------------------------------------
# Happy path — fixture files
# ---------------------------------------------------------------------------

def test_weld_fixture_flagged():
    """Committed synthetic weld fixture must be detected as flagged."""
    result = detect_file(WELD_FIXTURE)
    assert result.status == "flagged", f"Expected flagged, got {result.status}"
    assert result.weld_total > 0, f"Expected weld_total > 0, got {result.weld_total}"
    norms = [f.normalized for f in result.findings]
    assert any("pilgrim people" in n for n in norms), (
        f"Expected 'pilgrim people' in findings, got {norms}"
    )


def test_clean_fixture_clean():
    """Committed clean fixture must produce zero welds."""
    result = detect_file(CLEAN_FIXTURE)
    assert result.status == "clean", f"Expected clean, got {result.status}"
    assert result.weld_total == 0, f"Expected weld_total 0, got {result.weld_total}"


# ---------------------------------------------------------------------------
# Happy path — inline HTML
# ---------------------------------------------------------------------------

def test_weld_inline_flagged():
    """Inline HTML with PILGRIM PEOPLE glued-start on 6/50 pages → flagged."""
    html = _weld_html(total=50, weld_pages=[1, 4, 7, 10, 13, 16])
    result = detect(html)
    assert result.status == "flagged"
    assert result.weld_total >= 6

    f = next((f for f in result.findings if "pilgrim people" in f.normalized), None)
    assert f is not None
    assert f.occurrences == 6
    assert f.distinct_pages == 6
    assert abs(f.density - 6 / 50) < 0.01


def test_clean_inline():
    """HTML with no recurring CAPS patterns → clean."""
    pages = [(pg, f"Normal body text on page {pg} with ordinary content.") for pg in range(1, 41)]
    html = _make_html(pages)
    result = detect(html)
    assert result.status == "clean"
    assert result.weld_total == 0


# ---------------------------------------------------------------------------
# Density gate
# ---------------------------------------------------------------------------

def test_low_density_not_flagged():
    """Candidate on 3 of 260 pages (1.1%) must NOT be flagged (below 10%)."""
    pages = []
    for pg in range(1, 261):
        if pg in (1, 50, 100):
            pages.append((pg, f"SOMETHING ELSE {pg} begins here with more body text following."))
        else:
            pages.append((pg, f"Normal body text on page {pg}."))
    html = _make_html(pages)
    result = detect(html)
    assert result.weld_total == 0, (
        f"Low-density candidate should not be flagged, got weld_total={result.weld_total}"
    )
    assert result.status == "clean"


def test_exactly_five_pages_threshold():
    """Candidate on exactly 5 of 50 pages (10%) must be flagged (boundary)."""
    html = _weld_html(total=50, weld_pages=[1, 11, 21, 31, 41])
    result = detect(html)
    assert result.weld_total >= 5, (
        f"Boundary case (5/50=10%) should be flagged, got weld_total={result.weld_total}"
    )


def test_four_pages_not_flagged():
    """Candidate on only 4 of 50 pages (8%) must NOT be flagged."""
    html = _weld_html(total=50, weld_pages=[1, 11, 21, 31])
    result = detect(html)
    assert result.weld_total == 0, (
        f"4/50=8% should not be flagged, got weld_total={result.weld_total}"
    )


# ---------------------------------------------------------------------------
# ALL-CAPS rule: 2+ word requirement
# ---------------------------------------------------------------------------

def test_single_word_not_flagged():
    """Single ALL-CAPS word EXERCISE on many pages must NOT be flagged (2+-word rule)."""
    pages = []
    for pg in range(1, 51):
        pages.append((pg, f"EXERCISE begin the practice on page {pg} with careful attention."))
    html = _make_html(pages)
    result = detect(html)
    assert result.weld_total == 0, "Single CAPS word should not be flagged"
    assert result.status == "clean"


def test_single_word_summary_not_flagged():
    """Single ALL-CAPS word SUMMARY on many pages must NOT be flagged."""
    pages = []
    for pg in range(1, 51):
        pages.append((pg, f"SUMMARY of the main points covered in the chapter on page {pg}."))
    html = _make_html(pages)
    result = detect(html)
    assert result.weld_total == 0, "Single CAPS word SUMMARY should not be flagged"


def test_atomic_habits_canary():
    """85-char repeating mixed-case body line must NOT be flagged (no ALL-CAPS)."""
    long_line = "The surprising power of small habits is that they compound over time into remarkable results."
    pages = [(pg, long_line) for pg in range(1, 51)]
    html = _make_html(pages)
    result = detect(html)
    assert result.weld_total == 0, "Mixed-case long line should not be flagged"
    assert result.status == "clean"


# ---------------------------------------------------------------------------
# Glue-position classification
# ---------------------------------------------------------------------------

def test_standalone_goes_to_standalone_repeats():
    """PILGRIM PEOPLE as whole <p> → standalone_repeats, weld_total==0."""
    pages = []
    for pg in range(1, 51):
        if pg <= 8:
            pages.append((pg, f"PILGRIM PEOPLE {pg}"))
        else:
            pages.append((pg, f"Normal body text on page {pg}."))
    html = _make_html(pages)
    result = detect(html)
    assert result.weld_total == 0, (
        f"Standalone repeats must not count as welds, got weld_total={result.weld_total}"
    )
    assert result.status == "clean"
    sr_norms = [f.normalized for f in result.standalone_repeats]
    assert any("pilgrim people" in n for n in sr_norms), (
        f"Expected standalone_repeats for 'pilgrim people', got {sr_norms}"
    )


def test_glued_start_is_weld():
    """PILGRIM PEOPLE at START of longer paragraph → glued-start, counted in weld_total."""
    pages = []
    for pg in range(1, 51):
        if pg <= 8:
            pages.append((pg, f"PILGRIM PEOPLE {pg} the body text continues with more content here."))
        else:
            pages.append((pg, f"Normal body text on page {pg}."))
    html = _make_html(pages)
    result = detect(html)
    assert result.weld_total > 0, "Glued-start should be counted as weld"
    assert result.status == "flagged"

    f = next((f for f in result.findings if "pilgrim people" in f.normalized), None)
    assert f is not None
    non_standalone = [g for g in f.glue_positions if g != "standalone"]
    assert len(non_standalone) == 8
    assert all(g == "glued-start" for g in non_standalone), (
        f"Expected all glued-start, got {f.glue_positions}"
    )


def test_glued_end_is_weld():
    """PILGRIM PEOPLE at END of longer paragraph → glued-end, counted in weld_total."""
    pages = []
    for pg in range(1, 51):
        if pg <= 8:
            pages.append((pg, f"The body text precedes the header PILGRIM PEOPLE {pg}"))
        else:
            pages.append((pg, f"Normal body text on page {pg}."))
    html = _make_html(pages)
    result = detect(html)
    assert result.weld_total > 0, "Glued-end should be counted as weld"

    f = next((f for f in result.findings if "pilgrim people" in f.normalized), None)
    assert f is not None
    non_standalone = [g for g in f.glue_positions if g != "standalone"]
    assert all(g == "glued-end" for g in non_standalone), (
        f"Expected all glued-end, got {f.glue_positions}"
    )


def test_mid_paragraph_is_weld():
    """PILGRIM PEOPLE in MIDDLE of paragraph → mid-paragraph, counted in weld_total."""
    pages = []
    for pg in range(1, 51):
        if pg <= 8:
            pages.append((pg, f"Body text before and PILGRIM PEOPLE {pg} then body text after here."))
        else:
            pages.append((pg, f"Normal body text on page {pg}."))
    html = _make_html(pages)
    result = detect(html)
    assert result.weld_total > 0, "Mid-paragraph should be counted as weld"

    f = next((f for f in result.findings if "pilgrim people" in f.normalized), None)
    assert f is not None
    non_standalone = [g for g in f.glue_positions if g != "standalone"]
    assert all(g == "mid-paragraph" for g in non_standalone), (
        f"Expected all mid-paragraph, got {f.glue_positions}"
    )


def test_heading_only_not_a_weld():
    """PILGRIM PEOPLE in <h*> only → heading_repeats, weld_total==0, status clean."""
    pages = []
    for pg in range(1, 51):
        if pg <= 8:
            pages.append((pg, "HEADING"))  # placeholder, will be replaced below
        else:
            pages.append((pg, f"Normal body text on page {pg}."))
    # Build manually with h2 tags for those pages
    parts = ["<html><body>"]
    seen: set[int] = set()
    for pg in range(1, 51):
        if pg not in seen:
            parts.append(f'<a id="page_{pg}"></a>')
            seen.add(pg)
        if pg <= 8:
            parts.append(f"<h2>PILGRIM PEOPLE</h2>")
        else:
            parts.append(f"<p>Normal body text on page {pg}.</p>")
    parts.append("</body></html>")
    html = "\n".join(parts)

    result = detect(html)
    assert result.weld_total == 0, "Heading-only repeats must not count as welds"
    assert result.status == "clean"
    hr_norms = [f.normalized for f in result.heading_repeats]
    assert any("pilgrim people" in n for n in hr_norms), (
        f"Expected heading_repeats for 'pilgrim people', got {hr_norms}"
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_curly_apostrophe_candidate():
    """Candidate with right-single-quote apostrophe (O’HALLORAN FAMILY) must match."""
    pages = []
    for pg in range(1, 51):
        if pg <= 8:
            pages.append((pg, f"O’HALLORAN FAMILY {pg} the story continues with more text here."))
        else:
            pages.append((pg, f"Normal body text on page {pg}."))
    html = _make_html(pages)
    result = detect(html)
    assert result.weld_total > 0, (
        "Curly-apostrophe CAPS candidate should be detected as weld"
    )


def test_straight_apostrophe_candidate():
    """EB-372: ASCII straight apostrophe (U+0027) must be in the token class.

    Before the fix, _APOSTROPHES omitted U+0027 (it duplicated U+2019), so
    straight-apostrophe headers were either missed (e.g. JOHN'S WAR -> clean)
    or misreported with a split candidate (KING'S ROAD -> 's road'). This
    asserts both detection AND the correctly-normalized candidate.
    """
    pages = []
    for pg in range(1, 51):
        if pg <= 8:
            pages.append((pg, f"KING'S ROAD {pg} the story continues with more text here."))
        else:
            pages.append((pg, f"Normal body text on page {pg}."))
    html = _make_html(pages)
    result = detect(html)
    assert result.weld_total > 0, "Straight-apostrophe CAPS candidate should be detected as weld"
    norms = [f.normalized for f in result.findings]
    assert "king's road" in norms, (
        f"Expected candidate \"king's road\" with straight apostrophe preserved, got {norms}"
    )


def test_non_page_anchors_ignored():
    """Non-page_ anchors (endnote_, footnote_, noteref_) must be ignored."""
    pages = []
    for pg in range(1, 41):
        if pg <= 6:
            pages.append((pg, f"PILGRIM PEOPLE {pg} the body text continues after the header."))
        else:
            pages.append((pg, f"Normal body text on page {pg}."))
    html = _make_html(pages)
    # Inject non-page anchors
    extra = "\n<a id=\"endnote_1\"></a>\n<a id=\"footnote_3\"></a>\n<a id=\"noteref_5\"></a>"
    html = html.replace("</body>", extra + "\n</body>")

    result = detect(html)
    assert result.total_pages == 40, (
        f"Non-page_ anchors must not inflate total_pages, got {result.total_pages}"
    )
    assert result.weld_total > 0


def test_total_pages_fallback_no_numeric_anchors():
    """When no page_ anchors present, total_pages falls back (>=1, no divide by zero)."""
    html = "<html><body><p>Normal body text paragraph here.</p></body></html>"
    result = detect(html)
    assert result.total_pages >= 1


def test_finding_fields():
    """Findings must include occurrences, distinct_pages, and correct density."""
    html = _weld_html(total=50, weld_pages=[1, 4, 7, 10, 13, 16])
    result = detect(html)
    f = next((f for f in result.findings if "pilgrim people" in f.normalized), None)
    assert f is not None
    assert f.occurrences == 6
    assert f.distinct_pages == 6
    assert abs(f.density - 6 / 50) < 0.005


def test_length_floor_6_catches_14_char_candidate():
    """Normalized candidate of 14 chars (like 'pilgrim people') must be caught at len_min=6."""
    html = _weld_html(total=50, weld_pages=[1, 4, 7, 10, 13, 16])
    result = detect(html, DetectorParams(len_min=6))
    assert result.weld_total > 0, "14-char candidate must pass len_min=6 filter"


def test_length_floor_15_misses_14_char_candidate():
    """With len_min=15, 'pilgrim people' (14 chars) must NOT be flagged (A2's old floor)."""
    html = _weld_html(total=50, weld_pages=[1, 4, 7, 10, 13, 16])
    result = detect(html, DetectorParams(len_min=15))
    norms = [f.normalized for f in result.findings]
    pilgrim_found = any("pilgrim people" in n for n in norms)
    assert not pilgrim_found, (
        f"'pilgrim people' (14 chars) must be excluded at len_min=15, found in {norms}"
    )


def test_length_ceiling_40_excludes_long_pattern():
    """Normalized candidate over 40 chars must NOT be flagged (len_max=40)."""
    long_cand = "VERY LONG RUNNING HEADER TEXT SPANNING MANY WORDS HERE"  # > 40 chars
    pages = []
    for pg in range(1, 51):
        if pg <= 8:
            pages.append((pg, f"{long_cand} {pg} body text continues after this long header here."))
        else:
            pages.append((pg, f"Normal body text on page {pg}."))
    html = _make_html(pages)
    result = detect(html)
    # Should not be flagged (normalized len > 40)
    norms = [f.normalized for f in result.findings]
    assert not any(long_cand.lower() in n for n in norms), (
        f"Long candidate should be excluded by len_max=40, found in {norms}"
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_determinism():
    """Same HTML input twice → identical findings (envelope timestamps excluded)."""
    html = _weld_html(total=50, weld_pages=[1, 4, 7, 10, 13, 16])
    r1 = detect(html)
    r2 = detect(html)
    assert r1.status == r2.status
    assert r1.weld_total == r2.weld_total
    assert r1.total_pages == r2.total_pages
    assert len(r1.findings) == len(r2.findings)
    for f1, f2 in zip(
        sorted(r1.findings, key=lambda f: f.normalized),
        sorted(r2.findings, key=lambda f: f.normalized),
    ):
        assert f1.normalized == f2.normalized
        assert f1.occurrences == f2.occurrences
        assert f1.distinct_pages == f2.distinct_pages
        assert sorted(f1.glue_positions) == sorted(f2.glue_positions)


# ---------------------------------------------------------------------------
# Exit-code helper
# ---------------------------------------------------------------------------

def test_exit_code_empty_is_1():
    assert _compute_exit_code([]) == 1


def test_exit_code_clean_is_0():
    b = BookResult("", "clean", 0, 10, [], [], [])
    assert _compute_exit_code([b]) == 0


def test_exit_code_flagged_is_2():
    b = BookResult("", "flagged", 3, 10, [], [], [])
    assert _compute_exit_code([b]) == 2


def test_exit_code_error_is_3():
    b = BookResult("", "error", 0, 0, [], [], [], error="read error")
    assert _compute_exit_code([b]) == 3


def test_exit_code_error_takes_precedence_over_flagged():
    """Exit 3 takes precedence over exit 2."""
    b1 = BookResult("", "flagged", 2, 10, [], [], [])
    b2 = BookResult("", "error", 0, 0, [], [], [], error="err")
    assert _compute_exit_code([b1, b2]) == 3


def test_exit_code_flagged_takes_precedence_over_clean():
    """Exit 2 takes precedence over exit 0."""
    b1 = BookResult("", "clean", 0, 10, [], [], [])
    b2 = BookResult("", "flagged", 1, 10, [], [], [])
    assert _compute_exit_code([b1, b2]) == 2


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

def test_cli_weld_fixture_exits_2(tmp_path):
    """CLI on weld fixture → exit 2; JSON report exit_code == 2."""
    out = tmp_path / "report.json"
    r = subprocess.run(
        ["py", "-3.12", str(TOOLS_DIR / "check_header_bleed.py"),
         "--input", str(WELD_FIXTURE), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 2, (
        f"Expected exit 2 on weld fixture, got {r.returncode}\nstderr: {r.stderr}"
    )
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["exit_code"] == 2


def test_cli_clean_fixture_exits_0(tmp_path):
    """CLI on clean fixture → exit 0; JSON report exit_code == 0."""
    out = tmp_path / "report.json"
    r = subprocess.run(
        ["py", "-3.12", str(TOOLS_DIR / "check_header_bleed.py"),
         "--input", str(CLEAN_FIXTURE), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, (
        f"Expected exit 0 on clean fixture, got {r.returncode}\nstderr: {r.stderr}"
    )
    data = json.loads(out.read_text())
    assert data["exit_code"] == 0


def test_cli_invalid_arg_exits_3():
    """Invalid CLI flag must exit 3 (not argparse default 2)."""
    r = subprocess.run(
        ["py", "-3.12", str(TOOLS_DIR / "check_header_bleed.py"),
         "--nonexistent-flag-xyz"],
        capture_output=True, text=True,
    )
    assert r.returncode == 3, (
        f"Expected exit 3 for invalid arg, got {r.returncode}"
    )


def test_cli_missing_required_arg_exits_3():
    """Missing required --input must exit 3."""
    r = subprocess.run(
        ["py", "-3.12", str(TOOLS_DIR / "check_header_bleed.py")],
        capture_output=True, text=True,
    )
    assert r.returncode == 3, (
        f"Expected exit 3 for missing --input, got {r.returncode}"
    )


def test_cli_nonexistent_input_exits_3(tmp_path):
    """Non-existent input path must exit 3."""
    r = subprocess.run(
        ["py", "-3.12", str(TOOLS_DIR / "check_header_bleed.py"),
         "--input", str(tmp_path / "nonexistent.html")],
        capture_output=True, text=True,
    )
    assert r.returncode == 3, (
        f"Expected exit 3 for missing file, got {r.returncode}"
    )


def test_cli_empty_directory_exits_1(tmp_path):
    """Empty directory (no matching HTML) must exit 1."""
    r = subprocess.run(
        ["py", "-3.12", str(TOOLS_DIR / "check_header_bleed.py"),
         "--input", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 1, (
        f"Expected exit 1 for empty dir, got {r.returncode}"
    )


def test_cli_json_exit_code_matches_process(tmp_path):
    """JSON report exit_code field must equal the process exit code."""
    out = tmp_path / "report.json"
    r = subprocess.run(
        ["py", "-3.12", str(TOOLS_DIR / "check_header_bleed.py"),
         "--input", str(WELD_FIXTURE), "--out", str(out)],
        capture_output=True, text=True,
    )
    data = json.loads(out.read_text())
    assert data["exit_code"] == r.returncode, (
        f"JSON exit_code {data['exit_code']} != process exit {r.returncode}"
    )


# ---------------------------------------------------------------------------
# Calibration tests (env-gated: RUN_CALIBRATION=1)
# ---------------------------------------------------------------------------

import os  # noqa: E402 (imported here for clarity with the gating pattern)

_RUN_CAL = os.environ.get("RUN_CALIBRATION", "0") == "1"


class TestCalibration:
    """Calibration gate: determinism + zero-FP canaries + sensitivity.

    Env-gated behind RUN_CALIBRATION=1 (mirrors the PDF-dependent skip
    pattern). These tests scan the committed fixtures (not live PDFs) so
    they can run without the corpus on disk.
    """

    def setup_method(self):
        if not _RUN_CAL:
            pytest.skip("Set RUN_CALIBRATION=1 to run calibration tests")

    def test_calibration_determinism(self):
        """Detector run twice on both fixtures → identical findings."""
        for fixture in (WELD_FIXTURE, CLEAN_FIXTURE):
            r1 = detect_file(fixture)
            r2 = detect_file(fixture)
            assert r1.status == r2.status, f"{fixture.name}: status differs across runs"
            assert r1.weld_total == r2.weld_total, f"{fixture.name}: weld_total differs"
            assert len(r1.findings) == len(r2.findings), f"{fixture.name}: finding count differs"

    def test_calibration_zero_fp_clean_fixture(self):
        """Clean canary fixture must produce weld_total == 0."""
        result = detect_file(CLEAN_FIXTURE)
        assert result.weld_total == 0, (
            f"Clean canary produced false positive: {[f.normalized for f in result.findings]}"
        )

    def test_calibration_sensitivity_weld_fixture(self):
        """Synthetic weld fixture must be detected (sensitivity gate)."""
        result = detect_file(WELD_FIXTURE)
        assert result.weld_total > 0, (
            "Weld fixture was NOT detected — sensitivity gate FAILED. "
            "The detector is not catching the synthetic weld signature."
        )
        assert result.status == "flagged"
