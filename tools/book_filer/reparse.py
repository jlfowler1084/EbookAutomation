"""Reject reparse points (junctions/symlinks/mount points) anywhere in a path.

Defends against the SCRUM-301 junction-traversal data-loss class: a junction
ANYWHERE in the source/destination ancestry can redirect a move into foreign
storage. Stricter than prefix-matching `F:\\Books`.

Polarity: ``has_reparse_in_ancestry`` returns ``True`` for "reparse present ->
unsafe -> do not traverse". Because this gates a destructive mover, every
*ambiguous* result MUST fail CLOSED (return ``True``). Only two outcomes are
allowed to report "safe" (``False``): a clean check that finds no reparse bit,
and a component that is *determinately* absent (a move destination that does
not exist yet). See EB-360.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _extended(path: Path) -> str:
    r"""Return an absolute path, prefixed with ``\\?\`` on Windows.

    The extended-length prefix lets ``os.lstat`` resolve paths over the legacy
    260-char ``MAX_PATH`` limit instead of raising ``OSError`` (EB-360 mode #2).
    ``os.path.abspath`` normalizes ``.``/``..`` and makes the path absolute
    *without* following junctions/symlinks, so it cannot be used to escape the
    reparse check itself.
    """
    p = os.path.abspath(str(path))
    if os.name == "nt" and not p.startswith("\\\\?\\"):
        if p.startswith("\\\\"):  # UNC path: \\server\share -> \\?\UNC\server\share
            return "\\\\?\\UNC\\" + p[2:]
        return "\\\\?\\" + p
    return p


def _is_reparse_point(path: Path) -> bool:
    """Whether ``path`` is itself a reparse point. Fails CLOSED on ambiguity.

    - ``FileNotFoundError``: the component is determinately absent (no reparse
      point there) -> ``False``.
    - any other ``OSError`` (long path even with the prefix, permission denied,
      etc.): we could not determine safety -> fail CLOSED -> ``True``.
    - success but no ``st_file_attributes`` (non-Windows platform, which has no
      junction concept): ``False``.
    """
    try:
        st = os.lstat(_extended(path))
    except FileNotFoundError:
        return False
    except OSError:
        return True
    attrs = getattr(st, "st_file_attributes", None)  # Windows-only attribute
    if attrs is None:
        return False
    return bool(attrs & _REPARSE)


def has_reparse_in_ancestry(path: Path) -> bool:
    """True if the leaf or any ancestor of ``path`` is (or may be) a reparse point.

    Every component is probed via ``os.lstat`` directly rather than gating on
    ``Path.exists()``/``Path.is_symlink()`` first: a *dangling* junction reports
    ``exists()==False`` and ``is_symlink()==False`` on Windows, yet its directory
    entry still carries the reparse bit (EB-360 mode #1). ``_is_reparse_point``
    handles the genuinely-absent case via ``FileNotFoundError``.
    """
    p = Path(path)
    for component in (p, *p.parents):
        if _is_reparse_point(component):
            return True
    return False
