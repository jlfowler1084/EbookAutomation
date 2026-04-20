# SCRUM-281 — VQA calibration P3: fallback fingerprint routing for cloud-primary VQA

**Model:** SONNET
**Justification:** Structured 5-unit implementation following a tight plan with strong origin grounding (SCRUM-283 close-out supplied the routing design directly). Units 1 + 2 are independent and parallelizable; Unit 3 is the integration + cost-accounting refactor; Units 4–5 are config plumbing + corpus validation. Sonnet handles structured, well-bounded work well. Opus-level reasoning already spent on scope deliberation (Option B deferred) and design decisions.

## Tickets

- **Primary:** SCRUM-281 — VQA calibration P3: detection-miss remediation for Oil Kings + Mexico Illicit (re-scoped by SCRUM-283 close-out to "fallback fingerprint routing for cloud-primary VQA")
- **Blocks:** None. Promotes SCRUM-283's routing recommendation from design to shippable production default.
- **Relates to:** SCRUM-275 (local provider shipped), SCRUM-279 (P1 guided_json shipped), SCRUM-280 (P2 calibration partial-closed — academic-book ceiling identified), SCRUM-283 (cloud VLM evaluation — supplies the primary model recommendation, the fingerprint design, and the fallback cost model).

## Estimated Scope

Five-unit multi-file change: one new module (`tools/llm_providers/fingerprint_detector.py`), one new data file (`tools/visual_qa_fallback_fingerprints.json`), one new `.env.example`, one new test file (`tests/test_fingerprint_detector.py`), one new integration test file (`tests/test_visual_qa_hybrid_routing.py`). Modifications to `tools/visual_qa.py` (integration seam + helper + `build_report` + `main()` CLI), `tools/llm_providers/__init__.py` (exports), `config/settings.json` (`visual_qa` block), `CLAUDE.md` (env-var registry). Unit 5 also captures smoke corpus to gitignored `data/scrum281_corpus_smoke_hybrid/`.

---

## Phase 0 — Worktree Setup

**Branch:** `worktree/SCRUM-281-fallback-fingerprint-routing`
**Base:** `master` at HEAD (`12a31fc` — SCRUM-283 merge, or later)
**Worktree Mode:** **create** — no worktree exists yet for this ticket

Before any other work:

1. `git checkout master && git pull`
2. Confirm `master` HEAD is `12a31fc` or later (SCRUM-283 merged): `git log --oneline -5`
3. Create worktree: `git worktree add .worktrees/worktree-SCRUM-281-fallback-fingerprint-routing -b worktree/SCRUM-281-fallback-fingerprint-routing master`
4. Enter worktree: `cd .worktrees/worktree-SCRUM-281-fallback-fingerprint-routing`
5. Confirm branch: `git branch --show-current` → `worktree/SCRUM-281-fallback-fingerprint-routing`
6. Confirm clean state: `git status` should show no modifications
7. Confirm SCRUM-283 baseline tests green: `py -3.12 -m pytest tests/test_vision_provider_phase1.py tests/test_local_provider_phase2.py -q` → zero failures

If any step fails, STOP and report. Do not attempt to "fix up" worktree state.

---

## Context

Read the full implementation plan at: `docs/plans/2026-04-19-001-feat-scrum-281-fallback-fingerprint-routing-plan.md`

The plan is self-contained — units are independent enough that an implementer can execute sequentially (1 → 2 → 3 → 4 → 5) or parallelize Units 1+2. The points below are **what isn't obvious from the plan alone** — decisions transferred from the brainstorm/scope-resolution session that shape how you should read the plan itself.

