import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer import reparse
from book_filer.config import LibraryConfig
from book_filer.scaffold import (
    _INBOX_SUBFOLDERS,
    UnsafeLayoutError,
    ensure_inbox_subfolders,
    ensure_operational_layout,
)


def _cfg(tmp_path: Path) -> LibraryConfig:
    return LibraryConfig(
        library_root=tmp_path / "Books",
        calibre_library=tmp_path / "Calibre",
        audio_root=tmp_path / "Books" / "Audio_Books",
        documents_root=tmp_path / "Documents",
        materialize_mode="copy",
        trash_retention_days=30,
        operational_folders=("_Inbox", "_Needs_Review", "_Trash_Pending"),
        scan_exclude=("Audio_Books",),
        max_path_length=240,
    )


def test_creates_all_operational_folders(tmp_path):
    cfg = _cfg(tmp_path)
    created = ensure_operational_layout(cfg)
    for name in cfg.operational_folders:
        assert (cfg.library_root / name).is_dir()
    assert cfg.documents_root.is_dir()
    assert {p.name for p in created} == set(cfg.operational_folders)


def test_is_idempotent(tmp_path):
    cfg = _cfg(tmp_path)
    ensure_operational_layout(cfg)
    created_second = ensure_operational_layout(cfg)
    assert created_second == []


def test_rejects_file_named_like_operational_folder(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.library_root.mkdir(parents=True)
    (cfg.library_root / "_Inbox").write_text("x", encoding="utf-8")
    with pytest.raises(UnsafeLayoutError):
        ensure_operational_layout(cfg)


def test_rejects_reparse_point_operational_folder(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cfg.library_root.mkdir(parents=True)
    junction = cfg.library_root / "_Inbox"
    junction.mkdir()
    monkeypatch.setattr(reparse, "_is_reparse_point", lambda p: Path(p) == junction)
    with pytest.raises(UnsafeLayoutError):
        ensure_operational_layout(cfg)


# ---------------------------------------------------------------------------
# ensure_inbox_subfolders (EB-380 U1)
# ---------------------------------------------------------------------------


def test_inbox_subfolders_creates_all_four(tmp_path):
    cfg = _cfg(tmp_path)
    (cfg.library_root / "_Inbox").mkdir(parents=True)
    created = ensure_inbox_subfolders(cfg)
    assert {p.name for p in created} == set(_INBOX_SUBFOLDERS)
    for name in _INBOX_SUBFOLDERS:
        assert (cfg.library_root / "_Inbox" / name).is_dir()


def test_inbox_subfolders_creates_inbox_if_missing(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.library_root.mkdir(parents=True)
    # _Inbox does not exist yet — function must create it
    created = ensure_inbox_subfolders(cfg)
    assert (cfg.library_root / "_Inbox").is_dir()
    assert {p.name for p in created} == set(_INBOX_SUBFOLDERS)


def test_inbox_subfolders_idempotent(tmp_path):
    cfg = _cfg(tmp_path)
    ensure_inbox_subfolders(cfg)
    created_second = ensure_inbox_subfolders(cfg)
    assert created_second == []


@pytest.mark.skipif(
    __import__("os").name != "nt",
    reason="Junction/reparse points are Windows-only",
)
def test_inbox_subfolders_rejects_junctioned_inbox(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cfg.library_root.mkdir(parents=True)
    inbox = cfg.library_root / "_Inbox"
    inbox.mkdir()
    monkeypatch.setattr(reparse, "_is_reparse_point", lambda p: Path(p) == inbox)
    with pytest.raises(UnsafeLayoutError):
        ensure_inbox_subfolders(cfg)
    # Nothing created under the junctioned _Inbox
    for name in _INBOX_SUBFOLDERS:
        assert not (inbox / name).exists()
