---
module: visual_qa, llm_providers, scan_bench
tags: [eb-392, eb-391, vqa, provenance, local-llm, llama.cpp, context-window, harness, subprocess, windows, cloud-off, determinism]
problem_type: implementation-lessons
ticket: EB-392
date: 2026-09-06
status: shipped (Units 1-4; Units 5-6 are operational captures after merge)
---

# EB-392 Phase 0 — resolved provenance, adaptive context budget, and the scan-bench harness

Phase 0 of the local-LLM upgrade (epic EB-391) had one job: establish ground truth before any
pipeline logic changes. Six lessons came out of building it that later phases (and any other
harness in this repo) should reuse.

## 1. Provenance must come from the server, not the request

The EB-377 Gate-9 incident (grading silently ran on `localhost:8000`) recurred in a new form in
September: `.env` still pointed VQA at `localhost:8000`, which had since become the Flash **text**
gateway. It answers `/v1/models` fine and returns HTTP 500 on images. Nothing in a report said
which server answered — only `model`, the *requested* string, which llama.cpp ignores anyway.

**Rule:** every report carries `provider_resolved` populated from what the server *returns*:
`model_served` (the `/v1/models` entry matching the requested id), `n_ctx` and its source,
`n_ctx_train`, `total_slots`, `model_path`, `build_info`, `probe_ok`, and the effective batch /
max_tokens. `LocalVisionProvider.describe()` is the single source; `visual_qa.py`,
`vqa_determinism_check.py`, and `scan_bench.py` all read it. One resolver
(`resolve_local_vqa_target()`, cli > env > config, no literal fallback) replaced the two
divergent factories. A preflight that only lists models is not enough — the harness sends a
tiny image and fails on a text-only backend.

Verified server facts: llama.cpp `/v1/models` `data[].meta` carries **both** `n_ctx` (served)
and `n_ctx_train`; `/props` (host root, not under `/v1`) carries `total_slots` and, on some
builds, `model_path`/`build_info`; the gateway returns 404 on `/props`. The model `id` is the
operator's `--alias`, so `model_path` is the only weights identity.

## 2. Fit the budget to the probed window, and never let a probe failure be silent

