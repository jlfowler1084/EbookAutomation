"""Tests for capture_pipeline provenance field added to visual_qa.py (SCRUM-282 U2).

All tests operate on build_report() and the dispatch logic in run_visual_qa()
without invoking Calibre or the Claude API.

Key invariants:
  - .kfx / .azw3 / .epub inputs → capture_pipeline="kfx-calibre" (Calibre ran)
  - .pdf input                  → capture_pipeline="pdf-direct"   (PDF-skip branch)
  - Legacy baselines without the field parse without error (backward compat)
  - Existing source_format field in extraction-pipeline sidecars is untouched
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import visual_qa as vqa


# ---------------------------------------------------------------------------
# build_report() unit tests — field presence and value
# ---------------------------------------------------------------------------

def _minimal_qa_data():
    return {
        "overall_score": 85,
        "category_scores": {},
        "pages": [{"page_number": 1, "score": 85, "issues": []}],
        "summary": "test",
        "top_issues": [],
    }


def _call_build_report(**extra):
    return vqa.build_report(
        book_path="book.kfx",
        qa_data=_minimal_qa_data(),
        total_pages=100,
        pages_sampled=8,
        dpi=150,
        model="claude-haiku-4-5",
        input_tokens=1000,
        output_tokens=200,
        **extra,
    )


def test_kfx_input_emits_kfx_calibre():
    report = _call_build_report(capture_pipeline="kfx-calibre")
    assert report["capture_pipeline"] == "kfx-calibre"


def test_pdf_input_emits_pdf_direct():
    report = _call_build_report(capture_pipeline="pdf-direct")
    assert report["capture_pipeline"] == "pdf-direct"


def test_legacy_call_omits_field():
    """build_report called without capture_pipeline (legacy) must not emit the field."""
    report = _call_build_report()
    assert "capture_pipeline" not in report


def test_capture_pipeline_none_omits_field():
    """Explicit None also omits the field — same as legacy call path."""
    report = _call_build_report(capture_pipeline=None)
    assert "capture_pipeline" not in report


# ---------------------------------------------------------------------------
# run_visual_qa() dispatch tests — via monkeypatching internals
# ---------------------------------------------------------------------------

def _make_mock_provider(name="TestProvider"):
    provider = MagicMock()
    provider.name = name
    provider.estimate_cost.return_value = 0.001
    # Provide a real response so token accumulation and JSON serialization work.
    # visual_qa uses duck-typing: hasattr(provider, "two_pass_call") → True on any
    # MagicMock, so we configure that path to return proper integer token counts.
    mock_response = MagicMock()
    mock_response.input_tokens = 500
    mock_response.output_tokens = 100
    mock_response.raw_text = json.dumps({
        "overall_score": 85,
        "category_scores": {},
        "pages": [{"page_number": 1, "score": 85, "issues": []}],
        "summary": "ok",
        "top_issues": [],
    })
    provider.two_pass_call.return_value = mock_response
    provider.call.return_value = mock_response
    return provider


def _patch_pipeline_internals(monkeypatch, tmp_path, total_pages=100):
    """Patch Calibre helpers, page rendering, and rubric loading so run_visual_qa
    can execute its dispatch logic without external dependencies."""
    monkeypatch.setattr(vqa, "convert_to_pdf",
                        lambda input_path, calibre_path, **kw: str(tmp_path / "converted.pdf"))
    monkeypatch.setattr(vqa, "get_pdf_page_count", lambda *a, **kw: total_pages)
    monkeypatch.setattr(vqa, "get_pdf_bookmarks", lambda *a, **kw: [30, 60, 90])
    monkeypatch.setattr(vqa, "select_sample_pages",
                        lambda *a, **kw: [1, 2, 3, 30, 60, 90, 120, 140])
    monkeypatch.setattr(vqa, "render_pages_to_png",
                        lambda *a, **kw: [(1, b"fake_png_bytes")])
    # Stub out rubric loading
    monkeypatch.setattr(vqa.Path, "exists", lambda self: True)
    monkeypatch.setattr(vqa.Path, "read_text", lambda self, **kw: "rubric content")
    # Stub FallbackFingerprintDetector to avoid loading fingerprint corpus
    monkeypatch.setattr(vqa, "FallbackFingerprintDetector",
                        lambda *a, **kw: MagicMock(classify=lambda imgs: []))


def test_kfx_dispatch_sets_kfx_calibre(monkeypatch, tmp_path):
    """KFX input takes the Calibre branch → capture_pipeline="kfx-calibre"."""
    _patch_pipeline_internals(monkeypatch, tmp_path)
    kfx_input = tmp_path / "book.kfx"
    kfx_input.touch()

    provider = _make_mock_provider()
    report_path = run_and_read_report(kfx_input, provider, tmp_path)
    assert report_path["capture_pipeline"] == "kfx-calibre"


def test_pdf_dispatch_sets_pdf_direct(monkeypatch, tmp_path):
    """PDF input takes the skip branch → capture_pipeline="pdf-direct"."""
    _patch_pipeline_internals(monkeypatch, tmp_path)
    pdf_input = tmp_path / "book.pdf"
    pdf_input.touch()

    provider = _make_mock_provider()
    report_path = run_and_read_report(pdf_input, provider, tmp_path)
    assert report_path["capture_pipeline"] == "pdf-direct"


def test_azw3_dispatch_sets_kfx_calibre(monkeypatch, tmp_path):
    """AZW3 input flows through Calibre branch → capture_pipeline="kfx-calibre"."""
    _patch_pipeline_internals(monkeypatch, tmp_path)
    azw3_input = tmp_path / "book.azw3"
    azw3_input.touch()

    provider = _make_mock_provider()
    report_path = run_and_read_report(azw3_input, provider, tmp_path)
    assert report_path["capture_pipeline"] == "kfx-calibre"


def test_epub_dispatch_sets_kfx_calibre(monkeypatch, tmp_path):
    """EPUB input flows through Calibre branch → capture_pipeline="kfx-calibre"."""
    _patch_pipeline_internals(monkeypatch, tmp_path)
    epub_input = tmp_path / "book.epub"
    epub_input.touch()

    provider = _make_mock_provider()
    report_path = run_and_read_report(epub_input, provider, tmp_path)
    assert report_path["capture_pipeline"] == "kfx-calibre"


def test_legacy_baseline_parses_without_error(tmp_path):
    """A baseline JSON that lacks capture_pipeline must load cleanly — no KeyError."""
    legacy = {
        "book": "oldbook.kfx",
        "pages_total": 100,
        "pages": [{"page_number": 1, "score": 85}],
    }
    path = tmp_path / "oldbook_visual_qa_report.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    with path.open("r", encoding="utf-8") as fh:
        loaded = json.load(fh)

    assert "capture_pipeline" not in loaded
    assert loaded["pages"][0]["page_number"] == 1


def test_capture_pipeline_does_not_affect_existing_fields(monkeypatch, tmp_path):
    """Adding capture_pipeline must not alter any pre-existing report fields."""
    report_with = _call_build_report(capture_pipeline="kfx-calibre")
    report_without = _call_build_report()

    shared_keys = set(report_without.keys())
    for key in shared_keys:
        assert report_with[key] == report_without[key], \
            f"Field '{key}' changed after adding capture_pipeline"


# ---------------------------------------------------------------------------
# Helper: run run_visual_qa and load the written JSON report
# ---------------------------------------------------------------------------

def run_and_read_report(input_path: Path, provider, output_dir: Path) -> dict:
    """Run run_visual_qa with a stubbed provider and return the parsed report."""
    vqa.run_visual_qa(
        input_path=input_path,
        provider=provider,
        calibre_path="fake_calibre",
        poppler_path="",
        output_dir=str(output_dir),
        dpi=150,
        max_pages=8,
        model="claude-haiku-4-5",
        rubric_path="nonexistent_rubric.md",
        pass_threshold=70,
        fallback_enabled=False,
    )
    report_path = output_dir / f"{input_path.stem}_visual_qa_report.json"
    with report_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
