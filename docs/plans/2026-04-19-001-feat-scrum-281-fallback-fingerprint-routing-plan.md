---
title: "feat: SCRUM-281 — fallback fingerprint routing for cloud-primary VQA"
type: feat
status: active
date: 2026-04-19
origin_ticket: SCRUM-281
predecessor_plan: docs/plans/2026-04-19-feat-scrum-283-cloud-vlm-eval-plan.md
predecessor_solution: docs/solutions/scrum-283-cloud-vlm-evaluation.md
---

# feat: SCRUM-281 — fallback fingerprint routing for cloud-primary VQA

## Overview

Promote cloud `qwen/qwen3-vl-30b-a3b-instruct` (via OpenRouter) to the default VQA primary, and add a response-level fingerprint detector that re-routes low-confidence pages to Claude in a single batched call. Ships the hybrid architecture SCRUM-283 recommended so cloud-primary doesn't silently regress on technical-layout books (Python-class).

Non-Claude primaries (cloud, local) run the detector after their batch loop completes. Pages whose parsed response matches a known-fallback fingerprint (`issues: []` + high score, generic "text is clean" descriptions, collapsed `category_scores: {}`) are collected into a single `ClaudeVisionProvider` batch call; returned per-page results replace the primary's entries in the report by `page_number`. Token totals accumulate across both providers.

## Problem Frame

SCRUM-283 closed partial: cloud A3B clears the academic-book ceiling that blocked SCRUM-280 (Oil Kings 22.6 → 14.6, Mexico 28.6 → 20.0) but degenerates on Python-in-Easy-Steps (36.6 |Δ|) because its vision circuit can't evaluate technical layouts — it emits a detectable default-response fingerprint instead of real findings. Claude evaluated the same pages correctly in the baseline.

SCRUM-283 Lesson 3 demonstrated that those fallback responses are text-stable across pages and books — a fingerprint detector can identify them at the report level and trigger a targeted Claude re-evaluation. The cost delta vs Claude-only is ~5× in Claude-only's favor (~$0.28/mo vs $1.60/mo at 20 books/month, 8-page sample), so hybrid is both quality-safe and cheap.

This ticket is the routing remediation. Without it, the SCRUM-283 routing recommendation can't ship to production.

## Requirements Trace

- **R1.** Primary-provider pages matching a known-fallback fingerprint are re-evaluated by Claude, and Claude's results replace the primary's per-page entries in the final report (see origin: `docs/solutions/scrum-283-cloud-vlm-evaluation.md` Lesson 3 + Routing recommendation).
- **R2(a).** Corpus mean |Δ| < 15 across 6 books, measured against `data/vqa_baseline_post_274/` (SCRUM-281 ticket description).
- **R2(b).** No per-book mean |Δ| > 20 (SCRUM-281 ticket description).
- **R3.** Non-degenerate score distribution maintained (no regression to SCRUM-280 2a-i collapse pattern).
- **R4.** `--provider claude` (primary) remains a no-op path for the detector — no redundant self-fallback.
- **R5.** Missing `ANTHROPIC_API_KEY` degrades gracefully: log a warning and ship the primary-only report, rather than crashing.
- **R6.** Claude re-invocation is a single batched call containing only the flagged pages — not one call per page (cost amortization per SCRUM-283 implementation note).

## Scope Boundaries