**Design decisions made during planning (reinforced by this session's scope resolution):**

- **Option B (back-matter deduction weighting) was deliberated and deferred this session.** Mexico's per-book |Δ| dropped from 28.6 → 20.0 under cloud A3B without Option B, so it's no longer load-bearing for R2. Do NOT re-add back-matter deduction weighting, per-`page_type` weight modifiers, or leniency tables in `build_scoring_request()`. If Mexico p234-style over-deduction reappears in production under the hybrid stack, file a fresh residual ticket with specific evidence. See plan "Scope Boundaries → Deferred to Separate Tasks."
- **Respect the "close partial over force-pass" posture.** Per user memory `feedback_close_partial_over_force_pass.md`: if R2 fails on corpus-scale smoke after the hybrid stack lands, DO NOT stack additional prompt hacks, threshold tuning passes, or heuristic fallbacks on top of Claude. Close SCRUM-281 partial with sharp residual evidence (which book, which pages, which category misses) and file a residual ticket for thinking-variant probe or other escalation. This posture protected SCRUM-280 and SCRUM-283 — do not break it here.
- **Seed the fingerprint corpus from SCRUM-283 captured artifacts, not synthesized examples.** `data/scrum283_unit3_6book_smoke_a3b/` (cloud A3B) and `data/scrum283_unit5b_6book_smoke_qwen_vl_max/` (Max) contain real observed fallback responses. Grep those directories for recurring generic phrases during Unit 1. If you want to expand the corpus speculatively based on what "might" be a fallback pattern, STOP — you need evidence from captured data, not intuition.
- **SCRUM-280 grounding guards are load-bearing — do not modify them.** `tools/llm_providers/local_provider.py` lines 401-414 hold the P2 grounding clause in the detection prompt. `tests/test_local_provider_phase2.py` lines 1193-1222 pin the corresponding system-message content. These are specified by SCRUM-280 P2 and must stay verbatim. SCRUM-281 works above this layer — the fingerprint detector sits between the parse step and the aggregate step, untouched by local_provider guard code.
- **Detector operates on parsed pages (post-schema-validation), not raw text.** The guided_json constraints are what make `issues: []` a Python boolean instead of a prose regex match. If you find yourself tempted to add NLP, spaCy, or sentence-embedding fuzzy matching, STOP — the matcher is a short list of exact substring checks plus two boolean checks. Keep it boring.
- **Duck-typing, not Protocol extension.** Detection is a response-layer concern, not a provider concern. The precedent at `tools/visual_qa.py:581-586` (`if hasattr(provider, "two_pass_call")`) is the pattern to mirror. Do not add methods to `VisionProvider` Protocol in `tools/llm_providers/base.py`. Do not add provider-side detection hooks.

**Options considered and rejected:**

- **Option A (category-specific detection instruction tuning)** — rejected upstream by SCRUM-283: prompt tuning within the local-A3B class cannot close the MMMU-shaped ceiling. Superseded by cloud A3B + fingerprint fallback.
- **Option C (hybrid routing for ALL pages through Claude)** — rejected by the SCRUM-281 ticket: does not fix the detection miss. If local returns `issues: []` and Claude receives an empty issue list for scoring, Claude also produces a high score. Per-page routing on the empty-detection signal (Option D) is the correct architecture.
- **Option B (back-matter deduction weighting)** — deferred (see above).
- **Escalating fallback target to Qwen3-VL-235B-A22B-thinking** — deferred by SCRUM-283 close-out. Cost is 2.5× Max's; `OutputTruncatedError` guard may trip even with `enable_thinking=False`; and if the core Python-class fix doesn't land cleanly with Claude, the fix is a residual ticket, not another model probe. Hardwire Claude Sonnet 4.6 as the fallback target.
- **Pluggable fallback-target interface** — rejected. Speculative flexibility for a single production path. If thinking-variant or another provider becomes the fallback later, refactor then, not now.
- **Fingerprint detection as an exception type (like `OutputTruncatedError`, `PageCountMismatchError`)** — rejected. Detection is recoverable — the right shape is a function returning `set[int]` of flagged page numbers, not a terminal error. The research compared the two patterns and the recoverable-return shape fits the "route and merge" semantics better.

**Hidden constraints or gotchas:**

- **`data/scrum*/` directories are gitignored** per existing SCRUM-280/SCRUM-283 precedent. Verify this holds for `data/scrum281_corpus_smoke_hybrid/` before creating it. If somehow it isn't covered, add the pattern — do NOT commit smoke artifacts.
- **Claude's `build_request` signature is batch-only** — `list[tuple[int, bytes]]`, no per-page helper. The fallback helper (Unit 2) will call `build_request([single_page_1, single_page_2, ...], rubric, model)` with the flagged subset. Batch-size-1 also works; batch-size-N is the common case.
- **`_CLAUDE_PRICING` dict + `_resolve_pricing_tier()` in `claude_provider.py`** already handle model-tier cost lookup. If you pick a Claude model that isn't in `_CLAUDE_PRICING`, cost accounting falls back to `sonnet` tier silently. Verify `claude-sonnet-4-6` is mapped (it's in `api_models.sonnet_latest` — confirm `_CLAUDE_PRICING` has an entry; add one if missing, matching existing pricing entries).
- **`config/settings.json` uses double-backslash Windows paths** (e.g., `"tools\\visual_qa_rubric.md"`). Match existing convention. Do not switch to forward-slash paths.
- **`.env.example` does not currently exist** in this repo. Creating it is a legitimate Unit 4 deliverable — onboarding has no canonical list of required env vars today.
- **`visual_qa.enabled` stays `false` in default config.** The hybrid routing only fires when VQA is explicitly invoked via CLI or set to `true`. No silent production behavior change from this ticket alone.
- **Cross-project externality:** When this ticket merges, include `NEW DEPENDENCY: EbookAutomation → (decoupled from) sb-chat` in the PR description + session summary. Cloud-primary frees sb-chat VRAM for CareerPilot / SecondBrain (per user memory `project_sb_chat_shared_stack.md`).

