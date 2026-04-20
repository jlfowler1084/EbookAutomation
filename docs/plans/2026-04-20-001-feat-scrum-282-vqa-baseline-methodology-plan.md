---
title: "feat: VQA baseline methodology — standardize to KFX→Calibre source (SCRUM-282)"
type: feat
status: active
date: 2026-04-20
origin: docs/brainstorms/2026-04-20-scrum-282-vqa-baseline-methodology-requirements.md
ticket: SCRUM-282
---

# feat: VQA baseline methodology — standardize to KFX→Calibre source (SCRUM-282)

## Overview

Fix VQA baseline source-format drift by strengthening the audit mechanism, adding a
`capture_pipeline` field with true code-path provenance, emitting a capture-time
warning when a PDF input shadows an existing KFX, and re-capturing the one
known-drifted baseline (Atomic Habits) from the KFX→Calibre path. Lands a reusable
audit capability inside `tools/compare_vqa_reports.py` so future baseline sets can
be validated without burning Claude Vision API spend. The field is named
`capture_pipeline` (not `source_format` as the origin doc proposed) because
`source_format` already exists in the repo with different, extension-derived
semantics (see Key Technical Decisions).

## Problem Frame

During SCRUM-280 Investigation (A), the Atomic Habits Claude baseline in
`data/vqa_baseline_post_274/` was found to have been captured from the original PDF
source (266 pages) rather than the KFX→Calibre path (272 pages). Because
`select_sample_pages()` in `tools/visual_qa.py` is deterministic on
`(pages_total, bookmark_pages)`, the baseline sampled
`[1, 2, 3, 73, 92, 145, 158, 232]` while the live smoke sampled
`[1, 2, 3, 91, 94, 149, 152, 238]` — zero interior-page overlap, so direct |Δ|
comparison is unreliable. Atomic Habits was excluded from the SCRUM-280 R2 gate
as a result. The other 5 baselines are believed to be in parity but have never been
programmatically verified, and the JSON schema has no field recording which source
path produced each baseline.

(See origin: `docs/brainstorms/2026-04-20-scrum-282-vqa-baseline-methodology-requirements.md`)

## Requirements Trace

Carried forward from the origin document. R5 and R6 use `capture_pipeline` instead
of the origin doc's `source_format` to avoid collision with an existing field of
the same name in `tools/test_pipeline.py`, `tools/pattern_db.py`, and
`test-corpus/*.baseline.json` (see Key Technical Decisions).

- **R1.** Audit all 6 baselines by comparing `pages[].page_number` arrays against a
  fresh `select_sample_pages()` run on the current KFX-derived PDF.
- **R2.** Re-capture the Atomic Habits Claude baseline from the KFX→Calibre path.
- **R3.** Preserve the existing PDF-sourced Atomic Habits baseline in an archive
  subdirectory (moved, not copied).
- **R4.** Re-run R1's audit after re-capture; confirm all 6 baselines produce exact
  sampled-page parity against fresh KFX-derived sampler runs.
- **R5.** Add a `capture_pipeline` field (values: `"kfx-calibre"` or `"pdf-direct"`)
  to every baseline JSON, set by capture code based on which pipeline branch
  executed.
- **R6.** Backfill `capture_pipeline` on the 5 in-parity baselines (patch JSONs
  once R1 confirms parity; backfill gated on U1 exit 0 — see Key Decisions).
- **R7.** Emit a loud warning at capture time when input is PDF and a matching KFX
  exists at the conventional output path (using normalized stem matching — see
  U3). Capture still proceeds.
- **R8.** Add a KFX-only baseline rule to the `CLAUDE.md` Visual QA section
  documenting the `capture_pipeline` field.
- **R9.** When re-capturing Atomic Habits, the new baseline's filename stem must
  match the KFX-based smoke-run stem so `compare_vqa_reports.py` finds it via
  stem lookup. Archiving is a move, not a copy.

## Scope Boundaries

- **Not re-baselining** the 5 books believed in parity (pending R1 confirmation);
  the audit is expected to confirm them without burning Claude Vision API spend.
- **No hard block** on PDF-sourced captures when KFX exists — warning only
  (see origin: Key Decisions).
- **No richer provenance** beyond `capture_pipeline` (no file hash, Calibre
  version, or capture-tool version). See Calibre-version caveat in Risks table —
  this boundary is intentional but has a known failure mode that the plan
  accepts as tracked rather than prevented.
- **No change to** `select_sample_pages()` — the determinism property is correct;
  the fix is at the input layer, not the sampler.
- **No change to** the VQA rubric or scoring logic.
- **No modification of the existing `source_format` field** in
  `tools/test_pipeline.py`, `tools/pattern_db.py`, or `test-corpus/*.baseline.json`.
  That field has different semantics (extension-derived, pipeline-agnostic) and
  its own consumers; renaming or merging it is out of scope.

## Context & Research

### Relevant Code and Patterns

