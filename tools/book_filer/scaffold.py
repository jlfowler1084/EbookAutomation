"""Idempotently create the operational folders that sit beside the shelves."""
from __future__ import annotations

from pathlib import Path

from .config import LibraryConfig
from .reparse import has_reparse_in_ancestry

# Per-source intake subfolders staged inside _Inbox for the steady-state auto-filer (EB-380).
_INBOX_SUBFOLDERS: tuple[str, ...] = ("BookFinder", "Manual", "Conversions", "Migration")


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


def ensure_inbox_subfolders(config: LibraryConfig) -> list[Path]:
    """Create per-source intake subfolders inside _Inbox. Returns folders newly created.

    Ensures _Inbox itself exists first (it is listed in operational_folders and created
    by ensure_operational_layout, but this function is safe to call standalone). Each
    subfolder is validated via _ensure_safe_dir, which raises UnsafeLayoutError if any
    reparse point appears in the path or ancestry (SCRUM-301 junction-traversal defense).
    A second call is a no-op and returns [].
    """
    inbox = config.library_root / "_Inbox"
    _ensure_safe_dir(inbox)
    created: list[Path] = []
    for name in _INBOX_SUBFOLDERS:
        subfolder = inbox / name
        if _ensure_safe_dir(subfolder):
            created.append(subfolder)
    return created
