---
title: "feat(SCRUM-283): cloud-hosted VLM evaluation for VQA grader-leniency ceiling"
type: feat
status: complete-partial
date: 2026-04-19
origin: docs/plans/2026-04-18-004-feat-scrum-280-p2-calibration-grounding-plan.md
predecessor: docs/solutions/scrum-280-local-vqa-calibration-patterns.md
ticket: SCRUM-283
parent_ticket: SCRUM-280
related_tickets: [SCRUM-275, SCRUM-279, SCRUM-281, SCRUM-282]
scope: Cloud VLM R2-gate smoke across 6-book corpus; model-class escalation ladder if A3B fails; routing recommendation vs SCRUM-281 Option D.
target_model: sonnet
outcome: Partial close. Cloud Qwen3-VL-30B-A3B-Instruct cleared the SCRUM-280 academic-book ceiling (detection misses 7→1, 6→0, 7→0 on Oil Kings/Mexico/RotG) but failed formal R2 (corpus mean |Δ| 18.48) due to Python-in-Easy-Steps technical-layout blind spot. Unit 5b dense Qwen-VL-Max probe was worse than A3B broadly (20.62 |Δ|, 7-8 detection misses every book) — dense-vs-MoE hypothesis falsified. Recommendation: cloud-A3B primary + response-level fingerprint fallback to Claude (hybrid). SCRUM-281 Option D promoted from optional to required. See docs/solutions/scrum-283-cloud-vlm-evaluation.md.
---

# feat(SCRUM-283): cloud-hosted VLM evaluation for VQA grader-leniency ceiling

## Overview

SCRUM-280 partial-closed with R2 unmet on the two academic books (Oil Kings, Mexico Illicit) at what Investigation (C) identified as an MoE active-parameter ceiling for structural visual judgment. The parent plan (SCRUM-275) listed Qwen2.5-VL-32B as the primary model-swap fallback but deferred it due to shared-stack VRAM saturation on sb-chat. Cloud inference bypasses the VRAM constraint entirely — no second GPU, no dedicated vision container, pay-per-token instead of pay-per-VRAM-hour.

This plan drives a targeted R2-gate evaluation of `qwen/qwen3-vl-30b-a3b-instruct` on OpenRouter (same architecture class as local but newer reasoning weights — hypothesis: the failure mode is MMMU-shaped reasoning, not DocVQA-shaped perception). If A3B fails, a cost-ordered escalation ladder probes dense Qwen3-VL-32B, Qwen-VL-Max, and Qwen3-VL-235B-A22B-Thinking before falling back to the SCRUM-281 hybrid path.

The `CloudVLProvider` class shipped pre-plan as a design artifact; this plan lands the CLI integration that makes it reachable, the comparison harness that evaluates R2 across candidate models, and the routing decision that determines whether SCRUM-281 Option D ships as "optional" or "required."

## Problem Frame

Local Qwen3.5-35B-A3B post-SCRUM-280-two-pass-calibrated shipped corpus mean |Δ| 17.0 (48% improvement from 33.0) but failed R2 on academic books at ~22–28 |Δ|. Investigation (C) documented 11 zero-local-issues pages where Claude detected moderate-to-major defects, with failures clustering by defect category (`paragraph_flow`, `heading_formatting`, `text_integrity`) but diffuse by page type (cover, front-matter, body, chapter_start, back_matter all affected).

The failure taxonomy indicates the ceiling is **schema knowledge of correct ebook typography**, not **character-pattern matching** — the one defect Qwen caught on Mexico p234 was a URL broken-space (`htt p://...`), a mechanical character-sequence pattern. All misses required knowing what correct paragraph-flow, heading hierarchy, and text-integrity should look like.

Per solutions-doc Lesson 4: MoE active-parameter ceiling for structural visual judgment is bounded-category + diffuse-page-type. Routing cannot bypass it by page type (no page-type cluster); it must be bypassed by either (a) a different model class entirely (this plan), or (b) response-level routing on `issues: []` empty-detection as a confidence fingerprint (SCRUM-281 Option D).

## Requirements Trace