- `tools/visual_qa.py`
  - `select_sample_pages()` (~line 212) — deterministic sampler on
    `(pages_total, bookmark_pages)`
  - `convert_to_pdf()` (~line 118) — Calibre `ebook-convert` subprocess with
    300s timeout per book. Used by U1's audit via direct import to refresh
    the KFX-derived PDF (see U1 Approach).
  - `get_pdf_page_count()` (~line 166) and `get_pdf_bookmarks()` (~line 186) —
    pypdf-based helpers imported by U1.
  - Capture dispatch (~lines 608-614) — branches on input extension among
    `.pdf` / `.kfx` / `.azw3` / `.epub`. The KFX/AZW3/EPUB branches invoke
    Calibre conversion; the PDF branch skips it. This is the branch point from
    which R5 derives `capture_pipeline`.
  - Baseline JSON writer (`build_report`) — emits the report with current keys:
    `book, timestamp, model, pages_sampled, pages_total, dpi, overall_score,
    overall_pass, pass_threshold, category_scores, pages, summary, top_issues,
    token_usage`. No `capture_pipeline` field today.
- `tools/compare_vqa_reports.py`
  - `_stems()` discovery (~line 94) and `_load()` lookup (~line 123) — stem-based
    baseline matching that drives smoke comparison. R9's stem-parity requirement
    flows through this file. The audit subcommand (U1) extends this tool rather
    than creating a new one because the overlap-guard and stem-matching logic
    already live here.
- `data/vqa_baseline_post_274/` — 6 baseline JSONs. The `book` field in each
  already ends in `.pdf` or `.kfx`, confirming which input was used (5 `.kfx`,
  1 `.pdf` for Atomic Habits). This is the source for R1's initial triage but
  not the load-bearing audit — R1 compares sampled pages, not file extensions.
- **Existing `source_format` field collision** (discovered during plan review)
  - `tools/test_pipeline.py:467` — sets `'source_format': ext.lstrip('.')`
  - `module/EbookAutomation.psm1:6276` — passes `source_format=$ext` to pattern_db
  - `tools/pattern_db.py:162` — SQLite column storing extension-derived value
  - `test-corpus/*.baseline.json` — 6 files, each with
    `"source_format": "pdf"` or similar, using extension semantics
  - `tools/import_vqa_reports.py:92` — consumes VQA baselines and derives
    format via `.suffix` (a real downstream consumer of the VQA baseline JSON).
  - These use extension-derived semantics and are out of scope for this plan.
    The VQA-baseline field uses the new name `capture_pipeline` to avoid
    semantic conflation.
- `CLAUDE.md` — "Visual QA System" section (~line 164). R8 inserts the KFX-only
  baseline rule here; deferred question already resolved to integrate into
  existing section rather than creating a new subsection.
- `feature-manifest.json` — tracks CLI flags and paths; the `--audit` subcommand
  in U1 needs an entry here. `tools/verify-manifest.ps1` must pass after edits.

### Institutional Learnings

From `docs/solutions/` — directly applicable patterns from recent sibling tickets:

- **`scrum-280-local-vqa-calibration-patterns.md` Lesson 5** — canonical root-cause
  writeup of the baseline source-format drift. Recommends verifying
  page-selection parity *before* interpreting |Δ| as a quality gap. That
  verification is exactly the contract of R1's audit subcommand. Note: the
  lesson uses `source_format` as the proposed field name; this plan departs
  to `capture_pipeline` for the collision reason above.
- **`scrum-281-fallback-fingerprint-routing.md` Lesson 2** — additive field
  pattern for baseline schema extensions. `build_report` grew four optional
  kwargs in SCRUM-281 without restructuring the schema; existing consumers
  unaffected. Apply the same pattern for `capture_pipeline` — additive optional
  kwarg with a default, not a required-field breaking change.
- **`scrum-281-fallback-fingerprint-routing.md` Lesson 4** — regression fixtures
  for tunable detection logic. Land 3 frozen fixtures with U1: the Atomic Habits
  drift case (pre-fix), a partial-overlap fixture to exercise the skipped/mismatch
  exit-code logic, and a clean-parity case. Document fixture provenance.

### External References

None — internal tooling methodology change; local patterns and institutional
learnings are sufficient.

## Key Technical Decisions

- **Audit via sampled-pages diff, not full Claude re-run** — comparing
  `pages[].page_number` lists against a fresh `select_sample_pages()` run
  exercises the exact determinism surface that produced the drift. Zero Claude
  API spend; a local Calibre invocation per book is needed to refresh the
  KFX-derived PDF from which bookmarks are extracted. Chosen over pages_total
  diff because coincidentally-matching page counts would otherwise pass audit
  with no real signal.
- **U1 obtains fresh PDF page count + bookmarks by importing helpers from
  `visual_qa.py` and invoking Calibre per book** — of the three options
  considered (import helpers, `--pdf-cache-dir` flag, shared helper module),
  direct import is the smallest change: 3 helper imports (`convert_to_pdf`,
  `get_pdf_page_count`, `get_pdf_bookmarks`) and no new flags. The audit
  subcommand therefore has the same Calibre dependency as the capture tool,
  which is acceptable because an operator running audits already has Calibre
  available. If the coupling grows painful later, extract to a shared helper
  module as a refactor.
- **Field named `capture_pipeline`, not `source_format`** — the origin document
  proposed `source_format`, but `source_format` is already a field in
  `tools/test_pipeline.py`, `tools/pattern_db.py`, and the 6
  `test-corpus/*.baseline.json` files, where it carries extension-derived
  semantics ("pdf", "kfx", etc.). A VQA-baseline field with the same name but
  different semantics (pipeline-branch provenance) would confuse future
  readers and creates a real collision risk with `tools/import_vqa_reports.py`,
  which currently consumes VQA baselines and derives format from the `book`
  field's extension. `capture_pipeline` with values `"kfx-calibre"` /
  `"pdf-direct"` is distinct enough to rule out conflation.
