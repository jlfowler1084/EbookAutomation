---
module: book_filer
tags: [classification, taxonomy, calibration, determinism, false-positive, format-tier, EB-365]
problem_type: classification-accuracy
date: 2026-06-03
---

# book_filer: format-tier demotion → strict GREEN (EB-365)

Follow-up to [EB-355 Plan 5](eb355-book-filer-classification-metadata-accuracy-2026-06-02.md).
Closes the last confident mis-shelf that kept the `-WhatIf` calibration RED-with-1.

## Problem
After Plan 5 the frozen 680-file `F:\Books` `-WhatIf` A/B run was deterministic, auto-shelf 228
(≥224 floor), trash-safety clean — but **1 confident wrong-shelf** in the 50-row spot-check:
#32 *Theological Dictionary of the New Testament* auto-shelved to *09 Technology, Science &
Reference / Reference & Encyclopedic* instead of *03 Religion*.

## Root cause (characterized against the real plan artifact, not assumed)
`dictionary` / `encyclopedia` / `handbook` / `atlas` describe a book's **form**, not its **subject**,
yet they live in the *Reference & Encyclopedic* subcategory — which sits under a *subject* section
(Technology/Science). So any "Dictionary/Encyclopedia of <unknown subject>" wrongly implies Technology.
For #32 there is **no** competing Religion signal at all: the keyword is `theology` but the title says
`theologi**cal**` (the Plan-5 word boundary correctly refuses the partial), and `testament` is not a
keyword anywhere. The lone form word `dictionary` won uncontested; `publishing` (from "Eerdmans
**Publishing**") is publisher boilerplate leaking from the filename, not a subject signal. The same
class produced two latent (unsampled) mis-shelves: *Encyclopedia of Ancient Giants* and *Encyclopedia
of Chart Patterns*.

## Fix (deterministic, structural — no LLM, no new subject keywords)
A **format-tier demotion guard**, not another keyword (avoids the EB-353 keyword treadmill):
- **Taxonomy overlay** (`books-taxonomy.json`, `taxonomy.py`): top-level `format_keywords`
  (`encyclopedia/dictionary/handbook/atlas`) + `boilerplate_keywords` (`publishing`), `version` 1→2.
  Form words **stay** in the Reference subcategory index — overlay flag, not removal — so a Reference
  shelf is still reachable when a section-09 subject co-occurs. v1 files load with empty sets.
- **Guard** (`classify.py`): on `M = name-hits ∪ title-hits`, with
  `subject_evidence = M − format_keywords − boilerplate_keywords`, demote a would-be `shelf` to
  `review` (reason `"format-only: no subject evidence"`, section/subcategory retained for audit) **iff**
  `M ∩ format_keywords ≠ ∅` **and** `subject_evidence == ∅`. Applied as a final check before any shelf
  return; scoring/boundary/title-primary/tie logic untouched. The format-hit **precondition** is what
  keeps a `publishing`-only book (no form word) shelving as today — `publishing` stays a valid keyword.
- **Wiring** (`scan.py`): `_resolve_action`'s review branch emits `facts.cls.reason or` the generic
  string, so the demotion reason reaches the manifest row.

## Why it can't regress the majority
The guard is **monotonic**: it can only move `shelf → review`, never the reverse. Any row with ≥1
subject hit, or no form-word hit, is byte-identical to before. That is why the full suite (1094 tests)
passed unchanged and the gated re-run moved **exactly** three rows.

## Outcome (gated read-only A/B, run `20260603-184428`, frozen corpus)
- Determinism **YES** (680 = 680, byte-identical projection).
- `copy` 228 → **225** (−3), `review` 406 → **409** (+3) — the three demotions are exactly
  #32 + the two encyclopedias; nothing collateral.
- Auto-shelf floor **225 ≥ 224**; trash-safety **44 rows, 0 violations**.
- 50-row spot-check **wrong_shelf == 0**, human-signed → **strict GREEN**.
- Signed verdict (with explicit floor + trash-safety fields, not bare `evaluate_calibration`):
  `data/batch_reports/book_filer_whatif/20260603-184428/run-b/calibration-verdict-signed.json`.

## Lessons
1. **Form vs. subject is a tier, not a keyword.** When a token describes a book's *form*, tagging it
   as an overlay and demoting form-only evidence beats adding/removing per-book keywords.
2. **Precondition before demotion.** Requiring a form-word hit scopes the guard to the exact bug class
   and preserves dual-use tokens (`publishing`) — verified by a dedicated precondition regression.
3. **Corpus-validated, not logic-validated.** The A/B re-run + human spot-check is the arbiter; the
   −3 diff matching the predicted three cases is the proof the rule fired on exactly its intended class.
4. **Record the machine gates in the verdict.** `evaluate_calibration()` does not encode the auto-shelf
   floor or trash-safety; the signed artifact must include them explicitly or GREEN is under-specified.

## Scope boundary
The file-moving **actuator** remains gated behind this GREEN + backup + approval + ADR-0045 (ClaudeInfra, INFRA-552). The
LLM-assisted tail + auto-`review`-rate reduction (406/680) is deferred to **EB-366** (Relates EB-365).