From the SCRUM-283 ticket acceptance criteria:

- **R1.** Candidate VLM identified with verified pricing and access pattern — **pre-landed** in `tools/llm_providers/cloud_vl_provider.py` (`_CLOUD_PRICING` table dated 2026-04-19, OpenRouter as R2 smoke target, OpenAI-compatible API shape so Fireworks/Together work with base-URL swap only)
- **R2.** R2-gate smoke on 6-book corpus vs `data/vqa_baseline_post_274/`, same 8-page sampling, same rubric, no pipeline changes other than `--provider cloud`
- **R3.** Per-book corpus mean |Δ|, per-book |Δ|, detection-miss rate on Oil Kings / Mexico Illicit failure pages recorded in a reproducible format
- **R4.** Gate threshold: **R2(a)** corpus mean |Δ| < 15, **R2(b)** no per-book > 20 — identical to SCRUM-280
- **R5.** Pass → cost comparison vs SCRUM-281 Option D hybrid; routing recommendation. Fail → document ceiling and confirm SCRUM-281 Option D as required
- **R6.** Final configuration decision (cloud-primary / hybrid / claude-primary) committed to `config/settings.json` defaults with a load-bearing comment, OR partial close with SCRUM-281 re-scoped

## Scope Boundaries

- Primary change target: `tools/visual_qa.py` (CLI surface) + new `tools/compare_vqa_reports.py` (gate computation)
- CLI integration: **landed pre-plan** — `--provider cloud`, `--cloud-host {openrouter,fireworks,together}`, settings.json `visual_qa.cloud_host` / `visual_qa.cloud_model` defaults, provider-factory branch
- `tools/llm_providers/cloud_vl_provider.py`: **landed pre-plan** — no code changes expected in this plan unless a host-specific quirk surfaces (e.g., Fireworks schema enforcement differences)
- `tools/llm_providers/base.py` Protocol: unchanged — `CloudVLProvider` already satisfies the existing `VisionProvider` Protocol (intentionally preserved in SCRUM-280 Unit 4 sub-unit 4b-ii)
- `tools/visual_qa_rubric.md`: not modified — rubric is the contract, must evaluate identically across providers for the comparison to be valid
- `tools/llm_providers/local_provider.py`: not touched — this plan does not relitigate the local two-pass architecture
- `config/settings.json` schema: widened via optional `visual_qa.cloud_host` / `visual_qa.cloud_model` keys (already falls through to hardcoded defaults if absent)

### Deferred to Separate Tasks

- **Production routing integration** — if Unit 6 recommends hybrid or cloud-primary, the actual switch lands as a follow-up ticket. This plan produces the *recommendation*, not the production wiring
- **SCRUM-281 Option D implementation** — orthogonal ticket. This plan's outcome sets SCRUM-281's priority (required vs optional) but does not implement it
- **SCRUM-282 baseline source-format standardization** — orthogonal ticket. Lesson-5 drift is guarded-against in the comparison script (page-overlap assertion) but the proper fix lives in SCRUM-282
- **Fine-tuning / LoRA on cloud provider** — off the table. Cloud providers don't expose per-tenant fine-tunes at the relevant price points
- **Non-Qwen candidates (GPT-4o, Gemini 2.0 Flash)** — the ticket lists these; this plan narrows to Qwen-family because the failure-mode hypothesis (MMMU reasoning, not DocVQA perception) predicts same-class-better-reasoning fixes the ceiling. If all four Qwen escalations fail, a GPT-4o / Gemini probe is a legitimate follow-up ticket but not this plan's scope

## Context & Research

**Pre-landed code artifacts** (already in the repo on `master` before this plan executes):
- [tools/llm_providers/cloud_vl_provider.py](../../tools/llm_providers/cloud_vl_provider.py) — provider class, pricing table, OpenAI-compatible request shape
- [tools/visual_qa.py](../../tools/visual_qa.py) — CLI wired for `--provider cloud`, `--cloud-host`, factory branch at ~L840
- [tools/llm_providers/__init__.py](../../tools/llm_providers/__init__.py) — `CloudVLProvider` re-exported

