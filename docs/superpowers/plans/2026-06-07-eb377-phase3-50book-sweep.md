# EB-377 Phase-3 50-Book Regression & Pattern Sweep — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run ~50 books through the full PDF→KFX pipeline with free local-Qwen VQA, confirm the running-header-bleed fixes hold corpus-wide, and produce a ranked findings document that drives the next round of fix tickets.

**Architecture:** `tools/batch_qa.py run` is the orchestrator (extraction → KFX → local VQA → clustering). Phase 1 makes four small, TDD'd harness changes on a feature branch and merges them. Phase 2 runs fail-fast preflight gates. Phase 3 runs the batch from the **main working tree**, scans header-bleed against provenance-scoped intermediates, and synthesizes findings.

**Tech Stack:** Python 3.12 (`py -3.12`), PowerShell 7 (`pwsh`), pytest, Calibre (`Convert-ToKindle`), local Qwen3-VL via OpenAI-compatible endpoint at `http://192.168.1.33:8080/v1`.

**Spec:** `docs/superpowers/specs/2026-06-07-eb-phase3-50book-regression-sweep-design.md` (EB-377).

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `tools/batch_qa.py` | Modify (`run_visual_qa_for_book`, ~line 718) | Pin calibrated, fallback-off, serialized local VQA |
| `tools/select_batch_corpus.py` | Create | Build the reviewable 11/39 manifest (seeded, stratified) and stage the 50 PDFs |
| `tools/build_batch_provenance.py` | Create | Join run artifacts by KFX basename; run provenance-scoped header-bleed scan; emit provenance index |
| `tools/synthesize_batch_findings.py` | Create | Merge `batch_qa` clusters/observations + welds + VQA + coverage → findings markdown |
| `tests/test_eb377_vqa_policy.py` | Create | Assert VQA argv/timeout/semaphore |
| `tests/test_eb377_select_corpus.py` | Create | Assert filtering, seed reproducibility, counts, strata |
| `tests/test_eb377_provenance.py` | Create | Assert basename join, SHA-256, coverage gaps, header-bleed scoping |
| `tests/test_eb377_synthesis.py` | Create | Assert findings merge + separation of measurement artifacts |

**Branch:** `feat/EB-377-phase3-sweep-harness`. Phase 1 lands via PR. Phases 2–3 run on `master` from the main tree (never a worktree — the CLAUDE.md junction hazard applies to any run touching `archive/`, `output/`, `processing/`).

**Test command (project standard):** `py -3.12 -m pytest <path> -v`

---

## Phase 1 — Harness code changes (feature branch, TDD, PR)

### Task 1: Pin calibrated, fallback-off, serialized local VQA

**Files:**
- Modify: `tools/batch_qa.py` (`run_visual_qa_for_book`, ~lines 718-745; add a module-level semaphore + `import threading` if absent)
- Test: `tests/test_eb377_vqa_policy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eb377_vqa_policy.py
import sys, threading
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import batch_qa  # noqa: E402


def test_vqa_argv_is_calibrated_and_fallback_off(tmp_path):
    kfx = tmp_path / "book.kfx"
    kfx.write_bytes(b"x")
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["timeout"] = kwargs.get("timeout")
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch.object(batch_qa.subprocess, "run", side_effect=fake_run):
        batch_qa.run_visual_qa_for_book(str(kfx))

    argv = captured["argv"]
    assert "--full" in argv
    assert argv[argv.index("--provider") + 1] == "local"
    assert argv[argv.index("--fallback-enabled") + 1] == "false"
    assert captured["timeout"] == 900


def test_vqa_semaphore_is_single_permit():
    assert isinstance(batch_qa._VQA_SEMAPHORE, threading.Semaphore)
    # CPython Semaphore exposes its counter as _value
    assert batch_qa._VQA_SEMAPHORE._value == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest tests/test_eb377_vqa_policy.py -v`
Expected: FAIL — `AttributeError: module 'batch_qa' has no attribute '_VQA_SEMAPHORE'` and argv assertions fail (current call has no `--full`/`--provider`/`--fallback-enabled`, timeout 300).

- [ ] **Step 3: Add the import + semaphore (top of `batch_qa.py`, with the other imports)**

```python
import threading

# EB-377: serialize local-Qwen VQA so --parallel keeps extraction/KFX
# concurrent while only one VQA request hits the R9700 at a time.
_VQA_SEMAPHORE = threading.Semaphore(1)
```

(If `import threading` already exists, do not duplicate it — only add the semaphore.)

- [ ] **Step 4: Rewrite the body of `run_visual_qa_for_book`**

Replace the existing `subprocess.run([... "--verbose"], ... timeout=300)` block with:

```python
def run_visual_qa_for_book(kfx_path):
    """Run visual QA scoring on a KFX file. Returns (score, category_scores, cost, duration).

    EB-377: calibrated full VQA (20pg/150dpi), local provider, Claude fallback
    OFF (free run), serialized via _VQA_SEMAPHORE so concurrent batch workers do
    not contend on the single R9700 GPU.
    """
    qa_script = SCRIPT_DIR / "visual_qa.py"
    if not qa_script.exists():
        return None, {}, 0, 0

    argv = [
        sys.executable, str(qa_script),
        "--input", str(kfx_path),
        "--verbose",
        "--full",                       # visual_qa.py: 20 pages @ 150 DPI
        "--provider", "local",
        "--fallback-enabled", "false",  # pass EXACTLY 'false' — keeps run $0
    ]

    t0 = time.time()
    try:
        with _VQA_SEMAPHORE:            # only one VQA subprocess at a time
            result = subprocess.run(
                argv, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=900,  # 20pg two-pass
            )
        duration = time.time() - t0

        report_path = str(kfx_path).rsplit('.', 1)[0] + '_visual_qa_report.json'
        if os.path.isfile(report_path):
            with open(report_path, 'r', encoding='utf-8') as f:
                report = json.load(f)
            score = report.get('overall_score', report.get('score'))
            categories = report.get('category_scores', {})
            cost = report.get('cost_usd', report.get('api_cost_usd', 0))
            return score, categories, cost, duration
        return None, {}, 0, duration
    except (subprocess.TimeoutExpired, Exception):
        return None, {}, 0, time.time() - t0
```

- [ ] **Step 5: Run test to verify it passes**

Run: `py -3.12 -m pytest tests/test_eb377_vqa_policy.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Regression — confirm no syntax/import breakage**

Run: `py -3.12 -c "import sys, pathlib; sys.path.insert(0, 'tools'); import batch_qa; print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add tools/batch_qa.py tests/test_eb377_vqa_policy.py
git commit -m "feat(EB-377): calibrated, fallback-off, serialized local VQA in batch_qa"
```

---

### Task 2: `select_batch_corpus.py` — seeded, stratified 11/39 manifest + staging

**Files:**
- Create: `tools/select_batch_corpus.py`
- Test: `tests/test_eb377_select_corpus.py`

**Interface (contract for later tasks):**
- `select_corpus(archive_dir, fresh_dir, n_fresh=39, seed=377) -> dict` returns
  `{"seed": int, "ticket": "EB-377", "anchors": [path,...], "fresh": [{"path","size_mb","stratum"}...], "strata_counts": {stratum: count}}`.
- `ANCHOR_PATTERNS: list[str]` — 11 glob patterns, each must resolve to exactly one file.
- `JUNK_RE: re.Pattern`, `HEADER_PRONE_RE: re.Pattern`.
- CLI: `python tools/select_batch_corpus.py --archive archive --fresh F:\books --out logs/batch-selection-2026-06-07.json [--stage processing/batch-2026-06-07]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eb377_select_corpus.py
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import select_batch_corpus as sbc  # noqa: E402


def _touch(p: Path, mb=1.0):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"0" * int(mb * 1024 * 1024))


def _fixture(tmp_path):
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    # 11 anchors (filenames chosen to match ANCHOR_PATTERNS)
    for name in [
        "On First Principles - Origen.pdf", "Pilgrim People.pdf",
        "The Oil Kings - Cooper.pdf", "Mexico's Illicit Drug Networks.pdf",
        "The Return of the Gods - Cahn.pdf", "Python in easy steps.pdf",
        "Atomic Habits - Clear.pdf", "Decline of the West Vol 1 and 2.pdf",
        "Dionysius the Areopagite.pdf", "Reading Genesis After Darwin.pdf",
        "Fate of Empires - Glubb.pdf",
    ]:
        _touch(arch / name)
    # fresh pool: 60 good books + junk + a dupe
    hist = fresh / "History"
    for i in range(30):
        _touch(hist / f"history_book_{i}.pdf", mb=2.0 + i * 0.1)
    for i in range(30):
        _touch(fresh / f"misc_book_{i}.pdf", mb=1.0)
    _touch(fresh / "2024_tax_return.pdf")          # junk
    _touch(fresh / "Joe_Fowler_resume.pdf")        # junk
    _touch(fresh / "history_book_0 (1).pdf")       # dupe
    _touch(fresh / "audiobook.mp3")                # non-pdf
    return arch, fresh


def test_counts_and_no_junk(tmp_path):
    arch, fresh = _fixture(tmp_path)
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    assert len(result["anchors"]) == 11
    assert len(result["fresh"]) == 39
    picked = [Path(f["path"]).name for f in result["fresh"]]
    assert not any("tax_return" in n or "resume" in n for n in picked)
    assert not any(n.endswith(" (1).pdf") for n in picked)
    assert not any(n.endswith(".mp3") for n in picked)
    assert result["strata_counts"]  # non-empty


def test_seed_is_reproducible(tmp_path):
    arch, fresh = _fixture(tmp_path)
    a = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    b = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    assert [f["path"] for f in a["fresh"]] == [f["path"] for f in b["fresh"]]


def test_each_anchor_pattern_resolves_once(tmp_path):
    arch, _ = _fixture(tmp_path)
    for pat in sbc.ANCHOR_PATTERNS:
        matches = list(Path(arch).glob(pat))
        assert len(matches) == 1, f"{pat} -> {matches}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest tests/test_eb377_select_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'select_batch_corpus'`.

