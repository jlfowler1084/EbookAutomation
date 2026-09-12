# EB-355 Book Filer — Metadata Extraction + Identity Implementation Plan (Plan 3 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **GATED:** Implementation begins only after Plan 2 (classifier + taxonomy) is merged. Start from a clean worktree off the latest `master`.

**Goal:** Extract embedded metadata (title, author, year, ISBN, series) from PDF and EPUB files — a stronger signal than the filename for classification and naming — and derive a **deterministic** `planned_calibre_key` for dry-run/plan manifests (so plans are reproducible without mutating Calibre or assigning real IDs).

**Architecture:** Two new pure-ish modules in the existing `tools/book_filer/` package: `metadata.py` (format-dispatched extraction; degrades gracefully to `None`s on any failure) and `identity.py` (the deterministic key). EPUB parsing uses stdlib `zipfile` + `xml.etree`; PDF uses `pypdf` (already a project dependency). No live `F:\Books` access — tests generate their own fixture files in `tmp_path`.

**Tech Stack:** Python 3.12, `zipfile`, `xml.etree.ElementTree`, `pypdf`, `dataclasses`, `re`, pytest.

**Spec:** `docs/superpowers/specs/2026-06-01-fbooks-organization-and-hermes-enforcement-design.md` §5.2 (collision-safe identifier), §6.1 (`planned_calibre_key`), §6.3 (filename-insufficient files need embedded metadata). **Ownership:** book-domain → EbookAutomation.

---

## Before you start
- Worktree branch `feat/EB-355-plan3-metadata` off the latest `master` (worktree-management skill). Code-only.
- Confirm `pypdf` is importable: `python -c "import pypdf; print(pypdf.__version__)"`. It is listed in the project's requirements; if missing, `py -3.12 -m pip install pypdf`.
- Test convention matches Plans 1–2: `sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))` then `from book_filer.* import ...`.
- Run: `python -m pytest tests/test_book_filer_metadata.py tests/test_book_filer_identity.py -q`.

## File Structure

| File | Responsibility |
|------|----------------|
| `tools/book_filer/metadata.py` | `extract_metadata(path)` → `BookMetadata`, dispatching on extension; graceful `None`s on failure. |
| `tools/book_filer/identity.py` | `planned_calibre_key(meta, content_sha256)` → deterministic key (ISBN → normalized author+title+year → sha). |
| `tests/test_book_filer_metadata.py` | EPUB + PDF + fallback extraction (fixtures generated in-test). |
| `tests/test_book_filer_identity.py` | Key-derivation priority + determinism. |

---

### Task 1: Embedded metadata extraction

**Files:**
- Create: `tools/book_filer/metadata.py`
- Test: `tests/test_book_filer_metadata.py`

- [ ] **Step 1: Write the failing test `tests/test_book_filer_metadata.py`**

```python
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.metadata import BookMetadata, extract_metadata


def _make_epub(path: Path, title: str, author: str, date: str, isbn: str | None = None) -> None:
    ident = f'<dc:identifier id="bookid">urn:isbn:{isbn}</dc:identifier>' if isbn else ""
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:title>{title}</dc:title><dc:creator>{author}</dc:creator>"
        f"<dc:date>{date}</dc:date>{ident}"
        "</metadata><manifest/><spine/></package>"
    )
    container = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
        '<rootfiles><rootfile full-path="content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("content.opf", opf)


def _make_pdf(path: Path, title: str, author: str) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_metadata({"/Title": title, "/Author": author, "/CreationDate": "D:20110101000000"})
    with open(path, "wb") as fh:
        writer.write(fh)


def test_extract_epub_metadata(tmp_path):
    epub = tmp_path / "book.epub"
    _make_epub(epub, "The Oil Kings", "Andrew Scott Cooper", "2011-09-08", isbn="9781416597865")
    meta = extract_metadata(epub)
    assert meta == BookMetadata(
        title="The Oil Kings", author="Andrew Scott Cooper", year=2011, isbn="9781416597865",
    )


def test_extract_pdf_metadata(tmp_path):
    pdf = tmp_path / "book.pdf"
    _make_pdf(pdf, "Designing Data-Intensive Applications", "Martin Kleppmann")
    meta = extract_metadata(pdf)
    assert meta.title == "Designing Data-Intensive Applications"
    assert meta.author == "Martin Kleppmann"
    assert meta.year == 2011
    assert meta.isbn is None


def test_unknown_extension_returns_empty(tmp_path):
    other = tmp_path / "book.txt"
    other.write_text("x", encoding="utf-8")
    assert extract_metadata(other) == BookMetadata(None, None, None, None)


def test_corrupt_epub_degrades_gracefully(tmp_path):
    bad = tmp_path / "bad.epub"
    bad.write_text("not a zip", encoding="utf-8")
    assert extract_metadata(bad) == BookMetadata(None, None, None, None)
```

