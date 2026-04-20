---
title: Local VLM calibration patterns — lessons from SCRUM-280 P2
type: solution
status: compound
date: 2026-04-19
origin_ticket: SCRUM-280
origin_plan: docs/plans/2026-04-18-004-feat-scrum-280-p2-calibration-grounding-plan.md
related_tickets: [SCRUM-275, SCRUM-279, SCRUM-281, SCRUM-282, SCRUM-283]
tags: [vlm, qwen, calibration, visual-qa, shared-stack, moe-architecture]
---

# Local VLM calibration patterns — lessons from SCRUM-280 P2

Compound-knowledge write-up of five reusable lessons from the SCRUM-280 grader-leniency-calibration + page_number-grounding work. Written after ticket partial-close, PR #2 open, follow-up tickets SCRUM-281/282/283 filed. Intended as reference for future VLM calibration work anywhere on the EbookAutomation / SecondBrain / CareerPilot shared sb-chat stack.

## Context

SCRUM-275 Phase 2 shipped a local VQA provider (Qwen3.5-35B-A3B-fp8 via sb-chat) as a Claude substitute to eliminate per-call Claude cost on ebook conversion quality checks. Phase 2's smoke surfaced two failure modes: page-count hallucination (221 entries for 8 images, fixed in SCRUM-279 P1 via `guided_json`) and grader leniency (scores Δ 11-32 higher than Claude baseline). SCRUM-280 P2 drove the calibration + `page_number` marker-grounding work that this document compounds from.

Final outcome: R4 (marker grounding) solved cleanly via prompt-only edit; R2 (grader leniency) cleared on 3 of 5 corpus books but failed on academic books (Oil Kings, Mexico Illicit) at a capability ceiling. Two-pass calibrated architecture delivered 48% corpus mean |Δ| reduction (33.0 → 17.0). Partial close; residual scoped to SCRUM-281 (routing remediation) and SCRUM-283 (dedicated-VLM evaluation).

---

## Lesson 1 — Prompt-layer arithmetic succeeds where prompt-layer posture backfires

**Pattern:** Separating *arithmetic calibration* (how many points per issue) from *behavioral posture* (be strict) in prompt engineering unlocks calibration that raw directive prompting cannot.

**Evidence from SCRUM-280 Unit 4:**
- **Variant 2a-i (strict-grader posture in system message):** `"Grade strictly. If ANY issue is present, deduct points. A score of 100 requires zero visible issues."` → mean |Δ| went from 33.0 to 40.5 (worse). Distribution collapsed to all-8-pages-100 on the fixture. Reward-hacking: RLHF'd model interpreted "strict grading" as "avoid being wrong by scoring safely high" — the `100` exit was open because instruction-tuned models default agreeable.
- **Variant 4b-ii-calibrated (arithmetic deduction table in pass-2 user message, after pass-1 committed an issue list):** `"each critical 45-60 points; each major 20-30; each moderate 12-18; each minor 4-6. Multiple issues compound — a page with two moderate issues and one minor should score in the 60-72 range, not 80+."` → mean |Δ| 12.5 on Python fixture, 11.2 on RotG. Reward-hacking exit structurally closed: `100` requires zero issues, but pass-1's issue list is in the prompt.

**Why it works:** When arithmetic is applied to an already-committed concrete input (the pass-1 issue list), the model's attention has no degrees of freedom for reward-hacking. The instruction is "apply these specific deductions to these specific issues," not "behave as a strict grader." Arithmetic is a constraint on output; posture is a constraint on behavior. Models can hack behavior; they can't hack arithmetic applied to facts already in the context.

**How to apply (reusable):**
- When calibrating a grading/evaluation LLM on any project (VQA, code review, writing feedback, etc.), prefer arithmetic rubrics applied to a concrete input list over posture directives in the system message
- Two-pass separation (detection then scoring) is one way to produce the concrete input list; other patterns include multi-agent detection → single-agent scoring, or retrieval-then-rate
- If you must use posture, make it about the *arithmetic* itself: "apply deductions compoundingly, not linearly" is posture-about-math, not posture-about-role

**Anti-pattern to avoid:** "You are a strict grader" or "You must find every flaw" or equivalent posture directives in system messages for a zero-shot combined task. These invite reward-hacking more than they shape output distribution.

---

## Lesson 2 — Two-pass detection/scoring separation as VLM calibration unlock

**Pattern:** Combined detection-and-scoring tasks starve calibration signals when the model's visual attention budget is consumed by detection. Separating the tasks frees pass-2 attention for calibration.

**Evidence from SCRUM-280 Unit 4:**
- **Variants 2a-i (strict-grader), 2a-4 (few-shot anchor), 4b-i (forced-enumeration):** all prompt-only edits on the combined task. Mean |Δ| movement: −0.1, 0.0, +7.5. Three orthogonal mechanisms (directive framing, distribution demonstration, enumeration prompting) failed to move calibration in the combined task.
- **Variant 4b-ii-v1 (two-pass, uncalibrated):** mean |Δ| 33.0 → 24.1. Architectural change alone: −8.9.
- **Variant 4b-ii-calibrated (two-pass + arithmetic deduction table):** mean |Δ| 33.0 → 12.5. Same arithmetic deduction table applied to the combined task would have been 2a-i-equivalent; applied to pass-2 of a separated task, it delivers.

