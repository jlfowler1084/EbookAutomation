---
title: Fallback fingerprint routing — lessons + failure-mode taxonomy from SCRUM-281
type: solution
status: compound
date: 2026-04-19
origin_ticket: SCRUM-281
origin_plan: docs/plans/2026-04-19-001-feat-scrum-281-fallback-fingerprint-routing-plan.md
predecessor: docs/solutions/scrum-283-cloud-vlm-evaluation.md
related_tickets: [SCRUM-275, SCRUM-279, SCRUM-280, SCRUM-282, SCRUM-283]
tags: [vlm, vqa, fingerprint, hybrid-routing, mmmu, docvqa, failure-modes, cost-amortization]
---

# Fallback fingerprint routing — lessons + failure-mode taxonomy from SCRUM-281

Compound-knowledge writeup of four reusable lessons from the SCRUM-281 hybrid-routing implementation. Written after the R2 gate passed on the 6-book corpus smoke (corpus mean |Δ|=7.97, max per-book |Δ|=16.5 Oil Kings) with the cloud-A3B-primary + Claude-fallback architecture landed in production. The headline finding is a taxonomy — two distinct shapes of model failure that need different detection mechanisms — which generalizes well beyond VQA.

## Context

SCRUM-283 closed with a concrete routing recommendation: cloud Qwen3-VL-30B-A3B-Instruct on OpenRouter as the VQA primary, with Claude as a fallback for pages where the primary emitted response-level fallback fingerprints. SCRUM-281 implemented the hybrid architecture: `FallbackFingerprintDetector` class, corpus-backed substring matching, batched Claude re-invocation for flagged pages, cost accounting in the final report.

The corpus smoke demonstrated the hybrid works as designed on MMMU-shaped failures (Python in Easy Steps, Atomic Habits) — but also surfaced a second failure mode on Oil Kings that the fingerprint detector cannot catch by design. That surprise is the most valuable learning from the ticket.

Smoke summary (6 books, 48 pages sampled, hybrid stack vs Claude-only baseline):

| Book | \|Δ\| | Fallback fired | Pattern |
|---|---|---|---|
| Python in easy steps | **1.9** | 7/8 pages | MMMU-shaped — fingerprint fired, hybrid nearly perfectly calibrated |
| Mexico's Illicit Drug Networks | 6.3 | No | Clean cloud-primary response |
| Return of the Gods | 7.1 | No | Clean cloud-primary response |
| Decline of the West | 8.0 | No | Clean cloud-primary response (partial page overlap — SCRUM-282) |
| Atomic Habits | (skipped) | 4/8 pages | MMMU-shaped — fingerprint fired, fallback ran, filename drift excluded from comparison |
| Oil Kings | **16.5** | No | DocVQA-shaped — fingerprint did NOT fire, but baseline disagreement on p3 (|Δ|=56) |

Total smoke cost: ~$0.13 across 6 books (cloud ~$0.006 + Claude fallback $0.12). Well under SCRUM-283's $0.28/month projection for 20 books.

---

## Lesson 1 — Bounded-recoverable failure modes come in two shapes; detectors designed for one miss the other by design

**Pattern:** When a model fails on bounded tasks in ways that a secondary oracle could recover, the failure takes one of two *distinct* shapes. Fingerprint-style detection catches one shape cleanly and is blind to the other.

**The taxonomy:**

| Shape | What it looks like | How to detect | SCRUM-281 example |
|---|---|---|---|
| **MMMU-shaped** (empty default) | Model emits a text-stable default response — generic phrasing, empty issue lists, collapsed structured fields — when the input is outside its judgment distribution | Response-level fingerprint: substring corpus + empty-list + high-score checks on structured output | Python p35/p68/p108 with `issues: []` + score 100, or `"text is clean — no action needed"` boilerplate |
| **DocVQA-shaped** (confidently wrong) | Model emits a *specific, structurally-rich* response that matches the expected schema but disagrees with ground truth | Response-level fingerprint cannot help. Requires cross-reference against an oracle, an outlier-score heuristic, or a page-type score ceiling | Oil Kings p3: `issues: [{"category": "text_integrity", ...}]`, `score: 90` — specific finding, but Claude baseline scored p3 at 34 |