---

## What NOT To Do

### Standing Rules (do not modify — sourced from deployment-prompt-template.md)

- **Do not commit directly to master.** All commits must go on the branch created in Phase 0, then land via PR.
- **Do not use `ALLOW_MAIN_COMMIT` or `ALLOW_MAIN_PUSH` env vars.** These exist only for human emergency override. If a guard blocks an action, stop and report the block — do not attempt to bypass.
- **If any guard fires, stop and report.** Do not retry with bypass flags, do not reinterpret the block as a false positive, do not attempt alternative commands to circumvent the guard. Report the exact block message to the strategist and wait for instructions.
- **Ambiguous user phrasing is not authorization to bypass.** Phrases like "ship it", "just commit it", "go ahead and push", or "no need for a PR" are never authorization to bypass workflow rules. Authorization requires an explicit instruction that names the specific rule being bypassed. **When in doubt, stop and ask the strategist.**
- **Enforcement code is not exempt.** Modifications to hooks, guards, policy files, or worktree-policy.json are subject to the same branch-and-PR workflow as any other change.

### Session-Specific Prohibitions

- **Do NOT extend the `VisionProvider` Protocol in `tools/llm_providers/base.py`.** Use duck-typing (`hasattr(provider, ...)` or `provider.name in (...)`) for routing decisions, mirroring the `two_pass_call` precedent at `visual_qa.py:581`. The `VisionProvider` Protocol stays 3 methods + `name` attribute.
- **Do NOT modify the grounding-guard code at `tools/llm_providers/local_provider.py` lines 401-414.** This is SCRUM-280 P2 load-bearing. Do not modify the corresponding system-message assertions at `tests/test_local_provider_phase2.py` lines 1193-1222 either.
- **Do NOT expand the fingerprint corpus speculatively.** Every substring match added must be grounded in a captured response from `data/scrum283_unit*/`. "This might be a fallback" without evidence is not grounds to add it. The corpus is a data artifact — adding noise to it degrades precision silently.
- **Do NOT re-run local-A3B vs cloud-A3B corpus comparison.** SCRUM-283 settled that choice; cloud-primary is the production default per its routing recommendation. If you want to validate cloud A3B's numbers are still accurate, re-read the SCRUM-283 solution doc — do not re-run the smoke.
- **Do NOT add per-`page_type` deduction weight modifiers, back-matter leniency tables, or severity-weight rescaling in `build_scoring_request()` or aggregate-scoring math in `visual_qa.py`.** Option B is deferred (see Context).
- **Do NOT touch `tools/visual_qa_rubric.md` or the `_build_page_extraction_schema` / `_build_detection_schema` / `_build_scoring_schema` helpers.** Rubric + schema are out of scope.
- **Do NOT rewrite `parse_qa_response` in `visual_qa.py`.** Study its error-handling shape (for mirroring in Unit 2) but do not modify it.

