"""Idempotently create the operational folders that sit beside the shelves."""
from __future__ import annotations

from pathlib import Path

from .config import LibraryConfig


def ensure_operational_layout(config: LibraryConfig) -> list[Path]:
    """Create operational folders + the documents root. Returns folders newly created."""
    config.library_root.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for name in config.operational_folders:
        folder = config.library_root / name
        if not folder.exists():
            folder.mkdir(parents=True)
            created.append(folder)
    config.documents_root.mkdir(parents=True, exist_ok=True)
    return created
