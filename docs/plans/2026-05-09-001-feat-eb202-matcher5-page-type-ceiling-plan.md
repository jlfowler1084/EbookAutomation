---
title: "feat: EB-202 Matcher 5 — page-type score ceiling for DocVQA-shaped failures"
type: feat
status: active
date: 2026-05-09
origin: docs/brainstorms/2026-05-09-eb-202-docvqa-failure-detection-requirements.md
---

# feat: EB-202 Matcher 5 — page-type score ceiling for DocVQA-shaped failures

## Overview

Adds Matcher 5 to `FallbackFingerprintDetector` — a page-type score ceiling that catches
DocVQA-shaped failures: cloud VLM responses that are schema-valid, specific, and high-scoring
but confidently wrong. Oil Kings p3 (`front_matter`, score=90, Δ=56 vs Claude baseline) is
the concrete evidence case; all four existing matchers missed it.

The change is detector-only. No VisionProvider protocol changes, no routing logic changes.

## Problem Frame

The existing `FallbackFingerprintDetector` catches MMMU-shaped failures (empty issues, boilerplate
phrases, stuck uniform scores). It cannot catch DocVQA-shaped failures because those responses pass
every structural check — they have real-looking issues and high scores.

The insight: for certain page types (`front_matter`), a score > 80 with no moderate or higher
severity issue is implausible given the rubric. That combination is the ceiling signal.
(See origin: `docs/brainstorms/2026-05-09-eb-202-docvqa-failure-detection-requirements.md`)

## Requirements Trace

- R1. Matcher 5 flags `front_matter` pages where score > ceiling AND no moderate/major/critical issues
- R2. Runs as final pass after matchers 1–4; OR-combines with flagged set
- R3. Ceiling threshold configurable (default 80); severity condition fixed in v1
- R4. DEBUG log on fire: page number, page type, score, reason `"page_type_ceiling"`
- R5. `config/settings.json → visual_qa.fallback.page_type_ceilings: {"front_matter": 80}`
- R6. `FingerprintSettings` gains `page_type_ceilings: dict[str, int]` defaulting to `{}`
- R7–R9. Unit tests in `tests/test_fingerprint_detector.py` (flagged, false-positive guard, backward compat)
- R10. Frozen regression fixture in `tests/test_visual_qa_hybrid_routing.py TestRegressionContract`

## Scope Boundaries

- `front_matter` page type only in v1
- Severity condition (no moderate/major/critical) is not configurable in v1
- No changes to `visual_qa.py` routing logic, `run_claude_fallback()`, or VisionProvider protocol
- No Option B (cross-book outlier stats) or Option C (stratified sampler)

### Deferred to Separate Tasks

- Extending `page_type_ceilings` to `cover`, `toc`, `back_matter` — pending evidence of same failure pattern

## Context & Research

### Relevant Code and Patterns

- `tools/llm_providers/fingerprint_detector.py` — `FingerprintSettings` dataclass (lines 30–57),
  `detect()` method structure (lines 117–228); Matcher 4 (lines 193–219) is the direct precedent
- `tools/visual_qa.py` — config-to-`FingerprintSettings` wiring: `main()` config-loading block
  (~lines 1169–1179), `run_visual_qa()` signature (~line 735), `FingerprintSettings(...)` construction
  (~lines 969–979), and `main()` → `run_visual_qa()` call (~lines 1336–1354)
- `tests/test_fingerprint_detector.py` — `_make_page()` / `_make_issue()` helpers; `SETTINGS_UNIFORM_ONLY`
  shows how to build a settings object that isolates one matcher
- `tests/test_visual_qa_hybrid_routing.py` — `TestRegressionContract` (line 701): module-level frozen
  fixture dicts, `_make_detector_with_real_corpus()` helper, `test_fixture_*` naming convention
- `config/settings.json` — `visual_qa.fallback` block (lines 89–97); Matcher 4 keys are the precedent

### Institutional Learnings

- `docs/solutions/scrum-281-fallback-fingerprint-routing.md` — primary reference: failure-mode taxonomy
  (MMMU vs DocVQA), regression fixture discipline (provenance comments, same commit as tune), integration
  seam documentation (merge into `all_pages_results` by `page_number`)