---

## Phase 1 — Audit (READ-ONLY, STOP FOR REVIEW)

Before writing any code:

1. Read `docs/plans/2026-04-19-001-feat-scrum-281-fallback-fingerprint-routing-plan.md` top-to-bottom. Confirm you understand all 5 units, the R1–R6 requirements, and the Scope Boundaries → Deferred section.
2. Read `docs/solutions/scrum-283-cloud-vlm-evaluation.md` Lesson 3 (fingerprint detection) + Routing recommendation + Implications for SCRUM-281 (lines 175-179). This is the origin of the detection design.
3. Read `tools/llm_providers/base.py` (Protocol + dataclass), `tools/llm_providers/claude_provider.py` (fallback target signature), `tools/llm_providers/cloud_vl_provider.py` (primary), `tools/llm_providers/local_provider.py` (detection prompt + grounding guards — DO NOT MODIFY).
4. Read `tools/visual_qa.py` lines 486–709 (`run_visual_qa` function top to bottom). Identify the exact integration seam between the batch loop and aggregate scoring (plan calls it "between line 608 and 613" — confirm these line numbers are still accurate on master HEAD).
5. Read `tools/visual_qa.py::build_report()` (around line 429). Confirm the current `token_usage` shape in the final report.
6. Read `tests/test_local_provider_phase2.py` lines 1193-1222 (grounding system-message assertion — DO NOT MODIFY) and lines 1230-1313 (duck-typing contract test — template for Unit 3 routing tests).
7. Inspect captured fingerprint artifacts: list `data/scrum283_unit3_6book_smoke_a3b/` and `data/scrum283_unit5b_6book_smoke_qwen_vl_max/`. Open the Python-in-easy-steps report from Unit 5b (Max) — identify at least 3 concrete substring fingerprints beyond the 4 seeded in the plan.
8. Verify `.gitignore` covers `data/scrum*/` (it should — SCRUM-280/SCRUM-283 precedent). If not, flag to strategist BEFORE Phase 6.
9. Confirm `config/settings.json` `visual_qa` block on master HEAD matches what the plan's Unit 4 expects (`provider: "claude"`, no `cloud_host`, `cloud_model`, `fallback` block). If it differs (e.g., someone pre-flipped a default), flag to strategist.
10. Verify `_CLAUDE_PRICING` in `tools/llm_providers/claude_provider.py` has an entry for `claude-sonnet-4-6` or `claude-sonnet-4` (substring match). If missing, this is a micro-deliverable inside Unit 4.

**Success criteria:**
- You can name the integration seam line numbers (post-batch-loop, pre-aggregate) on master HEAD.
- You have a list of at least 3 additional substring fingerprints grounded in captured artifacts (beyond the 4 seeded in the plan).
- You know whether `claude-sonnet-4-6` is in `_CLAUDE_PRICING` or needs adding.
- You have confirmed `.gitignore` coverage for smoke artifacts.
- You understand the duck-typing routing pattern and can explain why the detector doesn't live on the Protocol.

**STOP.** Report findings to strategist before proceeding to Phase 2.

---

## Phase 2 — Unit 1: Fingerprint Detector Module + Corpus JSON

Implement the plan's Unit 1 deliverables:

1. Create `tools/visual_qa_fallback_fingerprints.json` with `version`, `provenance` (KFX-source, SCRUM-283 Unit 3 + Unit 5b artifacts), `substring_fingerprints` (seed list from plan + your Phase 1 additions), and `notes` fields.
2. Create `tools/llm_providers/fingerprint_detector.py`:
   - `FingerprintSettings` frozen dataclass with `empty_issues_score_threshold: int`, `substring_corpus: tuple[str, ...]`, `match_category_scores_collapse: bool`.
   - `FallbackFingerprintDetector` class with `from_corpus(corpus_path: str | Path)` classmethod and `detect(parsed_pages: list[dict], settings: FingerprintSettings) -> set[int]` instance method.
   - All three matcher categories (empty-plus-high-score per-page, substring per-issue, category-scores-collapse at report level).
3. Modify `tools/llm_providers/__init__.py` to export `FallbackFingerprintDetector` and `FingerprintSettings`.
4. Create `tests/test_fingerprint_detector.py` covering ALL test scenarios listed in the plan's Unit 1 (happy path × 3, edge cases × 4, error paths × 2, integration scenario × 1).

**Execution posture:** Test-first. Write the failing test for matcher 1 (empty-plus-high-score per-page) before writing the detector class. Then matcher 2, then matcher 3. Get each test green before moving to the next.

**Success criteria:**
- `py -3.12 -m pytest tests/test_fingerprint_detector.py -v` → all scenarios pass.
- `python -c "import json; print(json.load(open('tools/visual_qa_fallback_fingerprints.json'))['version'])"` → `1`.
- `python -c "from tools.llm_providers import FallbackFingerprintDetector; print('ok')"` → `ok`.
- No modifications to any file outside Unit 1's `Files:` list.

**STOP.** Report: list of fingerprints you added beyond the plan's seed, test pass count, any edge cases you discovered during implementation that weren't in the plan. Wait for strategist approval before Phase 3.

---

## Phase 3 — Unit 2: Batched Claude Fallback Helper

Implement the plan's Unit 2 deliverables:

1. Add `run_claude_fallback(flagged_page_numbers: set[int], page_images: list[tuple[int, bytes]], rubric_text: str, claude_model: str, api_key: str | None) -> tuple[list[dict], int, int]` as a module-level function in `tools/visual_qa.py` (near the top, with the other helpers — not inside `run_visual_qa`).
2. Handle missing `api_key` via WARN log + `([], 0, 0)` return. Never raise.
3. Filter `page_images` to only flagged pages, instantiate `ClaudeVisionProvider`, make ONE batched `build_request → call` sequence, parse via `parse_qa_response`, extract `pages`.
4. Wrap Claude call + parse in try/except — log and return partial tokens on failure.
5. Create `tests/test_visual_qa_hybrid_routing.py` (new file) with a `TestRunClaudeFallback` class covering ALL test scenarios from the plan's Unit 2 (happy × 2, edge × 3, error × 2, integration × 1).
6. Mock Claude's `call()` via `unittest.mock.MagicMock` — do NOT make live HTTP calls. Use `_make_fake_completion`-style helpers adapted to the Anthropic Messages API response shape.

**Execution posture:** Characterization-lean. Write one happy-path test first to pin the function signature, then iterate on edge and error cases.

**Success criteria:**
- `py -3.12 -m pytest tests/test_visual_qa_hybrid_routing.py::TestRunClaudeFallback -v` → all scenarios pass.
- Helper is independently importable: `python -c "from tools.visual_qa import run_claude_fallback; print(run_claude_fallback.__doc__[:80] if run_claude_fallback.__doc__ else 'ok')"`.
- No modifications to `run_visual_qa`, `build_report`, or `main()` yet — Unit 2 only adds the helper.
- Claude provider is NEVER instantiated when `api_key is None` (assert this via mock call count).

**STOP.** Report: test pass count, any Anthropic-response shape surprises, confirmation that `run_visual_qa` body is still untouched. Wait for strategist approval before Phase 4.

---

## Phase 4 — Unit 3: Integration — Wire Detector + Helper into `run_visual_qa`

