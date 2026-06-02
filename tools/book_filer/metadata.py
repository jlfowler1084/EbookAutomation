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
