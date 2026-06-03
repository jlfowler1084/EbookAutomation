---
module: book_filer
tags: [classification, taxonomy, metadata, calibration, determinism, false-positive, EB-355]
problem_type: classification-accuracy
date: 2026-06-02
---

# book_filer: title-aware word-boundary classification + metadata sanitization (EB-355 Plan 5)

First compounded solution for the `book_filer` package (Plans 1-4 were uncompounded).

## Problem
The first real-corpus `-WhatIf` run (680 files) was deterministic but calibration-RED:
4 of 16 sampled auto-`copy` rows were mis-shelved **at confidence 1.0**. The classifier
(`classify_name`) scored by **substring** match (`keyword in text`) on the **filename only**,
ignoring the embedded metadata title. Separately, raw embedded `author`/`year` flowed into
`destination_path`, so junk (`svejk, josef`; implausible years) was an apply-time naming risk.

## Root causes (verified by a Unit-1 characterization harness, not assumed)
1. **Substring matching at conf 1.0.** A single short keyword matching inside a larger word
   gives 1 hit / 1 total = 1.0 confidence — a *confident* wrong shelf. Real culprits:
   - `"eco"` ⊂ "se**co**nd" and "r**eco**vering" → Fiction (Creature from Jekyll Island; The Unseen Realm)
   - `"knowledge"` ⊂ "unac**knowledge**d" → Philosophy (Unacknowledged / Greer)
   The brainstorm's assumed culprits ("creature"/"island"/"supernatural") were **not even keywords** —
   characterizing against the real taxonomy first corrected the premise.
2. **Filename-only + publisher boilerplate.** `"publishing"` (a whole word) from
   "Random House **Publishing** Group" → Writing/Publishing (When Genius Failed). Word-boundary
   matching does NOT fix a whole-word boilerplate token.
3. **Raw metadata into naming.** `_year_from` was unbounded; no author-junk scrub.

## Fixes (deterministic-only; no LLM this pass)
- **Word-boundary matching** (`classify.py`): normalize text + keywords, match with
  `(?<![a-z0-9])phrase(?![a-z0-9])` lookarounds; deterministic `(-hits, section, sub)` ranking
  (replacing nondeterministic `Counter.most_common`). Kills the substring class generally.
- **Title-primary source-aware scoring**: `classify_name(name, taxonomy, title=None)` scores the
  embedded title as primary evidence (not equal-weight concatenation — that wouldn't let the title
  win under hit-count math); cross-section title-vs-filename conflict routes to `review`; narrow
  publisher-boilerplate stripping. `scan.py` passes `meta.title`.
- **Metadata sanitization at the source** (`metadata.py`): `_year_from` bounded to
  `[1450, current_year+1]`; `_clean_author` drops a curated fake-handle blocklist (`svejk, josef`)
  while preserving real lowercase authors (e.g. "bell hooks"). Applied in `extract_metadata` so
  `destination_path`, the `ManifestRow`, and `planned_calibre_key` all agree.

## Outcome
Re-run (read-only, frozen corpus): **confident mis-shelves 4 → 1**; auto-shelf `copy+hardlink`
**224 → 228** (held the ≥224 floor); determinism YES; trash-safety 0 violations; title-aware path
engaged on 177/680 files. Verdict: **RED-with-1** — the lone residual (#32, *Theological Dictionary
of the New Testament* → Technology/Reference, belongs in Religion) is a **keyword-precedence**
problem (generic "dictionary/reference" out-weighing "theological/new testament"), the deterministic
ceiling. Maintainer judged it good enough to land; the actuator stays gated until a clean run.

## Key lessons (reusable)
1. **Short substrings are rampant false-positive surfaces.** `"eco"` matched across the whole
   corpus. Match keywords on word boundaries, not substrings.
2. **Use the embedded title, weighted as primary** — but degrade to filename when absent and strip
   publisher/source boilerplate, which otherwise dominates cryptic libgen/Anna's-Archive names.
3. **Sanitize metadata at the source.** `author`/`year` feed naming AND `planned_calibre_key`
   (dedup/work_key). Changing them shifts dedup grouping — add a dedup/trash-safety regression.
4. **Corpus-validated, not logic-validated** (cf. EB-353): every keyword/precedence rule is a new
   false-positive surface. The read-only `-WhatIf` re-run + spot-check is the arbiter; revert any
   rule that regresses the labeled set even if it looks sound.
5. **A deterministic classifier has a ceiling.** Substring/boundary fixes are cheap and safe;
   precedence cases like #32 are the documented scope for an LLM-assisted tail (kept cached for
   determinism) — not more keyword whack-a-mole.
6. **Make the gate measurable before automating it** (#188): the spot-check sheet must emit the
   calibration vocabulary (shelf/review) or an automated ingestion false-GREENs; and "GREEN is
   gameable" by routing everything to review, so pair zero-wrong-shelf with an auto-shelf floor.

## References
- Plan: `docs/plans/2026-06-02-001-feat-eb355-plan5-classification-metadata-accuracy-plan.md`
- Requirements: `docs/brainstorms/2026-06-02-eb355-plan5-classification-metadata-accuracy-requirements.md`
- Runs: RED `data/batch_reports/book_filer_whatif/20260602-182319/` → RED-with-1 `…/20260602-212244/`
- Gate-hardening: PR #188; primitive follow-ups: EB-359 (fragments folder-blind), EB-360 (reparse fail-open)
