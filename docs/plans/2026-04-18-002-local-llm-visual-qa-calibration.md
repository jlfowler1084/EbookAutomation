---
date: 2026-04-18
plan_id: 2026-04-18-002
title: Local VQA — hallucination and calibration remediation investigation
status: ready
parent_plan: docs/plans/2026-04-13-001-local-llm-visual-qa.md
parent_ticket: SCRUM-275
ticket: SCRUM-279
ce_phase_reference: Phase 5 (baseline comparison + calibration)
owner: Joe
estimated_sessions: 2 (1 Opus for experiment design, 1 Sonnet for execution)
---

# Ticket Draft — Local VQA Hallucination & Calibration Investigation

## Summary

SCRUM-275 Phase 2 6-book live smoke surfaced **two independent failure modes** in the local Qwen3.5-35B-A3B provider. Both are scoped out of Phase 2 (plumbing) and into this follow-up investigation.

1. **Page-count hallucination (structural correctness).** Return of the Gods produced 221 sequential page entries for 8 input images, 10,661 output tokens. Other 5 books returned 8/8 cleanly. Structural fix: vLLM `guided_json` with `minItems`/`maxItems` constraints on the `pages` array.
2. **Grader leniency (score calibration).** All 6 books scored higher than Claude by Δ 11-32 (consistent directional bias). Prompt-engineering + anchored few-shot likely sufficient; model swap reserved as fallback.

An interim defensive guard (`PageCountMismatchError` raised on count mismatch in `local_provider.call()`) shipped with SCRUM-275 merge. This ticket drives the structural fix and calibration remediation.

## 6-Book Phase 2 Gate Results

| Book | Pages returned | Local score | Claude score | Δ | Structural OK |
|---|---|---|---|---|---|
| Oil Kings | 8 | 94 | 75 | 19 | ✅ |
| Mexico Illicit | 8 | 90 | 72 | 18 | ✅ |
| Return of the Gods | **221** | 95 | 81 | 14 | ❌ (hallucinated) |
| Atomic Habits | 8 | 95 | 84 | 11 | ✅ |
| Decline of the West | 8 | 94 | 79 | 15 | ✅ |
| Python in easy steps | 8 | 91 | 59 | **32** | ✅ |

Plan's literal gate (`valid report JSON matching schema, no exceptions`) is met on all 6 (the 221-entry output is still schema-valid since the schema does not constrain `pages` length). Strict reading (sensible output) is 5 of 6.

## Side finding — grader leniency is softening

Between the v3 sample (all 100s, 400 output tokens) and this 6-book run (91-95 spread, 400-933 output tokens), removing `frequency_penalty` unlocked score variance. Insufficient to match Claude, but the model is no longer pinning everything at 100. Phase 5 experiments should start from this post-fix baseline, not v3's.

---

## Priority 1 — Page-Count Hallucination (structural correctness)

### Nature of the failure

Return of the Gods input: 8 images labelled pages [3, 17, 34, 55, 89, 110, 142, 171] (or similar — whatever the sampler picked). Model output: 221 entries with `page_number` 1 through 221, sequentially. No duplicates, plausible-looking rubric fields per entry. Output tokens = 10,661 (typical range for non-hallucinated 8-page runs: 400-900). The model invented ~213 page evaluations that correspond to no input image.

### Why this is more dangerous than grader leniency

Leniency is a magnitude bias — scores are wrong by a knowable amount. Hallucination corrupts the *referent*: downstream consumers trust `page_number` as a pointer back to the source ("fix the issue on page 183"). A consumer acting on a hallucinated entry would investigate a page the model never saw. Schema-valid but semantically fabricated output is the worst failure mode.

### Interim guard (shipped with SCRUM-275)

- `PageCountMismatchError` raised in `LocalVisionProvider.call()` when `len(parsed["pages"]) != len(input_images)`
- Handles both hallucination (overcount) and silent dropout (undercount)
- Skips on malformed JSON to preserve `parse_qa_response` retry path
- 4 test cases: hallucination, undercount, matching-count passthrough, malformed-JSON passthrough

The guard is defensive — it detects and surfaces the failure but does not prevent it. Phase 5 owns the structural fix.

