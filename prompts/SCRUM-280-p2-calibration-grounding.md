# SCRUM-280 P2 — Local VQA grader-leniency calibration + page_number marker grounding

**Model:** SONNET
**Justification:** Structured multi-file implementation with conditional branching (Unit 1 mode classification drives Unit 4 branch; Unit 3 is conditional on Unit 2 + Unit 5 R4 gate failure), 6 implementation units, shared-stack approval gates, and experiment-loop execution. Sonnet handles structured execution well; the plan is tight and the 13 document-review findings were addressed before handoff.

## Tickets

- **Primary:** SCRUM-280 — Local VQA — P2 grader-leniency calibration + page_number marker grounding
- **Blocks:** None
- **Relates to:** SCRUM-275 (Phase 2 local provider — shipped), SCRUM-279 (P1 guided_json structural fix — shipped, merge `ac033cd`, opens this P2 follow-up)

## Estimated Scope

Six-unit multi-file change under `tools/llm_providers/local_provider.py` (primary edit target), `tools/visual_qa.py` (orchestration, only if two-pass lands), `tools/llm_providers/base.py` (Protocol extension, only if two-pass lands), `tests/test_local_provider_phase2.py` (regression contracts), plus three new files: `tools/analyze_vqa_mode_classification.py` (classifier script), `tests/test_vqa_mode_classifier.py`, `data/scrum280_mode_classification/classification.json`. Also extends `tools/debug_guided_json_preflight.py` with two new probe cases. Unit 3 and Unit 4 sub-unit 4b-ii are conditional — the winning-configuration set depends on runtime evidence.

---

## Phase 0 — Worktree Setup

**Branch:** `worktree/SCRUM-280-p2-calibration-grounding`
**Base:** `master@0ac7b1c` (the P1 merge-follow-up "mark P1 plan complete after merge")
**Worktree Mode:** **create** — no worktree exists yet for this ticket

Before any other work:

1. `git checkout master && git pull`
2. Confirm `master` HEAD is `0ac7b1c` or later (P1 complete): `git log --oneline -5`
3. Create worktree: `git worktree add .worktrees/worktree-SCRUM-280-p2-calibration-grounding -b worktree/SCRUM-280-p2-calibration-grounding master`
4. Enter worktree: `cd .worktrees/worktree-SCRUM-280-p2-calibration-grounding`
5. Confirm branch: `git branch --show-current` → `worktree/SCRUM-280-p2-calibration-grounding`
6. Confirm clean state: `git status` should show no modifications
7. Confirm P1 baseline: `py -3.12 -m pytest tests/test_vision_provider_phase1.py tests/test_local_provider_phase2.py -q` → all P1 tests green (38+ tests — exact count depends on P1 additions, just verify zero failures)

If any step fails, STOP and report. Do not attempt to "fix up" worktree state.

---

## Context

Read the full implementation plan at: `docs/plans/2026-04-18-004-feat-scrum-280-p2-calibration-grounding-plan.md`

The plan is structured so you can execute each unit in order; Unit 2 and Unit 1 are independent and can interleave. The points below are **what isn't obvious from the plan alone** — decisions transferred from document-review that shape how you should read the plan itself.

**Design decisions made during planning (reinforced by document-review):**

