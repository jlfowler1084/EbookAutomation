"""Tests for the audit subcommand added to compare_vqa_reports.py (SCRUM-282 U1).

All tests monkeypatch convert_to_pdf, get_pdf_page_count, get_pdf_bookmarks,
and select_sample_pages in the compare_vqa_reports module namespace to avoid
invoking Calibre.

Fixtures live in tests/fixtures/vqa_baseline_audit/:
  atomic_habits_drift.json  — PDF-sourced baseline; pages don't match KFX sample
  partial_overlap.json      — partial page-list mismatch
  clean_parity.json         — pages exactly match KFX sample
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pytest

# Add tools/ to sys.path so compare_vqa_reports is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import compare_vqa_reports as cvqa

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vqa_baseline_audit"

_DRIFT_BASELINE_PAGES = [1, 2, 3, 73, 92, 145, 158, 232]
_DRIFT_EXPECTED_PAGES = [1, 2, 3, 91, 94, 149, 152, 238]
_PARITY_PAGES = [1, 2, 3, 30, 60, 90, 120, 140]
_PARTIAL_BASELINE_PAGES = [1, 2, 3, 50, 100, 150, 175, 190]
_PARTIAL_EXPECTED_PAGES = [1, 2, 3, 50, 100, 160, 180, 195]


def _make_args(baseline_dir, kfx_dir, calibre="fake_calibre_path"):
    return argparse.Namespace(
        baseline_dir=Path(baseline_dir),
        kfx_dir=Path(kfx_dir),
        calibre=calibre,
        verbose=False,
    )


def _install_fixture(src_json: str, dest_dir: Path, stem: str) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / src_json, dest_dir / f"{stem}{cvqa._REPORT_SUFFIX}")


def _make_kfx_dir(tmp_path: Path, *stems: str) -> Path:
    kfx_dir = tmp_path / "kindle"
    kfx_dir.mkdir(exist_ok=True)
    for stem in stems:
        (kfx_dir / f"{stem}.kfx").touch()
    return kfx_dir


# ---------------------------------------------------------------------------
# Happy path: clean parity → exit 0
# ---------------------------------------------------------------------------

def test_clean_parity_exits_zero(monkeypatch, tmp_path):
    baseline_dir = tmp_path / "baseline"
    _install_fixture("clean_parity.json", baseline_dir, "clean_parity_test")
    kfx_dir = _make_kfx_dir(tmp_path, "clean_parity_test")

    monkeypatch.setattr(cvqa, "convert_to_pdf", lambda *a, **kw: "/fake/clean.pdf")
    monkeypatch.setattr(cvqa, "get_pdf_page_count", lambda *a, **kw: 150)
    monkeypatch.setattr(cvqa, "get_pdf_bookmarks", lambda *a, **kw: [30, 60, 90, 120])
    monkeypatch.setattr(cvqa, "select_sample_pages", lambda *a, **kw: list(_PARITY_PAGES))

    result = cvqa._cmd_audit(_make_args(baseline_dir, kfx_dir))
    assert result == 0


# ---------------------------------------------------------------------------
# Error path: drift fixture → exit 2 (mismatch), diff table present
# ---------------------------------------------------------------------------

def test_atomic_habits_drift_exits_two(monkeypatch, tmp_path, capsys):
    baseline_dir = tmp_path / "baseline"
    _install_fixture("atomic_habits_drift.json", baseline_dir, "atomic_habits_drift_test")
    kfx_dir = _make_kfx_dir(tmp_path, "atomic_habits_drift_test")

    monkeypatch.setattr(cvqa, "convert_to_pdf", lambda *a, **kw: "/fake/ah.pdf")
    monkeypatch.setattr(cvqa, "get_pdf_page_count", lambda *a, **kw: 272)
    monkeypatch.setattr(cvqa, "get_pdf_bookmarks", lambda *a, **kw: [91, 94, 149, 152])
    monkeypatch.setattr(cvqa, "select_sample_pages", lambda *a, **kw: list(_DRIFT_EXPECTED_PAGES))

    result = cvqa._cmd_audit(_make_args(baseline_dir, kfx_dir))
    assert result == 2

    out = capsys.readouterr().out
    assert "mismatch" in out
    assert "atomic_habits_drift_test" in out


# ---------------------------------------------------------------------------
# Edge case: baseline missing pages[].page_number → exit 2, no silent pass
# ---------------------------------------------------------------------------

def test_missing_page_numbers_exits_two(monkeypatch, tmp_path, capsys):
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    kfx_dir = _make_kfx_dir(tmp_path, "malformed_test")

    malformed = {
        "book": "malformed_test.kfx",
        "pages_total": 100,
        "pages": [{"score": 80}, {"score": 75}],
    }
    (baseline_dir / f"malformed_test{cvqa._REPORT_SUFFIX}").write_text(
        json.dumps(malformed), encoding="utf-8"
    )

    result = cvqa._cmd_audit(_make_args(baseline_dir, kfx_dir))
    assert result == 2

    out = capsys.readouterr().out
    assert "malformed_test" in out


# ---------------------------------------------------------------------------
# Edge case: no matching KFX → exit 1 (skipped, no mismatch)
# ---------------------------------------------------------------------------

def test_no_matching_kfx_exits_one(monkeypatch, tmp_path):
    baseline_dir = tmp_path / "baseline"
    _install_fixture("clean_parity.json", baseline_dir, "clean_parity_test")
    kfx_dir = tmp_path / "empty_kindle"
    kfx_dir.mkdir()

    result = cvqa._cmd_audit(_make_args(baseline_dir, kfx_dir))
    assert result == 1


# ---------------------------------------------------------------------------
# Edge case: partial page mismatch → exit 2 (mismatch)
# ---------------------------------------------------------------------------

def test_partial_overlap_exits_two(monkeypatch, tmp_path):
    baseline_dir = tmp_path / "baseline"
    _install_fixture("partial_overlap.json", baseline_dir, "partial_overlap_test")
    kfx_dir = _make_kfx_dir(tmp_path, "partial_overlap_test")

    monkeypatch.setattr(cvqa, "convert_to_pdf", lambda *a, **kw: "/fake/partial.pdf")
    monkeypatch.setattr(cvqa, "get_pdf_page_count", lambda *a, **kw: 200)
    monkeypatch.setattr(cvqa, "get_pdf_bookmarks", lambda *a, **kw: [50, 100, 160])
    monkeypatch.setattr(cvqa, "select_sample_pages", lambda *a, **kw: list(_PARTIAL_EXPECTED_PAGES))

    result = cvqa._cmd_audit(_make_args(baseline_dir, kfx_dir))
    assert result == 2


# ---------------------------------------------------------------------------
# Exit-code priority: mismatch beats skipped → exit 2
# ---------------------------------------------------------------------------

def test_mismatch_beats_skipped(monkeypatch, tmp_path):
    baseline_dir = tmp_path / "baseline"
    kfx_dir = tmp_path / "kindle"
    kfx_dir.mkdir()

    # drift_test has matching KFX → will mismatch
    _install_fixture("atomic_habits_drift.json", baseline_dir, "atomic_habits_drift_test")
    (kfx_dir / "atomic_habits_drift_test.kfx").touch()

    # clean_parity_test has NO matching KFX → will be skipped
    _install_fixture("clean_parity.json", baseline_dir, "clean_parity_test")

    monkeypatch.setattr(cvqa, "convert_to_pdf", lambda *a, **kw: "/fake/ah.pdf")
    monkeypatch.setattr(cvqa, "get_pdf_page_count", lambda *a, **kw: 272)
    monkeypatch.setattr(cvqa, "get_pdf_bookmarks", lambda *a, **kw: [91, 94, 149, 152])
    monkeypatch.setattr(cvqa, "select_sample_pages", lambda *a, **kw: list(_DRIFT_EXPECTED_PAGES))

    result = cvqa._cmd_audit(_make_args(baseline_dir, kfx_dir))
    assert result == 2


# ---------------------------------------------------------------------------
# Integration: existing compare CLI path still works (no subcommand given)
# ---------------------------------------------------------------------------

def test_existing_compare_mode_unchanged(monkeypatch, tmp_path):
    """Legacy bare invocation --candidate/--baseline still routes to compare."""
    cand_dir = tmp_path / "candidate"
    base_dir = tmp_path / "baseline"
    cand_dir.mkdir()
    base_dir.mkdir()

    report = {"pages": [{"page_number": 1, "score": 85, "issues": []}]}
    for d in (cand_dir, base_dir):
        (d / f"mybook{cvqa._REPORT_SUFFIX}").write_text(json.dumps(report), "utf-8")

    monkeypatch.setattr(
        sys, "argv",
        ["compare_vqa_reports.py", "--candidate", str(cand_dir), "--baseline", str(base_dir)],
    )

    result = cvqa.main()
    assert result in (0, 1)


def test_compare_subcommand_explicit(monkeypatch, tmp_path):
    """Explicit 'compare' subcommand also works."""
    cand_dir = tmp_path / "cand"
    base_dir = tmp_path / "base"
    cand_dir.mkdir()
    base_dir.mkdir()

    report = {"pages": [{"page_number": 5, "score": 90, "issues": []}]}
    for d in (cand_dir, base_dir):
        (d / f"abook{cvqa._REPORT_SUFFIX}").write_text(json.dumps(report), "utf-8")

    monkeypatch.setattr(
        sys, "argv",
        ["compare_vqa_reports.py", "compare",
         "--candidate", str(cand_dir), "--baseline", str(base_dir)],
    )

    result = cvqa.main()
    assert result in (0, 1)
