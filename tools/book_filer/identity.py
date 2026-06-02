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
# A real ISBN is 13 digits or 9 digits + a check char (X). A truthy-but-shapeless
# value like "N/A" must not produce a bare/garbage "isbn:" key, which would
# collide every junk-ISBN book onto one identity. Mirrors metadata._ISBN_RE.
_ISBN_SHAPE = re.compile(r"(?:\d{13}|\d{9}[\dX])$")


def _normalize(text: str) -> str:
    return _NON_ALNUM.sub("-", text.lower()).strip("-")


def planned_calibre_key(meta: BookMetadata, content_sha256: str) -> str:
    if meta.isbn:
        digits = re.sub(r"[^0-9Xx]", "", meta.isbn).upper()
        if _ISBN_SHAPE.fullmatch(digits):
            return f"isbn:{digits}"
    if meta.author and meta.title:
        year = str(meta.year) if meta.year else ""
        return f"meta:{_normalize(meta.author)}|{_normalize(meta.title)}|{year}"
    return f"sha:{content_sha256.lower()[:16]}"
