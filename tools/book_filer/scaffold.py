"""Idempotently create the operational folders that sit beside the shelves."""
from __future__ import annotations

from pathlib import Path

from .config import LibraryConfig
from .reparse import has_reparse_in_ancestry


class UnsafeLayoutError(RuntimeError):
    """A scaffold target is a reparse point or an existing non-directory."""


def _ensure_safe_dir(path: Path) -> bool:
    """Ensure `path` exists as a real directory. Return True if newly created.

    Refuses (raises ``UnsafeLayoutError``) if any reparse point — junction,
    symlink, or mount point — appears in the path or its ancestry (the SCRUM-301
    junction-traversal defense), or if `path` already exists as something other
    than a directory. The scaffolder must never bless an ``_Inbox`` junction or a
    file masquerading as an operational folder.
    """
    if has_reparse_in_ancestry(path):
        raise UnsafeLayoutError(
            f"Refusing to scaffold {path}: reparse point in path or ancestry"
        )
    if path.exists():
        if not path.is_dir():
            raise UnsafeLayoutError(
                f"Refusing to scaffold {path}: exists but is not a directory"
            )
        return False
    path.mkdir(parents=True)
    return True


def ensure_operational_layout(config: LibraryConfig) -> list[Path]:
    """Create operational folders + the documents root. Returns folders newly created.

    Every target (library root, each operational folder, documents root) is
    validated for reparse points and non-directory collisions before creation.
    """
    _ensure_safe_dir(config.library_root)
    created: list[Path] = []
    for name in config.operational_folders:
        folder = config.library_root / name
        if _ensure_safe_dir(folder):
            created.append(folder)
    _ensure_safe_dir(config.documents_root)
    return created
