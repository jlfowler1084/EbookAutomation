# EB-355 Book Filer — Foundation Implementation Plan (Plan 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the safety + configuration foundation for the `F:\Books` auto-filer — a Python `book_filer` package providing config loading, filesystem-safe path construction (sanitization, collision suffixes, title-only truncation), reparse-point (junction/symlink) rejection, and idempotent operational-folder scaffolding.

**Architecture:** A Python core engine (`tools/book_filer/`) holds all testable logic so it runs under the project's pytest harness; later plans add the PowerShell guarded wrapper (`Invoke-BookFileGuarded.ps1`) that calls this core and performs the actual copy/move. This plan is **purely additive** — it creates new files and adds one config block; it modifies no existing logic, so it carries no regression risk to the pipeline.

**Tech Stack:** Python 3.12, `pathlib`, `dataclasses`, `re`, `os`/`stat` (Windows file attributes), pytest.

**Spec:** `docs/superpowers/specs/2026-06-01-fbooks-organization-and-hermes-enforcement-design.md` (commit `5e7790d`). This plan implements spec §2 (config), §5.1–5.3 (naming, identifiers, path-safety), and §2/§6 operational folders.

---

## Before you start

- Work in a worktree branch for EB-355 (per project policy): `feat/EB-355-book-filer`. Create it with the `worktree-management` skill. **Do not run any migration here** — this plan only creates new package + test files; nothing touches live `F:\Books`.
- Test command (whole suite): `python -m pytest tests/ -q`. Per-file commands are given in each task.
- Python invocation on this machine: `py -3.12 -m pytest ...` is equivalent if `python` is not on PATH.

## File Structure

| File | Responsibility |
|------|----------------|
| `tools/book_filer/__init__.py` | Package marker (empty) |
| `tools/book_filer/config.py` | Load the `library` block from `config/settings.json` into a frozen `LibraryConfig` |
| `tools/book_filer/pathsafe.py` | `sanitize_component`, `build_base_name`, `compute_shelf_path` (title-only truncation), `unique_path` |
| `tools/book_filer/reparse.py` | `has_reparse_in_ancestry` — reject junctions/symlinks anywhere in a path's ancestry |
| `tools/book_filer/scaffold.py` | `ensure_operational_layout` — idempotently create `_Inbox`, `_Needs_Review`, … |
| `config/settings.json` | **Modify:** add a top-level `library` block |
| `tests/test_book_filer_config.py` | Tests for config loader |
| `tests/test_book_filer_pathsafe.py` | Tests for path-safety functions |
| `tests/test_book_filer_reparse.py` | Tests for reparse-point rejection |
| `tests/test_book_filer_scaffold.py` | Tests for operational-folder scaffolding |

**Test import convention (used by every test file in this plan):** the package is imported by putting the repo's `tools/` dir on `sys.path`, so `book_filer` is a top-level import regardless of pytest config:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
```

---

### Task 1: Config block + `LibraryConfig` loader

**Files:**
- Modify: `config/settings.json` (add `library` block)
- Create: `tools/book_filer/__init__.py` (empty)
- Create: `tools/book_filer/config.py`
- Test: `tests/test_book_filer_config.py`

- [ ] **Step 1: Add the `library` block to `config/settings.json`**

Insert this top-level key immediately after the `"log_level": "INFO",` line (so it sits beside `BookFinder`):

```json
  "library": {
    "library_root": "F:\\Books",
    "calibre_library": "F:\\Library\\Calibre",
    "audio_root": "F:\\Books\\Audio_Books",
    "documents_root": "F:\\Documents",
    "materialize_mode": "copy",
    "trash_retention_days": 30,
    "operational_folders": ["_Inbox", "_Needs_Review", "_Quarantine", "_Duplicates_Pending", "_Trash_Pending", "_Migration_Manifests"],
    "scan_exclude": ["Audio_Books"],
    "max_path_length": 240
  },
```

- [ ] **Step 2: Create the empty package marker**

Create `tools/book_filer/__init__.py` with a single line:

```python
"""Book filer foundation: config, path-safety, reparse rejection, scaffolding."""
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_book_filer_config.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `python -m pytest tests/test_book_filer_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'book_filer.config'`.

- [ ] **Step 5: Implement `tools/book_filer/config.py`**

