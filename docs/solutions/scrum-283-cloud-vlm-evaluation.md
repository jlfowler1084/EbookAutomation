---
title: Cloud VLM evaluation — lessons and routing decision from SCRUM-283
type: solution
status: compound
date: 2026-04-19
origin_ticket: SCRUM-283
origin_plan: docs/plans/2026-04-19-feat-scrum-283-cloud-vlm-eval-plan.md
predecessor: docs/solutions/scrum-280-local-vqa-calibration-patterns.md
related_tickets: [SCRUM-275, SCRUM-279, SCRUM-280, SCRUM-281, SCRUM-282]
tags: [vlm, qwen, openrouter, visual-qa, routing, cloud-inference, hybrid]
---

# Cloud VLM evaluation — lessons and routing decision from SCRUM-283

Compound-knowledge writeup of three reusable lessons plus the routing recommendation from the SCRUM-283 cloud-VLM R2-gate evaluation. Written after the evaluation partial-closed: cloud Qwen3-VL-30B-A3B-Instruct clears the SCRUM-280 academic-book ceiling decisively, dense Qwen-VL-Max did *worse* than A3B broadly, and a consistent "text is clean — no action needed" fallback fingerprint makes response-level routing viable. Partial close favored over force-pass per the precedent in SCRUM-280.

## Context

SCRUM-280 P2 partial-closed with local Qwen3.5-35B-A3B-fp8 two-pass-calibrated landing corpus mean |Δ| = 17.0 against the Claude baseline — clean on 3 of 5 books but ~22-28 |Δ| on academic content (Oil Kings, Mexico Illicit), attributed to MoE active-parameter ceiling for structural visual judgment (SCRUM-280 Lesson 4). SCRUM-283 was filed to evaluate whether a cloud-hosted VLM (Qwen2.5-VL-32B or equivalent) would bypass the ceiling, un-deferring the parent-plan's model-swap fallback by changing the compute constraint from local-VRAM to pay-per-token.

The evaluation ran three probes across the 5-book overlap of the SCRUM-280 test corpus (Atomic Habits excluded — filename-normalization drift, SCRUM-282 territory):

- **Unit 3** — Cloud Qwen3-VL-30B-A3B-Instruct on OpenRouter, single-pass
- **Unit 5b** — Cloud Qwen-VL-Max on OpenRouter (dense flagship, different checkpoint family)
- **Unit 5a (skipped)** — Fireworks Qwen3-VL-32B-Instruct (deferred: Fireworks signup not set up; OpenRouter Max serves the dense-vision hypothesis)

R2 gate (same as SCRUM-280): equal-weight corpus mean |Δ| < 15 AND no per-book |Δ| > 20. **Both probes fail the formal gate.** But the *shape* of the failure is what the routing decision hinges on.

---

## Lesson 1 — Newer reasoning weights at the same MoE active-param class DO clear bounded-category structural-judgment ceilings

**Pattern:** When a model fails a visual-judgment task in a bounded category (Lesson 4 from SCRUM-280), a newer-generation model at the same architecture class with stronger reasoning weights is a targeted fix that often works, without needing to jump to a more expensive model class.

**Evidence from SCRUM-283 Unit 3 vs SCRUM-280 baseline:**

| Book | Local Qwen3.5-A3B 2-pass |Δ| (SCRUM-280) | Cloud Qwen3-VL-A3B 1-pass |Δ| (SCRUM-283) | Detection misses: local → cloud |
|---|---|---|---|
| The Oil Kings | 22.6 (R2(b) FAIL) | **14.6** (R2(b) PASS) | 7 → **1** |
| Mexico Illicit | 28.6 (R2(b) FAIL) | **20.0** (R2(b) border) | 6 → **0** |
| Return of the Gods | 11.2 | 10.8 | 7 → **0** |
| Decline of the West | 7.6 | 10.4 | 1 → 0 |
| Python in easy steps | 15.0 | 36.6 (see Lesson 3) | 2 → 2 |

The three SCRUM-280 "ceiling" books (Oil Kings, Mexico, RotG) collectively went from 39 detection misses to 1 — a 97% reduction. This is a much larger gain than would be expected from prompt tuning or calibration within the local-A3B class. Something about Qwen3-VL's vision+reasoning training actually knows more about correct ebook formatting than Qwen3.5-A3B does, and the active-parameter budget is spent on that knowledge rather than on generic pattern-matching.

**Why it works:** MMMU-class benchmarks evaluate structured visual judgment over domain knowledge. DocVQA-class benchmarks evaluate character-pattern matching in document images. The SCRUM-280 ceiling was MMMU-shaped (all misses required schema knowledge of correct typography), and Qwen3-VL's training evidently emphasized MMMU-class capabilities within its active-parameter budget. DocVQA performance (which Qwen3.5-A3B also has) is insufficient for structural-quality judgment.