- `docs/solutions/scrum-280-local-vqa-calibration-patterns.md` — page-type ceiling design rationale,
  why response-level detection over page-type routing; `field(default_factory=...)` gotcha documented

### External References

None needed — local patterns are sufficient; all 4 existing matchers are direct precedents.

## Key Technical Decisions

- **Matcher 5 placement: after Matcher 4, before the final `if flagged: logger.debug(...)` block.**
  Matcher 3 has an early return (line 162) that skips matchers 1–4 when all pages are empty-issues.
  That case cannot produce a DocVQA-shaped failure (DocVQA pages have non-empty issues), so placement
  after Matcher 4 is safe. If Matcher 3 already flagged everything, Matcher 5 is a no-op.

- **`field(default_factory=dict)` for `page_type_ceilings`.** Frozen dataclasses cannot use a raw
  `{}` default — Python raises `ValueError` at class-definition time. `default_factory=dict` defers
  construction per-instance. Requires adding `field` to `from dataclasses import dataclass, field`.
  New field must be positioned after all existing defaulted fields.

- **Severity check: `severity not in {"moderate", "critical"}`.** The canonical severity enum in
  the structured-output schema (`local_provider.py`) is `{"critical", "moderate", "minor"}` — three
  values, no `"major"`. The agent `contract.md` lists `"major"` as well, but it does not appear in
  any emitted output observed in the corpus. Using `{"moderate", "critical"}` covers all schema-valid
  high-severity values. `"major"` may be included defensively if desired, but the plan treats
  `{"moderate", "critical"}` as the minimal correct set. A page with no issues (empty list) vacuously
  passes the condition — ceiling still fires (correct: an empty-issue front_matter page at score > 80
  is also suspicious, and already a candidate for Matcher 1).

- **Config wiring: four changes in `visual_qa.py`, plus fixing the existing call-site gap.**
  Research confirmed that `default_fallback_threshold` (and all three Matcher 4 uniform-score vars)
  are read in `main()` but never forwarded to `run_visual_qa()` at the call site (~lines 1336–1354).
  Unit 2 must close this gap for all missing kwargs (including `fallback_empty_issues_score_threshold`,
  `fallback_match_uniform_score_responses`, `fallback_uniform_score_page_ratio`,
  `fallback_uniform_score_min_pages`) as part of the same change, so that `page_type_ceilings` does
  not introduce a fifth orphaned variable. The four new wiring points for `page_type_ceilings` are:
  (1) `main()` reads `fallback_cfg.get("page_type_ceilings", {})`, (2) assigns to
  `default_fallback_page_type_ceilings`, (3) `run_visual_qa()` signature gains `fallback_page_type_ceilings={}`,
  (4) passes `page_type_ceilings=fallback_page_type_ceilings` to `FingerprintSettings(...)`.

## Open Questions

### Resolved During Planning

- **Frozen dataclass + dict default**: use `field(default_factory=dict)` (see Key Technical Decisions)
- **Severity enum**: `{"moderate", "critical"}` are the canonical high-severity values per the
  structured-output schema. Matcher 5 flags pages that LACK these — i.e., all issues are `minor`
  or the list is empty. `"major"` is not in the schema enum but may be included defensively.
- **Matcher 3 early-return conflict**: placement after Matcher 4 is safe (see Key Technical Decisions)

### Deferred to Implementation

- **Oil Kings p3 artifact provenance**: synthetic reconstruction is acceptable. Use
  `page_type="front_matter"`, `score=90`, `issues=[{"category": "text_integrity", "severity": "minor",
  "description": "Front matter text is clean.", "suggestion": "Review page."}]` as the representative
  shape. Add a provenance comment citing EB-202 / SCRUM-281 Oil Kings p3 (Δ=56).
- **`fallback_empty_issues_score_threshold` wiring gap**: research found this kwarg may be read in
  `main()` but missing from the `run_visual_qa()` call. Verify against current code before wiring
  `page_type_ceilings` — use the same pattern as whichever kwargs *are* correctly threaded through.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation
> specification. The implementing agent should treat it as context, not code to reproduce.*

**Matcher 5 firing decision table:**

| `page_type` in `page_type_ceilings` | `score > ceiling` | Has moderate/major/critical issue | Matcher 5 fires? |
|---|---|---|---|
| No | any | any | **No** — type not in config map |
| Yes | No | any | **No** — score within ceiling |
| Yes | Yes | Yes | **No** — high-severity issue present |
| Yes | Yes | No | **Yes** — flag page, log debug |