- **R2 is a two-part gate, not an aggregate.** The plan spells this out (aggregate mean |Δ| < 15 AND per-book max |Δ| ≤ 20), but the *reason* is worth repeating: aggregate means hide tails, tails are the failure mode for a quality gate. A variant that lands at mean |Δ|=14.9 with one book at Δ=28 must fail R2. Do not treat per-book gate as optional.
- **`PageNumberGroundingError` defensive guard (Unit 2 sub-step 2b) lands regardless of prompt or schema fix success.** It is a P1-style defensive guard — mirrors `PageCountMismatchError` + `OutputTruncatedError`. Downstream consumers at `tools/pattern_db.py:660` and `module/EbookAutomation.psm1:2273` persist `page_number` to SQLite; positional output silently poisons analytics across books. The guard makes that failure mode loud. Stays in place even after Units 2+3 complete.
- **SB-35 is already live.** Document-review probed `http://localhost:8000/v1/models` on 2026-04-18 and confirmed `max_model_len: 131072`, vLLM 0.19.0. P1's smoke addendum numbers (in `docs/plans/2026-04-18-003-*`) were captured at 65K. Every P2 measurement must use a post-SB-35 P1 re-baseline as the comparison ceiling — re-baseline is mandatory in Unit 5 pre-smoke, not conditional on "if SB-35 lands."
- **Atomic Habits pre-P1 local data does not exist.** Document-review verified this: `data/scrum275_local_smoke*/` contains only the Python fixture. The plan's Atomic Habits diagnostic was reframed as a 2-way comparison (post-SB-35 P1 re-baseline vs P2 winning-config), not the original 3-way. Do not attempt to reconstruct a pre-P1 Atomic Habits local score — the data is gone.
- **Hybrid grader is a choice at marginal R2 pass, not a blanket rejection.** If the winning variant clears R2 marginally (|Δ| within 2 points of gate), surface hybrid as an explicit user choice before locking in the marginal prompt hack. The Risks table has this as a row; take it seriously.
- **Two-pass sub-unit 4b-ii IS a VisionProvider Protocol change.** The plan acknowledges this; the implementer must choose between (a) widening `build_request(..., variant: Literal[...])` or (b) adding `build_request_scoring(...)` as a new Protocol method. Either choice requires a Protocol-contract test. Do not pretend two-pass is "just orchestration" — `tools/llm_providers/base.py` must be updated and the change is surface-area.

**Options considered and rejected:**

- **Qwen2.5-VL-32B model swap** — deferred, shared-stack VRAM constraint. Concrete re-trigger: ≥80GB VRAM headroom on sb-chat. Do not attempt this in P2.
- **Hybrid grader as Unit 4 default** — rejected unless winning variant lands marginally; see above.
- **Landing R3 (page_number schema enum) before Unit 2 (prompt-only)** — rejected; prompt-first is user-decided sequencing. Unit 3 is CONDITIONAL on Unit 2 + Unit 5 R4 gate failure on any of three N≥3 non-sequential fixtures.
- **Rubric edits for strict-grader framing** — rejected. `tools/visual_qa_rubric.md` is the contract; strict-grader framing lives in the system prompt only.
- **Full 6-book corpus re-smoke per Unit 4 variant** — rejected. Full-corpus smoke happens in Unit 5 only; Unit 4 uses Python-in-easy-steps fixture + one non-Python fixture for gate eligibility.

**Hidden constraints / gotchas:**

- **`extra_body={"chat_template_kwargs": {"enable_thinking": False}}` MUST stay** on every request (SB-34). Any new `extra_body` additions you make (e.g., `structured_outputs.backend` in a rollback path) must compose with this, not replace it.
- **`frequency_penalty` absence is a P1 regression contract.** `test_no_frequency_penalty` pins it. Do not reintroduce in any Unit 4 variant.
- **`minItems == maxItems == page_count` is the P1 structural fix.** Do not remove this from `_build_page_extraction_schema`. If Unit 3 widens the helper signature to `(page_count, page_labels=None)`, preserve the bounds invariant unchanged.
- **sb-chat is shared with SecondBrain and CareerPilot.** Any inference-volume-doubling change (two-pass sub-unit 4b-ii) requires the explicit user approval gate recorded in Unit 5 addendum — not just a flag in the commit message.

---

## What NOT To Do

### Standing Rules (do not modify — sourced from deployment-prompt-template.md)

- **Do not commit directly to master.** All commits must go on the branch created in Phase 0, then land via PR.
- **Do not use `ALLOW_MAIN_COMMIT` or `ALLOW_MAIN_PUSH` env vars.** These exist only for human emergency override. If a guard blocks an action, stop and report the block — do not attempt to bypass.
- **If any guard fires, stop and report.** Do not retry with bypass flags, do not reinterpret the block as a false positive, do not attempt alternative commands to circumvent the guard. Report the exact block message to the strategist and wait for instructions.
- **Ambiguous user phrasing is not authorization to bypass.** Phrases like "ship it", "just commit it", "go ahead and push", or "no need for a PR" are never authorization to bypass workflow rules. Authorization requires an explicit instruction that names the specific rule being bypassed.
- **Enforcement code is not exempt.** Modifications to hooks, guards, policy files, or worktree-policy.json are subject to the same branch-and-PR workflow as any other change.