- [ ] **Step 3: Implement `tools/select_batch_corpus.py`**

```python
#!/usr/bin/env python3
"""EB-377: build the reviewable 11/39 corpus manifest and stage the 50 PDFs.

Anchors come from archive/ (regression confirmation); fresh picks come from a
large pool (default F:\\books), junk/dupe filtered, stratified by size bucket x
subject folder, seeded for reproducibility, with a soft bias toward header-prone
genres. Writes a manifest JSON; optionally copies the 50 PDFs into a staging dir.
"""
from __future__ import annotations
import argparse
import json
import logging
import random
import re
import shutil
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("select_batch_corpus")

# 11 anchors — each pattern MUST resolve to exactly one file in archive/.
ANCHOR_PATTERNS = [
    "*First Principles*.pdf",
    "*Pilgrim*People*.pdf",
    "*Oil*Kings*.pdf",
    "*Mexico*Illicit*.pdf",
    "*Return*Gods*.pdf",
    "*Python*easy*steps*.pdf",
    "*Atomic*Habits*.pdf",
    "*Decline*West*.pdf",
    "*Dionysius*.pdf",
    "*Genesis*Darwin*.pdf",
    "*Fate*Empires*.pdf",
]

JUNK_RE = re.compile(
    r"(tax[_ ]?return|resume|cv|boarding[_ ]?pass|insurance|w-?2|1099|"
    r"invoice|receipt|statement)", re.IGNORECASE,
)
DUPE_RE = re.compile(r"\(\d+\)\.pdf$", re.IGNORECASE)
HEADER_PRONE_RE = re.compile(
    r"(history|philosoph|theolog|classic|academ|ancient|empire|"
    r"princip|gods|religion|patristic)", re.IGNORECASE,
)

_SIZE_BUCKETS = [(0, 5), (5, 15), (15, 40), (40, 10_000)]  # MB


def _size_bucket(mb: float) -> str:
    for lo, hi in _SIZE_BUCKETS:
        if lo <= mb < hi:
            return f"{lo}-{hi}MB"
    return "huge"


def _resolve_anchors(archive_dir: Path) -> list[str]:
    anchors = []
    for pat in ANCHOR_PATTERNS:
        matches = sorted(archive_dir.glob(pat))
        if len(matches) != 1:
            raise SystemExit(
                f"Anchor pattern {pat!r} resolved to {len(matches)} files: "
                f"{[m.name for m in matches]} — fix the pattern or archive/."
            )
        anchors.append(str(matches[0]))
    return anchors


def select_corpus(archive_dir: str, fresh_dir: str, n_fresh: int = 39,
                  seed: int = 377) -> dict:
    archive_dir = Path(archive_dir)
    fresh_dir = Path(fresh_dir)
    anchors = _resolve_anchors(archive_dir)
    anchor_stems = {Path(a).stem.lower() for a in anchors}

    candidates = []
    for p in fresh_dir.rglob("*.pdf"):
        name = p.name
        if JUNK_RE.search(name) or DUPE_RE.search(name):
            continue
        if p.stem.lower() in anchor_stems:
            continue
        mb = p.stat().st_size / (1024 * 1024)
        subject = p.parent.name if p.parent != fresh_dir else "_root"
        stratum = f"{subject}|{_size_bucket(mb)}"
        weight = 2.0 if HEADER_PRONE_RE.search(str(p)) else 1.0
        candidates.append(
            {"path": str(p), "size_mb": round(mb, 2),
             "stratum": stratum, "_weight": weight}
        )

    rng = random.Random(seed)
    # Deterministic weighted sample without replacement: sort by an Efraimidis-
    # Spirakis key (u**(1/weight)), descending, then take the top n_fresh.
    candidates.sort(key=lambda c: c["path"])  # stable base order before keying
    for c in candidates:
        u = rng.random()
        c["_key"] = u ** (1.0 / c["_weight"])
    candidates.sort(key=lambda c: c["_key"], reverse=True)
    fresh = candidates[:n_fresh]

    strata_counts: dict[str, int] = {}
    for c in fresh:
        strata_counts[c["stratum"]] = strata_counts.get(c["stratum"], 0) + 1
        del c["_weight"], c["_key"]

    if len(fresh) < n_fresh:
        log.warning("Only %d fresh candidates after filtering (< %d requested)",
                    len(fresh), n_fresh)

    return {"seed": seed, "ticket": "EB-377",
            "anchors": anchors, "fresh": fresh, "strata_counts": strata_counts}


def stage(manifest: dict, staging_dir: str) -> None:
    staging = Path(staging_dir)
    staging.mkdir(parents=True, exist_ok=True)
    paths = list(manifest["anchors"]) + [f["path"] for f in manifest["fresh"]]
    for src in paths:
        src_p = Path(src)
        dest = staging / src_p.name
        if dest.exists() and dest.stat().st_size == src_p.stat().st_size:
            continue
        shutil.copy2(src_p, dest)
        log.info("staged %s", src_p.name)
    log.info("Staged %d PDFs into %s", len(paths), staging)


def main(argv=None):
    ap = argparse.ArgumentParser(description="EB-377 corpus selection + staging")
    ap.add_argument("--archive", default="archive")
    ap.add_argument("--fresh", default=r"F:\books")
    ap.add_argument("--n-fresh", type=int, default=39)
    ap.add_argument("--seed", type=int, default=377)
    ap.add_argument("--out", default="logs/batch-selection-2026-06-07.json")
    ap.add_argument("--stage", default=None,
                    help="If set, copy the 50 PDFs into this directory.")
    args = ap.parse_args(argv)

    manifest = select_corpus(args.archive, args.fresh, args.n_fresh, args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("Wrote manifest: %s (%d anchors + %d fresh)", out,
             len(manifest["anchors"]), len(manifest["fresh"]))
    log.info("Strata: %s", json.dumps(manifest["strata_counts"]))

    if args.stage:
        stage(manifest, args.stage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.12 -m pytest tests/test_eb377_select_corpus.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/select_batch_corpus.py tests/test_eb377_select_corpus.py
git commit -m "feat(EB-377): seeded, stratified 11/39 corpus selection + staging"
```

