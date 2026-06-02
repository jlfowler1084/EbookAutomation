---
title: "EB-361 — VQA grader determinism self-check (run-twice guard)"
date: 2026-06-02
ticket: EB-361
module: visual_qa, vqa_determinism_check, llm_providers.local_provider
tags: [vqa, qwen3-vl, determinism, calibration, batch-invariance, llama-cpp, guard]
problem_type: bug-fix
status: shipped
related: [EB-150, EB-353, EB-340, EB-348]
---

# EB-361 — VQA grader determinism self-check

## Problem

The local VQA grader is **not bit-deterministic under concurrent node load**.
Measured on the Python-in-Easy-Steps canary (`--provider local --dpi 150
--max-pages 50`, `temperature=0`, `seed=42`):

- An **isolated** double-run was bit-identical: run1 ≡ run2 = 86 (0/50 per-page diffs).
- A **concurrent** back-to-back double-run **diverged**: run1 = 77, run2 = 75, with
  5/50 per-page score diffs of ±15–20 (e.g. p38/p43/p48 90→70).

This invalidated score-based prompt tuning during EB-353 (the 86→78→77→75 spread
was dominated by grader noise, not prompt edits) and blocks trusting VQA
`overall_score`/pass-fail for **converge gating**, **EB-340 re-evaluation**, and
**EB-348 rendering-delta measurement**.

## Root cause (verified against the code, not just hypothesized)

The non-determinism is **server-side batch-invariance failure**, not a missing
client knob:

1. The client already pins every reproducibility control it can —
   `temperature=0`, `seed=42`, guided-JSON schema, `enable_thinking=False` — in
   all three build paths (`LocalVisionProvider.build_request` /
   `build_detection_request` / `build_scoring_request`). The
   `test_vqa_grader_calibration.py::TestProviderTemperatureAndSeed` tests lock
   this in.
2. The **score arithmetic is already deterministic** by construction: EB-150
   derives `overall_score` from a fixed severity-deduction table
   (`critical=52, major=25, moderate=15, minor=5`), not from the VLM's
   stochastic score field (`visual_qa.py`, `_SEVERITY_PAGE_DEDUCTIONS`).

Since a stable issue list ⇒ a stable score, the only thing left that can vary is
**the set of issues the VLM emits**. That is decided during token generation on
the shared **llama.cpp Vulkan** node (`Qwen3VL-30B-A3B-Instruct`, the R9700 box).
The node runs **continuous batching**; when other clients (sb-chat is shared with
SecondBrain and CareerPilot) interleave, the grading request lands in a different
batch composition. Batched GPU matmuls reorder floating-point reductions, so a
borderline logit flips the greedy `argmax` to a different token → an issue
appears/vanishes → a page swings 90→70.

> **The crucial reframe: `temperature=0` does NOT guarantee reproducibility on a
> shared, batched inference server.** Determinism requires batch-invariant kernels
> or exclusive single-sequence decoding — properties of the *server*, not the
> request. No client-side prompt/param change can fix this. (This is why EB-353
> correctly validated its prompt fix against rendered ground-truth, not scores.)

Corroborated by `docs/solutions/eb340-full-vqa-batch-findings-2026-05-29.md`:
"Determinism: directional only … per-page scores swing up to ±10, *category
labels change between runs*."

## What shipped (the guard — not a cure)

A **determinism self-check** that encodes the global calibration rule: run the
same input twice and refuse to trust the scores unless the runs agree per-page.

- `tools/vqa_determinism_check.py`
  - `compare_reports(report_a, report_b, *, tolerance=0)` — pure comparator.
    Gate = per-page score |Δ| within `tolerance` (default **strict 0**, EB-361)
    **plus** page-set parity. Issue-category drift is surfaced
    (`n_issue_drift_pages`) as a secondary diagnostic but does **not** fail the
    score gate.
  - `run_determinism_check(runner, *, runs=2, tolerance=0)` — runs an injected
    runner N times (strictly sequential) and compares run 0 against each later run.
  - `build_vqa_runner(...)` / `main()` — live CLI path. **Fallback routing is
    forced OFF** (EB-361 measures the *local* grader; the Claude fallback would
    inject a second, different provider — matches the EB-340 sweep's
    `--fallback-enabled false`). `user_supplied_dpi/max_pages=True` so the
    large-file auto-reduction can't silently change coverage mid-measurement.
- `tests/test_vqa_determinism_check.py` — 16 hermetic tests (no node, no keys),
  including the exact EB-361 data (p38 90→70, overall 77 vs 75).

### Usage

```powershell
# Run the canary twice and gate on bit-determinism (exit 1 if scores wobble):
python tools/vqa_determinism_check.py --input "output/kindle/Python in easy steps, 2nd Edition - Mike McGrath.kfx" --dpi 150 --max-pages 50

# Keep both runs' reports for inspection, JSON output for CI/agents:
python tools/vqa_determinism_check.py --input book.kfx --out-dir data/debug/eb361 --json
```

**Exit codes:** `0` deterministic · `1` non-deterministic (scores UNRELIABLE) ·
`2` could not assess (a run produced no evaluated pages — node down, conversion
error). A non-deterministic verdict prints a WARN telling the operator to quiesce
the node and re-run before trusting any deltas.

## The true cure (operational — out of this repo)

The guard *detects* non-determinism; it does not eliminate it. To make the grader
actually reproducible during measurement runs, the node must decode grading
requests one sequence at a time:

1. **Serve with a single slot.** On the llama.cpp Vulkan node (`serve-qwen-vl.ps1`,
   which lives on the node / SecondBrain — not this repo), start the server with
   **`--parallel 1`** (single slot). With one slot, requests queue and decode
   individually, so the batch composition is always "just this request" →
   batch-invariant → deterministic. (vLLM equivalent: `--max-num-seqs 1`.)
2. **Quiesce other clients.** Even with `--parallel 1`, ensure SecondBrain and
   CareerPilot are not driving heavy local VLM load during a measurement run.
3. **Verify with this guard.** Run `vqa_determinism_check.py` on the canary and
   confirm exit 0 (0/50 per-page diffs) before trusting any scores.

A pure client-side lock was explicitly **not** shipped: it would only serialize
EbookAutomation's own processes and cannot bind SecondBrain/CareerPilot, so it
would be defense-in-depth at best, not a guarantee. `--parallel 1` is the real fix.

## Re-baseline procedure (after the node is deterministic)

Once `vqa_determinism_check.py` reports exit 0 on a quiesced single-slot node,
the EB-353 / EB-340 canary scores can be trusted again:

1. Re-capture baselines on the quiesced node (per
   `docs/solutions/scrum-282-vqa-baseline-methodology.md`).
2. Confirm parity with `python tools/compare_vqa_reports.py audit`.
3. Only then consider flipping `config/settings.json` `visual_qa.enabled = true`.

## Lessons

- A non-deterministic measurement harness is a **harness defect**, not data —
  resolve it before escalating any findings (global calibration rule).
- For shared LLM inference: reproducibility is a **server property**. Pin the
  client (`temperature`/`seed`), but gate on an empirical run-twice check rather
  than assuming the pin is sufficient.
- Gate on the metric that actually feeds decisions (per-page *score*); report
  the deeper signal (issue-category drift) without letting it block.
```