- **`capture_pipeline` records the executed code path, not the input extension** —
  if Calibre conversion ran in this capture, `"kfx-calibre"`; if the PDF-skip
  branch ran, `"pdf-direct"`. Extension-based labelling has the same failure
  mode it was designed to prevent (a KFX-derived intermediate PDF fed to
  `visual_qa.py` would be mis-labeled `"pdf"`). AZW3/EPUB inputs record
  `"kfx-calibre"` because they flow through the Calibre conversion branch —
  the value names the pipeline, not the input file extension.
- **Additive schema field, optional kwarg, default-null for legacy reads** —
  per SCRUM-281 precedent. Existing baselines without the field must still
  load cleanly; `capture_pipeline` is emitted only when the capture code knows
  which branch ran.
- **Warning, not hard block** — preserves the ability to baseline a book that
  hasn't been through Calibre yet (legitimate case); catches the recurring
  mistake class without forcing an override flag that itself becomes a foot-gun.
- **U3 warning uses normalized-stem matching, not exact-match** — the motivating
  Atomic Habits case has a PDF stem (underscored, no author) that does not
  exact-match the KFX stem (spaces, author suffix). The warning applies a
  normalization rule (see U3 Approach) so the Atomic Habits drift class
  actually triggers the warning.
- **Archive via move, not copy** — into `data/vqa_baseline_post_274/.archive/`
  (dot-prefixed as convention for future maintainers;
  `compare_vqa_reports.py::_stems()` uses a non-recursive glob that does not
  descend into subdirectories regardless of prefix). Move ensures only one
  baseline per book remains discoverable in the active directory.
- **U4 re-capture uses temp-promote protocol, not in-place overwrite** — the
  re-capture is the only destructive step in the plan. Protocol: (1) re-capture
  to a temp path; (2) run U1 audit against the temp file; (3) only on audit
  pass, `git mv` the drifted baseline to `.archive/` and promote the temp
  file into the active directory. Split across two commits (archive, then
  promote) so a failure between steps is recoverable by `git reset --soft
  HEAD~1` without losing the archived original. Prevents silent overwrite of
  an existing `output/kindle/Atomic Habits…_visual_qa_report.json` from a
  prior smoke run.
- **Extend `compare_vqa_reports.py` with an `--audit` subcommand, not a new
  standalone tool** — the overlap-guard and stem-matching logic already lives
  there; a new tool would duplicate ~100 lines. This is a delta, not a parallel
  tool.
- **R6 backfill is explicitly gated on U1 exit 0** — if any of the 5
  non-Atomic-Habits baselines fails audit, backfilling `"kfx-calibre"` onto it
  would stamp a false provenance claim. The plan's U5 dependency on U1 is
  structural; this decision makes the data contract explicit: no backfill
  until audit clears.
- **R6 backfill via JSON patch, not re-capture** — R1's strengthened
  sampled-pages audit is independent verification; re-capturing the 5 books
  would burn Claude Vision API spend for zero marginal signal.

## Open Questions

### Resolved During Planning

- **Archive location** (origin deferred question): `data/vqa_baseline_post_274/.archive/`
  subdirectory. Dot-prefix is convention only — `tools/compare_vqa_reports.py::_stems()`
  uses a non-recursive glob that does not descend into subdirectories regardless
  of prefix, so archived files are automatically excluded from smoke comparison.
  The dot-prefix signals "do not touch" to future maintainers.
- **Audit tool scope** (origin deferred question): Extend
  `tools/compare_vqa_reports.py` with an `--audit` subcommand rather than creating
  `tools/audit_vqa_baselines.py`. Overlap-guard and stem-matching live there;
  reuse reduces code-surface churn.
- **CLAUDE.md placement for R8** (origin deferred question): Integrate into the
  existing "Visual QA System" section (no new subsection).
- **R6 backfill method** (origin deferred question): JSON patch (in-place edit
  of the 5 baseline files). R1's audit provides the verification; no re-capture
  needed. Gated on U1 exit 0.
- **feature-manifest.json placement for `--audit`**: Register
  `compare_vqa_reports.py` as a new top-level entry with an explicit
  `subcommands: ["compare", "audit"]` field, following the convention used
  elsewhere for multi-subcommand tools. Do not add `--audit` as a flag on
  `visual_qa.py` (unrelated tool).
- **Field name collision with existing `source_format`** (surfaced by plan
  review): renamed to `capture_pipeline` with values `"kfx-calibre"` /
  `"pdf-direct"`. See Key Technical Decisions.
- **AZW3/EPUB enum semantics** (origin deferred question): value is
  `"kfx-calibre"` because both input formats flow through the Calibre
  conversion branch. The value names the executed pipeline, not the input
  extension; the rename to `capture_pipeline` makes this naturally unambiguous.
- **U1 Calibre invocation mechanism** (surfaced by plan review): import
  `convert_to_pdf`, `get_pdf_page_count`, `get_pdf_bookmarks` from
  `tools/visual_qa.py` as helpers. Audit invokes Calibre per book, subject to
  the per-book 300s timeout that already applies to capture. Per-audit
  wall-clock cost is dominated by Calibre conversion; performance target <10
  min on 6-book corpus.