`sb-vision` serves 8192 today (SB-231 raises it to 32768); the grader assumed 32768
(`GRADING_MAX_OUTPUT_TOKENS = 24576`, batch 8). The EB-350 branch (PR #184) added the probe but
floored output at 8192 tokens, which on an 8192 window is a guaranteed overflow. The floor now
scales with the window (`min(MIN_OUTPUT_BUDGET, available - images * per_image)`), with an
absolute minimum that logs an ERROR instead of raising. An unknown window assumes 8192
(smaller batches, still correct) **and** flags the report (`coverage_reason:
probe_failed_conservative_window`, `evaluation_status: evaluated_degraded`) so callers that never
read `provider_resolved` still see the degraded regime. An explicit `--n-ctx` wins over the
probe but warns when they disagree.

Two knock-on rules: the cap only addresses *input* overflow (EB-149 already declined batch
reduction as a truncation fix; partial coverage on scans is output truncation, EB-358), and
batch size is pinned at 8 across baselines because every prior VQA number was graded at 8 and
batch composition moves scores.

## 3. `subprocess.run(timeout=)` cannot kill a process tree on Windows

CPython's `run()` kills the direct child and then **blocks in `communicate()` until every
process holding the inherited pipe handles exits** — the `pwsh → python → ebook-convert →
calibre-parallel` grandchildren. By the time the harness sees `TimeoutExpired`, the root PID is
dead and `taskkill /T` enumerates nothing; the orphans keep running and can drop a KFX into the
run directory minutes later. `scan_bench.run_with_tree_kill` uses `Popen` +
`communicate(timeout)`, kills descendants **first** (`taskkill /F /T /PID <root>` while the root
is alive, psutil if importable), then kills the root and drains with a second bounded timeout.
Proven live: a nested `pwsh -Command 'python -c "sleep 60"'` under a 5 s timeout returns in
~5 s with no surviving descendant. A unit test that fakes `subprocess.run` raising
`TimeoutExpired` would have passed against the broken design — only the live test exposes it.

## 4. Cloud-off is proven from two sources, and only an empty string does it

Current master is not $0 by default: `Convert-ToKindle` passes `--api-key` whenever
`ANTHROPIC_API_KEY` is truthy, zero-text scans escalate to Gemini when `GEMINI_API_KEY` is set,
and the VQA Claude fallback defaults on. The harness pins its child environment: the three cloud
keys set to `""` (an empty string blocks `python-dotenv` `override=False` from repopulating from
`.env`, and is falsy in PowerShell's `if ($env:X)`), `LOCAL_LLM_*` and `LOCAL_LLM_N_CTX` pinned
from the manifest. `cost_zero_verified` requires **both** a clean VQA report (`fallback_enabled
false`, no `fallback_*_tokens`) **and** a conversion log free of the extractor's cloud markers
(`AI Quality Pass: using model=`, non-skipped `AI Rejoin:`, `attempting Gemini fallback`,
`sending text to Claude`). A cost field is never evidence (`batch_qa` has read a nonexistent one
since SCRUM-290).

Consequence for baselines: cloud-off changes *content*, not just cost (paragraph rejoin,
sub-heading promotion, Gemini escalation), so row 0 is captured three ways at the same commit —
`row0-convert` (cloud off, now), `row0-vqa` (after SB-231, single slot), and `row0-cloud`
(as configured) — because after Phase 1 turns the Anthropic sites into an opt-in provider the
cloud comparator can no longer be produced from master.

## 5. Harness postconditions that the reviewers had to add

The 11-persona review of the first cut found 41 issues, 6 of them P1, all in the harness:
paths interpolated into a `pwsh -Command` string in double quotes (`"`, backtick, `$(` inject —
use single-quoted literals with `'` doubled; one of the 13 manifest paths contains an ASCII
apostrophe); the post-kill drain had no timeout; run-summary/run-meta writes were not atomic
(tmp + `os.replace`); a real run never printed its generated run id while resume/promote
required it (envelopes on stdout + `--run-label` resolving the newest run); the determinism
check rejected the new `evaluated_degraded` status, which would have blanked an entire run's
grading on a probe hiccup (`could_not_assess` is now a distinct, resumable gate outcome);
`promote --force` merged onto a stale label (stage then swap). The plan committed to per-row
TEMP cleanup that the implementation forgot. Keep these as the checklist for any future
subprocess-driven harness here.

## 6. Small facts worth not rediscovering

- The common hand-optimized 1x1 PNG literal is rejected by llama.cpp's image loader (HTTP 400
  "Failed to load image"); a plain 8x8 RGB PNG built with `struct`/`zlib` works.
- `tools/poppler` in the main tree is a legitimate **junction** to the WinGet Poppler install; a
  junction hazard check must be scoped to the data directories (`archive/`, `output/`, `inbox/`,
  `processing/`, `data/`, `test-corpus/`, `logs/`) or it fails preflight exactly where captures
  must run.
- `test-corpus/*` is gitignored except top-level `*.baseline.json`; a manifest cannot live there.
  Raw runs under `data/scan_bench/runs/**` are gitignored; promoted baselines are tracked and
  land via PR (EB-181).
- A test in the suite writes `data/batch_reports/header_bleed/<ts>.json` into the repo on every
  full run (pre-existing leak; delete before committing).
- `tests/test_fingerprint_detector.py::test_integration_mapreduce_a2_report_flagged` fails on
  master (fixture drift, unrelated to VQA provenance).

## Follow-ups

- SB-231: raise `sb-vision` to 32768 keeping `--parallel 1` — prerequisite for `row0-vqa`.
- Todos 001 (typed contracts for the probe/row dicts) and 002 (resume orphan lock) under
  `.context/compound-engineering/todos/`.
- Cross-reference: `eb361-vqa-grader-determinism-self-check` and
  `eb377-phase3-50book-regression-sweep` — the "prove the resolved endpoint" lesson those entries
  asked for is now `provider_resolved` + `resolve_local_vqa_target()`.