**Pre-existing evidence and corpus**:
- `data/vqa_baseline_post_274/` — 6-book Claude baseline (KFX-source — no Lesson-5 drift vs cloud smoke)
- `data/scrum280_unit5_winning_smoke/` — 6-book local two-pass-calibrated smoke (corpus mean |Δ| 17.0 reference)
- `output/kindle/*.kfx` — 6-book test corpus per [CLAUDE.md Test Corpus](../../CLAUDE.md) table

**Hypothesis under test (from `cloud_vl_provider.py` docstring)**: "The failure mode is reasoning/calibration (MMMU-shaped), not vision accuracy (DocVQA-shaped), so jumping to a model with stronger reasoning at the same param class is the targeted fix."

**Counter-hypothesis to falsify in Unit 4**: If A3B fails R2 at roughly the same magnitude as local A3B (|Δ| > 20 on Oil Kings/Mexico Illicit), the architecture-class ceiling (Lesson 4) is confirmed and reasoning improvements within A3B class are insufficient. Dense-32B probe in Unit 5 becomes load-bearing.

**Cross-project constraint**: None for the cloud path — cloud inference is project-scoped, not shared-stack. In contrast, the current local path on sb-chat has a cross-project throughput concern flagged in `memory/project_sb_chat_shared_stack.md`. Successful cloud R2 pass would *reduce* sb-chat pressure by letting EbookAutomation opt out of local VQA.

## Key Technical Decisions

**D1. OpenRouter as primary host.** Lowest friction (single account reaches all Qwen SKUs), cheapest A3B tier at $0.13/$0.52 per M tokens, same OpenAI-compatible API as Fireworks/Together so escalation to a different host is a string swap. Trade-off: OpenRouter is a router, so latency is +100-300ms vs direct Fireworks. For a smoke this is noise; for production we'd re-evaluate.

**D2. Qwen3-VL-30B-A3B-Instruct as first probe despite A3B architecture class.** Pre-landed file docstring commits to this. The reasoning: SCRUM-280's ceiling was on Qwen3.5, this is Qwen3 (confusingly newer — 3.5 is the A3B MoE variant; 3-VL is a different newer lineage). Stronger reasoning weights at same active-parameter class tests the MMMU-vs-DocVQA hypothesis cheaply ($0.02/corpus) before committing to 5×-more-expensive dense or thinking-variant probes.

**D3. Comparison script as a new tool, not inline analysis.** SCRUM-280's mean-|Δ| analysis appears to have been ad-hoc (no committed comparison script). For SCRUM-283 we'll probe up to 4 models across the same corpus; a reusable `tools/compare_vqa_reports.py` pays for itself on the first escalation and becomes the canonical gate computation for any future VQA provider work.

**D4. Equal-weight corpus mean |Δ| primary, page-weighted secondary.** Equal-weight (mean of per-book means) prevents book-size bias in the corpus aggregate. Page-weighted (mean of per-page |Δ|) matches how SCRUM-280 likely computed it (same headline number 17.0 both ways when book page-counts are uniform). Script reports both; R2(a) gate is evaluated against equal-weight to match the spirit of "no book dominates the aggregate."

**D5. Detection-miss count as secondary signal, not gate.** Per-book count of `issues == []` pages-where-baseline-had-issues is a direct proxy for the SCRUM-280 Investigation (C) failure mode. It's not a formal gate (the R2 thresholds are the gate), but a cloud candidate that halves local's detection-miss count while nudging |Δ| gives a richer signal than |Δ| alone.

**D6. Partial-close posture per `memory/feedback_close_partial_over_force_pass.md`.** If the A3B probe lands |Δ| marginally above 15 and all escalations are within a narrow band, prefer documenting the ceiling + recommending SCRUM-281 hybrid over iterating on prompt hacks. The cloud probes either break the ceiling meaningfully or they don't; marginal passes aren't worth compounding on.

## Open Questions

