"""Regression tests for SCRUM-294.

Contract: ``run_kfx_conversion_for_book`` must not report success when
Calibre exits 0 with a parseable path but the produced KFX is missing or
0 bytes. The batch classifier relies on ``kindle_conversion.success`` to
route a book to PASS/WARN/FAIL — a silent 0-byte success (seen on Drug
War Zone, Campbell 2009) was classified PASS while VQA was skipped.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import batch_qa


def _completed_process(stdout: str, returncode: int = 0, stderr: str = ""):
    mock = MagicMock(spec=subprocess.CompletedProcess)
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


# ---------------------------------------------------------------------------
# run_kfx_conversion_for_book — producer contract
# ---------------------------------------------------------------------------


def test_zero_byte_kfx_is_failure(tmp_path, monkeypatch):
    """Calibre exit 0 + path match with a 0-byte .kfx MUST return success=False."""
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"fake pdf")
    kfx = tmp_path / "book.kfx"
    kfx.write_bytes(b"")  # 0 bytes — the bug condition

    monkeypatch.setattr(
        batch_qa.subprocess,
        "run",
        lambda *a, **kw: _completed_process(f"done -> {kfx}\n"),
    )

    success, kfx_path, _duration = batch_qa.run_kfx_conversion_for_book(pdf)
    assert success is False, "0-byte KFX must not be reported as success"
    assert kfx_path == str(kfx), "path should still be returned for diagnostics"


def test_missing_kfx_is_failure(tmp_path, monkeypatch):
    """If the reported KFX path does not exist on disk, treat as failure."""
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"fake pdf")
    missing = tmp_path / "never_created.kfx"

    monkeypatch.setattr(
        batch_qa.subprocess,
        "run",
        lambda *a, **kw: _completed_process(f"done -> {missing}\n"),
    )

    success, _kfx_path, _duration = batch_qa.run_kfx_conversion_for_book(pdf)
    assert success is False


def test_nonempty_kfx_is_success(tmp_path, monkeypatch):
    """Calibre exit 0 + a non-empty .kfx MUST still report success=True."""
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"fake pdf")
    kfx = tmp_path / "book.kfx"
    kfx.write_bytes(b"\x00" * 4096)  # realistic non-empty output

    monkeypatch.setattr(
        batch_qa.subprocess,
        "run",
        lambda *a, **kw: _completed_process(f"done -> {kfx}\n"),
    )

    success, kfx_path, _duration = batch_qa.run_kfx_conversion_for_book(pdf)
    assert success is True
    assert kfx_path == str(kfx)


# ---------------------------------------------------------------------------
# _classify_status — downstream consequence
# ---------------------------------------------------------------------------


def _passing_diag() -> dict:
    """Build a minimal diag that would otherwise classify PASS.

    Only the fields referenced by FAILURE_PATTERNS conditions and
    _classify_status need to be populated; other condition lambdas
    silently skip on KeyError.
    """
    return {
        "filename": "synthetic.pdf",
        "format": "pdf",
        "extraction": {
            "success": True,
            "duration_seconds": 1,
            "warnings": [],
            "errors": [],
        },
        "source_classification": {"source_type": "digital_native"},
        "structure": {
            "chapter_count": 12,
            "headings_look_like_backmatter": False,
            "word_count": 50_000,
            "heading_labels": ["Chapter 1"],
        },
        "text_quality": {
            "ligature_splits": 0,
            "footnotes_unlinked": 0,
            "footnotes_linked": 5,
            "standalone_page_numbers": 0,
            "italic_tags": 10,
            "bold_tags": 5,
            "encoding_errors": 0,
            "double_spaces": 0,
        },
        "kindle_conversion": {
            "attempted": True,
            "success": True,
            "kfx_size_bytes": 250_000,
            "duration_seconds": 60,
        },
        "visual_qa": {
            "attempted": False,
            "score": None,
            "pass_threshold": 70,
            "passed": False,
        },
        "issues": [],
    }


def test_zero_byte_kfx_never_classifies_as_pass():
    """With kindle_conversion.success=False, classifier must route to WARN/FAIL."""
    diag = _passing_diag()
    diag["kindle_conversion"]["success"] = False
    diag["kindle_conversion"]["kfx_size_bytes"] = 0

    batch_qa._detect_issues(diag)
    batch_qa._classify_status(diag)

    assert diag["overall_status"] in ("WARN", "FAIL"), (
        f"expected WARN/FAIL for 0-byte KFX, got {diag['overall_status']!r}; "
        f"issues={diag['issues']}"
    )
    assert any(i["category"] == "kfx_failed" for i in diag["issues"]), (
        f"expected kfx_failed pattern to fire; issues={diag['issues']}"
    )


def test_control_successful_kfx_classifies_as_pass():
    """Sanity check: same diag with a real KFX success still reaches PASS."""
    diag = _passing_diag()

    batch_qa._detect_issues(diag)
    batch_qa._classify_status(diag)

    assert diag["overall_status"] == "PASS", (
        f"expected PASS for valid KFX, got {diag['overall_status']!r}; "
        f"issues={diag['issues']}"
    )
