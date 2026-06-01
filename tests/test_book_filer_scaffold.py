import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.config import LibraryConfig
from book_filer.scaffold import ensure_operational_layout


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