**Interaction with Matcher 3 early-return:**

| Condition | Matcher 3 result | Matcher 5 behavior |
|---|---|---|
| All pages `issues==[]`, any score ≥ threshold | Early return, all pages flagged | Does not run |
| Some pages have issues (DocVQA case) | Matcher 3 does not fire | Runs as final pass |

## Implementation Units

- [ ] **Unit 1: Add Matcher 5 to `FingerprintSettings` and `detect()`**

**Goal:** Extend the detector with the page-type ceiling logic and its `FingerprintSettings` field.

**Requirements:** R1, R2, R3, R4, R6

**Dependencies:** None

**Files:**
- Modify: `tools/llm_providers/fingerprint_detector.py`
- Test: `tests/test_fingerprint_detector.py`

**Approach:**
- Extend `from dataclasses import dataclass` to also import `field`
- Add `page_type_ceilings: dict[str, int] = field(default_factory=dict)` as the last field in
  `FingerprintSettings` (after `uniform_score_min_pages: int = 3`)
- In `detect()`, after the Matcher 4 block and before the final `if flagged: logger.debug(...)` log,
  add the Matcher 5 loop: iterate `valid_pages`, check `page_type` in `settings.page_type_ceilings`,
  compare `score > ceiling`, verify no issue has `severity in {"moderate", "major", "critical"}`,
  add to `flagged`, log at DEBUG with reason `"page_type_ceiling"`
- Skip already-flagged pages for efficiency (same pattern as Matcher 2 check `if pn in flagged`)

**Execution note:** Test-first — write the R7 failing test before adding Matcher 5 to `detect()`.

**Patterns to follow:**
- `FingerprintSettings.match_uniform_score_responses: bool = True` — model for a new defaulted field
- Matcher 4 block (lines 193–219) — structural model for the new matcher block
- `SETTINGS_UNIFORM_ONLY` in `tests/test_fingerprint_detector.py` — model for an isolated-matcher
  settings object for new tests

**Test scenarios:**
- Happy path: `front_matter`, score=90, all issues `minor` → flagged (Oil Kings p3 shape, R7)
- Happy path: `front_matter`, score=90, `issues=[]` (empty) → also flagged (vacuous severity condition)
- No false positive: `front_matter`, score=90, one issue `moderate` → NOT flagged (R8)
- No false positive: `front_matter`, score=90, one issue `critical` → NOT flagged
- No false positive: `body` page, score=90, all issues `minor` → NOT flagged (type not in ceiling map)
- Edge case: `front_matter`, score exactly at ceiling (80) → NOT flagged (ceiling is strictly `>`,
  not `>=`; note that Matchers 1 and 3 use `>=` threshold — Matcher 5 intentionally uses `>`)
- Edge case: `front_matter`, score=81, all minor → flagged (first value strictly above ceiling)
- Edge case: empty `page_type_ceilings` dict → Matcher 5 does not fire (backward compat, R9)
- Edge case: `FingerprintSettings` constructed without `page_type_ceilings` kwarg → uses `{}`, no fire (R9)
- Composition: Matcher 5 adds to set without replacing Matcher 1/2/4 results; OR-combined correctly
- Integration: `page_number=None` pages skipped gracefully

**Verification:**
- `py -3.12 -m pytest tests/test_fingerprint_detector.py -v` — all existing tests green, new tests pass
- Isolated `SETTINGS_MATCHER5_ONLY` fixture (ceilings set, all other matchers disabled) exercises
  Matcher 5 independently without interference from other matchers

---

- [ ] **Unit 2: Wire `page_type_ceilings` through config and `visual_qa.py`**

**Goal:** Thread the new config key from `settings.json` through `main()` and `run_visual_qa()` into
`FingerprintSettings`, so the ceiling is active in production runs.

**Requirements:** R5, R3 (configurable default)

**Dependencies:** Unit 1 (FingerprintSettings field must exist)

**Files:**
- Modify: `config/settings.json`
- Modify: `tools/visual_qa.py`

