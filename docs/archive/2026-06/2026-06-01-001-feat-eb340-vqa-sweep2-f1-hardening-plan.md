---
title: "feat(EB-340): VQA stress sweep #2 (Lane A) + F1 coverage-accounting hardening"
type: feat
status: active
date: 2026-06-01
origin: docs/superpowers/specs/2026-06-01-eb340-vqa-stress-sweep2-design.md
---

# feat(EB-340): VQA stress sweep #2 (Lane A) + F1 coverage-accounting hardening

## Overview

Two coupled deliverables, anchored to **EB-340**:

1. **F1 coverage-accounting hardening** in `tools/visual_qa.py` — make the large-file
   DPI/page reduction **non-silent** by recording requested-vs-effective coverage in the
   report, reusing and extending the existing EB-149 `coverage_status` schema. This is the
   honest-accounting half of the tiered-VQA "coverage accounting" section, scoped to the
   interim EB-347 guard. **The streaming chunker is out of scope** (EB-148, prereq EB-342).
2. **Lane A breadth sweep** — a $0 local-VQA sweep over ~25–30 diverse books to surface new
   conversion-quality patterns and produce *causal* A/B evidence that the PR #167/#168 fixes
   (EB-347 override, EB-348 `<pre>`/CID, EB-349 OCR escalation) moved the known failure cases.
   Output: a findings doc in `docs/solutions/` + new tickets.

Lanes B (OCR-escalation validation) and C (Claude fallback-cost probe) are **documented
follow-up blocks** in the origin spec and are **not** planned here. The plan notes Lane B's
classifier-handoff code prerequisite as that follow-up's gating item.

## Problem Frame

The 2026-05-29 EB-340 sweep #1 (`docs/solutions/eb340-full-vqa-batch-findings-2026-05-29.md`)
proved the local R9700 Qwen3-VL endpoint makes VQA effectively free and surfaced real patterns
the cost-limited 8-page sample never saw — chiefly **F1**: `_apply_large_file_dpi_reduction`
silently collapses books >30 MB or >500 pages to 4 pages @ 72 DPI, making their scores
meaningless (p11=54 and p12=96 each from ~4 of 600–900 pages). EB-347 since made *explicit*
`--dpi`/`--max-pages` flags override the collapse, but the **default/batch path still collapses
silently**, and the report does not record that coverage was reduced. We want (a) the report to
tell the truth about coverage, and (b) a second, broader sweep to find new patterns and prove
the PR #167/#168 fixes worked — with the global CLAUDE.md calibration discipline applied before
any number is trusted.

## Requirements Trace