- **OQ1.** Does OpenRouter's router transparently pass through the `json_schema` `response_format` to the underlying Qwen3-VL endpoint? OpenAI-compatible proxies sometimes accept the parameter but don't enforce it server-side. **Resolution path**: Unit 1 auth smoke validates this — if the response shape matches schema strictly (no extra fields, no page count drift), enforcement is upstream. If response validates loosely, we may need a client-side schema re-check in `CloudVLProvider.call()`.
- **OQ2.** Is the SCRUM-280 local baseline (`data/scrum280_unit5_winning_smoke/`) a fair comparison point for cloud A3B, given it's two-pass-calibrated? If cloud A3B is single-pass (which it is — pre-landed file mirrors local single-pass shape, no two-pass wrapping), we're comparing single-pass-cloud vs two-pass-local. **Resolution path**: Unit 4 computes both deltas (vs Claude baseline AND vs local two-pass) and reports them separately. Two-pass-cloud is a Unit 5.5 candidate only if single-pass cloud misses R2 by a small margin.
- **OQ3.** Do Fireworks and Together enforce `response_format` identically to OpenRouter at the same model SKU? If OpenRouter A3B fails schema but Fireworks A3B passes it, that's a provider-behavior variance hidden under "same model." **Resolution path**: deferred to Unit 5 escalation — if we probe Fireworks dense-32B and find schema drift, add a `CloudVLProvider` host-quirks test matrix.

## High-Level Technical Design

### CLI invocation contract (unchanged from local/claude)

```
py -3.12 tools/visual_qa.py \
  --input <book.kfx> \
  --provider cloud \
  --cloud-host openrouter \
  --model qwen/qwen3-vl-30b-a3b-instruct \
  --output-dir data/scrum283_unit<N>_<description>/
```

Defaults resolve via env var → settings.json → hardcoded, matching the local-provider three-tier pattern. For the smoke we'll rely on hardcoded defaults; no `config/settings.json` changes required.

### Comparison harness contract

New script `tools/compare_vqa_reports.py`:

```
py -3.12 tools/compare_vqa_reports.py \
  --candidate data/scrum283_unit3_6book_smoke_a3b/ \
  --baseline  data/vqa_baseline_post_274/ \
  [--secondary data/scrum280_unit5_winning_smoke/] \
  [--json-out data/scrum283_unit4_gate_result.json]
```

Outputs:
- Markdown table to stdout: per-book `pages_overlap`, `mean_|Δ|_vs_baseline`, `max_page_|Δ|`, `detection_misses` (candidate issues-empty pages where baseline had ≥1 issue), `[secondary] mean_|Δ|_vs_secondary`
- Corpus summary row: equal-weight mean |Δ|, page-weighted mean |Δ|, max per-book |Δ|, R2(a) / R2(b) verdict
- JSON summary (`--json-out`) matching the markdown table structure for programmatic consumption in Unit 6 cost/routing analysis
- Exit code: 0 if R2 passes, 1 if fails, 2 if page-overlap guard fails on any book (Lesson-5 drift alarm)

### Page-overlap assertion (Lesson-5 guard)

For each book, compute `|candidate.page_numbers ∩ baseline.page_numbers|`. If overlap < min(candidate.pages_sampled, baseline.pages_sampled), warn and mark that book's |Δ| as "partial — {k}/{n} pages overlap." If overlap < 50%, hard-fail with exit 2 — the comparison is not trustworthy.

Both `data/vqa_baseline_post_274/` and cloud smoke run on the same KFX → Calibre-PDF → deterministic-sampler path, so overlap should be 100%. The guard is belt-and-suspenders — if SCRUM-282 is still open and a baseline regenerates from a different source format mid-project, the guard will catch it before an invalid |Δ| ships as a gate verdict.

### Detection-miss heuristic

Per page: `candidate.pages[i].issues == []` AND `baseline.pages[j].issues != []` (same `page_number`). Count per book. This is the direct fingerprint from SCRUM-280 Investigation (C) — zero-local-issues pages where Claude detected moderate-to-major defects. Reported alongside |Δ| as a secondary diagnostic, not a gate.

## Implementation Units

### Unit 1 — Auth + schema plumbing (≤ 15 min, ~$0.001)