- **U3 stem-normalization rule** (surfaced by plan review): for matching a PDF
  input's stem against KFX candidates in `output/kindle/`, normalize both by
  (a) lowercasing, (b) replacing non-alphanumeric runs with single spaces,
  (c) stripping a trailing " - <author>" suffix (longest-match), (d) collapsing
  whitespace and stripping leading/trailing. Match on normalized-stem equality.
  Locks the heuristic so the motivating Atomic Habits case triggers.
- **U4 destructive-step protocol** (surfaced by plan review): temp-promote,
  two-commit sequence. See Key Technical Decisions; see U4 Approach for the
  operational steps.

### Deferred to Implementation

- **Exact warning text + log level in R7** — must inspect the existing logging
  conventions in `tools/visual_qa.py` at implementation time. Project uses
  Python `logging` per CLAUDE.md global; pick `warning` severity with a message
  that names both the input path and the conflicting KFX path.
- **Calibre-version drift as a potential audit false-positive cause** — if any
  of the 5 "in-parity" baselines fails R1, the root cause could be source-format
  drift *or* a Calibre-version / bookmark-extraction change between original
  capture and audit. Scope Boundaries explicitly rejects Calibre-version
  tracking as a schema field, accepting this failure mode as "detect and
  investigate manually" rather than "prevent automatically." When a failure
  occurs, the operator should re-run the original baseline capture against
  the same KFX to confirm whether the Calibre output has changed before
  re-capturing the Claude baseline.
- **Fixture storage location** — `tests/fixtures/vqa_baseline_audit/` vs inline
  pytest fixtures. Planning defaults to a dedicated fixture directory for the
  3 frozen cases; implementer may inline if the fixtures end up tiny.
- **U1 DI seam for Calibre-free unit tests** — monkeypatching the three
  imported helpers in pytest is the path of least resistance; if that proves
  brittle, factor the audit as `run_audit(baseline_dir, fresh_sample_fn)` with
  a Calibre-backed default and a dict-lookup stub for tests. Leave the
  decision to the implementer; both work.

## Implementation Units

- [ ] **Unit 1: Baseline audit subcommand + regression fixtures**

**Goal:** Ship the reusable audit capability that compares a baseline's
`pages[].page_number` array against a fresh `select_sample_pages()` run against
the current KFX-derived PDF for the same book. Lands 3 frozen fixtures capturing
the known drift pattern, a partial-overlap case, and a clean-parity case for
regression protection.

**Requirements:** R1 (ships the audit code + fixtures). R4 satisfaction is
deferred to U4, which runs the audit against the live corpus after re-capture.

**Dependencies:** None. Runs independently of U2, U3 — units U1, U2, and U3
may be implemented in any order or in parallel.

**Performance target:** audit run on the 6-book corpus completes in under 10
minutes wall-clock (Calibre conversion dominates). Not a pre-commit gate; an
operator or CI job scope.

**Files:**
- Modify: `tools/compare_vqa_reports.py` (add `--audit` subcommand; import
  `convert_to_pdf`, `get_pdf_page_count`, `get_pdf_bookmarks`,
  `select_sample_pages` from `tools/visual_qa.py`; reuse `_stems()` / `_load()`
  helpers already present)
- Create: `tests/test_baseline_audit.py`
- Create: `tests/fixtures/vqa_baseline_audit/atomic_habits_drift.json`
- Create: `tests/fixtures/vqa_baseline_audit/partial_overlap.json`
- Create: `tests/fixtures/vqa_baseline_audit/clean_parity.json`

**Approach:**
- Subcommand signature: `python tools/compare_vqa_reports.py audit [--baseline-dir data/vqa_baseline_post_274/] [--kfx-dir output/kindle/]`.
- For each baseline JSON: look up the matching KFX by stem, call
  `convert_to_pdf(kfx_path)` to produce a fresh KFX-derived PDF, then
  `total_pages = get_pdf_page_count(pdf_path)`,
  `bookmark_pages = get_pdf_bookmarks(pdf_path)`, then
  `select_sample_pages(total_pages, max_samples=8, bookmark_pages=bookmark_pages)`,
  and compare the result to the baseline's `pages[].page_number` list.
- Exit codes: 0 all-parity, 1 any-skipped (no mismatches), 2 any-mismatch
  (regardless of skips). Print a parity table (baseline / expected sample /
  actual sample) for debug.
- Fixture structure: minimal baseline-JSON shape (just `book` + `pages_total` +
  `pages[].page_number`) plus a synthetic "expected fresh sample" value. Unit
  tests monkeypatch the three imported `visual_qa.py` helpers so Calibre is
  not invoked.

**Patterns to follow:**
- `tools/compare_vqa_reports.py` existing CLI argparse + subcommand layout
- SCRUM-281 frozen-fixtures pattern
  (`docs/solutions/scrum-281-fallback-fingerprint-routing.md` Lesson 4)

**Test scenarios (unit, pytest, Calibre helpers monkeypatched):**
- Happy path: a fixture baseline JSON whose `pages[].page_number` matches a
  synthetic "expected fresh sample" list → audit reports parity, exit 0.
- Error path: `atomic_habits_drift.json` fixture (PDF-sourced pages) vs
  synthetic KFX-based expected sample → audit reports drift, exit 2, diff
  table names book + shows both page lists.
- Edge case: baseline JSON missing the `pages[].page_number` array (legacy or
  malformed) → clear error message naming the file, exit 2, no silent pass.
- Edge case: matching KFX file not found for a given baseline stem → warn and
  continue (do not crash); audit marks entry "skipped" in summary; exit 1 if
  any skipped and no mismatches, exit 2 if any mismatches regardless of
  skips.
