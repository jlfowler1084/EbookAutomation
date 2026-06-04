---
title: "feat: Header-bleed batch guard (detector + batch gate + corpus sweep)"
type: feat
status: active
date: 2026-06-04
origin: docs/superpowers/specs/2026-06-03-header-bleed-batch-guard-design.md
jira: EB-370
---

# feat: Header-bleed batch guard (detector + batch gate + corpus sweep)

## Overview

EB-367 fixed the project's most-recurring defect — short ALL-CAPS running headers
(e.g. `PILGRIM PEOPLE 73`) welded into body paragraphs by the page-boundary rejoin
pass (Pilgrim People: 310 welds → 0). This plan adds an **automated, deterministic
regression net** over that fix so the defect class cannot silently recur:

1. A reusable, read-only Python detector (`tools/check_header_bleed.py`) that scans
   the pipeline's intermediate `_kindle.html` for welded running headers.
2. A new **Phase 2.5** gate in the overnight batch runner that scans this-run output
   and warns loudly without blocking.
3. A scoped **corpus sweep** wrapper that re-extracts a trusted book set and scans it,
   doubling as the detector's calibration baseline.

## Problem Frame

The EB-367 fix is code-level and book-agnostic, but nothing verifies that future
conversions stay clean, and nothing audits already-converted books. Header bleed is a
*text-structure* defect — running-header text fused into a body `<p>`, sometimes
mid-word. The `_kindle.html` artifact (preserved at
`output/kindle/.intermediates/<name>_kindle.html`) is the last stage where the defect
is cheaply and deterministically detectable: plain `<p>` tags + raw text, no binary
KFX, no page-sampled VLM. This is the 5th encounter with this bug class (after EB-143,
EB-174, EB-212, SCRUM-299) — the recurrence is precisely why a standing guard is
justified (see origin: docs/superpowers/specs/2026-06-03-header-bleed-batch-guard-design.md).

## Requirements Trace

- **R1.** A pure-function detector over HTML that flags welded short ALL-CAPS running
  headers without knowing the header string a priori (origin Component 1; EB-370 AC1).
- **R2.** A CLI with tiered exit codes matching the VQA-audit convention
  (`0` clean / `1` nothing-scannable / `2` flagged / `3` infra-or-usage), JSON report
  output under `data/batch_reports/header_bleed/` (origin Component 2; AC1).
- **R3.** A batch gate (Phase 2.5) that scans this run's new-KFX HTML, warns + flags,
  never blocks, and makes the batch exit with an accumulated status (origin Component 3; AC2).
- **R4.** A corpus sweep that re-extracts the scoped PDF corpus + Pilgrim via
  `run_extraction()` (never `recapture_baselines.py`) and scans it (origin Component 4; AC3).
- **R5.** A calibration gate that is bidirectional and ungameable: deterministic,
  **zero** detections on the clean canaries, **positive** detection on a known-weld
  fixture (origin Component 4 + EB-355/EB-353 learnings; AC4).
- **R6.** Unit + calibration tests green under `python -m pytest tests/`;
  `feature-manifest.json` updated and `verify-manifest.ps1` passing (origin Component 5; AC5).
- **R7.** No pipeline behavior change — detector is strictly additive/read-only over
  intermediate artifacts; the extraction hot path is untouched (AC6; pre-implementation-render-check learning).

## Scope Boundaries

- Non-ALL-CAPS bleed classes (mixed-case, small-caps, author-name verso headers) — the
  detector is structured to extend here later, but v1 ships the EB-367 ALL-CAPS class only.
- No quarantine, auto-delete, or batch-blocking. Warn-loudly-never-block.
- No inline self-check inside `extract_tts_text.py` (origin Approach C) — kept off the
  regression-cascade surface deliberately.
- No changes to `config/settings.json` — thresholds are CLI flags, not config keys.

### Deferred to Separate Tasks

- **EPUB sweep coverage** (the Sherlock Holmes anchor): `run_extraction()` is
  PDF-oriented; EPUB books are covered by the forward batch gate on their next run.
  Future sweep extension.
- **Full ~87-book re-extraction audit**: broad coverage comes from the forward gate
  catching books on their next batch run, not an expensive one-time re-extraction.

## Context & Research

### Relevant Code and Patterns