- **R1** — Report records requested-vs-effective coverage: add `pages_requested`,
  `requested_dpi`, `effective_dpi`, `coverage_reason`; reuse `coverage_status`. (spec §"Minimal
  F1 hardening")
- **R2** — A **default**-path large-file reduction sets `coverage_status: partial` +
  `coverage_reason` and emits a `logger.warning` (not `info`). Explicit-flag runs report
  `coverage_status: complete` with honored DPI/pages. (spec §"Minimal F1 hardening", §Testing)
- **R3** — New fields are **additive** and backward-compatible for existing report consumers
  (CLI summary, DB persistence, sweep summary projection). (SCRUM-281 additive rule)
- **R4** — Lane A sweep runs $0 local-only with explicit `--dpi 150 --max-pages 50
  --fallback-enabled false`; server `n_ctx ≥ 32k` verified first; skip-and-warn on node down.
  (spec §"Lane A")
- **R5** — Reproducibility manifest per the spec schema (git SHA, commands, config blocks,
  provider/model/base-URL, n_ctx, per-book sha256/pages/size/format/AZW3-fallback/coverage).
  (spec §"Reproducibility snapshot")
- **R6** — Calibration gate (run-twice determinism, known-good canary, spot-check 2–3
  findings/class) passes **before** findings are recorded; cross-book patterns reported
  separately from grader artifacts. (spec §"Calibration / trust gate"; global CLAUDE.md)
- **R7** — Artifact-based A/B reruns (`<pre>` count, `(cid:N)` count, `text_integrity`,
  spot-checked pages) for 2–3 sweep-#1 books; overall score is not the evidence. (spec §"A/B
  rerun protocol")
- **R8** — Outputs: findings doc in `docs/solutions/` + new tickets for spot-checked real
  defects; updated EB-340 decision input (local-only/no-fallback scope). (spec §"Outputs")

## Scope Boundaries

- No streaming render→eval→release chunker / full per-page coverage.
- No changes to rubric content or the converge-loop algorithm.
- No new vision provider; reuse the EB-339 local provider.
- No modification of the production `tools/run_overnight_batch.ps1` or
  `module/EbookAutomation.psm1 › Test-ConversionQuality` — the sweep uses a standalone runner.
- No new `config/settings.json` key for F1 (thresholds stay module constants), so no
  config-round-trip wiring is introduced.

### Deferred to Separate Tasks

- **Lane B — OCR-escalation validation** (separate follow-up execution block): gated on a
  **code prerequisite** — the CLI does not pass `classifier_verdict` into `process_kindle_html`
  (`tools/extract_tts_text.py`), so the EB-349 auto-Gemini branch never fires from a bare
  `Convert-ToKindle -NoCache`; and only `needs_paid_tier=gemini` verdicts qualify. Requires a
  classifier handoff + an env override for the toggle before it can validate anything.
- **Lane C — Claude fallback-cost probe** (separate follow-up execution block): gate on
  "fallback fired" (token fields present), not non-zero cost.
- **Streaming chunker / full per-page coverage** → EB-148 (execution), prereq EB-342 (tiering +
  3-way coverage accounting).

## Context & Research

### Relevant Code and Patterns

- `tools/visual_qa.py`
  - `build_report(book_path, qa_data, total_pages, pages_sampled, dpi, model, input_tokens,
    output_tokens, provider=None, pass_threshold=70, fallback_tokens=None, ...,
    capture_pipeline=None, truncation_events=None)` — single report-dict literal; **already**
    computes `pages_evaluated` and `coverage_status` (`complete`/`partial`, EB-149). New fields
    insert into the same dict.
  - `_apply_large_file_dpi_reduction(kfx_size_bytes, total_pages, dpi, max_pages,
    user_supplied_dpi=False, user_supplied_max_pages=False) -> (dpi, max_pages)` — reduces on
    `size>30MB or pages>500` when not user-supplied; constants `_LARGE_FILE_*` directly above.
  - `run_visual_qa(...)` call site reassigns `dpi, max_pages` in place from the reduction, then
    calls `build_report(..., len(page_images), dpi, ...)` — so **rendered** and **effective**
    values reach the report; requested values are lost unless snapshotted at the call site.
  - `main()` derives `user_supplied_dpi = any(a.startswith('--dpi') for a in sys.argv)` /
    `user_supplied_max_pages`, threaded through `run_visual_qa`. The stdout summary block reads
    `report["pages_sampled"]` / `report["pages_total"]` — keep those keys stable.
- `docs/solutions/eb-149-vqa-coverage-loss-surfacing.md` — the schema precedent: `pages_sampled`
  (sent) vs `pages_evaluated` (valid), `coverage_status` intentionally broader than any single
  cause, typed `truncation_events[]` names the specific cause. **Extend this**, don't fork it.
- Sweep harness precedent: `logs/eb340-full-vqa-2026-05-29/run-sweep.ps1` (+ `run-vqa.ps1`) —
  phased `-Phase Convert|VQA|Both`; sets `$env:LOCAL_LLM_BASE_URL` / `$env:LOCAL_LLM_VISION_MODEL`;
  reads `manifest.json` (`{id,type_axis,classification,source_path,mb,pages}`), rewrites
  `run-summary.json` after each book (interruption-safe); VQA call:
  `py -3.12 tools/visual_qa.py --input <kfx> --provider local --fallback-enabled false
  --dpi <n> --max-pages <n> --output-dir <dir>`.
- Test homes: `tools/test_visual_qa_evaluation_status.py` (`unittest`; `FakeProvider.estimate_cost
  -> 0.0`; `_minimal_report(qa_data)` helper calling `build_report`) for report-field assertions;
  `tools/test_visual_qa_retry.py` (`TestLargeFileDpiReduction*`; `with self.assertLogs("visual_qa",
  level="WARNING") as cm: ... self.assertIn("EB-347", "\n".join(cm.output))`) for the
  default-reduction warning test.

### Institutional Learnings

- **Calibration discipline is already measured** (`docs/solutions/eb340-full-vqa-batch-findings-2026-05-29.md`,
  `scrum-280-local-vqa-calibration-patterns.md`): determinism ±1 overall / ±10 per-page;
  grounding PASS (grader reads real content); mode (a) score inflation + mode (b) detection
  failure carry equal weight; dedupe per-page criticals; weight category scores over raw counts.
  Trust cross-book patterns only.
- **Counter-measurement before "it's noise"** (`docs/solutions/best-practices/verify-tool-dependent-hypotheses-before-shipping-diagnosis-2026-05-15.md`):
  any "grader artifact" claim must run the re-score / spot-check before being reported.
- **Additive report fields only** (`scrum-281-fallback-fingerprint-routing.md`); **grep a new
  field name before ratifying** (`scrum-282-vqa-baseline-methodology.md` — `source_format`
  collision precedent); **severity enum is exactly `{critical, moderate, minor}`**.
- **Test double-import trap** (`eb-149-vqa-coverage-loss-surfacing.md`): import via
  `from llm_providers...`, never `from tools.llm_providers...` (breaks `isinstance`).
- **EB-181 data discipline**: VQA baseline files are gitignored / land via PR; this plan does
  not touch `data/vqa_baseline_*` (no re-baseline here).

### External References

None required — the work follows strong existing local patterns.

## Key Technical Decisions

- **Reuse `coverage_status`, disambiguate with `coverage_reason`.** `coverage_status` already
  exists (EB-149) and is intentionally broad ("any coverage gap"). The large-file default
  reduction sets `coverage_status: partial` and a new `coverage_reason` string names the cause
  (e.g. `"large_file_default_reduction"`), parallel to how `truncation_events[]` names the
  truncation cause. *Alternative considered:* a typed `coverage_reductions[]` event array
  (closer to EB-149's `truncation_events`); rejected for now as over-built for a single cause —
  a `coverage_reason` string plus the requested/effective fields carries the same information.
- **Capture requested values at the reduction call site (Option B, non-breaking).** Snapshot
  `requested_dpi`/`pages_requested` before `_apply_large_file_dpi_reduction` reassigns `dpi`/
  `max_pages`, and thread them into `build_report` as new params. *Alternative:* change the
  function to return a 3-tuple with the reason — rejected because it breaks the 2-tuple unpacking
  in `tools/test_visual_qa_retry.py` (8+ sites) and the `run_visual_qa` call site.
- **Additive, omitted-when-not-applicable fields.** `effective_dpi` is always present (= the
  post-reduction `dpi`); `requested_dpi`/`pages_requested` always present (snapshot);
  `coverage_reason` present only when a reduction/truncation actually changed coverage (else
  `null`/omitted) — preserves backward-compat per SCRUM-281.
- **Field-name pre-flight.** Grep the repo for `pages_requested`, `requested_dpi`,
  `effective_dpi`, `coverage_reason` before ratifying, per SCRUM-282.
- **Sweep uses explicit flags, so F1's *partial* branch won't fire during the sweep** — but the
  new requested/effective fields make the manifest's requested-vs-effective columns first-class,
  and the large/long A/B book confirms explicit override → `coverage_status: complete`.

## Open Questions

### Resolved During Planning

- *Is `coverage_status` new?* No — EB-149 added it; extend it. (research finding)
- *Change the reduction return tuple?* No — Option B snapshots at the call site to stay
  non-breaking.
- *New config key for F1 thresholds?* No — keep module constants; avoids config-round-trip
  surface this session.
- *Which planner?* `ce:plan` per global CLAUDE.md (writing-plans is legacy).

### Deferred to Implementation

- Exact `coverage_reason` string value(s) and whether `null` vs omitted when no reduction — pick
  during implementation to match the existing `truncation_events` omission style.
- Final corpus list (specific 22–27 fresh titles + 2–3 reruns) — selected at sweep time from
  `F:\Books` via `classify_source.py`, recorded in the manifest.
- Whether the large/long A/B F1 book renders cleanly at `--max-pages 50 --dpi 150` without
  memory pressure — an execution-time observation (streaming is explicitly deferred).

## Implementation Units

- [ ] **Unit 1: F1 coverage-accounting fields in `build_report` + run_visual_qa**

**Goal:** Record requested-vs-effective coverage in the report; set `coverage_status: partial` +
`coverage_reason` when a **default** large-file reduction fires; emit a `logger.warning`.

**Requirements:** R1, R2, R3

**Dependencies:** None

**Files:**
- Modify: `tools/visual_qa.py` (`build_report` signature + report dict; `run_visual_qa` call
  site snapshots requested values and detects default-driven reduction)
- Test: `tools/test_visual_qa_evaluation_status.py`

**Approach:**
- In `run_visual_qa`, snapshot `requested_dpi = dpi` and `pages_requested = max_pages` (or the
  resolved requested sample count) **before** calling `_apply_large_file_dpi_reduction`.
- After the call, compute `effective_dpi = dpi` (post-reduction). Detect a default-driven
  reduction as: `is_large and (not user_supplied_dpi or not user_supplied_max_pages) and
  (effective_dpi < requested_dpi or effective_max < pages_requested)`. When true, set
  `coverage_reason = "large_file_default_reduction"`.
- Thread `pages_requested`, `requested_dpi`, `effective_dpi`, `coverage_reason` into
  `build_report` as new keyword params (defaulting to non-breaking values).
- In `build_report`, add the four fields to the report dict (additive). Keep existing
  `pages_sampled`/`pages_total`/`coverage_status` keys stable. When `coverage_reason` indicates
  a reduction, ensure `coverage_status` resolves to `"partial"` (reconcile with the existing
  evaluated-vs-sampled computation — `partial` wins if either signals a gap).
- Pre-flight grep the four field names for collisions before finalizing.

**Patterns to follow:** EB-149 `coverage_status`/`pages_evaluated` block in `build_report`;
additive-field rule (SCRUM-281); severity enum untouched.

**Test scenarios:**
- Happy path: `build_report` with explicit-flag inputs (requested == effective) → report has
  `pages_requested`, `requested_dpi`, `effective_dpi` equal to inputs, `coverage_reason` null,
  `coverage_status: complete`.
- Edge case: requested DPI/pages > effective (simulated default reduction) → `effective_dpi` <
  `requested_dpi`, `coverage_reason == "large_file_default_reduction"`, `coverage_status:
  partial`.
- Edge case: small file (not large) → no reduction, `coverage_reason` null, fields equal.
- Backward-compat: a report consumer reading only legacy keys still finds `pages_sampled`,
  `pages_total`, `coverage_status` unchanged in meaning for the non-reduced case.

**Verification:** Report JSON for an explicit-flag run shows `coverage_status: complete` and
honored `effective_dpi`; a simulated default reduction shows `partial` + `coverage_reason`.

- [ ] **Unit 2: Default-reduction WARNING + partial-status regression test**

**Goal:** Lock in that a **default** (non-user-supplied) large-file reduction is non-silent —
emits a `logger.warning` and produces `coverage_status: partial`.

**Requirements:** R2

**Dependencies:** Unit 1

**Files:**
- Modify: `tools/visual_qa.py` (ensure the default-path branch in
  `_apply_large_file_dpi_reduction` logs at `warning` level for the coverage-reduction message,
  or that the call-site detection logs the warning — choose the site that keeps the function's
  2-tuple return contract intact)
- Test: `tools/test_visual_qa_retry.py`

**Approach:**
- Mirror `TestLargeFileDpiReductionUserSupplied`'s `assertLogs` idiom but for the **default**
  path: assert a `WARNING` is emitted naming the coverage reduction, distinct from the existing
  `info` SCRUM-319 message (or upgraded to warning). Keep the existing 2-tuple unpacking
  assertions intact (Option B — no return-contract change).

**Patterns to follow:** `with self.assertLogs("visual_qa", level="WARNING") as cm: ... assertIn`.

**Test scenarios:**
- Edge case: large file, neither flag user-supplied → reduction fires, a `WARNING` is logged
  mentioning coverage reduction; returned tuple still `(72, 4)`-style clamp.
- Edge case: large file, both flags user-supplied → no clamp, existing EB-347 warning path
  unchanged (no new coverage-reduction warning).
- Regression: existing `TestLargeFileDpiReduction*` 2-tuple assertions still pass unchanged.

**Verification:** `python -m pytest tools/test_visual_qa_retry.py
tools/test_visual_qa_evaluation_status.py` green; full `python -m pytest tests/` shows no new
failures beyond the known pre-existing `test_clean_read_profile`.

- [ ] **Unit 3: Lane A sweep runner + reproducibility manifest**

**Goal:** A standalone, interruption-safe runner that converts a corpus and runs $0 local VQA
with explicit flags, writing the spec's reproducibility manifest — without touching the
production batch.

**Requirements:** R4, R5

**Dependencies:** Unit 1 (so reports carry the new coverage fields the summary projects)

**Files:**
- Create: `logs/eb340-sweep2-2026-06-01/manifest.json` (corpus + per-book source metadata)
- Create: `logs/eb340-sweep2-2026-06-01/run-sweep.ps1` (adapted from the sweep-#1 runner)
- Create: `logs/eb340-sweep2-2026-06-01/run-summary.json` (generated; per-book results)

**Approach:**
- Adapt `logs/eb340-full-vqa-2026-05-29/run-sweep.ps1`: `#Requires -Version 7.0`; phased
  `Convert|VQA|Both`; set `$env:LOCAL_LLM_BASE_URL` (`http://192.168.1.33:8080/v1`) and
  `$env:LOCAL_LLM_VISION_MODEL`; **pre-flight check server `n_ctx ≥ 32k`** (query
  `/v1/models` or the server props) and **abort with a clear message** if not; **skip-and-warn**
  per book if the node is unreachable.
- Convert: `Convert-ToKindle -InputFile <pdf> -OutputDir <kfx> -NoCache`. VQA: explicit
  `--provider local --fallback-enabled false --dpi 150 --max-pages 50 --output-dir <dir>`.
- Manifest records run-wide (git SHA, exact commands, `visual_qa`/`classifier_escalation`/
  `ocr_escalation`/`converge_loop` config blocks, provider/model/base-URL, confirmed n_ctx) and
  per-book (source path + **sha256**, page count, file size, classify result, output format +
  **AZW3-fallback flag**, conversion warnings, the new VQA coverage fields, category scores,
  token/$ — expected $0 for Lane A).
- Carry forward sweep-#1 harness fixes: KFX named from metadata (match output by title–author,
  not source stem); use `-LiteralPath` for `[...]`-bracketed filenames.

**Execution note:** This unit creates the runner + manifest; the **sweep run itself** is Unit 4.

**Patterns to follow:** `logs/eb340-full-vqa-2026-05-29/run-sweep.ps1` (env vars,
`Save-Summary` interruption-safety, report-field projection); `powershell-windows` skill
conventions (UTF-8, no em-dashes, no bash `&`).

**Test scenarios:** `Test expectation: none — operational runner + data artifacts (no
behavioral unit under test). Validated by Unit 4 execution (dry-run on 1 book first).`

**Verification:** A 1-book dry run produces a KFX, a `_visual_qa_report.json` with the new
coverage fields, and a `run-summary.json` row; manifest has all required per-book fields incl.
sha256 and git SHA; aborts cleanly if n_ctx < 32k or node down.

- [ ] **Unit 4: Calibration gate, breadth sweep + A/B reruns, findings doc**

**Goal:** Run the validated sweep, separate real findings from grader artifacts, and produce the
EB-340 sweep-#2 findings doc + new tickets.

**Requirements:** R6, R7, R8

**Dependencies:** Units 1–3

**Files:**
- Create: `docs/solutions/eb340-vqa-sweep2-findings-2026-06-01.md`
- Modify: `logs/eb340-sweep2-2026-06-01/run-summary.json` (populated by the run)

**Approach:**
- **Calibration gate first (R6):** (1) run-twice determinism on one book — expect ±1 overall;
  flag if worse. (2) Known-good canary — re-run a clean digital book (sweep-#1 `p01` two-col CS
  @ 91 or `p07` academic @ 93 are the baselines); any real critical is a grader artifact,
  recorded as such. (3) Spot-check 2–3 findings per failure-class against rendered pages before
  anything enters the findings doc.
- **Breadth sweep (R4):** ~22–27 fresh `F:\Books` titles by technical type + 2–3 sweep-#1
  reruns.
- **A/B reruns (R7):** for 1 code/math book, 1 scan/OCR book, optionally 1 large/long F1 book —
  compare `<pre>` count (↑ good), `(cid:N)` count (↓ good), `text_integrity` category, and
  spot-checked rendered pages against the sweep-#1 baseline. A fix "moved the needle" only if
  the artifact metric changed in the right direction on the spot-checked pages.
- **Findings doc (R8):** model on the sweep-#1 doc — issue taxonomy, cross-book patterns, A/B
  artifact deltas, and a **separate grader-artifact section**. Scope the EB-340 decision input
  explicitly to **local-only/no-fallback** (Lanes B/C answer the rest). File new tickets for
  each spot-checked real defect.

**Execution note:** Counter-measurement discipline — any "grader noise" claim must run the
re-score/spot-check before being reported; trust cross-book patterns, not single page scores or
single criticals.

**Patterns to follow:** `docs/solutions/eb340-full-vqa-batch-findings-2026-05-29.md` structure
and harness/calibration-notes section.

**Test scenarios:** `Test expectation: none — investigative execution + documentation. The
"tests" are the calibration gate (determinism re-run, canary, spot-check) enumerated above; no
code unit is under test.`

**Verification:** Findings doc committed with calibration-gate results shown, real findings
separated from grader artifacts, A/B artifact deltas tabulated; new tickets filed; manifest +
summary complete and reproducible (git SHA + sha256 recorded).

## System-Wide Impact

- **Interaction graph:** `build_report` is consumed by the `main()` stdout summary (reads
  `pages_sampled`/`pages_total`), DB persistence in `module/EbookAutomation.psm1`, and the sweep
  `run-summary.json` projection. New fields are additive; existing keys unchanged.
- **Error propagation:** sweep runner is skip-and-warn per book; a VQA/conversion failure
  records `partial`/error in the summary, never aborts the whole run (except the deliberate
  pre-flight n_ctx abort).
- **State lifecycle risks:** interruption-safe summary rewrite after each book (mirror
  `Save-Summary`); no shared mutable state across books.
- **API surface parity:** the same coverage truth should eventually flow to the batch path
  (EB-340 auto-enable) — noted, not implemented here.
- **Unchanged invariants:** `_apply_large_file_dpi_reduction` keeps its 2-tuple return; rubric,
  converge-loop, provider abstraction, and `data/vqa_baseline_*` are untouched.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Reusing `coverage_status` conflates truncation vs large-file cause | `coverage_reason` names the specific cause; `truncation_events[]` unchanged |
| Changing the reduction return tuple breaks 8+ test sites | Option B — snapshot/detect at call site; 2-tuple contract preserved |
| New field name collides (e.g. `source_format` precedent) | Grep all four names before ratifying (SCRUM-282) |
| Test double-import `isinstance` mismatch | Import via `from llm_providers...` not `from tools.llm_providers...` |
| Grader non-determinism pollutes findings | Calibration gate first; report cross-book patterns only; filter `partial` coverage out of corpus stats |
| Large/long A/B book memory pressure at 50pg/150 DPI | Execution-time observation; streaming deferred (EB-148); reduce that one book's `--max-pages` if needed and record it |
| Node down mid-sweep | Skip-and-warn; interruption-safe summary allows resume |

## Documentation / Operational Notes

- Findings land in `docs/solutions/`; new defects become tickets (EB-340 children/links).
- Sweep artifacts under `logs/eb340-sweep2-2026-06-01/` (logs are batch-report-exempt from
  worktree policy; the **code** change in Units 1–2 lands on a worktree branch via PR per
  EB-181 / global git workflow).
- Server must be at `--ctx-size 32768`; document the 8k-overflow failure mode in the runner's
  abort message.

## Sources & References

- **Origin document:** `docs/superpowers/specs/2026-06-01-eb340-vqa-stress-sweep2-design.md`
- Sweep #1 method/findings: `docs/solutions/eb340-full-vqa-batch-findings-2026-05-29.md`
- Coverage schema precedent: `docs/solutions/eb-149-vqa-coverage-loss-surfacing.md`
- Grader calibration: `docs/solutions/scrum-280-local-vqa-calibration-patterns.md`
- Additive-fields / regression-fixture discipline: `docs/solutions/scrum-281-fallback-fingerprint-routing.md`,
  `docs/solutions/scrum-282-vqa-baseline-methodology.md`
- Sweep runner pattern: `logs/eb340-full-vqa-2026-05-29/run-sweep.ps1`
- Code: `tools/visual_qa.py` (`build_report`, `_apply_large_file_dpi_reduction`, `run_visual_qa`,
  `main`); tests `tools/test_visual_qa_evaluation_status.py`, `tools/test_visual_qa_retry.py`
