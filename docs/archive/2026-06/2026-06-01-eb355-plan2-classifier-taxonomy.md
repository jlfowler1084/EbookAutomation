# EB-355 Book Filer — Classifier + Taxonomy Implementation Plan (Plan 2 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **GATED:** Do not begin implementation until PR #174 (Plan 1 foundation) is merged to `master` — done — **and** the local `master` tree is synced (currently blocked by uncommitted `config/settings.json` WIP / coordinated with `fix/EB-356-bookfinder`). Start from a clean worktree off the merged `master`.

**Goal:** A deterministic, config-driven classifier that maps a book's filename to a `(section, subcategory, confidence, disposition)` in the 12-section taxonomy — shelving confident matches, flagging non-book files, and routing ambiguous/low-confidence files to review. The LLM (Qwen) escalation layer is **not** in this plan; this is the deterministic first pass that the later filer escalates from.

**Architecture:** Builds directly on the Plan 1 `tools/book_filer/` package. Two new modules — `taxonomy.py` (loads + indexes a new `config/books-taxonomy.json`) and `classify.py` (scores a filename against the keyword index) — plus the taxonomy data file. Pure functions, fully unit-testable under pytest; no filesystem mutation, no live `F:\Books` access.

**Tech Stack:** Python 3.12, `dataclasses`, `json`, `re`, pytest. Reuses Plan 1's `book_filer.config` patterns.

**Spec:** `docs/superpowers/specs/2026-06-01-fbooks-organization-and-hermes-enforcement-design.md` §4 (taxonomy), §6.3 (non-book boundaries), §7 (deterministic-first → escalation). **Ownership:** book-domain → EbookAutomation (this plan).

---

## Before you start
- Worktree branch `feat/EB-355-plan2-classifier` off the merged `master` (worktree-management skill). Code-only; no data dirs, no junctions.
- Test convention is identical to Plan 1: each test file does `sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))` then imports `book_filer.*`.
- Run: `python -m pytest tests/test_book_filer_taxonomy.py tests/test_book_filer_classify.py -q`.

## File Structure

| File | Responsibility |
|------|----------------|
| `config/books-taxonomy.json` | The 12-section taxonomy: per-subcategory keyword lists + a non-library keyword set + the confidence threshold. The single source of classification vocabulary. |
| `tools/book_filer/taxonomy.py` | `load_taxonomy()` → validated `Taxonomy` with a flattened keyword index. |
| `tools/book_filer/classify.py` | `classify_name(name, taxonomy)` → `Classification` (section, subcategory, confidence, disposition). |
| `tests/test_book_filer_taxonomy.py` | Taxonomy load/validation/index tests. |
| `tests/test_book_filer_classify.py` | Classifier behavior tests. |

---

### Task 1: The taxonomy data file + loader

**Files:**
- Create: `config/books-taxonomy.json`
- Create: `tools/book_filer/taxonomy.py`
- Test: `tests/test_book_filer_taxonomy.py`

- [ ] **Step 1: Create `config/books-taxonomy.json`**

A complete starter taxonomy (keywords are tuned during the §6.2 calibration pass; this is a working baseline, not a placeholder):

