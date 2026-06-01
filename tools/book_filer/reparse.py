"""Reject reparse points (junctions/symlinks/mount points) anywhere in a path.

Defends against the SCRUM-301 junction-traversal data-loss class: a junction
ANYWHERE in the source/destination ancestry can redirect a move into foreign
storage. Stricter than prefix-matching `F:\\Books`.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _is_reparse_point(path: Path) -> bool:
    try:
        attrs = os.lstat(path).st_file_attributes  # Windows-only attribute
    except (OSError, AttributeError):
        return False
    return bool(attrs & _REPARSE)


def has_reparse_in_ancestry(path: Path) -> bool:
    """True if the leaf or any existing ancestor of `path` is a reparse point."""
    p = Path(path)
    for component in (p, *p.parents):
        if component.exists() or component.is_symlink():
            if _is_reparse_point(component):
                return True
    return False
