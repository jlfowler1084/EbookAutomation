---
date: 2026-05-09
topic: eb-202-docvqa-failure-detection
---

# EB-202: DocVQA-Shaped Failure Detection (Matcher 5)

## Problem Frame

The `FallbackFingerprintDetector` catches MMMU-shaped failures — cloud VLM responses that are
structurally empty, boilerplate, or uniformly stuck. It is blind to DocVQA-shaped failures:
responses that are schema-valid, specific, and high-scoring, but confidently wrong.

Evidence: Oil Kings p3 (`front_matter`) received a cloud score of 90 and a Claude baseline
score of 34 (|Δ|=56). The response included specific-looking `text_integrity` issues — none of
the four existing matchers fired. This was the single largest per-page disagreement in the
SCRUM-281 6-book corpus.

The fix is a **Matcher 5**: a page-type score ceiling that routes pages where a structurally
clean, high-confidence response is implausible given the page type and issue severity profile.

## Requirements

**Detector — Matcher 5**

- R1. Add Matcher 5 to `FallbackFingerprintDetector.detect()`: flag a page when its
  `page_type == "front_matter"`, its score exceeds the configured ceiling, and it has no
  `moderate` or `major` severity issues (i.e. all issues are `minor`, `informational`, or
  the issues list is empty).
- R2. Matcher 5 runs as a final pass after matchers 1–4 (including after Matcher 3's
  potential early return). It adds to the flag set; if Matcher 3 already flagged all pages,
  Matcher 5 is a no-op. The DocVQA failure case (has issues, all minor) is never caught
  by Matcher 3 (which requires `issues==[]`), so placement after Matcher 3 is safe.
- R3. The ceiling threshold is configurable and defaults to 80. The severity condition
  (no moderate/major issues) is not configurable in v1.
- R4. When Matcher 5 fires, log at DEBUG level with page number, page type, score, and
  the reason string `"page_type_ceiling"`.

**Configuration**

- R5. Add a `page_type_ceilings` block under `visual_qa.fallback` in `config/settings.json`.
  Initial value: `{"front_matter": 80}`. The key is a `page_type` string; the value is the
  score ceiling (exclusive upper bound).
- R6. `FingerprintSettings` gains a new field `page_type_ceilings: dict[str, int]` with a
  default of `{}` (empty dict disables Matcher 5, preserving backward compatibility).

**Tests**

- R7. At least one frozen fixture in `tests/test_fingerprint_detector.py` covering the
  Oil Kings p3 shape: `front_matter`, score=90, issues list non-empty with all severities
  `minor` or `informational` (no `moderate`/`major`) → flagged by Matcher 5.
- R8. A complementary "no false positive" fixture: `front_matter`, score=90, with at
  least one `moderate` issue → NOT flagged by Matcher 5.
- R9. A fixture confirming backward compatibility: `FingerprintSettings` constructed
  without `page_type_ceilings` (or with `{}`) → Matcher 5 does not fire.
- R10. Extend `tests/test_visual_qa_hybrid_routing.py` `TestRegressionContract` with a
  frozen DocVQA-shaped case (Oil Kings p3 candidate response) to lock the routing behavior.

## Success Criteria

- The SCRUM-281 R2 regression gate holds: corpus mean |Δ| ≤ 8.0 (baseline: 7.97). This
  ticket must not regress it.
- Oil Kings p3-class pages (`front_matter`, score > 80, no moderate/major issues) are
  flagged and re-evaluated by Claude.
- Pages that legitimately score high with only minor issues on non-`front_matter` types
  are NOT flagged by Matcher 5.
- All new tests pass; existing test suite remains green.

## Scope Boundaries

- Only `front_matter` pages in v1. `cover`, `toc`, `back_matter` deferred until evidence
  of the same failure pattern appears for those types.
- The severity condition (no moderate/major) is fixed in v1 — not configurable.
- No changes to the VisionProvider protocol, routing logic in `visual_qa.py`, or the
  batched Claude fallback call — this is detector-only.
- No Option B (cross-book outlier statistics) or Option C (stratified sampler) in this ticket.

## Key Decisions

- **Option A (page-type ceiling) over B/C**: Lowest complexity, directly grounded in the
  known failure case (Oil Kings p3), and bounded to per-page-type rules already present in
  the rubric. Options B/C deferred unless Option A misses further cases.
- **front_matter only**: The single validated evidence point is `front_matter`. Applying
  ceilings to `cover`, `toc`, etc. without evidence risks false positives.
- **Severity condition not configurable**: "No moderate/major issues" is the semantically
  correct invariant for this rule. Making it configurable adds complexity without a use case.

## Dependencies / Assumptions

- `page_type` field is already present in parsed page dicts (confirmed in `_make_page`
  helper in existing test fixtures and `detect()` docstring).
- The `FingerprintSettings` dataclass accepts new fields with defaults without breaking
  existing call sites (frozen dataclass with `field(default=...)` pattern already used for
  `match_uniform_score_responses`).

## Outstanding Questions

### Deferred to Planning

- [Affects R6][Technical] `FingerprintSettings` is a frozen dataclass. Confirm the right
  pattern for a `dict` field default (frozen dataclasses cannot use mutable defaults —
  verify `field(default_factory=dict)` works correctly here).
- [Affects R10][Needs research] Locate or reconstruct the Oil Kings p3 candidate response
  from SCRUM-281/283 artifacts. Synthetic reconstruction is explicitly acceptable — the
  fixture must match the known shape: `page_type="front_matter"`, `score=90`,
  `issues=[{"category": "text_integrity", "severity": "minor", ...}]`. The frozen fixture
  locks routing behavior, not the exact artifact provenance.

## Next Steps

-> `/ce:plan` for structured implementation planning