- **Exit-code + JSON tool to mirror:** `tools/compare_vqa_reports.py` — audit-mode
  exit codes `0/1/2/3` (header comment ~lines 25-30), a dedicated `_compute_audit_exit_code()`
  helper so the JSON field and process return agree, pure `_render_*_json()` functions
  returning dicts, `@dataclass` + `asdict()` serialization, and the
  `logging`→stderr / `print()`→stdout split. **Caveat:** it does *not* override
  `parser.error()` (exits 2) — EB-370 must (see Key Technical Decisions).
- **Page anchor format (detector parse target):** `extract_tts_text.py` emits
  `<a id="page_N"></a>`. Filter anchor ids to `^page_(\d+)$` only — `endnote_`,
  `noteref_`, `footnote_` ids also exist.
- **A2 running-header filter (gate constants to borrow):** `extract_tts_text.py`
  `_mark_a2_running_headers` — `distinct_pages >= 5 AND distinct_pages/total_pages >= 0.10`.
  Borrow the density gate; **lower the 15-char length floor to 6** (the 15-char floor is
  the literal reason A2 missed "PILGRIM PEOPLE" = 14 chars).
- **Intermediate HTML write site:** `module/EbookAutomation.psm1` — copies the
  pipeline HTML to `output/kindle/.intermediates/${outName}_kindle.html` (Hidden dir).
- **Batch runner:** `tools/run_overnight_batch.ps1` — `$newKfx` set already computed
  (snapshot `$preExisting` then diff); `py -3.12` invocation pattern; `Write-Log`
  helper; Phase 2 (pipeline) → Phase 3 (VQA) seam; **no final exit today** (ends on
  summary `Write-Log` lines).
- **Extraction primitive for the sweep:** `tools/test_pipeline.py` `run_extraction(pdf_path, use_pdfminer=True, test_name="test")`
  → returns `(html_path, stdout, stderr)`, writes HTML under `output/kindle` (env
  `OUTPUT_DIR`-overridable), does **not** mutate baselines. `find_pdf()` and
  `_safe_test_name()` (in `tests/recapture_baselines.py`) reusable.
- **Corpus patterns:** `tests/recapture_baselines.py` `BOOK_PATTERNS` — 9 PDF books +
  Sherlock (EPUB, deferred). Pilgrim resolves from `archive/Pilgrim People - Anita Libman Lebeson (1950).pdf` (inbox fallback).
- **Test harness conventions:** `tests/test_eb367_header_bleed_html.py` and
  `tests/test_scrum_299_running_header_a2.py` — worktree-aware path resolution,
  `sys.path.insert(0, TOOLS_DIR)` + `# noqa: E402` imports, inline `pytest.skip()` for
  missing PDFs. **No pytest config file exists** → custom markers warn; use env-gated
  skip for slow calibration tests.
- **Manifest:** `feature-manifest.json` — `python_cli_modes[]` and `critical_files[]`
  catalogs; `tools/verify-manifest.ps1` only `Test-Path`-checks `python_cli_modes`
  scripts and line-count-checks `critical_files` (truncation tripwire).

### Institutional Learnings

- **`docs/solutions/eb367-running-header-bleed-html-path.md`** — the weld surface is
  `rejoin_html_fragments()`; scan **post-rejoin** HTML (where welds are observable);
  position not frequency is the fix's discriminator (unavailable in HTML — see Key
  Decisions); page-number adjacency is the prose-FP guard; rejoin-aware testing is
  mandatory (the first diagnosis was wrong from a shortcut test).
- **`docs/solutions/scrum-299-structural-widgets-as-body-content.md`** — the A2 density
  gate origin; **classify by glue position** (standalone vs glued-start/end/mid — only
  glued/mid are true welds); named FP canaries: Atomic Habits 85-char repeating line,
  Python in Easy Steps `window.mainloop()`.
- **`docs/solutions/eb361-vqa-grader-determinism-self-check-2026-06-02.md`** — run-twice
  determinism gate; gate on the decision metric, surface deeper signals non-blocking;
  a deterministic scanner passes trivially (risk-reducer, still worth proving).
- **`docs/solutions/eb353-vqa-grader-code-false-positive-2026-06-02.md`** & **`eb355-book-filer-classification-metadata-accuracy-2026-06-02.md`** —
  **the corpus is the arbiter, not logical completeness**; every heuristic clause is a
  new FP surface; whole-token matching not substring; document residual edge cases
  rather than over-fitting; make the gate **bidirectional/ungameable**.
