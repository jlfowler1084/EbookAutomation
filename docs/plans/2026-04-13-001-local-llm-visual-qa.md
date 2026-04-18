---
date: 2026-04-13
amended: 2026-04-18
plan_id: 2026-04-13-001
title: Full-book visual QA via local sb-chat Qwen3.5-35B (amended from Qwen3-VL)
status: amended
parent_brainstorm: docs/brainstorms/2026-04-13-local-llm-integration-opportunities.md
ticket: SCRUM-274
phase_2_ticket: SCRUM-275
related_tickets: [SB-34]
owner: Joe
estimated_sessions: 2–3 (Sonnet for implementation, Opus for review)
---

# Plan — Full-Book Visual QA via Local sb-chat (Qwen3.5-35B-A3B-FP8)

## Amendment — 2026-04-18 — Phase 1 corpus rebuild

PC migration from `DESKTOP-488UQB2` to current host left `output/kindle/` with only
`Intune-Study-Notes.kfx`. Of the six canonical CLAUDE.md test books, only Oil Kings
and Mexico Illicit had converted KFX artifacts on the old PC's admin share. No
source PDFs for Lincoln Highway, Atomic Habits, Sapiens, or Extreme Ownership
existed anywhere on the old host; the user supplied an Atomic Habits PDF from
`C:\Users\Joe\Downloads`.

The 87-KFX inventory on the old PC was mined for substitutes that preserve each
slot's **regression focus**, not its genre:

| Original slot | Substitute | Rationale |
|---|---|---|
| Lincoln Highway (stylistic chapters) | `The Return of the Gods - Jonathan Cahn.kfx` | Narrative non-fiction with thematic chapter names — best chapter-detection stressor in inventory |
| Sapiens (long chapters + footnotes) | `Decline of the West Volumes 1 and 2 - Oswald Spengler.kfx` | Sweeping historical work with long chapters and heavy footnote apparatus |
| Extreme Ownership (simple structure) | `Python in easy steps, 2nd Edition - Mike McGrath.kfx` | Short, regularly-structured — good canary |

Atomic Habits remains as a PDF input for Phase 1. `visual_qa.py --input` accepts
PDF natively, which exercises the same Claude Vision call path the refactor
touched. Converting to KFX is a follow-up task; doing it *before* baseline would
introduce Calibre conversion as a second confounding variable in the gate.

**This changes the Phase 1 gate from "all 6 canonical books" to "all 6 corpus
slots per the updated CLAUDE.md test corpus table."** Defensible because the
refactor commit `0014c1c` is book-agnostic — it extracts `VisionProvider` with
zero branching on book identity. The gate's purpose is to catch "did the refactor
change Claude's payload or response handling?" — a structural question satisfied
by any KFX/PDF inputs with varied page content.

The Phase 1 baseline runbook below (originally written for the 6 canonical books)
is updated inline: the foreach book list now reads the rebuilt corpus.

## Amendment — 2026-04-17 — pivot to sb-chat

This plan was originally written against a *separate* `Qwen3-VL-30B-A3B-Instruct-FP8`
container to be stood up on port 8000. That premise is obsolete.

During SB-33 ship-day testing on 2026-04-17, Joe discovered that **sb-chat
(`Qwen/Qwen3.5-35B-A3B-FP8`) is natively multimodal** — it has been loaded
with its vision tower the entire time on port 8000 without anyone noticing.
Cross-project reference doc: **SB-34**. Architecture confirmed as
`Qwen3_5MoeForConditionalGeneration` with 27 vision transformer blocks and
`image_token_id: 248056`. Live verified end-to-end via a 1×1 red pixel round-trip.

A smoke-test probe against the EbookAutomation VQA rubric on four pages
(Oil Kings p7/p15/p25, Mexico Illicit p30) returned structurally correct JSON
with zero hallucinations, zero parse failures, and flagged one genuine
pipeline bug (unstripped `"Introduction  15"` running header on Mexico Illicit
p30). Average API latency: 3.3 s/page at 150 DPI. Artifacts:
`data/debug/qwen_vqa_probe/`.

### What this changes in the plan

- **Model target:** `Qwen/Qwen3.5-35B-A3B-FP8` on sb-chat, not `Qwen/Qwen3-VL-30B-A3B-Instruct-FP8`.
- **Deployment:** we do NOT stand up a new vLLM container. sb-chat already serves this
  model. The Deployment Reference section below is retained for historical context
  only — it documents a container we are not deploying.
