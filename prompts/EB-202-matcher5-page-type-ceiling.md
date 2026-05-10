# EB-202 — Matcher 5: page-type score ceiling for DocVQA-shaped VQA failures

**Model:** SONNET
**Justification:** Bounded 3-unit change — one new matcher method, config plumbing, and tests.
All architectural decisions resolved during planning. No live API calls required.

## Tickets

- **Primary:** EB-202 — VQA: detect DocVQA-shaped failures beyond fingerprint coverage
- **Relates to:** SCRUM-281 (shipped matchers 1–4), SCRUM-292 (Matcher 4), SCRUM-283 (Oil Kings corpus evidence)

## Estimated Scope

Three focused units: (1) `FingerprintSettings` field + Matcher 5 logic in `fingerprint_detector.py`,
(2) config wiring in `visual_qa.py` + `settings.json` (includes closing a pre-existing call-site gap),
(3) frozen regression fixture in `TestRegressionContract`. No new files; all changes are additions to
existing files. Full suite should remain green throughout.

---

## Phase 0 — Worktree Setup

**Branch:** `feat/eb-202-matcher5-page-type-ceiling`

Before any other work:

1. `git checkout master && git pull`
2. Confirm `git log --oneline -3` shows the most recent master commit
3. Create worktree:
   `git worktree add .worktrees/feat-eb-202-matcher5-page-type-ceiling -b feat/eb-202-matcher5-page-type-ceiling master`
4. Enter worktree: `Set-Location .worktrees/feat-eb-202-matcher5-page-type-ceiling`
5. Confirm branch: `git branch --show-current` → `feat/eb-202-matcher5-page-type-ceiling`
6. Confirm baseline green:
   `py -3.12 -m pytest tests/test_fingerprint_detector.py tests/test_visual_qa_hybrid_routing.py -q`
   → zero failures

If any step fails, STOP and report. Do not proceed with a broken baseline.

---

## Context

Read the full implementation plan at:
`docs/plans/2026-05-09-001-feat-eb202-matcher5-page-type-ceiling-plan.md`

The plan is self-contained. The notes below are **what isn't obvious from the plan alone**.

### Design decisions already made (do not re-open)

- **Matcher 5 placement:** After the Matcher 4 block, before the final `if flagged: logger.debug(...)`.
  Matcher 3 has an early return (fires when ALL pages have `issues==[]`). DocVQA-shaped failures have
  non-empty issues so Matcher 3's early-return never fires on the same batch — placement after Matcher 4
  is safe. Verified during planning.

- **`field(default_factory=dict)` for the frozen dataclass field.** Python raises `ValueError` at
  class-definition time if you use a bare `{}` as a default on a `@dataclass(frozen=True)` field.
  `field(default_factory=dict)` is the correct pattern. Requires extending the import:
  `from dataclasses import dataclass, field`. Function parameters (in `run_visual_qa()`) use plain `= {}`
  — `field()` is only for dataclass fields. These are different things; do not confuse them.

- **Ceiling is strictly `>`, not `>=`.** Matchers 1 and 3 use `>=` for their threshold comparisons.
  Matcher 5 intentionally uses strictly `>` — a page at exactly the ceiling is not flagged.
  The test scenarios call this out explicitly. Do not copy-paste the Matcher 1 comparison.

- **Severity set is `{"moderate", "critical"}`.** The structured-output schema (`local_provider.py`)
  defines three severity values: `critical`, `moderate`, `minor`. There is no `major` in the schema.
  Matcher 5 fires when NO issue has severity in `{"moderate", "critical"}`. `"major"` may be included
  defensively if desired, but it is not required and does not appear in corpus outputs.

- **The call-site wiring gap is real and must be fixed.** Research confirmed that
  `default_fallback_threshold` (and the three Matcher 4 uniform-score variables) are read in `main()`
  but never passed through to `run_visual_qa()` at the call site. Unit 2 must close this gap for all
  missing kwargs before adding `page_type_ceilings`. Wire these first, then add the new kwarg.

- **`TestConfigRoundTrip` has no assertions for Matcher 4 kwargs.** The existing class does not catch
  call-site wiring gaps. Unit 2 must add an explicit assertion that `page_type_ceilings` flows from
  config through to `FingerprintSettings`. This is required, not optional.

