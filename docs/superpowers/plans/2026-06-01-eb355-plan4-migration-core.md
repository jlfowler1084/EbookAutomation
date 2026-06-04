# EB-355 Book Filer — Migration Core (Decide + Record) Implementation Plan (Plan 4 of 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **GATED:** Begin only after Plan 3 (metadata + identity) is merged. **This plan performs NO filesystem mutation of `F:\Books`** — it produces manifests, dedup decisions, fragment verdicts, and calibration verdicts. The actuator that actually moves files is Plan 5 and is fenced behind backup + calibration + approval + ADR-0045 gates. Start from a clean worktree off the latest `master` (now `fdf3694`, EB-356 merged).

**Goal:** Build the "migration brain" — the pure, testable decision-and-record layer: the manifest engine (schema + CSV/JSON/MD writer + deterministic projection + undo-script generator), duplicate planning (merge-formats + keep-best-of-exact), fragment attribution (review-only), and the calibration verdict (zero-wrong-shelf + determinism). None of it touches `F:\Books`.

**Architecture:** Four new Python modules in `tools/book_filer/`, each pure logic over in-memory records or `tmp_path`. They consume the Plan 1–3 primitives (`pathsafe`, `classify`, `metadata`, `identity`). Decisions locked in the Plan 4 brainstorm (2026-06-01): **merge formats; keep best of exact dups · review-only fragments · green = determinism + zero wrong-shelf + sign-off · backup must be different-drive/fresh/count-verified** (the backup gate is enforced by Plan 5's actuator; recorded here as the manifest's `apply_preconditions`).

**Tech Stack:** Python 3.12, `dataclasses`, `csv`, `json`, `re`, pytest.

**Spec:** `docs/superpowers/specs/2026-06-01-fbooks-organization-and-hermes-enforcement-design.md` §6.1 (manifest), §6.2 (determinism), §6.3 (fragments), §6.4 (multi-format), §6 Phase table (calibration gate). **Ownership:** book-domain → EbookAutomation.

---

## Before you start
- Worktree branch `feat/EB-355-plan4-migration-core` off `master`. Code-only; **no migration is run** by this plan.
- All times/IDs are passed IN to functions (tests supply a fixed `stamp`); never call `Date.now()`-equivalents inside the engine — manifests must be reproducible.
- Test convention as in Plans 1–3.
- Run: `python -m pytest tests/test_book_filer_manifest.py tests/test_book_filer_dedup.py tests/test_book_filer_fragments.py tests/test_book_filer_calibration.py -q`.

## File Structure

| File | Responsibility |
|------|----------------|
| `tools/book_filer/manifest.py` | `ManifestRow` (spec §6.1) + `write_manifest` (CSV/JSON/MD) + `canonical_projection` (§6.2 determinism) + `generate_undo_script`. |
| `tools/book_filer/dedup.py` | `plan_dedup(files)` → per-group keeper + per-path action (`keep`/`merge-format`/`trash`) under the merge-formats rule. |
| `tools/book_filer/fragments.py` | `detect_fragment_sets(paths)` → fragment sets, all routed to `review` (never auto-trash). |
| `tools/book_filer/calibration.py` | `evaluate_calibration(...)` → green/red verdict (determinism + zero wrong-shelf + sign-off). |
| `tests/test_book_filer_{manifest,dedup,fragments,calibration}.py` | One test file each. |

---

### Task 1: Manifest engine

**Files:**
- Create: `tools/book_filer/manifest.py`
- Test: `tests/test_book_filer_manifest.py`

- [ ] **Step 1: Write the failing test `tests/test_book_filer_manifest.py`**