**How to apply (reusable):**
- When a model's bounded-category ceiling is MMMU-shaped (schema knowledge over visual patterns), probe a newer generation at the same active-parameter class *before* jumping to bigger models. A ~2-5% cost premium for a generation increment may beat a 10-20× cost premium for a flagship.
- The fingerprint of "MMMU-shaped" failure: detection misses cluster by category (paragraph_flow, heading_formatting, text_integrity) but diffuse by page type (cover, body, chapter_start all affected). If the cluster is by page type, the failure is likely DocVQA-shaped and a different fix applies.
- For the EbookAutomation VQA use case specifically: Qwen3-VL-30B-A3B on OpenRouter is measurably better than Qwen3.5-35B-A3B locally, at $0.0017/book vs $0/book — a trade most projects should accept for the quality uplift.

**Anti-pattern to avoid:** Assuming ceiling = architecture class = need for bigger model. SCRUM-275's original fallback plan listed Qwen2.5-VL-32B (a dense model) as the primary escalation. That path was deferred due to VRAM, but this evaluation shows a cheaper alternative was always available if the hypothesis had been framed as "need better reasoning, same vision circuit" rather than "need more vision compute."

---

## Lesson 2 — Dense vs MoE vision circuit is NOT the discriminator for detection thoroughness

**Pattern:** The intuition that "dense vision circuit (~10× larger than MoE active params) unlocks structural judgment" does not survive empirical probing. Training-time RLHF behavior dominates architecture class.

**Evidence from SCRUM-283 Unit 5b (Qwen-VL-Max dense flagship on OpenRouter):**

| Metric | Cloud A3B (Unit 3) | Cloud Max (Unit 5b) | Max vs A3B |
|---|---|---|---|
| Corpus mean |Δ| | 18.48 | **20.62** | Max WORSE |
| Max per-book mean |Δ| | 36.62 (Python) | 34.25 (Python) | ~tie |
| Mean detection misses / book | ~0.6 (all books), 2 (Python) | **~7.8 (all books)** | Max MUCH worse |
| Per-book |Δ| on academic books | 10.8, 14.6, 20.0 | 12.6, 18.9, 22.6 | Max WORSE on all 3 |
| Cost / book | $0.0017 | $0.0064 | **Max 4× more** |
| Wall-clock per book | ~12 sec | ~30-40 sec | **Max ~3× slower** |

Max didn't just fail to resolve the Python ceiling — it *degraded* detection across every book. The "text is clean, no action needed" fallback pattern that A3B emits only on Python became Max's default response on *all* books. The `category_scores` object collapsed to `{}` — Max didn't even populate the rubric's category-score fields on its Python report.

**Why it didn't work:** Max is likely RLHF-trained for helpful, conversational, "benign" responses — optimized for "don't hallucinate defects that aren't there" in a general VLM chat setting. That's the opposite of what a QA evaluator needs ("find every defect, err on the side of flagging"). Architecture class (dense vs MoE) doesn't override training objectives. A3B, by contrast, appears to have retained the "report issues specifically" behavior needed for this task.

**How to apply (reusable):**
- **Do not assume** that bigger, denser, or more expensive VLMs will do better on detection-thoroughness tasks. Their RLHF may be tuned for the opposite of what you need.
- Always run a small empirical probe (~$0.04 for 6 books × 8 pages on a flagship) before committing to a more expensive tier. The expected-value of a probe that costs $0.04 and can invert a $X/month routing decision is extremely high.
- When choosing a cloud VLM for QA evaluation specifically, prioritize models that *emit structured issue lists with category labels* in their default response patterns, not models that ace general VLM benchmarks. Inspect a 2-page output sample before committing to full-corpus smoke.

**Anti-pattern to avoid:** Reading a model's published benchmarks (MMMU, DocVQA, MMBench) and treating higher scores as predictive of your task performance. Published benchmarks are optimized responses; what matters for detection work is *default* response behavior on out-of-distribution inputs, which benchmarks don't measure.

---

## Lesson 3 — Response-level fingerprint detection enables hybrid routing for VLM fallback

**Pattern:** When a VLM can't meaningfully evaluate a page, it emits a detectable *default-response fingerprint* — a short, generic, boilerplate-style `issues` entry that is text-matchable at the report level. This fingerprint is the routing signal for hybrid VLM-primary + Claude-fallback architectures.

**Evidence from SCRUM-283 Units 3 and 5b (Python in Easy Steps):**