- **The Oil Kings p3 fixture is synthetic — that's fine.** The regression fixture in Unit 3 uses a
  representative shape (`page_type="front_matter"`, `score=90`, one `minor` severity `text_integrity`
  issue), not the raw artifact. Synthetic reconstruction is the documented approach. Include a provenance
  comment: `# Oil Kings p3 (EB-202 / SCRUM-281 corpus smoke, DocVQA-shaped, Δ=56 vs Claude baseline)`

### Hidden gotchas

- When skipping already-flagged pages in Matcher 5, check `if pn in flagged: continue` before the
  ceiling logic — same pattern as Matcher 2. It's an optimization (set.add is idempotent) but keeps
  the implementation consistent with existing matchers.
- Missing `severity` key: treat defensively. If an issue dict has no `severity` key, `.get("severity")`
  returns `None`, which is not in `{"moderate", "critical"}` — Matcher 5 would fire. Consider using
  `issue.get("severity", "minor")` to make the defensive behavior explicit.
- The `_make_detector_with_real_corpus()` helper in `TestRegressionContract` constructs `FingerprintSettings`
  without `page_type_ceilings`. Unit 3 regression tests for Matcher 5 must construct their own settings
  with `page_type_ceilings={"front_matter": 80}` — do not reuse the helper as-is for Matcher 5 tests.

---

## What NOT To Do

- **Do NOT modify `run_claude_fallback()`, the VisionProvider Protocol, or routing logic in `visual_qa.py`.**
  This ticket is detector-only. No routing changes.
- **Do NOT apply ceilings to page types other than `front_matter`.** The config schema supports a dict,
  but the v1 value is `{"front_matter": 80}` only. Do not pre-populate other types speculatively.
- **Do NOT make the severity condition configurable.** `{"moderate", "critical"}` is fixed in v1.
- **Do NOT commit directly to master.** All work on the worktree branch, landed via PR.

---

## Phase 1 — Audit (READ-ONLY)

Before writing any code:

1. Read the full plan: `docs/plans/2026-05-09-001-feat-eb202-matcher5-page-type-ceiling-plan.md`
2. Read `tools/llm_providers/fingerprint_detector.py` top-to-bottom. Confirm:
   - Current `FingerprintSettings` fields and their ordering
   - Exact line where the Matcher 4 block ends
   - Exact line of the final `if flagged: logger.debug(...)` — Matcher 5 goes between these two
3. Read `tests/test_fingerprint_detector.py`:
   - `_make_page()` and `_make_issue()` helpers — you will use these in new tests
   - `SETTINGS_UNIFORM_ONLY` — model for an isolated-matcher settings object
4. Read `tests/test_visual_qa_hybrid_routing.py` lines 630–760 (`TestRegressionContract`) — note
   the module-level frozen fixture pattern and the `_make_detector_with_real_corpus()` helper
5. Read `config/settings.json` lines 82–98 (`visual_qa.fallback` block) — confirm current keys
6. Read `tools/visual_qa.py`:
   - Find `main()` config-loading block for `fallback_cfg` — note which kwargs are read
   - Find the `run_visual_qa()` call in `main()` — confirm which kwargs ARE and ARE NOT passed through
   - Find the `FingerprintSettings(...)` construction call — confirm current kwargs
7. Confirm: `from dataclasses import dataclass` is the current import (not `dataclass, field`)

**STOP.** Report:
- The exact line range of the Matcher 4 block and the line of the final debug log
- Which of the Matcher 4 kwargs (`fallback_empty_issues_score_threshold`,
  `fallback_match_uniform_score_responses`, `fallback_uniform_score_page_ratio`,
  `fallback_uniform_score_min_pages`) are missing from the `run_visual_qa()` call in `main()`
- Confirm the `from dataclasses import dataclass` import line

Wait for confirmation before proceeding to Phase 2.

---

## Phase 2 — Unit 1: `FingerprintSettings` + Matcher 5 in `detect()` (test-first)

Implement Unit 1 from the plan.

**Order of operations:**

1. Write the R7 failing test first (Oil Kings p3 shape: `front_matter`, score=90, minor issues → flagged)
   — run it and confirm it fails with `AttributeError` or `AssertionError`
2. Add `field` to the `from dataclasses import` line
3. Add `page_type_ceilings: dict[str, int] = field(default_factory=dict)` as the **last** field in
   `FingerprintSettings` (after `uniform_score_min_pages: int = 3`)
4. Add the Matcher 5 block to `detect()` — placed after Matcher 4, before the final `if flagged: logger.debug(...)`
5. Run the R7 test — confirm it now passes
6. Write remaining Unit 1 tests (R8 false-positive guard, R9 backward compat, edge cases, composition)