**Approach:**
- `config/settings.json`: add `"page_type_ceilings": {"front_matter": 80}` to the
  `visual_qa.fallback` block (alongside existing `empty_issues_score_threshold`, `corpus_path`, etc.)
- **First**: audit the `main()` → `run_visual_qa()` call site and close the confirmed gap — add any
  of `fallback_empty_issues_score_threshold`, `fallback_match_uniform_score_responses`,
  `fallback_uniform_score_page_ratio`, `fallback_uniform_score_min_pages` that are read in `main()`
  but missing from the call. This is a prerequisite before adding `page_type_ceilings`.
- `config/settings.json`: add `"page_type_ceilings": {"front_matter": 80}` to the `visual_qa.fallback` block
- `tools/visual_qa.py` — four wiring changes for `page_type_ceilings`:
  1. `main()` config-loading: `default_fallback_page_type_ceilings = fallback_cfg.get("page_type_ceilings", {})`
  2. `run_visual_qa()` signature: add `fallback_page_type_ceilings={}` parameter (plain `= {}` default
     is correct for function parameters; `field(default_factory=dict)` is only for `@dataclass` fields)
  3. `FingerprintSettings(...)` construction: add `page_type_ceilings=fallback_page_type_ceilings`
  4. `main()` → `run_visual_qa()` call: pass `fallback_page_type_ceilings=default_fallback_page_type_ceilings`

**Patterns to follow:**
- Matcher 4 wiring: `match_uniform_score_responses`, `uniform_score_page_ratio`, `uniform_score_min_pages`
  in `config/settings.json` and their `fallback_cfg.get(...)` / `run_visual_qa()` / `FingerprintSettings`
  wiring in `visual_qa.py`

**Test scenarios:**
- Required: add an assertion to `TestConfigRoundTrip` that `page_type_ceilings` is correctly
  threaded from config through to `FingerprintSettings`. The existing `TestConfigRoundTrip` does
  not assert any Matcher 4 kwargs (confirmed gap) — it cannot detect a missing kwarg at the call
  site. This addition is mandatory, not conditional, to verify Unit 2's wiring is complete.
- Edge case: `page_type_ceilings` absent from config → `fallback_cfg.get("page_type_ceilings", {})` 
  returns `{}` → Matcher 5 disabled (assert through the mandatory config round-trip test addition)

**Verification:**
- `py -3.12 -m pytest tests/test_visual_qa_hybrid_routing.py::TestConfigRoundTrip -v` — all green
- Manual spot-check: `python tools/visual_qa.py --help` exits cleanly (no import errors from new param)

---

- [ ] **Unit 3: Add frozen regression fixture for DocVQA-shaped failure to `TestRegressionContract`**

**Goal:** Lock the Matcher 5 routing behavior with a corpus-derived frozen fixture so future changes
to the ceiling thresholds or severity condition must explicitly update this assertion.

**Requirements:** R10

**Dependencies:** Unit 1, Unit 2

**Files:**
- Modify: `tests/test_visual_qa_hybrid_routing.py`

**Approach:**
- Add module-level frozen fixture `_OIL_KINGS_P3_DOCVQA` representing the Oil Kings p3 candidate
  response shape: `page_type="front_matter"`, `score=90`, `issues=[...]` with one `minor` severity
  `text_integrity` issue. Add a provenance comment: `# Oil Kings p3 (EB-202 / SCRUM-281 corpus smoke,`
  `# DocVQA-shaped, Δ=56 vs Claude baseline); synthetic reconstruction matching known shape`
- Add a complementary batch `_OIL_KINGS_P3_MIXED_BATCH` pairing p3 with a `body` page at score=90
  with minor issues (should NOT be flagged by Matcher 5)
- In `TestRegressionContract`, add `test_fixture4_oil_kings_p3_docvqa_flagged_by_matcher5()`:
  construct settings with Matcher 5 enabled (`page_type_ceilings={"front_matter": 80}`), all other
  matchers disabled; assert `flagged == {3}` (the p3 page number)
- Add `test_fixture5_body_page_high_score_minor_issues_not_flagged()`: same settings; assert `body`
  page with score=90 and minor issues is NOT in `flagged`
- Use `_make_detector_with_real_corpus()` helper (already present) and extend `FingerprintSettings`
  call to include `page_type_ceilings={"front_matter": 80}`