```python
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
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python -m pytest tests/test_book_filer_config.py -q`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add config/settings.json tools/book_filer/__init__.py tools/book_filer/config.py tests/test_book_filer_config.py
git commit -m "feat(EB-355): add library config block + LibraryConfig loader"
```

---

### Task 2: `sanitize_component` — filesystem-safe path segments

**Files:**
- Create: `tools/book_filer/pathsafe.py`
- Test: `tests/test_book_filer_pathsafe.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_book_filer_pathsafe.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.pathsafe import sanitize_component


def test_sanitize_replaces_middot_and_collapses_spaces():
    assert sanitize_component("World Wars (WWI · WWII · Weimar)") == "World Wars (WWI WWII Weimar)"


def test_sanitize_colon_becomes_dash():
    assert sanitize_component("Title: Subtitle") == "Title - Subtitle"


def test_sanitize_slash_becomes_dash():
    assert sanitize_component("Marx/Engels") == "Marx - Engels"


def test_sanitize_strips_other_illegal_chars():
    assert sanitize_component('a<b>c"d|e?f*g') == "abcdefg"


def test_sanitize_trims_trailing_dots_and_spaces():
    assert sanitize_component("name...  ") == "name"


def test_sanitize_guards_reserved_names():
    assert sanitize_component("CON") == "_CON"
    assert sanitize_component("com1") == "_com1"


def test_sanitize_empty_becomes_placeholder():
    assert sanitize_component("///") == "-"  # slashes -> ' - ', collapse, trim -> '-'
    assert sanitize_component("") == "_"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_book_filer_pathsafe.py -q`
Expected: FAIL — `ImportError: cannot import name 'sanitize_component'`.

- [ ] **Step 3: Implement `sanitize_component` in `tools/book_filer/pathsafe.py`**

Create `tools/book_filer/pathsafe.py`:

```python
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


def sanitize_component(name: str) -> str:
    """Return a single path segment safe for Windows NTFS folders/filenames."""
    name = name.replace("·", " ")          # middot -> space
    name = _TO_DASH_RE.sub(" - ", name)         # path-separators / colon -> dash
    name = _STRIP_RE.sub("", name)              # remaining illegal chars -> removed
    name = _WS_RE.sub(" ", name).strip()        # collapse whitespace
    name = name.rstrip(". ")                     # no trailing dots/spaces (Windows)
    if not name:
        return "_"
    if name.split(".")[0].upper() in _RESERVED:
        name = f"_{name}"
    return name
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_book_filer_pathsafe.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/pathsafe.py tests/test_book_filer_pathsafe.py
git commit -m "feat(EB-355): add sanitize_component for FS-safe path segments"
```

---

### Task 3: `build_base_name` — the `Author Last, First - Title (Year)` convention

**Files:**
- Modify: `tools/book_filer/pathsafe.py`
- Modify: `tests/test_book_filer_pathsafe.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_book_filer_pathsafe.py`:

```python
from book_filer.pathsafe import build_base_name


def test_build_base_name_simple():
    assert build_base_name("Cooper, Andrew Scott", "The Oil Kings", 2011) == \
        "Cooper, Andrew Scott - The Oil Kings (2011)"


def test_build_base_name_no_year():
    assert build_base_name("Spencer, Herbert", "The Man Versus the State", None) == \
        "Spencer, Herbert - The Man Versus the State"


def test_build_base_name_with_series():
    assert build_base_name(
        "Spengler, Oswald", "Form and Actuality", 1918,
        series="Decline of the West", series_index="01",
    ) == "Spengler, Oswald - [Decline of the West 01] Form and Actuality (1918)"


def test_build_base_name_with_disambiguator():
    assert build_base_name(
        "Coogan, Michael", "The New Oxford Annotated Bible", 2010, disambiguator="NRSV",
    ) == "Coogan, Michael - The New Oxford Annotated Bible (2010) [NRSV]"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_book_filer_pathsafe.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_base_name'`.

- [ ] **Step 3: Implement `build_base_name` (append to `pathsafe.py`)**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_book_filer_pathsafe.py -q`
Expected: PASS (11 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/pathsafe.py tests/test_book_filer_pathsafe.py
git commit -m "feat(EB-355): add build_base_name (Author - Title (Year) convention)"
```

---

### Task 4: `compute_shelf_path` — assemble the full shelf path with title-only truncation

