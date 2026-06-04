---
title: EB-370 Header-bleed batch guard (detector + batch gate + corpus sweep)
type: solution
status: resolved
date: 2026-06-04
origin_ticket: EB-370
related_tickets: [EB-367, EB-212, EB-143, EB-174, SCRUM-299, EB-149, EB-353, EB-355, EB-361]
tags: [pipeline, qa-tooling, running-headers, regression-guard, detector, batch, calibration, exit-codes, testing]
---

# EB-370 — Header-bleed batch guard

After EB-367 fixed running-header welds at the code level (Pilgrim People 310 → 0), there
was still no standing guard: nothing verified future conversions stayed clean, and nothing
audited already-converted books. EB-370 added a deterministic, **read-only** regression net
over the fix — a detector, an overnight-batch gate, and a corpus sweep.

## What was built

- **`tools/check_header_bleed.py`** — pure-function detector over the intermediate
  `_kindle.html` artifact (`output/kindle/.intermediates/<name>_kindle.html`). CLI with
  tiered exit codes `0` clean / `1` nothing-scannable / `2` flagged / `3` infra-or-usage.
- **Phase 2.5** in `tools/run_overnight_batch.ps1` — scans this-run new-KFX HTML between the
  pipeline and VQA phases; warns + flags; never blocks; folds a status accumulator into a
  final `exit`.
- **`tools/sweep_header_bleed.ps1`** — re-extracts a scoped corpus via
  `test_pipeline.run_extraction()` (never `recapture_baselines.py`) and scans it.

## Lessons (the load-bearing ones)

1. **Borrow the *gate*, not the *blind spot*.** The detector reuses the A2 filter's density
   gate (`distinct_pages >= 5 AND distinct_pages/total_pages >= 0.10`) but lowers A2's
   **15-char length floor to 6**. That 15-char floor is the literal reason A2 missed
   "PILGRIM PEOPLE" (14 chars) and the bug class existed (see [[eb367-running-header-bleed-html-path]]).
   A guard that copies a filter wholesale inherits the filter's blind spot.

2. **Detect on what the artifact actually carries.** The EB-367 *fix* discriminates headers
   by margin-zone y-coordinates, but that metadata is gone by the HTML stage. The detector
   uses only HTML-observable signals: a run of **2+ ALL-CAPS words**, page-number adjacency,
   recurrence/density, and **glue-position**. The 2+-word rule structurally excludes the
   single-word EXERCISE/SUMMARY/QUESTIONS false-positive class that plagued the fix.

3. **Glue-position classification separates a weld from a milder gap.** A `<p>` that is *only*
   the header (`<p>PILGRIM PEOPLE 73</p>`) is a different, milder issue than the header fused
   into body prose. `weld_total` counts only `glued-start | glued-end | mid-paragraph`;
   standalone repeats go to an informational bucket (per [[scrum-299-structural-widgets-as-body-content]]).

4. **Exit-code design is an interface.** Mirroring the `compare_vqa_reports.py audit` 0/1/2/3
   convention means existing automation reads this tool with no new mental model. Compute the
   code in one helper so the JSON `exit_code` field and the process return cannot disagree.
   Subclass `argparse.ArgumentParser.error()` to exit **3** — argparse's default is **2**,
   which would collide with "flagged."

5. **A cheap real-corpus scan beats a synthetic-only gate.** The execution session validated
   only against synthetic fixtures (the live re-extraction sweep was deferred over the EB-369
   SQLite-lock risk). During PR verification, pointing the detector at the **38 `_kindle.html`
   files already on disk** — zero re-extraction, no EB-369 exposure — gave the real-world
   proof the synthetic gate couldn't: **zero false positives on 35 books** (incl. code-heavy
   canaries), Pilgrim clean (fix holds), and **3 genuine welded books found** (On First
   Principles = 60 body welds, the EB-212 book; To End All Wars; Wilsonianism). The "scan
   existing HTML" mode is a free, fast first look — use it before paying for re-extraction.
   This is the [[eb353-vqa-grader-code-false-positive-2026-06-02]] "corpus is the arbiter"
   lesson applied at verification time.

6. **Stale artifact ≠ live defect.** On-disk intermediates are of unknown vintage; a flag
   means "this HTML has welds," not "the current pipeline produces welds for this book." The
   3 flagged books are leads requiring re-extraction with current code to classify (tracked
   as the EB-370 follow-up).

7. **Keep the guard off the hot path.** The detector is strictly read-only over intermediate
   artifacts; the extraction engine (`extract_tts_text.py` marking/rejoin) is untouched.
   This keeps a recurring-defect guard off the regression-cascade surface
   (per [[pre-implementation-render-check-2026-04-22]]). Confirmed: full suite 1134 passed
   with no hot-path diff.

## Verification record

Full suite 1134 passed / 7 skipped; `verify-manifest.ps1` exit 0; detector unit (36) +
calibration (determinism / zero-FP / sensitivity) green; real-corpus scan as above.
Merged PR #194 (`978dce2`).
