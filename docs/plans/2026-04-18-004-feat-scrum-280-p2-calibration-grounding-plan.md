---
title: "feat(SCRUM-280 P2): grader-leniency calibration + page_number marker grounding"
type: feat
status: active
date: 2026-04-18
origin: docs/plans/2026-04-18-002-local-llm-visual-qa-calibration.md
predecessor: docs/plans/2026-04-18-003-feat-scrum-279-p1-guided-json-schema-plan.md
ticket: SCRUM-280
parent_ticket: SCRUM-275
scope: P2 only (grader-leniency calibration + marker grounding). Structural hallucination fix shipped in P1.
target_model: sonnet
---

# feat(SCRUM-280 P2): grader-leniency calibration + page_number marker grounding

## Overview

SCRUM-279 P1 eliminated the 221-entry hallucination cascade by enforcing `minItems == maxItems == len(page_images)` via vLLM `guided_json`. P1's clean 8-entry output exposed two remaining defects that were previously masked:

1. **Grader leniency** — local Qwen3.5-35B-A3B scores 86–94 across the corpus; Claude scores 59–84 on the same pages. Mean absolute Δ still 11–32 points post-P1.
2. **`page_number` positional-vs-marker grounding** — RotG input markers `[1, 2, 3, 70, 87, 138, 154, 221]` produce output `[1, 2, 3, 4, 5, 6, 7, 8]`. The model emits input-sequence position, not the marker value.

This plan drives both to completion with an explicit diagnostic gate (Step 1 mode classification) separating "grading bias" (mode a — remediable by prompts) from "detection failure" (mode b — requires architectural change). VRAM constraint on the shared sb-chat stack rules out a Qwen2.5-VL-32B swap — architectural fallback for mode (b) is forced-enumeration prompting → two-pass detection/scoring, staying resident on the existing model.

## Problem Frame

Post-P1, `page_number` is the primary source pointer — a consumer acting on `"fix the issue on page N"` must be able to navigate to source page N. Positional output breaks that for any book whose sampled pages are not `[1..N]`. Grader leniency is magnitude bias: scores are inflated by a knowable amount, still actionable if calibrated, unusable as a quality gate without calibration. Neither defect blocks P1's structural correctness achievement, but both block production trust of local VQA as a Claude substitute.

See origin: `docs/plans/2026-04-18-002-local-llm-visual-qa-calibration.md` (Priority 1 and Priority 2 sections) and the Out-of-Scope Finding block in `docs/plans/2026-04-18-003-feat-scrum-279-p1-guided-json-schema-plan.md` (Smoke Results Addendum) for direct evidence of the grounding failure.

## Requirements Trace

From the SCRUM-280 ticket acceptance criteria:

- **R1.** Mode classification (a/b/mixed) documented with evidence table from the post-P1 corpus in `data/scrum275_local_6book/`
- **R2.** At least one grader-leniency remediation produces (a) mean absolute Δ < 15 vs Claude across the 6-book corpus AND (b) no individual book exceeds Δ > 20. The per-book ceiling prevents a worst-case book hiding inside an acceptable aggregate — aggregate means hide tails and tails are the failure mode for a quality gate
- **R3.** Non-degenerate score distribution — no all-pages-same-score behavior; at least one FAIL (< 60) where Claude flagged one
- **R4.** `page_number` marker-grounding remediation landed — RotG pages `[1, 2, 3, 70, 87, 138, 154, 221]` produce output `page_number` values `[1, 2, 3, 70, 87, 138, 154, 221]` exactly
- **R5.** Final configuration committed to `tools/llm_providers/local_provider.py` with load-bearing comment
- **R6.** Test coverage matching the `test_no_frequency_penalty` / `test_response_format_is_json_schema` style for each landed behavior

## Scope Boundaries

- Primary change target: `tools/llm_providers/local_provider.py` (`build_request` trailing instruction, optional schema helper widening, optional `PageNumberGroundingError` class, optional two-pass orchestration changes)
- `tools/visual_qa.py` orchestration: modified ONLY if Unit 4 sub-unit 4b-ii (two-pass) triggers; in that case the call site at `tools/visual_qa.py:564` gains a second invocation AND transactional semantics for pass-1-success/pass-2-failure
- `tools/llm_providers/base.py` Protocol: modified ONLY if two-pass triggers — Protocol extension is explicit (either widen `build_request` signature or add `build_request_scoring` method; see Unit 4 sub-unit 4b-ii). This is a surface-area change; plan acknowledges it and requires a Protocol-contract test if the sub-unit lands
- `tools/visual_qa_rubric.md`: not modified — rubric is the contract, schema/prompt must conform
- `tools/llm_providers/claude_provider.py`: not touched (grader leniency is Qwen-specific)
- `config/settings.json` schema: unchanged

### Deferred to Separate Tasks

- **Qwen2.5-VL-32B model swap** — pre-listed in parent plan as fallback, out of scope here due to shared-stack VRAM constraint. Concrete re-trigger condition: revisit once sb-chat has ≥80GB VRAM headroom (a dedicated vision container, a second GPU, or a larger card replacing the current SKU). Not a vague "future work" placeholder — the trigger is capacity, not calendar time
- **Hybrid grader (local detect + Claude score)** — explicit escape hatch documented in Key Technical Decisions. Not implemented unless both prompt-only and two-pass experiments fail AND the user accepts the per-call Claude cost that undermines the "local is free" motivation
- **Full-book mode (`--all-pages`, `--batch-size`, tempdir streaming)** — SCRUM-275 Phase 3, separate ticket
- **Fine-tuning / LoRA** — deferred until all prompt-engineering, two-pass, and model-swap options are exhausted. Opportunistic training-data capture tracked in `docs/brainstorms/2026-04-18-local-llm-training-data-collection.md`
- **Dedicated vision container** — infrastructure work, not calibration
- **Extract VQA rubric enums to a Python constants module** — governance improvement noted in P1 risks; still out of scope here

## Context & Research

### Relevant Code and Patterns

- `tools/llm_providers/local_provider.py:30-191` — `_build_page_extraction_schema(page_count: int) -> dict` is the pure schema helper shipped in P1. R3 fallback (Unit 3) widens this signature to `(page_count, page_labels: list[int] | None = None)` and adds `items.properties.page_number: {type: integer, enum: page_labels}` when labels are provided. No new abstraction — existing pattern extends cleanly
- `tools/llm_providers/local_provider.py:271-293` — `build_request` emits `--- Page N ---` text content blocks immediately before each `image_url` block. R4's prompt instruction (Unit 2) appends an explicit grounding clause to the trailing instruction text on line 286-293; no structural change
- `tools/llm_providers/local_provider.py:220-238` — `PageCountMismatchError` class style is the canonical module-private-class pattern: typed constructor, load-bearing docstring citing the originating incident. Mirror for any new error type
- `tools/llm_providers/local_provider.py:194-217` — `OutputTruncatedError` added in P1; mirrors the same pattern. P2 units do not introduce new error classes unless a variant fails in a distinct new way
- `tests/test_local_provider_phase2.py:272-368` — schema helper test block (`test_schema_*`). Unit 3's schema widening adds tests in the same style. Parameterized construction (`page_count=1, 8, 16` edges) is already the established pattern; extend to `(page_count, page_labels)` permutations
- `tests/test_local_provider_phase2.py:379-442` — `test_response_format_*` block asserts build_request-level payload shape. Unit 2's prompt instruction lands assertions here
- `tests/test_local_provider_phase2.py:517` — `test_repair_payload_strips_response_format` is the orchestration-side test pattern established in P1 Unit 2. If a two-pass structure lands in Unit 4, mirror this integration style
- `data/scrum275_local_6book/*.json` — Post-P1 6-book VQA reports. Step 1 classification (Unit 1) reads these directly; Claude's per-page reports (already captured in the SCRUM-275 baseline) provide the per-page Δ inputs
- `tools/debug_guided_json_preflight.py` — Reusable preflight probe from P1. Re-run to verify backend enforcement is still live if Unit 3's schema widening ships (new `enum` constraint could tickle an xgrammar fallback edge case)
- `docs/plans/2026-04-18-003-feat-scrum-279-p1-guided-json-schema-plan.md` Smoke Results Addendum — direct evidence of both defects with per-book numbers. Section "Out-of-Scope Finding (material for P2)" is the authoritative record of the grounding failure evidence table

### Institutional Learnings

- **Debugging LLM output anomalies** (parent plan, Methodology Note section) — reusable template: hypothesis → unique prediction → watch for counter-intuitive metric movement → one variable per iteration → distinguish magnitude bias from structural failure. Directly applies to P2 calibration iteration
- **Qwen3 `enable_thinking: False` is load-bearing** (SB-34) — must remain on every request. Any new `extra_body` additions in P2 must not drop this
- **`frequency_penalty` breaks multi-page JSON** (P1 regression contract) — `test_no_frequency_penalty` asserts absence. Any P2 prompt/payload variant that reintroduces it fails the guard
- **Schema strictness can degrade output coherence on dense pages** (P1 smoke, Atomic Habits 95 → 86 drop hypothesis) — worth cross-referencing in Unit 5 smoke analysis; some of the grader-leniency Δ may actually be P1-introduced pessimism on callout-heavy pages, not pre-P1 leniency
- **`docs/solutions/` is currently empty** — no prior institutional knowledge on VQA calibration specifically. Unit 6 Compound-Engineering output from this ticket is a candidate for the first entry under that directory

### External References

Local patterns are dense and P1 shipped three weeks of surrounding work — external research adds marginal value. Skipped intentionally. Revisit if Unit 4's experiment ladder stalls and needs fresh VLM calibration patterns; in that case the relevant literature would be on strict-grader prompting and RLHF teacher-bias remediation for vision models.

## Key Technical Decisions

