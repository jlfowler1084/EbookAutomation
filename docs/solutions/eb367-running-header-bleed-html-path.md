---
title: EB-367 Running-header bleed on the HTML extraction path
type: solution
status: resolved
date: 2026-06-03
origin_ticket: EB-367
related_tickets: [EB-143, EB-174, EB-212, SCRUM-299]
tags: [pipeline, extraction, running-headers, rejoin, a2-filter, position-guard, testing, kfx]
---

# EB-367 — Running-header bleed on the single-column HTML path

Running headers like `PILGRIM PEOPLE 73` were welded into body paragraphs (sometimes
mid-word: `...Span-` + `PILGRIM PEOPLE` + `ish traveler...`) on the single-column
pdfminer HTML path. Full conversion of *Pilgrim People* (Lebeson, 1950; 662 pp) left
**310** header occurrences; confirmed on a second book (Fruchtenbaum, `ISRAELOLOGY` /
`INTRODUCTION`). This is the 5th encounter with running-header bleed (after EB-143,
EB-174, EB-212, SCRUM-299), each of which closed a different facet.

## TL;DR

1. **Root cause: unmarked-before-rejoin.** The headers were never marked
   `_is_a2_running_header` (the A2 filter skips `len(text) < 15`; `PILGRIM PEOPLE` = 14,
   and per-page numbers make each full string unique, so the frequency threshold is never
   met). `rejoin_html_fragments()` then welds the unmarked header into adjacent body text.
   Format-time stripping runs too late to remove text already embedded in a paragraph.
2. **The fix is marking + rejoin-skip + a guarded prefix strip — not a new detector.**
   - `_mark_a2_running_headers` admits short ALL-CAPS candidates (>=7 chars), **gated on
     `_margin_zone`** (top/bottom margin band, computed at extraction from `y0_max`/`y0_min`
     vs page height). The >=5-page / >=10%-density thresholds still apply.
   - `rejoin_html_fragments` skips `_is_a2_running_header` as the **current** paragraph, not
     only as the next merge candidate.
   - A confirmed all-caps header welded into a paragraph start (per-page grouping weld) is
     stripped, with a **required** leading or trailing page number.
3. Result: Pilgrim **310 body welds -> 0**; full 10-book baseline regression 10/10.

## Two lessons worth compounding

### Lesson 1 — Characterization tests must replay the real preprocessing order ("rejoin-aware testing")

The first diagnosis was **wrong**: it concluded the bug was "chunking-specific" (large
books >500 pp use `_extract_chunked`). That conclusion came from a test that called
`extract_with_pdfminer_html(...)` then `format_paragraphs_as_html(...)` **directly**,
skipping the `_mark_a2_running_headers -> rejoin_html_fragments` steps the real pipeline
runs between them (`process_kindle_html`, STEP 1a2 / STEP 1b). With rejoin skipped the
weld didn't happen (42 header paras -> 2), so the full-pipeline 310 looked like a
chunking artifact.

Running the **real order** (`mark -> rejoin -> format`) reproduced the weld identically
with or without chunking (42 -> 28 on a 60-page slice). The "variable" was the rejoin
step the test omitted, not chunking.

Takeaway: when characterizing a multi-stage pipeline bug, the test must replay the actual
stage sequence (or call the real entry point). A shortcut that skips intermediate passes
can manufacture a false root cause. See also
`best-practices/verify-tool-dependent-hypotheses-before-shipping-diagnosis-2026-05-15.md`.

### Lesson 2 — Short repeated ALL-CAPS need position/role evidence, not just frequency

The first fix admitted short ALL-CAPS text into the A2 frequency filter using only
all-caps + the >=10%-density threshold. That false-positives on textbook labels:
`EXERCISE` / `SUMMARY` / `QUESTIONS` legitimately recur on >=10% of pages as **body**
content. Frequency cannot distinguish a running header from a recurring body label.

The distinguishing signal is **position**: a running header sits in the top/bottom margin;
a body label sits in the text block. Gating short-header admission on `_margin_zone`
(already derivable from the per-paragraph `y0_max`/`y0_min` the footnote detector uses)
closes the false-positive cleanly while still catching true headers.

Corollary on the prefix strip: it originally allowed zero digits, so it would strip a
legitimate sentence opening with the title phrase (`PILGRIM PEOPLE should...` -> `should...`).
Requiring an adjacent page number keeps numbered welds stripping while protecting prose.

## Regression coverage

`tests/test_eb367_header_bleed_html.py` (source PDF in `archive/`):
- `test_pilgrim_running_header_not_welded_into_body` — real `mark->rejoin->format` order; 0 welds.
- `test_body_zone_short_allcaps_label_not_marked` — `EXERCISE`/`SUMMARY`/`QUESTIONS` body-zone, not marked.
- `test_title_phrase_start_without_page_number_not_stripped` — no-number title phrase preserved; numbered welds stripped.

The 10-book `expected_baselines.json` corpus had **no** anchor for "short ALL-CAPS title +
running header on the single-column HTML path" — which is why this class kept recurring.
The characterization test is that anchor (adding the 662-page book to the baseline suite was
rejected as too slow for marginal coverage).

## Files

- `tools/extract_tts_text.py` — `_is_short_allcaps_header`, `_margin_zone` marking,
  `_mark_a2_running_headers` (margin-gated short admission + confirmed-header prefix strip),
  `rejoin_html_fragments` (skip marked header as current paragraph).
- Diagnosis trail: `docs/investigations/EB-367-header-bleed-investigation.md`.
