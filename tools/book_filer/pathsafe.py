"""Filesystem-safe path construction for the book filer (spec §5.1, §5.3)."""
from __future__ import annotations

import re
from pathlib import Path

_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
    f"LPT{i}" for i in range(1, 10)
}
# `/`, `\`, `:` become " - " (readable); the rest are stripped.
_TO_DASH_RE = re.compile(r"[/\\:]")
_STRIP_RE = re.compile(r'[<>"|?*\x00-\x1f]')
_WS_RE = re.compile(r"\s+")
# Collapse repeated " - " separators produced by adjacent slash/colon runs
_MULTI_DASH_RE = re.compile(r"(\s*-\s*){2,}")


def sanitize_component(name: str) -> str:
    """Return a single path segment safe for Windows NTFS folders/filenames."""
    name = name.replace("·", " ")          # middot -> space
    name = _TO_DASH_RE.sub(" - ", name)         # path-separators / colon -> dash
    name = _STRIP_RE.sub("", name)              # remaining illegal chars -> removed
    name = _WS_RE.sub(" ", name).strip()        # collapse whitespace
    name = _MULTI_DASH_RE.sub(" - ", name).strip()  # collapse repeated " - " sequences
    name = name.rstrip(". ")                     # no trailing dots/spaces (Windows)
    if not name:
        return "_"
    if name.split(".")[0].upper() in _RESERVED:
        name = f"_{name}"
    return name
