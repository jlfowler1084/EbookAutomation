---
date: 2026-04-18
topic: local-llm-training-data-collection
status: brainstorm
parent: docs/brainstorms/2026-04-13-local-llm-integration-opportunities.md
related_tickets:
  - SCRUM-279 (P1 guided_json, P2 calibration)
  - SB-35 (sb-chat --max-model-len 65536 → 131072)
---

# Local LLM Training Data Collection — Passive Capture for Future Fine-Tuning

## Problem

EbookAutomation's visual-QA pipeline now runs two evaluators side-by-side: Claude (via Anthropic API) and Qwen3.5 (via sb-chat/vLLM local). SCRUM-275 Phase 2 6-book smoke produced paired reports — useful, but transient: the data lives in `data/scrum275_local_smoke/` (gitignored, single run) and is regenerated/overwritten on every new run.

If a future project decision requires **fine-tuning Qwen to close the grader-leniency gap** (SCRUM-279 P2) or **validating a model swap** (Qwen2.5-VL-32B-Instruct, pre-listed in the parent plan as fallback), we will face a cold-start data problem. Labeling image/rubric pairs from scratch is expensive. The pairs we need are already being generated as a side effect of normal work — we just aren't keeping them.

## Premise

Fine-tuning is **not** on the near-term roadmap. The SCRUM-279 sequence explicitly defers it:
1. SCRUM-279 P1 — guided_json structural fix (ship first)
2. SCRUM-279 P2 — prompt-engineering ladder (strict-grader → persona → score-band → few-shot → chain-of-criticism)
3. Only after the P2 ladder fails to close Δ < 15 vs Claude → consider FT vs model-swap

Data collection must be **cheap insurance, not a commitment**. No labeling workflows. No eval harnesses. Just persist what the pipeline already produces, gitignored, in a format that a future FT experiment can actually use.

## The Idea

Passively log every `tools/visual_qa.py` run as a JSONL record in `data/vqa-runs/` (gitignored), one file per book/run.

### Record shape

```jsonc
{
  "run_id": "2026-04-18T14:32:05Z_oil-kings_local",
  "book": "oil-kings",
  "provider": "local|claude",
  "model": "qwen3.5-35b-a3b-fp8" | "claude-sonnet-4-6",
  "provider_version": {                        // captured from server response headers / SDK version
    "vllm_version": "0.19.0",
    "backend": "guidance"                      // observed structured-output backend (SCRUM-279 P1)
  },
  "page_sample": {
    "pdf_path": "output/kindle/Oil Kings_...kfx",
    "page_labels": [15, 40, 87, 142, 210, 278, 340, 401],
    "image_sha256s": ["sha256:...", ...]       // dedupe/compare across runs; don't persist the PNGs themselves
  },
  "rubric_version": "sha256-of-tools/visual_qa_rubric.md",
  "request": {
    "max_tokens": 16384,
    "temperature": 0.1,
    "response_format_kind": "json_schema" | "json_object",
    "schema_hash": "sha256-of-schema-body"
  },
  "response": {
    "finish_reason": "stop" | "length",
    "input_tokens": 4321,
    "output_tokens": 847,
    "latency_ms": 3300,
    "parsed_report": { /* full VQA report JSON */ },
    "raw_text_sha256": "sha256:..."            // store hash; keep raw text separately if useful
  },
  "guard_signals": {
    "page_count_mismatch": false,
    "truncation_detected": false,
    "json_parse_failed": false
  }
}
```

### Storage layout

```
data/
  vqa-runs/
    2026-04-18/
      oil-kings_local_14:32:05.jsonl
      oil-kings_claude_14:33:12.jsonl
      mexico-illicit_local_14:35:01.jsonl
      ...
    .gitignore  (just `*`)
```

- **One record per run**, not per page. Keeps the collection analyzable per-book-per-provider.
- **Gitignored** — this is training data, not source. Separate backup strategy if retention matters.
- **Content-addressed image hashes**, not embedded images — lets us dedupe/verify without bloating storage. PNGs live in the existing `data/debug/` or are re-extractable from the source PDF.
- **Rubric + schema hashes** — so a future FT experiment knows which rubric/schema version the pair was generated under. Drift invalidates pairs; capturing the hash makes drift detectable.