- **Out of scope:** Option B (per-`page_type` deduction weighting for back-matter). User-confirmed defer (2026-04-19) — Mexico's |Δ| dropped from 28.6 to 20.0 under cloud A3B without Option B; file a sharp residual ticket if p234-style over-deduction fires in production.
- **Out of scope:** Escalation to Qwen3-VL-235B-A22B-thinking or other premium VLMs. SCRUM-283 deferred; not urgent until production shows Claude fallback itself missing technical-layout defects.
- **Out of scope:** Baseline source-format standardization (SCRUM-282 territory — KFX vs PDF sampler drift).
- **Out of scope:** Rubric enum changes (e.g., the latent `"major"` severity inconsistency at `tools/visual_qa.py:619` vs the rubric's `critical/moderate/minor`). Separate cleanup ticket.

### Deferred to Separate Tasks

- **Option B (back-matter deduction weighting):** file a residual ticket with fresh evidence if needed; not part of SCRUM-281.
- **Thinking-variant probe:** file only if production shows fallback also missing Python-class defects.
- **`"major"` severity rubric reconciliation:** file a cleanup ticket (exists independently of SCRUM-281).

## Context & Research

### Relevant Code and Patterns

- **Provider base contract:** `tools/llm_providers/base.py` — `VisionProvider` (Protocol, `@runtime_checkable`) + `VisionResponse` (frozen dataclass: `raw_text`, `input_tokens`, `output_tokens`). Three providers (`ClaudeVisionProvider`, `LocalVisionProvider`, `CloudVLProvider`) each implement independently; no inheritance, no shared mixin.
- **Duck-typing precedent for provider-specific extensions:** `tools/visual_qa.py` batch loop at lines 569–586 uses `if hasattr(provider, "two_pass_call")` to route `LocalVisionProvider` through its two-pass path without extending the base Protocol. Mirror this pattern for detection — detection is a response-layer concern, not a provider concern.
- **Batch loop integration seam:** `tools/visual_qa.py` lines 558–608. Batch loop populates `all_pages_results: list[dict]` with parsed per-page entries (keys: `page_number`, `page_type`, `score`, `pass`, `issues[]`) and accumulates `total_input_tokens`, `total_output_tokens`. The clean injection point for the hybrid logic is between line 608 (end of batch loop) and line 613 (aggregate scoring).
- **Claude invocation signature:** `ClaudeVisionProvider.build_request(page_images: list[tuple[int, bytes]], rubric_text: str, model: str)` already handles batch-size-1 and batch-size-N cleanly. Use the same signature for the fallback call — no new helper needed on the provider itself.
- **Parse / repair pattern:** `tools/visual_qa.py::parse_qa_response()` at line 353 does a one-shot repair re-prompt on parse failure. This is the closest architectural analog to "re-evaluate flagged pages against a different provider" — the fallback helper should follow the same error-handling shape (log, return partial, never crash the run).
- **Rubric / enum source of truth:** `tools/visual_qa_rubric.md`. Per-page schema helpers in `tools/llm_providers/local_provider.py::_build_page_extraction_schema`. Claude uses prompt-level contract, not guided_json.
- **Config pattern:** `config/settings.json` `visual_qa` block — flat dict, no typed loader. Keys read inline via `.get(...)` + literal defaults in `visual_qa.py::main()` (provider factory at lines 857–885). Models registry is separate: `api_models` block already defines `haiku`, `sonnet`, `sonnet_latest`, `gemini_flash`.
- **Test conventions:** `tests/test_local_provider_phase2.py` — pytest, `unittest.mock.MagicMock` + `_make_fake_completion` helper, inline JSON (no fixture files). Duck-typing contract test at lines 1230–1313 is the direct template for "visual_qa routes to fallback when detector fires."
- **Captured ground-truth fingerprint samples:** `data/scrum283_unit3_6book_smoke_a3b/` (cloud A3B) and `data/scrum283_unit5b_6book_smoke_qwen_vl_max/` (Max). These contain real `"text is clean and readable with no visible artifacts"`, `"No action needed"`, `category_scores: {}`, `issues: []` + `score: 95` responses. Seed the fingerprint corpus from these, not from synthetic examples.

### Institutional Learnings

- **Response-level fingerprint is the routing trigger** — `docs/solutions/scrum-283-cloud-vlm-evaluation.md` Lesson 3. Three matchers: `issues == []` with `score >= threshold`, substring match on `issues[i].description` against a known-fallback corpus, collapsed `category_scores == {}`. Detector operates on parsed pages (post-schema-validation), not raw text.
- **Batched re-invocation, not per-page** — `docs/solutions/scrum-283-cloud-vlm-evaluation.md` Implementation (line 142). Cost model assumes one Claude call per run with the flagged-page subset, not N individual calls.
- **Do NOT gate on page-type alone** — `docs/solutions/scrum-280-local-vqa-calibration-patterns.md` Lesson 4. MoE ceiling is bounded by defect category, diffuse by page type. Page-type heuristics are insufficient; fingerprint is the primary signal.
- **Cheap smoke probe before corpus-scale** — `docs/solutions/scrum-283-cloud-vlm-evaluation.md` Methodology (line 165). Auth smoke as the first real invocation caught the `enable_thinking=False` bug for $0.009 vs $0.11 counterfactual.
- **Partial-close over force-pass** — user memory `feedback_close_partial_over_force_pass.md`. If Python-class books still fail after fallback, file a residual ticket rather than stacking fixes.
- **sb-chat VRAM decoupling** — user memory `project_sb_chat_shared_stack.md`. Cloud-primary frees sb-chat VRAM for CareerPilot / SecondBrain. Flag in session summary on merge: `NEW DEPENDENCY: EbookAutomation → (decoupled from) sb-chat`.
- **Source-format drift on fixtures** — `docs/solutions/scrum-280-local-vqa-calibration-patterns.md` Lesson 5. Fingerprint corpus should note provenance (which source format the captured responses came from); SCRUM-283 artifacts are KFX-source, which is the production path.

### External References

No external research performed. The codebase has strong local patterns for provider invocation + parse/repair; SCRUM-283 supplied the routing design directly; institutional learnings cover the remaining gaps.

## Key Technical Decisions

- **Detector lives in a new module, not on the Protocol.** `tools/llm_providers/fingerprint_detector.py` with a `FallbackFingerprintDetector` class. Follows the duck-typing precedent already established by `two_pass_call`; keeps response-layer logic out of the provider interface.
- **Detector input is parsed pages, not raw `VisionResponse`.** Signature: `detect(parsed_pages: list[dict], settings: FingerprintSettings) -> set[int]`. Separates parse concerns from detection concerns; easier to test with inline JSON; keeps the detector provider-agnostic.
- **Fingerprint corpus ships as a versioned JSON resource**, not Python constants. File: `tools/visual_qa_fallback_fingerprints.json`. Rationale: mirrors `visual_qa_rubric.md` as a versioned data artifact; new patterns can be added without code review; future provenance field tracks which source format/provider generated each sample.
- **Three matcher categories, combined via OR:** (1) `issues == []` AND `score >= fallback.empty_issues_score_threshold` (default `80`). (2) Any `issues[i].description` substring-matches the case-insensitive corpus. (3) Top-level `category_scores` is `{}` on a page that has any issues array content or a score ≥ 80. The empty+high-score combination is the hardest signal; lone `issues == []` on a low-scoring page is a legitimate pass-fail result, not a fingerprint.
- **Fallback target is hardwired to `ClaudeVisionProvider`.** Do not speculatively build a pluggable-target interface. If the fallback itself starts failing, open a residual ticket; SCRUM-281 does not design for that future.
- **Claude model for fallback defaults to `sonnet_latest` (`claude-sonnet-4-6`).** Rationale: VQA fallback is analysis-class work (project convention: sonnet for analysis); the SCRUM-280 Claude baseline was captured on Sonnet, so fallback results stay apples-to-apples against that baseline. Configurable via `visual_qa.fallback.claude_model`.
- **Missing `ANTHROPIC_API_KEY` degrades gracefully.** Log a warning, skip fallback, ship primary-only report. Production runs always have the key; CI/offline runs may not, and crashing there is the wrong failure mode.
- **Primary == Claude short-circuits the detector.** If `provider.name == "claude"`, skip fingerprint detection entirely — there's no self-fallback. Detector runs for `local` and `cloud_vl` providers.
- **Cost accounting gets a second token bucket.** `build_report()` signature grows to accept `fallback_tokens: tuple[int, int] | None = None` and `fallback_provider: VisionProvider | None = None`. Token usage in the final report is reported per provider, with combined cost summed.
- **`visual_qa.fallback.enabled` config flag gates whether the fallback fires.** Default `true`. Set to `false` for air-gapped / offline-only runs where Claude cannot be called. When disabled, detector does not run (no wasted CPU on the matcher).
- **Config default provider flip ships in this ticket.** `config/settings.json` `visual_qa.provider`: `"claude"` → `"cloud"`, and new keys `cloud_host`, `cloud_model`, `fallback` block added. This is the production rollout of SCRUM-283's recommendation.
- **`.env.example` is created** to document `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `LOCAL_LLM_VISION_MODEL`, `LOCAL_LLM_BASE_URL`, `CLOUD_VL_MODEL`. Currently no such file exists; onboarding has no clue which env vars the pipeline needs.

## Open Questions

### Resolved During Planning

- **Option B scope:** Deferred to a sharp residual ticket (user-confirmed 2026-04-19).
- **Detector lives where:** New module `tools/llm_providers/fingerprint_detector.py` (resolved by research — duck-typing precedent + greenfield placement).
- **Fingerprint corpus storage format:** JSON resource file (resolved — versioned data artifact, aligned with `visual_qa_rubric.md`).
- **Local-provider handling:** Detector runs for any non-Claude primary (local + cloud); `fallback.enabled` is the per-deployment gate.
- **Claude model for fallback:** `sonnet_latest` default, preserves baseline parity.

### Deferred to Implementation

- **Exact `empty_issues_score_threshold` value:** `80` as a starting point. Implementer validates against captured SCRUM-283 artifacts — if Python front-matter page 2 (`{"issues": [], "score": 100, "pass": true}`) is legitimately a clean page or a fallback depends on review of the actual PNG; tune threshold from the evidence, document the final choice in the corpus JSON.
- **Final list of substring fingerprints:** seed from SCRUM-283 artifacts (Lesson 3 samples), but the implementer should grep the full corpora under `data/scrum283_unit*/` for other recurring generic phrases before locking the list.
- **Cost accounting refactor shape:** `build_report` grows to accept fallback tokens — exact parameter shape (keyword arg vs positional vs a `TokenUsage` dataclass) can be decided during Unit 3 implementation when the real call site is in view.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

**Data flow (sequence):**

```
run_visual_qa(provider=cloud_vl)
  │
  │ [Batch loop — existing behavior, unchanged]
  ├─► for batch in batches:
  │     response = provider.build_request(...).call()  # or two_pass_call
  │     parsed = parse_qa_response(response.raw_text)
  │     all_pages_results.extend(parsed["pages"])
  │     total_input_tokens += response.input_tokens
  │     total_output_tokens += response.output_tokens
  │
  │ [NEW — hybrid routing between batch loop and aggregate]
  ├─► if provider.name != "claude" and settings.fallback.enabled:
  │     detector = FallbackFingerprintDetector.from_corpus(corpus_path)
  │     flagged_pages = detector.detect(all_pages_results, settings.fallback)
  │     if flagged_pages:
  │         claude_provider = ClaudeVisionProvider(api_key=ANTHROPIC_API_KEY)
  │         flagged_images = [(n, png) for n, png in page_images if n in flagged_pages]
  │         claude_response = claude_provider.build_request(flagged_images, rubric, model).call()
  │         claude_pages = parse_qa_response(claude_response.raw_text)["pages"]
  │         # Replace primary's entries by page_number
  │         for cp in claude_pages:
  │             for i, ap in enumerate(all_pages_results):
  │                 if ap.get("page_number") == cp.get("page_number"):
  │                     all_pages_results[i] = cp
  │         fallback_tokens = (claude_response.input_tokens, claude_response.output_tokens)
  │
  │ [Aggregate scoring — existing behavior, unchanged]
  ├─► compute overall_score, category_scores, top_issues from all_pages_results
  │
  │ [Report — signature grows to carry fallback cost]
  └─► build_report(..., fallback_tokens=fallback_tokens,
                        fallback_provider=claude_provider)
```

**Matcher decision logic (conceptual):**

```
detect(page, settings):
    if page.issues == [] and page.score >= settings.empty_issues_score_threshold:
        return True   # Matcher 1: empty-plus-high-score
    for issue in page.issues:
        if any(fp in issue.description.lower() for fp in settings.substring_corpus):
            return True   # Matcher 2: known-fallback phrase
    # Matcher 3 applies at the report level, not per-page:
    if report.category_scores == {} and any(p.score >= 80 for p in report.pages):
        flag_all_empty_issue_pages()
    return False
```

**Config surface:**

```
visual_qa.provider               = "cloud"            (flipped from "claude")
visual_qa.cloud_host             = "openrouter"       (new, with CLI default fallback)
visual_qa.cloud_model            = "qwen/qwen3-vl-30b-a3b-instruct"  (new)
visual_qa.fallback.enabled       = true               (new, gates detector + fallback)
visual_qa.fallback.claude_model  = "claude-sonnet-4-6" (new, keyed into api_models.sonnet_latest)
visual_qa.fallback.empty_issues_score_threshold = 80  (new, matcher tuning)
visual_qa.fallback.corpus_path   = "tools/visual_qa_fallback_fingerprints.json" (new)
```

## Implementation Units

- [ ] **Unit 1: Fingerprint detector module + corpus JSON**

**Goal:** Pure-data detector class with unit tests, fully decoupled from `visual_qa.py` and provider instances. No production wiring yet.

**Requirements:** R1 (detection half).

**Dependencies:** None.

**Files:**
- Create: `tools/llm_providers/fingerprint_detector.py`
- Create: `tools/visual_qa_fallback_fingerprints.json`
- Modify: `tools/llm_providers/__init__.py` (add `FallbackFingerprintDetector` to exports)
- Test: `tests/test_fingerprint_detector.py`

**Approach:**
- `FallbackFingerprintDetector` class with `from_corpus(corpus_path: str | Path) -> FallbackFingerprintDetector` classmethod and `detect(parsed_pages: list[dict], settings: FingerprintSettings) -> set[int]` instance method.
- `FingerprintSettings` as a simple frozen dataclass: `empty_issues_score_threshold: int`, `substring_corpus: tuple[str, ...]`, `match_category_scores_collapse: bool`.
- Corpus JSON schema: `{"version": 1, "provenance": "...", "substring_fingerprints": [...], "notes": "..."}`. Document provenance (KFX-source, SCRUM-283 artifacts) in the top-level `provenance` field.
- Seed corpus from SCRUM-283 captured artifacts: minimum `["text is clean and readable", "no action needed", "no visible artifacts", "no significant issues"]`; grep `data/scrum283_unit*/` for additional recurring phrases during implementation.

**Execution note:** Test-first. Detector is a pure function on parsed data — trivially unit-testable and the behavior is specified tightly enough in the SCRUM-283 doc that tests can be written before implementation.

**Patterns to follow:**
- Module layout: mirror `tools/llm_providers/local_provider.py` header conventions (`from __future__ import annotations`, `logging.getLogger(...)`, utf-8 stdout reconfig not needed here).
- Test style: `tests/test_local_provider_phase2.py` — `MagicMock`, inline JSON dicts, pytest fixtures for settings.

**Test scenarios:**
- *Happy path:* parsed page with `issues == [] and score == 95` → flagged.
- *Happy path:* parsed page with `issues == [{"description": "Text is clean and readable with no visible artifacts", ...}]` → flagged.
- *Happy path:* parsed pages where `report.category_scores == {}` AND at least one page has `score >= 80` → all empty-issues pages flagged.
- *Edge case:* parsed page with `issues == [] and score == 30` (legitimate failed page) → NOT flagged.
- *Edge case:* parsed page with rich issues (e.g., 3 moderate findings with specific descriptions) → NOT flagged.
- *Edge case:* empty `parsed_pages` list → returns empty set.
- *Edge case:* `score` threshold boundary — `score == 80` with empty issues → flagged; `score == 79` → not flagged.
- *Edge case:* substring matcher is case-insensitive ("NO ACTION NEEDED" matches).
- *Error path:* `from_corpus` with missing file → raises `FileNotFoundError` with path in message.
- *Error path:* `from_corpus` with malformed JSON → raises `ValueError` with helpful parse hint.
- *Integration scenario:* load real fixtures from `data/scrum283_unit5b_6book_smoke_qwen_vl_max/` Python file → detector flags the known-fallback pages and skips the legitimate ones.

**Verification:**
- Running `py -3.12 -m pytest tests/test_fingerprint_detector.py -v` passes all scenarios.
- `tools/visual_qa_fallback_fingerprints.json` parses as valid JSON and contains `version`, `provenance`, `substring_fingerprints` keys.

---

- [ ] **Unit 2: Batched Claude fallback helper**

**Goal:** Add a `run_claude_fallback(...)` helper in `tools/visual_qa.py` that takes flagged page numbers + the original page_images list + rubric + claude_model, instantiates `ClaudeVisionProvider` from `ANTHROPIC_API_KEY`, makes ONE batched Claude call with the flagged-page subset, parses the response, and returns `(claude_pages: list[dict], input_tokens: int, output_tokens: int)`. Does not modify existing code paths.

**Requirements:** R1 (re-invocation half), R5 (graceful degradation), R6 (single batched call).

**Dependencies:** None (Unit 1 not strictly required; can build in parallel if desired).

**Files:**
- Modify: `tools/visual_qa.py` (add helper function — no wiring yet)
- Test: `tests/test_visual_qa_hybrid_routing.py` (new file)

**Approach:**
- Function signature: `run_claude_fallback(flagged_page_numbers: set[int], page_images: list[tuple[int, bytes]], rubric_text: str, claude_model: str, api_key: str | None) -> tuple[list[dict], int, int]`.
- If `api_key` is `None` or empty → log warning (`logger.warning("ANTHROPIC_API_KEY not set — skipping fallback for %d flagged pages", ...)`) and return `([], 0, 0)`.
- Filter `page_images` down to only flagged pages.
- Instantiate `ClaudeVisionProvider(api_key=api_key)`, call `build_request(filtered, rubric_text, claude_model)` → `call(payload)`.
- Parse response via existing `parse_qa_response(response.raw_text, provider=claude_provider, original_payload=payload)`; extract `pages` from parsed dict.
- On any exception during the Claude call or parse: log error, return `([], response.input_tokens, response.output_tokens)` if response captured else `([], 0, 0)`. Never crash the outer `run_visual_qa`.

**Execution note:** Characterization-lean — mock Claude's `call()` response rather than making live HTTP. Integration smoke is deferred to Unit 5.

**Patterns to follow:**
- Error handling shape: mirror the parse-and-repair logic at `tools/visual_qa.py::parse_qa_response()` (line 353-ish) — try, log, return partial.
- Test mocks: `tests/test_local_provider_phase2.py::_make_fake_completion` for the mock-response helper; adapt for the Anthropic Messages API response shape used by `ClaudeVisionProvider`.

**Test scenarios:**
- *Happy path:* 3 flagged pages → helper filters images to those 3, builds ONE Claude payload, returns 3 parsed pages + non-zero tokens. Assert Claude's `build_request` was called exactly once with exactly those 3 page images.
- *Happy path:* 1 flagged page → same logic at batch-size-1 works.
- *Edge case:* `flagged_page_numbers` is empty → returns `([], 0, 0)` without touching Claude at all.
- *Edge case:* `api_key is None` → logs warning, returns `([], 0, 0)`, Claude constructor never called.
- *Error path:* Claude's `call()` raises → logs error, returns `([], 0, 0)`. `run_visual_qa` can continue with primary results.
- *Error path:* Claude response is malformed JSON → logs error, returns `([], input_tokens, output_tokens)` so the tokens that WERE consumed are still accounted for in cost.
- *Integration scenario:* flagged set contains a page number not present in `page_images` (defensive check) → filter silently drops it, doesn't crash.

**Verification:**
- `py -3.12 -m pytest tests/test_visual_qa_hybrid_routing.py::TestRunClaudeFallback -v` passes.
- Helper is callable standalone (can be imported and exercised without invoking `run_visual_qa`).

---

- [ ] **Unit 3: Integration — wire detector + fallback helper into `run_visual_qa`**

**Goal:** Insert the hybrid routing between the batch loop and the aggregate-scoring block in `run_visual_qa`. Extend `build_report` to carry fallback token/cost data. Short-circuit the detector when primary is Claude.

**Requirements:** R1 (full end-to-end), R4 (Claude-primary no-op), R5, R6.

**Dependencies:** Unit 1 (detector), Unit 2 (helper).

**Files:**
- Modify: `tools/visual_qa.py` — insert routing block between lines 608 and 613; update `build_report` signature + call site; thread new config values through `run_visual_qa` parameters
- Modify: `tests/test_visual_qa_hybrid_routing.py` (extend)

**Approach:**
- New `run_visual_qa` parameters: `fallback_enabled: bool = True`, `fallback_claude_model: str = "claude-sonnet-4-6"`, `fallback_corpus_path: str | Path = "tools/visual_qa_fallback_fingerprints.json"`, `fallback_empty_issues_score_threshold: int = 80`. Default values preserve current behavior for callers that don't opt in (though `main()` will set them from config).
- Integration block (after line 608):
  1. Short-circuit: `if provider.name == "claude" or not fallback_enabled: fallback_tokens = None; fallback_provider = None`.
  2. Otherwise: load detector via `FallbackFingerprintDetector.from_corpus(fallback_corpus_path)`; build `FingerprintSettings` from params.
  3. `flagged = detector.detect(all_pages_results, settings)`. If empty → skip fallback.
  4. Call `run_claude_fallback(flagged, page_images, rubric_text, fallback_claude_model, os.environ.get("ANTHROPIC_API_KEY"))`.
  5. Merge returned Claude pages by `page_number`: replace matching entries in `all_pages_results`.
  6. Set `fallback_tokens = (claude_in, claude_out)`, `fallback_provider = ClaudeVisionProvider(...)` (or a name-only sentinel if we don't want to double-instantiate).
- `build_report` signature grows: `build_report(..., fallback_tokens: tuple[int, int] | None = None, fallback_provider_name: str | None = None, fallback_cost_usd: float | None = None)`. Final report's `token_usage` dict gains `fallback_input_tokens`, `fallback_output_tokens`, `fallback_estimated_cost_usd`, `fallback_model` fields when fallback fired; omitted when not.
- Logging: one INFO log when detector flags > 0 pages (`"Fingerprint detector flagged %d/%d pages — routing to Claude (%s)"`); one after the Claude call completes with token counts.

**Execution note:** Characterize the existing `run_visual_qa` behavior with a primary-only integration test before modifying the function body — ensures the hybrid path additions don't silently change existing semantics.

**Patterns to follow:**
- Duck-typing at the routing boundary: mirror `if hasattr(provider, "two_pass_call")` pattern at lines 581-586 — keep provider-type checks branchless where possible.
- Token accounting: mirror the existing `total_input_tokens += response.input_tokens` incremental pattern.

**Test scenarios:**
- *Happy path:* primary is cloud, detector flags 2 pages → Claude called once with 2 images → merged report has Claude's entries for those 2 page numbers, primary's for the rest. `token_usage.fallback_input_tokens > 0`.
- *Happy path:* primary is cloud, detector flags 0 pages → Claude is NEVER called. `token_usage.fallback_input_tokens` absent or zero.
- *Edge case (R4):* primary is Claude → detector not invoked, Claude not called a second time, report shape matches current behavior exactly (regression guard).
- *Edge case:* `fallback_enabled=False` in settings → detector not invoked, no Claude call, primary-only results.
- *Error path (R5):* `ANTHROPIC_API_KEY` missing → Unit 2 helper returns empty, primary results unchanged, warning logged.
- *Error path:* detector raises unexpectedly (e.g., corpus file missing) → caught, logged, primary-only report shipped. This is a `try/except` around the hybrid block; do not let detector failures break the run.
- *Integration scenario:* primary is local two-pass, detector flags 1 page → two-pass path is respected in the batch loop, then fallback still fires on flagged page (local is not excluded from detection just because it's local).
- *Integration scenario:* merge-by-`page_number` — primary returns pages [2, 35, 68], Claude returns pages [35, 68], final `all_pages_results` has exactly 3 entries with Claude data on 35/68 and primary data on 2.

**Verification:**
- `py -3.12 -m pytest tests/test_visual_qa_hybrid_routing.py -v` passes all scenarios.
- Manual smoke: run `py -3.12 tools/visual_qa.py --provider cloud --input output/kindle/"Python in easy steps*".kfx --max-pages 2` (or equivalent) with `OPENROUTER_API_KEY` and `ANTHROPIC_API_KEY` set; verify logs show detector flagging + Claude call + merged report containing Claude-shaped issues on the flagged pages. **Do this first** before Unit 5 corpus-scale smoke.

---

- [ ] **Unit 4: Configuration defaults + env-var registry**

**Goal:** Flip the default provider to cloud, add the fallback config block, document all VQA env vars in a new `.env.example`, update `CLAUDE.md` to list `OPENROUTER_API_KEY` alongside existing keys.

**Requirements:** Ships the SCRUM-283 routing recommendation as the production default.

**Dependencies:** Unit 3 must be implementation-complete (config keys must exist before being set in config).

**Files:**
- Modify: `config/settings.json` — `visual_qa` block update
- Create: `.env.example`
- Modify: `CLAUDE.md` (project-level) — add `OPENROUTER_API_KEY` to External Dependencies or a new "Cloud VQA" subsection
- Modify: `tools/visual_qa.py::main()` — read new config keys, thread them into `run_visual_qa`; update CLI `argparse` to accept `--fallback-enabled`, `--fallback-claude-model`, `--fallback-corpus-path` as overrides
- Test: `tests/test_visual_qa_hybrid_routing.py` — add config round-trip test

**Approach:**
- `config/settings.json` `visual_qa` block after edit:
  ```
  "visual_qa": {
    "enabled": false,
    "dpi": 100,
    "max_pages": 8,
    "pass_threshold": 70,
    "rubric_path": "tools\\visual_qa_rubric.md",
    "provider": "cloud",
    "cloud_host": "openrouter",
    "cloud_model": "qwen/qwen3-vl-30b-a3b-instruct",
    "local_model": "qwen3.5-35b-a3b-fp8",
    "local_base_url": "http://localhost:8000/v1",
    "fallback": {
      "enabled": true,
      "claude_model": "claude-sonnet-4-6",
      "empty_issues_score_threshold": 80,
      "corpus_path": "tools\\visual_qa_fallback_fingerprints.json"
    }
  }
  ```
- `.env.example` contents (single-source onboarding doc): all keys with comments, no real values:
  ```
  ANTHROPIC_API_KEY=     # Claude API — baseline VQA + fallback re-invocation
  OPENROUTER_API_KEY=    # Qwen3-VL-A3B cloud primary (SCRUM-283)
  GEMINI_API_KEY=        # Gemini 2.5 Flash — Tier 2.5 OCR fallback
  LOCAL_LLM_VISION_MODEL=qwen3.5-35b-a3b-fp8
  LOCAL_LLM_BASE_URL=http://localhost:8000/v1
  CLOUD_VL_MODEL=qwen/qwen3-vl-30b-a3b-instruct
  EBOOK_SMTP_PASSWORD=   # Kindle email delivery
  ```
- `CLAUDE.md` update: append to the existing "External Dependencies" Python table or add a new line under "Claude API Integration" / "Gemini API Integration" sections for "Cloud VQA: Use OpenRouter API (`OPENROUTER_API_KEY`) for Qwen3-VL-A3B vision. Model configured via `visual_qa.cloud_model`."

**Execution note:** None — pure config plumbing.

**Patterns to follow:**
- `config/settings.json` uses backslash-escaped Windows paths (`"tools\\visual_qa_rubric.md"`). Match existing convention; don't switch to forward-slash.
- `argparse` additions: mirror existing flag conventions (snake_case_underscore Python, `--kebab-case` CLI).

**Test scenarios:**
- *Happy path:* `load_settings_json()` returns the new `visual_qa.fallback` block; integration test asserts `run_visual_qa(...)` called with `fallback_enabled=True, fallback_claude_model="claude-sonnet-4-6"` when settings round-trip through `main()`.
- *Happy path:* CLI `--fallback-enabled false` override wins over config `true`.
- *Edge case:* legacy `config/settings.json` without the `fallback` block (backward compat) → `main()` applies hardcoded defaults (`enabled=true`, `claude_model="claude-sonnet-4-6"`, `empty_issues_score_threshold=80`, default corpus path).
- *Edge case:* `visual_qa.fallback.corpus_path` is a relative path → resolved relative to repo root.
- *Integration scenario:* fresh checkout with no `.env` → `.env.example` present; running `main()` with missing `OPENROUTER_API_KEY` errors at provider construction with a clear message pointing at `.env.example`.

**Verification:**
- `python -c "import json; s=json.load(open('config/settings.json')); print(s['visual_qa']['provider'], s['visual_qa']['fallback']['enabled'])"` prints `cloud True`.
- `.env.example` exists and parses as valid KEY=value format (no quoting, one per line).
- `grep -n OPENROUTER_API_KEY CLAUDE.md` returns a match.

---

- [ ] **Unit 5: Corpus smoke + regression contract**

**Goal:** Validate the hybrid stack against the 6-book corpus, confirm R2(a)/R2(b)/R3 pass, and capture a regression contract that freezes the detector+merge behavior against code drift.

**Requirements:** R2(a), R2(b), R3.

**Dependencies:** Units 1-4 complete.

**Files:**
- Create: `data/scrum281_corpus_smoke_hybrid/` (gitignored per existing `data/` pattern — verify entry in `.gitignore`)
- Modify: `tests/test_visual_qa_hybrid_routing.py` — add regression-contract class with frozen-response fixtures
- Optional: `docs/solutions/scrum-281-fallback-fingerprint-routing.md` (close-out compound knowledge — only at ticket close, not in implementation)

**Approach:**
- Run `py -3.12 tools/visual_qa.py --input <each of 6 books> --provider cloud` (or the existing corpus-runner if one exists; otherwise shell loop). Redirect reports to `data/scrum281_corpus_smoke_hybrid/`.
- Run `py -3.12 tools/compare_vqa_reports.py data/scrum281_corpus_smoke_hybrid/ data/vqa_baseline_post_274/` (or whatever the comparison script is called per SCRUM-283 references) — capture corpus mean |Δ|, per-book |Δ|, score distribution.
- Verify: corpus mean |Δ| < 15 (R2(a)); no per-book |Δ| > 20 (R2(b)); score distribution non-degenerate (R3).
- Regression contract: pick 3 representative primary-provider raw JSON outputs (one clear-flag, one clear-no-flag, one borderline) from the smoke run, commit them as test fixtures in `tests/fixtures/scrum281/` (inline via string constants if preferred, matching `test_local_provider_phase2.py` style), and assert `detector.detect(parsed) == expected_set` for each. This freezes the corpus + threshold behavior; future fingerprint-corpus changes that alter these assertions require deliberate acknowledgment.

**Execution note:** If R2(a) or R2(b) fail on corpus-scale with the hybrid stack, do NOT tune thresholds or expand the corpus unless the failure clearly maps to a single un-fingerprinted fallback pattern. If the failure is broader, close SCRUM-281 partial with specific residual evidence per the `close partial over force-pass` pattern.

**Patterns to follow:**
- SCRUM-283 corpus smoke methodology: cheap 2-page auth smoke (Unit 3 verification) before corpus-scale; cost probe before acceptance.

**Test scenarios:**
- *Regression contract:* frozen fixture 1 (known-fallback Python page from SCRUM-283 Unit 5b Max) → detector flags.
- *Regression contract:* frozen fixture 2 (clean SCRUM-283 Unit 3 A3B academic-book page with real findings) → detector does NOT flag.
- *Regression contract:* frozen fixture 3 (borderline empty-issues page with score 85) → detector flags (above 80 threshold).
- *Corpus validation (one-shot, not re-run each test):* corpus smoke produces reports within R2 bounds; this is captured as a manual verification step in the PR description, not a persistent test (integration test would require live API calls).

**Verification:**
- Hand-verified: 6-book corpus smoke report summary shows corpus mean |Δ| < 15, no per-book > 20, non-degenerate distribution. Numbers pasted into the PR description alongside a link to `data/scrum281_corpus_smoke_hybrid/`.
- `py -3.12 -m pytest tests/test_visual_qa_hybrid_routing.py -v` passes including the regression-contract tests.

---

## System-Wide Impact

- **Interaction graph:** The hybrid routing adds one post-batch-loop step to `run_visual_qa`. It does NOT change the batch-loop invariants, the parse/repair logic in `parse_qa_response`, or the aggregate-scoring math — only inserts between batch completion and aggregation. Callers of `run_visual_qa` that didn't pass the new kwargs get primary-only behavior via default values, though `main()` will always set them from config.
- **Error propagation:** Detector or fallback-helper failures are caught within the hybrid block, logged, and skipped — they do not propagate up and break the run. This matches the "partial results better than none" philosophy already established in the batch loop at `visual_qa.py:601-603`.
- **State lifecycle risks:** The merge-by-`page_number` in `all_pages_results` is in-place mutation. If any downstream code held a reference to a pre-merge entry, it would see the post-merge state. Current code does not hold such references, but this is worth a sanity check during Unit 3 implementation.
- **API surface parity:** CLI flags `--fallback-enabled`, `--fallback-claude-model`, `--fallback-corpus-path` are additive; no existing flags change semantics. `run_visual_qa` signature grows with optional kwargs; existing callers continue to work.
- **Integration coverage:** The unit tests in `test_visual_qa_hybrid_routing.py` mock both providers. Real end-to-end validation is Unit 5 corpus smoke + Unit 3 verification manual smoke. No mock will prove the OpenRouter → detector → Anthropic chain behaves correctly on a live network; the 2-page manual smoke in Unit 3 is the gate for that.
- **Unchanged invariants:**
  - `VisionProvider` Protocol shape and three provider implementations are untouched (duck-typing preserves this).
  - Grounding / page-number guards in `local_provider.py` (SCRUM-280 P2 lines 401-414) are untouched.
  - Parse/repair logic (`parse_qa_response`) is untouched.
  - Two-pass routing for local provider is untouched.
  - Rubric (`visual_qa_rubric.md`) and schema helpers (`_build_page_extraction_schema`) are untouched.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Fingerprint corpus has false positives on Python-class-like simple structure books (e.g., Decline of the West) — detector flags legitimately-clean pages, Claude cost overshoots projected ~15%. | Seed corpus conservatively from SCRUM-283 artifacts; Unit 5 corpus smoke validates trigger rate per book; if Decline shows >5% trigger, tune `substring_corpus` or `empty_issues_score_threshold` before ship. |
| Claude fallback also misses technical-layout issues on Python-class books — hybrid doesn't actually fix the regression. | Close SCRUM-281 partial per `close partial over force-pass` precedent; file residual ticket for Qwen3-VL-235B-A22B-thinking probe. Do NOT stack additional fixes. |
| `ANTHROPIC_API_KEY` missing in production silently degrades to cloud-only — R2 gate fails in CI but dev doesn't notice until deploy. | Unit 4 `main()` startup: if `fallback.enabled=true` AND provider != claude AND `ANTHROPIC_API_KEY` missing → log a clear WARNING (not just debug). CI check: if we have a CI gate for VQA, it should fail if this warning is emitted. |
| Cost accounting refactor in `build_report` breaks existing tests that pin the report schema. | Backward-compat: new fields (`fallback_*`) are additive; existing `input_tokens`, `output_tokens`, `estimated_cost_usd` keep their meaning (primary only). Update affected tests as part of Unit 3. |
| `data/` directories for smoke results grow large over time (KFX + PDF + PNG + JSON). | Verify `.gitignore` already covers `data/scrum*/` (it should — SCRUM-280/283 precedent). Do not commit smoke artifacts. |

## Documentation / Operational Notes

- **Close-out compound-knowledge doc:** At ticket close, write `docs/solutions/scrum-281-fallback-fingerprint-routing.md` covering: final corpus seed, threshold tuning evidence, corpus-smoke R2 results, false-positive rate per book, cost delta vs projection, and one reusable lesson (likely around "detector false-positive tuning via frozen regression fixtures"). Not part of implementation — post-ship artifact.
- **PR / session summary note:** Flag `NEW DEPENDENCY: EbookAutomation → (decoupled from) sb-chat` on merge (cross-project externality per memory). Also flag the `OPENROUTER_API_KEY` addition so ClaudeInfra's env-var registry can mirror it.
- **No migration or rollout hazard:** `visual_qa.enabled = false` in default config means this feature doesn't fire on every pipeline run; it's opt-in via CLI. No silent production behavior change.

## Sources & References

- **Ticket:** [SCRUM-281](https://jlfowler1084.atlassian.net/browse/SCRUM-281)
- **Predecessor solution:** [docs/solutions/scrum-283-cloud-vlm-evaluation.md](../solutions/scrum-283-cloud-vlm-evaluation.md) — Lesson 3 (fingerprint), Routing recommendation, Implementation (lines 140-144), Implications for SCRUM-281 (lines 175-179).
- **Predecessor plan:** [docs/plans/2026-04-19-feat-scrum-283-cloud-vlm-eval-plan.md](2026-04-19-feat-scrum-283-cloud-vlm-eval-plan.md)
- **Related solution:** [docs/solutions/scrum-280-local-vqa-calibration-patterns.md](../solutions/scrum-280-local-vqa-calibration-patterns.md) — Lesson 4 (bounded-category + diffuse-page-type failure), Lesson 5 (source-format drift on fixtures).
- **Key files:**
  - [tools/llm_providers/base.py](../../tools/llm_providers/base.py) — Protocol + dataclass
  - [tools/llm_providers/claude_provider.py](../../tools/llm_providers/claude_provider.py) — fallback target
  - [tools/llm_providers/cloud_vl_provider.py](../../tools/llm_providers/cloud_vl_provider.py) — primary per SCRUM-283
  - [tools/llm_providers/local_provider.py](../../tools/llm_providers/local_provider.py) — schema + guard patterns
  - [tools/llm_providers/__init__.py](../../tools/llm_providers/__init__.py) — package exports
  - [tools/visual_qa.py](../../tools/visual_qa.py) — batch loop + integration seam (lines 558-608) + `build_report` (line 429) + `main()` factory (lines 857-885)
  - [tools/visual_qa_rubric.md](../../tools/visual_qa_rubric.md) — enum source of truth
  - [config/settings.json](../../config/settings.json) — `visual_qa` block
  - [tests/test_local_provider_phase2.py](../../tests/test_local_provider_phase2.py) — test pattern template
- **Captured ground-truth artifacts (fingerprint seed + regression fixtures):**
  - `data/scrum283_unit3_6book_smoke_a3b/` — cloud A3B primary corpus
  - `data/scrum283_unit5b_6book_smoke_qwen_vl_max/` — Max corpus (aggressive fallback fingerprint exemplar)
  - `data/vqa_baseline_post_274/` — Claude baseline (R2 comparison target)
