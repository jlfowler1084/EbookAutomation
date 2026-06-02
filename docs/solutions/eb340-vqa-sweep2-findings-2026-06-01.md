---
module: visual_qa
tags: [vqa, eb-340, stress-sweep, calibration, f1-coverage, eb-353, eb-348]
problem_type: investigation
ticket: EB-340
date: 2026-06-01
---

# EB-340 VQA Stress Sweep #2 — Lane A Findings

Local-only (zero-cloud) breadth sweep over a curated 31-book corpus, run after
PRs #170 (F1 non-silent coverage accounting), #171 (sweep runner), and #172
(runner KFX-resolution fix) landed on master (`ad65df5`).

- **Runner:** `tools/run_eb340_sweep2.ps1 -Phase Both` at `git_sha = ad65df5` (clean tree)
- **Provider:** local Qwen3-VL-30B-A3B (R9700, `http://192.168.1.33:8080`, `n_ctx=32768`)
- **Flags (explicit):** `--provider local --fallback-enabled false --dpi 150 --max-pages 50`
- **Corpus:** 31 real books (pages ≥ 10) curated from a 432-book `-Phase Select`
  inventory — digital 10 / scan 14 / two-column 5 / ocr 2; 8 large files
  (39–222 MB) for the F1 path; 3 A/B reruns vs sweep #1.
- **Calibration gate (passed before the sweep):** run-twice determinism
  (81≡81, 0/50 per-page diffs) + known-good prose canary (Oil Kings 91, zero
  garbled-OCR false positives). See [[eb340-sweep2-state]] memory.

## Headline