**Execute:**
```powershell
py -3.12 tools/visual_qa.py `
  --input "output/kindle/Python in easy steps, 2nd Edition - Mike McGrath.kfx" `
  --provider cloud --cloud-host openrouter --max-pages 2 `
  --output-dir data/scrum283_unit1_auth_smoke/
```

**Expected output:** one JSON report, `pages[]` length == 2, `token_usage.estimated_cost_usd > 0`, no `OutputTruncatedError` / `PageCountMismatchError` / openai-library 400/401.

**Gate:** environment and auth work; response schema enforcement observed upstream (OQ1 resolved).

**Stopping rule:** any error → diagnose before Unit 2. Credential errors → verify `.env` parsing; schema 400 → check OpenRouter's `response_format` support for Qwen3-VL-30B-A3B specifically (may require host-specific payload shim in `CloudVLProvider`).

### Unit 2 — Single-book full smoke (≤ 5 min, ~$0.003)

**Execute:**
```powershell
py -3.12 tools/visual_qa.py `
  --input "output/kindle/Python in easy steps, 2nd Edition - Mike McGrath.kfx" `
  --provider cloud --cloud-host openrouter `
  --output-dir data/scrum283_unit2_single_book_a3b/
```

**Expected output:** JSON report matching baseline report shape; `pages[].page_number` set overlaps the `data/vqa_baseline_post_274/Python in easy steps...` page set (Lesson-5 guard pre-check).

**Gate:** end-to-end shape parity, page overlap ≥ 75% (8/8 ideal; 6/8 acceptable given deterministic sampler stability). The single-book |Δ| is observational, not gate-bearing here — R2 evaluates against the full corpus.

**Stopping rule:** schema mismatch → halt and fix `CloudVLProvider` shape. Page overlap < 75% → SCRUM-282 pre-work required before Unit 3.

### Unit 3 — Full 6-book corpus smoke — A3B (≤ 20 min, ~$0.02)

**Execute (PowerShell loop over the 6-book test corpus):**
```powershell
$books = @(
  "The Oil Kings_ How the U - Cooper, Andrew Scott.kfx",
  "Mexico's Illicit Drug Networks and the State Reaction - Nathan P. Jones.kfx",
  "The Return of the Gods - Jonathan Cahn.kfx",
  "Atomic Habits Tiny Changes, Remarkable Results An Easy & Proven Way to Build Good Habits & Break Bad Ones - James Clear.kfx",
  "Decline of the West Volumes 1 and 2 - Oswald Spengler.kfx",
  "Python in easy steps, 2nd Edition - Mike McGrath.kfx"
)
foreach ($book in $books) {
  py -3.12 tools/visual_qa.py `
    --input "output/kindle/$book" `
    --provider cloud --cloud-host openrouter `
    --output-dir data/scrum283_unit3_6book_smoke_a3b/
}
```

**Gate (non-R2 — completeness check):** six JSON reports present in output dir, no fatal Python exceptions mid-loop.

**Stopping rule:** >1 book raises a fatal error → halt and diagnose (likely rate-limit or provider-side instability). Partial data is not a valid smoke.

### Unit 4 — Gate computation + detection-miss diagnosis (≤ 10 min, $0)

**Deliverable: `tools/compare_vqa_reports.py`** (written in parallel with plan per user direction).

**Execute:**
```powershell
py -3.12 tools/compare_vqa_reports.py `
  --candidate data/scrum283_unit3_6book_smoke_a3b/ `
  --baseline  data/vqa_baseline_post_274/ `
  --secondary data/scrum280_unit5_winning_smoke/ `
  --json-out  data/scrum283_unit4_gate_result_a3b.json