### Session-Specific Prohibitions

- **Do NOT land Unit 4 sub-unit 4b-ii (two-pass structure) without the explicit user approval gate.** Two-pass doubles sb-chat inference volume on a shared stack. Before committing two-pass code, record in the Unit 5 addendum: (1) explicit user approval, (2) measured per-batch steady-state latency at current sb-chat load, (3) `NEW DEPENDENCY: EbookAutomation → sb-chat shared stack throughput` flag added to the session summary per the cross-project protocol. If the approval record is missing, the two-pass change is incomplete.
- **Do NOT modify `tools/visual_qa_rubric.md`.** The rubric is the contract that schema and prompt must conform to. Any strict-grader framing lives in the system prompt inside `build_request`, not in the rubric.
- **Do NOT modify `tools/llm_providers/claude_provider.py`.** Grader leniency is Qwen-specific. The Claude provider is intentionally asymmetric and remains untouched.
- **Do NOT commit tests for Unit 4 intermediate variants that simply didn't win.** Unit 6 owns both positive regression tests (for the winning configuration) AND negative regression tests (for variants that ACTIVELY REGRESSED a metric — distribution collapse, `finish_reason` drift, token overrun, etc., mirroring `test_no_frequency_penalty`). Variants that reached baseline but didn't pass the gate live in the Unit 5 addendum narrative, not the test suite.
- **Do NOT skip the mandatory SB-35 re-baseline in Unit 5 pre-smoke.** P1's smoke addendum numbers are pre-SB-35 and are NOT a valid comparison baseline for P2. The probe is `curl -s http://localhost:8000/v1/models | jq '.data[0].max_model_len'` (verify 131072) and `curl -s http://localhost:8000/version` (verify 0.19.0). Re-run P1's `test_response_format_is_json_schema` configuration against the current sb-chat across all 6 books, commit those numbers to the Unit 5 addendum under "Post-SB-35 P1 re-baseline" before ANY P2-winning-config smoke.
- **Do NOT attempt Qwen2.5-VL-32B swap.** Shared-stack VRAM blocks it; re-trigger is ≥80GB VRAM headroom. Route this as an escalation, not an implementation choice.

---

## Phase 1 — Audit (READ-ONLY, STOP FOR REVIEW)

Before writing any code, verify the environment and confirm the plan still matches the repo state:

1. Read `tools/llm_providers/local_provider.py` end-to-end — confirm:
   - `_build_page_extraction_schema(page_count: int)` helper exists (lines ~30–191)
   - `PageCountMismatchError` and `OutputTruncatedError` classes present
   - `build_request` at ~lines 257–324 emits `--- Page N ---` text blocks before image_url blocks
   - Trailing instruction text at ~lines 284–293 (this is the Unit 2 sub-step 2a edit target)
2. Read `tools/llm_providers/base.py` — confirm `VisionProvider` Protocol signature for `build_request` matches what the plan assumes (for two-pass Protocol extension impact)
3. Read `tools/visual_qa.py:560-583` — confirm batch loop uses `provider.build_request(batch, rubric_text, model)` at one call site (line ~564) and has `except Exception as e: ... continue` for partial-result tolerance (relevant for two-pass transactional semantics if sub-unit 4b-ii triggers)
4. Read `tests/test_local_provider_phase2.py` — inventory the existing test patterns (`test_schema_*`, `test_response_format_*`, `test_trailing_instruction_*`, `test_call_raises_*`) and confirm P1 baseline passes
5. Inspect `data/scrum275_local_6book/` — confirm all 6 post-P1 book reports present (Oil Kings, Mexico Illicit, Return of the Gods, Atomic Habits, Decline of the West, Python in easy steps)
6. Inspect `data/vqa_baseline_post_274/` — confirm Claude baseline reports present for the same 6 books (this is Unit 1's Claude-side input; NOT `vqa_baseline_pre_274/`)
7. Probe sb-chat: `curl -s http://localhost:8000/v1/models | jq '.data[0].max_model_len'` — record the ceiling, note if it's 131072 (confirms document-review's SB-35 observation)
8. Run `py -3.12 tools/debug_guided_json_preflight.py` and record the backend vLLM selects (this is the "enforcement is still live" baseline before any Unit 3 schema widening)

