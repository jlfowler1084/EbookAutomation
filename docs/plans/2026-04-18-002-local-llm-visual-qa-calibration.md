---
date: 2026-04-18
plan_id: 2026-04-18-002
title: Local VQA calibration investigation — grader leniency in Qwen3.5-35B-A3B
status: draft
parent_plan: docs/plans/2026-04-13-001-local-llm-visual-qa.md
parent_ticket: SCRUM-275
proposed_ticket: SCRUM-next (investigation)
ce_phase_reference: Phase 5 (baseline comparison + calibration)
owner: Joe
estimated_sessions: 2 (1 Opus for experiment design, 1 Sonnet for execution)
---

# Ticket Draft — Local VQA Calibration Investigation

## Summary

Investigate and remediate grader-leniency bias observed in SCRUM-275 Phase 2 live smoke testing. Local Qwen3.5-35B-A3B provider produces structurally-valid output but scores every page 100/100, disagreeing dramatically with Claude baseline (e.g., p3 empty TOC: Claude=22, Local=100, Δ=78). Must determine whether this is a **grading bias** (fixable via prompt engineering) or a **detection failure** (requires model swap), then remediate.

## Context

SCRUM-275 Phase 2 closed the literal plumbing gate across three smoke iterations:

| Version | max_tokens | frequency_penalty | Pages returned | Output tokens | Overall score |
|---|---|---|---|---|---|
| v1 | 8192 | 0.3 | 5 of 8 (with `{}` trailers) | 541 | 71 |
| v2 | 16384 | 0.3 | 5 of 8 (with `{}` trailers) | 374 (↓) | 71 |
| v3 | 16384 | removed | 8 of 8 ✓ | 400 | 100 ⚠️ |

v1→v2 falsified the max_tokens-budget hypothesis (output decreased with more headroom = self-limiting, not truncation). v2→v3 fixed the true cause (frequency_penalty=0.3 penalizing repeated JSON schema tokens). Plumbing is complete; calibration is the remaining question.

**Per-page scores, Python in easy steps, v3 run:**

| Page | Claude | Local | Δ |
|---|---|---|---|
| p1 (cover) | 92 | 100 | 8 |
| p2 (front matter) | 68 | 100 | 32 |
| p3 (TOC) | 22 | 100 | 78 |
| p35 (body) | 58 | 100 | 42 |
| p68 | 72 | 100 | 28 |
| p108 (chapter start) | 62 | 100 | 38 |
| p139 | 48 | 100 | 52 |
| p173 | 52 | 100 | 48 |

Claude identified the empty TOC on p3; Local rated it perfect. That delta is not sampling noise — it is the grader refusing to grade.

## The Key Open Question — (a) vs (b)

The remediation path forks entirely on this distinction:

**(a) Grading bias** — Qwen *detects* issues and populates the `issues` array, but assigns `severity: "minor"` and still emits `score: 100`. This is classic instruction-tuned teacher bias: the model is RLHF'd to be agreeable and defaults high unless forced otherwise.
- **Remediable via prompts alone.** Hardened instructions, few-shot anchoring, score-band enums, and guided_json all work here.

**(b) Detection failure** — Qwen's visual attention does not register the anomaly at all. `issues` array is empty on pages Claude flagged hard.
- **Requires model swap or prompt restructure.** Qwen2.5-VL-32B-Instruct (pre-listed in parent plan as fallback) has denser visual attention. Alternative: forced-enumeration prompting ("list every visual element present, then evaluate").

**This question must be answered before designing remediation.** Running any prompt experiment without knowing which failure mode we are in will waste cycles.

## Investigation Sequence

### Step 1 — Classify the failure mode across 6-book corpus
**Gate:** SCRUM-275 Phase 2 closure (remaining 5 books run against local provider).

For every page scoring 100, record:
- `len(issues)` — populated or empty?
- If populated: what severities? (`minor` / `major` / `critical` distribution)
- If empty: does Claude's corresponding report flag real issues on that same page?