**Why it works:** Vision attention is limited per forward pass. The combined task forces the model to simultaneously (a) attend to the image for defect detection AND (b) weight detected defects for scoring. Both are load-bearing for output quality, and the model allocates attention between them implicitly. When you separate:
- Pass 1 is pure detection — all attention goes to the image, the schema forces exactly one shape of output (issues only, no score)
- Pass 2 is pure arithmetic on the pass-1 output — text-only (no image), minimal attention load, calibration signals land on a well-defined input

The calibration signal's effective delivery is what changes, not the calibration content itself.

**How to apply (reusable):**
- Any LLM task that combines perception + judgment in one call is a candidate for this pattern
- Architecture cost: 2-3× inference volume per logical batch. Measured cost on SCRUM-280: 9s vs 3s single-pass on 8-page VQA batches (3× overhead — pass-1 issue-enumeration is token-verbose, exceeded the 2× planning estimate)
- The pass-1 schema should be minimal (only the detection output field) to prevent the model from "leaking" scoring work into pass 1
- The pass-2 schema should strip the input pass-1 referenced (e.g., no images in pass 2) to prevent implicit re-detection

**Shared-stack caveat:** on a shared vLLM backend (sb-chat serving multiple projects), the 2-3× amplification is a cross-project throughput concern. Surface as a `NEW DEPENDENCY` flag in session summary before landing.

---

## Lesson 3 — Mode classification (page count) ≠ mean-|Δ| dominance (page weighting)

**Pattern:** When a classifier uses a *count* property to drive a remediation whose acceptance is measured by a *weighted* property, the verdict and the gate can diverge. Mode (a) grading-bias pages and mode (b) detection-failure pages contribute EQUAL weight to mean absolute delta even if their counts differ.

**Evidence from SCRUM-280 Unit 1 + Unit 4:**
- Unit 1 classifier verdict on post-P1 corpus: **dominant-b** (3 of 5 classifiable books, 60% b-family).
- Unit 4 mode-(b) remediation (4b-i forced-enumeration prompt): null result, |Δ| moved 0.1 points.
- Hypothesis formed mid-iteration: the |Δ| signal has a significant mode-(a) component (page-wise grading bias), even if page-count-wise the corpus leans mode-b. Mode-a pages (score 95 with populated issues) contribute the same weighted delta as mode-b pages (score 95 with empty issues).

**Why it matters:** A dominant-b classifier verdict does NOT mean "mode-a remediations are useless." It means "if you had to pick ONE remediation type, pick mode-b." But if the delta aggregate spans both modes, addressing only mode-b won't close the gate — the mode-a contribution remains untouched.

**How to apply (reusable):**
- When building a classification-to-remediation mapping, check whether the classifier's aggregation property matches the gate's acceptance property. Page counts vs page-weighted deltas = mismatch.
- If the signals diverge, design remediations that stack across modes (arithmetic-in-pass-2 from Lesson 1 is mode-agnostic — it helps whether the issue is grading bias OR detection failure on a detected issue).
- Mode classification is a sequencing heuristic ("try this remediation first"), not a scope predictor ("only this remediation will help").

---

## Lesson 4 — MoE active-parameter ceiling for structural visual judgment

**Pattern:** Mixture-of-Experts models (like Qwen3.5-35B-A3B) route to a small subset of parameters per forward pass. The image encoder is a subset of the active path, so the effective visual-processing circuit is a fraction of the total model. For structural/semantic visual judgments requiring schema knowledge, this is a hard ceiling that prompting cannot bridge.

**Evidence from SCRUM-280 Investigation (C):**
- 11 zero-local-issues pages examined on Oil Kings + Mexico Illicit: Qwen returned `issues: []` on pages where Claude detected moderate-to-major defects.
- Failure-mode taxonomy (bounded by defect category, diffuse by page type):
  - `paragraph_flow`: 10 of 11 pages — merged copyright/front-matter blocks, epigraph structure, endnote paragraph splits
  - `heading_formatting`: 6 of 11 pages — chapter ordinal + title at same visual weight
  - `text_integrity`: 6 of 11 pages — non-URL structural variants (e.g., raw HTML tag leakage `<sup>` into body)
- One defect Qwen DID catch: Mexico p234 URL broken-space (`htt p://...`) — mechanical character-level pattern matching.
- All misses required **schema knowledge of what correct ebook formatting looks like**, not pattern-matching character sequences.

**Why the ceiling is bounded-category + diffuse-page-type:**
- Bounded by category because the model's blind spots cluster on specific judgment types (layout/structure vs character patterns)
- Diffuse by page type because cover, front-matter, body, chapter_start, back_matter ALL have the same blind spots
- Implication for routing: you can't route around this by page type (no page-type cluster); you must route at the response level (pass-1 `issues: []` is the observable fingerprint of a detection miss)