**Success criteria:**
- P1 baseline tests pass (zero failures)
- Plan's file-path assumptions verified against current repo (no drift since plan was written)
- sb-chat is reachable and at the expected ceiling
- All 6-book corpus data present in both local and Claude baseline directories

**STOP.** Report findings before proceeding to Phase 2. If any assumption is violated (e.g., a P1 test fails, a file path has drifted, sb-chat is unreachable), report and wait — do not try to patch around it.

---

## Phase 2 — Unit 1: Mode classification harness + Step 1 evidence table

Implement per plan Unit 1 (plan lines ~184–230):
1. Create `tools/analyze_vqa_mode_classification.py` — deterministic classifier with `classify_mode(local_report, claude_report) -> ClassificationResult`; see plan for the per-page breakdown schema (explicit field names now specified)
2. Create `tests/test_vqa_mode_classifier.py` with the test scenarios enumerated in plan (test-first discipline applies — inputs are deterministic JSON fixtures)
3. Run the classifier on the 6-book corpus: `py -3.12 tools/analyze_vqa_mode_classification.py --local-dir data/scrum275_local_6book --claude-dir data/vqa_baseline_post_274 --out data/scrum280_mode_classification/classification.json`
4. Append the Step 1 addendum to the P2 plan file (NOT this prompt file) with the evidence table per plan guidance; use the three-tier threshold (≥70% / 55-69% / <55%) per the plan's updated classification

**Success criteria:**
- `data/scrum280_mode_classification/classification.json` exists and has the `mode` + `per_page` + `aggregate` fields populated
- The plan file has a new "Step 1 Addendum" section at the bottom with evidence table
- Classifier tests all pass
- Classification verdict (mode a / b / mixed / dominant-a / dominant-b) is recorded with the percentage split documented

**STOP.** Report the classification verdict before proceeding to Phase 3 — the verdict determines which Unit 4 branch is executed in Phase 5.

---

## Phase 3 — Unit 2: `page_number` grounding prompt + defensive guard

Implement per plan Unit 2 (plan lines ~231–283):

Sub-step 2a — Trailing instruction text edit to `build_request`:
1. Add the grounding clause (three required elements: marker phrase, NOT-position phrase, non-sequential example) to the trailing user-content text
2. Load-bearing inline comment citing SCRUM-280

Sub-step 2b — `PageNumberGroundingError` defensive guard:
1. New class in `local_provider.py` mirroring `PageCountMismatchError` style
2. Post-parse guard in `call()` — fires after JSON parse succeeds, before `return VisionResponse(...)`
3. Load-bearing inline comment citing the pattern_db/psm1 downstream consumers

Tests (all in `tests/test_local_provider_phase2.py`):
- Positive: grounding clause present in payload, unchanged regardless of image count
- Positive: existing `test_trailing_instruction_text_matches_claude_provider` updated (not deleted) to accommodate new clause
- Error path: `PageNumberGroundingError` fires on positional output; fires BEFORE `return VisionResponse`; does not fire on correctly-grounded output
- Integration: `PageCountMismatchError` still fires first on count mismatch; `OutputTruncatedError` still fires before JSON parse; existing P1 invariants (`test_no_frequency_penalty`, `test_enable_thinking_is_false`, `test_response_format_is_json_schema`) all stay green

**Success criteria:**
- `py -3.12 -m pytest tests/test_local_provider_phase2.py -q` passes (existing tests + new Unit 2 tests)
- `grep "PageNumberGroundingError" tools/llm_providers/local_provider.py` shows class definition AND guard invocation in `call()`
- Payload serialization shows the grounding clause in the trailing text block

**STOP.** Report test results before proceeding.

---

## Phase 4 — Unit 3: `page_number` schema enum fallback (CONDITIONAL)