**Evidence from the corpus smoke:**

The fingerprint detector fired on 2/6 books (Python, Atomic Habits) — both MMMU-shaped. Claude fallback recovered them to within |Δ|=1.9 and the skipped-Atomic-Habits-80 respectively. That's the architecture working exactly as SCRUM-283 Lesson 3 designed.

The detector did *not* fire on Oil Kings p3, even though the page is the corpus's largest per-page disagreement. Cloud A3B's response was structurally rich and schema-valid — `issues[0].description` named a real finding category, score was 90 not 100, `category_scores` was populated. None of the three matchers (empty-issues, substring, category-scores-collapse) can see a "confidently wrong" response. That's not a detector bug — it's a boundary of the detection mechanism.

**Why this matters:** Fingerprint detection is cheap ($0 marginal cost per page) but only catches MMMU-shaped failures. Catching DocVQA-shaped failures requires a more expensive signal — cross-reference against a secondary response, an outlier statistic, or a domain-specific heuristic. Before designing any hybrid-routing architecture, name *which shape* the detector targets and acknowledge the residual blind spot explicitly in the design doc.

**How to apply (reusable):**

- In any hybrid-routing spec, enumerate failure modes by *shape*, not by frequency. "Fingerprint detection catches empty-default responses; confidently-wrong responses are a separate residual that this design does not address" is a stronger scope statement than "this design addresses the known failure modes."
- For critical domains (payments, medical, legal), fingerprint-alone is likely insufficient — budget for the DocVQA-shaped detector too, either as a follow-up or as a gated sampler (e.g., "5% of pages get a second-provider sanity check regardless of fingerprint").
- For non-critical domains, accept the DocVQA blind spot and document it as a known-limitation residual. The cost math still favors hybrid over oracle-only.

**Anti-pattern to avoid:** Declaring a hybrid-routing design "complete" when it only addresses one failure mode. If the design-phase solution doc doesn't name both MMMU and DocVQA shapes, the post-ship surprise is guaranteed.

---

## Lesson 2 — Response-level fingerprint corpus + batched re-invocation delivers the projected cost model even on small corpora

**Pattern:** SCRUM-283 projected the hybrid would cost ~$0.28/month at 20 books with ~15% of books triggering fallback. SCRUM-281's 6-book smoke landed at ~$0.13 on 2/6 books firing (33% book rate, 11/48 = 23% page rate). Both the projection and the corpus-smoke number are dominated by the Claude token cost on the flagged pages, not the primary cloud call.

**Evidence:**

- Cloud A3B (all 6 books, 8 pages each): ~$0.006 total. Cloud is essentially free at this scale.
- Claude fallback (Atomic Habits 4 pages + Python 7 pages): $0.0465 + $0.0735 = $0.12. This dominates.
- Per-flagged-page Claude cost: ~$0.01/page. Projection math held.

**Implementation notes that matter for reproducing:**

- **Batched, not per-page.** One Claude call per book with the flagged-page subset, not N individual calls. Plan R6 and SCRUM-283 Implementation note (line 142) both specified this. HTTP RTT + auth overhead would double the cost if per-page. `tools/visual_qa.py::run_claude_fallback()` filters `page_images` down to flagged pages and makes one `build_request → call`.
- **Post-batch-loop, pre-aggregate-scoring seam.** Integration at `tools/visual_qa.py` between the batch loop termination (~line 690) and aggregate-scoring block. Fallback mutations merge into `all_pages_results` by `page_number` before score aggregation, so the final overall score already reflects Claude's re-evaluation.
- **Cost accounting as additive fields.** `build_report` grew four optional kwargs (`fallback_tokens`, `fallback_provider_name`, `fallback_cost_usd`, `fallback_model`). `token_usage` dict gets `fallback_input_tokens`, `fallback_output_tokens`, `fallback_estimated_cost_usd`, `fallback_provider`, `fallback_model` fields *only when fallback fired* — omitted entirely when not. Existing callers that inspect `token_usage` don't break.

