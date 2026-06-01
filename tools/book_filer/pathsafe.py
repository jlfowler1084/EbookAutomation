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


def build_base_name(
    author_sort: str,
    title: str,
    year: int | None,
    series: str | None = None,
    series_index: str | None = None,
    disambiguator: str | None = None,
) -> str:
    """Build the filename stem (no extension) per spec §5.1."""
    author_sort = sanitize_component(author_sort)
    title = sanitize_component(title)
    out = f"{author_sort} - "
    if series and series_index:
        out += f"[{sanitize_component(series)} {series_index}] "
    out += title
    if year:
        out += f" ({year})"
    if disambiguator:
        out += f" [{sanitize_component(disambiguator)}]"
    return out


def compute_shelf_path(
    library_root: Path,
    section: str,
    subcategory: str,
    author_sort: str,
    title: str,
    ext: str,
    year: int | None = None,
    series: str | None = None,
    series_index: str | None = None,
    disambiguator: str | None = None,
    max_path_length: int = 240,
) -> Path:
    """Compose <root>/<Section>/<Subcategory>/<Author>/<base><ext>.

    If the full path exceeds max_path_length, truncate the TITLE only (never
    section/subcategory/author/year/disambiguator/extension), appending an
    ellipsis. Returns a best-effort path even if the folder alone is over budget;
    the caller (the guarded filer) quarantines anything still too long.
    """
    folder = (
        Path(library_root)
        / sanitize_component(section)
        / sanitize_component(subcategory)
        / sanitize_component(author_sort)
    )

    def assemble(t: str) -> Path:
        base = build_base_name(author_sort, t, year, series, series_index, disambiguator)
        return folder / f"{base}{ext}"

    full = assemble(title)
    if len(str(full)) <= max_path_length:
        return full

    overflow = len(str(full)) - max_path_length
    san_title = sanitize_component(title)
    keep = max(8, len(san_title) - overflow - 1)   # -1 reserves room for the ellipsis
    truncated = san_title[:keep].rstrip() + "…"
    return assemble(truncated)


def unique_path(dest: Path) -> Path:
    """Return `dest` if free, else `dest (2)`, `dest (3)`, ... (spec §5.3)."""
    dest = Path(dest)
    if not dest.exists():
        return dest
    stem, suffix, parent = dest.stem, dest.suffix, dest.parent
    i = 2
    while True:
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1
