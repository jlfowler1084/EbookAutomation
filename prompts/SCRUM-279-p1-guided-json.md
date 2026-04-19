# SCRUM-279 P1 — vLLM guided_json schema for page-count hallucination

**Model:** SONNET
**Justification:** Structured multi-file implementation following an Opus-authored plan with document-review-incorporated design nuance. Sonnet handles structured execution well when the plan is tight.

## Tickets

- **Primary:** SCRUM-279 — Local VQA — page-count hallucination (P1) and grader leniency (P2) remediation
- **Blocks:** None
- **Relates to:** SCRUM-275 (Phase 2 local provider — shipped; 6-book smoke surfaced the two failure modes this ticket addresses)

## Estimated Scope

Narrow multi-file change: 1 provider module (`tools/llm_providers/local_provider.py`) + 1 defensive edit in `tools/visual_qa.py` (two-line `.pop()` only, no refactor) + test updates + 1 new preflight script under `tools/` — 4 implementation units.

---

## Phase 0 — Worktree Setup

**Branch:** `worktree/SCRUM-279-p1-guided-json`
**Base:** `master@7f2ff40` (the plan-promotion commit)
**Worktree Mode:** **already created** — do NOT create a new one

The worktree was created by the Opus planning session. Confirm and enter it:

1. `git worktree list` — should show `.worktrees/worktree-SCRUM-279-p1-guided-json` on `worktree/SCRUM-279-p1-guided-json`
2. `cd .worktrees/worktree-SCRUM-279-p1-guided-json`
3. Confirm branch: `git branch --show-current` → `worktree/SCRUM-279-p1-guided-json`
4. Confirm clean state: `git status` should show no modifications
5. Confirm baseline: `py -3.12 -m pytest tests/test_vision_provider_phase1.py tests/test_local_provider_phase2.py -q` → **38 passed**

If any of these fail, STOP and report. Do not attempt to "fix up" worktree state.

---

## Context

Read the full implementation plan at: `docs/plans/2026-04-18-003-feat-scrum-279-p1-guided-json-schema-plan.md`

The plan is structured so you can execute each unit in order. The points below are **what isn't obvious from the plan alone** — design decisions, rejected alternatives, and hidden constraints that came out of planning and document-review discussions. Internalize them before starting Phase 2.

**Design decisions made during planning:**