**Files:**
- Modify: `tools/book_filer/pathsafe.py`
- Modify: `tests/test_book_filer_pathsafe.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_book_filer_pathsafe.py`:

```python
from book_filer.pathsafe import compute_shelf_path


def test_compute_shelf_path_layout():
    p = compute_shelf_path(
        library_root=Path("F:\\Books"),
        section="01 History",
        subcategory="World Wars (WWI, WWII, Weimar)",
        author_sort="Cooper, Andrew Scott",
        title="The Oil Kings",
        ext=".pdf",
        year=2011,
        max_path_length=240,
    )
    assert p == Path(
        "F:\\Books\\01 History\\World Wars (WWI, WWII, Weimar)\\"
        "Cooper, Andrew Scott\\Cooper, Andrew Scott - The Oil Kings (2011).pdf"
    )


def test_compute_shelf_path_truncates_title_only_when_too_long():
    long_title = "A " * 200  # 400 chars
    p = compute_shelf_path(
        library_root=Path("F:\\Books"),
        section="02 Philosophy",
        subcategory="Ethics & Political Philosophy",
        author_sort="Author, Test",
        title=long_title,
        ext=".epub",
        year=1999,
        max_path_length=160,
    )
    assert len(str(p)) <= 160
    assert "…" in p.name           # ellipsis marker present
    assert p.name.endswith("(1999).epub")  # year + ext preserved after the title
    assert p.parent == Path(
        "F:\\Books\\02 Philosophy\\Ethics & Political Philosophy\\Author, Test"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_book_filer_pathsafe.py -q`
Expected: FAIL — `ImportError: cannot import name 'compute_shelf_path'`.

- [ ] **Step 3: Implement `compute_shelf_path` (append to `pathsafe.py`)**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_book_filer_pathsafe.py -q`
Expected: PASS (13 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/pathsafe.py tests/test_book_filer_pathsafe.py
git commit -m "feat(EB-355): add compute_shelf_path with title-only truncation"
```

---

### Task 5: `unique_path` — collision suffixing

**Files:**
- Modify: `tools/book_filer/pathsafe.py`
- Modify: `tests/test_book_filer_pathsafe.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_book_filer_pathsafe.py`:

```python
from book_filer.pathsafe import unique_path


def test_unique_path_returns_input_when_free(tmp_path):
    target = tmp_path / "Book.epub"
    assert unique_path(target) == target


def test_unique_path_suffixes_on_collision(tmp_path):
    (tmp_path / "Book.epub").write_text("x", encoding="utf-8")
    assert unique_path(tmp_path / "Book.epub") == tmp_path / "Book (2).epub"


def test_unique_path_increments_until_free(tmp_path):
    (tmp_path / "Book.epub").write_text("x", encoding="utf-8")
    (tmp_path / "Book (2).epub").write_text("x", encoding="utf-8")
    assert unique_path(tmp_path / "Book.epub") == tmp_path / "Book (3).epub"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_book_filer_pathsafe.py -q`
Expected: FAIL — `ImportError: cannot import name 'unique_path'`.

- [ ] **Step 3: Implement `unique_path` (append to `pathsafe.py`)**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_book_filer_pathsafe.py -q`
Expected: PASS (16 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/pathsafe.py tests/test_book_filer_pathsafe.py
git commit -m "feat(EB-355): add unique_path collision suffixing"
```

---

### Task 6: `has_reparse_in_ancestry` — reject junctions/symlinks (SCRUM-301 defense)

**Files:**
- Create: `tools/book_filer/reparse.py`
- Test: `tests/test_book_filer_reparse.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_book_filer_reparse.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer import reparse


def test_no_reparse_in_clean_tree(tmp_path):
    target = tmp_path / "a" / "b" / "Book.epub"
    assert reparse.has_reparse_in_ancestry(target) is False


def test_detects_reparse_in_ancestry(tmp_path, monkeypatch):
    junction = tmp_path / "linked"
    junction.mkdir()
    target = junction / "child" / "Book.epub"

    def fake_is_reparse(p: Path) -> bool:
        return Path(p) == junction

    monkeypatch.setattr(reparse, "_is_reparse_point", fake_is_reparse)
    assert reparse.has_reparse_in_ancestry(target) is True


def test_detects_reparse_at_leaf(tmp_path, monkeypatch):
    leaf = tmp_path / "Book.epub"
    leaf.write_text("x", encoding="utf-8")
    monkeypatch.setattr(reparse, "_is_reparse_point", lambda p: Path(p) == leaf)
    assert reparse.has_reparse_in_ancestry(leaf) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_book_filer_reparse.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'book_filer.reparse'`.