- [ ] **Step 2: Run — confirm it fails**

Run: `python -m pytest tests/test_book_filer_metadata.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'book_filer.metadata'`.

- [ ] **Step 3: Implement `tools/book_filer/metadata.py`**

```python
"""Embedded PDF/EPUB metadata extraction (spec §5.2, §6.3).

Always degrades to all-``None`` on any failure — a missing/corrupt file must
never raise into the filer; it simply yields no metadata and falls back to the
filename classifier.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

_DC = "{http://purl.org/dc/elements/1.1/}"
_CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
_YEAR_RE = re.compile(r"(\d{4})")
_ISBN_RE = re.compile(r"(\d{13}|\d{9}[\dXx])")


@dataclass(frozen=True)
class BookMetadata:
    title: str | None
    author: str | None
    year: int | None
    isbn: str | None
    series: str | None = None
    series_index: str | None = None


def _year_from(text: str | None) -> int | None:
    if not text:
        return None
    m = _YEAR_RE.search(text)
    return int(m.group(1)) if m else None


def _extract_epub(path: Path) -> BookMetadata:
    try:
        with zipfile.ZipFile(path) as zf:
            container = ET.fromstring(zf.read("META-INF/container.xml"))
            rootfile = container.find(".//c:rootfile", _CONTAINER_NS)
            opf = ET.fromstring(zf.read(rootfile.get("full-path")))
    except (KeyError, OSError, zipfile.BadZipFile, ET.ParseError, AttributeError):
        return BookMetadata(None, None, None, None)

    def _txt(tag: str) -> str | None:
        el = opf.find(f".//{_DC}{tag}")
        return el.text.strip() if el is not None and el.text else None

    isbn = None
    for ident in opf.findall(f".//{_DC}identifier"):
        if ident.text:
            m = _ISBN_RE.search(ident.text.replace("-", ""))
            if m:
                isbn = m.group(1)
                break

    return BookMetadata(_txt("title"), _txt("creator"), _year_from(_txt("date")), isbn)


def _extract_pdf(path: Path) -> BookMetadata:
    try:
        from pypdf import PdfReader

        info = PdfReader(str(path)).metadata
    except Exception:  # pypdf raises a variety of types on malformed PDFs
        return BookMetadata(None, None, None, None)
    if not info:
        return BookMetadata(None, None, None, None)
    title = info.title or None
    author = info.author or None
    year = _year_from(str(info.get("/CreationDate", "")))
    return BookMetadata(title, author, year, None)


def extract_metadata(path: Path) -> BookMetadata:
    """Best-effort embedded metadata; all-``None`` for unknown/unreadable files."""
    ext = Path(path).suffix.lower()
    if ext == ".epub":
        return _extract_epub(Path(path))
    if ext == ".pdf":
        return _extract_pdf(Path(path))
    return BookMetadata(None, None, None, None)
```

- [ ] **Step 4: Run — confirm 4 passed**

Run: `python -m pytest tests/test_book_filer_metadata.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/metadata.py tests/test_book_filer_metadata.py
git commit -m "feat(EB-355): add embedded PDF/EPUB metadata extraction"
```

---

### Task 2: Deterministic `planned_calibre_key`

**Files:**
- Create: `tools/book_filer/identity.py`
- Test: `tests/test_book_filer_identity.py`

- [ ] **Step 1: Write the failing test `tests/test_book_filer_identity.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.metadata import BookMetadata
from book_filer.identity import planned_calibre_key

_SHA = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"


def test_isbn_takes_priority():
    meta = BookMetadata("Title", "Author", 2011, "978-1-4165-9786-5")
    assert planned_calibre_key(meta, _SHA) == "isbn:9781416597865"


def test_falls_back_to_normalized_author_title_year():
    meta = BookMetadata("The Oil Kings", "Cooper, Andrew Scott", 2011, None)
    assert planned_calibre_key(meta, _SHA) == "meta:cooper-andrew-scott|the-oil-kings|2011"


def test_falls_back_to_sha_when_no_usable_metadata():
    meta = BookMetadata(None, None, None, None)
    assert planned_calibre_key(meta, _SHA) == f"sha:{_SHA[:16]}"


def test_is_deterministic():
    meta = BookMetadata("The Oil Kings", "Cooper, Andrew Scott", 2011, None)
    assert planned_calibre_key(meta, _SHA) == planned_calibre_key(meta, _SHA)
```