```json
{
  "version": 1,
  "confidence_threshold": 0.34,
  "non_library_keywords": [
    "resume", "cover_letter", "cover letter", "_cv", "tax", "1040", "w-2", "w2",
    "passport", "ds82", "boarding", "pasabordo", "insurance", "cobra", "unum",
    "invoice", "receipt", "statement", "declarations page", "return to work",
    "health_card", "health card", "scytl", "robocopy", ".log"
  ],
  "sections": [
    {"code": "01 History", "subcategories": [
      {"name": "World Wars (WWI, WWII, Weimar)", "keywords": ["world war", "wwi", "wwii", "weimar", "stab-in-the-back", "league of nations", "versailles", "nuremberg", "reich"]},
      {"name": "Russia, Soviet & Eastern Europe", "keywords": ["soviet", "bolshevik", "russia", "stalin", "lenin", "ussr", "romanov"]},
      {"name": "Revolution & Political Upheaval", "keywords": ["revolution", "french revolution", "reconstruction", "ancien", "tragedy and hope"]},
      {"name": "Modern & 20th-Century General", "keywords": ["operation paperclip", "twentieth century", "history of"]},
      {"name": "United States & Americas", "keywords": ["american", "washington", "jefferson", "founding", "civil war"]},
      {"name": "Military History", "keywords": ["military", "battle", "war ", "campaign", "wehrmacht"]}
    ]},
    {"code": "02 Philosophy", "subcategories": [
      {"name": "Ancient & Classical", "keywords": ["aristotle", "plato", "stoic", "socrates"]},
      {"name": "Modern & Continental", "keywords": ["nietzsche", "hegel", "heidegger", "feuerbach", "spengler"]},
      {"name": "Ethics & Political Philosophy", "keywords": ["ethics", "leviathan", "social contract", "man versus the state"]},
      {"name": "Logic & Epistemology", "keywords": ["logic", "epistemology", "knowledge"]},
      {"name": "Eastern & Comparative", "keywords": ["tao", "buddhis", "confucian", "vedanta"]}
    ]},
    {"code": "03 Religion & Bible Study", "subcategories": [
      {"name": "Bible Study & Commentary", "keywords": ["bible", "commentary", "ezekiel", "revelation", "genesis", "annotated bible", "study bible", "septuagint"]},
      {"name": "Theology & Doctrine", "keywords": ["theology", "doctrine", "trinity", "soteriology"]},
      {"name": "Christianity (History & Denominations)", "keywords": ["church history", "papacy", "reformation", "catholic", "protestant"]},
      {"name": "Comparative Religion & World Faiths", "keywords": ["world religions", "islam", "judaism", "comparative religion"]},
      {"name": "Apologetics & Devotional", "keywords": ["apologetics", "devotional", "daily reflections"]}
    ]},
    {"code": "04 Politics & Society", "subcategories": [
      {"name": "Marxism & Socialist Theory", "keywords": ["marx", "marxism", "kapital", "communist", "socialism", "kolakowski"]},
      {"name": "Political Ideologies & Geopolitics", "keywords": ["geopolitics", "dugin", "mackinder", "fukuyama", "end of history", "ideology"]},
      {"name": "Economics & Political Economy", "keywords": ["political economy", "public finance", "gruber"]},
      {"name": "Government & International Relations", "keywords": ["foreign policy", "international relations", "diplomacy", "state department"]},
      {"name": "Middle East & Foreign Policy", "keywords": ["iran", "shah", "mossad", "saudi", "israel lobby", "kingdom"]}
    ]},
    {"code": "05 Finance & Investing", "subcategories": [
      {"name": "Stock Market & Trading", "keywords": ["stock", "trading", "technical analysis", "options", "natenberg", "mcmillan"]},
      {"name": "Investing & Personal Finance", "keywords": ["investing", "investor", "portfolio", "reminiscences of a stock operator"]},
      {"name": "Economics (Markets & Theory)", "keywords": ["economics", "market", "lopez de prado"]},
      {"name": "Money, Banking & Macro", "keywords": ["lords of finance", "banking", "federal reserve", "macroeconomic"]},
      {"name": "Business & Entrepreneurship", "keywords": ["startup", "mom test", "running lean", "zero to sold", "entrepreneur"]}
    ]},
    {"code": "06 Fiction & Literature", "subcategories": [
      {"name": "Classic & Literary Fiction", "keywords": ["foucault's pendulum", "eco", "novel"]},
      {"name": "Austen & 19th-Century Novel", "keywords": ["austen", "pride and prejudice", "dickens", "bronte"]},
      {"name": "Poetry & Drama", "keywords": ["paradise lost", "milton", "shakespeare", "tempest", "poetry", "folio"]},
      {"name": "Genre Fiction (SF / Fantasy / Mystery)", "keywords": ["science fiction", "fantasy", "mystery", "sherlock"]},
      {"name": "Literary Criticism", "keywords": ["literary criticism", "critical essays"]}
    ]},
    {"code": "07 Conspiracy, Esoterica & Fringe", "subcategories": [
      {"name": "Conspiracy & Hidden History", "keywords": ["illuminati", "bloodlines", "one nation under blackmail", "conspiracy", "hidden history"]},
      {"name": "Esoteric, Occult, Kabbalah & Theosophy", "keywords": ["kabbalah", "occult", "crowley", "blavatsky", "theosophy", "secret doctrine", "codex magica"]},
      {"name": "Secret Societies (Freemasonry, Illuminati)", "keywords": ["freemason", "masonic", "secret societ"]},
      {"name": "UFO & Paranormal", "keywords": ["ufo", "alien", "abduction", "disclosure", "extraterrestrial", "the threat"]},
      {"name": "Prophecy & Apocalyptic", "keywords": ["prophecy", "apocalyptic", "zeitgeist", "end times"]}
    ]},
    {"code": "08 Biography & Memoir", "subcategories": [
      {"name": "Historical & Political Figures", "keywords": ["a biography", "his excellency", "colonel house", "caesar a biography"]},
      {"name": "Military & War", "keywords": ["memoir of war", "general"]},
      {"name": "Religious & Philosophical Figures", "keywords": ["life of", "saint"]},
      {"name": "Literary & Artistic Lives", "keywords": ["life and times", "artist"]},
      {"name": "Memoir & Autobiography", "keywords": ["memoir", "autobiography", "my life"]}
    ]},
    {"code": "09 Technology, Science & Reference", "subcategories": [
      {"name": "Programming & Software (PowerShell / Python / CS)", "keywords": ["powershell", "python", "algorithm", "designing data-intensive", "programming", "code"]},
      {"name": "Systems, Cloud & IT Admin", "keywords": ["windows server", "intune", "domain controller", "azure", "cloud"]},
      {"name": "Science & Academic Papers", "keywords": ["quantum", "neutrino", "astronomy", "attention is all you need", "bert", "arxiv"]},
      {"name": "AI & Prompt Engineering", "keywords": ["prompt engineering", "machine learning", "neural", "llm"]},
      {"name": "Reference & Encyclopedic", "keywords": ["encyclopedia", "dictionary", "handbook", "atlas"]}
    ]},
    {"code": "10 How-To, Hobbies & Practical", "subcategories": [
      {"name": "Crafts, Hobbies & Music", "keywords": ["woodwork", "piano", "guitar", "knitting", "hobby"]},
      {"name": "Home, Garden & Aquatics", "keywords": ["aquaponic", "aquarium", "garden", "planted aquarium"]},
      {"name": "Health, Fitness & Cooking", "keywords": ["cookbook", "recipe", "pressure cooker", "fitness", "diet"]},
      {"name": "Career & Job Search (how-to)", "keywords": ["resume how", "tech resume", "cloud resume challenge", "career"]},
      {"name": "Recovery & 12-Step", "keywords": ["twelve steps", "alcoholics anonymous", "adult children of alcoholics", "12-step", "guided workbook"]}
    ]},
    {"code": "11 Writing & Children's Books", "subcategories": [
      {"name": "Writing the Children's Book", "keywords": ["children's book", "picture book", "kidlit"]},
      {"name": "Craft of Writing (General)", "keywords": ["writing craft", "on writing", "story structure"]},
      {"name": "Publishing & Self-Publishing", "keywords": ["self-publish", "kdp", "publishing"]},
      {"name": "Picture Books & Read-Alouds (study)", "keywords": ["read-aloud", "read aloud"]}
    ]},
    {"code": "12 Periodicals & Magazines", "subcategories": [
      {"name": "By Publication Title", "keywords": ["magazine", "culture wars", "issue", "vol.", "no."]}
    ]}
  ]
}
```