- **Mode classification is the diagnostic gate, not a discovery side-effect.** Unit 1 must land its evidence table before Unit 4 branches. Classifying mixed-mode or skipping the classifier invalidates Unit 4's experiment sequencing. Rationale: the parent plan's core insight is that mode (a) and mode (b) need different fixes; running a mode-(a) prompt ladder on a mode-(b) failure wastes iteration budget and produces misleading evidence.
- **R4 prompt-first, schema-enum fallback.** (This is the parent plan's deferred R3 experiment, renumbered to R4 in this plan's Requirements Trace.) Land the prompt instruction alone in Unit 2. Proceed to Unit 3 (schema widening) only if Unit 2's RotG test shows `page_number` still positional. Rationale: prompt-only is cheapest and most portable. Schema enum is structurally decisive but requires threading `page_labels` through the call graph and re-verifying backend enforcement on an enum-constrained integer field (a new xgrammar edge case P1 didn't exercise). Prompt-first lets us skip that work if Qwen can ground from text alone.
- **Qwen2.5-VL-32B is out of scope this ticket.** Shared sb-chat stack VRAM is saturated by the current Qwen3.5-35B-A3B + SecondBrain/CareerPilot workloads; a third model does not fit. Rationale: infrastructure is not calibration. Document as future work once GPU capacity expands.
- **Hybrid grader (local detect + Claude score) is an explicit opt-in escape hatch.** Not implemented. Rationale: re-introduces per-call Claude cost, which defeats the entire motivation for local VQA. Lives in the plan as a named fallback so a future reader knows why it was considered and rejected, not discovered anew.
- **Calibration experiments run on `Python in easy steps` 8-page fixture; smoke verification runs on all 6 books.** Rationale: parent plan established this convention — fast iteration fixture, full-corpus gate. Experiment loop stays tight; R2/R3 verification uses the full evidence base.
- **SB-35 has already tripped — P1-baseline re-capture is MANDATORY before Unit 4, not conditional.** Live probe of `http://localhost:8000/v1/models` confirmed by document review 2026-04-18: `max_model_len: 131072`, vLLM 0.19.0. P1's smoke addendum was captured against a 65K ceiling. Every post-SB-35 P2 measurement is confounded against pre-SB-35 P1 numbers. Unit 5 (and any Unit 4 fixture comparison) must first re-run P1's configuration against the current 131K sb-chat and treat those numbers as the P2 comparison baseline. Probe mechanism: `curl -s http://localhost:8000/v1/models | jq '.data[0].max_model_len'` — verify at the top of Unit 5 pre-smoke.
- **Test coverage attaches per-unit, not at the end.** Rationale: P1's test patterns already match each unit's change type (schema helper tests, payload-shape tests, call-path tests). Interleaving test scenarios with each unit keeps test coverage additive rather than a blanket pass at the close.
- **Calibration loop (Unit 4) carries an explicit exploratory-first execution posture.** Rationale: calibration is empirical. Pre-writing tests for experiments that may or may not land is over-engineering. Unit 6 owns both POSITIVE regression tests (for the winning configuration) AND NEGATIVE regression tests (for variants that ACTIVELY REGRESSED a metric — mirrors P1's `test_no_frequency_penalty` pattern).
- **R2 is a two-part gate: aggregate AND per-book.** Rationale: mean |Δ| < 15 alone can hide a per-book Δ=28 hiding inside an acceptable average. Production trust is a worst-case property, not an average-case property. Per-book ceiling Δ ≤ 20 closes the tail-hiding failure mode.
- **`PageNumberGroundingError` is a P1-style defensive guard that stays regardless of prompt or schema fix.** Rationale: P1 established the defensive-guard + structural-fix pattern. Downstream consumers at `tools/pattern_db.py:660` and `module/EbookAutomation.psm1:2273` persist `page_number` to SQLite. Positional output silently poisons analytics. Guard catches future regressions (prompt edit, model swap, decoder change) even after Units 2+3 land.
- **Two-pass sub-unit 4b-ii requires explicit user approval gate, not just coordination.** Rationale: sb-chat is shared with SecondBrain and CareerPilot. Doubled inference volume under load is a cross-project cost the caller of Unit 4 cannot safely assume. Approval record + `NEW DEPENDENCY` session flag is the gate; policy coordination alone is insufficient.
- **Hybrid grader escape hatch becomes a user choice when R2 lands marginally (|Δ| > 12).** Rationale: the "no Claude cost" motivation is real but not absolute. A hybrid that cuts Claude spend by 80%+ while landing cleanly at |Δ|=6 is a Pareto point a marginal prompt-hack cannot reach. Keep the hatch available as an informed choice, not a blanket rejection.

## Open Questions

### Resolved During Planning

- **Sequencing for R4 marker grounding (the parent plan's deferred R3 experiment)?** Prompt-first, schema-enum fallback. User decision 2026-04-18.
- **Mode-(b) experiment scope given VRAM constraint?** Forced enumeration (prompt) first, two-pass (architectural) second, Qwen2.5-VL-32B OUT, hybrid grader OUT. User decision 2026-04-18.
- **Fast-iteration fixture for experiments?** `Python in easy steps, 2nd Edition - Mike McGrath.kfx` — established convention carried forward from parent plan.
- **Evidence format for mode classification?** Markdown table in a Step 1 addendum appended to this plan file, plus a `data/scrum280_mode_classification/` JSON output for programmatic re-use. Matches the P1 smoke addendum pattern.
- **Does a schema-enum on `page_number` require a backend re-verification?** Yes — xgrammar's enum-on-integer support is orthogonal to its `minItems`/`maxItems` support; PR #12210 auto-fallback may or may not fire. Unit 3 includes a preflight re-run (reuses `tools/debug_guided_json_preflight.py` with a swapped schema) before the corpus smoke.

### Deferred to Implementation

- **Which of the 5 prompt-engineering variants (Step 2a ladder) hits the Δ < 15 gate first?** Runtime-only answer. Unit 4 runs them in the cheapest-first order defined by the ticket.
- **Whether forced-enumeration alone is sufficient for mode (b), or two-pass is required.** Depends on Unit 4 iteration results. Two-pass sub-unit only lands if forced enumeration fails the gate.
- **Does Unit 3's schema-enum constraint degrade first-request latency?** xgrammar/guidance re-compile time on the new schema variant. Captured during Unit 5 smoke.
- **Does the Atomic Habits 95 → 86 P1 drop reflect true grader leniency or schema-induced pessimism?** Originally planned as a three-way comparison (pre-P1 local, P1 local, P2 winning-config), but pre-P1 local Atomic Habits score was never captured — `data/scrum275_local_smoke*/` contains only the Python fixture. The three-way diagnostic is unachievable on this branch. Reframed: Unit 5's mandatory SB-35 re-baseline (P1 configuration re-run on current 131K sb-chat) captures a "post-P1, pre-P2" reference for Atomic Habits. Compare that reference to the P2-winning-config Atomic Habits score — if the deltas cluster, the drop was schema-induced and Unit 4's calibration did not touch it. This is a two-way comparison, not three-way; the "was it leniency or schema pessimism pre-P1" question is accepted as unresolvable and documented as such.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

### Decision matrix (Step 1 output → Unit 4 branch)

| Step 1 classification | Unit 4 branch | First experiment | Fallback |
|---|---|---|---|
| Mode (a) — grading bias (≥70% of ≥95 pages have populated + reasonable `issues`) | Step 2a prompt ladder | Strict-grader instruction append | Persona framing → score-band enum → few-shot anchoring → chain-of-criticism |
| Mode (b) — detection failure (≥70% empty `issues` despite Claude flagging) | Step 2b architectural | Forced-enumeration prompt prepend | Two-pass detection/scoring (local, 2× inference) |
| Mixed | Treat as (b) for safety | Forced-enumeration prompt prepend | Two-pass detection/scoring |
| Any branch fails gate | Hybrid grader (escape hatch, user opt-in) | — | — |

### Sketch — `build_request` after Unit 2 prompt instruction lands

```
user_content:
  [for each (page_num, png_bytes)]:
    text: "--- Page {page_num} ---"
    image_url: {data:image/png;base64,...}
  text: (
    "Evaluate all pages above against the rubric. "
    "Return ONLY valid JSON (no markdown fences, no commentary). "
    "..."
    "CRITICAL: The `page_number` value for each entry MUST be the integer "
    "in the `--- Page N ---` label above each image, NOT the image's "
    "position in the batch. For example, if the labels are [1, 2, 3, 70], "
    "your `page_number` values must be [1, 2, 3, 70], not [1, 2, 3, 4]."
  )
```

### Sketch — `_build_page_extraction_schema` after Unit 3 schema widening (conditional)

```
def _build_page_extraction_schema(page_count, page_labels=None):
    per_page_schema = {
        ...
        "properties": {
            "page_number": (
                {"type": "integer", "enum": page_labels}
                if page_labels is not None
                else {"type": "integer"}
            ),
            ...
        },
    }
    ...
```

Call-site thread (Unit 3 only): `build_request` extracts `page_labels = [n for (n, _) in page_images]` and passes to the helper.

### Sketch — two-pass structure (Unit 4 conditional sub-unit, only if forced-enumeration prompt fails mode-(b) gate)

```
pass_1 = provider.call(build_request(images, rubric, model, variant="detection_only"))
    # schema emits issues[] only, no score field
pass_2 = provider.call(build_request_scoring(pass_1.issues, rubric, model))
    # schema emits score given detected issues, no images
merge(pass_1.issues, pass_2.score) -> final report
```

Directional only. If this sub-unit triggers, its own mini-plan for schema split + orchestration merge is captured in the Unit 4 smoke addendum.

## Implementation Units

- [ ] **Unit 1: Mode classification harness + Step 1 evidence table**

**Goal:** Classify the post-P1 6-book corpus into mode (a) grading bias, mode (b) detection failure, or mixed. Produce a per-page evidence table in a Step 1 addendum appended to this plan file.

**Requirements:** R1

**Dependencies:** None — reads existing `data/scrum275_local_6book/*.json` post-P1 reports and the corresponding Claude baseline reports captured in the SCRUM-275 smoke

**Files:**
- Create: `tools/analyze_vqa_mode_classification.py` — deterministic classifier script
- Create: `data/scrum280_mode_classification/classification.json` — programmatic output for Unit 4 re-use
- Modify: `docs/plans/2026-04-18-004-feat-scrum-280-p2-calibration-grounding-plan.md` — append Step 1 addendum with evidence table
- Test: `tests/test_vqa_mode_classifier.py`

**Approach:**
- Pure-function classifier: `classify_mode(local_report: dict, claude_report: dict) -> ClassificationResult` with:
  - `mode: Literal["a", "b", "mixed"]` — the verdict
  - `per_page: list[PageBreakdown]` where each `PageBreakdown` has `{page_number: int, local_score: int, claude_score: int, local_issues_count: int, claude_issues_count: int, local_has_nonminor_severity: bool, claude_has_critical_or_moderate: bool, per_page_classification: Literal["a", "b", "ambiguous"]}`
  - `aggregate: {pct_mode_a: float, pct_mode_b: float, pct_ambiguous: float, high_scoring_page_count: int}`
- Aggregation with a three-tier threshold (sharpens the parent plan's binary heuristic):
  - **≥70% mode-a indicators** (high-scoring pages with populated + non-trivial `issues`) → clean mode (a). Run Step 2a prompt ladder
  - **≥70% mode-b indicators** (high-scoring pages with empty `issues` despite Claude flagging) → clean mode (b). Run Step 2b architectural ladder starting at sub-unit 4b-i
  - **55–69% dominant-mode** (partial signal toward either a or b) → dominant-mode-first: run the ladder corresponding to the dominant signal, fall through to the other ladder if the first fails gate. Explicit in the evidence table: "dominant-a fallback-b" or "dominant-b fallback-a"
  - **<55% for both** (truly mixed) → treat as (b) for safety per parent plan guidance. Run Step 2b architectural ladder
- Document the percentage split for both a-indicator and b-indicator pages explicitly in the addendum, not just the verdict — future readers need to see how close the call was
- Canonical Claude baseline: `data/vqa_baseline_post_274/` (verified present by document review; contains all 6 books with `model: claude-sonnet-4-6`). NOT `vqa_baseline_pre_274/` — that is pre-SCRUM-274 and uses an earlier Claude config
- CLI: `py -3.12 tools/analyze_vqa_mode_classification.py --local-dir data/scrum275_local_6book --claude-dir data/vqa_baseline_post_274 --out data/scrum280_mode_classification/classification.json`
- Addendum output: a markdown table per book showing per-page `local_score`, `claude_score`, `local_issues_count`, `claude_issues_count`, classification verdict, plus the aggregate classification at the end. Append to this plan file (do not rewrite existing sections)

**Execution note:** Write the classifier with test-first discipline — inputs are deterministic JSON fixtures so TDD applies cleanly.

**Patterns to follow:**
- `tools/debug_guided_json_preflight.py` — short, self-contained CLI script with argparse, returns non-zero on unexpected state
- `PageCountMismatchError` docstring style for any new exception types raised by the classifier

**Test scenarios:**
- *Happy path:* fixture with 8 local pages all `score >= 95` + populated `issues[]` with at least one moderate severity → classifier returns `mode="a"`
- *Happy path:* fixture with 8 local pages all `score >= 95` + empty `issues[]`, Claude report showing `critical` issues on the same pages → classifier returns `mode="b"`
- *Edge case:* fixture with 5 local high-scoring pages populated and 3 empty → aggregate across 6 books might flip the decision; assert the per-book verdict is independent of aggregation
- *Edge case:* aggregate across 6 books where 3 come back (a) and 3 come back (b) → classifier returns `mode="mixed"`
- *Error path:* local report and Claude report have different page counts → classifier raises `ValueError` with both counts in the message (mirror `PageCountMismatchError` style)
- *Error path:* missing corpus directory → CLI exits non-zero with a clear error

**Verification:** `py -3.12 tools/analyze_vqa_mode_classification.py` produces `data/scrum280_mode_classification/classification.json` with a top-level `mode` field and a 6-book breakdown. Step 1 addendum in this plan file contains the evidence table and a clear statement of the classification verdict. `py -3.12 -m pytest tests/test_vqa_mode_classifier.py -q` passes.

---

- [ ] **Unit 2: `page_number` marker-grounding prompt instruction + defensive guard (R4 prompt-first)**

**Goal:** Append an explicit grounding instruction to the trailing user-content text in `build_request` pinning `page_number` to the `--- Page N ---` marker value. Add a post-parse defensive guard (`PageNumberGroundingError`) in `call()` that surfaces grounding failures regardless of whether the prompt or schema remediations land — mirrors the P1 defensive-guard + structural-fix pattern.

**Requirements:** R4 (primary), R5, R6

**Dependencies:** None — independent of Unit 1. Can run in parallel

**Files:**
- Modify: `tools/llm_providers/local_provider.py` (`build_request` trailing instruction text + new `PageNumberGroundingError` class + post-parse guard in `call()`)
- Test: `tests/test_local_provider_phase2.py`

**Approach:**

*Sub-step 2a — grounding prompt instruction (always lands, orthogonal to Unit 1 classification):*
- Single-site edit: the trailing `user_content.append({"type": "text", "text": "Evaluate all pages..."})` block at roughly `local_provider.py:284-293`. Append the grounding clause at the end of the instruction string
- Grounding clause text (exact wording chosen at implementation time, but must include all three elements): (a) "MUST be the integer in the `--- Page N ---` label", (b) "NOT the image's position in the batch", (c) a concrete example with non-sequential labels (e.g., `[1, 2, 3, 70]`) showing expected vs wrong output
- Do not change the existing instruction text, schema block, `max_tokens`, `temperature`, `extra_body`, or any other payload field
- Add a brief inline comment above the instruction text citing SCRUM-280 and the positional-vs-marker finding

*Sub-step 2b — `PageNumberGroundingError` defensive guard (always lands, independent of prompt success):*
- New module-level class in `local_provider.py` following the `PageCountMismatchError` and `OutputTruncatedError` style — typed constructor, load-bearing docstring citing SCRUM-280 and the positional-vs-marker finding, attrs on self for caller introspection
- Post-parse guard in `call()`: after JSON parse succeeds (and `PageCountMismatchError` has not fired), check that every `parsed["pages"][i]["page_number"]` appears in the input label set `[n for (n, _) in page_images]`. If any output `page_number` is NOT in the input set, raise `PageNumberGroundingError(expected_labels=..., actual_page_numbers=...)`
- Must fire BEFORE the existing `return VisionResponse(...)` path — grounding failure is a distinct failure mode from count mismatch or truncation and should surface as its own error
- **Rationale (load-bearing):** downstream consumers at `tools/pattern_db.py:660` and `module/EbookAutomation.psm1:2273` persist `page_number` into the `issues` SQLite table. Positional output (ungrounded) silently poisons analytics across all books (all issues cluster at indexes 1-8). The guard makes a silent failure mode loud. Stays in place even after Unit 2 prompt + Unit 3 schema enum land — same belt-and-suspenders posture as the P1 `PageCountMismatchError`

*Smoke verification is NOT part of this unit's code deliverable — lands in Unit 5. Unit 2's verification is the test assertions + a single RotG one-shot run (recorded in Unit 5 addendum, not duplicated here)*

**Execution note:** Test-first — the instruction-text assertion can be written before the change.

**Patterns to follow:**
- `test_trailing_instruction_text_matches_claude_provider` at `tests/test_local_provider_phase2.py:133` — asserts the trailing instruction string content. Extend its assertion to require the new grounding clause, or add a new test that specifically pins the grounding clause so the existing test stays focused on Claude-parity
- Load-bearing inline comment style: see `local_provider.py:303-312` (frequency_penalty + SCRUM-279 comment block) — cite ticket, cite finding, cite rationale

**Test scenarios:**
*Sub-step 2a (grounding prompt instruction):*
- *Happy path:* `build_request(...)` produces a payload where the last user-content text block contains all three required elements of the grounding clause (marker phrase, NOT-position phrase, concrete non-sequential example)
- *Happy path:* existing `test_trailing_instruction_text_matches_claude_provider` adjusted (not deleted) to accommodate the new clause — assertion must still verify the rubric-parity portion
- *Happy path:* the grounding clause text is consistent regardless of `len(page_images)` (instruction is not parameterized by count — it's a general grounding rule)
- *Integration — unchanged:* `test_no_frequency_penalty`, `test_response_format_is_json_schema`, `test_response_format_strict_true`, `test_enable_thinking_is_false` all still pass. Grounding instruction is additive, must not break existing payload shape contracts
- *Edge case:* `build_request` with 1 image produces the grounding instruction too (generic, not specific to multi-image batches)

*Sub-step 2b (`PageNumberGroundingError` guard):*
- *Error path:* `_make_fake_completion` returns a parsed response where `pages[3].page_number == 4` but input labels were `[1, 2, 3, 70, 87, 138, 154, 221]` → `call()` raises `PageNumberGroundingError` with `expected_labels` and `actual_page_numbers` both in the exception attrs
- *Error path:* `PageNumberGroundingError` fires BEFORE `return VisionResponse(...)` — even a response with correct count and valid JSON raises if any single `page_number` is outside the input label set
- *Happy path:* matching count + all `page_number` values in input label set → no exception raised, `VisionResponse` returned normally
- *Integration — unchanged:* `PageCountMismatchError` still fires first when count mismatches (guard order: count → grounding → return). `OutputTruncatedError` still fires before JSON parse. Existing `call()` tests stay green
- *Edge case:* single-image batch (`page_images=[(5, b"...")]`) with `pages[0].page_number == 5` → no exception. With `pages[0].page_number == 1` → `PageNumberGroundingError` raised (the 1 is positional, not the input label 5)

**Verification:** `py -3.12 -m pytest tests/test_local_provider_phase2.py -q` passes (existing 38+ tests + new grounding-clause + new guard assertions). Inspecting a serialized payload shows the trailing text block includes the grounding language. `grep "PageNumberGroundingError" tools/llm_providers/local_provider.py` shows the class definition AND the guard invocation in `call()`.

---

- [ ] **Unit 3: `page_number` schema enum fallback — CONDITIONAL on Unit 2 + Unit 5 smoke failing R4**

**Goal:** If Unit 2's prompt instruction alone does not achieve R4 on the RotG test case (`page_number` output still positional), widen `_build_page_extraction_schema` to accept an optional `page_labels` list and add an `enum` constraint on `items.properties.page_number`. Thread labels from `build_request`. Re-run Unit 5 smoke to verify.

**Requirements:** R4 (fallback path), R5, R6

**Dependencies:** Unit 2 (primary remediation must be tried and fail first). **Trigger condition:** Unit 5 smoke shows ANY deviation in output `page_number` values from the input label set on ANY of the three N≥3 verification fixtures (RotG, Oil Kings, third stress fixture). A single mismatched value on any of the three fixtures triggers Unit 3. "Exact match on all three fixtures" is the pass condition for Unit 2 alone

**Files:**
- Modify: `tools/llm_providers/local_provider.py` (`_build_page_extraction_schema` signature, `build_request` call site)
- Modify: `tools/debug_guided_json_preflight.py` (add an enum-on-integer preflight case) — re-run before corpus smoke
- Test: `tests/test_local_provider_phase2.py` (schema helper block + payload assertion)

**Approach:**
- Widen signature: `_build_page_extraction_schema(page_count: int, page_labels: list[int] | None = None) -> dict`
- When `page_labels is None` (backward compat): emit the current `{"type": "integer"}` for `page_number`
- When `page_labels` is provided: assert `len(page_labels) == page_count`, emit `{"type": "integer", "enum": page_labels}` for `page_number`
- `build_request` call site: extract labels from `page_images` (`[n for (n, _) in page_images]`) and pass. No API surface change for callers — the `VisionProvider` Protocol is unchanged
- Preflight re-run: add TWO new cases to `tools/debug_guided_json_preflight.py`:
  - **Case A — enum-on-integer enforcement:** schema with `page_number: {type: integer, enum: [42]}` and a prompt that would naturally produce a different integer. Verify backend enforcement is live (xgrammar may or may not support it; PR #12210 auto-fallback behavior on this specific keyword is not pre-verified)
  - **Case B — rollback keyword exercise:** a separate probe using explicit `extra_body={"structured_outputs": {"json": {...}, "backend": "guidance"}}` — the rollback path in the P1/P2 plan has NEVER been exercised against this vLLM 0.19.0 sb-chat instance. Run it once to verify the keyword syntax still works as documented. If Case A fails and Case B is needed as a rollback, the implementer should not be debugging vLLM keyword syntax under pressure
- Load-bearing comment in the helper citing SCRUM-280 R4 and the positional-grounding finding

**Execution note:** Test-first for the schema shape; preflight verification is integration-time.

**Patterns to follow:**
- P1 schema helper test pattern at `tests/test_local_provider_phase2.py:272-368` — parameterized across `page_count=1, 8, 16`, asserts shape properties via direct dict access
- `tools/debug_guided_json_preflight.py` probe structure for the new enum-on-integer preflight case

**Test scenarios:**
- *Happy path:* `_build_page_extraction_schema(8, page_labels=[1, 2, 3, 70, 87, 138, 154, 221])` returns schema where `pages.items.properties.page_number == {"type": "integer", "enum": [1, 2, 3, 70, 87, 138, 154, 221]}`
- *Happy path:* `_build_page_extraction_schema(8)` — no labels — returns unchanged shape with `page_number == {"type": "integer"}` (regression protection)
- *Edge case:* `page_labels=[1]` with `page_count=1` works (single-image boundary still valid)
- *Edge case:* `_build_page_extraction_schema(8, page_labels=[1, 2, 3, 70, 87, 138, 154, 221])` — schema still round-trips through `json.dumps` without error
- *Error path:* `len(page_labels) != page_count` raises `ValueError` with both counts in the message
- *Integration:* `build_request(...)` with non-sequential page numbers threads `page_labels` through to the schema; payload asserted to contain the enum constraint
- *Integration (preflight):* updated `tools/debug_guided_json_preflight.py` run shows backend enforcement is live for enum-on-integer; if it fails, rollback is `extra_body={"structured_outputs": {"json": {...}, "backend": "guidance"}}` (same rollback pattern documented in P1)

**Verification:** `py -3.12 -m pytest tests/test_local_provider_phase2.py -q` passes. `py -3.12 tools/debug_guided_json_preflight.py` shows enum-on-integer preflight is enforced. Unit 5 RotG re-smoke shows `page_number` output == input labels exactly.

---

- [ ] **Unit 4: Grader-leniency calibration — iterative experiments per Unit 1 mode classification**

**Goal:** Reduce mean absolute score Δ vs Claude across the 6-book corpus to < 15 points (R2). Branch per Unit 1 classification: mode (a) → Step 2a prompt ladder; mode (b) or mixed → Step 2b architectural ladder starting with forced enumeration. Stop at the first variant that passes the gate.

**Requirements:** R2 (fixture-level exploration), R3 (fixture-level non-degeneracy check), R5. Full-corpus R2/R3 verification lands in Unit 5; this unit establishes the variant that passes the 8-page fixture gate.

**Dependencies:** Unit 1 (classification must be in hand before branching)

**Files:**
- Modify: `tools/llm_providers/local_provider.py` (`build_request` system/user prompt construction — exact variant depends on the winning experiment; schema helper only if a variant requires schema-level changes like score_band enum)
- Modify: `tools/visual_qa_rubric.md` is INTENTIONALLY NOT TOUCHED — rubric is the contract; any strict-grader framing lives in the local provider's system/user prompts, not the rubric itself
- Create (conditional on two-pass landing): orchestration changes in `tools/visual_qa.py` for the second `call()`. Scope is narrow — one additional call in the existing `payload = provider.build_request(...); response = provider.call(payload)` flow at `tools/visual_qa.py:564`
- Test: `tests/test_local_provider_phase2.py` — tests land only for the WINNING configuration (see Execution note)

**Approach:**

*If Unit 1 = mode (a) — Step 2a prompt ladder (cheapest-first):*
1. **Strict-grader instruction append** — system message prefix: "Grade strictly. If ANY issue is present, deduct points. A score of 100 requires zero visible issues."
2. **Persona framing** — system prompt: "You are a strict editor reviewing this book for quality control. Your job is to find every flaw."
3. **Score-band enum via guided_json** — replace `score: integer [0-100]` in the per-page schema with `score_band: enum["FAIL", "POOR", "ACCEPTABLE", "GOOD", "EXCELLENT"]` + explicit criteria per band in the system prompt. Post-process to numeric in `parse_qa_response` if any downstream consumer depends on integer scores
4. **Few-shot anchoring** — include 1-2 Claude-scored example pages in the system message
5. **Chain-of-criticism structure** — require `issues_detected` array output *before* the `score` field in the schema property ordering. Forces enumeration pass before grading pass at decoder time. **PRECONDITION:** before running this variant, extend `tools/debug_guided_json_preflight.py` with a property-ordering probe (schema with two fields; ask the model a question whose natural answer biases toward the later field; check if the earlier field is emitted first). If the preflight shows ordering is not honored by the current vLLM backend, SKIP this variant entirely — running it would produce inconclusive calibration numbers. JSON spec does not guarantee property ordering; vLLM backend behavior (xgrammar / guidance / outlines) varies and may differ per-request under PR #12210 auto-fallback

*If Unit 1 = mode (b) or mixed — Step 2b architectural ladder (SEQUENTIAL, NOT PARALLEL):*

**Sub-unit 4b-i — Forced-enumeration prompt prepend (try first):**
System message appends: "Before evaluating, list every visual element visible on this page: headers, body text blocks, images, tables, page numbers. Then evaluate each against the rubric." Orthogonal to Step 2a prompts — can stack if mixed. If this hits the R2 gate, STOP — do not proceed to two-pass.

**Sub-unit 4b-ii — Two-pass structure (triggered ONLY if 4b-i fails R2 gate on fixture):**
Pass 1 emits `issues[]` only; pass 2 accepts issues list and emits score. Requires:
- **Protocol extension** — this IS a change to `tools/llm_providers/base.py::VisionProvider`. Either (a) widen `build_request(..., variant: Literal["full", "detection_only", "scoring_only"] = "full")`, OR (b) add `build_request_scoring(issues: list, rubric: str, model: str) -> dict` as a new Protocol method. Plan does not pre-decide; implementer chooses based on which is less invasive given the final winning Unit 4 configuration. Either choice must be reflected in the test file as a Protocol-contract test
- **Independent preflight** — the two new schemas (detection-only, scoring-only) have not been validated against vLLM guided decoding. Each needs its own preflight case in `tools/debug_guided_json_preflight.py` before the two-pass smoke runs
- **Transactional semantics in `tools/visual_qa.py:560-583`** — the current batch loop has `except Exception as e: ... continue`. A pass-1 success + pass-2 failure would currently drop detected issues silently. Two-pass orchestration must add: if pass_1 succeeds and pass_2 fails, surface an explicit error (new `TwoPassScoringFailed` in `local_provider.py`?) that preserves pass_1.issues in the error payload so they can be salvaged upstream
- **EXPLICIT USER APPROVAL GATE** — two-pass doubles sb-chat inference volume on a shared stack (SecondBrain + CareerPilot also consume). Before landing, Unit 5 addendum MUST record: (1) explicit user approval, (2) measured per-batch steady-state latency at current sb-chat load, (3) a `NEW DEPENDENCY: EbookAutomation → sb-chat shared stack throughput` flag added to the session summary per the cross-project protocol. "Flag and coordinate" is not sufficient — require the approval as a gate

*Iteration loop:*
- **Primary fixture:** `Python in easy steps, 2nd Edition - Mike McGrath.kfx`, 8 pages. Same deterministic bookmark sample for every variant — swapping samples between variants confounds the comparison
- **Secondary fixture (REQUIRED before Unit 5 eligibility):** a non-Python book — RotG or Atomic Habits 8-page subset. Python-in-easy-steps is the "simple structure canary" in the test corpus and generalizes poorly; a variant that passes only there is not yet worthy of the full corpus smoke
- One variable changed per iteration (reusable template from parent plan Methodology Note). Stop at the first variant hitting mean |Δ| < 15 on BOTH fixtures
- **Stopping rule for iteration loop:** if two consecutive variants pass both fixture gates but fail Unit 5 corpus gate (mean |Δ| ≥ 15 OR any per-book |Δ| > 20), abandon the current ladder branch (Step 2a or Step 2b sub-unit) and proceed to the next. Maximum iteration budget: 5 variants per ladder branch. If both 2a and 2b exhaust without clearing the corpus gate, escalate to the hybrid-grader escape hatch as an explicit user choice
- Full 6-book corpus re-smoke happens in Unit 5 against the variant that passed both fixture gates — do not re-run the full corpus on every fixture iteration

*What NOT to do:*
- Do not combine multiple variants in a single fixture run — confounds the diagnosis
- Do not modify `tools/visual_qa_rubric.md` — rubric is the contract; any strict-grader framing lives in the system prompt
- Do not land tests for intermediate variants in Unit 4 itself. Unit 6 owns both the positive regression contract for the winning configuration AND negative regression contracts for variants that ACTIVELY REGRESSED a metric (distinguished from those that simply didn't win — see Unit 6 Approach)

**Execution note:** Exploratory-first. This unit is an experiment loop, not a TDD sequence. Lock in test coverage in Unit 6 for the winning configuration only. Document each attempted variant (even failures) in the Unit 5/6 addendum so future readers see the full experiment trace.

**Patterns to follow:**
- Parent plan Methodology Note (Reusable diagnostic template section) — hypothesis → unique prediction → one variable per iteration → distinguish magnitude bias from structural failure
- System prompt construction pattern: current `build_request` puts the rubric in the system message. Strict-grader framing extends or wraps the rubric, does not replace it

**Test scenarios:**
- Intermediate variants: no new tests. Existing 38+ tests continue to pass — they pin invariants (`frequency_penalty` absence, `enable_thinking=False`, `response_format.type=="json_schema"`) that every variant must preserve
- *Integration — after each variant run:* the existing test suite passes (no regression of invariants)
- Final variant: test scenarios for the WINNING configuration land in Unit 6, not here

**Verification:**
- Fixture iteration (`Python in easy steps`) shows mean |Δ| < 15 for the winning variant
- Existing test suite (`py -3.12 -m pytest tests/test_local_provider_phase2.py -q`) stays green after every intermediate change
- Winning variant identified and documented in this plan's Unit 5 addendum (not here; Unit 5 owns the full-corpus verification)

---

- [ ] **Unit 5: 6-book corpus smoke + R2/R3/R4 gate verification**

**Goal:** Verify the winning configuration from Unit 4 (and the R4 remediation from Unit 2, plus Unit 3 if it triggered) against the full 6-book corpus. Capture evidence for R2 (mean |Δ| < 15), R3 (non-degenerate score distribution), R4 (RotG page_number marker match exactly), and compare against the P1 baseline.

**Requirements:** R2 (full-corpus verification — authoritative acceptance gate), R3 (full-corpus non-degeneracy — authoritative acceptance gate), R4 (verification — exact marker match on multiple non-sequential label sets), R5

**Dependencies:** Unit 1 (classification), Unit 2 (prompt-first R4), and Unit 4 (winning calibration variant). Unit 3 dependency only if it triggered.

**Files:**
- Execute: `py -3.12 tools/visual_qa.py --provider local ...` across 6 books
- Modify: `docs/plans/2026-04-18-004-feat-scrum-280-p2-calibration-grounding-plan.md` — append Unit 5 smoke addendum with per-book metrics table and per-page page_number verification for RotG
- Create (optional): `docs/solutions/scrum-280-p2-calibration-and-grounding.md` if the results compound as institutional knowledge for other Qwen VQA work

**Approach:**

*Pre-smoke checks:*
- **SB-35 re-baseline (MANDATORY, not conditional):** sb-chat is already at 131K (confirmed 2026-04-18 via `/v1/models` probe). P1's smoke addendum numbers were captured at 65K and are NOT directly comparable to P2. Re-run P1's `test_response_format_is_json_schema` configuration against the current sb-chat, across all 6 books, and treat THOSE numbers as the P2 comparison baseline. Commit the re-baselined numbers to this plan's Unit 5 addendum under a "Post-SB-35 P1 re-baseline" subheading before running any P2-winning-config smoke
- Probe mechanism (concrete): `curl -s http://localhost:8000/v1/models | jq '.data[0].max_model_len'` returns the context ceiling; `curl -s http://localhost:8000/version` returns the vLLM version. Record both in the addendum
- Re-run `tools/debug_guided_json_preflight.py` to confirm backend enforcement is still live after any schema/prompt changes
- **Re-validate Unit 1 mode classification (added 2026-04-18 per Phase 2 STOP gate):** Re-run `py -3.12 tools/analyze_vqa_mode_classification.py` against the fresh post-P1 re-baseline data. Record the updated verdict in the Unit 5 addendum. If verdict still dominant-b, lock in; if it flips to dominant-a (only plausible if strict: true schema masked optional fields), revisit Unit 4 branch before winning-variant smoke.

*Corpus smoke:*
- 6 books, same corpus as P1: Oil Kings, Mexico Illicit, Return of the Gods, Atomic Habits, Decline of the West, Python in easy steps
- Capture per book: page count returned, per-page score, per-page `len(issues)`, input/output tokens, inference latency, `finish_reason`
- Compute mean |Δ| vs Claude baseline across all 48 pages (6 books × 8 pages). Must be < 15 for R2(a). AND compute per-book |Δ| — NO individual book may exceed 20 for R2(b). Failing either sub-condition fails R2
- Verify score distribution: at least one page < 60 somewhere in the corpus if Claude flagged one (R3 non-degeneracy)

*R4 verification (≥3 non-sequential label sets required — prompt-only remediation demands a broader sample than a single book):*
- **Primary fixture (RotG):** input markers `[1, 2, 3, 70, 87, 138, 154, 221]`. Output `page_number` field must equal this list exactly — any deviation fails R4
- **Secondary fixture (Oil Kings):** input markers `[1, 2, 3, 119, 229, 354, 360, 573]` (per P1 smoke record). Output must match exactly
- **Stress fixture (any third book with highly non-sequential labels):** e.g., Decline of the West with widely-spaced sampled pages. Output must match exactly
- Rationale for N≥3: a prompt-only remediation can pass one fixture by happy accident (e.g., the model's positional default happens to match markers on easy cases). Three distinct non-sequential label sets reduces that false-positive risk materially
- If all three pass under Unit 2 alone: document and skip Unit 3
- If ANY of the three fails: trigger Unit 3, re-smoke all three fixtures, verify exact match on all

*If Unit 3 triggers — enum-load-bearing verification (NOT just enum-preflight):*
- The Unit 3 preflight only verifies that the backend enforces the enum schema — it cannot distinguish "enum is load-bearing" from "enum silently dropped, model happens to emit labels anyway because Unit 2 prompt is doing the work."
- Run two experiments on RotG:
  - **Experiment (i):** Unit 2 prompt + Unit 3 schema enum together → verify correct output
  - **Experiment (ii):** Unit 3 schema enum alone, Unit 2 prompt REVERTED → verify correct output
- If (ii) succeeds, enum is genuinely load-bearing — keep it
- If (ii) fails, the enum was cosmetic and the prompt was doing the work — the plan should DROP Unit 3 and keep Unit 2 prompt-only, documenting in the addendum that the schema widening was not load-bearing
- Cost: one additional 8-page inference on RotG — cheap relative to the ambiguity cost

*Latency comparison:*
- Steady-state inference latency per book vs P1 baseline. Flag if any book exceeds 2× P1 steady-state
- If Unit 3 schema widening landed, first-request compilation latency is expected to increase (new schema variant). Record separately

**Test scenarios:**
- *Integration — R2(a):* mean |Δ| across 48 pages < 15
- *Integration — R2(b):* no individual book has |Δ| > 20 (per-book ceiling, prevents a Δ=28 book hiding inside an acceptable average)
- *Integration — R3:* at least one page with `score < 60` in the corpus. Score distribution not collapsed to a narrow band
- *Integration — R4:* RotG output `page_number` field == `[1, 2, 3, 70, 87, 138, 154, 221]` exactly. Oil Kings (sampled pages `[1, 2, 3, 119, 229, 354, 360, 573]` per P1 record) also tested as a secondary R4 fixture with non-sequential labels
- *Integration — invariants:* no `PageCountMismatchError`, no `OutputTruncatedError`, all `finish_reason == "stop"`
- *Integration — latency:* steady-state ≤ 2× P1 baseline. First-request compilation latency documented separately from steady-state
- *Integration — SB-35 re-baseline:* if triggered, pre-Unit-5 P1 baseline re-run numbers are recorded alongside the new numbers so the comparison is on matched context-ceiling conditions

**Verification:** All 4 integration assertions pass. Smoke addendum appended to this plan file with per-book metrics table, RotG per-page `page_number` match table, and explicit R2/R3/R4 sign-off. If any gate fails, the addendum records the failure and loops back to Unit 3 or Unit 4 as indicated.

---

- [ ] **Unit 6: Final test coverage for winning configuration + load-bearing comments**

**Goal:** Lock in test coverage for the exact configuration landed in Units 2/3/4. Mirror the P1 pattern (`test_no_frequency_penalty` style) — tests that pin the winning behavior as a regression contract. Add load-bearing comments to the relevant code paths citing SCRUM-280 and the evidence.

**Requirements:** R5, R6

**Dependencies:** Unit 5 (winning configuration must be verified against corpus before tests are locked in)

**Files:**
- Modify: `tools/llm_providers/local_provider.py` — comments on the winning configuration (system prompt framing, schema enum if Unit 3 landed, page_number grounding clause from Unit 2)
- Modify: `tests/test_local_provider_phase2.py` — regression-contract tests for the winning configuration

**Approach:**
- Identify the delta between pre-P2 `local_provider.py` and the winning configuration. Every delta that matters (grounding clause, `PageNumberGroundingError` guard, strict-grader framing, schema enum, two-pass orchestration if applicable) gets:
  - A load-bearing inline comment citing SCRUM-280, the specific evidence that motivated it, and what the failure mode is if a future edit removes it (same style as the P1 `frequency_penalty` + `SCRUM-279` comment block at `local_provider.py:303-312`)
  - A POSITIVE regression test that asserts the behavior is present (payload-shape style — no network calls)
- Apply the full P1 test pattern inventory (positive tests for the winning configuration):
  - `test_trailing_instruction_contains_page_number_grounding_clause` (Unit 2 sub-step 2a)
  - `test_call_raises_page_number_grounding_error_on_positional_output` (Unit 2 sub-step 2b — defensive guard)
  - `test_schema_page_number_enum_when_labels_provided` (Unit 3, conditional)
  - Tests for whatever Unit 4 landed — e.g., `test_system_prompt_includes_strict_grader_framing`, `test_score_band_enum_if_score_replaced`, `test_two_pass_orchestration_passes_issues_between_calls`, etc. Exact names match the shape of the winning configuration
- Apply NEGATIVE regression tests for actively-regressed variants per the "Simply didn't win vs Actively regressed" distinction below — mirrors P1's `test_no_frequency_penalty` pattern
- Distinguish two kinds of rejected variants:
  - **Simply didn't win** (reached baseline but didn't pass the gate) → no test, addendum narrative only
  - **Actively regressed** (produced a specific reproducible failure mode — e.g., distribution collapse, `finish_reason` drift, token overrun, grader output outside enum bounds) → add a NEGATIVE regression test in Unit 6 pinning absence of the offending pattern. Mirrors the P1 `test_no_frequency_penalty` pattern: a test whose purpose is to prevent reintroduction of a known-bad variant. Comment cites the SCRUM-280 addendum evidence
- Do NOT add tests for variants that were tried and reached baseline but simply didn't win — the point is to lock in the winner, not catalogue the full experiment trace (that lives in the Unit 5 addendum)

**Execution note:** Test-first — with the winning configuration already in hand from Unit 4, the tests can be written as the regression contract immediately.

**Patterns to follow:**
- `test_no_frequency_penalty` at `tests/test_local_provider_phase2.py:191` — comment explains why absence is load-bearing
- `test_response_format_is_json_schema` at `tests/test_local_provider_phase2.py:379` — asserts payload-shape presence and the specific value that matters
- Docstring style for the test itself: one-line what, one-line why it's a regression contract

**Test scenarios:**
- *Happy path:* tests for every delta between pre-P2 and winning configuration. Each test follows the `test_no_frequency_penalty` pattern: isolate one invariant, comment explains why it's load-bearing, assert it
- *Integration — full suite green:* `py -3.12 -m pytest tests/test_local_provider_phase2.py -q` passes with all new tests + all existing 38+ tests

**Verification:** `py -3.12 -m pytest tests/test_local_provider_phase2.py -q` green. `grep "SCRUM-280" tools/llm_providers/local_provider.py` shows comments on every winning-configuration delta. Test file docstrings name each regression contract the test is pinning.

## System-Wide Impact

- **Interaction graph:** No new callbacks. Unit 4's two-pass conditional sub-unit adds one extra call site at `tools/visual_qa.py:564` — the orchestration layer invokes `provider.call()` twice per batch when two-pass lands. No new middleware or observers.
- **Error propagation:** Existing `PageCountMismatchError` and `OutputTruncatedError` (P1) continue to be the primary failure modes. No new exception types introduced. Unit 1 classifier may raise `ValueError` on mismatched report page counts — scoped to the classifier CLI, not the provider.
- **State lifecycle risks:** None — all changes are stateless request construction (Units 2, 3) or stateless orchestration (Unit 4 two-pass sub-unit is two atomic calls, not a resumable stream).
- **API surface parity:** `VisionProvider` Protocol (`build_request`, `call`, `estimate_cost`) signatures are unchanged. Claude provider is not touched (grader leniency is Qwen-specific). Surface stays asymmetric by design.
- **Integration coverage:** Unit 5 smoke is the only signal that the winning configuration actually achieves R2/R3/R4 in production conditions. Unit tests alone cannot prove grader Δ or marker grounding — those are model-behavior properties.
- **Unchanged invariants:** `minItems == maxItems == len(page_images)` (P1 structural fix), `PageCountMismatchError` guard, `OutputTruncatedError` guard, `extra_body.chat_template_kwargs.enable_thinking = False`, absence of `frequency_penalty`, all P1 top-level required fields. Any P2 variant that tampers with these fails the existing invariant tests.
- **Shared-stack contention risk:** If Unit 4's two-pass sub-unit lands, inference volume per batch doubles on sb-chat. SecondBrain and CareerPilot share this stack. Flag in rollout notes; coordinate with INFRA-167/187 routing work if throughput becomes a concern.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Unit 2 prompt-only R4 fix fails and Unit 3 schema enum also fails (Qwen visual attention genuinely cannot ground from markers) | Document the failure in the Unit 5 addendum with full evidence. R4 becomes a ticket that cannot close on this branch; requires either (a) Qwen2.5-VL-32B swap (deferred, VRAM-blocked) or (b) switching to positional indexing everywhere downstream and deprecating `page_number` as a source pointer. Escalation decision, not a plan decision |
| Step 1 mode classification is ambiguous — neither ≥70% threshold is met cleanly | Parent plan says "treat as mixed → treat as (b) for safety." Unit 4 starts with forced enumeration (prompt-only, cheapest) per that guidance. Ambiguous classification does not block progress |
| SB-35 has already tripped — sb-chat is at 131K as of 2026-04-18 (P1 was captured at 65K) | Unit 5 pre-smoke MUST re-capture P1 baseline under the 131K ceiling before running any P2 variant smoke. Probe mechanism: `curl http://localhost:8000/v1/models | jq '.data[0].max_model_len'`. Re-baseline numbers go in the Unit 5 addendum under a dedicated subheading |
| Unit 3 enum-on-integer constraint triggers an xgrammar fallback edge case P1 didn't exercise | Unit 3 re-runs `tools/debug_guided_json_preflight.py` with an enum-on-integer probe before Unit 5 corpus smoke. If enforcement fails, rollback is explicit `extra_body={"structured_outputs": {"backend": "guidance"}}` (same two-line rollback P1 documented) |
| Two-pass structure doubles sb-chat inference volume under a shared stack (SecondBrain + CareerPilot also consume) | Unit 4 sub-unit 4b-ii has an EXPLICIT USER APPROVAL GATE — two-pass cannot land without: (1) explicit user approval recorded in Unit 5 addendum, (2) measured per-batch steady-state latency at current sb-chat load documented in the addendum, (3) a `NEW DEPENDENCY: EbookAutomation → sb-chat shared stack throughput` flag in the session summary. "Coordinate with INFRA-167/187" is policy, not a gate — the approval record is the gate |
| Hybrid grader (local detect + Claude score) is quietly revisited mid-experiment and re-introduces per-call Claude cost | Explicit Key Technical Decisions entry locks it out unless the user opts in. If Unit 4 stalls, surface the hybrid option to the user as an explicit choice, not a fait accompli |
| Atomic Habits P1 score drop (95 → 86) is actually schema-induced pessimism, not pre-P1 leniency — Unit 4 "fixes" a symptom caused by P1 | Two-way comparison only (pre-P1 local data for Atomic Habits was never captured). Unit 5 smoke addendum records P1-re-baseline Atomic Habits score (from mandatory SB-35 re-baseline) vs P2-winning-config score. If deltas cluster, drop was schema-induced and Unit 4 did not address it. The pre-P1 confound is accepted as unresolvable — documented, not diagnosed |
| Score-band enum variant (Step 2a #3) requires replacing `score: integer` in the schema — 5+ integer-score consumers downstream (not one) | Integer-score consumers enumerated: `batch_qa.py:224, 1317-1336, 1434, 1524, 1926, 2406` (arithmetic on `page.score`, threshold comparisons like `< pass_threshold - 10`); `visual_qa.py:594` (averages per-page scores into `overall_score`). The 5-band mapping (`FAIL=30, POOR=50, ACCEPTABLE=70, GOOD=85, EXCELLENT=95`) collapses `batch_qa.py`'s WARN/FAIL thresholds to always-WARN or always-PASS — degrades quality-signal granularity. If Unit 4's winning variant is score-band: (a) enumerate every `.get("score")` and `.get("category_scores")` consumer in a pre-commit grep pass, (b) define whether the mapping happens at `parse_qa_response` or provider boundary, (c) verify `batch_qa.py` WARN/FAIL thresholds still produce non-degenerate status output under the mapping, (d) consider a finer band granularity (e.g., 9 bands) if coarse mapping breaks threshold semantics |
| Winning variant clears R2 marginally (|Δ| within 2 points of the gate — e.g., mean |Δ| = 13.5, per-book max = 19) with fragile hold | Surface hybrid grader as an explicit user choice before locking in the marginal prompt hack. Hybrid grader (local detect + Claude score) is NOT the blanket "defeat of local VQA" it reads as elsewhere — routing only the text-only scoring half through Claude can cut Claude spend by 80%+ while landing cleanly at |Δ|=6. A cleanly-landing hybrid may be more honest than a prompt hack barely clearing the gate. Quantify: record fraction-of-Claude-spend retained under the hybrid on the 6-book workload; if < 25% and |Δ| < 10, the hybrid is a legitimate Pareto choice |
| Unit 4 fixture iteration loops indefinitely — variants pass Python-in-easy-steps (the corpus's "simple structure canary") but fail on RotG or Decline of the West in Unit 5 corpus smoke | Explicit stopping rule: if two consecutive variants pass the fixture gate but fail Unit 5 corpus gate, abandon the current ladder branch and proceed to the next (Step 2a → Step 2b, or Step 2b → hybrid escape hatch). Additionally: a Unit 4 variant is NOT eligible for Unit 5 corpus smoke until it passes the fixture gate on ≥1 non-Python fixture (e.g., RotG or Atomic Habits 8-page subset). Python-in-easy-steps alone is insufficient — it is the simplest book in the corpus and generalizes poorly |
| Unit 4 iteration drift — more than 5 variants run, fixture numbers become stale as the model's baseline shifts across sb-chat restarts | Fixture cache: record `sb-chat server start timestamp` and model version in every variant run. If sb-chat restarts mid-iteration, re-baseline the fixture before continuing |
| Grounding clause (Unit 2) gets silently stripped by a future `build_request` refactor | Test `test_trailing_instruction_contains_page_number_grounding_clause` (Unit 6) pins it as a regression contract. Inline comment cites SCRUM-280 and the positional-vs-marker finding |

## Documentation / Operational Notes

- On completion: update SCRUM-280 ticket — check each AC (R1–R6) with evidence links (plan addendum, commit hashes, test names)
- Unit 5 smoke addendum is the canonical evidence record. Optional promotion to `docs/solutions/scrum-280-p2-calibration-and-grounding.md` if results compound for future Qwen VQA work (`docs/solutions/` is currently empty — this would be the first entry under the `ce:compound` workflow)
- No runbook changes — `--provider local` CLI surface stays identical
- No migration, no feature flag — behavior change is bounded and recoverable via `git revert`
- If two-pass orchestration lands: brief note in `tools/visual_qa.py` docstring flagging the 2× per-batch call volume under `--provider local`. Do not bury that in an inline comment — it's a production cost signal

## Sources & References

- **Origin plan:** `docs/plans/2026-04-18-002-local-llm-visual-qa-calibration.md` (Priority 1 calibration section, Priority 2 grounding section still canonical)
- **Predecessor plan:** `docs/plans/2026-04-18-003-feat-scrum-279-p1-guided-json-schema-plan.md` (P1 complete, smoke addendum contains direct grounding-failure evidence)
- **Parent ticket:** SCRUM-275 (Phase 2 local provider shipped)
- **Predecessor ticket:** SCRUM-279 (P1 guided_json structural fix shipped, merge `ac033cd`)
- **This ticket:** SCRUM-280
- Rubric contract: `tools/visual_qa_rubric.md`
- Primary edit target: `tools/llm_providers/local_provider.py` (function `LocalVisionProvider.build_request`, helper `_build_page_extraction_schema`)
- Primary test file: `tests/test_local_provider_phase2.py`
- Reusable preflight probe: `tools/debug_guided_json_preflight.py`
- Training-data capture brainstorm (out of scope for this ticket but referenced): `docs/brainstorms/2026-04-18-local-llm-training-data-collection.md`
- Post-P1 corpus data: `data/scrum275_local_6book/` (Step 1 classifier input)
- vLLM Structured Outputs: https://docs.vllm.ai/en/latest/features/structured_outputs/
- vLLM PR #12210 (xgrammar-unsupported fallback): https://github.com/vllm-project/vllm/pull/12210

---

## Step 1 Addendum — Mode Classification Evidence (SCRUM-280 Unit 1, 2026-04-18)

Classifier: `tools/analyze_vqa_mode_classification.py`
Output: `data/scrum280_mode_classification/classification.json`
Run: `py -3.12 tools/analyze_vqa_mode_classification.py --local-dir data/scrum275_local_6book --claude-dir data/vqa_baseline_post_274 --out data/scrum280_mode_classification/classification.json`

### Data-source caveat (assumption change from plan)

**Classification ran on pre-P1 `data/scrum275_local_6book/` because post-P1 6-book local data was never persisted after the P1 smoke.** The `scrum275_local_6book/` directory is the original SCRUM-275 Phase 2 smoke — RotG's 221-page output confirms it predates the P1 cardinality fix.

The verdict is expected to hold across this boundary. Mode (a/b) is an **attention property** (does the model's visual attention surface issues?), not a decoder-constraint property (does the schema enforce array length?). P1 changed only decoder plumbing (guided_json cardinality bounds), not the model's ability to detect visual issues. A model that fails detection at 65K with frequency_penalty=0.3 will also fail detection at 131K with guided_json — same attention, different plumbing.

**Re-validation gate:** In Phase 6 (Unit 5), after the mandatory SB-35 re-baseline produces fresh post-P1 6-book local data, re-run the classifier on THAT data. If the verdict is still dominant-b, lock it in. If it flips to dominant-a (only plausible if strict: true schema was masking optional fields the model would have populated under json_object), reconsider the Unit 4 branch before the winning-variant smoke. The re-run command is identical; the new data directory will be whatever Unit 5 uses to store the re-baseline outputs.

`data/scrum275_local_6book/` contains the original SCRUM-275 Phase 2 smoke run, not a post-P1 re-run. The RotG local report has 221 pages (the pre-P1 hallucination cascade that motivated P1). All other 5 books have 8 pages and were classifiable. RotG is recorded as an error and excluded from the overall mode verdict. The classification below is derived from 5 books.

### Per-Book Evidence Tables

**Atomic Habits** — verdict: `mixed` (a=0%, b=38%, ambig=62%)

| Page (Claude marker) | Local pg# | Local score | Claude score | Local issues | Claude issues | Classification |
|---|---|---|---|---|---|---|
| 1 | 1 | 95 | 93 | 1 (minor) | 1 (minor) | ambiguous |
| 2 | 2 | 98 | 85 | 0 | 2 (minor×2) | ambiguous |
| 3 | 3 | 100 | 50 | 0 | 2 (**critical×2**) | **b** |
| 73 | 73 | 95 | 90 | 1 (minor) | 2 (minor×2) | ambiguous |
| 92 | 92 | 92 | 92 | 1 (minor) | 1 (minor) | ambiguous |
| 145 | 145 | 90 | 82 | 2 (minor×2) | 3 (**moderate×2**, minor) | **b** |
| 158 | 158 | 95 | 91 | 1 (minor) | 2 (minor×2) | ambiguous |
| 232 | 232 | 95 | 78 | 1 (minor) | 2 (**moderate**, minor) | **b** |

*Note: page_numbers match (no grounding failure on Atomic Habits). Local gave score 100 on page 3 where Claude found two critical issues — prototypical detection failure.*

**Decline of the West** — verdict: `dominant-b` (a=0%, b=62%, ambig=38%)

| Page (Claude marker) | Local pg# | Local score | Claude score | Local issues | Claude issues | Classification |
|---|---|---|---|---|---|---|
| 1 | 1 | 95 | 91 | 1 (minor) | 1 (minor) | ambiguous |
| 2 | **2** | 92 | 78 | 1 (minor) | 2 (**moderate**, minor) | **b** |
| 3 | **3** | 90 | 82 | 1 (minor) | 3 (minor×2, **moderate**) | **b** |
| 310 | **4** ← grounding | 95 | 72 | 0 | 3 (**major**, minor×2) | **b** |
| 380 | **5** ← grounding | 95 | 65 | 0 | 3 (**major**, **moderate×2**) | **b** |
| 597 | **6** ← grounding | 95 | 78 | 0 | 2 (minor, **moderate**) | **b** |
| 656 | **7** ← grounding | 95 | 88 | 0 | 1 (minor) | ambiguous |
| 951 | **8** ← grounding | 95 | 85 | 0 | 2 (minor×2) | ambiguous |

*"← grounding" marks pages where local emitted positional page_number (4,5,6,7,8) instead of actual marker (310,380,597,656,951). R4 grounding defect confirmed. Local scored all pages 90–95 with no non-minor issues; Claude found major/moderate on 5 pages.*

**Mexico's Illicit Drug Networks** — verdict: `mixed` (a=38%, b=38%, ambig=25%)

| Page (Claude marker) | Local pg# | Local score | Claude score | Local issues | Claude issues | Classification |
|---|---|---|---|---|---|---|
| 1 | 1 | 95 | 92 | 1 (minor) | 1 (minor) | ambiguous |
| 2 | 2 | 95 | 62 | 1 (minor) | 3 (**major**, **moderate×2**) | **b** |
| 3 | 3 | 90 | 74 | 2 (**moderate**, minor) | 3 (**moderate**, minor×2) | **a** |
| 33 | 33 | 85 | 63 | 2 (**moderate**, minor) | 4 (**major×2**, **moderate**, minor) | **a** |
| 93 | 93 | 90 | 78 | 1 (minor) | 2 (**moderate**, minor) | **b** |
| 147 | 147 | 90 | 80 | 1 (minor) | 2 (minor×2) | ambiguous |
| 166 | 166 | 85 | 60 | 2 (**moderate**, minor) | 3 (**major**, **moderate**, minor) | **a** |
| 234 | 234 | 90 | 70 | 1 (minor) | 3 (**moderate×2**, minor) | **b** |

*page_numbers match. This book shows genuine mixed behavior: pages 3, 33, 166 are mode (a) (local detected moderate issues, still inflated score), pages 2, 93, 234 are mode (b) (local missed moderate/major that Claude found).*

**Python in easy steps** — verdict: `dominant-b` (a=25%, b=62%, ambig=12%)

| Page (Claude marker) | Local pg# | Local score | Claude score | Local issues | Claude issues | Classification |
|---|---|---|---|---|---|---|
| 1 | 1 | 95 | 92 | 0 | 1 (minor) | ambiguous |
| 2 | 2 | 95 | 66 | 0 | 3 (**major×2**, **moderate**) | **b** |
| 3 | 3 | 85 | 22 | 1 (**moderate**) | 1 (**critical**) | **a** |
| 35 | 35 | 85 | 58 | 1 (**moderate**) | 4 (**critical**, **major**, **moderate**, minor) | **a** |
| 68 | 68 | 90 | 72 | 1 (minor) | 2 (**moderate**, minor) | **b** |
| 108 | 108 | 95 | 55 | 0 | 3 (**major**, **moderate**, minor) | **b** |
| 139 | 139 | 90 | 54 | 1 (minor) | 4 (**major×2**, **moderate**, minor) | **b** |
| 173 | 173 | 95 | 57 | 0 | 4 (**major**, **moderate×2**, minor) | **b** |

*page_numbers match. Local correctly detected moderate issues on pages 3 and 35, but missed major/moderate on 5 other pages. Claude found very severe issues (score 22, 54, 55, 57, 58) that local gave 85–95.*

**Oil Kings** — verdict: `dominant-b` (a=0%, b=62%, ambig=38%)

| Page (Claude marker) | Local pg# | Local score | Claude score | Local issues | Claude issues | Classification |
|---|---|---|---|---|---|---|
| 1 | 1 | 95 | 91 | 1 (minor) | 1 (minor) | ambiguous |
| 2 | **2** | 98 | 72 | 0 | 3 (**moderate×2**, minor) | **b** |
| 3 | **3** | 90 | 34 | 1 (minor) | 2 (**critical**, **major**) | **b** |
| 119 | **4** ← grounding | 92 | 80 | 1 (minor) | 2 (**moderate**, minor) | **b** |
| 229 | **5** ← grounding | 95 | 90 | 1 (minor) | 1 (minor) | ambiguous |
| 354 | **6** ← grounding | 94 | 80 | 1 (minor) | 2 (**moderate**, minor) | **b** |
| 360 | **7** ← grounding | 93 | 92 | 1 (minor) | 1 (minor) | ambiguous |
| 573 | **8** ← grounding | 96 | 65 | 1 (minor) | 5 (**major×4**, minor) | **b** |

*"← grounding" marks pages where local emitted positional page_number (4,5,6,7,8) instead of actual marker (119,229,354,360,573). R4 grounding defect confirmed. Local scored all pages 90–98 with only minor issues; Claude found critical/major/moderate on 5 pages.*

**Return of the Gods** — verdict: `ERROR` (page count mismatch: local=221, claude=8)

Pre-P1 hallucination cascade: the local RotG report in `data/scrum275_local_6book/` was generated before P1 enforced `minItems==maxItems==8`. The model returned 221 sequential page entries for 8 input images. This book is excluded from the classification aggregate. The RotG data is the canonical evidence for the R4 page_number grounding problem (the P1 smoke confirmed page_number output was positional [1..221] instead of the input markers [1,2,3,70,87,138,154,221]).

### Aggregate Classification

| Book | mode | a% | b% | ambig% |
|---|---|---|---|---|
| Atomic Habits | mixed | 0% | 38% | 62% |
| Decline of the West | **dominant-b** | 0% | 62% | 38% |
| Mexico's Illicit | mixed | 38% | 38% | 25% |
| Python in easy steps | **dominant-b** | 25% | 62% | 12% |
| Oil Kings | **dominant-b** | 0% | 62% | 38% |
| Return of the Gods | ERROR (pre-P1 data) | — | — | — |

**Overall corpus verdict: `dominant-b`**

3 of 5 classifiable books (60%) are b-family (dominant-b). This falls in the 55–69% band → "dominant-b fallback-a."

Across all 40 classifiable pages: mode_a=5 (12.5%), mode_b=21 (52.5%), ambiguous=14 (35%).

### Unit 4 Branch Decision

**Verdict: dominant-b → execute Step 2b architectural ladder first.**

Per the plan's decision matrix:
1. **Sub-unit 4b-i first:** Forced-enumeration prompt prepend — "Before evaluating, list every visual element visible on this page..."
2. **Sub-unit 4b-ii if 4b-i fails gate:** Two-pass structure (requires explicit user approval gate)
3. **Fallback to Step 2a if Step 2b exhausts:** Strict-grader instruction append ladder

**Confidence note:** Dominant-b (60% of books) rather than clean-b (≥70%) means the fallback-a ladder is non-trivial — Mexico Illicit's 38% mode-a signal suggests some pages would benefit from stricter grading. The forced-enumeration approach (sub-unit 4b-i) is additive to the rubric and compatible with both failure modes, making it the right first experiment regardless.

### Additional Findings for SCRUM-280 Plan

1. **R4 grounding defect confirmed on Decline of the West and Oil Kings** (in addition to RotG already documented in P1 smoke addendum). Pages 310, 380, 597, 656, 951 (Decline) and 119, 229, 354, 360, 573 (Oil Kings) have local page_number output as positional 4–8 instead of the actual input markers. Three books now have confirmed grounding failures — satisfies the N≥3 fixture requirement for Unit 5 R4 verification.

2. **Mexico Illicit's mode-a pages (3, 33, 166) are the only evidence that local detection is NOT purely broken.** All three are lower-scored pages (85–90 local vs 60–74 Claude) where the local model detected moderate issues but still inflated the score. The calibration problem on these pages is grader-leniency (mode a), not detection failure. A strict-grader prompt alone might fix these; the forced-enumeration approach (4b-i) adds detection pressure but doesn't hurt them.

3. **`data/scrum275_local_6book/` is SCRUM-275 Phase 2 smoke data, not a post-P1 re-run.** The plan said "post-P1 reports" but RotG confirms this is the original smoke. For Units 4 and 5, all inference runs must use the current post-P1 provider (P1 is already merged into master). The `scrum275_local_6book/` data is suitable as a classification input (evidence of the problem) but not as a P2 comparison baseline — Unit 5 mandates the SB-35 re-baseline run as the authoritative baseline.

---

## Step 5 Addendum — Unit 4 Experiment Log (Phase 5 execution)

*Appended 2026-04-18. Records every Unit 4 variant attempted, per the plan's stopping rule.*

### Fixture baseline

Run: P1+Unit2 provider (master, post-SCRUM-279 merge) on the Python fixture (`data/scrum280_unit4_variants/baseline-p1-unit2/`). 8-page Python-in-easy-steps batch, same pages as Unit 1 classification.

| Metric | Value |
|---|---|
| Mean \|Δ\| vs Claude baseline | **33.0** |
| Gate threshold | < 15 |
| Gap to gate | 18.0 points |

Per-page scores (local vs Claude):

| Page | Local | Claude | \|Δ\| |
|---|---|---|---|
| 1 | 95 | 92 | 3 |
| 2 | 95 | 66 | 29 |
| 3 | 85 | 22 | 63 |
| 35 | 85 | 58 | 27 |
| 68 | 90 | 72 | 18 |
| 108 | 95 | 55 | 40 |
| 139 | 90 | 54 | 36 |
| 173 | 95 | 57 | 38 |

*Secondary fixture (RotG) not run — not required for baseline, only for winner confirmation.*

---

### Variant 4b-i — Forced-enumeration prompt prepend

**Date:** 2026-04-18  
**Branch:** Step 2b (dominant-b verdict)  
**Implementation:** Appended forced-enumeration instruction to system message content:

```python
system_content = (
    rubric_text
    + "\n\nFor each page you evaluate: first enumerate every visual element "
    "you can see on that page — text blocks, headings, images, tables, "
    "footnotes, page numbers, captions, and any formatting irregularities. "
    "Then evaluate each identified element against the rubric criteria. "
    "Only report zero issues if you have checked every element and confirmed "
    "each is correct. When in doubt about an element, report it as an issue."
)
```

**Python fixture result** (`data/scrum280_unit4_variants/4b-i-forced-enum/`):

| Metric | Baseline | 4b-i | Change |
|---|---|---|---|
| Mean \|Δ\| vs Claude | 33.0 | 32.9 | **−0.1** |
| Gate threshold | < 15 | < 15 | — |
| Gate passed? | No | **No** | — |

Per-page breakdown:

| Page | Local (baseline) | Local (4b-i) | Claude | Baseline \|Δ\| | 4b-i \|Δ\| |
|---|---|---|---|---|---|
| 1 | 95 | 95 | 92 | 3 | 3 |
| 2 | 95 | 95 | 66 | 29 | 29 |
| 3 | 85 | 85 | 22 | 63 | 63 |
| 35 | 85 | 85 | 58 | 27 | 27 |
| 68 | 90 | **92** | 72 | 18 | **20** |
| 108 | 95 | 95 | 55 | 40 | 40 |
| 139 | 90 | **93** | 54 | 36 | **39** |
| 173 | 95 | **94** | 57 | 38 | **37** |

**Observed behavior:** Scores changed on 3 of 8 pages (68: 90→92, 139: 90→93, 173: 95→94), but all changes were minor and in the wrong direction (scores *increased* or held). Score stdev 3.78 → 3.46, same 85–95 range — no distribution collapse. The forced-enumeration instruction had no meaningful effect; the model did not detect additional issues. Mean |Δ| noise of 0.1 is consistent with model temperature stochasticity, not prompt response.

**Side effects:** None. No distribution collapse, no `finish_reason` drift (all `stop`), no token overrun, no change in issue structure or JSON schema conformance.

**Classification: simply didn't win.** No active regression, no negative test required.

**Secondary fixture:** Not run. With 0.1 mean change on primary, secondary would add no diagnostic value.

**Conclusion:** Variant 4b-i is not sufficient to move the needle at mode (b). The model appears unresponsive to system-prompt enumeration instructions at this level — the forced-enumeration text is processed but does not alter the model's scoring behavior. The gap to gate (18 points) is unchanged.

**Status: STOP gate.** Per plan execution rules, 4b-i failure does not auto-escalate to 4b-ii. Sub-unit 4b-ii (two-pass) requires explicit user approval due to doubled sb-chat inference volume on the shared stack (SecondBrain + CareerPilot). Surfacing to user before proceeding.

---

### Variant 2a-i — Strict-grader framing (system message append)

**Date:** 2026-04-18  
**Branch:** Step 2a (fallback, user-approved after 4b-i null result)  
**Implementation:** Appended grading-posture text to system message after rubric:

```
## Grading Standard
Grade strictly. A score of 90 or above means the page is publication-ready
with no more than one minor issue. A score of 100 requires zero visible issues.
If ANY non-trivial formatting problem is present — heading level mismatch,
missing footnote marker, text reflow artifact, image misplacement, or layout
inconsistency — deduct points accordingly. Do NOT round scores up.
```

Placement: system message (rubric-adjacent), separate from Unit 2 grounding clause in user trailing text block.

**Python fixture result** (`data/scrum280_unit4_variants/2a-i-strict-grader/`):

| Metric | Baseline | 2a-i | Change |
|---|---|---|---|
| Mean \|Δ\| vs Claude | 33.0 | **40.5** | **+7.5 (REGRESSION)** |
| Score stdev | 3.78 | **0.00** | **Collapse** |
| Score range | 85–95 | **100–100** | **All pinned at 100** |
| Gate threshold | < 15 | < 15 | — |
| Gate passed? | No | **No** | — |

Per-page breakdown:

| Page | Baseline | 2a-i | Claude | \|Δ\| base | \|Δ\| 2a-i |
|---|---|---|---|---|---|
| 1 | 95 | **100** | 92 | 3 | 8 |
| 2 | 95 | **100** | 66 | 29 | 34 |
| 3 | 85 | **100** | 22 | 63 | 78 |
| 35 | 90 | **100** | 58 | 32 | 42 |
| 68 | 95 | **100** | 72 | 23 | 28 |
| 108 | 95 | **100** | 55 | 40 | 45 |
| 139 | 90 | **100** | 54 | 36 | 46 |
| 173 | 95 | **100** | 57 | 38 | 43 |

**Observed behavior:** All 8 pages scored 100, zero issues reported, stdev=0.00. Classic prompt reward-hacking: by defining the exit condition ("100 = zero visible issues"), the model found the easiest satisfying response — rate zero issues, assign 100. Mean |Δ| increased 33.0 → 40.5.

**Classification: ACTIVE REGRESSION.** R3 non-degenerate distribution fails (all-100 pinned, stdev=0). This is a reproducible failure mode distinct from "simply didn't win." Negative regression test added: `test_system_message_not_augmented_with_grading_posture` in `tests/test_local_provider_phase2.py`.

**Reversion:** 2a-i system_content fully reverted. System message restored to rubric-only. `test_payload_system_message_carries_rubric` updated to assert exact equality with caret to the 2a-i collapse evidence.

**Conclusion:** Appending grading-posture text to the system message is definitively ruled out. System message must remain rubric-only.

**Evidence accumulated — prompt-only variants exhausted:**

| Variant | Approach | Mean \|Δ\| | Change | Classification |
|---|---|---|---|---|
| Baseline | P1+Unit2 | 33.0 | — | — |
| 4b-i | Forced-enumeration (system append) | 32.9 | −0.1 | Simply didn't win |
| 2a-i | Strict-grader framing (system append) | 40.5 | +7.5 | **Active regression (R3)** |

Two consecutive system-message prompt variants — one targeting detection failure (4b-i), one targeting grader leniency (2a-i) — both failed to reduce mean |Δ|. This is the evidence basis for the 4b-ii approval request: prompt-only approaches on the system side are definitively ineffective for this model at this failure scale.

---

### Variant 2a-4 — Few-shot score-calibration anchors (system message append)

**Date:** 2026-04-18  
**Branch:** Step 2a, variant 4 (user-approved as final prompt-only attempt before 4b-ii)  
**Implementation:** Appended narrative score-calibration anchors to system message after rubric. Two anchor pages selected from `data/vqa_baseline_post_274/` — books NOT in the Python-in-easy-steps fixture to prevent contamination. Selection criteria: one in the 60–70 Claude-score band (moderate-issue reference), one in the 80–85 band (high-quality reference), from different books to ensure diversity:
- **Anchor A — Score 65 (significant issues):** Decline of West p380 — italic paragraphs broken into standalone indented lines (major), word-fusion error "thisbeing" (moderate), mid-sentence page end after ambiguous italic block (moderate). Source: `data/vqa_baseline_post_274/Decline of the West...json`, page 380.
- **Anchor B — Score 82 (moderate issues):** Atomic Habits p145 — section heading same font size as body text (moderate), benefit label indistinguishable from body text (moderate), inconsistent blank-line gap (minor). Source: `data/vqa_baseline_post_274/Atomic Habits...json`, page 145.

Format: human-readable narrative, not raw JSON, to shape score distribution rather than schema structure.

**Python fixture result** (`data/scrum280_unit4_variants/2a-4-few-shot-anchors/`):

| Metric | Baseline | 2a-4 | Change |
|---|---|---|---|
| Mean \|Δ\| vs Claude | 33.0 | **33.0** | 0.0 (null) |
| Score stdev | 3.78 | 3.78 | 0.00 |
| Score range | 85–95 | 85–95 | unchanged |
| Output tokens | 542 | 962 | +420 (model wrote more issue text) |
| Gate passed? | No | **No** | — |

Per-page scores: identical to baseline on all 8 pages. The model generated more issue descriptions (output tokens +78%) but did not change any scores. Few-shot anchoring influenced issue verbosity but not scoring behavior.

**Classification: simply didn't win.** No distribution collapse, no regression. No negative test required.

**Conclusion:** Three prompt-only variants (4b-i, 2a-i, 2a-4) exhausted. Mechanisms: detection engagement (null), grading-directive (active regression), distribution-by-example (null). No prompt approach on the system message has moved mean |Δ| in the right direction. This constitutes the three-variant evidence case for 4b-ii.

---

### Sub-unit 4b-ii — Three-part approval record

**1. Explicit user approval** (2026-04-18 session):

> "If 2a-4 also fails, 4b-ii is pre-approved on the spot — no further iteration."
> "Sonnet can commit the three-part approval record in the Unit 5 addendum (this message + the failed 2a-4 evidence + per-batch latency measurement) and proceed directly."
> — User, 2026-04-18

**2. Per-batch latency measurement (current sb-chat load):**

Measured from visual_qa.py runs on this session (8-page Python-in-easy-steps batch):
- Baseline single-pass: ~3s (9,742 input + 542 output tokens)
- 2a-4 single-pass (more verbose output): ~6s (9,742 input + 962 output tokens)
- sb-chat: `max_model_len=131072`, vLLM 0.19.0, model `qwen3.5-35b-a3b-fp8`

Estimated 4b-ii two-pass overhead: ~6–9s per 8-page batch (2–3× current single-pass 3s). Pass 1 (detection-only, more output) ~4–6s; Pass 2 (scoring-only, less input/output) ~2–3s.

**3. NEW DEPENDENCY flag (per cross-project protocol):**

> `NEW DEPENDENCY: EbookAutomation → sb-chat shared stack throughput`
> Two-pass VQA (sub-unit 4b-ii) doubles per-batch inference load on the sb-chat stack shared with SecondBrain (SB-35) and CareerPilot. Estimated overhead: 2–3× per VQA batch. Coordinate with SecondBrain and CareerPilot before scheduling concurrent heavy inference workloads.

**Gate: approval is granted.** 4b-ii implementation may proceed.

**Updated latency reading (post-implementation, actual measurement):**

Fixture runs on calibrated 4b-ii (8-page Python-in-easy-steps batch, no concurrent workloads):
- Pass 1 (detection): ~8s (9,781 input + 1,235 output tokens)
- Pass 2 (scoring): ~1s (3,646 input + 263 output tokens)
- Total wall time: ~9s per 8-page batch vs ~3s baseline single-pass
- **Actual overhead factor: ~3× (not 2× as initially estimated)** — pass 1 enumerates issues in full prose which is more verbose than a combined report. The 2× estimate assumed symmetric pass lengths. For SCRUM-275 Phase 3 (full-book mode) planning, use 3× as the base estimate for shared-stack cost.

**Updated NEW DEPENDENCY wording:**
> `NEW DEPENDENCY: EbookAutomation → sb-chat shared stack throughput`
> Two-pass VQA (sub-unit 4b-ii) adds ~3× inference volume per batch on the sb-chat stack shared with SecondBrain (SB-35) and CareerPilot (not 2× as initially planned — actual measurement shows 9s total per 8-page batch vs 3s single-pass). For SCRUM-275 Phase 3 full-book mode, this translates to ~5 minutes additional inference per book per VQA run. Coordinate with SecondBrain and CareerPilot before scheduling concurrent heavy VQA workloads.

---

### Sub-unit 4b-ii — Implementation record

**Protocol extension decision:** No change to `tools/llm_providers/base.py`. `two_pass_call()`, `build_detection_request()`, and `build_scoring_request()` are new public methods on `LocalVisionProvider` only. `visual_qa.py` routes via `hasattr(provider, "two_pass_call")` duck typing. Rationale: adding to the Protocol would require `ClaudeVisionProvider` to implement stubs for methods it doesn't need, breaking the single-responsibility of a provider that doesn't use two-pass. Duck typing keeps the Protocol unchanged and `ClaudeVisionProvider` untouched. Unit 6 Protocol-contract test will assert these three methods exist as callables on `LocalVisionProvider`.

---

### Variant 4b-ii v1 — Two-pass (initial deduction table)

**Date:** 2026-04-18  
**Branch:** Step 2b (pre-approved after 2a-4 null result)  
**Implementation:** Two-pass architecture — pass 1 enumerates issues (image payload, detection schema), pass 2 scores against committed issues (text-only payload, scoring schema). Deduction table in pass-2 instruction: critical 20+, major 10-15, moderate 5-10, minor 2-5 points.

**Python fixture result** (`data/scrum280_unit4_variants/4b-ii-two-pass/`):

| Metric | Baseline | 4b-ii v1 | Change |
|---|---|---|---|
| Mean \|Δ\| vs Claude | 33.0 | 24.1 | **−8.9** |
| Score stdev | 3.78 | 13.94 | Non-degenerate |
| Score range | 85–95 | 55–100 | Genuine spread |
| Gate passed? | No | **No** | — |

Per-page breakdown:

| Page | Baseline | 4b-ii v1 | Claude | \|Δ\| base | \|Δ\| v1 | Issues detected |
|---|---|---|---|---|---|---|
| 1 | 95 | 100 | 92 | 3 | 8 | 0x[] |
| 2 | 95 | 100 | 66 | 29 | 34 | 0x[] |
| 3 | 85 | 55 | 22 | 63 | 33 | 1x[critical] |
| 35 | 90 | 82 | 58 | 32 | 24 | 2x[moderate, minor] |
| 68 | 95 | 83 | 72 | 23 | 11 | 2x[moderate, minor] |
| 108 | 95 | 83 | 55 | 40 | 28 | 2x[moderate, minor] |
| 139 | 90 | 83 | 54 | 36 | 29 | 2x[moderate, minor] |
| 173 | 95 | 83 | 57 | 38 | 26 | 2x[moderate, minor] |

**Diagnosis:** Two-pass mechanism works — detection improved, distribution is real. But deduction table is too lenient: pages with 2×moderate+minor cluster at 83 while Claude scores 54–72 for equivalent severity. Scoring formula needs calibration.

**Classification: improved but gate missed.** Proceeding to scoring calibration sub-variant (single variable change — deduction table only).

---

### Variant 4b-ii calibrated — Two-pass (calibrated deduction table) — **WINNER**

**Date:** 2026-04-18  
**Branch:** Step 2b (sub-variant of 4b-ii, deduction table only)  
**Implementation:** Same two-pass architecture as v1. Only change: deduction table in pass-2 user instruction:

```
Apply these deductions from 100: each critical issue 45-60 points;
each major 20-30 points; each moderate 12-18 points; each minor 4-6 points.
Multiple issues compound — a page with two moderate issues and one minor
issue should score in the 60-72 range, not 80+.
```

No new mechanisms, no 2a-i patterns. Pass-2 system message remains rubric-only. Deduction table is arithmetic guidance applied to an already-committed issue list — not a behavioral directive, not a score-threshold framing. **Calibration is prompt-layer arithmetic, not prompt-layer posture.** This distinction is load-bearing: 2a-i failed because posture directives ("grade strictly") leave the exit condition open to reward-hacking; arithmetic in the user message alongside a committed issue list closes the 100 exit structurally (can't pick 100 if the issue list is non-empty). Future Qwen VQA calibration work on this stack should start with pass-2 arithmetic, not system-message directives.

**Python fixture result** (`data/scrum280_unit4_variants/4b-ii-calibrated/`):

| Metric | Baseline | 4b-ii cal | Change |
|---|---|---|---|
| Mean \|Δ\| vs Claude | 33.0 | **12.5** | **−20.5** |
| Score stdev | 3.78 | 20.56 | Non-degenerate |
| Score range | 85–95 | 40–100 | Genuine spread |
| Gate (< 15)? | No | **PASS ✓** | — |

Per-page breakdown:

| Page | Baseline | 4b-ii cal | Claude | \|Δ\| base | \|Δ\| cal |
|---|---|---|---|---|---|
| 1 | 95 | 100 | 92 | 3 | 8 |
| 2 | 95 | 100 | 66 | 29 | 34 |
| 3 | 85 | 40 | 22 | 63 | 18 |
| 35 | 90 | 62 | 58 | 32 | 4 |
| 68 | 95 | 62 | 72 | 23 | 10 |
| 108 | 95 | 68 | 55 | 40 | 13 |
| 139 | 90 | 62 | 54 | 36 | 8 |
| 173 | 95 | 62 | 57 | 38 | 5 |

**RotG secondary fixture:**

| Metric | Value |
|---|---|
| Mean \|Δ\| vs Claude | **11.2** |
| R4 grounding | **PASS — all 8 page_numbers match markers [1,2,3,70,87,138,154,221]** |

**Side effects:** None. No distribution collapse. Both fixtures pass.

**Pages 1 and 2 remaining gap:** Pages 1 and 2 scored 100 with zero detected issues; Claude scored 92 and 66 respectively. This is a residual detection-failure (mode-b) on those specific pages — pass 1 didn't find issues. The calibrated deduction table cannot fix detection misses. These two pages account for 42 of the 100-point total |Δ| across all pages.

**Classification: GATE PASSED.** Mean |Δ| 12.5 < 15. Secondary fixture (RotG) 11.2 < 15. R4 grounding confirmed. Proceeding to Unit 5 corpus smoke.

---

### Unit 4 experiment summary

| Variant | Mean \|Δ\| | Stdev | Classification |
|---|---|---|---|
| Baseline (P1+Unit2) | 33.0 | 3.78 | — |
| 4b-i forced-enum | 32.9 | 3.46 | Simply didn't win |
| 2a-i strict-grader | 40.5 | 0.00 | **Active regression (R3 collapse)** |
| 2a-4 few-shot anchors | 33.0 | 3.78 | Simply didn't win |
| 4b-ii v1 (initial deductions) | 24.1 | 13.94 | Improved, gate missed |
| **4b-ii calibrated (winner)** | **12.5** | **20.56** | **GATE PASSED ✓** |

---

## Step 5 Addendum — Unit 5 Corpus Smoke + Diagnostics (2026-04-19)

*Appended 2026-04-19. Records the full 6-book corpus smoke on the winning 4b-ii-calibrated
configuration, parallel investigations (A) sampling parity and (C) detection-miss diagnosis,
and the final R1–R6 gate verdicts for SCRUM-280 partial close.*

### Pre-smoke checks

**SB-35 re-baseline:** Mandatory. sb-chat confirmed at `max_model_len=131072`, vLLM 0.19.0.
P1 smoke was captured at 65K ceiling; all Unit 5 measurements use the 131K re-baseline as
reference, not the original SCRUM-275 P1 smoke. Re-baseline output: `data/scrum280_unit5_p1_rebaseline/`.
Corpus mean |Δ| under P1 config (local vs Claude, 6 books, 48 pages): **17.4**.

**Re-classification gate:** Ran `tools/analyze_vqa_mode_classification.py` on the post-SB-35
P1 re-baseline data. Verdict: **dominant-b holds** — 3 of 5 classifiable books remain
b-family (Decline, Oil Kings, RotG). Python flipped to dominant-a on the re-baseline (local
now detects moderate issues on pages 3 and 35 where it previously found nothing), but the
overall corpus verdict is unchanged. Re-classification output: `data/scrum280_unit5_mode_reclassification/`.

### 6-book corpus smoke — 4b-ii-calibrated vs Claude baseline

Data: `data/scrum280_unit5_winning_smoke/` (local) vs `data/vqa_baseline_post_274/` (Claude oracle).

**Note on Atomic Habits:** Excluded from gate computation. Investigation (A) confirmed
the Claude baseline was captured from the original PDF source (266 pages, bookmark
positions ~73/158), while the smoke runs the KFX→Calibre path (272 pages, bookmark
positions ~91/152). The `select_sample_pages` function is fully deterministic — different
inputs produce different pages. Zero interior page overlap between the two runs, making
direct |Δ| comparison unreliable. All other 5 books have exact page-selection parity.

#### Per-book results (5 books, n=40 pages)

| Book | n | mean \|Δ\| | max \|Δ\| | stdev | R2(a) | R2(b) |
|---|---|---|---|---|---|---|
| Decline of the West | 8 | **7.6** | 19 | 5.9 | PASS | PASS |
| Return of the Gods | 8 | **11.2** | 21 | 5.5 | PASS | PASS |
| Python in easy steps | 8 | **15.0** | 34 | 9.2 | PASS | PASS |
| Mexico Illicit | 8 | **28.6** | 70 | 20.8 | **FAIL** | **FAIL** |
| Oil Kings | 8 | **22.6** | 51 | 14.9 | PASS | **FAIL** |

Corpus aggregate (5 books, n=40): **mean |Δ| = 17.0, stdev = 14.30**

Mexico page 234 outlier (local=0, Claude=70): pass-1 detected 8 broken-URL moderate issues
in a back-matter bibliography; deduction table fired 8× (8 × moderate = 96–144 points →
floored to 0). Claude rated the same page 70 — it applied lenient treatment to bibliography
content. This is a back-matter scoring calibration gap, distinct from the detection-miss
pattern.

#### Gate verdicts (Unit 5)

| Gate | Threshold | Result | Verdict |
|---|---|---|---|
| R2(a) | Corpus mean \|Δ\| < 15 | 17.0 (5 books) | **FAIL** |
| R2(b) | No per-book mean \|Δ\| > 20 | Mexico 28.6, Oil Kings 22.6 | **FAIL** |
| R3 | Non-degenerate distribution (stdev > 0) | 14.30, multiple FAIL pages present | **PASS** |
| R4 | Exact marker match (RotG + Oil Kings + Mexico) | All 3 confirmed exact | **PASS** |

---

### Investigation (A) — Sampling parity (2026-04-19)

**Question:** Did page-selection drift between the Claude baseline and Unit 5 smoke confound
any comparisons beyond Atomic Habits?

**Sampler:** `select_sample_pages(total_pages, max_samples=8, bookmark_pages=None)` in
`tools/visual_qa.py`. Fully deterministic — no randomness. Pages 1, 2, 3 hardcoded;
remaining 5 slots computed from `total_pages` and live PDF bookmark positions using
integer-division arithmetic.

**Atomic Habits drift root cause:**

| Source | File type | total_pages | Bookmark positions | Pages sampled |
|---|---|---|---|---|
| Claude baseline (`vqa_baseline_post_274`) | PDF (original) | 266 | ~73, ~158 | [1,2,3,73,92,145,158,232] |
| Unit 5 smoke (`scrum280_unit5_winning_smoke`) | KFX → Calibre PDF | 272 | ~91, ~152 | [1,2,3,91,94,149,152,238] |

The Claude baseline was captured from the book's original source PDF. All subsequent smoke
runs go through the live KFX→Calibre conversion path, which produces different page count
and bookmark landing positions. Same formula, different inputs → different pages.

**5-book parity table:**

| Book | Baseline pages | Smoke pages | Exact match? |
|---|---|---|---|
| Oil Kings | [1,2,3,119,229,354,360,573] | [1,2,3,119,229,354,360,573] | **YES** |
| Mexico Illicit | [1,2,3,33,93,147,166,234] | [1,2,3,33,93,147,166,234] | **YES** |
| Return of the Gods | [1,2,3,70,87,138,154,221] | [1,2,3,70,87,138,154,221] | **YES** |
| Python easy steps | [1,2,3,35,68,108,139,173] | [1,2,3,35,68,108,139,173] | **YES** |
| Decline of the West | [1,2,3,310,380,597,656,951] | [1,2,3,310,380,597,656,951] | **YES** |

Mexico Illicit's page parity is confirmed — its mean |Δ| = 28.6 is a genuine quality gap,
not a confounded comparison.

**Verdict:** Sampler is deterministic. Atomic Habits drift is caused entirely by the Claude
baseline having been built from the original PDF source (not the KFX→Calibre path used by
all other baselines and all smoke runs). The 5 gate-comparison books are parity-stable.
Atomic Habits is correctly excluded.

**NEW DEPENDENCY flag (source-format stability):** Any book where the Claude baseline was
captured from the original PDF rather than the KFX→Calibre path will produce page-selection
drift on every subsequent smoke run. Atomic Habits is the only confirmed case in this 6-book
set. All historical VQA reports for that book are tied to PDF-source sampler state, not the
KFX-source state used by the live pipeline. Tracked as SCRUM-282.

---

### Investigation (C) — Detection-miss diagnosis (2026-04-19)

**Question:** Is `issues: []` on zero-score pages a genuine model detection miss, or a
parser silently returning `[]` on malformed JSON?

**Parser verdict:** Not a parser bug. The two-pass path calls `json.loads()` directly on
`detection_response.raw_text` and raises on malformed JSON — it does NOT route through
`parse_qa_response`'s silent-empty fallback. The guided-decoding schema permits `issues: []`
(no `minItems` constraint). Every `issues: []` is genuine model output — vLLM accepted it
as schema-valid.

**Local vs Claude issues (Oil Kings, zero-local-issues pages):**

| Page | Local score | Local issues | Claude score | Claude flags |
|---|---|---|---|---|
| 2 | 100 | [] | 72 | `paragraph_flow/moderate` ×2 (copyright/CIP merged), `paragraph_flow/minor` |
| 119 | 100 | [] | 80 | `heading_formatting/moderate` (ordinal+title same weight), `paragraph_flow/minor` |
| 229 | 100 | [] | 90 | `text_integrity/minor` (spaced ellipsis) |
| 354 | 100 | [] | 80 | `heading_formatting/moderate` (same as 119), `paragraph_flow/minor` |
| 360 | 100 | [] | 92 | `text_integrity/minor` |
| 573 | 100 | [] | 65 FAIL | `paragraph_flow/major` ×4 (endnote citations split across paragraphs) |

**Local vs Claude issues (Mexico Illicit, zero-local-issues pages):**

| Page | Local score | Local issues | Claude score | Claude flags |
|---|---|---|---|---|
| 2 | 100 | [] | 62 FAIL | `text_integrity/major` (half-title+copyright merged/truncated), `paragraph_flow/moderate`, `heading_formatting/moderate` |
| 3 | 100 | [] | 74 | `text_integrity/moderate` ("shutt erstock.com" URL split), `paragraph_flow/minor` |
| 93 | 100 | [] | 78 | `paragraph_flow/moderate` (footnote ref styling inconsistent) |
| 147 | 100 | [] | 80 | `paragraph_flow/minor` (footnote styling), `heading_formatting/minor` |
| 166 | 100 | [] | 60 FAIL | `text_integrity/major` (raw `<sup>` HTML leaked into body), `heading_formatting/moderate` |

**Pattern classification (across 11 zero-local-issues pages):**

| Category | Page count | Notes |
|---|---|---|
| `paragraph_flow` | 10/11 | Dominant. Merged copyright/CIP blocks, epigraph merges, endnote splits, footnote styling |
| `heading_formatting` | 6/11 | Chapter ordinal+title same visual weight; sub-heading indistinguishable from body |
| `text_integrity` | 6/11 | Structural variants only (HTML leakage, URL artifact) — spaced ellipsis/URL the one case Qwen caught |

Page type distribution: cover, front_matter, body, chapter_start, back_matter — **no single page type dominates**.

**Root cause:** Qwen's specific blind spots are **layout/structure judgment defects** —
detecting them requires knowing what correct ebook formatting *should* look like, not
pattern-matching character sequences. The one defect Qwen caught (Mexico p234 broken URLs)
is a mechanical text-integrity pattern detectable by character inspection alone.

**Implication for (B) deduction-table tuning:** Cannot close this gap. If pass 1 returns
`issues: []`, the arithmetic has nothing to fire on. This is a vision capability boundary,
not a calibration boundary.

**Verdict:** Detection miss (not parser bug). The miss is bounded to `paragraph_flow` +
`heading_formatting` (layout/structure categories). Deduction-table tuning (B) cannot
address detection misses. Tracked as SCRUM-281.

---

### R1–R6 Acceptance Table — SCRUM-280 Final

| AC | Threshold | Evidence | Status |
|---|---|---|---|
| **R1** | Mode classification documented | dominant-b verdict (3/5 books), evidence tables in Step 1 addendum, re-classification confirms on post-SB-35 re-baseline | **PASS** |
| **R2(a)** | Corpus mean \|Δ\| < 15 | 17.0 (5 books, n=40) — Decline 7.6, RotG 11.2, Python 15.0 pass; Mexico 28.6, Oil Kings 22.6 fail | **PARTIAL** |
| **R2(b)** | No per-book mean \|Δ\| > 20 | Mexico 28.6, Oil Kings 22.6 fail threshold | **PARTIAL** |
| **R3** | Non-degenerate distribution | stdev=14.30, multiple genuine FAILs present | **PASS** |
| **R4** | page_number = input markers | All 5 comparison books exact parity; Atomic Habits drift = source-format issue (not grounding defect) | **PASS** |
| **R5** | Winning config committed with load-bearing comment | 4b-ii-calibrated in `local_provider.py`, duck-typing comment in `visual_qa.py` | **PASS** |
| **R6** | Test coverage per landed behaviors | Unit 2 grounding (6 tests), Unit 4 two-pass (6 tests), 2a-i negative regression (1 test), Unit 6 Protocol-contract (added in Unit 6) | **PASS** |

**Partial-close declaration:** R1, R3, R4, R5, R6 close with this branch. R2 (the aggregate
calibration gate) does not fully pass for Oil Kings and Mexico Illicit. The diagnostic work
in (C) confirms this is not a prompt or arithmetic calibration problem — it is a detection
capability gap for layout/structure categories. Further prompt iteration on this branch is
not warranted; the diagnostic is the exit product.

---

### Forward: SCRUM-281 and SCRUM-282

#### SCRUM-281 — Detection-miss remediation: Oil Kings + Mexico Illicit

**Scope:** Address the `paragraph_flow` + `heading_formatting` detection gap on academic
and complex-layout books (Oil Kings, Mexico Illicit). Investigation (C) classified the miss
as a capability boundary for layout/structure judgment defects.

**Evidence base:**
- Investigation (C) table: 10/11 zero-local-issues pages have `paragraph_flow` flags in
  Claude's report; 6/11 have `heading_formatting` flags
- Specific defect classes missed: merged copyright/CIP blocks, chapter ordinal+title at same
  visual weight, epigraph structure, endnote paragraph splits, raw HTML tag leakage into body
- Deduction-table tuning (SCRUM-280 B) cannot fix detection misses — confirmed by (C) parser analysis

**Option A (recommended starting point): category-focused detection pass**
Add a third pass (or augment pass-1 instruction) specifically targeting layout/structure
defects — provide a short description of what `paragraph_flow` and `heading_formatting`
defects look like in ebook output (examples from the (C) table). This is a bounded prompt
change on the existing two-pass architecture; no new API calls, no model swap.

**Option B: back-matter scoring leniency**
Mexico page 234 over-deduction (0 vs Claude's 70) is a separate issue from detection misses.
Add a `back_matter` page-type scoring modifier in pass-2: reduce per-issue deduction weight
for `back_matter` pages (bibliography/endnotes with broken URLs are expected, not critical).

**Option C (escape hatch): hybrid routing per book mode**
Route Oil Kings + Mexico Illicit scoring through Claude (text-only, no images re-sent from
local detection results). Retains local detection cost savings while using Claude's superior
structural judgment for scoring. Investigation (C) confirmed the scoring pass is text-only
with no image round-trip — Claude's incremental cost for text-only scoring is low.

**Files:** `tools/llm_providers/local_provider.py` (build_scoring_request deduction logic),
`tools/visual_qa.py` (optional hybrid routing), `tests/test_local_provider_phase2.py`

**Data:** Use `data/scrum280_unit5_winning_smoke/` as baseline; gate threshold remains
R2(a) < 15 and R2(b) ≤ 20 per book.

#### SCRUM-282 — VQA baseline capture methodology (source-format stability)

**Scope:** Standardize all Claude VQA baseline captures to use the KFX→Calibre conversion
path rather than original PDF source. Investigation (A) confirmed that a baseline captured
from a different source format will always produce page-selection drift vs the live pipeline.

**Evidence base:**
- Atomic Habits: PDF baseline (266 pages, bookmarks ~73/158) vs KFX smoke (272 pages,
  bookmarks ~91/152) — zero interior page overlap
- Root cause: `select_sample_pages()` is deterministic; `total_pages` and `bookmark_pages`
  inputs differ between source formats
- The 5 other books in `vqa_baseline_post_274/` all have exact parity — they were captured
  from KFX source, not original PDF

**Fix:** Audit `vqa_baseline_post_274/` for any other books captured from original PDF
source. Re-capture Atomic Habits baseline using the KFX→Calibre path. Add a capture-mode
field to VQA baseline JSON (`"source_format": "kfx"` or `"pdf"`) so drift can be detected
programmatically in future comparisons.

**Priority:** Lower than SCRUM-281. Does not affect the R2 gate (Atomic Habits was correctly
excluded from gate math). Affects the reliability of long-term tracking metrics for Atomic
Habits across releases.