```

**Gate (R2, the primary ticket gate):**
- **R2(a)** equal-weight corpus mean |Δ| < 15
- **R2(b)** no per-book |Δ| > 20
- Both must hold for pass

**Stopping rule:** R2 pass → Unit 6. R2 fail → Unit 5. Detection-miss count is reported and logged but does not gate.

### Unit 5 (conditional) — Model-class escalation ladder

Triggered only if Unit 4 fails R2. Candidates cost-ordered ascending; stop at first pass, partial-close if all fail:

**5a. Fireworks `qwen3-vl-32b-instruct`** (dense 32B, $0.50/$0.50 per M — ~$0.04/corpus)
- Hypothesis: dense vision circuit (~10× effective-vision-circuit vs A3B per Lesson 4) resolves bounded-category ceiling
- Output: `data/scrum283_unit5a_6book_smoke_dense32b/`

**5b. OpenRouter `qwen/qwen-vl-max`** (dense flagship, $0.52/$2.08 per M — ~$0.06/corpus)
- Hypothesis: flagship vision weights + more capacity bridge schema knowledge gap on academic books
- Output: `data/scrum283_unit5b_6book_smoke_qwen_vl_max/`

**5c. OpenRouter `qwen/qwen3-vl-235b-a22b-thinking`** (MoE + native reasoning, $0.26/$2.60 per M — ~$0.10/corpus)
- Hypothesis: reasoning-mode inference surfaces the schema-knowledge judgment that instruct-mode elides
- Output: `data/scrum283_unit5c_6book_smoke_thinking/`

**Execution pattern identical to Unit 3** — PowerShell loop, different `--model` per unit. Comparison script (Unit 4) re-run per output dir.

**Stopping rule:** first candidate to pass R2 → Unit 6 with that candidate as the recommendation. All three fail → partial close, Unit 6 documents ceiling + confirms SCRUM-281 Option D as required path.

### Unit 6 — Routing recommendation and close-out

**Inputs:** Unit 4 + any Unit 5 gate results, plus production-volume assumption (default: 20 books/month, 8-page VQA sample per book = 160 pages/month).

**Computations:**
- Monthly cost per routing strategy:
  - Cloud-primary (winning candidate): input tokens × 160 × input-price + output tokens × 160 × output-price
  - Hybrid (SCRUM-281 Option D estimate): local for ~70% of pages (no cost) + Claude for ~30% of pages on empty-detection (Claude pricing × 0.3 × 160)
  - Claude-primary: 160 × Claude pricing
- Quality comparison: R2 gate pass/fail per strategy (hybrid requires SCRUM-281 implementation data — if SCRUM-281 is still unshipped, document "pending" for hybrid-path quality)

**Recommendation decision table:**
| Cloud R2 outcome | Recommendation |
|---|---|
| A3B passes R2 cleanly (|Δ| < 12) | Cloud-primary A3B — SCRUM-281 becomes optional |
| A3B passes R2 marginally (12–15) | Hybrid (cloud A3B + Claude on empty-detection) — SCRUM-281 Option D still load-bearing |
| A3B fails, Unit 5 candidate passes | Cloud-primary with that candidate — cost vs Claude-primary determines final pick |
| All fail | Partial close — SCRUM-281 Option D required; SCRUM-283 filed as "ceiling documented, no local remedy"; optional GPT-4o / Gemini probe as new ticket |

**Deliverable:** Recommendation written to `docs/solutions/scrum-283-cloud-vlm-evaluation.md` (compound knowledge doc) with the gate evidence table, cost table, and decision rationale. PR opens referencing SCRUM-283 + linking to SCRUM-281 with status update.

## System-Wide Impact

- **`config/settings.json`**: no schema change required for the smoke. If Unit 6 recommends cloud-primary or hybrid as the production default, the follow-up ticket changes `visual_qa.provider` default and adds `visual_qa.cloud_host` / `visual_qa.cloud_model` keys.
- **sb-chat shared stack**: no change during this plan. A successful cloud-primary outcome *reduces* sb-chat load by letting EbookAutomation opt out of local VQA. Flag as `NEW DEPENDENCY: EbookAutomation → OpenRouter` in session summary at plan close.
- **`data/` directory**: six new subdirectories during execution (`scrum283_unit1_`..`scrum283_unit5c_`). All are gitignored per existing `data/scrum280_*` precedent; they're evidence artifacts, not source.
- **`output/kindle/`**: read-only — no new KFX artifacts produced. This plan consumes the test corpus, does not extend it.
- **Existing tests**: `tools/test_pipeline.py --quick` unaffected — no pipeline-code changes. `tools/verify-manifest.ps1` — comparison script is a new tool, add it to `feature-manifest.json` in Unit 4.

## Risks & Dependencies

**Risks:**
- **R_A. OpenRouter rate limits / availability.** Free-tier rate limits may throttle the corpus smoke mid-loop. Mitigation: smoke budget is $0.02 — well within OpenRouter paid-tier daily limits. If rate-limited, `CloudVLProvider.call()` already has 3-retry exponential backoff.
- **R_B. Schema-enforcement variance across hosts.** OQ1. If OpenRouter loosely enforces `response_format`, downstream parsing may accept malformed outputs that would error on local vLLM. Mitigation: `PageCountMismatchError` belt-and-suspenders guard in `CloudVLProvider.call()` catches the worst case.
- **R_C. Baseline page-selection drift (Lesson 5).** If `data/vqa_baseline_post_274/` was captured against a slightly different Calibre-PDF rendering than today's conversion produces, per-page |Δ| becomes misleading. Mitigation: comparison-script page-overlap guard will surface this explicitly as partial/hard-fail, not hide it in an aggregated number.
- **R_D. Cloud cost attribution inaccuracy.** `CloudVLProvider.estimate_cost()` relies on a hardcoded pricing table that can drift. Mitigation: table was verified 2026-04-19 per the file header; smoke total is $0.20 worst case (all Unit 5 escalations), so even 50% pricing drift is ~$0.10 — below meaningful-cost-error threshold.

**Dependencies:**
- `OPENROUTER_API_KEY` env var (`.env` entry or user scope) — verified set pre-plan
- `openai >= 1.109.1` — verified installed
- Test corpus KFX files in `output/kindle/` — verified present
- `data/vqa_baseline_post_274/` — verified present with 6 books
- `data/scrum280_unit5_winning_smoke/` — verified present with 6 books (used for secondary comparison only; not a gate)

## Documentation / Operational Notes

- Close SCRUM-283 with either full-pass recommendation or partial-close per `memory/feedback_close_partial_over_force_pass.md`
- File `docs/solutions/scrum-283-cloud-vlm-evaluation.md` compound-knowledge doc at close (outcome, cost evidence, routing decision, lessons — especially whether MMMU-vs-DocVQA hypothesis held)
- Update `docs/solutions/scrum-280-local-vqa-calibration-patterns.md` Lesson 4 "How to apply" section with the SCRUM-283 outcome as a recorded data point
- Update SCRUM-281 ticket with the routing-optionality verdict (optional / required / re-scoped)
- If cloud-primary recommendation lands, add a one-line runbook change to `CLAUDE.md` noting the default `visual_qa.provider` and the per-host `<HOST>_API_KEY` env-var convention

## Sources & References

- Parent ticket plan: [docs/plans/2026-04-18-004-feat-scrum-280-p2-calibration-grounding-plan.md](2026-04-18-004-feat-scrum-280-p2-calibration-grounding-plan.md)
- Compound knowledge: [docs/solutions/scrum-280-local-vqa-calibration-patterns.md](../solutions/scrum-280-local-vqa-calibration-patterns.md)
- Pre-landed provider class: [tools/llm_providers/cloud_vl_provider.py](../../tools/llm_providers/cloud_vl_provider.py)
- Pre-landed CLI integration: [tools/visual_qa.py](../../tools/visual_qa.py) (`--provider cloud`, `--cloud-host`, factory branch)
- Rubric contract: [tools/visual_qa_rubric.md](../../tools/visual_qa_rubric.md)
- SCRUM-281 ticket (dependent): routing remediation — optional/required verdict set by this plan's Unit 6
- SCRUM-282 ticket (related): baseline source-format standardization — risk R_C mitigation in this plan, proper fix in SCRUM-282
- OpenRouter pricing (2026-04-19): `_CLOUD_PRICING` table in [cloud_vl_provider.py](../../tools/llm_providers/cloud_vl_provider.py#L44-L53)