- [ ] **Step 2: Write the failing test `tests/test_book_filer_taxonomy.py`**

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.taxonomy import Taxonomy, load_taxonomy


def test_load_taxonomy_real_file():
    tax = load_taxonomy()
    assert isinstance(tax, Taxonomy)
    assert len(tax.sections) == 12
    assert "01 History" in tax.sections
    assert 0.0 < tax.confidence_threshold < 1.0
    assert "passport" in tax.non_library_keywords


def test_keyword_index_maps_to_section_subcategory():
    tax = load_taxonomy()
    hits = tax.lookup("weimar")
    assert ("01 History", "World Wars (WWI, WWII, Weimar)") in hits


def test_lookup_is_case_insensitive_and_empty_for_unknown():
    tax = load_taxonomy()
    assert tax.lookup("WEIMAR") == tax.lookup("weimar")
    assert tax.lookup("zzz-nonsense") == set()


def test_load_taxonomy_rejects_duplicate_section_codes(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"version":1,"confidence_threshold":0.3,"non_library_keywords":[],'
        '"sections":[{"code":"X","subcategories":[]},{"code":"X","subcategories":[]}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate section"):
        load_taxonomy(bad)
```

- [ ] **Step 3: Run — confirm it fails**

Run: `python -m pytest tests/test_book_filer_taxonomy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'book_filer.taxonomy'`.

- [ ] **Step 4: Implement `tools/book_filer/taxonomy.py`**

```python
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
    sections: dict[str, tuple[str, ...]]              # section code -> subcategory names
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
```

- [ ] **Step 5: Run — confirm 4 passed**

Run: `python -m pytest tests/test_book_filer_taxonomy.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add config/books-taxonomy.json tools/book_filer/taxonomy.py tests/test_book_filer_taxonomy.py
git commit -m "feat(EB-355): add books-taxonomy.json + taxonomy loader/index"
```

---

### Task 2: The deterministic classifier

**Files:**
- Create: `tools/book_filer/classify.py`
- Test: `tests/test_book_filer_classify.py`

- [ ] **Step 1: Write the failing test `tests/test_book_filer_classify.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.taxonomy import load_taxonomy
from book_filer.classify import Classification, classify_name

TAX = load_taxonomy()


def test_classifies_clear_history_title():
    r = classify_name("The Stab-in-the-Back Myth and the Fall of the Weimar Republic.pdf", TAX)
    assert r.disposition == "shelf"
    assert r.section == "01 History"
    assert r.subcategory == "World Wars (WWI, WWII, Weimar)"
    assert r.confidence >= TAX.confidence_threshold


def test_flags_non_library_file():
    r = classify_name("Joseph_Fowler_Resume_Updated.pdf", TAX)
    assert r.disposition == "non_library"
    assert r.section is None


def test_unmatched_filename_routes_to_review():
    r = classify_name("-jd55w3j.pdf", TAX)
    assert r.disposition == "review"
    assert r.confidence == 0.0


def test_marxism_primary_source_goes_to_politics():
    r = classify_name("Kolakowski - Main Currents of Marxism.pdf", TAX)
    assert r.disposition == "shelf"
    assert r.section == "04 Politics & Society"
    assert r.subcategory == "Marxism & Socialist Theory"


def test_classification_is_deterministic():
    name = "Aleister Crowley - Book Of The Law.pdf"
    assert classify_name(name, TAX) == classify_name(name, TAX)
```

- [ ] **Step 2: Run — confirm it fails**

Run: `python -m pytest tests/test_book_filer_classify.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'book_filer.classify'`.

- [ ] **Step 3: Implement `tools/book_filer/classify.py`**

```python
"""Deterministic filename classifier (spec §7 deterministic-first pass).

Disposition is one of:
- "non_library": a non-book file (resume, tax form, ...) — never shelved.
- "shelf": a confident (section, subcategory) match at/above the threshold.
- "review": no match or a low-confidence/tie — routed to _Needs_Review.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .taxonomy import Taxonomy


@dataclass(frozen=True)
class Classification:
    disposition: str                 # "shelf" | "review" | "non_library"
    section: str | None
    subcategory: str | None
    confidence: float
    source: str = "rule"


def classify_name(name: str, taxonomy: Taxonomy) -> Classification:
    text = name.lower()

    # 1. Non-library short-circuit.
    if any(kw in text for kw in taxonomy.non_library_keywords):
        return Classification("non_library", None, None, 1.0)

    # 2. Score every (section, subcategory) by distinct keyword hits.
    scores: Counter[tuple[str, str]] = Counter()
    for keyword, targets in taxonomy._index.items():
        if keyword in text:
            for target in targets:
                scores[target] += 1

    if not scores:
        return Classification("review", None, None, 0.0)

    ranked = scores.most_common()
    (best_section, best_sub), best_hits = ranked[0]
    runner_hits = ranked[1][1] if len(ranked) > 1 else 0

    total = sum(scores.values())
    confidence = best_hits / total  # share of hits the winner owns; 1.0 == unambiguous

    # 3. A genuine tie across different sections is ambiguous -> review.
    tie = runner_hits == best_hits and ranked[1][0][0] != best_section
    if tie or confidence < taxonomy.confidence_threshold:
        return Classification("review", best_section, best_sub, confidence)

    return Classification("shelf", best_section, best_sub, confidence)
```

- [ ] **Step 4: Run — confirm 5 passed**

Run: `python -m pytest tests/test_book_filer_classify.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/classify.py tests/test_book_filer_classify.py
git commit -m "feat(EB-355): add deterministic filename classifier"
```

---

### Task 3: Regression guard

**Files:** none (verification only)

- [ ] **Step 1: Run the book_filer suite + the existing config consumer test**

Run: `python -m pytest tests/test_book_filer_config.py tests/test_book_filer_pathsafe.py tests/test_book_filer_reparse.py tests/test_book_filer_scaffold.py tests/test_book_filer_taxonomy.py tests/test_book_filer_classify.py -q`
Expected: PASS (26 from Plan 1 + 9 new = 35 passed).

- [ ] **Step 2: If anything pre-existing fails, STOP and diagnose** before continuing (additive change; only a new config file + two new modules).

---

## Self-Review

**Spec coverage (this plan's slice):**
- §4 12-section taxonomy as a config vocabulary → Task 1 ✅
- §6.3 non-book boundary detection → `non_library` disposition (Task 2) ✅
- §7 deterministic-first classification with review routing → Task 2 ✅ (the Qwen escalation is the later filer's job — out of scope here, intentionally)
- §6.2 confidence threshold surfaced as config → Task 1/2 ✅

**Out of scope (later plans):** embedded PDF/EPUB metadata extraction + the manifest/undo engine (Plan 3); the guarded filer + 9-phase migration (Plan 4); reconciliation + the automation rewire — coordinated with `fix/EB-356-bookfinder` for the `BookFinder.output_root → _Inbox` repoint (Plan 5).

**Placeholder scan:** none — `books-taxonomy.json` ships a working keyword baseline (tuned during calibration, not a TODO).

**Type consistency:** `Taxonomy.lookup` / `_index` shape is identical in Tasks 1 and 2; `Classification` fields are referenced consistently in the classifier and its tests.

---

## Revised plan sequence (EB-355 split, updated)
1. **Plan 1 — Foundation** (merged, PR #174): config, path-safety, reparse guard, scaffolding.
2. **Plan 2 — Classifier + Taxonomy** (this plan): `books-taxonomy.json`, loader/index, deterministic classifier.
3. **Plan 3 — Metadata + Manifest:** embedded PDF/EPUB metadata extraction (better-than-filename signal), `planned_calibre_key`, the manifest schema (spec §6.1) + undo engine + determinism-normalization (§6.2).
4. **Plan 4 — Guarded Filer + Migration:** `Invoke-BookFileGuarded.ps1` (copy-mode materialize, `calibredb add` on apply, Qwen escalation for `review`-disposition files), the 9-phase migration driver, dedup, fragment attribution.
5. **Plan 5 — Reconciliation + Rewire:** the Calibre↔shelf reconciliation job, the 5-file automation rewire (**coordinated with EB-356** for BookFinder), and the conversion-output completion hook.