- Integration: subcommand does not break existing `compare_vqa_reports.py`
  default behavior (verify the prior smoke-comparison path still works).

**Verification (integration, invokes Calibre):**
- `python tools/compare_vqa_reports.py audit` runs end-to-end on the 6
  current live baselines and produces a parity report. This is the
  operational verification that U4 later depends on, distinct from the
  fixture-based pytest cases above.
- `pytest tests/test_baseline_audit.py` passes on all 3 fixtures.
- Existing smoke comparison runs remain green.

---

- [ ] **Unit 2: `capture_pipeline` field + code-path derivation in visual_qa.py**

**Goal:** Record true pipeline-branch provenance on every baseline by tagging
which `visual_qa.py` code path executed, not the input file extension.

**Requirements:** R5

**Dependencies:** None. Independent of U1, U3 — may be implemented first,
last, or in parallel with the other two non-data units.

**Files:**
- Modify: `tools/visual_qa.py` (capture dispatch at ~lines 608-614; baseline
  JSON writer `build_report`)
- Create: `tests/test_capture_pipeline_derivation.py`

**Approach:**
- At the dispatch branch point in `visual_qa.py`, record which branch executes:
  `"kfx-calibre"` if Calibre conversion was invoked (KFX / AZW3 / EPUB inputs),
  `"pdf-direct"` if the PDF-skip branch was taken.
- Thread the value through to the baseline JSON writer as an additive optional
  kwarg (per SCRUM-281 precedent). Default to not emitting the field if the
  value is unknown — legacy compatibility.
- No change to `select_sample_pages()`, the rubric, the existing `source_format`
  field used elsewhere in the repo, or any other VQA baseline schema field.

**Patterns to follow:**
- SCRUM-281 additive-fields pattern
  (`docs/solutions/scrum-281-fallback-fingerprint-routing.md` Lesson 2) —
  `build_report` optional kwargs, emit only when derivable.

**Test scenarios:**
- Happy path: capture runs against a `.kfx` input, new baseline JSON contains
  `"capture_pipeline": "kfx-calibre"`.
- Happy path: capture runs against a `.pdf` input, new baseline JSON contains
  `"capture_pipeline": "pdf-direct"`.
- Edge case: capture runs against a `.azw3` or `.epub` input (both flow through
  Calibre), new baseline JSON contains `"capture_pipeline": "kfx-calibre"` —
  the code path that produced the rendered pages, not the input extension.
- Edge case: parsing an existing baseline JSON that lacks `capture_pipeline`
  (legacy format) does not crash and does not fabricate a value.
- Integration: `tools/compare_vqa_reports.py audit` (U1) still loads legacy
  and new-format baselines without error. The existing `source_format` field
  in `test-corpus/*.baseline.json` is untouched — U2 only modifies the VQA
  baseline writer, not the extraction pipeline sidecars.

**Verification:**
- `pytest tests/test_capture_pipeline_derivation.py` passes.
- A fresh capture against any KFX file produces a JSON with
  `"capture_pipeline": "kfx-calibre"`.

---

- [ ] **Unit 3: Capture-time KFX-shadow warning in visual_qa.py**

**Goal:** Emit a loud warning at capture time when a PDF input shadows an
existing KFX at the conventional output path, so operators catch the recurring
source-format mistake class immediately. Capture still proceeds. Uses
normalized-stem matching so the motivating Atomic Habits case actually triggers
the warning.

**Requirements:** R7

**Dependencies:** None. Independent of U1 and U2 — parallelizable with them.

**Files:**
- Modify: `tools/visual_qa.py` (capture dispatch PDF branch; add a
  `_normalize_book_stem()` helper)
- Create: `tests/test_pdf_kfx_warning.py`

**Approach:**
- Define `_normalize_book_stem(stem: str) -> str` which applies in order:
  (1) lowercase, (2) replace any run of non-alphanumeric characters with a
  single space, (3) strip a trailing ` - <author>` suffix if present (where
  `<author>` is the longest-matching suffix after the last ` - ` separator),
  (4) collapse whitespace and strip leading/trailing.
- Before the PDF-skip branch completes, normalize the input PDF's stem and
  every KFX stem in the conventional output path (e.g., `output/kindle/*.kfx`).
  If any normalized KFX stem equals the normalized PDF stem, emit a
  `logging.warning(...)` naming both the input PDF path and the conflicting
  KFX path.
- Continue with capture; do not block or require an override flag.
- The normalization rule handles the Atomic Habits case: PDF stem
  `"Atomic Habits_ Tiny Changes, Remarkable Results_ An Easy & Proven Way to Build Good Habits & Break Bad Ones"`
  normalizes to `"atomic habits tiny changes remarkable results an easy proven way to build good habits break bad ones"`;
  KFX stem `"Atomic Habits Tiny Changes, Remarkable Results An Easy & Proven Way to Build Good Habits & Break Bad Ones - James Clear"`
  normalizes to the same string after the author-suffix strip. Match succeeds,
  warning fires.

**Patterns to follow:**
- Existing `logging` usage in `tools/visual_qa.py` (per global CLAUDE.md:
  use `logging` module, not `print()`).

**Test scenarios:**
- Happy path: capture invoked with the actual Atomic Habits PDF whose KFX
  exists in `output/kindle/` with author suffix → warning log entry contains
  both paths. This is the explicit motivating case.
