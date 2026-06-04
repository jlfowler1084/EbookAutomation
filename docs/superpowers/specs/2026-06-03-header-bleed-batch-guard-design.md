# Header-Bleed Batch Guard — Design

- **Date:** 2026-06-03
- **Status:** Design approved (pre-implementation)
- **Builds on:** EB-367 (running-header bleed fix; merged PR #190 `8ec76d9`, solution PR #191 `0148b23`)
- **Jira:** [EB-370](https://jlfowler1084.atlassian.net/browse/EB-370) — "Header-bleed batch guard: HTML weld detector + overnight-batch gate + corpus sweep" (relates to EB-367)

## Problem

EB-367 fixed the project's most-recurring defect: short ALL-CAPS running headers
(e.g. `PILGRIM PEOPLE 73`) being welded into adjacent **body** paragraphs by the
page-boundary rejoin pass. Pilgrim People went from 310 body-header welds to 0.

That fix is code-level and book-agnostic, but there is **no batch-level guard**:
nothing verifies that future conversions stay clean, and nothing audits books that
already went through the pipeline. The ask: make future batch jobs detect header
bleed automatically, and confirm other books are clean.

## Goals

1. A **reusable detector** that finds header-bleed in a converted book's HTML
   without knowing the header string a priori.
2. A **forward batch gate**: every overnight batch run scans its own freshly
   produced HTML and flags suspect books — loudly, but never blocking the run.
3. A **retroactive sweep**: re-extract a scoped, trusted corpus with the current
   pipeline and scan it, doubling as the detector's calibration baseline.

## Non-goals (v1)

- Detecting non-ALL-CAPS bleed classes (mixed-case, small-caps, author-name verso
  headers). The detector is structured to extend here later; v1 ships the EB-367
  ALL-CAPS class only.
- Re-extracting the full ~87-book inventory. Broad coverage of books outside the
  scoped corpus comes from the forward gate catching them on their next batch run.
- EPUB re-extraction in the sweep (the Sherlock Holmes EPUB anchor). `run_extraction()`
  is PDF-oriented; EPUB sweep coverage is a logged, deferred extension.
- Auto-deleting, quarantining, or blocking any output. Warn-loudly-never-block.
- Inline self-check inside `extract_tts_text.py` (Approach C). The detector is built
  so this can be layered on later, but it is not built now.

## Approach (selected: A)

A standalone Python detector module + a thin batch phase + a sweep wrapper. Chosen
over folding into the VQA/baseline gate (wrong altitude — VQA is image/VLM and
page-sampled, baseline validation does not run on arbitrary new batch output) and
over an inline extraction assertion (awkward to emit batch-level reports/exit codes
from the hot path; cannot audit already-converted books).

The detector is a **pure function over HTML**, so the same core asset serves both
the forward gate (scan fresh HTML) and the sweep (scan re-extracted HTML), and can
be pointed at any directory of `*_kindle.html` ad-hoc.

## Component 1 — Detector core (`tools/check_header_bleed.py`)

**Input:** an HTML string or file path — the `_kindle.html` artifact the pipeline
preserves at `output/kindle/.intermediates/<name>_kindle.html`
([psm1:2359](../../../module/EbookAutomation.psm1)).

**Parsing:** stdlib `html.parser` (tolerant), **not** a line regex. The parser walks
the document tracking the "current page" from page anchors `<a id="page_N"></a>`
([extract_tts_text.py:7266](../../../tools/extract_tts_text.py)) and buckets each
`<p>` and `<h*>` element to the most recent anchor. This is robust to `<p class=…>`,
multi-line paragraphs, and inline tags (`<sup>`, `<em>`, `<a>`), which are stripped
to text before matching.

**Candidate generation (per body `<p>`):** find runs of **2+ consecutive ALL-CAPS
words** (letters plus apostrophes — including curly `'`/`'` — and hyphens),
optionally adjacent to a 1–4 digit page number. Normalize each candidate: strip a
leading/trailing page number, collapse whitespace, casefold. Yields e.g.
`pilgrim people`.

**Aggregation:** per normalized candidate, record occurrence count, the set of
distinct source pages (from anchor attribution), and windowed sample snippets
(±~60 chars around the match + page number, **not** the whole paragraph — faster
triage on long fused paragraphs).

**Body-weld gate — a candidate is a finding iff ALL hold:**

| Rule | Value | Source / rationale |
|---|---|---|
| Distinct-page recurrence | `distinct_pages >= 5` | A2 filter ([extract_tts_text.py:6641](../../../tools/extract_tts_text.py)) |
| Page density | `distinct_pages / total_pages >= 0.10` | A2 filter ([:6642](../../../tools/extract_tts_text.py)); protects content like *Python in Easy Steps* step-instructions (~2% density) |
| Normalized length | `6 <= len <= 40` | **Lower floor than A2's 15** — see trap below |

> **The 15-char trap (critical).** A2 only considers strings `>= 15` chars
> ([:6613](../../../tools/extract_tts_text.py), [:6626](../../../tools/extract_tts_text.py)).
> "PILGRIM PEOPLE" is 14 chars — *that floor is the literal reason A2 missed it and
> the bug existed*. The detector therefore borrows A2's **density gate** but uses a
> **lower length floor**, or it inherits A2's blind spot and reports "clean" on the
> exact defect class it exists to catch. The density gate (≥10% of pages) is what
> controls false positives at short lengths — not the length floor.

**`total_pages` = book page span** = max page number seen across anchors (fallback:
distinct-anchor count if anchors are non-numeric/absent). Span, not distinct-anchor
count, so density is not inflated when some pages emit no anchor.

**Page attribution is approximate (±1)** because rejoin can fuse a paragraph across
a page boundary. Tolerable: the gate keys on distinct-page **count** over dozens of
occurrences; ±1 does not move a real header below threshold.

**Heading-noise bucket (informational, never blocks):** the same density gate
applied to short header-like strings recurring as `<h*>` elements populates
`heading_repeats`. Running headers have historically been mis-promoted to headings,
so this evidence is reported — but it never increments `weld_total` or changes
`status`.

**Per-book output:**
```json
{
  "file": "<name>_kindle.html",
  "status": "clean | flagged",
  "weld_total": 0,
  "total_pages": 0,
  "findings": [
    {"candidate": "pilgrim people", "occurrences": 14, "distinct_pages": 12,
     "density": 0.41, "samples": ["…±60 char window… (p.73)"]}
  ],
  "heading_repeats": []
}
```

## Component 2 — CLI contract

```
py -3.12 tools/check_header_bleed.py --input <file|dir> [--glob "*_kindle.html"]
    [--out <json>] [--min-distinct-pages 5] [--min-density 0.10]
    [--len-min 6] [--len-max 40] [--quiet]
```

- Scans a file or directory (default glob `*_kindle.html`). Human summary → stdout;
  machine JSON → `--out` (default `data/batch_reports/header_bleed/<timestamp>.json`;
  `data/batch_reports/**` is worktree-exempt per EB-181 / CLAUDE.md).
- **Exit codes** (mirroring the VQA audit, [compare_vqa_reports.py:25](../../../tools/compare_vqa_reports.py)):
  - `0` — all scanned books clean
  - `1` — nothing scannable (no matching HTML); informational, not a defect
  - `2` — ≥1 book flagged (real body welds)
  - `3` — infrastructure/data/usage error (parse failure, unreadable file, bad args)
- **argparse override:** `ArgumentParser.error()` must be overridden to exit `3`,
  because argparse's default is `2` — which would collide with "flagged." An explicit
  invalid-args test asserts exit `3`.
- **JSON schema** `header_bleed_report/v1`:
  `{schema, generated_utc, params, summary:{scanned,clean,flagged,errors}, books:[…]}`.

## Component 3 — Batch integration (new Phase 2.5)

In `tools/run_overnight_batch.ps1`, after Phase 2 (pipeline) and **before** Phase 3
(VQA) — the cheap deterministic text check runs ahead of the expensive VLM pass.

- Resolve the intermediates dir as `output/kindle/.intermediates` (Hidden).
- Restrict to **this run's new KFX set** (the script already snapshots `$preExisting`
  and computes `$newKfx`): scan only `${stem}_kindle.html` matching the new KFX
  stems, so stale intermediates from prior runs do not pollute findings.
- Invoke the CLI, capture its exit code, write the report under
  `data/batch_reports/header_bleed/`.
- **Log flagged books prominently** in the final summary block.
- Add a **batch status accumulator** with precedence `3 > 2 > 1 > 0`, folding in
  pipeline and VQA failures deliberately, and `exit` with it. (The batch currently
  never sets a final exit code — [run_overnight_batch.ps1:192](../../../tools/run_overnight_batch.ps1).)
- **Never aborts** — all phases still run; the gate only warns + flags.

## Component 4 — Sweep wrapper + calibration (`tools/sweep_header_bleed.ps1`)

- Re-extract the **scoped corpus** — the PDF baseline books + Pilgrim — by reusing
  `test_pipeline.run_extraction()` ([test_pipeline.py:563](../../../tools/test_pipeline.py)),
  **not** `recapture_baselines.py` (which clobbers `expected_baselines.json` —
  [recapture_baselines.py:255](../../../tests/recapture_baselines.py)). Reads source
  files from `archive/`; writes HTML only inside the project (no `F:\books` writes).
  The Sherlock Holmes EPUB anchor is deferred (see non-goals).
- Run the CLI over the fresh HTML; emit a sweep report under
  `data/batch_reports/header_bleed/`.
- **Calibration gate** (CLAUDE.md harness-validation rules, baked in as the sweep's
  self-test):
  1. **Determinism** — detector run twice on identical HTML → identical
     `books[]`/`findings` (timestamp envelope excluded from the comparison).
  2. **Zero false positives** — the known-clean baseline books → **0 flagged**.
     Any flag is a detector bug, reported as such, not escalated as a real finding.
  3. **Sensitivity** — a committed **pre-fix Pilgrim HTML fixture** (small slice with
     the weld) → **must flag**. (Re-extracting Pilgrim today yields 0 welds since it
     is fixed, so sensitivity is proven against a captured fixture, not live
     extraction.)

## Component 5 — Testing (`tests/test_header_bleed_detector.py`, `python -m pytest tests/`)

**Unit (synthetic HTML, fast):**
- Welded short-caps header across 6 pages at ≥10% density → flagged, `weld_total>0`.
- Recurring instruction at <10% density (Python-in-Easy-Steps shape) → **not** flagged.
- ALL-CAPS acronym one-offs / sparse → not flagged.
- Header recurring as `<h*>` → `heading_repeats` populated, `weld_total==0`, clean.
- Anchor-based page attribution with a boundary-rejoined paragraph → ±1 tolerated.
- Curly-apostrophe candidate handled.
- Determinism (findings stable across two runs).
- All four exit codes, including invalid args → `3`.

**Calibration (slower, marked):** scoped re-extract → 0 flags; pre-fix Pilgrim
fixture → flagged.

**Regression:** detector is purely additive/read-only — no pipeline behavior change.
Add the new CLI/file to `feature-manifest.json`; run `verify-manifest.ps1` to keep
the manifest check green.

## Risks / open items

- **Threshold portability.** The 10% density gate is calibrated on the existing
  corpus. Books with very long page spans and genuinely repeated short caps content
  could in theory slip through or false-trip; the calibration baseline is the guard
  against this, and thresholds are CLI-tunable.
- **EPUB coverage gap** in the sweep (deferred). Forward gate covers EPUB books on
  their next batch run.
- **Pre-fix fixture maintenance.** The sensitivity fixture is a frozen artifact; if
  the HTML emission format changes materially, the fixture (and the anchor-parsing
  assumptions) must be revisited.
```