**All test scenarios to cover (from the plan's Unit 1):**

- `front_matter`, score=90, issues all `minor` → **flagged** (R7, Oil Kings p3 shape)
- `front_matter`, score=90, `issues=[]` (empty list) → **flagged** (vacuous severity condition)
- `front_matter`, score=90, one issue `moderate` → **NOT flagged** (R8)
- `front_matter`, score=90, one issue `critical` → **NOT flagged**
- `body` page, score=90, issues all `minor` → **NOT flagged** (type not in ceiling map)
- `front_matter`, score exactly at ceiling (80) → **NOT flagged** (strictly `>`, not `>=`)
- `front_matter`, score=81, all minor → **flagged** (first value strictly above ceiling)
- Empty `page_type_ceilings` dict → Matcher 5 does not fire (R9 backward compat)
- `FingerprintSettings` constructed without `page_type_ceilings` kwarg → uses `{}`, no fire (R9)
- Matcher 5 adds to flagged set without replacing Matcher 1/2/4 results

**Success criteria:**
- `py -3.12 -m pytest tests/test_fingerprint_detector.py -v` → all existing tests green, all new tests pass
- Verify all existing `DEFAULT_SETTINGS`/`SETTINGS_NO_COLLAPSE`/`SETTINGS_UNIFORM_ONLY` call sites
  still work without passing `page_type_ceilings` (backward compat confirmed)

**STOP.** Report: new test count, pass count, any edge-case discoveries not in the plan.
Wait for confirmation before Phase 3.

---

## Phase 3 — Unit 2: Config wiring in `visual_qa.py` + `settings.json`

Implement Unit 2 from the plan.

**Order of operations:**

1. **First, close the existing call-site gap.** In `main()`, find the `run_visual_qa()` call and add any
   of `fallback_empty_issues_score_threshold`, `fallback_match_uniform_score_responses`,
   `fallback_uniform_score_page_ratio`, `fallback_uniform_score_min_pages` that are currently missing
   from the call. Also add matching parameters with defaults to `run_visual_qa()`'s signature if absent.
2. Add `"page_type_ceilings": {"front_matter": 80}` to `config/settings.json` → `visual_qa.fallback` block
3. In `main()` config-loading: add `default_fallback_page_type_ceilings = fallback_cfg.get("page_type_ceilings", {})`
4. Add `fallback_page_type_ceilings={}` parameter to `run_visual_qa()` signature (plain `= {}`, not `field()`)
5. Add `page_type_ceilings=fallback_page_type_ceilings` to the `FingerprintSettings(...)` construction call
6. Add `fallback_page_type_ceilings=default_fallback_page_type_ceilings` to the `run_visual_qa()` call in `main()`
7. Add a required assertion to `TestConfigRoundTrip` that `page_type_ceilings` flows from config through
   to `FingerprintSettings` with the correct value

**Success criteria:**
- `py -3.12 -m pytest tests/test_visual_qa_hybrid_routing.py::TestConfigRoundTrip -v` → all green
- `py -3.12 -m pytest tests/test_fingerprint_detector.py tests/test_visual_qa_hybrid_routing.py -q` → zero failures
- `py -3.12 tools/visual_qa.py --help` exits cleanly (no import errors)

**STOP.** Report: which gap kwargs were added to the call site, config round-trip test pass count.
Wait for confirmation before Phase 4.

---

## Phase 4 — Unit 3: Frozen regression fixture in `TestRegressionContract`

Implement Unit 3 from the plan.

**Add to `tests/test_visual_qa_hybrid_routing.py`:**

1. Module-level frozen fixture (after `_BORDERLINE_BATCH`):
   ```
   _OIL_KINGS_P3_DOCVQA = {
       # Oil Kings p3 (EB-202 / SCRUM-281 corpus smoke, DocVQA-shaped, Δ=56 vs Claude baseline)
       # Synthetic reconstruction matching known shape: front_matter, score=90, minor issues only
       "page_number": 3,
       "page_type": "front_matter",
       "score": 90,
       "pass": True,
       "issues": [{"category": "text_integrity", "severity": "minor",
                   "description": "Front matter text is clean.", "suggestion": "Review page."}],
   }
   ```

2. In `TestRegressionContract`, add:
   - `test_fixture4_oil_kings_p3_docvqa_flagged_by_matcher5()`:
     Construct `FingerprintSettings` with `page_type_ceilings={"front_matter": 80}`, all other matchers
     disabled. Assert `flagged == {3}`.
   - `test_fixture5_body_page_minor_issues_not_flagged_by_matcher5()`:
     Same settings; run a `body` page at score=90 with minor issues. Assert NOT flagged.
   - `test_fixture6_oil_kings_p3_flagged_in_full_default_settings()`:
     Construct `FingerprintSettings` with ALL matchers on AND `page_type_ceilings={"front_matter": 80}`
     (do NOT use `_make_detector_with_real_corpus()` — that helper omits `page_type_ceilings`).
     Assert `3 in flagged`.

**Success criteria:**
- `py -3.12 -m pytest tests/test_visual_qa_hybrid_routing.py::TestRegressionContract -v` → all green
- Full combined run:
  `py -3.12 -m pytest tests/test_fingerprint_detector.py tests/test_visual_qa_hybrid_routing.py -v`
  → zero failures, all existing fixtures still pass

**STOP.** Report: new fixture count, full test pass count.
Wait for confirmation before Phase 5.

---

## Phase 5 — Commit and PR

After strategist confirms all phases pass:

1. Confirm full test suite clean: `py -3.12 -m pytest tests/ -q`
2. Stage specific files only:
   ```
   git add tools/llm_providers/fingerprint_detector.py
   git add tools/visual_qa.py
   git add config/settings.json
   git add tests/test_fingerprint_detector.py
   git add tests/test_visual_qa_hybrid_routing.py
   ```
3. Commit:
   ```
   git commit -m "[EB-202] feat(vqa): add Matcher 5 page-type score ceiling for DocVQA-shaped failures

   Extends FallbackFingerprintDetector with a new per-page matcher that flags
   front_matter pages where score > 80 and no moderate/critical severity issues
   are present -- the pattern observed in Oil Kings p3 (Δ=56 vs Claude baseline,
   SCRUM-281 corpus smoke). Closes the residual DocVQA-shaped failure gap left
   by Matchers 1-4.

   Also closes pre-existing call-site wiring gap in visual_qa.py main() where
   fallback kwargs were read from config but not forwarded to run_visual_qa().

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
   ```
4. Push: `git push -u origin feat/eb-202-matcher5-page-type-ceiling`
5. Open PR targeting `master`:
   - Title: `[EB-202] feat(vqa): Matcher 5 — page-type score ceiling for DocVQA-shaped failures`
   - Body should include: test count, which gap kwargs were added to the call site, a note that the
     Oil Kings p3 fixture is synthetic (shape matches SCRUM-281 corpus evidence)

**STOP before opening PR.** Report the commit hash and staged file list. Wait for strategist sign-off.

---

## Verification Checklist

- [ ] Worktree created from master; no commits to master
- [ ] Baseline test suite green before first edit
- [ ] `field` imported from `dataclasses` (not just `dataclass`)
- [ ] `page_type_ceilings` field is LAST in `FingerprintSettings` (after `uniform_score_min_pages`)
- [ ] Matcher 5 block placed AFTER Matcher 4, BEFORE the final `if flagged: logger.debug(...)`
- [ ] Ceiling uses strictly `>` (not `>=`)
- [ ] Severity set is `{"moderate", "critical"}` (not `{"moderate", "major", "critical"}`)
- [ ] `run_visual_qa()` signature uses `= {}` default (not `field(...)`)
- [ ] Call-site gap (Matcher 4 kwargs missing from `main()` → `run_visual_qa()` call) closed
- [ ] `TestConfigRoundTrip` has explicit `page_type_ceilings` assertion
- [ ] Oil Kings p3 fixture has provenance comment
- [ ] `test_fixture6` constructs its own `FingerprintSettings` with `page_type_ceilings` (not via helper)
- [ ] Full test suite green before commit

---

## Report Structure

At each STOP gate:
1. **Findings** — What was discovered or changed
2. **Assumptions changed** — Anything that contradicts the plan or this prompt
3. **Recommendation** — Your recommended path if a decision point was reached

At final completion, also include:
4. **Commit hash** and file list
5. **Out-of-scope findings** — anything warranting a follow-up ticket (e.g., `"major"` severity
   in `contract.md` vs schema, other page types that might benefit from ceilings)

---

## Invocation

```
claude --model sonnet "[EB-202] Matcher 5 page-type ceiling -- Read prompts/EB-202-matcher5-page-type-ceiling.md and follow the instructions"
```