- Happy path (simpler): capture with PDF input whose stem byte-exact-matches
  a KFX stem → warning fires.
- Happy path inverse: capture invoked with a PDF input whose normalized stem
  does not match any normalized KFX stem → no warning; capture proceeds
  silently.
- Edge case: capture invoked with a KFX input → no warning fires regardless
  of other files in the output directory.
- Edge case: the conventional output path is absent or empty → no warning;
  capture proceeds without raising.
- Edge case: multiple KFX files in `output/kindle/` normalize to the same
  string as the PDF input → warning fires, names all matches.
- Unit test for `_normalize_book_stem()` in isolation with 8+ inputs
  (underscored, author-suffixed, special-char, empty, already-normalized)
  confirming idempotency (`f(f(x)) == f(x)`).
- Integration: warning does not affect capture success or the emitted
  baseline JSON schema.

**Verification:**
- `pytest tests/test_pdf_kfx_warning.py` passes.
- Manual run: invoking `visual_qa.py` against the real Atomic Habits PDF
  (filename divergent from KFX) produces a visible warning in the log.

---

- [ ] **Unit 4: Archive old Atomic Habits baseline + re-capture from KFX (temp-promote protocol)**

**Goal:** Safely re-capture the Atomic Habits Claude baseline from the
KFX→Calibre path using a temp-promote sequence that avoids silent overwrites
and is rollback-recoverable if any step fails. Verifies both stem-parity (R9)
and sampled-pages parity (R4) using U1's audit.

**Requirements:** R2, R3, R4, R9 (R4 live-audit satisfaction lands here)

**Dependencies:** U1 (audit subcommand used for verification), U2
(`capture_pipeline` field must be written by the re-capture).

**Files:**
- Move: `data/vqa_baseline_post_274/Atomic Habits_ Tiny Changes, Remarkable Results_ An Easy & Proven Way to Build Good Habits & Break Bad Ones_visual_qa_report.json`
  → `data/vqa_baseline_post_274/.archive/<same-name>_pdf-source.json`
- Create: `data/vqa_baseline_post_274/<new-kfx-stem>_visual_qa_report.json`
  (produced by the re-capture run; exact stem determined by the KFX filename
  in `output/kindle/`)

**Approach (temp-promote, two-commit sequence):**

*Pre-flight (no git state changes):*
1. Verify the drifted baseline exists at the PDF-sourced stem in
   `data/vqa_baseline_post_274/`.
2. Verify exactly one Atomic Habits KFX exists in `output/kindle/`.
3. `grep -r` the repo for any hardcoded references to the OLD PDF-sourced
   baseline filename (`prompts/`, `docs/`, `tests/fixtures/`). Fix stale
   references before proceeding — this prevents dangling pointers after the
   rename.

*Step 1 — Capture to a temp path:*
4. Invoke `python tools/visual_qa.py --provider claude --input output/kindle/<Atomic Habits KFX> --output-dir /tmp/scrum-282-recapture/`
   (use a `--output-dir` flag or equivalent to direct the new baseline to a
   scratch path; if the current CLI does not support this, capture to a
   temp directory and move the file).
5. Verify the temp file's `capture_pipeline` field reads `"kfx-calibre"` and
   its `book` field ends in `.kfx`.