**31/31 books evaluated; ZERO infrastructure failures** (no `api_failure`,
`conversion_failure`, or `no_pages_sampled`). Every book converted (incl. the
222 MB / 5,664-page NKJV Study Bible) and produced a scored report. The runner
KFX-resolution fix (#172) and the worktree data-dir setup held across the full
corpus — no `no_kfx_produced` mislabels.

Per the EB-340 aggregation rule, `evaluation_status="evaluated"` + `vqa_exit=1`
is a **valid scored result below the pass threshold (70)**, not an infra
failure. 11 books scored < 70 (`vqa_exit=1`); all are real evaluations.

## Score distribution

| type_axis | n | mean | min | max | partial |
|---|---|---|---|---|---|
| digital | 10 | 82.1 | 69 | 90 | 0 |
| two-column | 5 | 83.4 | 66 | 95 | 0 |
| ocr | 2 | 70.5 | 48 | 93 | 0 |
| **scan** | 14 | **57.4** | **12** | 94 | **5** |
| **all** | 31 | 70.4 (median 78) | 12 | 95 | 5 |

- **Digital and two-column are robust** (means 82–83, no partial coverage).
- **Scan is the problem class** (mean 57.4, all 5 partial-coverage books, and
  every sub-50 outlier). Large files (>30 MB, n=8, mean 61.5) are mostly scans
  and inherit this.

## F1 coverage accounting (#170) — validated, with a coverage gap

`coverage_status` behaved **correctly**: `complete` when `pages_evaluated >= pages_sampled`,
`partial` otherwise. The 5 partial books (p28 47/50, p242, p15 49/50, p292 48/50,
p273 42/50) reflect the grader returning scores for **fewer pages than were
rendered**. The run.log identifies the specific cause as **output-token
truncation**, not input/batch sizing: dense multi-image batches hit
`finish_reason='length'` at the 16,384 output-token budget
(`OutputTruncatedError: ... output_tokens=13740 (budget=16384) — report invalid`),
returning incomplete JSON that is discarded; on these 5 books the single-page
retry also truncated (it can itself hit 16,384). Truncation-event counts: p273 ×27,
p242 ×17, p28 ×11, p292 ×9, p15 ×5. This is the EB-149 "report can never silently
read complete" guarantee working (truncation surfaced as explicit coverage loss).

> **Correction (per review):** an earlier draft attributed this to "batch/parse
> loss" tied to EB-350. That is wrong. EB-350 / PR #169 addresses **input**
> context sizing; it does not manage the **output**-token budget and does not
> solve this mode. Tracked separately as **EB-358**. Do not close it under EB-350.

**Coverage gap (sweep design):** `coverage_reason` was `None` on every row and
`effective_dpi == requested_dpi` everywhere — i.e., the **`large_file_default_reduction`
path of #170 was never exercised.** Because the runner passes *explicit*
`--dpi 150 --max-pages 50`, the EB-347 large-file guard honored them and never
reduced, so the "default reduction → forced `partial` with a reason" branch
never fired. **To validate that specific F1 branch, a future run must omit the
explicit flags** so the large-file guard engages on the >30 MB books.

## A/B vs sweep #1 (2026-05-29) — confounded, not clean regressions

| book | sweep #1 | sweep #2 | Δ | verdict |
|---|---|---|---|---|
| ML for Asset Managers (code/math) | 87 (p06) | 79 (abp06) | −8 | **confounded** |
| Zeitgeist 2025 (scan/OCR) | 73 (p09) | 70 (abp09) | −3 | stable |
| Monumental Christianity (large old scan) | 54 (p11) | 12 (p273) | −42 | **real degradation** |

The deltas are **not** clean apples-to-apples — they are confounded by (a)
different sampled pages between sweeps, (b) the EB-353 grader false-positive
mode, and (c) genuine extraction garbling. Two spot-checks (rendered KFX→PDF→PNG)
resolve them:

### Spot-check 1 — p273 Monumental (score 12): TRUE positive
Page 2 (title page) renders as genuinely corrupted OCR:
`MoNu~IENTAL CHRISTIANITY`, `~rt nnh Sptnboliitn of tbt lrimitibt ~burcb`,
`THEONECATHOLICFAITHANDPRACTICE`, `JOHNPLUNDY`, `PJU!.IB YTBil`. The 1876 scan's
text layer is genuinely broken; the grader's "severe text corruption / garbling"
findings (169 total issues, **63 critical**, 80 major across 42 evaluated pages)
are **correct**. Score 12 is justified — this
is a real conversion failure on an old scan, **not** a grader artifact.

### Spot-check 2 — abp06 ML for Asset Managers (score 79, worst page 51): MIXED
- **Real (EB-348):** equations render as `(cid:2)` / `(cid:3)h h (cid:3)` glyph
  garbage and garbled math (`λ1>λp`, `λjβ¼≤λβ`) — genuine math-glyph extraction
  failure. The grader is right about the equations.
- **False (EB-353):** the Python code snippet at the bottom
  (`def denoisedCorr(eVal,eVec,nFacts): ...`) is **perfectly legible**, yet the
  grader flagged it "completely illegible due to garbled text." A clear
  false positive.

So abp06's −8 is **partly unfair** (EB-353 deflation on readable code) and partly
real (EB-348 math glyphs). The clean comparison would require suppressing the
EB-353 FP and re-anchoring page sampling.

## Calibration: the grader's "garbled" findings are a MIX — read per case

Combining the pre-sweep calibration (Python in Easy Steps) with these
spot-checks, the local grader's `garbled / OCR / illegible / extraction failure`
findings split into three buckets:

| Content | Grader verdict | Reality |
|---|---|---|
| Clean prose (Oil Kings) | no garble findings | correct |
| Code / syntax templates (Python book, abp06 snippet) | "garbled OCR" | **FALSE (EB-353)** |
| Math / equations (abp06 p51) | "garbled" | **TRUE (EB-348 cid-glyph)** |
| Old scanned OCR (p273) | "severe corruption" | **TRUE (real bad scan)** |

**Implication for findings consumers:** a low score on a *code-heavy* book is
suspect (EB-353); a low score on an *old scan* or *math-dense* book is likely
real. Never treat the aggregate score on code books as ground truth without the
EB-353 lens.

## Low outliers (all `vqa_exit=1`, all real evaluations)

| id | book | type | score | note |
|---|---|---|---|---|
| p273 | Monumental Christianity (1876) | scan | 12 | real garbling (spot-checked) |
| p15 | Weimar sourcebook | scan | 15 | old scan; 144 total issues / 75 critical (49 eval) — probable real |
| p242 | (scan) | scan | 35 | partial coverage |
| p28 | ACA syndrome workbook | scan | 39 | partial coverage |
| p374 | Catholic Study Bible (203 MB) | scan | 41 | dense scan |
| p418 | UN replacement migration | ocr | 48 | |
| p284 | NKJV Study Bible (222 MB) | scan | 51 | 50/5664 pages sampled |
| p73 | Mastering Intune (120 MB) | scan | 54 | |
| p292 | (scan) | scan | 62 | partial coverage |

## Follow-ups

- **EB-353** (filed): grader mislabels readable code/syntax-template text as
  "garbled OCR" — confirmed again on abp06 page 51.
- **EB-348** (open, PR #169 era): code-block structure loss + math `(cid:N)`
  glyph garbling — confirmed live on abp06 equations.
- **EB-358** (filed): **output-token truncation** at the 16,384 budget
  (`finish_reason='length'`) on dense batches drove all 5 partial-coverage
  results — incomplete JSON discarded, single-page retries also truncating. This
  is the actual fix target for sweep #2 partials. **Distinct from EB-350/PR #169**,
  which sizes *input* context and does not manage the output budget. EB-149 (Done)
  only surfaces the loss as explicit partial coverage.
- **F1 large-file-reduction path untested** this sweep (explicit flags bypassed
  the EB-347 guard) — schedule a no-explicit-flags run to exercise
  `coverage_reason = large_file_default_reduction` on the >30 MB books.
- **Lanes B/C** remain out of scope (classifier-handoff + fallback-cost probes
  not yet in scope).

## Reproducibility

- Run artifacts (gitignored, not committed per EB-181): worktree
  `logs/eb340-sweep2-2026-06-01/` — `run-meta.json` (sha `ad65df5`),
  `manifest.json` (curated 31), `inventory-full.json` (432), `run-summary.json`,
  `vqa/`, `spotcheck2/`.
- Spec: `docs/superpowers/specs/2026-06-01-eb340-vqa-stress-sweep2-design.md`.
- Sweep #1 baseline: `logs/eb340-full-vqa-2026-05-29/`.
