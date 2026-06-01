import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer import reparse


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
