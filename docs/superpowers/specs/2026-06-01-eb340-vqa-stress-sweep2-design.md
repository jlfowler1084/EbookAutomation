# EB-340 VQA Stress-Test Campaign (Sweep #2) — Design

**Date:** 2026-06-01
**Status:** Design (pending implementation plan)
**Anchor ticket:** EB-340 (auto-enable VQA on overnight batch)
**Related:** EB-347 (large-file override — interim fix, landed), EB-348/EB-349 (extraction
code-block `<pre>` + CID-glyph fixes / classifier OCR escalation — landed in PR #169),
EB-342 / EB-148 (streaming render→eval→release chunker — out of scope here),
EB-150 (R9700 parity + baseline recapture — calibration gate, separate).

## Problem

The 2026-05-29 EB-340 sweep (`docs/solutions/eb340-full-vqa-batch-findings-2026-05-29.md`)
proved the local **R9700 Qwen3-VL** endpoint makes visual QA effectively free, and surfaced
real conversion-quality patterns that the cost-limited 8-page sample never saw (F1 large-file
coverage collapse, F2 code/math extraction failure, F4 scan under-escalation). Since then,
PR #169 landed the extraction-side fixes (EB-348/EB-349) and the EB-347 large-file override.

We want a **second, broader sweep** to (a) find new patterns at ~2× the corpus breadth, and
(b) produce *causal* evidence that the PR #169 fixes actually moved the known failure cases —
not just a noisier overall score.

## Critical framing: separate lanes, honest cost labels

A single bare `Convert-ToKindle -NoCache` run **cannot** validate everything, because:

- `classifier_escalation.auto_gemini_on_scan` is **`false`** in this checkout
  (`config/settings.json`). So the default conversion path does **not** exercise
  classifier-driven Gemini OCR escalation. "OCR escalation moved the needle" is therefore
  **not** a deliverable of a zero-cloud run.
- The sweep uses `--fallback-enabled false`, so it **cannot** answer the EB-340 *Claude
  fallback* cost question. Its auto-enable evidence is scoped to **local-only / no-fallback**.

The campaign is split into three lanes so each deliverable has clean causal attribution and a
truthful cost label.

### Lane A — Zero-cloud conversion-quality sweep ($0)

The breadth run. Validates **zero-cloud conversion quality** and the **EB-348/EB-349 code /
CID-glyph extraction fixes**. Does **not** validate OCR escalation.

- **Per book:** fresh `Convert-ToKindle -NoCache` (default HTML-extraction path, no converge
  loop, zero cloud) → local VQA with **explicit** flags:
  `--provider local --fallback-enabled false --dpi 150 --max-pages 50`.
  Explicit `--dpi` / `--max-pages` trigger the EB-347 override, so large/long books are
  **honored, not silently collapsed** to 4 pages @ 72 DPI.
- **Endpoint:** `192.168.1.33:8080`, model `Qwen3VL-30B-A3B-Instruct-Q4_K_M` (confirmed
  reachable 2026-06-01). Server **must** run at **≥32k `n_ctx`** — 8k overflows the multi-image
  batch at useful DPI and yields a silent `api_failure` (EB-340 blocker). Verify `n_ctx`
  before the run.
- **Node-down policy:** skip-and-warn per book; never hard-fail a conversion because the VQA
  node is down.

### Lane B — OCR-escalation validation (small Gemini $)

Proves classifier → Gemini escalation actually fires and helps. **Not $0.**

- 1–2 `scan_with_text` books (e.g. the Zeitgeist-class case from sweep #1 that the classifier
  flagged `ocr,gemini` but the default path didn't escalate).
- Run once with `classifier_escalation.auto_gemini_on_scan: false` (baseline) and once with
  it **`true`** (opt-in), comparing the **artifact metrics** below — primarily `(cid:N)` /
  OCR-garble counts and `text_integrity`.
- Cost is Gemini OCR calls only; record per-book token/$ in the manifest. Restore the config
  toggle to `false` after the lane.

### Lane C — Fallback-cost probe (small Claude $)

Answers the EB-340 *Claude fallback* cost question that Lane A explicitly cannot.

- 2–3 books run with `--fallback-enabled true` (fingerprint/uniform-score gating intact) to
  measure real Claude fallback token cost per book.
- Pick books likely to trip the fallback (uniform-score / front-matter ceiling cases) so the
  probe actually exercises the path. Record per-provider and canonical total cost.

## Corpus & selection (~25–30 books)

Source: `F:\Books`. Selected by **technical type, not topic**, labeled via
`classify_source.py`. Composition:

- **~22–27 fresh titles** (not in sweep #1's 12), spanning the type axes: two-column academic,
  code/math-heavy, scans needing OCR, image-plate / figure-heavy, magazine layout,
  footnote-dense, large files (>30 MB), long books (>500 pg), and 2 clean digital canaries.
- **2–3 reruns** of sweep #1's worst known-failure books for A/B causal evidence (see below).

## A/B rerun protocol — measure artifacts, not scores

Overall VQA score is too noisy (sweep #1: ±10 per-page, category labels change between runs).
For PR #169 validation, rerun and compare **artifact metrics** against the sweep-#1 baseline:

| Book class | Primary metrics |
|---|---|
| 1 code/math-heavy | `<pre>` block count (↑ good), `(cid:N)` count (↓ good), `text_integrity` category, spot-checked rendered code/equation pages |
| 1 scan / OCR | `(cid:N)` / OCR-garble phrase counts, `text_integrity`, spot-checked pages (Lane B if escalation is the variable) |
| (optional) 1 large/long F1 book | `pages_requested` vs `pages_rendered`, `effective_dpi`, `coverage_status` — confirm EB-347 override now covers it |

A fix "moved the needle" only if the **artifact metric** changed in the right direction on the
spot-checked pages — not merely the aggregate score.

## Calibration / trust gate (runs before any number is trusted — per global CLAUDE.md)

1. **Run-twice determinism** on one book — confirm still ±1 at book level; flag if worse.
2. **Known-good canary** (a clean digital book) — expect no real criticals; any hit is a grader
   artifact, recorded as such.
3. **Spot-check 2–3 findings per failure-class** against the actual rendered pages before
   anything enters the findings doc.

Reported rule, restated in the findings doc: **trust cross-book patterns, not individual page
scores or single criticals.** Grader artifacts (severity inflation, duplicate criticals,
"visual gap" tic) are reported separately from real findings.

## Reproducibility snapshot (manifest schema)

`logs/eb340-sweep2-2026-06-01/manifest.json` records, run-wide and per-book:

- **Run-wide:** git SHA (HEAD), exact commands per lane, relevant `config/settings.json` blocks
  (`visual_qa`, `classifier_escalation`, `ocr_escalation`, `converge_loop`), provider / model /
  `local_base_url`, confirmed server `n_ctx`, lane→config-delta map (Lane B toggle state).
- **Per-book:** source path + **sha256**, page count, file size (bytes), classify result
  (class + confidence + flags), output format (KFX vs **AZW3 fallback** flag), conversion
  warnings, VQA `pages_requested` / `pages_rendered` / `requested_dpi` / `effective_dpi` /
  `coverage_status`, scores by category, token/$ (per provider + canonical total).

## Minimal F1 hardening (EB-347 interim — concrete scope)

The sweep needs **no** code change to run (explicit flags bypass the collapse). The one small
fix in scope for EB-340 makes the **default / batch path** stop collapsing *silently*, so a
future batch auto-enable can't pass a 4-of-900-page report off as "complete":

- Emit a **`logger.warning`** (not `info`) when the large-file guard reduces values that came
  from **defaults**.
- Add report fields: `pages_requested`, `pages_rendered`, `requested_dpi`, `effective_dpi`,
  and a `coverage_reason` string + `coverage_status: partial` whenever reduction fires.

This is the honest-accounting half of the tiered-VQA design's "coverage accounting" section,
scoped to the interim guard. **Streaming render→eval→release chunking (full every-page
coverage) is explicitly NOT in scope** — that remains EB-342 / EB-148.

## Outputs

- `docs/solutions/eb340-vqa-sweep2-findings-2026-06-01.md` — findings doc (issue taxonomy,
  cross-book patterns, A/B artifact deltas, grader-artifact section), modeled on sweep #1.
- New tickets for each *real* (spot-checked) conversion defect.
- Updated EB-340 decision input: local-only/no-fallback auto-enable readiness (Lane A) + Claude
  fallback cost (Lane C) + OCR-escalation efficacy (Lane B), each with its honest cost label.

## Out of scope (YAGNI)

- Streaming chunker / full per-page coverage → EB-342 / EB-148.
- `vqa_policy` tiering layer + deterministic blind Claude audit slice → future tiered-VQA work.
- Rubric content and converge-loop algorithm changes.
- No new vision provider; reuse EB-339 local provider + existing Claude fallback.

## Testing / validation

- Calibration gate (above) passes before findings are recorded.
- F1 hardening: unit test that default-sourced reduction emits `coverage_status: partial` +
  warning, and that explicit-flag runs report `coverage_status: complete` with honored DPI.
- Manifest completeness check: every per-book field present; sha256 + git SHA recorded.
- Lane isolation check: Lane A reports show `fallback_enabled: false` and zero cloud cost;
  Lane B/C cost is non-zero and attributed to the correct provider.