A3B on Python, page 2 (`front_matter`):
```json
{"issues": [], "page_number": 2, "page_type": "front_matter", "pass": true, "score": 100}
```
A3B on Python, pages 35/68/108/139/173:
```json
{"issues": [{"category": "text_integrity", "description": "Text is clean and readable with no visible artifacts", "severity": "minor", "suggestion": "No action needed"}], ...}
```

Cloud Max on Python (all 8 pages):
```json
{"issues": [], "score": 95}
```

Both models emit characteristic fallback responses on pages they can't evaluate. Claude, on the same pages, emitted specific category-labeled findings (empty TOC, collapsed operator precedence table, inline bullet lists, merged code+prose). A response-level fingerprint detector — regex or model-output text similarity against a corpus of known fallback responses — can identify the fallback pattern at the *report* level without needing to re-evaluate the page.

**Why it works:** RLHF-trained models have default-response patterns that emerge when the model is outside its training distribution. Those patterns are text-stable (identical-or-near-identical strings repeat across pages and books) because the model's decoder collapses to a high-probability generic continuation. The stability is what makes them detectable. Random-looking misses would be hard to catch; consistent fallback text is easy to catch.

**How to apply (reusable):**
- For any VLM-primary + oracle-fallback routing architecture, build the fingerprint detector as a small function in the reporting layer: take `page.issues[0].description` and check text-similarity against a known-fallback corpus. Cosine similarity over sentence embeddings works; so does simple substring matching for the most common fallback strings ("text is clean", "no action needed", "no visible artifacts").
- Trigger Claude re-evaluation on *any* page where (a) `issues == []` AND (b) the page's position, heuristically, suggests issues might exist (e.g., TOC pages for complex books, or pages with low extraction confidence upstream). This is the SCRUM-281 Option D direction, generalized from local-A3B-specific to any-VLM-provider.
- Extend the fingerprint corpus over time. The corpus is a data artifact; when new fallback patterns emerge on new books or new models, add them to the corpus. Version it alongside the rubric.

**Anti-pattern to avoid:** Routing on page type alone. SCRUM-280 Lesson 4 already documented this: the bounded-category + diffuse-page-type failure mode means page-type-based routing catches some misses but not all. Response-level fingerprint detection is the general solution.

---

## Routing recommendation

### Decision: Cloud A3B primary with response-level fallback to Claude (hybrid)

**Quality:**
- Cloud A3B beats local A3B on 3 of 5 comparable books (the 3 that blocked SCRUM-280 from closing cleanly), materially better on detection-miss rate
- Cloud A3B ties or slightly loses on 1 simple-structure book (Decline +2.8)
- Cloud A3B fails hard on 1 technical-layout book (Python) — mitigated by fingerprint fallback to Claude
- Overall quality net: materially better than SCRUM-280 local on academic content, comparable on simple content, with fallback on technical content

**Cost (production assumption: 20 books/month, 8-page sample):**

| Strategy | Monthly cost | Notes |
|---|---|---|
| **Cloud A3B primary (no fallback)** | **~$0.034** | Fails Python-like books silently |
| **Cloud A3B + Claude fallback ~15% books** | **~$0.28** | Recommended — quality-safe |
| Claude-only | $1.60 | 5× more expensive than hybrid |
| Local A3B two-pass (SCRUM-280) | $0 | Fails academic books — quality floor |

Hybrid beats Claude-only by ~5× and is only ~$0.25/month more than cloud-primary — trivial. SCRUM-281 Option D is now *required*, not *optional*, but the Claude-fallback cost is lower than originally projected because cloud A3B has better baseline detection than local A3B (fewer pages trigger fallback).

**Implementation:**
- Set `visual_qa.provider = "cloud"` and `visual_qa.cloud_model = "qwen/qwen3-vl-30b-a3b-instruct"` as defaults in `config/settings.json`
- Ship SCRUM-281 Option D as a post-report fingerprint detector that re-invokes `ClaudeVisionProvider` on flagged pages (batch re-invocation, not per-page, to amortize HTTP cost)
- Add `OPENROUTER_API_KEY` to the standard env-var set in CLAUDE.md alongside `ANTHROPIC_API_KEY` and `GEMINI_API_KEY`

### Why not Max or thinking-variant

- **Max** is strictly dominated by A3B (worse quality, 4× cost, 3× slower) — no scenario favors it
- **Qwen3-VL-235B-A22B-thinking** is the ladder's next rung per the plan, but:
  - Max falsified the dense-vision hypothesis, which weakens the priors for the reasoning hypothesis (A3B already has reasoning; thinking variant just enables chain-of-thought emission, which may trip the `OutputTruncatedError` guard even with `enable_thinking=False` attempts)
  - Cost is 2.5× Max's ($0.10/corpus smoke)
  - Per the SCRUM-280 "close partial over force-pass" feedback: marginal escalation at escalating cost when the core picture is clear is the wrong pattern