- **Use OpenAI-native `response_format: {"type": "json_schema", ...}`, not deprecated `extra_body={"guided_json": ...}`.** The former survives vLLM 0.12+ deprecation and is what the current docs lead with.
- **Do not force a backend by default.** The plan relies on vLLM 0.19.0's auto-fallback (PR #12210) from xgrammar (which doesn't support `minItems`/`maxItems`) to `guidance` or `outlines` (which do). The Unit 4 Step 1 preflight probe is the gate that triggers backend-forcing rollback if auto-fallback is broken.
- **Defer Unit 4 (page_number enum A/B) to P2.** Single-book N=2 experiments are statistically worthless and confound the Unit 4 smoke measurement. R3's AC ("decision documented either way") is satisfied by explicit deferral — P2's calibration harness is the proper venue for the A/B.
- **Add `OutputTruncatedError` alongside `PageCountMismatchError`.** `guided_json` makes the 221-entry cascade structurally impossible but creates a new leading failure mode: `max_tokens: 16384` exhausted mid-schema, surfacing as `finish_reason == "length"`. Surface it explicitly rather than letting it fall through as malformed JSON.
- **Full strict-mode schema, not just array bounds.** Under `strict: true`, vLLM masks any field not declared in the schema — silent data loss on optional fields. Unit 1 must spell out `additionalProperties: false` on every object, complete `required` lists per OpenAI strict-mode rules, and distinct shapes for `pages[].items`, `pages[].items.issues[].items`, and `top_issues[].items` (the last has an `affected_pages` field the others don't).

**Options considered and rejected:**

- **Inline Unit 4 A/B as part of P1** — rejected per adversarial review (see `docs/plans/2026-04-18-003-...` Key Technical Decisions). Single-book one-shot is underpowered; defer to P2.
- **Force `guidance` backend explicitly by default** — rejected; adds coupling to vLLM internals without observable benefit. The preflight probe gives a deterministic signal without committing to a backend.
- **Fine-tuning Qwen to fix hallucination** — deferred. The three-step sequence is: P1 structural fix (this ticket) → P2 prompt-engineering ladder → only then consider FT vs model-swap based on evidence.
- **Prompt-engineering the cardinality constraint alone** — not the primary approach here; structured decoding is the stronger fix and the parent plan signals this direction.

**Hidden constraints / gotchas:**

- **`extra_body={"chat_template_kwargs": {"enable_thinking": False}}` MUST stay.** Per SB-34, prompt-level `/no_think` fails silently against Qwen3's reasoning parser; only `enable_thinking: False` via `extra_body` disables it. Do NOT move or remove this line.
- **`max_tokens: 16384` stays.** Per SB-33, values under ~1500 emit empty content with the reasoning parser; 16384 is a truncation-headroom budget, not a typical target (normal output is 400-900 tokens).
- **The rubric (`tools/visual_qa_rubric.md`) is unstructured markdown — no parser exists.** Enum lifts must be literal equality assertions in the tests (e.g., `assert schema["...enum"] == ["cover", "toc", "front_matter", "chapter_start", "body", "back_matter"]` in the rubric's order). Don't try to parse the markdown at runtime.
- **`top_issues[]` items are a distinct shape from per-page `issues[]` items.** The former includes `affected_pages: list[int]`; the latter doesn't. Under strict mode, conflating them causes silent field masking.
- **sb-chat is on vLLM 0.19.0.** Confirmed via SecondBrain's `docs/solutions/sb-33-vllm-optimization/README.md`. PR #12210 auto-fallback is included in that version, so xgrammar's lack of `minItems`/`maxItems` support is detected and routed to `guidance`/`outlines`.
- **The 38-test provider-unit baseline is the correctness gate.** `tests/test_vision_provider_phase1.py` + `tests/test_local_provider_phase2.py`. Do NOT run `tools/test_pipeline.py` as a baseline — that's a 6-book regression test, slow; the 6-book smoke is Unit 4's own job and lives in that phase.
- **SB-35 (sb-chat `--max-model-len` 65536→131072) is queued but INTENTIONALLY NOT coupled to this ticket.** Do not wait for it. Do not attempt to coordinate with it. P1's workload is context-light (~40K max); SB-35 unblocks full-book mode (separate future ticket), not this one.

---

## What NOT To Do

### Standing Rules

- **Do not commit directly to master.** All commits must go on the branch `worktree/SCRUM-279-p1-guided-json`, then land via PR.
- **If the worktree-guard hook (configured in `.claude/worktree-policy.json`) fires, stop and report.** Do not retry with bypass flags, do not reinterpret the block, do not attempt alternative commands to circumvent. Report the exact block message and wait for instructions.
- **Ambiguous user phrasing is not authorization to bypass.** Phrases like "ship it", "just commit it", "go ahead and push" are never authorization to bypass workflow rules. Authorization requires an explicit instruction that names the specific rule being bypassed.
- **Enforcement code is not exempt.** Modifications to hooks, guards, or `.claude/worktree-policy.json` are subject to the same branch-and-PR workflow as any other change.

### Session-Specific Prohibitions

- **Don't touch `tools/llm_providers/claude_provider.py`.** Asymmetric by design — Anthropic has no guided_json equivalent and is unaffected by this hallucination.
- **Don't modify `tools/visual_qa_rubric.md`.** The contract is the contract; if drift is needed, surface it as a follow-up finding rather than fixing it inline.
- **Don't add to `feature-manifest.json`.** Tracking `tools/llm_providers/*` is a separate governance decision, out of scope for this ticket.
- **Don't refactor `parse_qa_response` in `tools/visual_qa.py`.** The edit there is a narrow, defensive two-line `.pop()` plus a colocated test — not a rewrite invitation. Anything beyond that is scope creep.
- **Don't remove `PageCountMismatchError`.** It stays as belt-and-suspenders defense even though guided_json makes it dead-code in the happy path.
- **Don't run `tools/test_pipeline.py` as a pre-commit baseline.** Use the provider-unit tests (38 tests, <1s). The 6-book smoke is Unit 4's responsibility.
- **Don't proceed past Unit 4 Step 1 preflight if it fails.** The preflight probe is a BLOCKING GATE — if the deliberately-unsatisfiable schema is silently accepted, stop and invoke the backend-forcing rollback (see plan Risks table) before any corpus smoke runs.
- **Don't force a backend by default.** The plan's design is "auto-fallback + preflight gate." Only add `extra_body.structured_outputs.backend = "guidance"` if the preflight probe trips.

---

## Phase 1 — Audit (READ-ONLY, STOP FOR REVIEW)

Read-only investigation to confirm the plan's touchpoints are as described:

1. Read `tools/llm_providers/local_provider.py` in full — verify `PageCountMismatchError` class (lines 30-48), `build_request()` structure (67-121), `call()` (127+), and the `response_format: {"type": "json_object"}` line at 117.
2. Read `tools/llm_providers/base.py` — verify the `VisionProvider` Protocol contract.
3. Read `tests/test_local_provider_phase2.py` — locate `test_no_frequency_penalty` (the style to mirror) and `test_response_format_is_json_object` (the update target). Also locate `_make_fake_completion` helper and the `PageCountMismatchError` tests (266-334).
4. Read `tools/visual_qa_rubric.md` lines 59-109 — confirm the `page_type` enum values (rubric line 59) and the full output schema shape you'll be mirroring in the helper.
5. Read `tools/visual_qa.py::parse_qa_response` (approx lines 348-413) — locate the repair-payload construction (`repair_payload = dict(original_payload)`) that Unit 2 sub-step 2c targets. Verify the edit surface is narrow.
6. Re-read `docs/plans/2026-04-18-003-feat-scrum-279-p1-guided-json-schema-plan.md` Implementation Units section — make sure the acceptance criteria for each unit are clear before starting.

**Success criteria:**
- All 6 files read; no surprises vs plan description
- `test_response_format_is_json_object` target test identified by line number in the current file
- `page_type` enum in rubric verified (6 values: `cover, toc, front_matter, chapter_start, body, back_matter`)
- `parse_qa_response` repair-payload site identified and visibly narrow (single shallow-copy line followed by a `provider.call()`)

**STOP.** Report findings — especially any discrepancy between plan description and actual code state — before proceeding.

---

## Phase 2 — Unit 1: Pure schema-builder helper

Execute Unit 1 from the plan in full. Key points:

- Add `_build_page_extraction_schema(page_count: int) -> dict` as a module-private function near the top of `tools/llm_providers/local_provider.py`, above `LocalVisionProvider`.
- Schema must cover all three distinct object shapes (`pages[].items`, `pages[].items.issues[].items`, `top_issues[].items`) with `additionalProperties: false` on every object and complete `required` lists per strict mode.
- Write all test scenarios listed under Unit 1 — including the recursive `additionalProperties: false` walk and the `top_issues[]` vs per-page `issues[]` shape distinction.

**Success criteria:**
- Helper is a pure function (no class, no state)
- Schema round-trips through `json.dumps` without error
- All Unit 1 test scenarios pass
- Full `tests/test_local_provider_phase2.py` + `tests/test_vision_provider_phase1.py` suite stays green (38+N passed, 0 failed)

**STOP.** Report the helper's signature + test count + any rubric-vs-schema mismatch discovered.

---

## Phase 3 — Unit 2: Wire schema, add `OutputTruncatedError`, strip repair-path response_format

Three sub-steps from Unit 2:

- **2a:** Replace the `response_format` dict at `local_provider.py:117` with the `json_schema` block invoking the Unit 1 helper. Leave all other payload fields unchanged. Update the adjacent comment.
- **2b:** Add `OutputTruncatedError` class (mirroring `PageCountMismatchError` style) and a `finish_reason == "stop"` check in `call()`. The check must fire BEFORE `json.loads` / count-mismatch, so truncation surfaces as its own error type.
- **2c:** In `tools/visual_qa.py::parse_qa_response`, strip `response_format` from the repair payload via `repair_payload.pop("response_format", None)` after the shallow dict copy. Two-line defensive edit — do NOT rewrite the repair flow.

Write all test scenarios listed under Unit 2, including the `finish_reason` tests (extend `_make_fake_completion` to accept a `finish_reason` kwarg) and a patch-test confirming `response_format` is absent from the constructed `repair_payload`.

**Success criteria:**
- `response_format.type == "json_schema"` asserted and passes
- `OutputTruncatedError` fires on `finish_reason == "length"` and NOT on `"stop"`
- `repair_payload` does not contain `response_format` after construction
- Full provider-unit suite green

**STOP.** Report file counts + new test count + confirm `PageCountMismatchError` tests still pass unchanged.

---

## Phase 4 — Unit 3: Test hygiene sweep

Grep `tests/test_local_provider_phase2.py` for `json_object`. Each hit is either an update target or now-redundant. Update don't delete where possible; preserve `test_no_frequency_penalty` verbatim; preserve `PageCountMismatchError` tests and `_make_fake_completion` helper unchanged.

**Success criteria:**
- `grep -n "json_object" tests/test_local_provider_phase2.py` returns no stale assertion references (comments/docstrings describing history are acceptable if clearly marked)
- Full provider-unit suite green

**STOP.** Report grep output before and after.

---

## Phase 5 — Unit 4: Backend-enforcement preflight (BLOCKING GATE) + 6-book smoke + RotG multi-seed

This phase has an **internal blocking gate**. Do not proceed past Step 1 unless the preflight probe passes.

### Step 1 — Server-enforcement preflight (BLOCKING)

Create `tools/debug_guided_json_preflight.py` — a self-contained script that:
- Constructs a deliberately-unsatisfiable JSON schema (see plan Unit 4 Step 1 for the exact shape)
- Sends a single request to sb-chat with an unrelated prompt
- Expected outcome (either is acceptable): server rejects with 4xx/5xx, OR model emits the single valid completion the schema forced
- Failure outcome: model emits any other value → xgrammar silently accepted-and-ignored the schema

If the preflight FAILS:
- **STOP.** Do not proceed to Step 2.
- Activate the backend-forcing rollback: add `extra_body.structured_outputs.backend = "guidance"` in `build_request()` and re-run the preflight.
- Report to strategist before any corpus smoke.

If the preflight PASSES:
- Record the observed backend (from sb-chat server logs per SB-33 guidance) in the smoke addendum.

### Step 2 — 6-book corpus smoke

Execute `tools/visual_qa.py --provider local` against all 6 corpus books (Oil Kings, Mexico Illicit, Return of the Gods, Atomic Habits, Decline of the West, Python in easy steps). Record per-book:
- Pages returned (expect exactly 8)
- Latency per call — separate first-request-per-batch-size from steady-state
- Input/output token counts
- Observed `finish_reason`
- Whether `PageCountMismatchError` or `OutputTruncatedError` fired

Compare against the **non-hallucinated** SCRUM-275 Phase 2 baselines from `docs/plans/2026-04-18-002-local-llm-visual-qa-calibration.md` (exclude the 10,661-token Return-of-the-Gods hallucination from baseline math).

### Step 3 — Return of the Gods multi-seed re-trigger

Run Return of the Gods 3 additional times with different random seeds or perturbed page-sample offsets. For each run:
- Confirm 8 entries returned (cardinality bounded)
- Spot-check content grounding: do the `issues[]` entries reference elements visible in the corresponding input image? Ungrounded-but-schema-valid output is a material finding.

Append results as a *Smoke Results* addendum at the end of `docs/plans/2026-04-18-003-feat-scrum-279-p1-guided-json-schema-plan.md`.

**Success criteria:**
- Preflight proved server-side enforcement is live
- All 6 books in Step 2 returned `pages: [8 items]`; zero `PageCountMismatchError`; zero `OutputTruncatedError`; `finish_reason == "stop"` every call
- Latency delta documented; flag if steady-state > 2× non-hallucinated baseline
- Step 3 multi-seed results recorded (even if null — absence of re-trigger is a finding)

**STOP.** Report full smoke addendum. Ungrounded content in Step 3 is material for P2 even if R4 technically passes — raise it.

---

## Phase 6 — Commit and Push

**STOP before committing.** Report all files to the strategist:
- `tools/llm_providers/local_provider.py` — schema helper + build_request wire + OutputTruncatedError
- `tools/visual_qa.py` — repair-payload strip
- `tests/test_local_provider_phase2.py` — test updates
- `tools/debug_guided_json_preflight.py` — preflight probe
- `docs/plans/2026-04-18-003-feat-scrum-279-p1-guided-json-schema-plan.md` — smoke addendum

After approval:

1. Stage each file explicitly by path (no `git add .` or `-A`)
2. Consider splitting into logical commits if the change naturally decomposes (e.g., schema helper + wiring as one, repair-path strip + preflight as another, test hygiene as a third). One commit per coherent logical change.
3. Commit format: `[SCRUM-279] <type>: <description>` per the project's commit convention
4. Push: `git push -u origin worktree/SCRUM-279-p1-guided-json`
5. **STOP before opening PR.** Report commit hashes and branch URL.

---

## Verification Checklist

- [ ] Phase 0 confirmed the existing worktree (did not create a new one)
- [ ] Phase 1 audit completed; no surprises vs plan
- [ ] All Unit 1 test scenarios green before Phase 3
- [ ] `OutputTruncatedError` fires on `finish_reason="length"`, not on `"stop"`
- [ ] `response_format` absent from `repair_payload` after Unit 2 edit
- [ ] Unit 4 preflight passed (or rollback applied and re-verified) BEFORE corpus smoke
- [ ] All 6 books in Step 2 smoke returned exactly 8 entries
- [ ] Return of the Gods multi-seed Step 3 findings recorded (positive or null)
- [ ] No commits to master
- [ ] No `feature-manifest.json` or `visual_qa_rubric.md` changes
- [ ] No refactor of `parse_qa_response` beyond the `.pop()` edit
- [ ] Branch pushed, PR NOT yet opened

---

## Report Structure

At each STOP gate, report back with:
1. **Findings** — What was discovered or changed
2. **Assumptions changed** — Anything that contradicts the plan or this prompt
3. **Options** — If a decision point was reached, what are the alternatives
4. **Recommendation** — Your recommended path, with rationale

At final completion, also include:
5. **Commit hashes** — For each commit made
6. **Out-of-scope findings** — Anything that warrants a follow-up ticket (especially mode-a/mode-b evidence from Step 3 that feeds P2)

---

## Invocation

```
claude --model sonnet "[SCRUM-279] vLLM guided_json P1 -- Read prompts/SCRUM-279-p1-guided-json.md and follow the instructions"
```