- **`docs/solutions/eb-149-vqa-coverage-loss-surfacing.md`** & **`eb340-vqa-sweep2-findings-2026-06-01.md`** —
  separate "scanned" from "in batch"; a missing artifact is a loud coverage gap, never a
  silent pass; skip-and-warn rather than hard-fail; Windows `-LiteralPath` for filenames
  with `[...]`.
- **`docs/solutions/best-practices/pre-implementation-render-check-2026-04-22.md`** —
  additive read-only QA tooling is the endorsed safe pattern; do NOT touch the
  extraction hot path (keeps EB-370 off the regression-cascade surface).
- **`docs/decisions/ADR-EB-181-data-exemption-scope.md`** — only `data/batch_reports/**`
  and `data/debug/**` are worktree-exempt. A committed test fixture or a gate baseline
  that feeds an assertion is a **test fixture → must land via worktree branch + PR**.
  One-shot sweep evidence → `data/batch_reports/`.

### External References

- None. Internal Python (stdlib `html.parser`, `argparse`, `logging`) + PowerShell
  tooling with strong local patterns; no external research warranted.

## Key Technical Decisions

- **Detector scans post-rejoin `_kindle.html`, read-only.** That is where welds are
  observable, and it keeps the guard off the extraction hot path (R7;
  pre-implementation-render-check learning).