- [ ] **Step 2: Run — confirm it fails**

Run: `python -m pytest tests/test_book_filer_identity.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'book_filer.identity'`.

- [ ] **Step 3: Implement `tools/book_filer/identity.py`**

```python
"""Deterministic identity key for plan manifests (spec §6.1, §5.2).

A plan/dry-run manifest must be reproducible WITHOUT mutating Calibre or
assigning real IDs. ``planned_calibre_key`` derives a stable key from the most
authoritative signal available: ISBN, else normalized author+title+year, else a
truncated content hash.
"""
from __future__ import annotations

import re

from .metadata import BookMetadata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize(text: str) -> str:
    return _NON_ALNUM.sub("-", text.lower()).strip("-")


def planned_calibre_key(meta: BookMetadata, content_sha256: str) -> str:
    if meta.isbn:
        digits = re.sub(r"[^0-9Xx]", "", meta.isbn)
        return f"isbn:{digits}"
    if meta.author and meta.title:
        year = str(meta.year) if meta.year else ""
        return f"meta:{_normalize(meta.author)}|{_normalize(meta.title)}|{year}"
    return f"sha:{content_sha256[:16]}"
```

- [ ] **Step 4: Run — confirm 4 passed**

Run: `python -m pytest tests/test_book_filer_identity.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/identity.py tests/test_book_filer_identity.py
git commit -m "feat(EB-355): add deterministic planned_calibre_key"
```

---

### Task 3: Regression guard

**Files:** none (verification only)

- [ ] **Step 1: Run the whole book_filer suite**

Run: `python -m pytest tests/test_book_filer_config.py tests/test_book_filer_pathsafe.py tests/test_book_filer_reparse.py tests/test_book_filer_scaffold.py tests/test_book_filer_taxonomy.py tests/test_book_filer_classify.py tests/test_book_filer_metadata.py tests/test_book_filer_identity.py -q`
Expected: PASS (35 from Plans 1–2 + 8 new = 43 passed).

- [ ] **Step 2: If anything pre-existing fails, STOP and diagnose** (this plan is additive — two new modules + two new test files).

---

## Self-Review

**Spec coverage (this plan's slice):**
- §5.2 collision-safe identifier inputs (ISBN/author/title/year) → Task 1 + 2 ✅
- §6.1 deterministic `planned_calibre_key` for plan manifests → Task 2 ✅
- §6.3 embedded metadata for files where the filename is insufficient → Task 1 ✅
- Graceful degradation (never raise into the filer) → Task 1 (the `corrupt_epub` test) ✅

**Out of scope (later plans, intentionally):** the manifest schema + CSV/JSON writer + undo-script generator + determinism-normalization (Plan 4, beside the migration driver that emits it); the guarded filer + 9-phase migration (Plan 4); reconciliation + automation rewire coordinated with EB-356 (Plan 5).

**Placeholder scan:** none — complete code and runnable fixtures throughout.

**Type consistency:** `BookMetadata` is defined in `metadata.py` and consumed identically in `identity.py` and both test files; `planned_calibre_key(meta, content_sha256)` signature is consistent.

---

## Revised plan sequence (EB-355 split)
1. **Plan 1 — Foundation** (merged): config, path-safety, reparse guard, scaffolding.
2. **Plan 2 — Classifier + Taxonomy** (merged): `books-taxonomy.json`, loader, deterministic classifier.
3. **Plan 3 — Metadata + Identity** (this plan): embedded PDF/EPUB extraction, `planned_calibre_key`.
4. **Plan 4 — Manifest + Guarded Filer + Migration:** the manifest schema/engine (spec §6.1) + undo + determinism-normalization (§6.2), `Invoke-BookFileGuarded.ps1` (copy-mode materialize, `calibredb add` on apply, Qwen escalation for `review`-disposition files), and the 9-phase migration driver (backup, dedup, fragment attribution).
5. **Plan 5 — Reconciliation + Rewire:** the Calibre↔shelf reconciliation job, the 5-file automation rewire (**coordinated with `fix/EB-356-bookfinder`** for `BookFinder.output_root → _Inbox`), and the conversion-output completion hook.