---

### Task 3: `build_batch_provenance.py` — artifact join + provenance-scoped header-bleed scan

**Files:**
- Create: `tools/build_batch_provenance.py`
- Test: `tests/test_eb377_provenance.py`

**Interface:**
- `build_provenance(manifest, kfx_dir, header_out_dir) -> dict` returns
  `{"books": [ {source, sha256, staged, kfx, intermediate_html, vqa_report, header_report, weld_total, coverage: {...bools}, status} ...], "summary": {...}}`.
- A book whose intermediate HTML is missing gets `weld_total=None`, `coverage.intermediate_html=False`, `status="coverage_gap"`. **Only the manifest's basenames are scanned — never a `*_kindle.html` glob.**

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eb377_provenance.py
import sys, json, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_batch_provenance as prov  # noqa: E402

WELDED = (
    '<html><body>'
    '<p id="page_5">viii ON FIRST PRINCIPLES and the argument runs on here '
    'with more body text following the welded header token</p>'
    '<p id="page_6">viii ON FIRST PRINCIPLES and the argument runs on here '
    'with more body text following the welded header token</p>'
    '<p id="page_7">viii ON FIRST PRINCIPLES and the argument runs on here '
    'with more body text following the welded header token</p>'
    '<p id="page_8">viii ON FIRST PRINCIPLES and the argument runs on here '
    'with more body text following the welded header token</p>'
    '<p id="page_9">viii ON FIRST PRINCIPLES and the argument runs on here '
    'with more body text following the welded header token</p>'
    '</body></html>'
)


def _manifest(tmp_path):
    src = tmp_path / "src" / "On First Principles.pdf"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"pdf-bytes")
    staged = tmp_path / "stage" / "On First Principles.pdf"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"pdf-bytes")
    return {"anchors": [str(src)], "fresh": [],
            "_staged_dir": str(tmp_path / "stage")}


def test_join_and_sha_and_weld(tmp_path):
    manifest = _manifest(tmp_path)
    kfx_dir = tmp_path / "kindle"
    inter = kfx_dir / ".intermediates"
    inter.mkdir(parents=True)
    (kfx_dir / "On First Principles.kfx").write_bytes(b"kfx")
    (inter / "On First Principles_kindle.html").write_text(WELDED, encoding="utf-8")
    (kfx_dir / "On First Principles_visual_qa_report.json").write_text(
        json.dumps({"overall_score": 88}), encoding="utf-8")
    header_out = tmp_path / "hb"

    result = prov.build_provenance(manifest, str(kfx_dir), str(header_out))
    book = result["books"][0]
    assert book["sha256"] == hashlib.sha256(b"pdf-bytes").hexdigest()
    assert book["weld_total"] >= 1            # welded header detected
    assert book["coverage"]["kfx"] is True
    assert book["status"] == "complete"


def test_missing_intermediate_is_coverage_gap(tmp_path):
    manifest = _manifest(tmp_path)
    kfx_dir = tmp_path / "kindle"
    kfx_dir.mkdir()
    (kfx_dir / "On First Principles.kfx").write_bytes(b"kfx")  # KFX but no html
    result = prov.build_provenance(manifest, str(kfx_dir), str(tmp_path / "hb"))
    book = result["books"][0]
    assert book["weld_total"] is None
    assert book["coverage"]["intermediate_html"] is False
    assert book["status"] == "coverage_gap"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest tests/test_eb377_provenance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_batch_provenance'`.

- [ ] **Step 3: Implement `tools/build_batch_provenance.py`**