- **Phase 2 added requirement:** every vision request must include
  `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`. Without
  this, sb-chat's `--reasoning-parser qwen3` consumes the full `max_tokens`
  budget on `<think>` blocks and `message.content` is empty. This is a hard
  requirement, not a tunable. Documented in SB-34 and verified in the probe.
- **Phase 2 ticket split-off:** the Phase 2 integration work is tracked on
  **SCRUM-275** so commits land under a ticket scoped to the amended target,
  while SCRUM-274 remains the umbrella plan for Phases 1–5.
- **VRAM / deployment-risk rows** for "VRAM exhausted with VL + embedding models
  loaded" and "vLLM server crashes mid-book" are largely moot — sb-chat's
  lifecycle is managed by SecondBrain's compose, not this project.

### What did NOT change

- The `VisionProvider` abstraction (Phase 1, commit `0014c1c`) is architecturally
  correct regardless of which endpoint the local provider targets.
- The Phase 1 bit-identical Claude baseline gate is still open and still
  required before Phase 2 can ship.
- The VQA rubric (`tools/visual_qa_rubric.md`), report schema, and
  `import_vqa_reports.py` consumers all stay untouched.
- Phases 3–5 (full-book mode, escalation tier, baseline comparison) retain
  their original shape — only the model ID under the hood changes.

Sections below are preserved as originally written. Where an amendment
applies, it appears inline as an **Updated 2026-04-17** block immediately
after the original paragraph, so the historical rationale stays readable.

---

*The sections below are the original plan as of 2026-04-13, preserved
verbatim. References to "Qwen3-VL-30B-A3B" should be read through the
Amendment section above — the current target is sb-chat's
`Qwen3.5-35B-A3B-FP8`.*

## Goal

Enable visual QA to run on **every page** of a converted book instead of
8-page (default) or 20-page (full-mode) samples, by routing vision calls to a
local `Qwen/Qwen3-VL-30B-A3B-Instruct-FP8` server exposed via vLLM's
OpenAI-compatible API. Preserve Claude Vision as a high-confidence escalation
tier for low-scoring pages.

## Model Selection

**Chosen:** `Qwen/Qwen3-VL-30B-A3B-Instruct-FP8`

Rationale:

- **Native FP8 weights** map directly to Blackwell's FP8 tensor cores — no
  on-the-fly quantization penalty, no quality loss from post-hoc INT4/AWQ
  conversion paths designed for older hardware.
- **MoE architecture (30B total / ~3B active per token)** delivers
  dense-3B-class decode throughput, which is exactly what full-book per-page
  scans need. A dense 32B would be roughly 3× slower per page.
- **Qwen3-VL generation** has measurably stronger document understanding,
  OCR, and bounding-box output than Qwen2.5-VL — the Qwen team specifically
  targeted document-AI workloads in this release.
- **VRAM fit on the 96 GB Blackwell.** Realistic per-component footprint at
  65k context with FP8 KV cache:
  - LLM weights (30B × 1 byte FP8): ~30 GB
  - Vision encoder (ViT, stays FP16): ~1–2 GB
  - KV cache pool at 65k context, FP8: ~10–15 GB
  - CUDA graphs + activations + overhead: ~3–5 GB
  - **Working set: ~45–55 GB** to function; vLLM will claim more if
    `--gpu-memory-utilization` allows, using the surplus as a KV cache pool
    that improves batching throughput.

  Note: KV cache and weights are sized by *total* MoE parameters and layer
  count, not by active experts. The "3B active" figure governs **compute
  speed**, not memory — Qwen3-VL-30B-A3B has a 30B-class memory footprint
  with 3B-class decode latency.

  **Recommended utilization settings:**
  - **Solo VQA runs (embedding stopped):** `--gpu-memory-utilization 0.85`
    → vLLM grabs ~82 GB, leaves room for 16-page batches and longer
    effective context. Sweet spot for full-book mode.
  - **Concurrent with embedding model:** `--gpu-memory-utilization 0.75`
    → vLLM grabs ~72 GB, leaves ~14 GB for the embedding server. Smaller
    batches (4–8 pages) but both servers coexist.
  - **Bare minimum:** ~50 GB if context is cut to 32k and batching disabled.
    Not recommended — surrenders the throughput advantage.