**Why prompting can't bridge it:** Structural judgment requires the model to *know* what correct ebook typography looks like — what paragraph breaks should align with semantic boundaries, how epigraph attribution should be separated from body text, what a well-formed chapter heading hierarchy looks like. Prompting can redirect attention; it cannot transfer missing schema knowledge.

**How to apply (reusable):**
- When evaluating an MoE model for a visual task, weight its effective vision circuit (active params × image-encoder subset), not its total parameter count. Qwen3.5-A3B's ~3B active visual circuit is ~10× smaller than a dense 32B VLM's visual circuit
- If a failure mode is bounded-category + diffuse-page-type, route at response-level (use the response itself as a confidence signal), not request-level (page type is insufficient)
- The MoE ceiling for structural visual judgment is the best justification for (a) dedicated-VLM swap via local hosting pending hardware, OR (b) cloud VLM pay-per-token (SCRUM-283 evaluates this — un-defers the parent plan's deferred fallback by changing the compute assumption from local-host to cloud-API)

---

## Lesson 5 — VQA baselines are tied to capture-time source format

**Pattern:** Deterministic sampling (no randomness) does not guarantee stable page selection across source-format changes. Claude VQA baselines captured from one source format cannot be directly compared to live-pipeline runs on a different source format.

**Evidence from SCRUM-280 Investigation (A):**
- `tools/visual_qa.py::select_sample_pages` is fully deterministic — no randomness anywhere.
- Atomic Habits Claude baseline captured from original PDF source (266 pages) sampled `[1, 2, 3, 73, 92, 145, 158, 232]`.
- Atomic Habits live smoke via KFX → Calibre PDF (272 pages) sampled `[1, 2, 3, 91, 94, 149, 152, 238]`.
- Zero interior-page overlap despite both runs using the same deterministic sampler.
- Cause: `total_pages` and bookmark-position inputs differ between source formats → deterministic formula produces different outputs on different inputs.

**Why it compounds:** Any long-term quality-tracking metric is tied to the source-format state at baseline-capture time. If a project re-captures its baselines without noticing the source-format issue, regression detection becomes unreliable — you're not comparing the same pages.

**How to apply (reusable):**
- Before capturing any VQA baseline for any book, route through the SAME source-format path the live pipeline consumes (KFX → Calibre-converted PDF, NOT the original PDF)
- Add a `source_format` field to baseline JSON output ("kfx" | "pdf") so drift is detectable programmatically (tracked in SCRUM-282)
- When comparing baseline vs live-smoke |Δ|, verify page-selection parity BEFORE interpreting the |Δ| as a quality gap — a sampling mismatch will look like a quality problem but is not one
- Cross-project applicability: any project that has a sampling + baseline + regression-check loop has this class of drift risk (CareerPilot coaching evaluations, SecondBrain autobook QA)

---

## Methodology notes

- **File names lie; content doesn't.** `data/scrum275_local_6book/` was named as if it were post-P1 6-book data but is actually pre-P1 Phase 2 smoke data (RotG has the 221-entry hallucination cascade baked in). Sonnet session caught this during Unit 1 execution by inspecting the content rather than trusting the path. Generalizes: for any data directory referenced in a plan, verify content structure before trusting the path naming.
- **Cost-evidence progression is load-bearing for expensive architectural gates.** The SCRUM-280 plan's Unit 4 stopping rule (max 5 variants per ladder) + two-pass explicit approval gate forced the iteration to produce orthogonal evidence (null + active regression + null) before escalating. Approving two-pass after one failed variant would have short-circuited the evidence chain; the resulting "why did you choose two-pass" post-hoc would be thin.
- **Partial close with sharp residual tickets > force-pass with brittle fix.** SCRUM-280 closed with R2 unmet but R1/R3/R4/R5/R6 met, PR landed, three follow-up tickets (SCRUM-281/282/283) filed with specific next-action scope inherited from the diagnostic. Stronger outcome than a force-fix variant that barely cleared |Δ|<15 on a brittle prompt hack.

## References

- Plan: [docs/plans/2026-04-18-004-feat-scrum-280-p2-calibration-grounding-plan.md](../plans/2026-04-18-004-feat-scrum-280-p2-calibration-grounding-plan.md)
- Predecessor plan (P1 structural fix): [docs/plans/2026-04-18-003-feat-scrum-279-p1-guided-json-schema-plan.md](../plans/2026-04-18-003-feat-scrum-279-p1-guided-json-schema-plan.md)
- Origin plan (parent calibration): [docs/plans/2026-04-18-002-local-llm-visual-qa-calibration.md](../plans/2026-04-18-002-local-llm-visual-qa-calibration.md)
- PR: https://github.com/jlfowler1084/EbookAutomation/pull/2
- Primary code target: [tools/llm_providers/local_provider.py](../../tools/llm_providers/local_provider.py)
- Rubric contract: [tools/visual_qa_rubric.md](../../tools/visual_qa_rubric.md)
- Follow-up tickets: SCRUM-281 (detection-miss remediation), SCRUM-282 (baseline source-format standardization), SCRUM-283 (cloud VLM evaluation)
