"""Tests for tools/analyze_vqa_mode_classification.py (SCRUM-280 Unit 1).

All inputs are deterministic JSON fixtures — no network calls, no filesystem.
Run with: py -3.12 -m pytest tests/test_vqa_mode_classifier.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from analyze_vqa_mode_classification import classify_mode  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_issue(severity: str, category: str = "text_integrity") -> dict:
    return {
        "category": category,
        "severity": severity,
        "description": "test issue",
        "suggestion": "fix it",
    }


def _make_page(
    page_number: int,
    score: int,
    issues: list[dict] | None = None,
    page_type: str = "body",
) -> dict:
    return {
        "page_number": page_number,
        "page_type": page_type,
        "score": score,
        "pass": score >= 70,
        "issues": issues or [],
    }


def _make_report(pages: list[dict], model: str = "test-model") -> dict:
    return {
        "book": "test_book.kfx",
        "model": model,
        "pages_sampled": len(pages),
        "overall_score": sum(p["score"] for p in pages) // len(pages) if pages else 0,
        "pages": pages,
        "top_issues": [],
        "summary": "test",
    }


# ---------------------------------------------------------------------------
# Happy path — clean mode (a): grading bias
# Local detects non-minor issues but still scores high (inflated grade).
# ---------------------------------------------------------------------------


def test_classify_mode_a_all_pages_have_nonminor_issues() -> None:
    """8 pages all score >= 95, all have moderate severity locally → mode='a'."""
    pages = [
        _make_page(i, 95, issues=[_make_issue("moderate")])
        for i in range(1, 9)
    ]
    local = _make_report(pages)
    claude = _make_report([
        _make_page(i, 70, issues=[_make_issue("critical")])
        for i in range(1, 9)
    ], model="claude-sonnet-4-6")

    result = classify_mode(local, claude)

    assert result["mode"] == "a"


def test_classify_mode_a_critical_local_severity_also_classifies_a() -> None:
    """Critical local severity (not just moderate) still produces mode='a'."""
    pages = [_make_page(i, 97, issues=[_make_issue("critical")]) for i in range(1, 9)]
    local = _make_report(pages)
    claude = _make_report([_make_page(i, 60, issues=[_make_issue("critical")]) for i in range(1, 9)],
                          model="claude-sonnet-4-6")
    result = classify_mode(local, claude)
    assert result["mode"] == "a"


# ---------------------------------------------------------------------------
# Happy path — clean mode (b): detection failure
# Local misses issues (empty or only minor) that Claude finds.
# ---------------------------------------------------------------------------


def test_classify_mode_b_empty_local_issues_claude_flags_critical() -> None:
    """8 pages score >= 95, local issues empty, Claude flags critical → mode='b'."""
    pages = [_make_page(i, 96, issues=[]) for i in range(1, 9)]
    local = _make_report(pages)
    claude = _make_report([
        _make_page(i, 50, issues=[_make_issue("critical")])
        for i in range(1, 9)
    ], model="claude-sonnet-4-6")

    result = classify_mode(local, claude)

    assert result["mode"] == "b"


def test_classify_mode_b_only_minor_local_claude_moderate() -> None:
    """Local issues all minor, Claude finds moderate → per-page mode='b'."""
    pages = [_make_page(i, 90, issues=[_make_issue("minor")]) for i in range(1, 9)]
    local = _make_report(pages)
    claude = _make_report([
        _make_page(i, 70, issues=[_make_issue("moderate")])
        for i in range(1, 9)
    ], model="claude-sonnet-4-6")

    result = classify_mode(local, claude)

    assert result["mode"] == "b"


def test_classify_mode_b_claude_major_treated_as_nonminor() -> None:
    """Claude 'major' severity (not in local rubric enum) still triggers mode='b' indicator."""
    pages = [_make_page(i, 95, issues=[]) for i in range(1, 9)]
    local = _make_report(pages)
    claude = _make_report([
        _make_page(i, 65, issues=[_make_issue("major")])
        for i in range(1, 9)
    ], model="claude-sonnet-4-6")

    result = classify_mode(local, claude)

    assert result["mode"] == "b"


# ---------------------------------------------------------------------------
# Per-page breakdown fields
# ---------------------------------------------------------------------------


def test_per_page_breakdown_contains_required_fields() -> None:
    """Every PageBreakdown must have all required fields per the plan spec."""
    local = _make_report([_make_page(1, 95, [_make_issue("moderate")])])
    claude = _make_report([_make_page(1, 60, [_make_issue("critical")])], model="claude-sonnet-4-6")

    result = classify_mode(local, claude)

    assert len(result["per_page"]) == 1
    page = result["per_page"][0]
    for field in (
        "page_number", "local_score", "claude_score",
        "local_issues_count", "claude_issues_count",
        "local_has_nonminor_severity", "claude_has_critical_or_moderate",
        "per_page_classification",
    ):
        assert field in page, f"Missing field: {field}"


def test_per_page_classification_a_when_local_has_moderate() -> None:
    """A page with high local score and local moderate issue classifies as 'a'."""
    local = _make_report([_make_page(42, 92, [_make_issue("moderate")])])
    claude = _make_report([_make_page(42, 70, [_make_issue("critical")])], model="claude-sonnet-4-6")

    result = classify_mode(local, claude)

    pg = result["per_page"][0]
    assert pg["per_page_classification"] == "a"
    assert pg["local_has_nonminor_severity"] is True
    assert pg["local_score"] == 92
    assert pg["claude_score"] == 70


def test_per_page_classification_b_when_local_empty_claude_moderate() -> None:
    """A page where local has no issues but Claude finds moderate → per-page 'b'."""
    local = _make_report([_make_page(5, 95, [])])
    claude = _make_report([_make_page(5, 72, [_make_issue("moderate")])], model="claude-sonnet-4-6")

    result = classify_mode(local, claude)

    pg = result["per_page"][0]
    assert pg["per_page_classification"] == "b"
    assert pg["local_has_nonminor_severity"] is False
    assert pg["claude_has_critical_or_moderate"] is True


def test_per_page_classification_ambiguous_when_both_agree_page_ok() -> None:
    """When both local and Claude find only minor issues, page is ambiguous."""
    local = _make_report([_make_page(1, 90, [_make_issue("minor")])])
    claude = _make_report([_make_page(1, 88, [_make_issue("minor")])], model="claude-sonnet-4-6")

    result = classify_mode(local, claude)

    assert result["per_page"][0]["per_page_classification"] == "ambiguous"


def test_per_page_issues_count_accurate() -> None:
    """local_issues_count and claude_issues_count reflect actual issue list lengths."""
    local = _make_report([_make_page(1, 90, [_make_issue("moderate"), _make_issue("minor")])])
    claude = _make_report([_make_page(1, 70, [_make_issue("critical"), _make_issue("moderate"), _make_issue("minor")])],
                          model="claude-sonnet-4-6")

    result = classify_mode(local, claude)

    pg = result["per_page"][0]
    assert pg["local_issues_count"] == 2
    assert pg["claude_issues_count"] == 3


# ---------------------------------------------------------------------------
# Aggregate fields
# ---------------------------------------------------------------------------


def test_aggregate_fields_present() -> None:
    """Aggregate dict must contain pct_mode_a, pct_mode_b, pct_ambiguous, high_scoring_page_count."""
    local = _make_report([_make_page(1, 95, [_make_issue("moderate")])])
    claude = _make_report([_make_page(1, 70, [_make_issue("critical")])], model="claude-sonnet-4-6")

    result = classify_mode(local, claude)

    agg = result["aggregate"]
    for field in ("pct_mode_a", "pct_mode_b", "pct_ambiguous", "high_scoring_page_count"):
        assert field in agg, f"Missing aggregate field: {field}"


def test_aggregate_percentages_sum_to_one() -> None:
    """pct_mode_a + pct_mode_b + pct_ambiguous == 1.0 within floating point tolerance."""
    pages_local = [
        _make_page(1, 95, [_make_issue("moderate")]),  # a
        _make_page(2, 95, []),  # b (claude has critical)
        _make_page(3, 90, [_make_issue("minor")]),  # ambiguous
    ]
    pages_claude = [
        _make_page(1, 70, [_make_issue("critical")]),
        _make_page(2, 50, [_make_issue("critical")]),
        _make_page(3, 85, [_make_issue("minor")]),
    ]
    result = classify_mode(_make_report(pages_local), _make_report(pages_claude, model="claude-sonnet-4-6"))

    agg = result["aggregate"]
    total = agg["pct_mode_a"] + agg["pct_mode_b"] + agg["pct_ambiguous"]
    assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Edge cases — per-book verdicts are independent of cross-book aggregation
# ---------------------------------------------------------------------------


def test_per_book_mode_independent_of_other_books() -> None:
    """A book with 5 mode-a and 3 empty local pages is classified on its own pages."""
    pages_local = (
        [_make_page(i, 95, [_make_issue("moderate")]) for i in range(1, 6)]  # 5 mode-a
        + [_make_page(i, 95, []) for i in range(6, 9)]  # 3 potential-b
    )
    pages_claude = (
        [_make_page(i, 70, [_make_issue("critical")]) for i in range(1, 6)]
        + [_make_page(i, 80, [_make_issue("minor")]) for i in range(6, 9)]  # only minor → ambiguous
    )
    result = classify_mode(
        _make_report(pages_local),
        _make_report(pages_claude, model="claude-sonnet-4-6"),
    )
    # 5/8 = 62.5% mode-a → between 55-70% → dominant-a
    assert result["mode"] == "dominant-a"
    # Aggregate should show the per-book breakdown
    assert result["aggregate"]["pct_mode_a"] == pytest.approx(5 / 8)


def test_mixed_book_below_55pct_threshold() -> None:
    """When neither mode reaches 55%, the book is classified as 'mixed'."""
    pages_local = (
        [_make_page(i, 95, [_make_issue("moderate")]) for i in range(1, 4)]  # 3 a
        + [_make_page(i, 95, []) for i in range(4, 7)]  # 3 b (claude flags moderate)
        + [_make_page(i, 90, [_make_issue("minor")]) for i in range(7, 9)]  # 2 ambiguous
    )
    pages_claude = (
        [_make_page(i, 65, [_make_issue("critical")]) for i in range(1, 4)]
        + [_make_page(i, 60, [_make_issue("moderate")]) for i in range(4, 7)]
        + [_make_page(i, 85, [_make_issue("minor")]) for i in range(7, 9)]
    )
    result = classify_mode(
        _make_report(pages_local),
        _make_report(pages_claude, model="claude-sonnet-4-6"),
    )
    # 3/8 = 37.5% each — below 55% threshold for both → mixed
    assert result["mode"] == "mixed"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_raises_value_error_on_page_count_mismatch() -> None:
    """Different page counts between local and Claude → ValueError with both counts."""
    local = _make_report([_make_page(i, 95, []) for i in range(1, 9)])  # 8 pages
    claude = _make_report([_make_page(i, 70, [_make_issue("critical")]) for i in range(1, 4)],
                          model="claude-sonnet-4-6")  # 3 pages

    with pytest.raises(ValueError, match="8") as exc_info:
        classify_mode(local, claude)

    # Both counts must appear in the message
    assert "3" in str(exc_info.value)


def test_raises_value_error_message_contains_both_counts() -> None:
    """ValueError message contains both the local count and the claude count."""
    local = _make_report([_make_page(i, 95, []) for i in range(1, 222)])  # 221 pages (hallucination)
    claude = _make_report([_make_page(i, 80, [_make_issue("minor")]) for i in range(1, 9)],
                          model="claude-sonnet-4-6")  # 8 pages

    with pytest.raises(ValueError) as exc_info:
        classify_mode(local, claude)

    msg = str(exc_info.value)
    assert "221" in msg
    assert "8" in msg


# ---------------------------------------------------------------------------
# Positional matching (for grounding-failure books where page_numbers differ)
# ---------------------------------------------------------------------------


def test_matching_is_positional_not_by_page_number() -> None:
    """Local output positional page_numbers vs Claude's actual markers — match by index."""
    # Simulate Oil Kings / Decline of the West: local has [1,2,3,4,5,6,7,8]
    # but Claude has [1,2,3,119,229,354,360,573]
    local_pages = [
        _make_page(i, 95, [_make_issue("minor")])  # local positional numbers
        for i in range(1, 9)
    ]
    claude_pages = [
        _make_page(pn, 70, [_make_issue("critical")])  # Claude actual markers
        for pn in [1, 2, 3, 119, 229, 354, 360, 573]
    ]
    result = classify_mode(_make_report(local_pages), _make_report(claude_pages, model="claude-sonnet-4-6"))

    # local page_number in per_page should be what local reported (positional)
    # claude page_number should be what claude reported (actual marker)
    assert result["per_page"][3]["local_score"] == 95
    assert result["per_page"][3]["claude_score"] == 70
    # page number from claude (actual marker)
    assert result["per_page"][3]["page_number"] == 119


# ---------------------------------------------------------------------------
# JSON serializability
# ---------------------------------------------------------------------------


def test_result_is_json_serializable() -> None:
    """ClassificationResult dict must round-trip through json.dumps without error."""
    local = _make_report([_make_page(i, 90, [_make_issue("moderate")]) for i in range(1, 9)])
    claude = _make_report([_make_page(i, 65, [_make_issue("critical")]) for i in range(1, 9)],
                          model="claude-sonnet-4-6")
    result = classify_mode(local, claude)
    serialized = json.dumps(result)
    assert json.loads(serialized) == result