Only execute this phase IF Unit 5 Phase 6 smoke shows ANY deviation in `page_number` output from the input label set on ANY of the three N≥3 verification fixtures. If Unit 2 alone passes all three fixtures in Unit 5, skip directly to Unit 6 Phase 7.

If triggered, implement per plan Unit 3 (plan lines ~284–325):
1. Widen `_build_page_extraction_schema(page_count, page_labels: list[int] | None = None)` with enum on `page_number` when labels provided
2. Thread labels from `build_request`
3. Extend `tools/debug_guided_json_preflight.py` with two new probe cases (enum-on-integer enforcement + rollback keyword exercise)
4. Re-run Unit 5 corpus smoke after Unit 3 lands

**Success criteria:**
- Schema helper tests cover `(page_count, page_labels=[...])` and `(page_count)` backward-compat
- Preflight Case A shows enum-on-integer is enforced; Case B shows rollback keyword syntax still works on vLLM 0.19.0
- Unit 5 re-smoke shows R4 exact match on all three fixtures

**STOP.** Report whether Unit 3 was triggered and the outcome.

---

## Phase 5 — Unit 4: Grader-leniency calibration (iterative)

Branch per Phase 2 classification verdict:

- **Mode (a) or dominant-a:** run Step 2a prompt ladder (5 variants, cheapest-first per plan lines ~326–390). If dominant-a fallback-b, proceed to Step 2b ladder only if Step 2a exhausts
- **Mode (b), mixed, or dominant-b:** run Step 2b architectural ladder sequentially — 4b-i (forced-enumeration prompt prepend) first, 4b-ii (two-pass) only if 4b-i fails gate AND user approval gate is met

Variant #5 (chain-of-criticism property ordering) is GATED on the property-ordering preflight — extend preflight first, run only if preflight shows ordering is honored, otherwise SKIP variant #5 entirely.

Variant #3 (score-band enum via guided_json) requires the batch_qa.py consumer enumeration + mapping-consistent threshold verification per the plan's Risks table. If winning variant is score-band, the batch_qa verification lands before the commit.