### Structural fix — `guided_json` at the decoder layer

vLLM supports OpenAI's `response_format={"type": "json_schema", "json_schema": {...}}` via the outlines-backed guided decoding path. A schema with `minItems: N` / `maxItems: N` on the `pages` array **physically prevents** the decoder from emitting a 9th entry — the token masking at generation time makes it structurally impossible.

Proposed schema shape:

```json
{
  "type": "object",
  "required": ["pages"],
  "properties": {
    "pages": {
      "type": "array",
      "minItems": 8,
      "maxItems": 8,
      "items": {
        "type": "object",
        "required": ["page_number", "page_type", "score", "pass", "issues"],
        "properties": {
          "page_number": {"type": "integer"},
          "page_type": {"type": "string", "enum": ["cover", "front_matter", "toc", "body", "chapter_start", "appendix", "index"]},
          "score": {"type": "integer", "minimum": 0, "maximum": 100},
          "pass": {"type": "boolean"},
          "issues": {"type": "array", "items": { ... }}
        }
      }
    }
  }
}
```

Open questions:
- `minItems`/`maxItems` must match the dynamic batch size. Requires threading batch size through to the schema builder in `build_request()`.
- Can we also constrain `page_number` to be one of the input image labels? That would be a stronger check (prevents the "first 8 of 221" pseudo-validity case) but requires dynamic schema generation per-request. Worth trying.
- `guided_json` imposes some latency overhead and can occasionally hurt output coherence. Measure against post-leniency-fix baseline, not pre-fix.

### Priority 1 acceptance criteria

- [ ] `guided_json` JSON schema integrated into `build_request()`
- [ ] Schema enforces `minItems == maxItems == len(page_images)` dynamically
- [ ] `page_number` schema constraint experimented with (decision documented either way)
- [ ] 6-book corpus re-run: 0 hallucination events, 6 of 6 structural OK
- [ ] Performance delta vs pre-`guided_json` baseline measured (latency + token count)
- [ ] `PageCountMismatchError` guard stays in place as belt-and-suspenders defense

---

## Priority 2 — Grader Leniency Calibration

### The key open question — (a) grading bias vs (b) detection failure

**(a) Grading bias** — Qwen *detects* issues and populates the `issues` array, but assigns low severity and emits high scores anyway. Classic instruction-tuned teacher bias: RLHF'd to be agreeable, defaults high unless forced otherwise.
- **Remediable via prompts alone.** Hardened instructions, few-shot anchoring, score-band enums.

**(b) Detection failure** — Qwen's visual attention does not register the anomaly. `issues` array is empty on pages Claude flagged hard.
- **Requires prompt restructure or model swap.** Qwen2.5-VL-32B-Instruct (pre-listed in parent plan as fallback) has denser visual attention.

The 6-book data from SCRUM-275's smoke must be inspected to classify which mode we are in before designing remediation. Eyeball the first 10-20 pages with score=100 — don't let a threshold decide.

### Step 1 — Classify the failure mode (6-book corpus)

For every page scoring ≥95 in the local run, record:
- `len(issues)` — populated or empty?
- If populated: severity distribution (`minor` / `major` / `critical`)
- If empty: does Claude's corresponding report flag real issues on that same page?

Quantitative heuristic + qualitative judgment: if ≥70% of high-scoring pages have populated `issues` arrays AND the issues look reasonable → mode (a). If ≥70% have empty arrays despite Claude finding issues → mode (b). Mixed → treat as (b) for safety.

### Step 2a — If mode (a): prompt-engineering experiments

Run in order, cheapest first, same Python-in-easy-steps 8-page fixture for fast iteration:

1. **Strict-grader instruction append** — "Grade strictly. If ANY issue is present, deduct points. A score of 100 requires zero visible issues."
2. **Persona framing** — system prompt prefix: "You are a strict editor reviewing this book for quality control. Your job is to find every flaw."
3. **Score-band enum via guided_json** — replace `score: integer [0-100]` with `score_band: "FAIL" | "POOR" | "ACCEPTABLE" | "GOOD" | "EXCELLENT"` and explicit criteria per band. Post-process to numeric if needed.
4. **Few-shot anchoring** — include 1-2 Claude-scored example pages in the system message. Anchors the distribution.
5. **Chain-of-criticism structure** — require `issues_detected` array output *before* the `score` field. Forces enumeration pass before grading pass.