**Decision:** If ≥70% of all-100 pages have populated `issues` arrays → we are in mode (a). If ≥70% have empty arrays despite Claude finding issues → we are in mode (b). Mixed → treat as (b) for safety (prompting won't uniformly fix detection gaps).

### Step 2a — If mode (a): prompt-engineering experiments
Run in order, cheapest first, with same Python-in-easy-steps 8-page fixture for fast iteration:

1. **Strict-grader instruction append** — add to user-facing trailing text: *"Grade strictly. If ANY issue is present, deduct points. A score of 100 requires zero visible issues."*
2. **Persona framing** — system prompt prefix: *"You are a strict editor reviewing this book for quality control. Your job is to find every flaw."*
3. **Score-band enum via guided_json** — replace `score: integer [0-100]` with `score_band: "FAIL" | "POOR" | "ACCEPTABLE" | "GOOD" | "EXCELLENT"` and explicit criteria per band. Post-process to numeric.
4. **Few-shot anchoring** — include 1-2 Claude-scored example pages in the system message (score + short explanation). Anchors the distribution.
5. **Chain-of-criticism structure** — require `issues_detected` array output *before* the `score` field in the schema. Forces enumeration pass before grading pass.

**Gate:** mean absolute score delta vs Claude across 6-book corpus drops below 15 points. If any single experiment gets us there, stop and commit that configuration.

### Step 2b — If mode (b): architectural experiments
1. **Two-pass structure** — pass 1 emits `issues[]` only (no score), pass 2 accepts the issues list and emits score. Separates detection from grading; may work because scoring-with-input is easier than scoring-with-perception.
2. **Forced enumeration prompt** — *"List every visual element visible on this page: headers, body text blocks, images, tables, page numbers. Then evaluate."* Engages visual attention explicitly before evaluation.
3. **Model swap — Qwen2.5-VL-32B-Instruct** — pre-listed in parent plan as the designated fallback. Denser visual attention than MoE-A3B's 3B active params.
4. **Hybrid grader** — local model does detection (where it's adequate), Claude does scoring (where calibration is critical). Partial cost reduction, keeps trust. Only viable if detection is partially working (mixed mode).

**Gate:** same as 2a — mean absolute score delta below 15 points across corpus.

### Step 3 — Multi-book robustness
Whichever remediation lands in step 2, validate against all 6 corpus books (not just Python in easy steps) before declaring done. Score distribution should be non-degenerate: at least one book should have at least one FAIL (< 60) page if Claude flagged one.

## Acceptance Criteria

- [ ] Failure-mode classification (a/b/mixed) documented with evidence from 6-book corpus
- [ ] At least one remediation experiment produces mean absolute score Δ < 15 vs Claude across corpus
- [ ] Non-degenerate score distribution (no all-pages-same-score behavior)
- [ ] Final configuration committed to `local_provider.py` with load-bearing comment matching the `enable_thinking=False` style
- [ ] Test coverage for the new configuration (follow the `test_no_frequency_penalty` pattern)
- [ ] Parent plan `docs/plans/2026-04-13-001-local-llm-visual-qa.md` updated with amendment noting Phase 5 resolution path

## Out of Scope

- Full-book mode implementation (`--all-pages`, `--batch-size`, tempdir streaming) — that is SCRUM-275 Phase 3, a separate ticket
- Fine-tuning / LoRA adaptation — deferred until prompt-engineering + model-swap options are exhausted. Requires 50-200 labeled examples minimum; revisit only if step 2 fails
- Replacing the sb-chat shared stack with a dedicated vision model container — infrastructure decision, not a calibration investigation
- Re-architecting the provider abstraction — SCRUM-274's interface is adequate

## Methodology Note — Debugging LLM Output Anomalies (template for reuse)

The v1→v2→v3 sequence is a reusable diagnostic template for future LLM output debugging:

1. **Form a hypothesis, identify its unique prediction.** v1→v2 hypothesis was "max_tokens too low." Unique prediction: raising the ceiling increases output tokens.
2. **Watch for counterintuitive metric movement.** Output tokens *decreasing* (541 → 374) when the ceiling was raised falsified the hypothesis — self-limiting behavior rather than budget exhaustion.
3. **The tell often isn't where you're looking.** Page 35's duplicated description→suggestion text was the real evidence of frequency_penalty damage, not the score or token counts we were initially tracking.
4. **One variable per iteration.** v1→v2 changed only max_tokens. v2→v3 changed only frequency_penalty. If either had changed multiple settings at once, the diagnosis would be ambiguous.

This methodology should be referenced in future LLM behavior investigations (CareerPilot scoring, SecondBrain proposal quality, any downstream Qwen work on the shared stack).

## References

- Parent plan: `docs/plans/2026-04-13-001-local-llm-visual-qa.md`
- Parent ticket: SCRUM-275 (Phase 2 local provider implementation)
- Pre-listed fallback: parent plan's Phase 5 section naming Qwen2.5-VL-32B-Instruct
- Smoke test data: `data/scrum275_local_smoke/` (gitignored; regenerate via `tools/visual_qa.py --provider local`)
- Cross-project memory: `feedback_qwen_frequency_penalty_json.md` — non-obvious Qwen+JSON gotcha discovered during this work
