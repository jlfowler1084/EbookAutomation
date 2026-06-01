import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.config import LibraryConfig, load_library_config


def _write_settings(tmp_path: Path, materialize_mode: str = "copy") -> Path:
    data = {
        "log_level": "INFO",
        "library": {
            "library_root": "F:\\Books",
            "calibre_library": "F:\\Library\\Calibre",
            "audio_root": "F:\\Books\\Audio_Books",
            "documents_root": "F:\\Documents",
            "materialize_mode": materialize_mode,
            "trash_retention_days": 30,
            "operational_folders": ["_Inbox", "_Needs_Review", "_Quarantine"],
            "scan_exclude": ["Audio_Books"],
            "max_path_length": 240,
        },
    }
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_load_library_config_parses_fields(tmp_path):
    cfg = load_library_config(_write_settings(tmp_path))
    assert isinstance(cfg, LibraryConfig)
    assert cfg.library_root == Path("F:\\Books")
    assert cfg.documents_root == Path("F:\\Documents")
    assert cfg.materialize_mode == "copy"
    assert cfg.trash_retention_days == 30
    assert cfg.operational_folders == ("_Inbox", "_Needs_Review", "_Quarantine")
    assert cfg.max_path_length == 240


def test_load_library_config_rejects_bad_mode(tmp_path):
    with pytest.raises(ValueError, match="materialize_mode"):
        load_library_config(_write_settings(tmp_path, materialize_mode="symlink"))
