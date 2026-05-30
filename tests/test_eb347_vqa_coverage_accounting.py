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

    assert report["coverage_status"] == "complete"
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