**How to apply (reusable):**

- Any hybrid-provider architecture should land *one* batched secondary call per report, never per-page. Confirm this in the plan, test it in integration tests (assert mock call count == 1 when multiple pages flagged).
- Token accounting in multi-provider reports should be *additive* (new fields for the secondary provider), not *restructured* (new top-level token-usage schema). Preserves backward compatibility with report consumers for free.
- When pricing varies per Claude model (Haiku / Sonnet / Opus), route the fallback's cost through the *primary provider's* pricing helper, not through a separate tier. `_resolve_pricing_tier()` in `claude_provider.py` handles the substring-based tier lookup; the hybrid block imports it directly to avoid re-implementing tier resolution.

**Anti-pattern to avoid:** Per-page fallback calls for "granularity" or "visibility." The batched call already carries per-page results in the response — granularity is in the output, not in the request count.

---

## Lesson 3 — Matcher-3 (report-level collapse) may be over-engineered; Matcher-1+2 caught everything

**Pattern:** The fingerprint detector shipped with three OR-combined matchers: (1) empty-issues + high-score per page, (2) substring match in issue description, (3) report-level collapse (all pages empty-issues + any page above threshold). Matcher 3 was a defense-in-depth addition — designed to catch the catastrophic "whole report is a fallback" case.

**Evidence from corpus smoke:**

- Matcher 3 did **not fire** on any of the 6 corpus books. Both books where fallback triggered (Python, Atomic Habits) had at least some pages with non-empty issues from cloud A3B, so `pages_with_issues` was non-empty and Matcher 3's gate short-circuited.
- Matcher 1 (empty-issues + high-score) fired on 4/7 Python pages.
- Matcher 2 (substring) fired on 3/7 Python pages + 4/4 Atomic Habits pages.

In practice, cloud A3B's failure mode is *mixed* — some pages get fallback responses, others get real findings, even within the same book. Matcher 3's "all pages look degenerate" precondition is too strict to fire in realistic conditions.

**Why it was worth shipping anyway:**

- Cheap to maintain (20 lines of code, covered by unit tests).
- Protects against a worst-case regression: if a cloud provider fully degrades (e.g., "all pages return `{}`"), Matcher 3 fires unconditionally.
- Makes the detection logic readable — Matchers 1, 2, 3 map cleanly to three distinct signal types.

**How to apply (reusable):**

- Ship defensive matchers for failure modes you haven't empirically observed *if* the code is cheap and the test surface is small. Removing them later is easy; adding them post-production after a surprise outage is not.
- But don't *design around* unobserved failure modes. The plan's fallback-routing architecture worked because Matchers 1+2 covered observed patterns — Matcher 3 is insurance, not a load-bearing component.
- In regression-contract tests, explicitly mark which matchers are observed vs defensive. Future readers should know "Matcher 3 is the catastrophic-degradation backstop — if it ever fires, something upstream has changed dramatically."

**Anti-pattern to avoid:** Removing Matcher 3 in a cleanup PR "because it never fires." The rare firing case is exactly when it matters.

---

## Lesson 4 (methodology) — Frozen corpus-derived regression fixtures make detector behavior stable against future tuning

**Pattern:** The Unit 5 regression contract took 4 frozen fixtures — one clear-flag page, one clear-no-flag page, one borderline empty-issues page at score 85, one negative case — captured from real SCRUM-283 and SCRUM-281 artifacts. These live in `tests/test_visual_qa_hybrid_routing.py::TestRegressionContract` and assert `detector.detect(parsed) == expected_set` exactly.

**Why this matters:**

When someone (future me) tunes the fingerprint corpus or threshold — say, adds "page is fine" to the substring list because a new provider emits that phrase — these tests immediately flag any behavioral change to the previously-calibrated cases. Tuning the corpus without regression tests means each tune-cycle risks silently breaking recognition of patterns that were working.

**How to apply (reusable):**

