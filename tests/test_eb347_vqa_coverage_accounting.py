#!/usr/bin/env python3
"""EB-347 coverage-accounting tests for large-file VQA reduction."""

from __future__ import annotations

import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import visual_qa


class _Provider:
    def estimate_cost(self, model, input_tokens, output_tokens):
        return 0.0


def test_build_report_records_requested_vs_effective_coverage():
    report = visual_qa.build_report(
        "Book.kfx",
        {
            "evaluation_status": "evaluated",
            "overall_score": 90,
            "pages": [
                {"page_number": 1, "score": 90, "issues": []},
                {"page_number": 2, "score": 90, "issues": []},
                {"page_number": 3, "score": 90, "issues": []},
                {"page_number": 4, "score": 90, "issues": []},
            ],
        },
        total_pages=600,
        pages_sampled=4,
        dpi=72,
        model="qwen",
        input_tokens=0,
        output_tokens=0,
        provider=_Provider(),
        pages_requested=40,
        requested_dpi=150,
        coverage_loss_warning="Large-file auto-reduction applied",
    )

    # EB-347: a 40-page request reduced to 4 rendered pages is PARTIAL coverage,
    # not "complete" — coverage_status is judged against pages_requested (40),
    # not pages_sampled (4). (Regression: previously reported "complete".)
    assert report["coverage_status"] == "partial"
    assert report["pages_requested"] == 40
    assert report["pages_rendered"] == 4
    assert report["requested_dpi"] == 150
    assert report["effective_dpi"] == 72
    assert report["coverage_loss_warning"] == "Large-file auto-reduction applied"


def test_large_file_explicit_values_are_not_clamped():
    dpi, max_pages = visual_qa._apply_large_file_dpi_reduction(
        kfx_size_bytes=31 * 1024 * 1024,
        total_pages=600,
        dpi=150,
        max_pages=40,
        user_supplied_dpi=True,
        user_supplied_max_pages=True,
    )

    assert dpi == 150
    assert max_pages == 40


def _evaluated_report(pages_in_result, pages_sampled, pages_requested,
                      total_pages=100, coverage_loss_warning=None):
    """Build an 'evaluated' report with `pages_in_result` page entries."""
    return visual_qa.build_report(
        "Book.kfx",
        {
            "evaluation_status": "evaluated",
            "overall_score": 90,
            "pages": [
                {"page_number": i + 1, "score": 90, "issues": []}
                for i in range(pages_in_result)
            ],
        },
        total_pages=total_pages,
        pages_sampled=pages_sampled,
        dpi=100,
        model="qwen",
        input_tokens=0,
        output_tokens=0,
        provider=_Provider(),
        pages_requested=pages_requested,
        requested_dpi=100,
        coverage_loss_warning=coverage_loss_warning,
    )


def test_full_run_is_complete():
    # 8 requested, 8 sampled, 8 evaluated, no reduction -> complete.
    report = _evaluated_report(8, pages_sampled=8, pages_requested=8)
    assert report["coverage_status"] == "complete"


def test_short_book_not_false_partial():
    # Book shorter than the request: pages_requested = min(8, total) = 5.
    # All 5 sampled + evaluated -> complete (full coverage of a short book),
    # NOT mis-flagged partial just because fewer than the nominal 8 were seen.
    report = _evaluated_report(5, pages_sampled=5, pages_requested=5, total_pages=5)
    assert report["coverage_status"] == "complete"


def test_eval_gap_is_partial():
    # 8 sampled but only 6 returned valid results (truncation/parse gap) -> partial.
    report = _evaluated_report(6, pages_sampled=8, pages_requested=8)
    assert report["coverage_status"] == "partial"


def test_legacy_none_pages_requested_falls_back_to_sampled():
    # Legacy callers pass pages_requested=None -> compare against pages_sampled.
    report = _evaluated_report(4, pages_sampled=4, pages_requested=None)
    assert report["coverage_status"] == "complete"