**Fallback if Phase 5 baseline comparison shows weak OCR calibration:**
`Qwen/Qwen2.5-VL-32B-Instruct` served at FP8 via vLLM's on-the-fly
quantization. Denser, slightly higher quality on hard visual reasoning, 2–3×
slower per page.

## Why This Matters

The project's #1 time sink is fix-then-regression cycles — a change that
improves one book silently breaks four others because nobody visually
inspected every page of every test book. Current per-page Claude Vision cost
(roughly $0.10–$0.30 per page at Sonnet pricing with 1024×1024 images) makes
full-book scans prohibitive on a 400-page book: that's $40–$120 per regression
run across a 6-book test corpus. Local inference drops that to zero marginal
cost, unlocking the regression loop the project actually needs.

Quoting CLAUDE.md:

> The #1 time sink is fix-then-regression cycles. Changes to heading levels
> cascade into TOC nesting and Calibre compatibility. A fix for one book has
> broken 4 others multiple times.

## Non-Goals

- Replacing Claude Vision entirely. Claude remains the escalation tier for
  low-scoring pages and the source-of-truth for ship/no-ship decisions on
  audit-critical books.
- Rewriting the rubric. `tools/visual_qa_rubric.md` stays as-is — it's a
  prompt-level contract, not an implementation detail.
- Changing the report schema. `import_vqa_reports.py` and downstream consumers
  must keep working unchanged.

## Current State — What We're Changing

**File:** `tools/visual_qa.py` (871 lines)

Key functions we'll touch:

- `build_vision_request()` — constructs Claude-specific payload with
  `anthropic-version` header and `source.type = base64` image blocks
- `call_claude_vision()` — direct REST POST to
  `https://api.anthropic.com/v1/messages` with retry logic
- `parse_qa_response()` — strips markdown fences, JSON-parses
- `select_sample_pages()` — caps pages at `max_samples=8` by default
- `build_report()` — assumes Claude cost model for per-token pricing

Related files:

- `tools/visual_qa_rubric.md` — prompt text, unchanged
- `tools/import_vqa_reports.py` — consumes report JSON, unchanged
- `tools/vqa_quality_baseline.md` — baseline metrics to regression-test against
- `.env` — adds `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_VISION_MODEL`
- `settings.json` — new `visual_qa.provider` field (`claude` | `local`)

## Architecture

### Provider abstraction

Extract the vision call into a provider interface so `visual_qa.py` stays
thin:

```
tools/
├── visual_qa.py                   # orchestration, unchanged flow
└── llm_providers/
    ├── __init__.py
    ├── base.py                    # VisionProvider abstract interface
    ├── claude_provider.py         # existing Claude path, extracted
    └── local_provider.py          # new vLLM OpenAI-compatible client
```

The `VisionProvider` interface:

```python
class VisionProvider(Protocol):
    name: str
    cost_model: dict  # per-million-token rates or {"local": True}

    def build_request(
        self,
        page_images: list[tuple[int, bytes]],
        rubric_text: str,
        model: str,
    ) -> dict: ...

    def call(self, payload: dict) -> tuple[str, int, int]:
        """Returns (raw_response_text, input_tokens, output_tokens)."""
```

Both providers return the same response shape, so
`parse_qa_response()` and `build_report()` need no changes beyond the cost
model lookup (which moves into `VisionProvider.cost_model`).

### Local provider specifics

vLLM exposes `/v1/chat/completions` with OpenAI's multimodal format:

```python
{
  "model": "qwen3-vl",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "--- Page 5 ---"},
      {"type": "image_url",
       "image_url": {"url": "data:image/png;base64,..."}},
      ...
      {"type": "text", "text": "Evaluate all pages above..."}
    ]
  }],
  "max_tokens": 8192,
  "temperature": 0.0,
  "response_format": {"type": "json_object"}
}
```

Notes:

- `response_format` + JSON-object mode removes the markdown-fence stripping
  problem entirely on the local path.
- System prompt goes in a separate `{"role": "system", ...}` message, not a
  top-level `system` field.
- No `x-api-key` header; no retry-for-529 logic (local doesn't overload the
  same way). Replace retries with a simple connection-error retry.
- Base URL comes from `LOCAL_LLM_BASE_URL` env var, default
  `http://localhost:8000/v1`.

### Full-book mode

Add `--all-pages` flag:

- Skips `select_sample_pages()` entirely; renders every page
- Batches pages into groups of N (default 8, configurable via
  `--batch-size`) — a single Qwen3-VL call with 8 images in context
- Walks batches sequentially, aggregates the per-batch `pages` arrays into
  one report
- Memory guard: stream rendered PNGs to tempdir, load only the current batch
  into memory

Batch size matters because vLLM latency scales with context length. Needs
tuning on real hardware — start at 8 pages per call and measure.

### Escalation tier

New CLI flag `--escalate-below SCORE` (default 50):

- After the local pass, pages with `score < SCORE` or `pass=false` get
  re-evaluated individually on Claude Vision
- Escalated pages write a second report entry with `escalation: true`
- Final report merges: local result for high-confidence pages, Claude result
  for escalated pages, with provenance recorded per page

This is the critical "local as filter, Claude as judge" pattern from the
brainstorm doc.

## Configuration Changes

**Updated 2026-04-17.** Model IDs below reflect the actual sb-chat `served-model-name`
(`qwen3.5-35b-a3b-fp8`) rather than the obsolete `qwen3-vl` placeholder.

**`.env` additions:**

```bash
LOCAL_LLM_BASE_URL=http://localhost:8000/v1
LOCAL_LLM_VISION_MODEL=qwen3.5-35b-a3b-fp8
LOCAL_LLM_EMBEDDING_URL=http://localhost:8001/v1
LOCAL_LLM_EMBEDDING_MODEL=qwen3-embedding-4b
```

**`settings.json` additions (under existing `visual_qa` section):**

```json
"visual_qa": {
  "provider": "local",
  "claude_model": "claude-sonnet-4-6",
  "local_model": "qwen3.5-35b-a3b-fp8",
  "local_base_url": "http://localhost:8000/v1",
  "batch_size": 8,
  "escalate_below_score": 50,
  "max_pages": 8,
  "all_pages_default": false
}
```

Existing `max_pages` behavior preserved for backwards compatibility.

**`requirements.txt` additions:**

- `openai>=1.50.0` — thin client for OpenAI-compatible endpoints. Pinned
  loosely because we only use chat completions and embeddings.

## Step-by-Step Implementation

### Phase 1 — Provider abstraction (no behavior change) — STATUS: CODE COMPLETE, BASELINE PENDING

**Worktree:** `.worktrees/worktree-SCRUM-274-vqa-provider-abstraction`
**Branch:** `worktree/SCRUM-274-vqa-provider-abstraction`
**Commit:** `0014c1c refactor(SCRUM-274): extract VisionProvider abstraction from visual_qa`

1. ✅ Created `tools/llm_providers/__init__.py`, `base.py`, `claude_provider.py`
2. ✅ Moved `build_vision_request()` and `call_claude_vision()` into
   `claude_provider.py` byte-for-byte, wrapped in the `VisionProvider` interface
3. ✅ Updated `visual_qa.py` to instantiate `ClaudeVisionProvider` and call
   through the interface; removed unused `base64` and `time` top-level imports
4. ✅ Added `tests/test_vision_provider_phase1.py` — 13 pin tests covering
   payload shape, base64 encoding, multi-page ordering, the trailing
   instruction text, the cost model for all three Claude tiers + unknown-model
   fallback, and `build_report` integration. All pass.
5. ✅ CLI `--help` output unchanged (verified in worktree)
6. ✅ `tools/verify-manifest.ps1` reports all 16 critical files, 22 exports,
   10 Python CLI modes, 17 config keys intact
7. ✅ `tools/test_voice_tags.py` — 88 cross-repo regression tests still pass
8. ⏳ **Bit-identical baseline run on all 6 test books — pending Joe**

**Gate (still open):** the bit-identical baseline run requires the user to
execute `visual_qa.py` against real KFX files with a live Claude API key
and compare the resulting JSON reports against pre-refactor baselines.

#### Bit-Identical Baseline Verification — Runbook

This is the only remaining Phase 1 gate. The procedure costs Claude API
tokens (roughly $1–3 for the 6-book sample-mode pass) but is the
authoritative confirmation that the refactor introduced zero behavior drift.

