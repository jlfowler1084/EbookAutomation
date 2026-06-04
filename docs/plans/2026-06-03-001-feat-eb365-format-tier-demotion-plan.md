---
title: "feat(EB-365): book_filer format-tier demotion → strict GREEN (deterministic)"
type: feat
status: complete
date: 2026-06-03
origin: docs/brainstorms/2026-06-03-eb365-format-tier-demotion-requirements.md
---

# feat(EB-365): book_filer format-tier demotion → strict GREEN (deterministic)

> **COMPLETE (2026-06-03).** Units 1–5 done. Code committed `dece0bd`. Gated A/B run
> `20260603-184428` reached **strict GREEN**: determinism YES, wrong_shelf==0 (human-signed),
> auto_shelf 225≥224, trash-safety 0 violations. Exactly 3 format-only demotions (#32 + 2
> encyclopedias). Signed verdict: `data/batch_reports/book_filer_whatif/20260603-184428/run-b/
> calibration-verdict-signed.json`. Compound: `docs/solutions/eb365-book-filer-format-tier-demotion-2026-06-03.md`.

## Overview

Close the `book_filer` `#32`-class confident mis-shelf with a deterministic, structural rule:
**form words** (`dictionary`/`encyclopedia`/`handbook`/`atlas`) describe a book's *form*, not its
*subject*, so a file whose entire keyword evidence is form-tier + publisher boilerplate (with no
subject-tier keyword) is routed to `review` instead of being auto-shelved. Then re-run the read-only
`-WhatIf` two-run A/B to a **strict GREEN** verdict. No LLM; no new per-book keywords. This story
gates the (separate, later) file-moving actuator.

## Problem Frame

The last A/B run (`20260602-212244`) was **RED-with-1**: deterministic, auto-shelf 228 (≥224 floor),
trash-safety clean, but one confident wrong-shelf — spot-check `#32` *Theological Dictionary of the
New Testament* → *09 Technology/Reference* instead of *03 Religion*. Verified against the prior run's
plan artifact: `#32`'s only matched keywords are `dictionary` (form word) + `publishing` (publisher
boilerplate from the filename); no Religion keyword matches at all (`theology`≠`theologi**cal**` on
word boundary; `testament` is not a keyword). The lone form word wins uncontested. The same class
produced two other (unsampled) Reference shelves — *Encyclopedia of Ancient Giants*, *Encyclopedia of
Chart Patterns*. (See origin: `docs/brainstorms/2026-06-03-eb365-format-tier-demotion-requirements.md` §1.1.)

## Requirements Trace

- **R1** — A file whose evidence is entirely format-tier + boilerplate (≥1 form-word hit, zero
  subject-tier hits) routes to `review` with an auditable reason; never auto-shelf. (origin §3)
- **R2** — Any file with ≥1 subject-tier hit, or with no form-word hit, classifies **exactly as
  today** (zero regression for the majority). (origin §3)
- **R3** — A `publishing`-only file (boilerplate, no form word) is **not** demoted — `publishing`
  stays a valid classifier keyword. (origin §3, §4.1)
- **R4** — Determinism preserved: run A == run B, byte-identical `canonical-projection.txt`. (origin §5)
- **R5** — Strict GREEN on the frozen corpus: determinism ∧ `wrong_shelf == 0` (human spot-check) ∧
  `auto_shelf_count(copy+hardlink) ≥ 224` ∧ non-empty signer ∧ trash-safety 0 violations. (origin §2, §7.2)

## Scope Boundaries

- No LLM-assisted classification.
- No new subject keywords (`testament`, broadened `theolog*`) — declined as keyword treadmill (EB-353).
- No change to scoring math, boundary matching, title-primary logic, tie/threshold logic, dedup,
  fragments, or trash-safety.
- No writes to `F:\Books` — the actuator stays gated.

### Deferred to Separate Tasks

