import errno
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer import reparse


class _FakeStat:
    """Minimal stand-in for os.lstat() carrying st_file_attributes."""

    def __init__(self, attrs: int) -> None:
        self.st_file_attributes = attrs


def test_no_reparse_in_clean_tree(tmp_path):
    target = tmp_path / "a" / "b" / "Book.epub"
    assert reparse.has_reparse_in_ancestry(target) is False


def test_detects_reparse_in_ancestry(tmp_path, monkeypatch):
    junction = tmp_path / "linked"
    junction.mkdir()
    target = junction / "child" / "Book.epub"

    def fake_is_reparse(p: Path) -> bool:
        return Path(p) == junction

    monkeypatch.setattr(reparse, "_is_reparse_point", fake_is_reparse)
    assert reparse.has_reparse_in_ancestry(target) is True


def test_detects_reparse_at_leaf(tmp_path, monkeypatch):
    leaf = tmp_path / "Book.epub"
    leaf.write_text("x", encoding="utf-8")
    monkeypatch.setattr(reparse, "_is_reparse_point", lambda p: Path(p) == leaf)
    assert reparse.has_reparse_in_ancestry(leaf) is True


def test_dangling_junction_reports_unsafe(tmp_path, monkeypatch):
    """A junction whose target is gone (exists()==False, not a Python symlink)
    must still be flagged: os.lstat on the junction entry shows the REPARSE bit.

    EB-360 fail-OPEN mode #1.
    """
    junction = tmp_path / "linked"
    target = junction / "child" / "Book.epub"

    def fake_lstat(p, *args, **kwargs):
        name = os.path.basename(str(p).rstrip("\\/"))
        if name == "linked":
            return _FakeStat(reparse._REPARSE)
        # Everything below the dangling junction is unreachable.
        raise FileNotFoundError(errno.ENOENT, "missing", str(p))

    monkeypatch.setattr(reparse.os, "lstat", fake_lstat)
    assert reparse.has_reparse_in_ancestry(target) is True


def test_oserror_during_check_fails_closed(tmp_path, monkeypatch):
    """An ambiguous OSError (e.g. >260-char path) must fail CLOSED -> unsafe,
    not be swallowed as 'no reparse point'.

    EB-360 fail-OPEN mode #2.
    """
    target = tmp_path / "deep" / "Book.epub"

    def fake_lstat(p, *args, **kwargs):
        raise OSError(errno.ENAMETOOLONG, "path too long")

    monkeypatch.setattr(reparse.os, "lstat", fake_lstat)
    assert reparse.has_reparse_in_ancestry(target) is True


def test_missing_component_is_safe(tmp_path, monkeypatch):
    """A genuinely-absent component (e.g. a move destination not yet created)
    is a determinate answer, not an ambiguity -> must NOT fail closed."""
    target = tmp_path / "not_yet" / "Book.epub"

    def fake_lstat(p, *args, **kwargs):
        raise FileNotFoundError(errno.ENOENT, "missing", str(p))

    monkeypatch.setattr(reparse.os, "lstat", fake_lstat)
    assert reparse.has_reparse_in_ancestry(target) is False


def test_extended_length_prefix_applied_on_windows():
    """Long-path handling: lstat must run against a \\\\?\\-prefixed path so
    >260-char paths resolve instead of raising."""
    if os.name != "nt":
        pytest.skip("Windows-only extended-length path behavior")
    prefixed = reparse._extended(Path("C:\\Books\\some\\deep\\path"))
    assert prefixed.startswith("\\\\?\\")