```python
import sys
import json
import csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.manifest import ManifestRow, write_manifest, canonical_projection, generate_undo_script


def _row(**kw) -> ManifestRow:
    base = dict(
        original_path=r"F:\Books\_Inbox\x.epub", destination_path=r"F:\Books\01 History\a.epub",
        sha256="abc123", size=10, planned_calibre_key="isbn:9780", calibre_id=None, isbn="9780",
        format="epub", section="01 History", subcategory="Modern & 20th-Century General",
        author_sort="A, B", title="T", year=2000, duplicate_group_id=None, canonical_reason=None,
        classification_confidence=0.9, classification_source="rule", taxonomy_version=1,
        tool_version="0.4.0", action="copy", undo_action="Remove-Item -LiteralPath dest", review_required=False,
    )
    base.update(kw)
    return ManifestRow(**base)


def test_write_manifest_emits_csv_json_md(tmp_path):
    base = write_manifest([_row()], tmp_path, stamp="20260601-000000")
    assert Path(f"{base}.csv").exists() and Path(f"{base}.json").exists() and Path(f"{base}.md").exists()
    data = json.loads(Path(f"{base}.json").read_text(encoding="utf-8"))
    assert data[0]["section"] == "01 History"
    with open(f"{base}.csv", encoding="utf-8") as f:
        assert next(csv.DictReader(f))["action"] == "copy"


def test_canonical_projection_is_order_and_calibre_id_invariant():
    a = [_row(original_path="b", calibre_id=None), _row(original_path="a", calibre_id=None)]
    b = [_row(original_path="a", calibre_id="123"), _row(original_path="b", calibre_id="456")]
    # Sorted by original_path AND calibre_id dropped -> identical projection (determinism gate).
    assert canonical_projection(a) == canonical_projection(b)


def test_canonical_projection_detects_real_drift():
    a = [_row(original_path="a", section="01 History")]
    b = [_row(original_path="a", section="04 Politics & Society")]
    assert canonical_projection(a) != canonical_projection(b)


def test_generate_undo_script_reverses_in_order(tmp_path):
    rows = [_row(original_path="a", undo_action="Move-Item A"), _row(original_path="b", undo_action="Move-Item B")]
    script = generate_undo_script(rows)
    # Undo replays in REVERSE order (last action undone first).
    assert script.index("Move-Item B") < script.index("Move-Item A")
    assert script.startswith("#")  # a commented header
```

- [ ] **Step 2: Run — confirm fail**