- LLM-assisted classification tail + auto-`review`-rate reduction (406/680): **EB-366** (Relates EB-365).
- File-moving actuator: separate ce:plan after GREEN, behind backup + clean GREEN + approval + ADR-0045 (ClaudeInfra, INFRA-552).

## Context & Research

### Relevant Code and Patterns

- `tools/book_filer/classify.py` — `classify_name`, `_score_text` (hit-count `Counter[(section,sub)]`,
  line ~62), `_classification_from_scores`, `Classification` dataclass, `_keyword_matches`,
  `_strip_source_boilerplate`, `_SOURCE_BOILERPLATE_PHRASES`.
- `tools/book_filer/taxonomy.py` — `load_taxonomy`, frozen `Taxonomy` dataclass with `_index`;
  mirror the existing top-level `non_library_keywords` parse for the new overlay sets.
- `config/books-taxonomy.json` — `version`, `non_library_keywords` (the pattern to follow), the
  *09 / Reference & Encyclopedic* subcategory (`encyclopedia`/`dictionary`/`handbook`/`atlas`).
- `tools/book_filer/scan.py` — single classify call site (~L413, defensively wrapped); review-reason
  emission in `_resolve_action` (~L562); `classification_source`/`taxonomy_version` already plumbed
  into `ManifestRow`.
- `tools/book_filer/calibration.py` — `evaluate_calibration` (determinism ∧ wrong_shelf ∧ size ∧ signer).
- Tests mirror: `tests/test_book_filer_classify.py`, `tests/test_book_filer_scan.py` (Plans 2–5 TDD style).

### Institutional Learnings

- `docs/solutions/eb355-book-filer-classification-metadata-accuracy-2026-06-02.md` — lesson #1 (short
  substrings are false-positive surfaces), #4 (corpus-validated, not logic-validated — every rule is a
  new false-positive surface; the `-WhatIf` re-run + spot-check is the arbiter), #5 (deterministic
  classifier has a ceiling; precedence cases are documented LLM-tail scope — but a *structural* rule is
  not whack-a-mole), #6 (make the gate measurable; GREEN is gameable by routing all to review, so pair
  zero-wrong-shelf with an auto-shelf floor).

### External References

- None required — strong local patterns (Plans 3–5). No external contract surface beyond the existing
  taxonomy JSON schema.

## Key Technical Decisions

- **Overlay flag, not removal** — form words stay in *Reference & Encyclopedic*; a top-level
  `format_keywords` set marks them as form-tier. A Reference shelf is still reachable when a section-09
  subject co-occurs. (origin §4.1)
- **Format-hit precondition** — the guard fires only when `M ∩ format_keywords ≠ ∅` **and**
  `subject_evidence == ∅`. Without the precondition a `publishing`-only book would be wrongly demoted
  (R3). This scopes the guard to exactly the "form-word of <no-subject>" class.
- **`subject_evidence = M − format_keywords − boilerplate_keywords`** — `boilerplate_keywords` (init
  `{publishing}`) excludes publisher boilerplate from counting as subject evidence, but only for the
  guard's test, not for scoring.
- **Taxonomy `version` 1 → 2** — a rule change must be attributable per-row via `taxonomy_version`.
- **Demotion = `review`, section/subcategory retained** — review is always gate-safe (`wrong_shelf`
  counts only `disposition=="shelf"`); keeping the would-be target aids audit.

## Open Questions

### Resolved During Planning

- Where does the guard live? → In `classify.py`, after scoring and the existing non-library / tie /
  threshold logic, as a final check before any `shelf` return; applied on the union of name-hits ∪
  title-hits.
- How is matched-keyword identity recovered? → `_score_text` (or a sibling helper) must also return the
  set of matched keywords; counts/ranking unchanged.
- Floor risk? → Prior-run artifact: only 3 Reference auto-shelves; worst case 228→225 ≥ 224. The gated
  A/B run is the authoritative measurement.

### Deferred to Implementation

- Exact helper name/signature for matched-keyword accounting (e.g. `_collect_matches`) — resolve when
  touching `classify.py`.
