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
)

SETTINGS_NO_COLLAPSE = FingerprintSettings(
    empty_issues_score_threshold=80,
    substring_corpus=("text is clean and readable with no visible artifacts",
                      "no action needed"),
    match_category_scores_collapse=False,
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