Run: `python -m pytest tests/test_book_filer_manifest.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `tools/book_filer/manifest.py`**

```python
"""Migration manifest engine (spec §6.1, §6.2). Pure: writes files, mutates no library."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

# calibre_id is assigned only at APPLY (Plan 5); excluded from the determinism projection.
_VOLATILE = {"calibre_id"}


@dataclass
class ManifestRow:
    original_path: str
    destination_path: str
    sha256: str
    size: int
    planned_calibre_key: str
    calibre_id: str | None
    isbn: str | None
    format: str
    section: str | None
    subcategory: str | None
    author_sort: str | None
    title: str | None
    year: int | None
    duplicate_group_id: str | None
    canonical_reason: str | None
    classification_confidence: float
    classification_source: str
    taxonomy_version: int
    tool_version: str
    action: str
    undo_action: str
    review_required: bool


_FIELD_NAMES = [f.name for f in fields(ManifestRow)]


def write_manifest(rows: list[ManifestRow], out_dir: Path, stamp: str) -> Path:
    """Write plan-<stamp>.{csv,json,md}; returns the path stem. `stamp` is supplied by the caller."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"plan-{stamp}"
    dicts = [asdict(r) for r in rows]

    with open(f"{base}.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELD_NAMES)
        writer.writeheader()
        writer.writerows(dicts)

    Path(f"{base}.json").write_text(json.dumps(dicts, indent=2), encoding="utf-8")

    lines = [f"# Migration plan {stamp}", "", f"{len(rows)} item(s).", ""]
    lines += ["| action | section | subcategory | original → destination |",
              "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r.action} | {r.section or ''} | {r.subcategory or ''} | "
                     f"`{r.original_path}` → `{r.destination_path}` |")
    Path(f"{base}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return base


def canonical_projection(rows: list[ManifestRow]) -> str:
    """Deterministic projection for the calibration gate: sorted by original_path,
    volatile fields dropped, keys sorted. Identical inputs -> identical string."""
    projected = []
    for row in sorted(rows, key=lambda r: r.original_path):
        projected.append({k: v for k, v in asdict(row).items() if k not in _VOLATILE})
    return json.dumps(projected, sort_keys=True)


def generate_undo_script(rows: list[ManifestRow]) -> str:
    """Emit a PowerShell undo script that replays each row's undo_action in REVERSE order."""
    out = [
        "# Auto-generated undo script. Reverses the migration actions, last-first.",
        "$ErrorActionPreference = 'Stop'",
    ]
    for row in reversed(rows):
        if row.undo_action:
            out.append(row.undo_action)
    return "\n".join(out) + "\n"
```

- [ ] **Step 4: Run — confirm 4 passed.** `python -m pytest tests/test_book_filer_manifest.py -q`

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/manifest.py tests/test_book_filer_manifest.py
git commit -m "feat(EB-355): add migration manifest engine (schema, write, projection, undo)"
```

---

### Task 2: Duplicate planning (merge formats; keep best of exact dups)

**Files:**
- Create: `tools/book_filer/dedup.py`
- Test: `tests/test_book_filer_dedup.py`

- [ ] **Step 1: Write the failing test `tests/test_book_filer_dedup.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.dedup import FileInfo, plan_dedup


def test_format_twins_are_all_kept_as_merge_format():
    files = [
        FileInfo("a.epub", "h1", "epub", 100, True, "cooper|oilkings|2011"),
        FileInfo("a.pdf", "h2", "pdf", 200, True, "cooper|oilkings|2011"),
    ]
    decisions = {d.path: d.action for group in plan_dedup(files) for d in group.members}
    # Different formats of the same work are both kept (one canonical 'keep', the other 'merge-format').
    assert set(decisions.values()) == {"keep", "merge-format"}


def test_exact_same_format_dup_collapses_to_best():
    files = [
        FileInfo("Book (1).epub", "h", "epub", 100, False, "w"),
        FileInfo("Book.epub", "h", "epub", 100, True, "w"),  # has metadata -> keeper
    ]
    [group] = plan_dedup(files)
    keep = [m for m in group.members if m.action == "keep"]
    trash = [m for m in group.members if m.action == "trash"]
    assert [m.path for m in keep] == ["Book.epub"]
    assert [m.path for m in trash] == ["Book (1).epub"]


def test_distinct_works_are_not_grouped():
    files = [
        FileInfo("x.epub", "h1", "epub", 1, True, "work-a"),
        FileInfo("y.epub", "h2", "epub", 1, True, "work-b"),
    ]
    assert len(plan_dedup(files)) == 2


def test_keeper_tiebreak_is_deterministic():
    files = [
        FileInfo("Book.epub", "h", "epub", 100, False, "w"),
        FileInfo("Book copy.epub", "h", "epub", 100, False, "w"),
    ]
    a = [m.action for g in plan_dedup(files) for m in g.members]
    b = [m.action for g in plan_dedup(files) for m in g.members]
    assert a == b  # stable ordering, no randomness
```

- [ ] **Step 2: Run — confirm fail.**

- [ ] **Step 3: Implement `tools/book_filer/dedup.py`**

```python
"""Duplicate planning (spec §6.4). Merge formats; collapse exact same-format dups to the best copy.

No filesystem access — operates on FileInfo records the caller has gathered.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_REDOWNLOAD_RE = re.compile(r"\((\d+)\)|copy", re.IGNORECASE)


@dataclass(frozen=True)
class FileInfo:
    path: str
    sha256: str
    format: str        # "epub", "pdf", ...
    size: int
    has_metadata: bool
    work_key: str      # normalized author|title|year (from identity)


@dataclass(frozen=True)
class Member:
    path: str
    action: str        # "keep" | "merge-format" | "trash"
    reason: str


@dataclass(frozen=True)
class DupGroup:
    work_key: str
    members: tuple[Member, ...]


def _keeper_sort_key(f: FileInfo):
    # Prefer: has metadata, then larger, then a "clean" (non-redownload) name, then path (stable).
    return (not f.has_metadata, -f.size, bool(_REDOWNLOAD_RE.search(f.path)), f.path)


def plan_dedup(files: list[FileInfo]) -> list[DupGroup]:
    by_work: dict[str, list[FileInfo]] = {}
    for f in files:
        by_work.setdefault(f.work_key, []).append(f)

    groups: list[DupGroup] = []
    for work_key, work_files in by_work.items():
        members: list[Member] = []
        # Within a work, split by format. One canonical per work; same-format extras collapse.
        by_format: dict[str, list[FileInfo]] = {}
        for f in work_files:
            by_format.setdefault(f.format, []).append(f)

        # The overall canonical format-representative is the best file across all formats.
        overall_keeper = sorted(work_files, key=_keeper_sort_key)[0]

        for fmt, fmt_files in by_format.items():
            fmt_keeper = sorted(fmt_files, key=_keeper_sort_key)[0]
            for f in fmt_files:
                if f.path == fmt_keeper.path:
                    if f.path == overall_keeper.path:
                        members.append(Member(f.path, "keep", "canonical copy"))
                    else:
                        members.append(Member(f.path, "merge-format",
                                              f"alternate format ({fmt}) of the same work"))
                else:
                    members.append(Member(f.path, "trash",
                                          f"redundant {fmt} copy; keeper={fmt_keeper.path}"))
        groups.append(DupGroup(work_key, tuple(sorted(members, key=lambda m: m.path))))
    return sorted(groups, key=lambda g: g.work_key)
```

- [ ] **Step 4: Run — confirm 4 passed.**

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/dedup.py tests/test_book_filer_dedup.py
git commit -m "feat(EB-355): add duplicate planning (merge formats, keep best of exact dups)"
```

---

### Task 3: Fragment attribution (review-only)

**Files:**
- Create: `tools/book_filer/fragments.py`
- Test: `tests/test_book_filer_fragments.py`

- [ ] **Step 1: Write the failing test `tests/test_book_filer_fragments.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.fragments import detect_fragment_sets


def test_numbered_suffix_set_is_flagged_for_review():
    paths = [f"Fourth_Step_Guided_Workbook-{i}.pdf" for i in range(1, 8)]
    sets = detect_fragment_sets(paths)
    assert len(sets) == 1
    assert sets[0].disposition == "review"
    assert set(sets[0].members) == set(paths)


def test_exploded_epub_debris_is_flagged_for_review():
    paths = ["book/ch1.xhtml", "book/ch2.xhtml", "book/content.opf", "book/toc.ncx", "book/style.css"]
    sets = detect_fragment_sets(paths)
    assert len(sets) == 1
    assert sets[0].disposition == "review"


def test_normal_distinct_books_are_not_fragment_sets():
    paths = ["Author - Title One (2001).epub", "Author - Title Two (2002).epub"]
    assert detect_fragment_sets(paths) == []


def test_never_auto_trashes():
    paths = [f"x-{i}.pdf" for i in range(1, 5)]
    # Policy: fragments are ALWAYS routed to review, never to trash, in the migration.
    assert all(s.disposition == "review" for s in detect_fragment_sets(paths))
```

- [ ] **Step 2: Run — confirm fail.**

- [ ] **Step 3: Implement `tools/book_filer/fragments.py`**

```python
"""Fragment-set detection (spec §6.3). Policy: ALWAYS route to review, never auto-trash."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath

# stem ending in -N, (N), or _NN  (N >= 1)
_NUMBERED_RE = re.compile(r"^(?P<stem>.+?)[ _-]\(?(?P<num>\d{1,3})\)?$")
_EPUB_DEBRIS = {".xhtml", ".opf", ".ncx", ".css"}


@dataclass(frozen=True)
class FragmentVerdict:
    members: tuple[str, ...]
    disposition: str   # always "review"
    reason: str


def detect_fragment_sets(paths: list[str]) -> list[FragmentVerdict]:
    verdicts: list[FragmentVerdict] = []
    used: set[str] = set()

    # 1. Exploded-EPUB debris: a directory containing OPF/NCX/XHTML/CSS together.
    by_dir: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        by_dir[str(PurePosixPath(p).parent)].append(p)
    for _dir, members in by_dir.items():
        exts = {PurePosixPath(m).suffix.lower() for m in members}
        if len(_EPUB_DEBRIS & exts) >= 2:
            verdicts.append(FragmentVerdict(tuple(sorted(members)), "review",
                                            "exploded-EPUB debris (OPF/NCX/XHTML/CSS in one folder)"))
            used.update(members)

    # 2. Numbered-suffix sets: >= 3 files sharing a stem with consecutive-ish numbers.
    by_stem: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        if p in used:
            continue
        name = PurePosixPath(p).stem
        m = _NUMBERED_RE.match(name)
        if m:
            by_stem[m.group("stem")].append(p)
    for stem, members in by_stem.items():
        if len(members) >= 3:
            verdicts.append(FragmentVerdict(tuple(sorted(members)), "review",
                                            f"numbered fragment set (stem '{stem}', {len(members)} parts)"))

    return verdicts
```

- [ ] **Step 4: Run — confirm 4 passed.**

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/fragments.py tests/test_book_filer_fragments.py
git commit -m "feat(EB-355): add fragment-set detection (review-only, never auto-trash)"
```

---

### Task 4: Calibration verdict (determinism + zero wrong-shelf + sign-off)

**Files:**
- Create: `tools/book_filer/calibration.py`
- Test: `tests/test_book_filer_calibration.py`

- [ ] **Step 1: Write the failing test `tests/test_book_filer_calibration.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.calibration import SpotCheck, evaluate_calibration

_OK_SAMPLE = [SpotCheck(path=f"f{i}", disposition="shelf", correct=True) for i in range(20)]


def test_green_requires_determinism_zero_wrongshelf_and_signoff():
    v = evaluate_calibration("PROJ", "PROJ", _OK_SAMPLE, signed_off_by="joe", min_spot_check=20)
    assert v.green is True
    assert v.deterministic and v.wrong_shelf_count == 0


def test_non_deterministic_is_red():
    v = evaluate_calibration("PROJ_A", "PROJ_B", _OK_SAMPLE, signed_off_by="joe", min_spot_check=20)
    assert v.green is False and v.deterministic is False


def test_any_wrong_shelf_is_red():
    sample = _OK_SAMPLE[:-1] + [SpotCheck(path="bad", disposition="shelf", correct=False)]
    v = evaluate_calibration("PROJ", "PROJ", sample, signed_off_by="joe", min_spot_check=20)
    assert v.green is False and v.wrong_shelf_count == 1


def test_wrong_review_item_does_not_fail_green():
    # A 'review' item judged incorrect is NOT a wrong-shelf; review is always safe.
    sample = _OK_SAMPLE + [SpotCheck(path="r", disposition="review", correct=False)]
    v = evaluate_calibration("PROJ", "PROJ", sample, signed_off_by="joe", min_spot_check=20)
    assert v.green is True


def test_missing_signoff_or_small_sample_is_red():
    assert evaluate_calibration("P", "P", _OK_SAMPLE, signed_off_by=None, min_spot_check=20).green is False
    assert evaluate_calibration("P", "P", _OK_SAMPLE[:5], signed_off_by="joe", min_spot_check=20).green is False
```

- [ ] **Step 2: Run — confirm fail.**

- [ ] **Step 3: Implement `tools/book_filer/calibration.py`**

```python
"""Calibration verdict (spec §6.2 + Plan-4 brainstorm decision).

GREEN requires ALL of: byte-identical determinism across two runs; ZERO files
auto-shelved into the wrong section in the spot-check; a human sign-off; and a
spot-check at least `min_spot_check` large. A 'review' disposition judged wrong
is NOT a failure — routing to review is always safe.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpotCheck:
    path: str
    disposition: str   # "shelf" | "review" | "non_library"
    correct: bool      # human judgement of whether the disposition was right


@dataclass(frozen=True)
class CalibrationVerdict:
    deterministic: bool
    wrong_shelf_count: int
    spot_check_size: int
    signed_off_by: str | None
    green: bool
    reason: str


def evaluate_calibration(
    projection_a: str,
    projection_b: str,
    spot_check: list[SpotCheck],
    signed_off_by: str | None,
    min_spot_check: int = 20,
) -> CalibrationVerdict:
    deterministic = projection_a == projection_b
    wrong_shelf = sum(1 for c in spot_check if c.disposition == "shelf" and not c.correct)
    big_enough = len(spot_check) >= min_spot_check
    signed = signed_off_by is not None

    green = deterministic and wrong_shelf == 0 and big_enough and signed
    if green:
        reason = "GREEN: deterministic, zero wrong-shelf, signed off."
    else:
        fails = []
        if not deterministic:
            fails.append("non-deterministic")
        if wrong_shelf:
            fails.append(f"{wrong_shelf} wrong-shelf")
        if not big_enough:
            fails.append(f"spot-check {len(spot_check)} < {min_spot_check}")
        if not signed:
            fails.append("not signed off")
        reason = "RED: " + ", ".join(fails)

    return CalibrationVerdict(deterministic, wrong_shelf, len(spot_check), signed_off_by, green, reason)
```

- [ ] **Step 4: Run — confirm 5 passed.**

- [ ] **Step 5: Commit**

```bash
git add tools/book_filer/calibration.py tests/test_book_filer_calibration.py
git commit -m "feat(EB-355): add calibration verdict (determinism + zero wrong-shelf gate)"
```

---

### Task 5: Regression guard

**Files:** none (verification only)

- [ ] **Step 1: Run the whole book_filer suite.**

Run: `python -m pytest tests/ -k book_filer -q`
Expected: PASS (Plan 1: 26 + Plans 2–3 once merged + Plan 4: 17 new = manifest 4 + dedup 4 + fragments 4 + calibration 5). Report the count.

- [ ] **Step 2: If anything pre-existing fails, STOP and diagnose.** This plan is additive (four new modules + four new test files); it mutates no existing file and touches no `F:\Books` path.

---

## Self-Review

**Spec coverage (this plan's slice):**
- §6.1 manifest schema + CSV/JSON(+MD) writer → Task 1 ✅
- §6.2 deterministic projection (sort + drop `calibre_id`) → Task 1 ✅; undo generator → Task 1 ✅
- §6.4 merge-formats dedup + keep-best exact → Task 2 ✅ (brainstorm decision)
- §6.3 fragment attribution, review-only → Task 3 ✅ (brainstorm decision)
- Calibration gate: determinism + zero wrong-shelf + sign-off → Task 4 ✅ (brainstorm decision)

**Explicitly NOT here (Plan 5 — the actuator, gated):** `Invoke-BookFileGuarded.ps1` (the `--apply`-replays-approved-manifest **in-place atomic-rename mover** with reparse/collision TOCTOU re-check and **write-ahead journaling**, fail-safe per item); the migration driver (Phase 0 **external-mirror backup verified by count + sampled sha256**, batched apply); the apply-gate preconditions enforcement (backup + green calibration + approval token + ADR-0045 grant). **No `F:\Books` move/rename/delete exists in code until Plan 5, and even then only behind those gates.** (Per ADR-0045: in-place move, write-ahead journal, **no Calibre import**.)

**Placeholder scan:** none — complete code + runnable tests; `stamp` and IDs are injected for reproducibility.

**Type consistency:** `ManifestRow` field set matches spec §6.1 and is referenced consistently; `FileInfo`/`Member`/`DupGroup`, `FragmentVerdict`, and `SpotCheck`/`CalibrationVerdict` are each defined once and used consistently in their tests.

---

## Revised plan sequence (EB-355 split — now 6 plans)
1. **Plan 1 — Foundation** (merged): config, path-safety, reparse guard, scaffolding.
2. **Plan 2 — Classifier + Taxonomy** (merged): `books-taxonomy.json`, classifier.
3. **Plan 3 — Metadata + Identity** (on master): embedded extraction, `planned_calibre_key`.
4. **Plan 4 — Migration Core (Decide + Record)** (this plan): manifest, dedup, fragments, calibration. **No filesystem mutation.**
5. **Plan 5 — Guarded Filer + 9-Phase Migration Driver (the Actuator):** `Invoke-BookFileGuarded.ps1` + the driver, fenced behind the backup/calibration/approval/ADR-0045 gates. **First and only code that touches `F:\Books`.**
6. **Plan 6 — Reconciliation + Rewire:** Calibre↔shelf reconciliation job + the 5-file automation rewire (built on EB-356's *committed* BookFinder) + the conversion-output completion hook.