- Whether the boilerplate set needs members beyond `publishing` — only add if the gated run surfaces a
  second boilerplate token; do not pre-expand (treadmill).
- Final `feature-manifest.json` diff — depends on actual exported-symbol changes.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation
> specification. The implementing agent should treat it as context, not code to reproduce.*

Demotion guard as a decision matrix (evaluated on `M = name-hits ∪ title-hits`):

| Matched evidence `M` | `M ∩ format` | `subject_evidence` | Result |
|---|---|---|---|
| `{dictionary, publishing}` (#32) | non-empty | ∅ | **demote → review** |
| `{encyclopedia}` (Ancient Giants / Chart Patterns) | non-empty | ∅ | **demote → review** |
| `{python, handbook}` | non-empty | `{python}` | classify as today (shelf) |
| `{publishing}` (no form word) | ∅ | ∅ | classify as today (R3) |
| `{}` (nothing matched) | ∅ | ∅ | already `review` (unchanged) |

where `subject_evidence = M − format_keywords − boilerplate_keywords`.

## Implementation Units

- [x] **Unit 1: Taxonomy overlay — `format_keywords` + `boilerplate_keywords` + version bump**

**Goal:** Express the format and boilerplate tiers in config and load them onto `Taxonomy`.

**Requirements:** R1, R3

**Dependencies:** None

**Files:**
- Modify: `config/books-taxonomy.json`
- Modify: `tools/book_filer/taxonomy.py`
- Test: `tests/test_book_filer_taxonomy.py` (create if absent; else extend)

**Approach:**
- Add top-level `"format_keywords": ["encyclopedia","dictionary","handbook","atlas"]` and
  `"boilerplate_keywords": ["publishing"]`; bump `"version": 1 → 2`. Form words remain in the
  *Reference & Encyclopedic* subcategory (overlay, not removal).
- Parse both into `frozenset[str]` fields on `Taxonomy`, lowercased/normalized consistently with the
  index. Absent keys default to empty frozensets (back-compat with a v1 file).

**Patterns to follow:** the existing `non_library_keywords` parse in `load_taxonomy`.

**Test scenarios:**
- Happy path: a v2 taxonomy loads `format_keywords` and `boilerplate_keywords` as the expected frozensets.
- Edge case: a taxonomy file lacking both keys loads with empty frozensets and does not raise.
- Happy path: `version` reads as `2`; form words remain present in the Reference subcategory index.

**Verification:** loader exposes both sets; existing taxonomy tests still pass.

- [x] **Unit 2: Classifier demotion guard + matched-keyword accounting + `Classification.reason`**

**Goal:** Route format-only files to `review`; carry an auditable reason; preserve all current behavior otherwise.

**Requirements:** R1, R2, R3, R4

**Dependencies:** Unit 1

**Files:**
- Modify: `tools/book_filer/classify.py`
- Test: `tests/test_book_filer_classify.py`

**Approach:**
- Add a helper (e.g. `_collect_matches`) — or extend `_score_text` — to return matched keyword
  identities alongside the score `Counter`. Counts and the deterministic `(-hits, section, sub)`
  ranking are unchanged.
- Add `reason: str | None = None` to `Classification`.
- After scoring and the existing non-library / tie / threshold logic, apply the guard as a final check
  before any `shelf` return, on `M = name-hits ∪ title-hits`: if `M ∩ format_keywords ≠ ∅` and
  `M − format_keywords − boilerplate_keywords == ∅`, return
  `Classification("review", section, subcategory, confidence, source, reason="format-only: no subject evidence")`.
- No change to boundary matching, title-primary scoring, source-boilerplate stripping, or tie→review.

**Execution note:** Test-first — start with the pinned `#32` failing test, then the precondition and
no-regression cases, then implement the guard.

**Patterns to follow:** `_classification_from_scores` return shape; Plan-5 TDD cases in
`tests/test_book_filer_classify.py`.

**Test scenarios:**
- Happy path (pinned #32): title "Theological Dictionary of the New Testament" + a filename carrying
  `…Publishing…` → `disposition=="review"`, `reason=="format-only: no subject evidence"`,
  section/subcategory retained.
- Happy path: bare "Encyclopedia of <non-keyword subject>" / "Atlas of <non-keyword>" → `review`.
- Edge case (precondition / R3): a title whose only match is `publishing` (no form word) → classifies
  as today, **not** demoted.
- Edge case (R2 co-occurrence): "Python … Handbook" (subject + form) → still `shelf`.
- Edge case (R2): a sample of pure-subject titles classify identically to pre-change output.
- Edge case: format word present but a subject keyword in another section also matches → not demoted
  (subject_evidence non-empty); existing title-vs-name conflict routing unchanged.
- Determinism (R4): repeated classification of the same inputs is identical (no set-iteration leakage
  into the result).

**Verification:** #32 and siblings route to `review`; co-occurrence and pure-subject cases unchanged;
full classify test module green.

- [x] **Unit 3: Wire the demotion reason through `scan.py`**

**Goal:** Surface `Classification.reason` on the manifest/spot-check for demoted rows.

**Requirements:** R1

**Dependencies:** Unit 2

**Files:**
- Modify: `tools/book_filer/scan.py`
- Test: `tests/test_book_filer_scan.py`

**Approach:**
- In `_resolve_action`'s review branch (~L562), emit `facts.cls.reason or
  "low-confidence/ambiguous classification"` instead of the hard-coded generic string. The classify
  call site (~L413) signature is unchanged; the defensive fallback `Classification("review", …)` keeps
  `reason=None` → generic string.

**Patterns to follow:** existing `_resolve_action` review/​non-library reason returns.

**Test scenarios:**
- Integration: a format-only file scanned end-to-end produces a manifest/review row whose reason is
  "format-only: no subject evidence".
- Edge case: a genuinely low-confidence file (reason `None`) still emits the generic reason (no regression).

**Verification:** demoted rows carry the format-only reason; low-confidence rows unchanged.

- [x] **Unit 4: Feature-manifest refresh + full suite + determinism guard green**

**Goal:** Keep the manifest honest and prove no regression across the book_filer suite.

**Requirements:** R2, R4

**Dependencies:** Units 1–3

**Files:**
- Modify: `feature-manifest.json` (only if exported symbols/config keys changed)
- Test: (existing) `tests/test_book_filer_*.py`, determinism self-check

**Approach:**
- Re-run `powershell -File tools/verify-manifest.ps1 -Verbose`; update manifest entries if the new
  config keys / `Classification.reason` / helper are catalogued surfaces.
- Run `python -m pytest tests/` (or the book_filer subset) — all green, including dedup/fragments/
  trash-safety (unchanged) and the existing determinism guard.

**Test scenarios:** `Test expectation: none — verification/aggregation unit; coverage lives in Units 1–3.`

**Verification:** manifest verification passes; full suite green; no dedup/trash-safety drift.

- [x] **Unit 5: Gated GREEN run (manual A/B; requires explicit "frozen + go")**

**Goal:** Re-run the read-only `-WhatIf` two-run A/B on the frozen corpus and reach strict GREEN.

**Requirements:** R4, R5

**Dependencies:** Unit 4 + explicit "frozen + go" from the maintainer

**Files:** none (read-only run; artifacts land under `data/batch_reports/book_filer_whatif/<ts>/`)

**Approach:**
- On explicit **"frozen + go"**: `PYTHONHASHSEED=0`, run `-WhatIf` twice (A/B via `--compare-to`) on
  the frozen 680-file `F:\Books`. **No writes to `F:\Books`.**
- Verify determinism YES; `auto_shelf_count ≥ 224`; trash-safety 0 violations. Regenerate the
  spot-check sheet; maintainer signs off `wrong_shelf == 0` on the **new** sample.
- Watch-item: confirm no legitimate Writing/Publishing shelf whose sole evidence is `publishing` + a
  form word demoted in a way that (combined with the 3 Reference demotions) drops the floor below 224.
- GREEN → EB-365 done; open the actuator ticket. A new mis-shelf in the fresh sample → triage as a new
  finding (likely another format-class case); do not silently re-baseline.

**Execution note:** Manual, gated verification — not code. Do not run any real-corpus scan before
explicit "frozen + go".

**Test scenarios:** `Test expectation: none — manual gated verification run, governed by the GREEN gate.`

**Verification:** a committed-or-recorded calibration verdict shows GREEN (determinism ∧ wrong_shelf==0
∧ floor≥224 ∧ signer ∧ trash-safety 0).

## System-Wide Impact

- **Interaction graph:** only the classify → `_resolve_action` → manifest path changes; the change is
  additive (a new review reason + a guard that can only move `shelf`→`review`, never the reverse).
- **Error propagation:** `classify_name` stays defensively wrapped in `scan.py`; the guard cannot
  raise on normal inputs (set algebra over already-matched keywords).
- **State lifecycle risks:** none new — no writes, no dedup/identity change. `taxonomy_version` 1→2
  changes every row's recorded version (intended; makes runs attributable) and thus the projection vs.
  prior runs (expected).
- **API surface parity:** `Classification` gains an optional field; all constructors default it, so
  existing call sites and the defensive fallback are unaffected.
- **Integration coverage:** Unit 3's end-to-end scan test proves the reason reaches the manifest —
  not provable by classify unit tests alone.
- **Unchanged invariants:** scoring math, word-boundary matching, title-primary logic, tie/threshold,
  dedup, fragments, and the trash-safety invariant are explicitly unchanged; the auto-shelf floor and
  determinism gates are preserved (and re-measured in Unit 5).

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Demotions drop the auto-shelf floor below 224 | Prior-run artifact bounds Reference demotions at 3 (228→225); Unit 5 is the authoritative re-measurement before any GREEN claim. |
| Format-hit precondition omitted → `publishing`-only books wrongly demoted | Explicit precondition `M ∩ format ≠ ∅`; Unit 2 publishing-only regression test locks it (R3). |
| Over-broad `boilerplate_keywords` regresses real Writing/Publishing shelves | Initialize with only `{publishing}`; do not pre-expand; Unit 5 watch-item flags floor impact. |
| New keyword/precedence rule introduces a fresh false-positive surface (EB-353 treadmill) | Structural rule (no new subject keywords); corpus-validated via the A/B re-run + spot-check, not logic alone (learning #4); revert any rule that regresses the labeled set. |
| New confident mis-shelf surfaces in the fresh spot-check sample | Human sign-off on the new sample is the gate; triage as a new finding rather than re-baselining. |

## Documentation / Operational Notes

- On GREEN, compound a short addendum (or update the EB-355 solution doc) noting the format-tier rule
  and the corrected #32 root cause; transition EB-365 via the `ship` skill.
- `F:\Books` remains read-only; no rollout/monitoring surface in this story.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-06-03-eb365-format-tier-demotion-requirements.md](../brainstorms/2026-06-03-eb365-format-tier-demotion-requirements.md)
- Related code: `tools/book_filer/classify.py`, `tools/book_filer/taxonomy.py`, `tools/book_filer/scan.py`, `config/books-taxonomy.json`
- Compound: `docs/solutions/eb355-book-filer-classification-metadata-accuracy-2026-06-02.md`
- Plan 5: `docs/plans/2026-06-02-001-feat-eb355-plan5-classification-metadata-accuracy-plan.md`
- Jira: EB-365 (this story); EB-366 (deferred LLM tail + review-rate); epic EB-354; PR #189 (`f4c9367`)
- Prior runs (durable subset committed `9f3ccad`): `data/batch_reports/book_filer_whatif/{20260602-182319,20260602-212244}/run-b/`