If Python-class failures become more prevalent in production (i.e., more technical books), thinking-variant is a legitimate follow-up probe. Not blocking.

### Why not local-primary

- SCRUM-280 quality floor demonstrated: corpus mean |Δ| 17 with academic-book tails at 22-28. Cloud A3B lands corpus mean 14-15 with the academic tails collapsed to 10-20. This is measurably better.
- Local consumes sb-chat shared-stack VRAM (per memory `project_sb_chat_shared_stack.md`). Moving VQA to cloud *frees* VRAM for other projects (CareerPilot coaching, SecondBrain autobook) — a positive cross-project externality.
- Local is still useful as a "quality floor" (zero marginal cost, even if R2 doesn't clear). Configurable via `--provider local` for offline / air-gapped usage. Not removed, just deprioritized as default.

---

## Methodology notes

- **Early-probe cost amortization.** Unit 1 auth smoke caught the `enable_thinking=False` omission in CloudVLProvider for $0.009 wasted. Fix was a 3-line commit. Had we gone straight to the 6-book corpus smoke without the 2-page auth smoke, we would have burned ~$0.11 (12× cost) and ~45 min (for full corpus truncation retries) on the same bug. **Auth smoke as the first unit is a universal pattern for any new provider integration.**

- **Dense-vs-MoE hypothesis cost $0.04 to falsify.** Unit 5b probe of Qwen-VL-Max was $0.04 and ~16 min. Had we deferred to "run the cheaper A3B and trust Lesson 4's prediction that dense would do better," we'd have opened a PR recommending dense-Max for production and later discovered broader detection degradation. The $0.04 empirical probe was ~50× ROI vs that counterfactual.

- **Fingerprint emerged during diagnosis, not design.** Option B Python diagnosis (comparing Claude vs cloud page-by-page) surfaced the "text is clean — no action needed" fingerprint. Had we gone directly from Unit 4 FAIL to Unit 5 without the diagnostic pause, we'd still have the R2 data but would likely have missed the fingerprint pattern that makes hybrid routing actually implementable. **Cheap diagnostic pauses between expensive units protect the downstream design.**

- **Partial close with specific residual > force-pass at any ceiling.** Per SCRUM-280's feedback-memory pattern: cloud A3B fails the letter of R2 but clears the *spirit* (the three academic books that drove the partial close). The specific residual — Python's technical-layout blind spot — has a concrete, implementable mitigation (SCRUM-281 Option D with fingerprint detection). This is a stronger close than either "force-pass by tuning thresholds" or "escalate to thinking-variant hoping for a clean R2."

---

## Implications for SCRUM-281 and SCRUM-282

**SCRUM-281 (routing remediation):** Promoted from *optional* to **required** for cloud-primary production default. Scope should widen slightly to include response-level fingerprint detection as the routing trigger, not just page-type heuristics or `issues: []` emptiness. Concrete implementation: a `FallbackFingerprintDetector` class in `tools/llm_providers/` that takes a `VisionResponse` and returns a set of page numbers that should be re-evaluated against Claude. Cost amortization via batch re-invocation.

**SCRUM-282 (baseline source-format standardization):** Unblocked but not blocking. The comparison script's page-overlap guard handled this cleanly on all 5 comparable books (100% overlap); Atomic Habits filename-normalization was the only casualty, and it's a one-file rename away from resolved. No longer urgent.

---

## References

- Plan: [docs/plans/2026-04-19-feat-scrum-283-cloud-vlm-eval-plan.md](../plans/2026-04-19-feat-scrum-283-cloud-vlm-eval-plan.md)
- Predecessor solution: [docs/solutions/scrum-280-local-vqa-calibration-patterns.md](scrum-280-local-vqa-calibration-patterns.md)
- Provider class: [tools/llm_providers/cloud_vl_provider.py](../../tools/llm_providers/cloud_vl_provider.py)
- Comparison harness: [tools/compare_vqa_reports.py](../../tools/compare_vqa_reports.py)
- Gate result artifacts:
  - `data/scrum283_unit3_6book_smoke_a3b/` — Unit 3 A3B 6-book smoke
  - `data/scrum283_unit4_gate_result_a3b.json` — Unit 4 gate verdict
  - `data/scrum283_unit5b_6book_smoke_qwen_vl_max/` — Unit 5b Max 6-book smoke
  - `data/scrum283_unit5b_gate_result_max.json` — Unit 5b gate verdict
- OpenRouter pricing (2026-04-19): `_CLOUD_PRICING` table in [cloud_vl_provider.py](../../tools/llm_providers/cloud_vl_provider.py)
- SCRUM-281 (promoted to required): routing remediation with fingerprint detection
- SCRUM-282 (unblocked): baseline source-format standardization
