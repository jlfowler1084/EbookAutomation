"""Load and index config/books-taxonomy.json (spec §4)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# tools/book_filer/taxonomy.py -> parents[2] == repo root
_DEFAULT_TAXONOMY = Path(__file__).resolve().parents[2] / "config" / "books-taxonomy.json"


@dataclass(frozen=True)
class Taxonomy:
    confidence_threshold: float
    non_library_keywords: tuple[str, ...]
    sections: dict[str, tuple[str, ...]]
    _index: dict[str, set[tuple[str, str]]] = field(default_factory=dict)

    def lookup(self, keyword: str) -> set[tuple[str, str]]:
        """Return the set of (section, subcategory) a keyword maps to."""
        return self._index.get(keyword.lower(), set())


def load_taxonomy(path: Path | None = None) -> Taxonomy:
    data = json.loads((Path(path) if path else _DEFAULT_TAXONOMY).read_text(encoding="utf-8"))

    sections: dict[str, tuple[str, ...]] = {}
    index: dict[str, set[tuple[str, str]]] = {}
    for section in data["sections"]:
        code = section["code"]
        if code in sections:
            raise ValueError(f"duplicate section code: {code!r}")
        subs = tuple(s["name"] for s in section["subcategories"])
        sections[code] = subs
        for sub in section["subcategories"]:
            for kw in sub["keywords"]:
                index.setdefault(kw.lower(), set()).add((code, sub["name"]))

    return Taxonomy(
        confidence_threshold=float(data["confidence_threshold"]),
        non_library_keywords=tuple(k.lower() for k in data["non_library_keywords"]),
        sections=sections,
        _index=index,
    )
