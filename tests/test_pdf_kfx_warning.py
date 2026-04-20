"""Tests for _normalize_book_stem() and the KFX-shadow warning (SCRUM-282 U3).

Key invariants:
  - Normalization is idempotent: f(f(x)) == f(x)
  - Author suffix (' - Last, First') is stripped before non-alnum substitution
  - Atomic Habits worked example must round-trip correctly
  - Warning fires iff a KFX with the same normalized stem exists in output/kindle/
  - Warning does NOT fire for PDF input with no matching KFX
  - Warning does NOT fire for KFX/non-PDF input
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import visual_qa as vqa


# ---------------------------------------------------------------------------
# _normalize_book_stem() unit tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stem,expected", [
    # Already minimal
    ("simple", "simple"),
    # Uppercase → lowercase
    ("My Book", "my book"),
    # Author suffix stripped
    ("Atomic Habits - James Clear", "atomic habits"),
    # Atomic Habits full filename stem (the worked example)
    (
        "Atomic Habits Tiny Changes, Remarkable Results An Easy & Proven Way "
        "to Build Good Habits & Break Bad Ones - James Clear",
        "atomic habits tiny changes remarkable results an easy proven way "
        "to build good habits break bad ones",
    ),
    # Non-alnum replaced with space, collapsed
    ("Book: Sub-title!", "book sub title"),
    # Multiple spaces collapsed
    ("lots   of   spaces", "lots of spaces"),
    # Author with comma
    ("Oil Kings - Cooper, Andrew Scott", "oil kings"),
    # No author suffix → full title normalized
    ("Python in easy steps 2nd Edition", "python in easy steps 2nd edition"),
    # Subtitle with colon (no author)
    ("Decline of the West Volumes 1 and 2", "decline of the west volumes 1 and 2"),
])
def test_normalize_stem_values(stem, expected):
    assert vqa._normalize_book_stem(stem) == expected


def test_normalize_idempotent_simple():
    stem = "Atomic Habits - James Clear"
    once = vqa._normalize_book_stem(stem)
    twice = vqa._normalize_book_stem(once)
    assert once == twice, f"Not idempotent: f(x)={once!r}, f(f(x))={twice!r}"


@pytest.mark.parametrize("stem", [
    "Atomic Habits Tiny Changes, Remarkable Results An Easy & Proven Way "
    "to Build Good Habits & Break Bad Ones - James Clear",
    "Oil Kings - Cooper, Andrew Scott",
    "Mexico's Illicit Drug Networks and the State Reaction - Nathan P. Jones",
    "The Return of the Gods - Jonathan Cahn",
    "Decline of the West Volumes 1 and 2 - Oswald Spengler",
    "Python in easy steps, 2nd Edition - Mike McGrath",
])
def test_normalize_idempotent_corpus(stem):
    once = vqa._normalize_book_stem(stem)
    twice = vqa._normalize_book_stem(once)
    assert once == twice, f"Not idempotent for {stem!r}: {once!r} vs {twice!r}"


# ---------------------------------------------------------------------------
# KFX-shadow warning integration tests — via run_visual_qa() dispatch
# ---------------------------------------------------------------------------

def _make_mock_provider():
    provider = MagicMock()
    provider.name = "TestProvider"
    provider.estimate_cost.return_value = 0.001
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
    monkeypatch.setattr(vqa, "convert_to_pdf",
                        lambda input_path, calibre_path, **kw: str(tmp_path / "converted.pdf"))
    monkeypatch.setattr(vqa, "get_pdf_page_count", lambda *a, **kw: total_pages)
    monkeypatch.setattr(vqa, "get_pdf_bookmarks", lambda *a, **kw: [30, 60, 90])
    monkeypatch.setattr(vqa, "select_sample_pages",
                        lambda *a, **kw: [1, 2, 3, 30, 60, 90, 120, 140])
    monkeypatch.setattr(vqa, "render_pages_to_png",
                        lambda *a, **kw: [(1, b"fake_png_bytes")])
    monkeypatch.setattr(vqa.Path, "exists", lambda self: True)
    monkeypatch.setattr(vqa.Path, "read_text", lambda self, **kw: "rubric content")
    monkeypatch.setattr(vqa, "FallbackFingerprintDetector",
                        lambda *a, **kw: MagicMock(classify=lambda imgs: []))


def _run_vqa(input_path, provider, output_dir):
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


def test_warning_fires_when_kfx_match_exists(monkeypatch, tmp_path, caplog):
    """PDF input with a matching KFX stem in output/kindle/ must emit a WARNING."""
    _patch_pipeline_internals(monkeypatch, tmp_path)

    # Fake kfx_dir with a matching KFX
    kfx_dir = tmp_path / "output" / "kindle"
    kfx_dir.mkdir(parents=True)
    (kfx_dir / "Atomic Habits - James Clear.kfx").touch()

    # Redirect _normalize_book_stem's kfx_dir lookup to our tmp dir
    project_root = tmp_path
    monkeypatch.setattr(
        vqa.Path,
        "resolve",
        lambda self: project_root / "tools" / "visual_qa.py"
        if "visual_qa" in str(self) else self,
    )
    # Simpler: patch Path(__file__).resolve().parent.parent directly via monkeypatching
    # the kfx_dir lookup inside the function by redirecting the parent chain.
    # Instead, override is_dir() and glob() on the specific kfx_dir path.
    # Easiest: monkeypatch the kfx_dir by patching Path.resolve to return a
    # known location, or just use a real tmp structure and patch __file__ parent.

    # Reset monkeypatch on Path.resolve — use a more targeted approach:
    # override the kfx_dir logic by patching the module-level Path class
    # resolution. Since Path(__file__) in visual_qa resolves to the tools dir,
    # we create the output/kindle structure relative to the worktree root,
    # not tmp_path. So use the real worktree path.
    worktree = Path(__file__).resolve().parent.parent
    real_kfx_dir = worktree / "output" / "kindle"
    real_kfx_dir.mkdir(parents=True, exist_ok=True)
    kfx_file = real_kfx_dir / "Atomic Habits - James Clear.kfx"
    kfx_file.touch()

    pdf_input = tmp_path / "Atomic Habits - James Clear.pdf"
    pdf_input.touch()

    try:
        with caplog.at_level(logging.WARNING, logger="visual_qa"):
            _run_vqa(pdf_input, _make_mock_provider(), tmp_path)
        assert any(
            "shadows" in record.message and "Atomic Habits" in record.message
            for record in caplog.records
        ), f"Expected shadow warning. Records: {[r.message for r in caplog.records]}"
    finally:
        if kfx_file.exists():
            kfx_file.unlink()


def test_no_warning_when_no_kfx_match(monkeypatch, tmp_path, caplog):
    """PDF input with no matching KFX must not emit a shadow warning."""
    _patch_pipeline_internals(monkeypatch, tmp_path)

    # Ensure output/kindle has no matching KFX for this stem
    worktree = Path(__file__).resolve().parent.parent
    real_kfx_dir = worktree / "output" / "kindle"
    real_kfx_dir.mkdir(parents=True, exist_ok=True)

    pdf_input = tmp_path / "Completely Unknown Book With No KFX Match Ever.pdf"
    pdf_input.touch()

    with caplog.at_level(logging.WARNING, logger="visual_qa"):
        _run_vqa(pdf_input, _make_mock_provider(), tmp_path)

    shadow_warnings = [
        r for r in caplog.records
        if "shadows" in r.message
    ]
    assert not shadow_warnings, f"Unexpected shadow warning: {shadow_warnings}"


def test_no_warning_for_kfx_input(monkeypatch, tmp_path, caplog):
    """KFX input (non-PDF) must never emit a KFX-shadow warning."""
    _patch_pipeline_internals(monkeypatch, tmp_path)

    kfx_input = tmp_path / "Atomic Habits - James Clear.kfx"
    kfx_input.touch()

    with caplog.at_level(logging.WARNING, logger="visual_qa"):
        _run_vqa(kfx_input, _make_mock_provider(), tmp_path)

    shadow_warnings = [r for r in caplog.records if "shadows" in r.message]
    assert not shadow_warnings, f"KFX input should never trigger shadow warning: {shadow_warnings}"