Iteration rules (per plan's updated "Iteration loop"):
- Use Python-in-easy-steps AS primary fixture AND a non-Python fixture (RotG or Atomic Habits subset) for eligibility
- One variable per iteration; stop at first variant hitting mean |Δ| < 15 on BOTH fixtures
- If two consecutive variants pass fixture and fail Unit 5 corpus gate, abandon current ladder branch, proceed to next
- Maximum 5 variants per ladder branch before escalating to hybrid grader as explicit user choice

**Success criteria:**
- One winning variant identified with fixture-level evidence captured
- Addendum to the P2 plan file records all attempted variants (even rejected), with the active-regression ones flagged for Unit 6 negative-test treatment
- If two-pass landed (sub-unit 4b-ii), the approval gate is satisfied and recorded

**STOP.** Report winning variant + all rejected variants (distinguish "didn't win" from "actively regressed") before proceeding.

---

## Phase 6 — Unit 5: 6-book corpus smoke + R2/R3/R4 gate verification

Implement per plan Unit 5 (plan lines ~391–450):

Pre-smoke (MANDATORY before any variant smoke):
1. Probe sb-chat: `/v1/models` and `/version`, record in addendum
2. Re-run P1 configuration (`test_response_format_is_json_schema` shape, no P2 variant applied) against all 6 books — these are the post-SB-35 P1 re-baseline numbers
3. Re-run `tools/debug_guided_json_preflight.py` — confirm backend enforcement live

Corpus smoke:
- Run winning Unit 4 variant + Unit 2 grounding clause + Unit 3 schema enum (if triggered) against all 6 books
- Record per-book Δ vs post-SB-35 P1 re-baseline AND vs Claude baseline
- Verify R2(a): mean |Δ| < 15; R2(b): no per-book |Δ| > 20; R3: non-degenerate distribution (at least one page < 60 where Claude flagged one); R4: exact marker match on RotG + Oil Kings + third stress fixture

If Unit 3 was triggered, also run the enum-load-bearing verification: (i) Unit 2 prompt + Unit 3 enum together, (ii) Unit 3 enum alone (prompt reverted). Document whether enum is load-bearing or cosmetic.

Atomic Habits diagnostic: record post-SB-35 P1 re-baseline Atomic Habits score vs P2-winning-config Atomic Habits score. Delta reveals whether Unit 4 touched the 95→86 drop or not.

**Success criteria:**
- Smoke addendum appended to the P2 plan file with per-book metrics table, R4 per-page match table for all three fixtures, explicit R2(a)/R2(b)/R3/R4 sign-off
- Zero `PageCountMismatchError`, zero `PageNumberGroundingError`, zero `OutputTruncatedError`, all `finish_reason == "stop"`

**STOP.** Report gate verdict (all pass / partial fail / full fail) before proceeding.

---

## Phase 7 — Unit 6: Final test coverage + load-bearing comments

Implement per plan Unit 6 (plan lines ~451–490):
1. Identify deltas between pre-P2 `local_provider.py` and winning configuration
2. Add load-bearing inline comments for each delta citing SCRUM-280 + evidence
3. Add POSITIVE regression tests for the winning configuration (P1 `test_no_frequency_penalty` style)
4. Add NEGATIVE regression tests for actively-regressed Unit 4 variants (mirrors `test_no_frequency_penalty` — pins absence of a known-bad pattern)
5. Do NOT add tests for variants that simply didn't win without actively regressing

**Success criteria:**
- `py -3.12 -m pytest tests/test_local_provider_phase2.py -q` green with all new tests + all existing tests
- `grep "SCRUM-280" tools/llm_providers/local_provider.py` shows comments on every winning-config delta

---

## Phase 8 — Verification

### Per-file verification

- **Static:** read the final diff end-to-end. Verify every change has a load-bearing comment citing SCRUM-280 + evidence. Verify no `frequency_penalty`, `tools/visual_qa_rubric.md`, or `claude_provider.py` modifications
- **Runtime:** full test suite green — `py -3.12 -m pytest tests/ -q`. Full pipeline smoke per CLAUDE.md: `python tools/test_pipeline.py --quick` green

---

## Phase 9 — Commit and Push

**STOP before committing.** Report all files to the strategist.

After approval:

1. Stage: `git add <list every created/modified file explicitly — no wildcards>`
2. Commit per plan's implementation units (separate commits for separate logical changes per Joe's CLAUDE.md):
   - Unit 1: `[SCRUM-280] feat: mode classification harness + Step 1 evidence`
   - Unit 2: `[SCRUM-280] feat: page_number grounding prompt + PageNumberGroundingError guard`
   - Unit 3 (if triggered): `[SCRUM-280] feat: page_number schema enum fallback + preflight cases`
   - Unit 4: `[SCRUM-280] feat: grader-leniency calibration — {winning variant name}`
   - Unit 5: `[SCRUM-280] docs: Unit 5 smoke addendum + R2/R3/R4 sign-off`
   - Unit 6: `[SCRUM-280] test: regression contracts for winning config + actively-regressed variants`
3. Push: `git push -u origin worktree/SCRUM-280-p2-calibration-grounding`
4. **STOP before opening PR.** Report commit hashes to the strategist.

---

## Verification Checklist

- [ ] Branch was created via `git worktree add` and all work happened in the worktree
- [ ] No commits were made to master
- [ ] No bypass env vars were used
- [ ] Phase 1 audit was completed before any file creation
- [ ] SB-35 re-baseline executed before any P2 variant smoke
- [ ] Two-pass sub-unit 4b-ii, if landed, has the explicit approval gate recorded in the Unit 5 addendum
- [ ] `tools/visual_qa_rubric.md` and `tools/llm_providers/claude_provider.py` untouched
- [ ] Negative regression tests added for actively-regressed variants; no tests for merely-didn't-win variants
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
6. **Out-of-scope findings** — Anything that warrants a follow-up ticket (e.g., evidence pointing toward a hybrid grader being the better long-term answer, or toward SCRUM-281 scope)

---

## Invocation

```
claude --model sonnet "[SCRUM-280] P2 calibration + grounding — Read prompts/SCRUM-280-p2-calibration-grounding.md and follow the instructions"
```

Or with `@path` expansion:

```
claude --model sonnet "@prompts/SCRUM-280-p2-calibration-grounding.md"
```
