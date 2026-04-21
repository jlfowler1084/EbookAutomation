"""Tests for the fallback fingerprint detector.

SCRUM-281 Unit 1 — test-first. Covers all three matcher categories, edge
cases, error paths, and one live-fixture integration scenario.

Matcher categories:
  1. empty-issues + high score per-page
  2. substring match on issues[i].description (case-insensitive)
  3. report-level category_scores collapse (all pages empty → flag all >= threshold)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools.llm_providers.fingerprint_detector import (
    FallbackFingerprintDetector,
    FingerprintSettings,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CORPUS_PATH = Path(__file__).resolve().parent.parent / "tools" / "visual_qa_fallback_fingerprints.json"

DEFAULT_SETTINGS = FingerprintSettings(
    empty_issues_score_threshold=80,
    substring_corpus=("text is clean and readable with no visible artifacts",
                      "clean margins and balanced whitespace",
                      "no action needed",
                      "no visible artifacts",
                      "no significant issues"),
    match_category_scores_collapse=True,
    match_uniform_score_responses=False,
)

SETTINGS_NO_COLLAPSE = FingerprintSettings(
    empty_issues_score_threshold=80,
    substring_corpus=("text is clean and readable with no visible artifacts",
                      "no action needed"),
    match_category_scores_collapse=False,
    match_uniform_score_responses=False,
)


def _make_page(page_number: int, score: int, issues: list | None = None,
               pass_: bool = True, page_type: str = "body") -> dict:
    return {
        "page_number": page_number,
        "page_type": page_type,
        "score": score,
        "pass": pass_,
        "issues": issues if issues is not None else [],
    }


def _make_issue(description: str, category: str = "text_integrity",
                severity: str = "minor") -> dict:
    return {"category": category, "severity": severity, "description": description,
            "suggestion": "Review page."}


# ---------------------------------------------------------------------------
# Matcher 1: empty issues + high score per-page
# ---------------------------------------------------------------------------

def test_matcher1_empty_issues_high_score_flagged() -> None:
    """Page with issues==[] and score >= threshold is flagged (Matcher 1)."""
    pages = [_make_page(35, score=95)]
    detector = FallbackFingerprintDetector(["no action needed"])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == {35}


def test_matcher1_boundary_score_at_threshold_flagged() -> None:
    """Score exactly at threshold (80) with empty issues → flagged."""
    pages = [_make_page(10, score=80)]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == {10}


def test_matcher1_boundary_score_below_threshold_not_flagged() -> None:
    """Score one below threshold (79) with empty issues → NOT flagged."""
    pages = [_make_page(10, score=79)]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == set()


def test_matcher1_empty_issues_low_score_not_flagged() -> None:
    """issues==[] with score=30 (legitimate failed page) is NOT flagged."""
    pages = [_make_page(99, score=30, pass_=False)]
    detector = FallbackFingerprintDetector(["no action needed"])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == set()


# ---------------------------------------------------------------------------
# Matcher 2: substring match on issue descriptions (case-insensitive)
# ---------------------------------------------------------------------------

def test_matcher2_known_fingerprint_phrase_flagged() -> None:
    """Issue description matching corpus phrase → page flagged."""
    issue = _make_issue("Text is clean and readable with no visible artifacts")
    pages = [_make_page(68, score=95, issues=[issue])]
    detector = FallbackFingerprintDetector(["text is clean and readable with no visible artifacts"])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == {68}


def test_matcher2_case_insensitive_match() -> None:
    """Corpus match is case-insensitive: 'NO ACTION NEEDED' matches 'no action needed'."""
    issue = _make_issue("NO ACTION NEEDED — page looks fine")
    pages = [_make_page(5, score=90, issues=[issue])]
    detector = FallbackFingerprintDetector(["no action needed"])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == {5}


def test_matcher2_partial_substring_match() -> None:
    """'no visible artifacts' matches inside a longer description."""
    issue = _make_issue("This page has no visible artifacts or rendering issues.")
    pages = [_make_page(12, score=95, issues=[issue])]
    detector = FallbackFingerprintDetector(["no visible artifacts"])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == {12}


def test_matcher2_rich_specific_issues_not_flagged() -> None:
    """Page with 3 specific findings is NOT flagged by substring matcher."""
    pages = [_make_page(50, score=65, issues=[
        _make_issue("Ligature 'fi' rendered as box glyph on line 3", severity="moderate"),
        _make_issue("Endnote superscript misaligned in paragraph 2", severity="minor"),
        _make_issue("Column gutter too narrow — characters touching at page edge", severity="moderate"),
    ])]
    detector = FallbackFingerprintDetector(["no action needed", "text is clean"])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == set()


# ---------------------------------------------------------------------------
# Matcher 3: report-level category_scores collapse
# ---------------------------------------------------------------------------

def test_matcher3_all_empty_issues_high_score_flags_all() -> None:
    """All pages have issues==[], at least one score >= 80 → all flagged (Matcher 3)."""
    pages = [
        _make_page(1, score=95),
        _make_page(2, score=95),
        _make_page(3, score=85),
        _make_page(4, score=95),
    ]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, DEFAULT_SETTINGS)
    assert result == {1, 2, 3, 4}


def test_matcher3_all_empty_no_high_score_not_flagged() -> None:
    """All pages have issues==[] but NO score >= threshold → Matcher 3 does NOT fire."""
    pages = [_make_page(n, score=60) for n in (1, 2, 3)]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, DEFAULT_SETTINGS)
    assert result == set()


def test_matcher3_disabled_falls_back_to_matcher1() -> None:
    """With match_category_scores_collapse=False, only Matcher 1 fires (above-threshold only)."""
    pages = [
        _make_page(1, score=95),
        _make_page(2, score=60),  # below threshold — NOT flagged without Matcher 3
    ]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == {1}  # page 2 is NOT flagged


def test_matcher3_mixed_pages_does_not_fire() -> None:
    """If some pages have issues (real findings), Matcher 3 does NOT fire."""
    pages = [
        _make_page(1, score=95),                               # empty issues
        _make_page(2, score=80, issues=[_make_issue("Ligature broken")]),  # has real issue
    ]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, DEFAULT_SETTINGS)
    # Matcher 3 does not fire; Matcher 1 flags page 1 only
    assert result == {1}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_parsed_pages_returns_empty_set() -> None:
    """Empty input list → empty set, no errors."""
    detector = FallbackFingerprintDetector(["no action needed"])
    result = detector.detect([], DEFAULT_SETTINGS)
    assert result == set()


def test_non_dict_entries_skipped_gracefully() -> None:
    """Non-dict entries in parsed_pages are silently skipped."""
    pages = [_make_page(1, score=95), None, "garbage", 42]  # type: ignore[list-item]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == {1}


def test_page_number_none_skipped() -> None:
    """Pages without page_number are skipped silently."""
    pages = [{"score": 95, "issues": [], "page_type": "body", "pass": True}]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == set()


def test_multiple_pages_only_matching_ones_flagged() -> None:
    """Mix of flagged + unflagged pages — only matching ones appear in result."""
    pages = [
        _make_page(1, score=50),    # low score, empty issues — NOT flagged
        _make_page(2, score=90),    # high score, empty issues — Matcher 1
        _make_page(3, score=85, issues=[_make_issue("Ligature error")]),  # real issue — NOT flagged
        _make_page(4, score=95, issues=[_make_issue("Text is clean and readable with no visible artifacts")]),  # Matcher 2
    ]
    detector = FallbackFingerprintDetector(["text is clean and readable with no visible artifacts"])
    result = detector.detect(pages, SETTINGS_NO_COLLAPSE)
    assert result == {2, 4}


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_from_corpus_missing_file_raises_file_not_found() -> None:
    """Missing corpus file raises FileNotFoundError with path in message."""
    import re
    missing = Path("/nonexistent/path/fingerprints.json")
    with pytest.raises(FileNotFoundError, match=re.escape(str(missing))):
        FallbackFingerprintDetector.from_corpus(missing)


def test_from_corpus_malformed_json_raises_value_error(tmp_path: Path) -> None:
    """Malformed JSON raises ValueError with helpful parse hint."""
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed JSON"):
        FallbackFingerprintDetector.from_corpus(bad)


# ---------------------------------------------------------------------------
# from_corpus happy path
# ---------------------------------------------------------------------------

def test_from_corpus_loads_real_corpus() -> None:
    """from_corpus with the project corpus file loads successfully."""
    detector = FallbackFingerprintDetector.from_corpus(CORPUS_PATH)
    assert detector is not None


def test_corpus_json_structure() -> None:
    """Project corpus JSON has required fields."""
    with open(CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert data["version"] == 1
    assert "provenance" in data
    assert isinstance(data["substring_fingerprints"], list)
    assert len(data["substring_fingerprints"]) >= 4


# ---------------------------------------------------------------------------
# Integration: live fixture from SCRUM-283 artifacts
# ---------------------------------------------------------------------------

def _find_scrum283_max_dir() -> Path:
    """Find the SCRUM-283 Max smoke artifact dir, walking up past git worktree layout."""
    target = "scrum283_unit5b_6book_smoke_qwen_vl_max"
    candidate = Path(__file__).resolve().parent.parent
    for _ in range(4):  # walk up at most 4 levels
        d = candidate / "data" / target
        if d.exists():
            return d
        candidate = candidate.parent
    return Path(__file__).resolve().parent.parent / "data" / target  # not found → skip


SCRUM283_MAX_DIR = _find_scrum283_max_dir()


@pytest.mark.skipif(
    not SCRUM283_MAX_DIR.exists(),
    reason="SCRUM-283 Max smoke artifacts not present",
)
def test_integration_python_max_report_flagged() -> None:
    """Live Python-in-easy-steps Max report: all pages should be flagged via Matcher 3."""
    python_reports = list(SCRUM283_MAX_DIR.glob("Python*.json"))
    assert python_reports, "Python Max report not found in artifact directory"

    with open(python_reports[0], encoding="utf-8") as f:
        report = json.load(f)

    pages = report.get("pages", [])
    assert pages, "No pages in Python Max report"

    detector = FallbackFingerprintDetector.from_corpus(CORPUS_PATH)
    flagged = detector.detect(pages, DEFAULT_SETTINGS)

    # All 8 pages in the Max Python run had issues==[] with scores 85-95.
    # Matcher 3 should flag every page.
    assert len(flagged) == len(pages), (
        f"Expected all {len(pages)} pages flagged via Matcher 3, got {len(flagged)}: {flagged}"
    )


# ---------------------------------------------------------------------------
# Matcher 4 (SCRUM-292): dominant-score uniform response
# ---------------------------------------------------------------------------
# Grounded in A2 pilot evidence: Foucault's Pendulum (8×65, 4 verbatim issues
# per page) and MapReduce (8×85, 1 verbatim issue per page referencing wrong
# page numbers). Mexico Illicit (cover=90, 7×50 on body) from A1 quick mode
# is the mixed-cover case. Statistical matcher: if ≥ page_ratio of pages
# share one integer score AND that count ≥ min_pages, flag the matching
# pages. Does not touch pages at other scores.

SETTINGS_UNIFORM_ONLY = FingerprintSettings(
    empty_issues_score_threshold=80,
    substring_corpus=(),
    match_category_scores_collapse=False,
    match_uniform_score_responses=True,
    uniform_score_page_ratio=0.75,
    uniform_score_min_pages=3,
)


def test_matcher4_foucault_shape_all_pages_flagged() -> None:
    """8 pages all scoring exactly 65 (Foucault pattern) → all 8 flagged."""
    issues = [_make_issue("Minor OCR artifacts", severity="minor")]
    pages = [_make_page(n, score=65, pass_=False, issues=issues) for n in range(1, 9)]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_UNIFORM_ONLY)
    assert result == {1, 2, 3, 4, 5, 6, 7, 8}


def test_matcher4_mapreduce_shape_all_pages_flagged() -> None:
    """8 pages all scoring exactly 85 (MapReduce pattern) → all 8 flagged."""
    issues = [_make_issue("Minor text wrapping issues", severity="minor")]
    pages = [_make_page(n, score=85, pass_=True, issues=issues) for n in (1, 2, 3, 8, 13, 18, 22, 31)]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_UNIFORM_ONLY)
    assert result == {1, 2, 3, 8, 13, 18, 22, 31}


def test_matcher4_mexico_shape_flags_only_matching_pages() -> None:
    """cover=90 + 7 body pages at 50 → 7 body pages flagged, cover NOT flagged."""
    pages = [_make_page(1, score=90, issues=[_make_issue("Cover issue")], page_type="cover")]
    pages += [_make_page(n, score=50, issues=[_make_issue("Body issue")]) for n in range(2, 9)]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_UNIFORM_ONLY)
    assert result == {2, 3, 4, 5, 6, 7, 8}


def test_matcher4_healthy_spread_not_flagged() -> None:
    """Pages with varied scores (no dominant value) → NOT flagged by Matcher 4."""
    pages = [
        _make_page(1, score=90, issues=[_make_issue("Issue A")]),
        _make_page(2, score=65, issues=[_make_issue("Issue B")]),
        _make_page(3, score=70, issues=[_make_issue("Issue C")]),
        _make_page(4, score=85, issues=[_make_issue("Issue D")]),
        _make_page(5, score=50, issues=[_make_issue("Issue E")]),
    ]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_UNIFORM_ONLY)
    assert result == set()


def test_matcher4_boundary_ratio_exactly_075_flagged() -> None:
    """6 of 8 pages share score → ratio 0.75, at threshold inclusive → flagged."""
    pages = [_make_page(n, score=50, issues=[_make_issue("I")]) for n in range(1, 7)]
    pages += [
        _make_page(7, score=80, issues=[_make_issue("Real finding")]),
        _make_page(8, score=75, issues=[_make_issue("Another finding")]),
    ]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_UNIFORM_ONLY)
    assert result == {1, 2, 3, 4, 5, 6}


def test_matcher4_boundary_min_pages_inclusive_flagged() -> None:
    """Exactly 3 matching pages, ratio=1.0 → flagged (min_pages inclusive)."""
    pages = [_make_page(n, score=70, issues=[_make_issue("I")]) for n in (1, 2, 3)]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_UNIFORM_ONLY)
    assert result == {1, 2, 3}


def test_matcher4_below_min_pages_not_flagged() -> None:
    """2 matching pages, ratio=1.0 but count < min_pages=3 → NOT flagged."""
    pages = [_make_page(n, score=70, issues=[_make_issue("I")]) for n in (1, 2)]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_UNIFORM_ONLY)
    assert result == set()


def test_matcher4_tie_no_dominant_not_flagged() -> None:
    """4×80 and 4×65 — neither reaches 0.75 ratio → NOT flagged."""
    pages = [_make_page(n, score=80, issues=[_make_issue("I")]) for n in range(1, 5)]
    pages += [_make_page(n, score=65, issues=[_make_issue("I")]) for n in range(5, 9)]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, SETTINGS_UNIFORM_ONLY)
    assert result == set()


def test_matcher4_disabled_does_not_fire() -> None:
    """match_uniform_score_responses=False → uniform pattern NOT flagged."""
    disabled = FingerprintSettings(
        empty_issues_score_threshold=80,
        substring_corpus=(),
        match_category_scores_collapse=False,
        match_uniform_score_responses=False,
        uniform_score_page_ratio=0.75,
        uniform_score_min_pages=3,
    )
    pages = [_make_page(n, score=65, issues=[_make_issue("I")]) for n in range(1, 9)]
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, disabled)
    assert result == set()


def test_matcher4_composes_with_matcher1_and_matcher2() -> None:
    """Matcher 4 adds to the flag set without replacing 1/2 results.

    Uses 6 stuck pages at 65 + 1 Matcher-1 page + 1 Matcher-2 page = 6/8 at
    score 65 (ratio 0.75 inclusive), so Matcher 4 fires alongside the others.
    """
    settings = FingerprintSettings(
        empty_issues_score_threshold=80,
        substring_corpus=("no action needed",),
        match_category_scores_collapse=False,
        match_uniform_score_responses=True,
        uniform_score_page_ratio=0.75,
        uniform_score_min_pages=3,
    )
    pages = [_make_page(n, score=65, issues=[_make_issue("Stuck response A")])
             for n in range(1, 7)]
    pages.append(_make_page(7, score=95, issues=[]))  # Matcher 1 (empty + high)
    pages.append(_make_page(8, score=70, issues=[_make_issue("no action needed here")]))  # Matcher 2
    detector = FallbackFingerprintDetector(["no action needed"])
    result = detector.detect(pages, settings)
    assert result == {1, 2, 3, 4, 5, 6, 7, 8}


def test_matcher4_backward_compatible_defaults() -> None:
    """FingerprintSettings can be constructed with only the original 3 args (defaults apply)."""
    # The three original matchers still work when the new fields default to safe values.
    settings = FingerprintSettings(
        empty_issues_score_threshold=80,
        substring_corpus=(),
        match_category_scores_collapse=True,
    )
    pages = [_make_page(1, score=95)]  # empty issues + high score → Matcher 1
    detector = FallbackFingerprintDetector([])
    result = detector.detect(pages, settings)
    assert result == {1}


# ---------------------------------------------------------------------------
# Matcher 4 integration: live A2 pilot fixtures
# ---------------------------------------------------------------------------

def _find_a2_pilot_dir() -> Path:
    """Locate the A2 pilot VQA report directory (post-SCRUM-290 outputs)."""
    candidate = Path(__file__).resolve().parent.parent
    for _ in range(4):
        d = candidate / "output" / "kindle"
        if d.exists():
            return d
        candidate = candidate.parent
    return Path(__file__).resolve().parent.parent / "output" / "kindle"


A2_PILOT_DIR = _find_a2_pilot_dir()
FOUCAULT_REPORT = A2_PILOT_DIR / "Microsoft Word - Foucault's Pendulum - Miriam_visual_qa_report.json"
MAPREDUCE_REPORT = A2_PILOT_DIR / "mapreduce-osdi04_visual_qa_report.json"


@pytest.mark.skipif(
    not FOUCAULT_REPORT.exists(),
    reason="Foucault A2 pilot report not present",
)
def test_integration_foucault_a2_report_flagged() -> None:
    """Live Foucault report from A2 pilot: 8×65 → Matcher 4 flags all 8 pages."""
    with open(FOUCAULT_REPORT, encoding="utf-8") as f:
        report = json.load(f)
    pages = report.get("pages", [])
    assert pages, "No pages in Foucault report"

    detector = FallbackFingerprintDetector.from_corpus(CORPUS_PATH)
    flagged = detector.detect(pages, SETTINGS_UNIFORM_ONLY)

    assert len(flagged) == len(pages), (
        f"Expected all {len(pages)} Foucault pages flagged via Matcher 4, "
        f"got {len(flagged)}: {sorted(flagged)}"
    )


@pytest.mark.skipif(
    not MAPREDUCE_REPORT.exists(),
    reason="MapReduce A2 pilot report not present",
)
def test_integration_mapreduce_a2_report_flagged() -> None:
    """Live MapReduce report from A2 pilot: 8×85 → Matcher 4 flags all 8 pages."""
    with open(MAPREDUCE_REPORT, encoding="utf-8") as f:
        report = json.load(f)
    pages = report.get("pages", [])
    assert pages, "No pages in MapReduce report"

    detector = FallbackFingerprintDetector.from_corpus(CORPUS_PATH)
    flagged = detector.detect(pages, SETTINGS_UNIFORM_ONLY)

    assert len(flagged) == len(pages), (
        f"Expected all {len(pages)} MapReduce pages flagged via Matcher 4, "
        f"got {len(flagged)}: {sorted(flagged)}"
    )