1. **Capture pre-refactor baseline (run from master):**

   ```powershell
   git checkout master
   $env:VQA_BASELINE_DIR = "f:\Projects\EbookAutomation\data\vqa_baseline_pre_274"
   New-Item -ItemType Directory -Force -Path $env:VQA_BASELINE_DIR | Out-Null
   foreach ($book in @("Oil Kings", "Mexico Illicit", "Lincoln Highway",
                        "Atomic Habits", "Sapiens", "Extreme Ownership")) {
       $kfx = Get-ChildItem "output\kindle\*$book*.kfx" | Select-Object -First 1
       py -3.12 tools\visual_qa.py --input $kfx.FullName `
           --output-dir $env:VQA_BASELINE_DIR
   }
   ```

2. **Capture post-refactor output (run from worktree):**

   ```powershell
   cd .worktrees\worktree-SCRUM-274-vqa-provider-abstraction
   $env:VQA_POST_DIR = "f:\Projects\EbookAutomation\data\vqa_baseline_post_274"
   New-Item -ItemType Directory -Force -Path $env:VQA_POST_DIR | Out-Null
   foreach ($book in @("Oil Kings", "Mexico Illicit", "Lincoln Highway",
                        "Atomic Habits", "Sapiens", "Extreme Ownership")) {
       $kfx = Get-ChildItem "..\..\output\kindle\*$book*.kfx" | Select-Object -First 1
       py -3.12 tools\visual_qa.py --input $kfx.FullName `
           --output-dir $env:VQA_POST_DIR
   }
   ```

3. **Diff the reports.** Token counts and `estimated_cost_usd` will vary
   slightly across runs because Claude's vision input tokens are not
   deterministic for identical images — that is expected and **not** a
   refactor bug. The structural fields that must match exactly are:

   ```powershell
   foreach ($book in @("Oil Kings", "Mexico Illicit", "Lincoln Highway",
                        "Atomic Habits", "Sapiens", "Extreme Ownership")) {
       $pre  = Get-Content "$env:VQA_BASELINE_DIR\*$book*_visual_qa_report.json" -Raw | ConvertFrom-Json
       $post = Get-Content "$env:VQA_POST_DIR\*$book*_visual_qa_report.json" -Raw | ConvertFrom-Json

       $deltas = @()
       if ($pre.pages_sampled  -ne $post.pages_sampled)  { $deltas += "pages_sampled" }
       if ($pre.pages_total    -ne $post.pages_total)    { $deltas += "pages_total" }
       if ($pre.dpi            -ne $post.dpi)            { $deltas += "dpi" }
       if ($pre.model          -ne $post.model)          { $deltas += "model" }
       if ($pre.pass_threshold -ne $post.pass_threshold) { $deltas += "pass_threshold" }
       if (($pre.pages | ConvertTo-Json -Compress) -ne ($post.pages | ConvertTo-Json -Compress)) {
           # Per-page array structure must match — score values may drift slightly
           # due to Claude non-determinism, but the page list and shape must be identical.
           if ($pre.pages.Count -ne $post.pages.Count) { $deltas += "pages.Count" }
       }

       if ($deltas) {
           Write-Warning "$book — structural drift in: $($deltas -join ', ')"
       } else {
           Write-Host "$book — STRUCTURAL MATCH" -ForegroundColor Green
       }
   }
   ```

4. **What "bit-identical" means in practice.** Phase 1 guarantees:
   - Same Claude API payload (verified by `test_vision_provider_phase1.py`)
   - Same report JSON keys, same pricing tier, same threshold logic
   - Same per-page response shape, same category aggregation, same
     `top_issues` filtering

   It does NOT guarantee:
   - Identical `score` values (Claude vision is mildly non-deterministic
     even at temperature 0 for identical images)
   - Identical `input_tokens` / `output_tokens` (Anthropic's tokenizer
     occasionally returns different counts for identical inputs)
   - Identical `summary` text (free-form generation)

   **Pass criterion:** all 6 books log "STRUCTURAL MATCH" in step 3, AND
   per-page score values are within ±5 points of baseline (Claude jitter).

5. **If structural drift is detected:** stop, do not proceed to Phase 2.
   Diff the two report JSON files with a structural diff tool and bisect
   the change. The refactor commit (`0014c1c`) is the only suspect.

After step 4 passes, mark Phase 1 status as `completed` and proceed to
Phase 2.

### Phase 2 — Local provider

**Updated 2026-04-17 — tracked on SCRUM-275.** Target endpoint changed to
sb-chat (`http://localhost:8000/v1`, model id `qwen3.5-35b-a3b-fp8`). Step 2
below gains a hard requirement for `enable_thinking=False`, which the probe
proved is load-bearing.

1. Create `tools/llm_providers/local_provider.py` using the `openai` client
   pointed at `LOCAL_LLM_BASE_URL`
2. Implement `build_request()` producing OpenAI chat-completions format with:
   - `image_url` content blocks (`data:image/png;base64,...` URIs)
   - `response_format={"type": "json_object"}`
   - **`extra_body={"chat_template_kwargs": {"enable_thinking": False}}` —
     mandatory.** With thinking enabled, sb-chat's `--reasoning-parser qwen3`
     consumes the entire `max_tokens` budget on `<think>` blocks that get
     routed into a non-standard `reasoning` field, leaving `message.content`
     empty and `finish_reason=length`. Smoke-test evidence:
     `data/debug/qwen_vqa_probe/out_20260418T025912Z/` (thinking on, 42s,
     0 bytes content) vs `out_20260418T030235Z/` (thinking off, 2.5s, clean
     JSON, score 95). In-prompt `/no_think` does **not** work.
   - `temperature=0.1` + `frequency_penalty=0.3` recommended to avoid the
     repetition loops observed with `temperature=0` on visual inputs.
3. Implement `call()` with connection-error retries (3 attempts, 5s backoff)
4. Add `--provider local|claude` CLI flag; default from `settings.json`
5. Run against a single test book in sample mode (8 pages), compare report
   to Claude baseline — scores should be within reasonable agreement range

**Gate:** local provider produces valid report JSON matching schema, no
exceptions on all 6 test books in 8-page sample mode.

### Phase 3 — Full-book mode

1. Add `--all-pages` and `--batch-size` flags to argparse
2. Add `select_all_pages()` path that skips sampling
3. Add `batch_iterator()` that groups rendered pages into chunks
4. Rewrite the main loop to aggregate per-batch responses into one report
5. Add tempdir-based streaming so full 400-page books don't blow memory
6. Run full-book mode on Oil Kings (the most complex book) — measure
   wall-clock time, peak VRAM, peak RAM, total pages processed

**Gate:** full-book run completes on Oil Kings without OOM, total time
within reasonable bound (target: under 30 min for 400 pages).

### Phase 4 — Escalation tier

1. Add `--escalate-below` flag
2. After local pass, filter pages by score threshold
3. Re-render those pages individually, send to Claude provider
4. Merge results with `escalation: true` marker per escalated page
5. Update report schema doc to describe the new field

**Gate:** escalation loop correctly routes low-confidence pages, final
report has accurate provenance per page.

### Phase 5 — Baseline comparison and documentation

1. Run full-book mode on all 6 test books
2. Produce a side-by-side comparison table: sample-mode Claude scores vs
   full-book local scores vs escalated final scores
3. Document findings in `docs/superpowers/analysis/2026-04-xx-local-vqa-baseline.md`
4. Update `CLAUDE.md` Testing section to mention the new default flow
5. Update `feature-manifest.json` with new CLI flags and provider paths
6. Run `tools/verify-manifest.ps1` to confirm no features regressed

**Gate:** baseline comparison shows local-mode catches at least the same
regressions Claude sample-mode caught, plus at least one new regression on
an unsampled page.

## Verification Strategy

Each phase has a gate above. Global success criteria:

1. **Zero regressions on existing Claude workflow.** Running `visual_qa.py`
   with `--provider claude` and existing defaults produces bit-identical
   output to pre-change behavior on all 6 test books.
2. **Local provider works on all 6 books.** No exceptions, valid JSON
   reports, reasonable scores.
3. **Full-book mode completes without OOM.** Oil Kings (largest complexity)
   is the canary.
4. **Escalation catches low-confidence pages.** Injected test case: a
   deliberately broken page should trigger escalation and reach Claude.
5. **Feature manifest verification passes.** No existing CLI flags, configs,
   or exports removed.
6. **Cost telemetry shows reduction.** Running full test suite end-to-end
   should show Claude Vision spend drop by >90% compared to prior full-mode
   runs.

## Risks and Mitigations

**Updated 2026-04-17.** Added thinking-mode row (now mitigated but kept for
history). Deployment-coupled rows that applied to a dedicated VL container
are retained but no longer load-bearing since sb-chat is managed elsewhere.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| sb-chat thinking mode burns full max_tokens on `<think>` blocks, empties `message.content` | **resolved** | high | **Always** pass `extra_body={"chat_template_kwargs":{"enable_thinking":False}}`. In-prompt `/no_think` does not work because `--reasoning-parser qwen3` operates at the chat-template layer. Smoke-tested 2026-04-17. |
| sb-chat becomes unavailable (SecondBrain restarts, compose changes) | medium | medium | Add a preflight probe to `local_provider.py` that calls `/v1/models` before any VQA run; fail fast with a clear message if the model isn't loaded. Coordinate breaking-change notifications via the SB-34 dependency entry. |
| Qwen3.5-35B score calibration drifts from Claude baseline | high | medium | Run side-by-side comparison in Phase 5. Adjust rubric prompt or escalation threshold before declaring done. |
| Local model hallucinates issues not present on page | medium | medium | Escalation tier catches low-scoring pages. Track false-positive rate during Phase 5. Early probe (2026-04-17) showed zero hallucinations across 4 pages, but sample is small. |
| Temperature=0 triggers repetition loops on visual inputs | resolved | medium | Use `temperature=0.1` + `frequency_penalty=0.3`. Observed deterministic-mode looping on first probe run; fixed with slight temperature bump. |
| vLLM server crashes mid-book | low | medium | Add per-batch checkpointing — failed batches can be re-run without restarting the whole book. Sb-chat lifecycle now owned by SecondBrain. |
| Batch size too large → context overflow | medium | low | Start at 8, measure, tune. 65k context is plenty for 8 images + rubric. |
| ~~VRAM exhausted with both VL + embedding models loaded~~ | n/a | n/a | ~~Start with VL only; embedding model can be stopped during visual QA runs.~~ **Not applicable post-amendment** — sb-chat and embedding are managed by SecondBrain's compose, not this project. |
| Provider abstraction leaks Claude-isms | low | medium | Phase 1 gate requires bit-identical Claude output before touching local. |
| Response JSON varies between providers | medium | medium | Use JSON-object `response_format` on local; keep fence-stripping as defense in depth. Probe confirmed Qwen honors the flag. |

## Outstanding Questions (Non-Blocking)

1. **Escalation threshold default.** Is 50 the right score floor? Depends on
   how aggressive Claude Sonnet has been historically — check recent VQA
   reports before finalizing.
2. **Embedding server coexistence.** Default behavior during full-book VQA
   runs: stop the embedding server automatically, or require the operator
   to stop it manually? Leaning toward a startup check that refuses to run
   if both servers are up and `--all-pages` is set.

## Effort Estimate

- **Phase 1** (abstraction): 1 session, Sonnet
- **Phase 2** (local provider): 1 session, Sonnet
- **Phase 3** (full-book mode): 1 session, Sonnet
- **Phase 4** (escalation): 0.5 session, Sonnet
- **Phase 5** (baseline + docs): 0.5 session, Opus (reviews findings)

Total: ~2.5 Sonnet sessions + 0.5 Opus session. Ship in a week with normal
pace.

## Rollout

- Phase 1 lands as its own commit with `refactor:` prefix — pure refactor, no
  behavior change.
- Phases 2–4 land as separate commits with `feat:` prefix. Each commit keeps
  `--provider claude` working so rollback is one flag away.
- Phase 5 documentation commit with `docs:` prefix.
- Default `provider` in `settings.json` stays `claude` until baseline
  comparison (Phase 5) confirms local is safe to promote.

## Related Work

- **Brainstorm:** `docs/brainstorms/2026-04-13-local-llm-integration-opportunities.md`
- **Current VQA:** `tools/visual_qa.py`, `tools/visual_qa_rubric.md`
- **Baseline:** `docs/superpowers/analysis/2026-03-24-vqa-quality-baseline.md`
- **AI design precedent:** `docs/AI_Quality_Pass_Design.md`
- **Cost baseline:** `docs/api-cost-audit.md`
- **Phase 2 ticket (post-amendment):** SCRUM-275 — "Wire sb-chat Qwen3.5-35B vision into visual_qa.py as local provider"
- **Cross-project reference (capability discovery):** SB-34 — "Document sb-chat multimodal (vision) capability for consumer projects"
- **Smoke-test evidence (2026-04-17):** `data/debug/qwen_vqa_probe/qwen_vqa_probe.py` + `data/debug/qwen_vqa_probe/out_*/` (4 pages across Oil Kings and Mexico Illicit — zero hallucinations, 3.3 s/page avg, one real pipeline bug caught)