- When shipping any detector with a tunable corpus (substring list, threshold, rule set), capture 3–5 concrete ground-truth examples from the corpus smoke and freeze them as regression fixtures.
- Include both *positive* cases (detector must flag) and *negative* cases (detector must NOT flag). Asymmetric fixtures don't catch over-tuning — if all fixtures are "must flag," lowering thresholds makes everything pass.
- Document the fixture provenance in the test file (which book, which page, which smoke run). Future readers should be able to re-derive the fixture from raw data.
- When a tune is deliberate and a fixture needs to change, update the fixture in the same commit as the tune — don't split them. The commit is self-documenting: "tune threshold X; fixture Y moves from flagged to unflagged because [reason]."

**Anti-pattern to avoid:** "I'll add tests later once the corpus stabilizes." The corpus never stabilizes — new providers emit new patterns forever. Land fixtures with the first ship.

---

## Implications for residual tickets

**Residual #1 (DocVQA-shaped outlier detection):** Oil Kings p3 Δ=56 is the concrete motivation. A page-type score ceiling (e.g., "front_matter pages cannot score > 80 without at least one moderate issue") would have caught p3. Alternative: a light multi-provider sampler (every Nth page also goes to a second provider). Priority is low — it's one page out of 48 in corpus, and R2(b) passed at 16.5 without it. File it with the smoke evidence attached.

**Residual #2 (Python KFX layout investigation):** Both cloud A3B (58) and Claude (baseline ~60) agree Python in Easy Steps has genuine layout degradation. This is a *pipeline* issue, not a VQA issue — the book renders poorly through Calibre's KFX output (code blocks, inline bullet lists, operator precedence tables). SCRUM-281's hybrid stack did its job by reflecting the agreement faithfully. Separate concern worth investigating.

**Residual #3 (Option B back-matter deduction) — NOT filed:** Mexico's |Δ| landed at 6.3 without Option B. The scope-boundary decision at planning time (2026-04-19) was "file only if production evidence reappears." No evidence today; do not file speculatively.

**SCRUM-282 (baseline source-format drift):** Already filed. Smoke confirmed the drift limits comparison statistical power on Atomic Habits (skipped entirely), Decline (3/8 overlap), Mexico (3/8 overlap). No longer urgent for the R2 gate but still worth resolving for future calibration work.

---

## References

- Plan: [docs/plans/2026-04-19-001-feat-scrum-281-fallback-fingerprint-routing-plan.md](../plans/2026-04-19-001-feat-scrum-281-fallback-fingerprint-routing-plan.md)
- Predecessor solution: [docs/solutions/scrum-283-cloud-vlm-evaluation.md](scrum-283-cloud-vlm-evaluation.md) — Lesson 3 (fingerprint), Routing recommendation, Implementation notes
- Predecessor solution: [docs/solutions/scrum-280-local-vqa-calibration-patterns.md](scrum-280-local-vqa-calibration-patterns.md) — Lesson 4 (MoE ceiling, bounded-category + diffuse-page-type failure pattern)
- Deployment prompt: [prompts/SCRUM-281-fallback-fingerprint-routing.md](../../prompts/SCRUM-281-fallback-fingerprint-routing.md)
- Detector module: [tools/llm_providers/fingerprint_detector.py](../../tools/llm_providers/fingerprint_detector.py)
- Fingerprint corpus: [tools/visual_qa_fallback_fingerprints.json](../../tools/visual_qa_fallback_fingerprints.json)
- Integration point: [tools/visual_qa.py](../../tools/visual_qa.py) `run_visual_qa()` hybrid routing block (between batch loop and aggregate scoring)
- Tests: [tests/test_fingerprint_detector.py](../../tests/test_fingerprint_detector.py), [tests/test_visual_qa_hybrid_routing.py](../../tests/test_visual_qa_hybrid_routing.py)
- Merged PR: [jlfowler1084/EbookAutomation#5](https://github.com/jlfowler1084/EbookAutomation/pull/5)
- Smoke evidence (gitignored, local only): `data/scrum281_corpus_smoke_hybrid/` + `data/scrum281_corpus_smoke_hybrid/gate_result.json`
