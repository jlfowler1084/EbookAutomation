"""Load the `library` configuration block from config/settings.json."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# tools/book_filer/config.py -> parents[2] == repo root
_DEFAULT_SETTINGS = Path(__file__).resolve().parents[2] / "config" / "settings.json"
_VALID_MODES = ("copy", "hardlink")


@dataclass(frozen=True)
class LibraryConfig:
    library_root: Path
    calibre_library: Path
    audio_root: Path
    documents_root: Path
    materialize_mode: str
    trash_retention_days: int
    operational_folders: tuple[str, ...]
    scan_exclude: tuple[str, ...]
    max_path_length: int


def load_library_config(settings_path: Path | None = None) -> LibraryConfig:
    path = Path(settings_path) if settings_path else _DEFAULT_SETTINGS
    data = json.loads(path.read_text(encoding="utf-8"))
    lib = data["library"]

    mode = lib.get("materialize_mode", "copy")
    if mode not in _VALID_MODES:
        raise ValueError(
            f"materialize_mode must be one of {_VALID_MODES}, got {mode!r}"
        )

    return LibraryConfig(
        library_root=Path(lib["library_root"]),
        calibre_library=Path(lib["calibre_library"]),
        audio_root=Path(lib["audio_root"]),
        documents_root=Path(lib["documents_root"]),
        materialize_mode=mode,
        trash_retention_days=int(lib.get("trash_retention_days", 30)),
        operational_folders=tuple(lib["operational_folders"]),
        scan_exclude=tuple(lib.get("scan_exclude", ())),
        max_path_length=int(lib.get("max_path_length", 240)),
    )