```python
#!/usr/bin/env python3
"""EB-377: build the per-book artifact provenance index and run the
provenance-SCOPED header-bleed scan (only the manifest's basenames — never a
bare *_kindle.html glob, which would pull stale intermediates into EB-377)."""
from __future__ import annotations
import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_header_bleed as chb  # detect(html, params) -> BookResult

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("build_batch_provenance")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _book_record(source: str, staged_dir: Path, kfx_dir: Path,
                 header_out: Path) -> dict:
    src = Path(source)
    stem = src.stem
    staged = staged_dir / src.name
    kfx = kfx_dir / f"{stem}.kfx"
    inter = kfx_dir / ".intermediates" / f"{stem}_kindle.html"
    vqa = kfx_dir / f"{stem}_visual_qa_report.json"
    header_report = header_out / f"{stem}.json"

    coverage = {
        "staged": staged.exists(),
        "kfx": kfx.exists() and kfx.stat().st_size > 0,
        "intermediate_html": inter.exists(),
        "vqa_report": vqa.exists(),
    }

    weld_total = None
    if coverage["intermediate_html"]:
        result = chb.detect(inter.read_text(encoding="utf-8", errors="replace"))
        weld_total = result.weld_total
        header_out.mkdir(parents=True, exist_ok=True)
        header_report.write_text(
            json.dumps({"stem": stem, "weld_total": weld_total,
                        "findings": [f.__dict__ for f in result.findings]},
                       indent=2, default=str),
            encoding="utf-8",
        )

    if not coverage["kfx"]:
        status = "kfx_failed"
    elif not coverage["intermediate_html"]:
        status = "coverage_gap"
    else:
        status = "complete"

    return {
        "source": str(src), "sha256": _sha256(src) if src.exists() else None,
        "staged": str(staged), "kfx": str(kfx), "intermediate_html": str(inter),
        "vqa_report": str(vqa), "header_report": str(header_report),
        "weld_total": weld_total, "coverage": coverage, "status": status,
    }


def build_provenance(manifest: dict, kfx_dir: str, header_out_dir: str) -> dict:
    staged_dir = Path(manifest.get("_staged_dir", "."))
    kfx_dir = Path(kfx_dir)
    header_out = Path(header_out_dir)
    sources = list(manifest.get("anchors", [])) + \
        [f["path"] for f in manifest.get("fresh", [])]

    books = [_book_record(s, staged_dir, kfx_dir, header_out) for s in sources]
    flagged = [b for b in books if b["weld_total"]]
    summary = {
        "total": len(books),
        "complete": sum(b["status"] == "complete" for b in books),
        "coverage_gap": sum(b["status"] == "coverage_gap" for b in books),
        "kfx_failed": sum(b["status"] == "kfx_failed" for b in books),
        "weld_books": len(flagged),
        "weld_total_sum": sum(b["weld_total"] or 0 for b in books),
    }
    return {"ticket": "EB-377", "books": books, "summary": summary}


def main(argv=None):
    ap = argparse.ArgumentParser(description="EB-377 provenance + header-bleed")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--staged-dir", required=True)
    ap.add_argument("--kfx-dir", default=r"output\kindle")
    ap.add_argument("--header-out", default=r"data\batch_reports\header_bleed")
    ap.add_argument("--out", default=r"data\batch_reports\EB-377-provenance.json")
    args = ap.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    manifest["_staged_dir"] = args.staged_dir
    index = build_provenance(manifest, args.kfx_dir, args.header_out)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(index, indent=2), encoding="utf-8")
    log.info("Provenance: %s", json.dumps(index["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

> **Executor note:** verify `check_header_bleed.detect` returns an object with `.weld_total` and `.findings` (it does — `tools/check_header_bleed.py:181`, dataclass `BookResult`). If `detect` requires a `DetectorParams` argument in the installed version, pass `chb.detect(html, chb.DetectorParams())`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.12 -m pytest tests/test_eb377_provenance.py -v`
Expected: PASS (2 passed). If the welded-detection assertion fails, read `check_header_bleed.detect`'s real signature and adjust the call (note above) — do not weaken the assertion.

- [ ] **Step 5: Commit**

```bash
git add tools/build_batch_provenance.py tests/test_eb377_provenance.py
git commit -m "feat(EB-377): artifact provenance index + provenance-scoped header-bleed scan"
```

---

### Task 4: `synthesize_batch_findings.py` — merge into the findings document

**Files:**
- Create: `tools/synthesize_batch_findings.py`
- Test: `tests/test_eb377_synthesis.py`

**Interface:**
- `synthesize(provenance, batch_qa_report, determinism) -> str` returns markdown.
- Sections: header-bleed verdict (welds vs. clean anchors), new patterns (from `batch_qa` `failure_clusters` + `observations`, ranked by `count × severity`), VQA summary, **a separate "Measurement artifacts" section** (coverage gaps, non-deterministic VQA flag), and a prioritized fix list.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eb377_synthesis.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import synthesize_batch_findings as syn  # noqa: E402