Implement the plan's Unit 3 deliverables:

1. Add the four new kwargs to `run_visual_qa`: `fallback_enabled`, `fallback_claude_model`, `fallback_corpus_path`, `fallback_empty_issues_score_threshold` (with defaults per the plan).
2. Insert the hybrid routing block between the batch loop's end (around line 608 on master) and the aggregate-scoring block (around line 613):
   - Short-circuit on `provider.name == "claude"` or `fallback_enabled is False`.
   - Load detector via `FallbackFingerprintDetector.from_corpus(...)`.
   - `flagged = detector.detect(all_pages_results, settings)`.
   - If flagged is non-empty, call `run_claude_fallback(...)`, merge returned pages into `all_pages_results` by `page_number`, track `fallback_tokens`.
   - Wrap the entire hybrid block in try/except — log + skip on any failure, primary results must survive.
3. Extend `build_report` signature with `fallback_tokens: tuple[int, int] | None = None`, `fallback_provider_name: str | None = None`, `fallback_cost_usd: float | None = None`, `fallback_model: str | None = None`. Add matching fields to the `token_usage` dict — omitted when fallback didn't fire.
4. Update the `build_report` call site in `run_visual_qa` to pass the new kwargs.
5. If `_CLAUDE_PRICING` is missing `claude-sonnet-4-6`, add an entry matching existing sonnet pricing.
6. Extend `tests/test_visual_qa_hybrid_routing.py` with a `TestRunVisualQAHybridRouting` class covering ALL test scenarios from the plan's Unit 3 (happy × 2, edge × 2, error × 2, integration × 2).
7. Write a characterization test FIRST — a primary-Claude run that asserts the final report shape matches the pre-Unit-3 behavior byte-for-byte (modulo new optional fields being absent). This is the regression guard for R4.

**Execution posture:** Characterization-first on R4 (Claude-primary no-op). Write the regression test before touching `run_visual_qa`. If that test can't be written without touching `run_visual_qa` first (e.g., because mocks need the new signature), write a skip-marked placeholder and come back to it before commit.

**Success criteria:**
- `py -3.12 -m pytest tests/test_visual_qa_hybrid_routing.py -v` → all scenarios pass (both `TestRunClaudeFallback` from Phase 3 and `TestRunVisualQAHybridRouting` from this phase).
- `py -3.12 -m pytest tests/ -q` → zero regressions across the full test suite.
- `grep -n "def run_visual_qa" tools/visual_qa.py` — confirm the function signature grew as expected.
- Manual smoke (DEFERRED to end of Phase 4 — do NOT skip): set `ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY`, run `py -3.12 tools/visual_qa.py --input output/kindle/"Python in easy steps*".kfx --provider cloud --max-pages 2`. Verify logs show: primary cloud call → fingerprint detector flagging → Claude call with exactly 2 pages → merged report with Claude-shaped issues. Cost should be under $0.02 total. If the detector flags 0 pages on Python (which would be surprising given SCRUM-283 evidence), STOP and report.

**STOP.** Report: regression test pass count, full-suite test pass count, 2-page manual smoke output (paste the final token_usage dict + the count of fingerprint-flagged pages). Wait for strategist approval before Phase 5.

---

## Phase 5 — Unit 4: Configuration Defaults + Env-Var Registry

Implement the plan's Unit 4 deliverables:

1. Update `config/settings.json` `visual_qa` block: flip `provider: "claude"` → `"cloud"`, add `cloud_host`, `cloud_model`, and the full `fallback` block (`enabled`, `claude_model`, `empty_issues_score_threshold`, `corpus_path`) per the plan's specification. Preserve existing keys and ordering where reasonable.
2. Create `.env.example` at repo root documenting `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `LOCAL_LLM_VISION_MODEL`, `LOCAL_LLM_BASE_URL`, `CLOUD_VL_MODEL`, `EBOOK_SMTP_PASSWORD`. One per line, KEY=value format, with comments.
3. Update `CLAUDE.md` project-level: add a line to "External Dependencies" or a new "Cloud VQA" subsection noting `OPENROUTER_API_KEY` is required for `visual_qa.provider: "cloud"`.
4. Update `tools/visual_qa.py::main()`:
   - Read new config keys with fallback defaults (backward compat for configs missing the `fallback` block).
   - Add CLI overrides: `--fallback-enabled`, `--fallback-claude-model`, `--fallback-corpus-path`.
   - Thread values into the `run_visual_qa(...)` call.
5. Extend `tests/test_visual_qa_hybrid_routing.py` with a `TestConfigRoundTrip` class covering ALL test scenarios from the plan's Unit 4 (config → runtime, CLI override, legacy-config backward compat, relative corpus path resolution, missing `OPENROUTER_API_KEY` error clarity).

**Execution posture:** Straight plumbing. No need for test-first here — the tests codify the contract.

**Success criteria:**
- `python -c "import json; s=json.load(open('config/settings.json')); print(s['visual_qa']['provider'], s['visual_qa']['fallback']['enabled'])"` → `cloud True`.
- `test -f .env.example && echo exists` → `exists`.
- `grep -n OPENROUTER_API_KEY CLAUDE.md` → a match.
- `py -3.12 -m pytest tests/test_visual_qa_hybrid_routing.py::TestConfigRoundTrip -v` → all scenarios pass.
- `py -3.12 tools/visual_qa.py --help` shows the three new `--fallback-*` flags.
- Full test suite still green: `py -3.12 -m pytest tests/ -q`.

**STOP.** Report: config round-trip test pass count, CLI help output (paste the new flags' help text), confirmation that legacy configs (without `fallback` block) still load without errors. Wait for strategist approval before Phase 6.

---

## Phase 6 — Unit 5: Corpus Smoke + Regression Contract

Implement the plan's Unit 5 deliverables:

1. **Pre-smoke checklist:**
   - Confirm `.gitignore` covers `data/scrum281_corpus_smoke_hybrid/` (add pattern if needed).
   - Confirm `ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY` are set in `.env`.
   - Confirm the 6-book corpus exists in `output/kindle/` per `CLAUDE.md` Test Corpus table.
2. **2-page auth smoke FIRST** (per SCRUM-283 Lesson 6 methodology): run one cloud-provider invocation with `--max-pages 2` on a known-fallback book (Python). Confirm the detector fires and Claude is invoked on the 2 pages. Cost should be under $0.02. If smoke fails, STOP — corpus-scale smoke will burn ~10× the cost on the same bug.
3. **Corpus-scale smoke:** run the hybrid stack against all 6 books, writing reports to `data/scrum281_corpus_smoke_hybrid/`. Estimated cost: $0.05–$0.30 depending on fallback rate.
4. **R2/R3 evaluation:** run `py -3.12 tools/compare_vqa_reports.py data/scrum281_corpus_smoke_hybrid/ data/vqa_baseline_post_274/` (or whichever comparison script SCRUM-283 used — confirm path in `docs/solutions/scrum-283-cloud-vlm-evaluation.md` references). Capture:
   - Corpus mean |Δ| (target: < 15 for R2(a))
   - Per-book mean |Δ| (target: no book > 20 for R2(b))
   - Score distribution (target: non-degenerate, no 2a-i-style collapse for R3)
5. **Regression contract:** add a `TestFingerprintRegressionContract` class to `tests/test_visual_qa_hybrid_routing.py` (or a new `tests/fixtures/scrum281/` dir) with 3 frozen primary-response JSON fixtures (one clear-flag, one clear-no-flag, one borderline) and assert `detector.detect(parsed) == expected_set` for each. This freezes the fingerprint-corpus behavior against drift.
6. If R2(a) or R2(b) fails, STOP — do NOT tune thresholds or expand corpus unless the failure clearly maps to a single unfingerprinted pattern. Report to strategist; the "close partial over force-pass" posture may require filing a residual ticket rather than iterating.

**Execution posture:** Validation. If all gates pass, write the brief corpus-smoke findings for the PR description. If a gate fails, close partial per the posture in Context.

**Success criteria:**
- 2-page auth smoke logs show fingerprint flagging + Claude invocation + merged report.
- Corpus smoke completes without exceptions (or only expected "partial results" logged for individual book failures).
- R2(a): corpus mean |Δ| < 15.
- R2(b): no per-book |Δ| > 20.
- R3: score distribution non-degenerate (eyeball spread; if tooling produces a histogram, attach it).
- `py -3.12 -m pytest tests/test_visual_qa_hybrid_routing.py -v` → all scenarios (including new regression contract) pass.
- Full test suite still green.
- `data/scrum281_corpus_smoke_hybrid/` exists but is NOT staged in git (`git status` confirms).

**STOP.** Report: R2/R3 numbers (paste them), cost delta vs projected $0.28/mo, fallback trigger rate per book (should hover around 15%), regression-contract test pass count. Wait for strategist approval before Phase 7.

---

## Phase 7 — Commit and Push

**STOP before committing.** Report all files to strategist.

After approval:

1. Stage (list specific files — do NOT use `git add -A`):
   ```
   git add tools/llm_providers/fingerprint_detector.py
   git add tools/llm_providers/__init__.py
   git add tools/visual_qa_fallback_fingerprints.json
   git add tools/visual_qa.py
   git add config/settings.json
   git add .env.example
   git add CLAUDE.md
   git add tests/test_fingerprint_detector.py
   git add tests/test_visual_qa_hybrid_routing.py
   ```
   (Add `tests/fixtures/scrum281/` files if Unit 5 created any; do NOT add `data/scrum281_corpus_smoke_hybrid/`.)
2. Commit with a Conventional-Commits message:
   ```
   git commit -m "[SCRUM-281] feat: fallback fingerprint routing for cloud-primary VQA"
   ```
   (Multi-paragraph body optional; if added, mention the cross-project sb-chat VRAM decoupling note.)
3. Push: `git push -u origin worktree/SCRUM-281-fallback-fingerprint-routing`
4. **STOP before opening PR.** Wait for strategist to confirm PR creation.

---

## Verification Checklist

- [ ] Branch was created via `git worktree add` and all work happened in the worktree
- [ ] No commits were made to master
- [ ] No bypass env vars were used
- [ ] Phase 1 audit completed before any file creation
- [ ] `VisionProvider` Protocol in `tools/llm_providers/base.py` was NOT modified
- [ ] Grounding-guard code at `local_provider.py` lines 401-414 was NOT modified
- [ ] Rubric (`tools/visual_qa_rubric.md`) was NOT modified
- [ ] Fingerprint corpus additions are grounded in captured artifacts under `data/scrum283_unit*/`
- [ ] 2-page auth smoke ran BEFORE corpus-scale smoke (Unit 5)
- [ ] R2(a), R2(b), R3 numbers captured and reported
- [ ] `data/scrum281_corpus_smoke_hybrid/` is gitignored
- [ ] PR description flags `NEW DEPENDENCY: EbookAutomation → (decoupled from) sb-chat`
- [ ] Branch is pushed but PR is NOT yet opened

---

## Report Structure

At each STOP gate, report back with:
1. **Findings** — What was discovered or changed
2. **Assumptions changed** — Anything that contradicts the plan or this prompt
3. **Options** — If a decision point was reached, what are the alternatives
4. **Recommendation** — Your recommended path, with rationale

At final completion, also include:
5. **Commit hashes** — For each commit made
6. **Out-of-scope findings** — Anything that warrants a follow-up ticket (likely candidates: Option B residual, thinking-variant probe if Python still fails, `"major"` severity rubric reconciliation)

---

## Invocation

```
claude --model sonnet "[SCRUM-281] Fallback fingerprint routing for cloud-primary VQA -- Read prompts/SCRUM-281-fallback-fingerprint-routing.md and follow the instructions"
```