- [ ] **Step 3: Implement `tools/book_filer/reparse.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_book_filer_reparse.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/reparse.py tests/test_book_filer_reparse.py
git commit -m "feat(EB-355): add reparse-point ancestry rejection (SCRUM-301 defense)"
```

---

### Task 7: `ensure_operational_layout` — idempotent operational-folder scaffolding

**Files:**
- Create: `tools/book_filer/scaffold.py`
- Test: `tests/test_book_filer_scaffold.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_book_filer_scaffold.py`:

```python
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
    assert created_second == []   # nothing new created on the second run
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_book_filer_scaffold.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'book_filer.scaffold'`.

- [ ] **Step 3: Implement `tools/book_filer/scaffold.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_book_filer_scaffold.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the whole new suite + commit**

Run: `python -m pytest tests/test_book_filer_config.py tests/test_book_filer_pathsafe.py tests/test_book_filer_reparse.py tests/test_book_filer_scaffold.py -q`
Expected: PASS (24 passed).

```bash
git add tools/book_filer/scaffold.py tests/test_book_filer_scaffold.py
git commit -m "feat(EB-355): add idempotent operational-folder scaffolding"
```

---

### Task 8: Regression guard — confirm the existing suite still passes

**Files:** none (verification only)

- [ ] **Step 1: Run the full project suite**

Run: `python -m pytest tests/ -q`
Expected: PASS — all pre-existing tests still pass (this plan is additive; the only existing file touched is `config/settings.json`, which gained a new top-level key consumed by nothing yet).

- [ ] **Step 2: If any pre-existing test fails, STOP and diagnose** before continuing — do not stack fixes (per CLAUDE.md testing discipline).

---

## Self-Review

**Spec coverage (this plan's slice):**
- §2 config (`library` block) → Task 1 ✅
- §5.1 naming convention → Task 3 ✅
- §5.1 collision-safe identifier disambiguator → Task 3 (`disambiguator` arg) ✅; selection logic (ISBN→calibre_id→hash priority) belongs to Plan 2's classifier/manifest — noted, not a gap here.
- §5.3 sanitize / reserved names / collapse → Task 2 ✅
- §5.3 long-path title-only truncation → Task 4 ✅
- §5.3 collision suffix → Task 5 ✅
- §5.3 reparse-point rejection across ancestry → Task 6 ✅
- §2/§6 operational folders → Task 7 ✅
- `materialize_mode` config surface → Task 1 ✅ (the copy/hardlink *behavior* is Plan 3's filer)

**Out of scope here (later plans, intentionally):** classifier + `books-taxonomy.json` + metadata extraction + manifest/undo (Plan 2); guarded filer + Calibre + 9-phase migration (Plan 3); reconciliation + automation rewire + completion hook (Plan 4).

**Placeholder scan:** none — every step has runnable code/commands.

**Type consistency:** `LibraryConfig` fields are referenced identically in Tasks 1 and 7; `sanitize_component`/`build_base_name`/`compute_shelf_path`/`unique_path` signatures are consistent across Tasks 2–5; `reparse._is_reparse_point` is the exact name monkeypatched in Task 6's test and defined in its implementation.

---

## Subsequent plans (EB-355 split — for context, authored when this lands)
- **Plan 2 — Classifier + Manifest:** `books-taxonomy.json` (12-section vocabulary + keyword maps), deterministic-rule classifier, embedded PDF/EPUB metadata extraction, the manifest schema (spec §6.1) with `planned_calibre_key`, and the determinism-normalization projection (§6.2).
- **Plan 3 — Filer + Migration:** `Invoke-BookFileGuarded.ps1` (copy-mode materialize, `calibredb add` on apply, `SupportsShouldProcess`, fail-safe), and the 9-phase migration driver (§6) with backup, propose-only first runs, dedup, fragment attribution.
- **Plan 4 — Reconciliation + Rewire:** the Calibre↔shelf reconciliation job (§6.4), the 5-file automation rewire (§9), and the conversion-output completion hook (§6.5, §8 ⑤).
