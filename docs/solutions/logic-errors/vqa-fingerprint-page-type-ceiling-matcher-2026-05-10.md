---
title: VQA FallbackFingerprintDetector blind to DocVQA-shaped failures (Matcher 5 / page-type ceiling)
date: 2026-05-10
category: docs/solutions/logic-errors
module: visual_qa
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - Cloud VLM returns schema-valid, high-confidence score for a page the Claude baseline scores 56 points lower
  - FallbackFingerprintDetector fires on empty/boilerplate/stuck responses but not on plausible-looking wrong answers
  - front_matter pages score 90 from cloud provider while baseline scores 34; no fallback triggered
root_cause: logic_error
resolution_type: code_fix
tags:
  - vqa
  - fingerprint-detector
  - fallback-routing
  - page-type-ceiling
  - cloud-vlm
  - false-confidence
  - hybrid-routing
  - score-ceiling
---

# VQA FallbackFingerprintDetector blind to DocVQA-shaped failures (Matcher 5 / page-type ceiling)

## Problem

The `FallbackFingerprintDetector` had four matchers covering MMMU-shaped cloud VLM failures (empty,
boilerplate, or stuck responses) but was blind to DocVQA-shaped failures: responses that are
schema-valid, specific-looking, and high-scoring yet confidently wrong. A `front_matter` page in
Oil Kings received a cloud score of 90 against a Claude baseline of 34 (|Δ|=56) — the largest
single-page disagreement in the SCRUM-281 6-book corpus — and none of the four existing matchers
triggered, so the wrong score silently survived into the final VQA report.

## Symptoms

- Cloud VLM returns a structurally valid response with specific-sounding `text_integrity` issues
  and a high confidence score (e.g., 90) for a page type where high scores are implausible
  (e.g., `front_matter`).
- Claude fallback score for the same page is dramatically lower (e.g., 34), but the fingerprint
  detector does not flag the page for re-evaluation.
- No existing matcher fires: the response is non-empty, non-boilerplate, not stuck, and not a
  shallow pass — it just has a score that exceeds what the page type can justify.
- The disagreement silently inflates cloud accuracy for a category of failure that is qualitatively
  different from MMMU-style noise.

## What Didn't Work

**Extending Matcher 4 (book-level uniform-score):** Matcher 4 (SCRUM-292) fires when ≥75% of
pages in a book share the same integer score. Oil Kings p3 is a spatially isolated case — the
book's overall score distribution is not uniform, so Matcher 4's book-level ratio threshold never
triggers. Matcher 4 covers VLMs that get *stuck on a book*; Matcher 5 covers VLMs that are
*overconfident on a page type*. (session history)

**Option B — Cross-book outlier statistics:** Flag pages whose cloud score is a statistical outlier
relative to same-page-type scores across the full corpus. Rejected: too complex from a single
validated evidence point, and requires sufficient per-page-type sample counts for stable thresholds.

**Option C — Stratified sampler:** Sample pages by type and compare intra-stratum variance.
Rejected for the same complexity reason; deferred until multiple validated evidence points across
different page types demand a generalised solution.

**Repeated deferral of SCRUM-284:** The DocVQA failure class was identified during SCRUM-281 and
filed as SCRUM-284 with the note "one data point — needs corroboration, do not invest yet." The
ticket was passed over in the April 28 and May 8 batch sessions because it touches the cross-cutting
VQA pipeline where parallel edits have historically caused regressions. A dedicated focused session
was required. (session history)

## Solution

### 1. Add `field` import and new frozen dataclass field

`FingerprintSettings` is a `@dataclass(frozen=True)`. Python forbids a plain `{}` default for a
mutable field in a frozen dataclass; `field(default_factory=dict)` is required. The `field` import
was missing.

```python
# Before:
from dataclasses import dataclass

# After:
from dataclasses import dataclass, field

# New last field in FingerprintSettings (frozen=True):
page_type_ceilings: dict[str, int] = field(default_factory=dict)
```

### 2. Matcher 5 logic (in `FallbackFingerprintDetector.detect()`)

Inserted after the Matcher 4 block, before the final debug-log line:

```python
# Matcher 5: page-type score ceiling (DocVQA-shaped failures)
# Directional sketch — actual code uses an inverted skip-continue guard within a per-page loop.
if settings.page_type_ceilings and page_type in settings.page_type_ceilings:
    ceiling = settings.page_type_ceilings[page_type]
    if score > ceiling:   # strictly >, score==ceiling does NOT fire
        has_high_severity = any(
            issue.get("severity", "minor") in {"moderate", "critical"}
            for issue in issues
        )
        if not has_high_severity:
            flagged.add(5)
            logger.debug(
                "Page %s flagged by Matcher 5 (page_type_ceiling): "
                "page_type=%s, score=%s, ceiling=%s",
                page_num, page_type, score, ceiling,
            )
```

Key invariants:
- **`>`** not `>=` — a score exactly equal to the ceiling is not a failure signal.
- **`{"moderate", "critical"}`** — the VQA schema enum is `{critical, moderate, minor}`; there is
  no `"major"` value. Using the wrong string silently disables the guard (see EB-219 for the
  contract-doc audit).
- **`issue.get("severity", "minor")`** — the explicit `"minor"` default is load-bearing intent: a
  missing key means non-flagging. Without it, `None` also evaluates to `False` for this `in` test,
  so behaviour is identical — but in a negated guard (`not in {...}`), `None` would match
  incorrectly. Always use the explicit default when porting this pattern.
- **Empty issues list** — `any(...)` on `[]` returns `False`, so `has_high_severity=False`,
  so the ceiling fires correctly for the canonical DocVQA shape (specific-looking response with
  a clean issues list).

### 3. Default config

```json
// config/settings.json  →  visual_qa.fallback
{
  "page_type_ceilings": {
    "front_matter": 80
  }
}
```

An empty dict (`{}`) disables Matcher 5 entirely — fully backward compatible. Additional page types
can be added here as new evidence accumulates; no code changes required.

### 4. Wiring through the call chain (four points)

```python
# 1. main() reads from config:
default_fallback_page_type_ceilings = fallback_cfg.get("page_type_ceilings", {})

# 2a. Pre-existing gap closed: fallback_empty_issues_score_threshold was read from config
#     but never forwarded to run_visual_qa() — silently dropped before this PR.

# 2b. main() passes both to run_visual_qa():
run_visual_qa(
    ...,
    fallback_empty_issues_score_threshold=default_fallback_threshold,
    fallback_page_type_ceilings=default_fallback_page_type_ceilings,
)

# 3. run_visual_qa() signature adds the new kwarg:
#    (plain = {} is correct for a function parameter; only mutated if the caller never
#    modifies the argument — confirmed in this function, which passes it read-only to
#    FingerprintSettings)
def run_visual_qa(..., fallback_page_type_ceilings={}):

# 4. run_visual_qa() passes to FingerprintSettings:
settings = FingerprintSettings(
    ...,
    page_type_ceilings=fallback_page_type_ceilings,
)
```

## Why This Works

The root cause is category confusion between two distinct failure modes. MMMU-shaped failures are
structurally distinguishable from the response envelope (empty, boilerplate, stuck). DocVQA-shaped
failures are not — the response looks legitimate. The distinguishing signal is **semantic
plausibility by page type**: a `front_matter` page contains minimal evaluable content (title,
author, publisher) and cannot justify a score of 90 with a clean issues list. A cloud VLM that
returns 90 with no flagged severity on front matter is either hallucinating specificity or
miscalibrated for that page type.

Matcher 5 encodes this domain constraint directly. The "no moderate/critical issues" guard is
load-bearing — it distinguishes a legitimately troubled front-matter page (high score wrong for a
different reason) from a confidently-wrong clean-looking response. A page with a moderate or
critical issue genuinely found something worth penalising; Matcher 5 should not interfere with
legitimate re-routing decisions already made by the rubric.

Placement after Matchers 1–4 is safe by construction: Matcher 3's early return requires
`issues == []`. DocVQA-shaped pages have a non-empty issues list, so they can never trigger
Matcher 3's early exit; Matcher 5 always sees them. Matcher 5 OR-combines with the existing flag
set — if Matcher 3 already flagged all pages, Matcher 5 is a no-op.