def test_synthesis_sections_and_artifact_separation():
    provenance = {
        "summary": {"total": 50, "complete": 47, "coverage_gap": 1,
                    "kfx_failed": 2, "weld_books": 0, "weld_total_sum": 0},
        "books": [{"source": "On First Principles.pdf", "weld_total": 0,
                   "status": "complete"}],
    }
    batch_qa_report = {
        "failure_clusters": [
            {"pattern_id": "FOOTNOTES_UNLINKED", "severity": "medium", "count": 9},
            {"pattern_id": "VQA_SCORE_LOW", "severity": "high", "count": 3},
        ],
        "observations": ["VQA scores correlate with ligature_splits"],
    }
    determinism = {"reproducible": False, "max_delta": 4}

    md = syn.synthesize(provenance, batch_qa_report, determinism)
    assert "Header-bleed verdict" in md
    assert "New patterns" in md
    assert "Measurement artifacts" in md
    # high-severity cluster ranks above medium even with lower count
    assert md.index("VQA_SCORE_LOW") < md.index("FOOTNOTES_UNLINKED")
    # non-deterministic VQA is an artifact, not a finding
    assert "non-deterministic" in md.lower()
    assert "coverage_gap" in md or "coverage gap" in md.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest tests/test_eb377_synthesis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'synthesize_batch_findings'`.

- [ ] **Step 3: Implement `tools/synthesize_batch_findings.py`**

```python
#!/usr/bin/env python3
"""EB-377: merge provenance + batch_qa clusters/observations + determinism into
a findings document. Measurement artifacts are reported SEPARATELY from real
findings (Calibration-Sessions discipline)."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

_SEV_RANK = {"high": 3, "medium": 2, "low": 1}


def synthesize(provenance: dict, batch_qa_report: dict, determinism: dict) -> str:
    s = provenance["summary"]
    clusters = sorted(
        batch_qa_report.get("failure_clusters", []),
        key=lambda c: (_SEV_RANK.get(c.get("severity", "low"), 0),
                       c.get("count", 0)),
        reverse=True,
    )
    lines = ["# EB-377 Phase-3 Sweep — Findings", ""]

    lines += ["## Header-bleed verdict", ""]
    if s["weld_total_sum"] == 0:
        lines.append("All scanned books show **0 welds**. The header-bleed "
                     "fixes (EB-367/370/372/374) hold corpus-wide.")
    else:
        lines.append(f"**{s['weld_total_sum']} welds across {s['weld_books']} "
                     f"books.** Spot-check required before escalation.")
    lines.append("")

    lines += ["## New patterns (ranked: severity x count)", ""]
    if clusters:
        lines.append("| Pattern | Severity | Count |")
        lines.append("|---|---|---|")
        for c in clusters:
            lines.append(f"| {c['pattern_id']} | {c.get('severity','?')} | "
                         f"{c.get('count','?')} |")
    else:
        lines.append("No failure clusters detected.")
    lines.append("")
    for obs in batch_qa_report.get("observations", []):
        lines.append(f"- _Observation:_ {obs}")
    lines.append("")

    lines += ["## Prioritized fix list", ""]
    for i, c in enumerate(clusters, 1):
        lines.append(f"{i}. **{c['pattern_id']}** ({c.get('severity','?')}, "
                     f"n={c.get('count','?')}) → child ticket under EB-377")
    lines.append("")

    lines += ["## Measurement artifacts (NOT findings)", ""]
    lines.append(f"- Coverage: {s['complete']}/{s['total']} complete, "
                 f"{s['coverage_gap']} coverage_gap, {s['kfx_failed']} kfx_failed.")
    if not determinism.get("reproducible", True):
        lines.append(f"- **VQA scores are non-deterministic** "
                     f"(max delta {determinism.get('max_delta','?')}). Treat "
                     f"VQA-derived clusters as provisional until the grader is "
                     f"stabilized (cf. EB-361).")
    else:
        lines.append("- VQA determinism check passed (bit-exact).")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="EB-377 findings synthesis")
    ap.add_argument("--provenance", required=True)
    ap.add_argument("--batch-qa", required=True)
    ap.add_argument("--determinism", required=True)
    ap.add_argument("--out", default=r"data\batch_reports\EB-377-findings-2026-06-07.md")
    args = ap.parse_args(argv)
    md = synthesize(
        json.loads(Path(args.provenance).read_text(encoding="utf-8")),
        json.loads(Path(args.batch_qa).read_text(encoding="utf-8")),
        json.loads(Path(args.determinism).read_text(encoding="utf-8")),
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.12 -m pytest tests/test_eb377_synthesis.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/synthesize_batch_findings.py tests/test_eb377_synthesis.py
git commit -m "feat(EB-377): findings synthesis with measurement-artifact separation"
```

---

### Task 5: Full Phase-1 test pass + PR + merge

- [ ] **Step 1: Run the four new test modules together**

Run: `py -3.12 -m pytest tests/test_eb377_vqa_policy.py tests/test_eb377_select_corpus.py tests/test_eb377_provenance.py tests/test_eb377_synthesis.py -v`
Expected: all PASS (8 tests).

- [ ] **Step 2: Run the pipeline quick regression to confirm no batch_qa breakage**

Run: `python tools/test_pipeline.py --quick`
Expected: completes without import/syntax errors (header-bleed counts, headings, PAGE markers unchanged per CLAUDE.md post-edit checklist).

- [ ] **Step 3: Push and open the PR**

```bash
git push -u origin feat/EB-377-phase3-sweep-harness
gh pr create --base master --title "feat(EB-377): Phase-3 sweep harness (VQA policy, corpus selection, provenance, synthesis)" --body "Implements the EB-377 spec harness. Four units: calibrated/serialized local VQA in batch_qa.py, select_batch_corpus.py, build_batch_provenance.py, synthesize_batch_findings.py. 8 new tests. No config changes (flags passed per-run)."
```

- [ ] **Step 4: Merge after review (main session holds merge authority), then return to main tree on `master` and pull.**

---

## Phase 2 — Preflight gates (run from main tree on `master`, after merge)

> Each gate is a **stop condition**. Do not proceed to Phase 3 until all pass. Record outputs faithfully — if a gate fails, report it and stop.

### Task 6: R9700 reachability

- [ ] **Step 1: Confirm the local Qwen endpoint serves the model**

Run: `pwsh -Command "(Invoke-RestMethod http://192.168.1.33:8080/v1/models).data.id"`
Expected: contains `Qwen3VL-30B-A3B-Instruct-Q4_K_M.gguf`.
If unreachable: bring the R9700 box up, or escalate to the user before falling back to paid cloud (the spec's documented fallback).

### Task 7: Build + review the corpus manifest (no copy yet)

- [ ] **Step 1: Generate the manifest**

Run: `py -3.12 tools/select_batch_corpus.py --archive archive --fresh F:\books --seed 377 --out logs/batch-selection-2026-06-07.json`
Expected: `Wrote manifest: ... (11 anchors + 39 fresh)` and a non-empty strata line. If an anchor pattern fails to resolve, fix the pattern/filename before continuing.

- [ ] **Step 2: Eyeball the manifest** — open `logs/batch-selection-2026-06-07.json`, confirm the 11 anchors are the intended files and the 39 fresh picks are books (not junk) with a sane genre spread. Swap entries by hand if needed (the seed makes re-runs identical, so manual edits are the adjustment mechanism).

### Task 8: Stage the 50 PDFs

- [ ] **Step 1: Copy into the staging dir**

Run: `py -3.12 tools/select_batch_corpus.py --archive archive --fresh F:\books --seed 377 --out logs/batch-selection-2026-06-07.json --stage processing/batch-2026-06-07`
Expected: `Staged 50 PDFs into processing/batch-2026-06-07`.

### Task 9: VQA determinism

- [ ] **Step 1: Convert one anchor to KFX for the determinism probe**

Run: `pwsh -Command "Import-Module .\module\EbookAutomation.psd1 -Force; Convert-ToKindle -InputFile 'processing\batch-2026-06-07\Pilgrim People.pdf' -UsePdfminer -NoCache"`
Expected: `done -> ...Pilgrim People.kfx`.

- [ ] **Step 2: Run the determinism check with the run's exact policy**

Run: `py -3.12 tools/vqa_determinism_check.py --input "output\kindle\Pilgrim People.kfx" --provider local --dpi 150 --max-pages 20 --runs 2 --tolerance 0`
Expected: PASS / reproducible. If it drifts, **do not block the batch** — record `reproducible:false` and the max delta into `data/batch_reports/EB-377-determinism.json` (consumed by synthesis), so VQA clusters are flagged provisional rather than trusted.

### Task 10: Zero-weld baseline gates (anchors)

- [ ] **Step 1: Scan the two header-bleed anchors' intermediates**

Run: `py -3.12 tools/check_header_bleed.py --input "output\kindle\.intermediates\Pilgrim People_kindle.html"`
Then: `py -3.12 tools/check_header_bleed.py --input "output\kindle\.intermediates\On First Principles_kindle.html"`
(If `On First Principles.kfx` isn't built yet, convert it first as in Task 9 Step 1.)
Expected: both report `weld_total == 0` (exit 0). **Any weld on a clean anchor = harness regression — stop and investigate before the full run.**

### Task 11: Smoke test (2–3 books end-to-end)

- [ ] **Step 1: Run batch_qa over a 2-book smoke folder**

```pwsh
New-Item -ItemType Directory -Force processing\smoke-2026-06-07 | Out-Null
Copy-Item "processing\batch-2026-06-07\Pilgrim People.pdf" processing\smoke-2026-06-07\
Copy-Item "processing\batch-2026-06-07\Python in easy steps.pdf" processing\smoke-2026-06-07\
py -3.12 tools/batch_qa.py run processing\smoke-2026-06-07 --full --vqa --parallel 2
```
Expected: a `data/batch_reports/batch_<ts>.{json,md,html}` is produced, both books reach `visual_qa.attempted: true` with a non-null score, and `api_cost_usd == 0` (fallback off → free). If `visual_qa.enabled:false` blocks the call, that surfaces here — fix before the full run.

---

## Phase 3 — Run, scan, synthesize (main tree, overnight)

### Task 12: Launch the overnight batch

- [ ] **Step 1: Start the 50-book run (background/unattended)**

Run: `py -3.12 tools/batch_qa.py run processing\batch-2026-06-07 --full --vqa --parallel 2`
Expected: per-book progress; final `data/batch_reports/batch_<ts>.{json,md,html}`. Note the `<ts>` run id. Do **not** pass `--max-pages` (it would silently skip large books — see spec §4). Runtime ~2-4h.

### Task 13: Provenance + provenance-scoped header-bleed scan

- [ ] **Step 1: Build the provenance index (this also writes the per-book header reports)**

Run: `py -3.12 tools/build_batch_provenance.py --manifest logs/batch-selection-2026-06-07.json --staged-dir processing/batch-2026-06-07 --batch-qa data\batch_reports\batch_<ts>.json --kfx-dir output\kindle --header-out data\batch_reports\header_bleed --out data\batch_reports\EB-377-provenance.json`
Expected: `Provenance: {"total": 50, "complete": N, "coverage_gap": M, ...}`. Coverage gaps and KFX failures are expected data, not errors.

> **`--batch-qa` is required, not optional.** `Convert-ToKindle` names KFX output from parsed Title/Author metadata, not the source stem (EbookAutomation.psm1). The provenance join reads the real `kindle_conversion.output_path` from the batch_qa report; without `--batch-qa` it falls back to source-stem paths and would misclassify every metadata-renamed success as `coverage_gap`/`kfx_failed`. Use the `<ts>` from Task 12.

### Task 14: Synthesize findings

- [ ] **Step 1: Merge into the findings document**

Run: `py -3.12 tools/synthesize_batch_findings.py --provenance data\batch_reports\EB-377-provenance.json --batch-qa data\batch_reports\batch_<ts>.json --determinism data\batch_reports\EB-377-determinism.json --out data\batch_reports\EB-377-findings-2026-06-07.md`
Expected: `Wrote data\batch_reports\EB-377-findings-2026-06-07.md` with header-bleed verdict, ranked patterns, and a separate measurement-artifacts section.

### Task 15: Validate findings + file child tickets

- [ ] **Step 1: Spot-check (Calibration discipline).** Open 2-3 VQA-flagged pages' PNGs (under the VQA run's image dir) and confirm the flagged issue is real. Open 2-3 header-bleed welds (if any) in the corresponding `_kindle.html` and confirm they are true welds, not detector false positives. Record results in the findings doc.
- [ ] **Step 2: Commit the artifacts.** `data/batch_reports/**` is worktree-exempt (EB-181), so commit directly:

```bash
git add data/batch_reports/EB-377-provenance.json data/batch_reports/EB-377-findings-2026-06-07.md data/batch_reports/EB-377-determinism.json logs/batch-selection-2026-06-07.json
git commit -m "data(EB-377): 50-book sweep provenance, determinism, and findings"
```

- [ ] **Step 3: File a child EB ticket per prioritized real finding**, linked to EB-377 (Atlassian `createJiraIssue`, `parent`/issue-link to EB-377). Measurement artifacts (coverage gaps, non-deterministic VQA) are noted in the findings doc but only become tickets if they represent a real harness defect.
- [ ] **Step 4: Post a summary comment on EB-377** with the header-bleed verdict, the top 3 patterns, and links to the committed artifacts; transition EB-377 per the project workflow.

---

## Self-Review

**Spec coverage:**
- Approach A / `batch_qa.py run` orchestrator → Tasks 1, 11, 12. ✓
- 11/39 hybrid, seeded, stratified, soft genre bias, no hard quota → Task 2. ✓
- Sherlock EPUB excluded (PDF-only) → enforced by `.pdf` filtering in Task 2 + the existing `ext=='pdf'` guard. ✓
- Serialized local VQA (`Semaphore(1)`), `--full` 20pg/150dpi, `--provider local --fallback-enabled false`, 300→900s → Task 1. ✓
- Header-bleed scan scoped to provenance basenames (no stale glob), coverage gaps → Task 3. ✓
- `--max-pages` footgun (none passed) → Task 12 Step 1 note. ✓
- Preflight: R9700, determinism (exact command), zero-weld anchors, smoke test → Tasks 6-11. ✓
- Artifact provenance (source+SHA-256, staged, KFX, intermediate HTML, VQA report, header report, coverage status) → Task 3. ✓
- Synthesis with measurement-artifacts separated → Task 4. ✓
- Findings doc at `data/batch_reports/EB-377-findings-2026-06-07.md` → Task 14. ✓
- Code lands via PR before run; batch runs from main tree → Tasks 5, Phase 2/3 headers. ✓
- Child fix tickets under EB-377 → Task 15. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every command shows expected output. ✓

**Type consistency:** `select_corpus` returns `{anchors, fresh, strata_counts, seed}` (Task 2) consumed by `build_provenance` (Task 3) which adds `_staged_dir`; `build_provenance` returns `{books, summary}` consumed by `synthesize` (Task 4). `weld_total` is `int|None` consistently. `check_header_bleed.detect(...).weld_total/.findings` used in Task 3 matches the verified `BookResult` dataclass. ✓
