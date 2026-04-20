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
    # Fix #1a: Leading separator (' - Author') must not collapse to empty string
    # sep_idx == 0 guard prevents stripping, leaving normalized author text
    (" - Author", "author"),
    # Fix #1b: Embedded subtitle separator ('Foo - A Subtitle') — Option A behavior:
    # 'A Subtitle' passes the author-name heuristic (short, letters/spaces only),
    # so it IS stripped. Pinned explicitly so future changes are visible.
    ("Foo - A Subtitle", "foo"),
])
def test_normalize_stem_values(stem, expected):
    assert vqa._normalize_book_stem(stem) == expected


@pytest.mark.parametrize("stem", [
    "東京の本 - 著者",
    "Война и мир - Толстой",
    "Ünlü Kitap - Ahmet Çelik",
])
def test_normalize_non_ascii_is_nonempty(stem):
    """Non-ASCII titles must not normalize to an empty string (Fix #1a re.UNICODE)."""
    result = vqa._normalize_book_stem(stem)
    assert result, f"_normalize_book_stem({stem!r}) returned empty string"


def test_normalize_non_ascii_books_are_distinct():
    """Two different non-ASCII book titles must produce different normalized strings."""
    r1 = vqa._normalize_book_stem("東京の本 - 著者")
    r2 = vqa._normalize_book_stem("北京の本 - 著者")
    assert r1 != r2, f"Expected distinct normalized stems but both are {r1!r}"


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
    """PDF input with a matching KFX stem in output/kindle/ must emit a WARNING.

    Uses _get_kfx_dir() monkeypatch so no real worktree files are touched.
    """
    _patch_pipeline_internals(monkeypatch, tmp_path)

    # Plant KFX in a hermetic tmp dir and redirect the seam
    kfx_dir = tmp_path / "output" / "kindle"
    kfx_dir.mkdir(parents=True)
    (kfx_dir / "Atomic Habits - James Clear.kfx").write_bytes(b"")
    monkeypatch.setattr(vqa, "_get_kfx_dir", lambda: kfx_dir)

    pdf_input = tmp_path / "Atomic Habits - James Clear.pdf"
    pdf_input.touch()

    with caplog.at_level(logging.WARNING, logger="visual_qa"):
        _run_vqa(pdf_input, _make_mock_provider(), tmp_path)

    assert any(
        "shadows" in record.message and "Atomic Habits" in record.message
        for record in caplog.records
    ), f"Expected shadow warning. Records: {[r.message for r in caplog.records]}"


def test_no_warning_when_no_kfx_match(monkeypatch, tmp_path, caplog):
    """PDF input with no matching KFX must not emit a shadow warning."""
    _patch_pipeline_internals(monkeypatch, tmp_path)

    # Empty kfx_dir — no match possible
    kfx_dir = tmp_path / "output" / "kindle"
    kfx_dir.mkdir(parents=True)
    monkeypatch.setattr(vqa, "_get_kfx_dir", lambda: kfx_dir)

    pdf_input = tmp_path / "Completely Unknown Book With No KFX Match Ever.pdf"
    pdf_input.touch()

    with caplog.at_level(logging.WARNING, logger="visual_qa"):
        _run_vqa(pdf_input, _make_mock_provider(), tmp_path)

    shadow_warnings = [r for r in caplog.records if "shadows" in r.message]
    assert not shadow_warnings, f"Unexpected shadow warning: {shadow_warnings}"


def test_no_warning_for_kfx_input(monkeypatch, tmp_path, caplog):
    """KFX input (non-PDF) must never emit a KFX-shadow warning."""
    _patch_pipeline_internals(monkeypatch, tmp_path)

    # Even if kfx_dir has a match, KFX input skips the shadow check entirely
    kfx_dir = tmp_path / "output" / "kindle"
    kfx_dir.mkdir(parents=True)
    (kfx_dir / "Atomic Habits - James Clear.kfx").write_bytes(b"")
    monkeypatch.setattr(vqa, "_get_kfx_dir", lambda: kfx_dir)

    kfx_input = tmp_path / "Atomic Habits - James Clear.kfx"
    kfx_input.touch()

    with caplog.at_level(logging.WARNING, logger="visual_qa"):
        _run_vqa(kfx_input, _make_mock_provider(), tmp_path)

    shadow_warnings = [r for r in caplog.records if "shadows" in r.message]
    assert not shadow_warnings, f"KFX input should never trigger shadow warning: {shadow_warnings}"