- **HTML-observable discriminators only.** The fix's `_margin_zone` signal is gone by
  the HTML stage, so the detector uses: a run of **2+ ALL-CAPS words** (letters +
  curly/straight apostrophes + hyphens), **±1–4 digit page-number adjacency**,
  **recurrence/density** (`distinct_pages >= 5 AND ≥10%`), and **normalized length
  `[6,40]`** (lower floor than A2's 15 — the EB-367 gap). The 2+-word rule structurally
  excludes the EXERCISE/SUMMARY/QUESTIONS single-word FP class.
- **Glue-position classification (precision upgrade over the spec).** Each `<p>` match is
  classified `standalone | glued-start | glued-end | mid-paragraph`. `weld_total` counts
  only glued-start/glued-end/mid-paragraph; `standalone` repeats go to an informational
  `standalone_repeats` bucket (a milder, different gap per SCRUM-299). This refines the
  spec's "any `<p>` containing the header."
- **`heading_repeats` bucket** (same density gate, on `<h*>`) stays informational —
  never touches `weld_total`/`status`.
- **Exit codes via a `_compute_exit_code()` helper** so the JSON `exit_code` field and
  the process return are guaranteed to agree; precedence `3 > 2 > 1 > 0`.
- **argparse override is net-new and required:** subclass `argparse.ArgumentParser` to
  make `error()` exit **3** (default is 2, which collides with "flagged").
- **Sensitivity fixture is synthetic, not git-archaeology.** A small, hand-crafted
  committed HTML fixture reproducing the EB-367 weld signature (PILGRIM PEOPLE welded
  into body `<p>` across ≥6 pages at ≥10% density) — deterministic, no PDF dependency,
  no fragile pre-fix checkout.
- **Coverage accounting in the batch gate.** The report records `books_in_batch` vs
  `artifacts_scanned` vs `artifacts_missing[]`. A new KFX whose `_kindle.html` is absent
  surfaces as a loud coverage gap (logged + in report), not a silent "0 welds" pass. v1
  treats coverage gaps as warnings (does not by itself drive a non-zero exit), to avoid
  blocking on benign `.intermediates` timing.
- **Calibration tests are env-gated (`RUN_CALIBRATION=1`), not marker-based** — the repo
  has no pytest marker config; an unregistered `@pytest.mark.slow` would only warn. Env
  skip mirrors the existing PDF-dependent skip pattern.
- **Implementation lands on a worktree branch + PR.** This is code + a committed test
  fixture (not docs/config) — per ADR-EB-181 and the global worktree policy.

## Open Questions

### Resolved During Planning

- *How to detect generically without the header string?* — Recurrence-geometry +
  ALL-CAPS + page-number adjacency + glue-position (Key Decisions).
- *Calibration test gating?* — Env-gated skip (`RUN_CALIBRATION=1`).
- *How to build the sensitivity fixture given the fix is already merged?* — Synthetic
  hand-crafted HTML fixture (Key Decisions).
- *Where do outputs/fixtures live under ADR-EB-181?* — Sweep evidence →
  `data/batch_reports/header_bleed/`; the committed sensitivity fixture is a test
  fixture → `tests/fixtures/` via worktree + PR.

### Deferred to Implementation

- Exact `html.parser` subclass structure and helper names.
- Final `min_lines` value for the `critical_files` manifest entry (set to ~80% of the
  actual final line count once the module is written).
- Whether any sweep book needs `_safe_test_name()` truncation (depends on resolved
  filenames at run time).

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not
> implementation specification. The implementing agent should treat it as context, not
> code to reproduce.*

Detection flow over one `_kindle.html`:

```
parse HTML (html.parser, tolerant)
  └─ walk elements, tracking current_page from <a id="page_N"></a>
  └─ for each <p>: extract text (strip inline <sup>/<em>/<a>)
       └─ find candidate = run of 2+ ALL-CAPS words (±1–4 digit page number)
       └─ normalize (strip page number, collapse ws, casefold)  e.g. "pilgrim people"
       └─ classify glue position within the <p>:
            whole <p> == candidate            → standalone
            candidate at start, more text after → glued-start   ┐
            candidate at end, text before       → glued-end      ├─ welds
            candidate surrounded by text        → mid-paragraph  ┘
  └─ for each <h*>: same candidate extraction → heading bucket

aggregate by normalized candidate:
  occurrences, distinct_pages (set), density = distinct_pages / total_pages,
  windowed samples (±~60 chars + page no.)

gate (a candidate is a WELD finding iff):
  distinct_pages >= 5  AND  density >= 0.10  AND  6 <= len(norm) <= 40
  AND has >=1 occurrence classified glued-start/glued-end/mid-paragraph

per-book result: { status, weld_total, total_pages,
                   findings[], standalone_repeats[], heading_repeats[] }
```

Exit-code decision (single book or directory aggregate):

| Condition | Exit |
|---|---|
| Bad args / unreadable / parse failure | 3 |
| ≥1 book has weld_total > 0 | 2 |
| Nothing scannable (no matching HTML at all) | 1 |
| All scanned books clean | 0 |

## Implementation Units

- [ ] **Unit 1: Detector core + CLI (`tools/check_header_bleed.py`)**

**Goal:** The reusable pure-function detector and its CLI — the heart of EB-370.

**Requirements:** R1, R2, R7

**Dependencies:** None.

**Files:**
- Create: `tools/check_header_bleed.py`
- Test: `tests/test_header_bleed_detector.py` (unit scenarios below)
- Create: `tests/fixtures/header_bleed_pilgrim_prefix.html` (synthetic weld fixture)
- Create: `tests/fixtures/header_bleed_clean.html` (synthetic clean fixture)

**Approach:**
- Pure functions: `detect(html: str, params) -> BookResult` (no I/O), plus thin file/dir
  wrappers. Parse with stdlib `html.parser`; track `current_page` from `id="page_N"`
  anchors; bucket `<p>`/`<h*>` to the most recent anchor.
- Candidate extraction, normalization, glue-position classification, density gate, and
  the `[6,40]` length floor per High-Level Technical Design and Key Decisions.
- `@dataclass` results + `asdict()` for JSON. Report envelope
  `header_bleed_report/v1`: `{schema, generated_utc, git_head_sha, params, summary, books[]}`.
  Reuse the `_git_head_sha()` / ISO-UTC timestamp patterns from `recapture_baselines.py`.
- CLI: `--input <file|dir>`, `--glob "*_kindle.html"`, `--out`, `--min-distinct-pages 5`,
  `--min-density 0.10`, `--len-min 6`, `--len-max 40`, `--quiet`, `--verbose`. Default
  `--out` → `data/batch_reports/header_bleed/<timestamp>.json` (`mkdir(parents=True, exist_ok=True)`).
- `_compute_exit_code()` helper; `main()` returns int; `sys.exit(main())`.
- Subclassed `ArgumentParser.error()` → exit 3.
- `logging`→stderr; human summary + JSON→stdout via `print()` (mirror `compare_vqa_reports.py`).
- Windows UTF-8 stdout/stderr reconfigure preamble.

**Execution note:** Test-first — write the synthetic-HTML unit scenarios (and commit the
two fixtures) before/alongside the detector so the gate semantics are pinned by tests.

**Patterns to follow:** `tools/compare_vqa_reports.py` (exit codes, JSON render, logging
split, dataclasses); `tests/test_eb367_header_bleed_html.py` (worktree path resolution,
tools import). Whole-token ALL-CAPS matching, never substring (EB-355).

**Test scenarios:**
- Happy path: header welded into body `<p>` across 6 pages at ≥10% density →
  `weld_total>0`, `status=flagged`, finding lists the candidate, occurrences, distinct_pages.
- Happy path: clean HTML (no recurring caps welds) → `weld_total==0`, `status=clean`, exit 0.
- Edge: candidate recurs but `<10%` density (Python-in-Easy-Steps shape, e.g. 5 of 260 pages)
  → **not** flagged.
- Edge: candidate is a single ALL-CAPS word (EXERCISE/SUMMARY/QUESTIONS) on many pages →
  **not** flagged (2+-word rule).
- Edge: 85-char repeating mixed-case body line (Atomic Habits canary) → not flagged (length + caps).
- Edge: `<p>PILGRIM PEOPLE 73</p>` standalone across pages → `standalone_repeats`
  populated, `weld_total==0` (glue-position classification).
- Edge: glued-start vs glued-end vs mid-paragraph each classified correctly and counted in `weld_total`.
- Edge: header recurring only as `<h*>` → `heading_repeats` populated, `weld_total==0`, status clean.
- Edge: curly-apostrophe candidate (e.g. `O'HALLORAN`-style) matched.
- Edge: page attribution with a boundary-rejoined paragraph → distinct-page count tolerates ±1.
- Edge: only non-`page_` anchors present (endnote_/footnote_) → `total_pages` falls back to distinct-anchor count.
- Error path: invalid CLI flag → exit **3** (not 2); unreadable file → exit 3;
  directory with no matching HTML → exit 1.
- Determinism: same input twice → identical `books[]`/`findings` (timestamp envelope excluded).

**Verification:** `python -m pytest tests/test_header_bleed_detector.py` green; running the
CLI on the committed synthetic weld fixture exits 2 and on the clean fixture exits 0; the
JSON `exit_code` field equals the process exit code in both.

---

- [ ] **Unit 2: Corpus sweep wrapper + calibration tests (`tools/sweep_header_bleed.ps1`)**

**Goal:** Re-extract the scoped trusted corpus, scan it with the detector, and enforce
the bidirectional calibration gate.

**Requirements:** R4, R5

**Dependencies:** Unit 1.

**Files:**
- Create: `tools/sweep_header_bleed.ps1`
- Create/extend: `tests/test_header_bleed_detector.py` (calibration class, env-gated)
- Reads: `archive/*.pdf` (read-only), writes HTML under `output/kindle` via `run_extraction()`

**Approach:**
- Sweep re-extracts the **9 PDF baseline books + Pilgrim** by invoking the existing
  `run_extraction()` primitive (via `py -3.12 tools/test_pipeline.py`-style call or a thin
  Python entry) — **never** `recapture_baselines.py` (mutates `expected_baselines.json`).
  Restrict to the 9 PDF `BOOK_PATTERNS` + Pilgrim; Sherlock EPUB excluded.
- Run from the main working tree (or set `OUTPUT_DIR` env override) — never junction data
  dirs into a worktree (CLAUDE.md data-loss warning). Use `-LiteralPath` for any filename
  with `[...]` (EB-340).
- Scan the produced HTML with `check_header_bleed.py`; write a sweep report under
  `data/batch_reports/header_bleed/`.
- **Calibration gate (bidirectional, ungameable):** determinism (two runs identical);
  **zero** weld findings on the clean canaries (Atomic Habits, Python in Easy Steps, +
  the other clean baseline books); **positive** detection on the synthetic Pilgrim-prefix
  weld fixture. Spot-check guidance: open 2–3 real hits against the actual HTML before
  trusting sweep output (CLAUDE.md calibration rule).

**Execution note:** Calibration tests env-gated behind `RUN_CALIBRATION=1` (skip
otherwise), mirroring the PDF-dependent skip pattern.

**Patterns to follow:** `tools/run_overnight_batch.ps1` (PowerShell header, `Write-Log`,
`py -3.12` invocation); `tests/recapture_baselines.py` `BOOK_PATTERNS` / `find_pdf` /
`_safe_test_name`; the EB-340 grounding-PASS + determinism-precondition discipline.

**Test scenarios:**
- Calibration (env-gated): detector run twice over the same fixture set → identical findings.
- Calibration (env-gated): clean canary fixtures/books → `weld_total==0` (zero false positives).
- Calibration (env-gated): synthetic Pilgrim-prefix weld fixture → flagged (sensitivity).
- Error path: a sweep book PDF missing from `archive/` → logged + skipped, sweep continues
  (skip-and-warn, not hard-fail).

**Verification:** `RUN_CALIBRATION=1 python -m pytest tests/test_header_bleed_detector.py`
green (determinism + zero-FP + sensitivity all pass); `tools/sweep_header_bleed.ps1`
produces a report and reports zero welds on the current (post-EB-367) corpus.

---

- [ ] **Unit 3: Batch gate — Phase 2.5 + status accumulator (`tools/run_overnight_batch.ps1`)**

**Goal:** Wire the detector into the overnight batch as a non-blocking gate, with coverage
accounting and a real final exit code.

**Requirements:** R3, R7

**Dependencies:** Unit 1.

**Files:**
- Modify: `tools/run_overnight_batch.ps1`

**Approach:**
- Insert **Phase 2.5** between Phase 2 (pipeline) and Phase 3 (VQA). Resolve
  `$intermediatesDir = Join-Path $OutputDir '.intermediates'`. Map each `$newKfx`
  `BaseName` → `<BaseName>_kindle.html` (use `Join-Path` + `-LiteralPath`) so only this
  run's output is scanned.
- Invoke `py -3.12 tools/check_header_bleed.py --input <files/dir> --out <data/batch_reports/header_bleed/...>`;
  capture `$LASTEXITCODE`; stream output through `Write-Log` with an `[HB]` tag.
- **Coverage accounting:** record `books_in_batch` (= `$newKfx.Count`) vs
  `artifacts_scanned` vs `artifacts_missing`; log any new KFX with no `_kindle.html` as a
  loud `WARN` coverage gap (EB-149) — never a silent pass.
- Log flagged book names prominently in the summary block.
- **Status accumulator:** initialize `$batchStatus = 0`; a `Set-Status` step folds each
  phase's code with precedence `3 > 2 > 1 > 0` (`if ($code -gt $batchStatus) { $batchStatus = $code }`);
  fold in the Phase 2 pipeline catch and Phase 3 VQA failures deliberately; add
  `exit $batchStatus` as the **last line** after the summary. Never abort mid-run.

**Patterns to follow:** existing `$preExisting`/`$newKfx` snapshot-diff; `Write-Log`;
the `py -3.12` + `$LASTEXITCODE` VQA invocation block.

**Test scenarios:** `Test expectation: none (orchestration script)` — the detector logic
is covered by Unit 1's pytest suite; this unit's correctness is verified by manual
dry-run (below). No new behavioral Python surface is introduced here.

**Verification:** A dry-run of the batch over a small inbox produces a Phase 2.5 report,
logs flagged/coverage lines, and the script exits with the accumulated status
(`echo $LASTEXITCODE`): `0` clean, `2` when a known-weld book is present, `3` on a
detector infra error. A clean run still completes all phases (never aborts).

---

- [ ] **Unit 4: Manifest registration + regression verification (`feature-manifest.json`)**

**Goal:** Catalog the new tool so the manifest/truncation guard covers it and the
regression check stays green.

**Requirements:** R6

**Dependencies:** Unit 1 (final line count known).

**Files:**
- Modify: `feature-manifest.json`

**Approach:**
- Add a `python_cli_modes[]` entry for `tools/check_header_bleed.py` (script, `mode: "direct"`,
  `flags[]`, description).
- Add a `critical_files[]` entry (`path`, `type: "python_script"`, `min_lines` ≈ 80% of the
  final line count — a truncation tripwire, not an exact match).
- Leave `config_schema_keys` and `test_infrastructure` unchanged (no new settings keys; the
  pytest file is not cataloged in `test_infrastructure`).

**Patterns to follow:** the existing `compare_vqa_reports.py` `python_cli_modes` entry and
the `critical_files` shape.

**Test scenarios:** `Test expectation: none (manifest data)` — validated by the verify
script, not pytest.

**Verification:** `powershell -File tools\verify-manifest.ps1 -Verbose` exits 0 (the new
script is found and above its `min_lines`); JSON remains valid (`ConvertFrom-Json` clean).

## System-Wide Impact

- **Interaction graph:** New Phase 2.5 sits between the pipeline and VQA phases in
  `run_overnight_batch.ps1`; it consumes `.intermediates/*_kindle.html` and writes a
  report. No call into `extract_tts_text.py` or the module hot path.
- **Error propagation:** Detector errors → exit 3 → folded into `$batchStatus` (precedence
  `3 > 2 > 1 > 0`); the batch never aborts on a detector or coverage problem (skip-and-warn).
- **State lifecycle risks:** Scans only this-run `$newKfx` stems → no stale-intermediates
  contamination. Read-only over artifacts → no partial-write/cleanup risk.
- **API surface parity:** Exit-code semantics intentionally match `compare_vqa_reports.py audit`
  and `vqa_determinism_check.py` so existing automation reads EB-370 the same way.
- **Integration coverage:** The detector↔pipeline contract (anchor format
  `<a id="page_N">`, `${outName}_kindle.html` naming, `.intermediates` location) is the
  cross-layer seam — covered by the corpus sweep (Unit 2) running real extraction, not just
  synthetic unit fixtures.
- **Unchanged invariants:** `extract_tts_text.py` marking/rejoin logic, `config/settings.json`
  schema, `expected_baselines.json`, and all existing pipeline outputs are untouched (R7).

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| New heuristic clause introduces a false positive (EB-353 lesson: logically-sound rules empirically regress canaries) | Corpus is the arbiter: every threshold validated against the clean canaries + known-weld fixture; revert any rule that creates a new FP even if sound. |
| Detector silently passes a book whose `_kindle.html` was never produced (EB-149 silent coverage loss) | Coverage accounting in the batch gate: `books_in_batch` vs `artifacts_scanned` + loud `WARN` on missing artifacts. |
| Margin-zone signal (the fix's discriminator) unavailable in HTML → weaker discrimination | Compensate with 2+-word + page-number-adjacency + density + glue-position; framed as a regression net over the fix, not a reimplementation. Documented residual edge cases rather than over-fitting. |
| Windows filename foot-guns (`[...]` wildcards, metadata-vs-source naming) in artifact matching (EB-340) | Match by `$newKfx.BaseName` → `${BaseName}_kindle.html`; use `-LiteralPath`. |
| Sweep writes into `output/kindle` and could clobber real output / data-loss via worktree junctions | Run sweep from main working tree or set `OUTPUT_DIR`; never junction data dirs into a worktree (CLAUDE.md). |
| Calibration non-determinism (paragraph iteration ordering) | Deterministic by construction (no LLM); run-twice gate proves it cheaply. |
| Fixture/output placement violates ADR-EB-181 | Sensitivity fixture = test fixture → `tests/fixtures/` via worktree + PR; sweep evidence → `data/batch_reports/header_bleed/`. |

## Documentation / Operational Notes

- After landing, compound a `docs/solutions/` entry (per the CE cycle) capturing the
  detector heuristic, the glue-position classification, and the calibration protocol — this
  would be the first doc on the header-bleed *guard* (the lineage docs cover the *fixes*).
- Implementation runs on a worktree branch (`feat/EB-370-header-bleed-batch-guard`) and
  lands via PR — code + committed fixture, not docs/config (ADR-EB-181 + worktree policy).
- The design spec was already committed direct-to-master (docs) at `15f6f98`.

## Sources & References

- **Origin document:** [docs/superpowers/specs/2026-06-03-header-bleed-batch-guard-design.md](../superpowers/specs/2026-06-03-header-bleed-batch-guard-design.md)
- Jira: EB-370 (relates to EB-367)
- Related code: `tools/compare_vqa_reports.py`, `tools/run_overnight_batch.ps1`,
  `tools/test_pipeline.py` (`run_extraction`), `tools/extract_tts_text.py`
  (`_mark_a2_running_headers`, page anchors), `module/EbookAutomation.psm1` (`.intermediates`),
  `tests/test_eb367_header_bleed_html.py`, `feature-manifest.json`, `tools/verify-manifest.ps1`
- Related solutions: `docs/solutions/eb367-running-header-bleed-html-path.md`,
  `scrum-299-structural-widgets-as-body-content.md`,
  `eb361-vqa-grader-determinism-self-check-2026-06-02.md`,
  `eb353-vqa-grader-code-false-positive-2026-06-02.md`,
  `eb-149-vqa-coverage-loss-surfacing.md`,
  `best-practices/pre-implementation-render-check-2026-04-22.md`
- ADR: `docs/decisions/ADR-EB-181-data-exemption-scope.md`