**Patterns to follow:**
- `_OIL_KINGS_A3B_PAGE_119` fixture and `test_fixture2_*` in `TestRegressionContract` (lines 657–678,
  and the test method below line 728) — exact pattern to mirror
- `SETTINGS_UNIFORM_ONLY` pattern in `tests/test_fingerprint_detector.py` — for isolating one matcher

**Test scenarios:**
- Regression fixture: `_OIL_KINGS_P3_DOCVQA` (front_matter, score=90, minor issues) → flagged by
  Matcher 5 when ceiling enabled (R10)
- Negative regression: `body` page at score=90 with minor issues → NOT flagged (ceiling only covers
  `front_matter` in v1)
- Composition guard: run `_OIL_KINGS_P3_DOCVQA` through full default settings (all matchers on,
  `page_type_ceilings={"front_matter": 80}` explicitly set) — assert it is still flagged. Note:
  `_make_detector_with_real_corpus()` constructs `FingerprintSettings` without `page_type_ceilings`;
  this test must construct its own settings with the ceiling enabled to exercise Matcher 5 in context

**Verification:**
- `py -3.12 -m pytest tests/test_visual_qa_hybrid_routing.py::TestRegressionContract -v` — all green
- Full test run: `py -3.12 -m pytest tests/test_fingerprint_detector.py tests/test_visual_qa_hybrid_routing.py -v` — 0 failures

## System-Wide Impact

- **Interaction graph:** `FallbackFingerprintDetector.detect()` is called only from `run_visual_qa()`
  in `tools/visual_qa.py`. No callbacks, no observers, no middleware. Impact is contained.
- **Error propagation:** Matcher 5 reads page dicts defensively (uses `.get()` throughout). A missing
  `severity` key defaults to the absence of the severity string — treated as non-high-severity, so
  the ceiling may fire. Implementation should handle missing `severity` explicitly (treat as `minor`).
- **State lifecycle risks:** No state written; `detect()` is pure read → set. No cleanup needed.
- **API surface parity:** `FingerprintSettings` is imported in `tests/test_fingerprint_detector.py`
  and `tests/test_visual_qa_hybrid_routing.py`. Both are in-repo test files; no external consumers.
- **Integration coverage:** The `TestRegressionContract` fixture (Unit 3) plus the full-matchers
  composition test in Unit 1 cover the cross-layer scenario: ceiling fires in context of a real
  detector with the real corpus loaded.
- **Unchanged invariants:** Matchers 1–4 behavior is unchanged. All existing `TestRegressionContract`
  fixtures must remain passing unchanged — Matcher 5 is additive and must not alter their assertions.
  The `visual_qa.py` routing logic (which pages go to Claude, how results merge) is untouched.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Matcher 5 fires on `body` pages with minor issues (false positive at scale) | Ceiling map is `front_matter`-only; `body` pages are never in the map. Unit tests guard this. |
| `field(default_factory=dict)` omitted → `ValueError` at import | Unit 1 is test-first; import error would surface immediately on first test run. |
| `run_visual_qa()` wiring gap leaves `page_type_ceilings` always `{}` in prod | Unit 2 verification step: `TestConfigRoundTrip` must exercise the new kwarg. |
| Frozen fixture synthetic data drifts from real artifact | Provenance comment names EB-202/SCRUM-281; changing the shape requires deliberate fixture update. |
| `critical` severity missing from `local_provider.py` JSON schema but present in `contract.md` | Check `{"moderate", "major", "critical"}` exhaustively; no branch is taken for missing severity. |

## Documentation / Operational Notes

- No CLAUDE.md or README changes needed — this is an internal detector extension.
- `tools/visual_qa_fallback_fingerprints.json` is unchanged — Matcher 5 does not use the fingerprint
  corpus; it uses the config-driven `page_type_ceilings` map.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-05-09-eb-202-docvqa-failure-detection-requirements.md](docs/brainstorms/2026-05-09-eb-202-docvqa-failure-detection-requirements.md)
- Related code: `tools/llm_providers/fingerprint_detector.py`, `tools/visual_qa.py`
- Related institutional learnings: `docs/solutions/scrum-281-fallback-fingerprint-routing.md`,
  `docs/solutions/scrum-280-local-vqa-calibration-patterns.md`
- Related issues: EB-202, SCRUM-281, SCRUM-292