Gate: mean absolute score delta vs Claude across 6-book corpus drops below 15 points. Stop at the first experiment that hits the gate — no need to stack.

### Step 2b — If mode (b): architectural experiments

1. **Two-pass structure** — pass 1 emits `issues[]` only (no score), pass 2 accepts the issues list and emits score. Separates detection from grading.
2. **Forced enumeration prompt** — "List every visual element visible on this page: headers, body text blocks, images, tables, page numbers. Then evaluate." Engages visual attention explicitly before evaluation.
3. **Model swap — Qwen2.5-VL-32B-Instruct** — pre-listed in parent plan. Denser visual attention than MoE-A3B's 3B active params.
4. **Hybrid grader** — local model does detection, Claude does scoring. Only viable in mixed-mode (detection partially works). Partial cost reduction, keeps trust.

Gate: same as 2a — mean absolute score delta below 15 points.

### Step 3 — Multi-book robustness

Whichever remediation lands in Step 2, validate against all 6 corpus books. Score distribution should be non-degenerate: at least one FAIL (< 60) page across the corpus if Claude flagged one.

### Priority 2 acceptance criteria

- [ ] Failure-mode classification (a/b/mixed) documented with evidence table
- [ ] At least one remediation experiment produces mean absolute Δ < 15 vs Claude across corpus
- [ ] Non-degenerate score distribution (no all-pages-same-score behavior)
- [ ] Final configuration committed to `local_provider.py` with load-bearing comment
- [ ] Test coverage matching the `test_no_frequency_penalty` style

---

## Out of Scope

- Full-book mode (`--all-pages`, `--batch-size`, tempdir streaming) — SCRUM-275 Phase 3, a separate ticket
- Fine-tuning / LoRA adaptation — deferred until prompt-engineering + model-swap options are exhausted
- Replacing sb-chat shared stack with a dedicated vision container — infrastructure, not calibration
- Re-architecting the provider abstraction — SCRUM-274's interface is adequate
- Automatic retry on `PageCountMismatchError` — may be useful later, not structurally required for this ticket

---

## Methodology Note — Debugging LLM Output Anomalies (reusable template)

The SCRUM-275 v1→v2→v3 sequence is a reusable diagnostic template:

1. **Form a hypothesis, identify its unique prediction.** v1→v2 hypothesis: "max_tokens too low." Unique prediction: raising the ceiling increases output tokens.
2. **Watch for counterintuitive metric movement.** Output tokens *decreased* (541 → 374) when the ceiling was raised, falsifying the budget hypothesis and pointing at self-limiting behavior.
3. **The tell often isn't where you're looking.** Page 35's duplicated `description` → `suggestion` text was the evidence of `frequency_penalty` damage, not the score or token counts we were initially tracking.
4. **One variable per iteration.** v1→v2 changed only `max_tokens`. v2→v3 changed only `frequency_penalty`. Multiple-variable changes make the diagnosis ambiguous.
5. **Distinguish magnitude bias from structural failure.** Leniency and hallucination look similar on aggregate metrics (both inflate scores) but require different fixes. Always check per-page outputs, not just summary stats.

Apply this template to future CareerPilot scoring work, SecondBrain proposal quality investigations, and any downstream Qwen work on the shared vLLM stack.

---

## References

- Parent plan: `docs/plans/2026-04-13-001-local-llm-visual-qa.md`
- Parent ticket: SCRUM-275 (Phase 2 local provider implementation)
- Pre-listed fallback model: parent plan Phase 5 — Qwen2.5-VL-32B-Instruct
- Interim hallucination guard: `tools/llm_providers/local_provider.py` (`PageCountMismatchError` class)
- Smoke test data: `data/scrum275_local_smoke/` (gitignored; regenerate via `tools/visual_qa.py --provider local`)
- vLLM guided_json docs: https://docs.vllm.ai/en/latest/features/structured_outputs.html