### Where the hook goes

Single line in `tools/visual_qa.py` at the end of a successful run: `_log_vqa_run(run_record, outdir="data/vqa-runs")`. Unchanged if the outdir is missing (opt-in via existence of the directory, or a config flag `settings.json:visual_qa.log_runs: true`).

## What this unlocks (ordered by likelihood of use)

1. **Paired-report diffing (immediate, this ticket).** SCRUM-279 P2 Step 1 is "classify failure mode (a/b/mixed) by eyeballing high-score pages and their `issues[]` arrays." Having durable local/Claude pairs makes that analysis repeatable rather than requiring a fresh smoke each time.
2. **Supervised fine-tuning dataset (possible, 2-3 months out).** If P2 prompt-eng fails to close the Δ, Claude's reports become the training target for a Qwen LoRA. Thousands of paired examples accumulated passively is a different cost envelope than labeling from scratch.
3. **Model-swap validation (possible).** When Qwen2.5-VL-32B-Instruct is tried (P2 Step 2b.3), we can replay the same `page_sample` image_sha256s and compare outputs without regenerating the full corpus.
4. **Drift detection (quiet win).** If the rubric or schema changes, records from before the change are tagged with old hashes. Never-diverge-silently.
5. **Grounding for SB-35 context ceiling doubling.** Raising sb-chat's `--max-model-len` from 65K → 131K (SB-35) unlocks longer per-request contexts. Historical runs captured at 65K give us a pre-change baseline to measure whether the larger context actually helps on real workloads.

## Non-goals

- **Not** a labeling pipeline — no human-in-the-loop annotation UI
- **Not** an eval harness — doesn't score anything, just persists
- **Not** a dataset for *this* ticket (SCRUM-279 P1) — the structural fix ships without it
- **Not** cross-project (SecondBrain, CareerPilot) — each project's pipeline would make its own decision, no shared schema
- **Not** committed to the repo — gitignored; lives on the machine that runs the pipeline

## Risks & questions

- **Storage growth.** 6-book corpus * ~2 providers * arbitrary-re-runs = can accumulate. Mitigation: rotate old runs after N days via a maintenance script, or rely on the gitignored directory being on the same disk budget as other local caches.
- **Sensitive content.** Some books may be copyrighted / sensitive. Hashes of images are fine to keep; consider whether raw rubric responses (which can quote source text) need scrubbing if the data ever leaves the machine. Short answer: don't share the dir externally.
- **Open question — should `run_id` include git SHA of pipeline code?** Would pin provenance tightly; adds hash-collection overhead. Deferred.
- **Open question — single JSONL per day vs per run?** Per-run is simpler; per-day aggregation can be a post-processing step.

## Decision if pursued

Single implementation unit, small:
1. Add `_log_vqa_run(record, outdir)` helper in `tools/visual_qa.py`
2. Wire at the end of the `run_visual_qa` function, behind a config flag
3. Add `data/vqa-runs/` to `.gitignore` (or rely on existing pattern if `data/` is already covered)
4. Unit test that the record shape round-trips and omits raw images
5. Documentation: one paragraph in `CLAUDE.md` about the logging surface

Estimated effort: 1-2 hours Sonnet session. No ticket required until prompt-eng work actually consumes the data — pure opportunistic capture.

## References

- Parent brainstorm: `docs/brainstorms/2026-04-13-local-llm-integration-opportunities.md`
- SCRUM-279 P1 plan: `docs/plans/2026-04-18-003-feat-scrum-279-p1-guided-json-schema-plan.md`
- SCRUM-279 P2 investigation plan: `docs/plans/2026-04-18-002-local-llm-visual-qa-calibration.md`
- SB-35 context-ceiling change: relevant because the 131K ceiling changes what per-run token numbers mean; captured via `provider_version` field