6. Run `python tools/compare_vqa_reports.py audit --baseline-dir /tmp/scrum-282-recapture/`
   (or feed the temp file through the audit subcommand's single-file mode).
   If audit reports mismatch or error, HALT — do not mutate the active
   baseline directory. Investigate before retrying.

*Step 2 — Commit the archive move (Commit A):*
7. `git mv data/vqa_baseline_post_274/Atomic\ Habits...Break\ Bad\ Ones_visual_qa_report.json data/vqa_baseline_post_274/.archive/Atomic\ Habits...Break\ Bad\ Ones_visual_qa_report_pdf-source.json`
8. Commit: `chore(scrum-282): archive PDF-sourced Atomic Habits baseline`.

*Step 3 — Commit the promote (Commit B):*
9. Move the validated temp file into `data/vqa_baseline_post_274/` at the
   KFX-derived stem.
10. Re-run `python tools/compare_vqa_reports.py audit` on the full active
    baseline directory; confirm exit 0.
11. Commit: `feat(scrum-282): re-capture Atomic Habits from KFX path`.

*Rollback:*
- After Commit A, before Commit B: if anything goes wrong, `git revert
  HEAD` restores the original baseline. No loss.
- After Commit B: if regression detected, `git revert HEAD~1..HEAD`
  restores both archive and original baseline atomically.
- Critical: do not combine archive + promote into a single commit. The
  two-commit split is the rollback guarantee.

**Patterns to follow:**
- `git mv` for the archive move so history tracks the rename.
- Temp-promote sequence borrowed from standard migration-safety protocols
  (validate in a scratch space, commit the old-version archive first, then
  promote the new version only after independent verification).

**Test scenarios:**
*Test expectation: none — this is a data/operational unit. Verification
happens via U1's audit on the re-captured baseline and the pre-flight grep
check for stale references.*

**Verification:**
- Pre-flight grep found zero or resolved all stale references to the old
  PDF-sourced baseline filename.
- After Commit A: archive subdir contains the PDF-sourced baseline
  (dot-prefixed, single file with `_pdf-source` suffix).
- After Commit B: new Atomic Habits baseline exists in
  `data/vqa_baseline_post_274/` at the KFX-derived stem with
  `"capture_pipeline": "kfx-calibre"`.
- `python tools/compare_vqa_reports.py audit` returns exit 0 on all 6
  baselines.
- Future smoke-run compare (existing `compare_vqa_reports.py` default mode)
  finds the new baseline by stem without manual aliasing.
- Any existing `output/kindle/Atomic Habits…_visual_qa_report.json` from
  prior smoke runs is not affected by this unit (smoke-run outputs live in
  `output/kindle/`, not in `data/vqa_baseline_post_274/`; re-capture targets
  only the baseline directory).

---

- [ ] **Unit 5: Backfill capture_pipeline + CLAUDE.md + feature-manifest**

**Goal:** Patch `capture_pipeline: "kfx-calibre"` onto the 5 in-parity
baselines (gated on U1 exit 0), document the KFX-only baseline rule in
`CLAUDE.md`, and register U1's new `audit` subcommand in `feature-manifest.json`.

**Requirements:** R6, R8

**Dependencies:** U1 (audit must have confirmed parity before backfill);
U4 (Atomic Habits must have the field set via re-capture, not backfill).

**Pre-flight gate:** do not execute this unit if `tools/compare_vqa_reports.py audit`
exits non-zero. If audit reports any mismatch on a non-Atomic-Habits baseline,
halt and investigate that baseline before proceeding with backfill on the
remaining books.

**Files:**
- Modify: 5 JSONs in `data/vqa_baseline_post_274/` (all except Atomic Habits —
  Decline of the West, Mexico Illicit, Oil Kings, Python in easy steps,
  Return of the Gods)
- Modify: `CLAUDE.md` (Visual QA System section, ~line 164)
- Modify: `feature-manifest.json` (new entry for `compare_vqa_reports.py`
  with `subcommands: ["compare", "audit"]`)

**Approach:**
- Patch each in-parity baseline JSON in place by adding
  `"capture_pipeline": "kfx-calibre"` adjacent to the existing `book` field.
  Do not touch any other field.
- In `CLAUDE.md` Visual QA section, add a terse rule: all Claude VQA
  baselines must be captured from the KFX→Calibre path, not original PDFs;
  reference the `capture_pipeline` field and the `audit` subcommand as the
  verification mechanism. Note explicitly that `capture_pipeline` is distinct
  from the existing `source_format` field in extraction-pipeline sidecars.
- Register the `compare_vqa_reports.py` tool path + `compare` / `audit`
  subcommands in `feature-manifest.json` following the multi-subcommand
  entry pattern; run `powershell -File tools/verify-manifest.ps1 -Verbose`
  to confirm no removed features.

**Patterns to follow:**
- Existing multi-subcommand entries in `feature-manifest.json`.
- CLAUDE.md project-specific rule tone — short imperative sentences.

**Test scenarios:**
- Happy path: all 5 patched baselines now include
  `"capture_pipeline": "kfx-calibre"`; `tools/compare_vqa_reports.py audit`
  still passes.
- Happy path: `CLAUDE.md` diff is scoped to the Visual QA section; the new
  rule references `capture_pipeline` and disambiguates from `source_format`.
- Integration: `powershell -File tools/verify-manifest.ps1 -Verbose` reports
  no removed features and the new `audit` subcommand is registered under
  `compare_vqa_reports.py`.

**Verification:**
- Diff of the 5 baseline JSONs shows only the new field.
- `verify-manifest.ps1` passes.
- `CLAUDE.md` Visual QA section contains the new rule; diff limited to that
  section.

## System-Wide Impact

- **Interaction graph:** `tools/visual_qa.py` (capture + new warning + new
  field in `build_report`), `tools/compare_vqa_reports.py` (smoke + new audit
  subcommand + import of 3 helpers from visual_qa.py), baseline JSONs (schema
  + data patch), `CLAUDE.md` (doc rule), `feature-manifest.json` (subcommand
  registry). Known downstream consumer: `tools/import_vqa_reports.py:92`
  reads VQA baselines and derives format from the `book` field's extension —
  unchanged by this plan. The existing `source_format` field in
  `tools/test_pipeline.py` / `tools/pattern_db.py` / `test-corpus/*.baseline.json`
  is unrelated to VQA baselines and untouched.
- **Error propagation:** The audit subcommand returns a non-zero exit code on
  any parity mismatch or skipped entry; existing CI or manual workflows that
  invoke `compare_vqa_reports.py` in default (compare) mode are unaffected.
  The capture-time warning is logged, not raised — it does not propagate to
  callers.
- **State lifecycle risks:** The U4 temp-promote protocol ensures the active
  baseline directory never has Atomic Habits missing between the archive and
  promote commits — the archive is visible to `compare_vqa_reports.py`
  (because `.archive/` is a subdir that the non-recursive glob skips) and the
  original baseline remains in place until promote. A crash or halt between
  archive and promote requires a `git reset --soft HEAD~1` to recover, which
  is standard.
- **API surface parity:** No public API surface. `capture_pipeline` is an
  additive JSON field distinct from the existing `source_format` field;
  downstream consumers of either are unaffected.
- **Integration coverage:** U1 and U4 exercise the end-to-end cross-layer
  behavior that unit tests alone cannot prove — fresh sampler output matches
  stored baseline arrays exactly, across both legacy-format and new-format
  baselines.
- **Unchanged invariants:** `select_sample_pages()` signature and determinism
  property, VQA rubric, `overall_score` / `pages[].score` calculations,
  `compare_vqa_reports.py` default smoke-comparison behavior, and the
  existing `source_format` field in extraction-pipeline sidecars. This plan
  strictly adds capabilities at the input layer and the schema edge.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| One or more of the 5 "in-parity" baselines fails U1's audit (Calibre-version drift or latent source drift). | Investigate before re-capturing. R6 backfill is explicitly gated on U1 exit 0 — a failure pauses U5 rather than stamping `"kfx-calibre"` onto an unverified baseline. The plan accepts that a failure extends scope to re-capture the affected book. Flag to user before auto-re-capture. |
| Calibre version drift between original baseline capture and current audit produces false-positive mismatches. | Accepted as a known failure mode per Scope Boundaries (no Calibre-version tracking in schema). When a mismatch occurs, operator re-runs the original baseline capture against the same KFX to confirm whether Calibre output has changed before re-capturing the Claude baseline. Adding a Calibre-version field remains a future option if this pattern recurs. |
| Re-capture of Atomic Habits produces a different filename stem than the KFX-based smoke run (breaks stem lookup in `compare_vqa_reports.py`). | The stem-parity guarantee is between the **new capture** and **future KFX-based smoke runs** — both derive from the same KFX filename via `visual_qa.py`'s `input_path.stem + "_visual_qa_report.json"` convention. The **old** PDF-sourced baseline stem will differ from the new KFX-sourced stem; that's expected and why R3 archives the old baseline rather than renaming it. U4 pre-flight grep catches any hardcoded references to the old stem. |
| U4 re-capture silently overwrites an existing `_visual_qa_report.json` from a prior smoke run in `output/kindle/`. | Not a risk: U4 captures with `--output-dir` pointing at a temp directory (not `output/kindle/`). The smoke-run outputs in `output/kindle/` are separate from the baseline directory and untouched by this plan. If the current CLI lacks `--output-dir`, implementer captures to a temp dir first and moves the file. |
| U4 re-capture fails mid-flight (Claude API outage, KFX file corruption). | Temp-promote protocol: re-capture writes to a scratch directory and is audit-verified before the archive commit. A failure halts the unit with no state change in `data/vqa_baseline_post_274/`. Commit A (archive) is reversible via `git revert`. |
| `capture_pipeline` field confused with the existing `source_format` field in extraction-pipeline sidecars. | Explicit naming (`capture_pipeline` vs `source_format`), distinct value ranges (`kfx-calibre/pdf-direct` vs `kfx/pdf/…`), CLAUDE.md rule documents both fields with their scopes. `tools/import_vqa_reports.py` is unchanged — it still derives format from `book` field extension, independent of either new or existing field. |
| Downstream consumer reads `capture_pipeline` without null-check and crashes on legacy baselines. | Additive-field pattern means legacy baselines load identically (field absent). No known consumer reads this field pre-implementation (it's new). If `tools/import_vqa_reports.py` is extended to read it, that change comes with its own null-check. |

## Documentation / Operational Notes

- `CLAUDE.md` Visual QA section gains the KFX-only baseline rule and a
  reference to `compare_vqa_reports.py audit`. The rule must disambiguate
  `capture_pipeline` (new VQA-baseline field, pipeline-branch provenance)
  from `source_format` (existing extraction-pipeline sidecar field,
  extension-derived).
- `feature-manifest.json` gains the `compare_vqa_reports.py` entry with
  `subcommands: ["compare", "audit"]`; verify with `verify-manifest.ps1`.
- No rollout gate required — changes are additive or data-layer. Worktree
  branch convention per project `worktree-policy.json`:
  `.worktrees/worktree-SCRUM-282-vqa-baseline-methodology`.
- After merge, update `data/vqa_baseline_post_274/` via `git add -A` including
  the `.archive/` subdir so the archived baseline is version-controlled.
- Commit ordering for U4: `chore(scrum-282): archive PDF-sourced Atomic Habits baseline`
  precedes `feat(scrum-282): re-capture Atomic Habits from KFX path`. Other
  units can land in any order; each is a standalone commit.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-04-20-scrum-282-vqa-baseline-methodology-requirements.md](../brainstorms/2026-04-20-scrum-282-vqa-baseline-methodology-requirements.md)
- **Jira:** SCRUM-282 (https://jlfowler1084.atlassian.net/browse/SCRUM-282)
- **Sibling compound-knowledge:**
  - `docs/solutions/scrum-280-local-vqa-calibration-patterns.md` — root-cause
    writeup; the field name this plan departs from (`source_format`) originates
    here.
  - `docs/solutions/scrum-281-fallback-fingerprint-routing.md` — additive-fields
    pattern + regression-fixtures pattern
  - `docs/solutions/scrum-283-cloud-vlm-evaluation.md` — related VQA routing
    context
- **Related code:**
  - `tools/visual_qa.py` (capture + sampler + helpers imported by U1)
  - `tools/compare_vqa_reports.py` (stem lookup + audit seam)
  - `tools/import_vqa_reports.py` (VQA-baseline downstream consumer)
  - `tools/test_pipeline.py`, `tools/pattern_db.py` (existing `source_format`
    field — out of scope, unchanged)
  - `data/vqa_baseline_post_274/` (baseline corpus)
- **Memory:** `project_vqa_baseline_source_format_drift.md` — user's standing
  note on this failure class.