## Prevention

**Frozen dataclass dict fields always use `field(default_factory=...)`**

```python
# Never (TypeError at class definition):
some_dict: dict[str, int] = {}

# Always:
from dataclasses import dataclass, field

some_dict: dict[str, int] = field(default_factory=dict)
```

This rule applies only to dataclass fields. Function parameters may use `= {}` as a default.

**Severity strings must match the schema enum exactly**

The VQA response schema defines `severity` as one of `{"critical", "moderate", "minor"}`. There is
no `"major"` or `"high"`. Any guard that checks severity must use only these three values. Add a
named constant or enum if the string set grows. See EB-219 for the pending contract-doc audit that
surfaced this discrepancy.

**Config-to-function wiring must be covered by a structural assertion in `TestConfigRoundTrip`**

Prior to EB-202, `TestConfigRoundTrip` had no assertions on any fallback kwargs — every prior
matcher's wiring was validated manually at PR review time. (session history) Add an assertion for
every new config key before shipping:

```python
def test_page_type_ceilings_flows_from_config_to_run_visual_qa(self):
    """Regression: prevents silent call-site wiring gaps."""
    with patch("tools.visual_qa.run_visual_qa") as mock_run:
        main(["--config", str(self.config_path), ...])
        call_kwargs = mock_run.call_args.kwargs
        self.assertIn("fallback_page_type_ceilings", call_kwargs)
        # assertIn on the key is the structural assertion — the value test belongs
        # in a separate "ceiling value is read correctly from config" test
```

**New matchers require frozen regression fixtures in `TestRegressionContract`**

Add a module-level `_FIXTURE_N` constant for every new matcher. The fixture must encode the exact
page shape that the matcher targets, verified against real evidence. Test methods must construct
`FingerprintSettings` inline (with `page_type_ceilings` explicit) rather than using
`_make_detector_with_real_corpus()`, which constructs settings without the new field:

```python
_OIL_KINGS_P3_DOCVQA = {
    # Provenance: Oil Kings p3, cloud=90, Claude baseline=34, |Δ|=56 (SCRUM-281 corpus)
    # Shape: front_matter, high score, non-empty issues all minor — canonical DocVQA-shaped failure
    "page_num": 3,
    "page_type": "front_matter",
    "score": 90,
    "issues": [{"category": "text_integrity", "severity": "minor", "detail": "..."}],
}

def test_fixture4_oil_kings_p3_docvqa_flagged_by_matcher5(self):
    # FingerprintSettings is a frozen dataclass — do NOT construct with only page_type_ceilings;
    # the constructor will TypeError on missing required fields.
    # dataclasses.replace() is the correct pattern for frozen-dataclass overrides:
    from dataclasses import replace
    settings = replace(DEFAULT_SETTINGS, page_type_ceilings={"front_matter": 80})
    flagged = self.detector.detect([self._OIL_KINGS_P3_DOCVQA], settings)
    self.assertIn(3, flagged)  # page index 3 flagged
```

**Ceiling expansion policy**

Add new page types to `page_type_ceilings` only when there is a validated evidence point (real
corpus page, known cloud vs. Claude delta, confirmed matcher miss). Do not speculatively add
`cover`, `toc`, or `back_matter` without data — a miscalibrated ceiling that fires on legitimate
pages is worse than no ceiling.

## Related Issues

- **PR #44** — `[EB-202] feat(vqa): Matcher 5 -- page-type ceiling for DocVQA-shaped failures` (merged 2026-05-10)
- **EB-219** — Pending audit of contract.md for "major" severity value not present in schema enum
- **[docs/solutions/scrum-281-fallback-fingerprint-routing.md](../scrum-281-fallback-fingerprint-routing.md)** — Direct predecessor: built Matchers 1–4 and named DocVQA-shaped detection as Residual #1; EB-202 closes that residual
- **[docs/solutions/scrum-283-cloud-vlm-evaluation.md](../scrum-283-cloud-vlm-evaluation.md)** — Upstream routing architecture that established the hybrid fingerprint-detect-then-route design
