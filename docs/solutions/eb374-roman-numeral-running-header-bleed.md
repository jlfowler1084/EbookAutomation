---
title: EB-374 Roman-numeral running-header bleed (arabic-only strip gap)
type: solution
status: resolved
date: 2026-06-04
origin_ticket: EB-374
related_tickets: [EB-367, EB-370, EB-371, EB-212, EB-143, EB-174, SCRUM-299]
tags: [pipeline, extraction, running-headers, roman-numerals, a2-filter, detector, regression-guard, front-matter]
---

# EB-374 — Roman-numeral running-header bleed

EB-367 fixed running-header welds whose page number is **arabic**. Books with a
roman-numbered front matter (e.g. *On First Principles* — a ~40-page roman-numbered
scholarly introduction) still welded: `viii ON FIRST PRINCIPLES`, `XXIV ON FIRST
PRINCIPLES`. The EB-370 guard caught it (36 welds), EB-371 confirmed it was a *live*
defect (not a stale artifact), and EB-374 closed the gap.

## Root cause

`_mark_a2_running_headers` (tools/extract_tts_text.py) normalizes candidates by
stripping **arabic** page numbers (`_TRAILING_NUM`/`_LEADING_NUM` = `\d{1,4}`), and
the EB-367 welded-prefix strip also matched only `\d{1,4}`. So `viii ON FIRST
PRINCIPLES` / `xii ON FIRST PRINCIPLES` never collapsed to one candidate, never hit
the density gate, and were never marked or stripped.

## Fix

1. **Extraction** — roman-aware candidate grouping (leading/trailing) + roman
   welded-prefix strip, **symmetric to the arabic handling** and gated by the same
   `>=5 distinct pages AND >=10% density` rule. Header pattern stays case-sensitive
   (all-caps); only the roman token is case-insensitive. Strict roman grammar
   (`m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})`) anchored to a whole token.
2. **Detector** (tools/check_header_bleed.py `_classify_glue`) — a leading/trailing
   page token (arabic **or** roman) is treated as non-body, so `viii HEADER`
   classifies as a *standalone repeat*, not a misreported body weld.

## Lessons

1. **The density gate, not the token regex, is the false-positive guard.** Roman +
   ALL-CAPS adjacency is *common* corpus-wide (a pre-implementation scan found Kass 72,
   Ezekiel 28/24, Computer Systems 26 — none in the 10-baseline). Single-letter romans
   (`I`, `X`, `V`) match ordinary words/sentence starts. Recognizing roman tokens is
   only safe because marking still requires the `>=5-page / >=10%-density` running-header
   signature: **constant text with a varying leading/trailing roman token IS a running
   header; numbered lists vary their content and never group.** Mirror EB-367's gate,
   don't loosen it.

2. **Diagnosis-first across ALL books is not optional for hot-path regex changes**
   (CLAUDE.md). The cross-corpus adjacency scan *before* editing is what justified the
   approach and set the negative-guard tests. Verified with the 10-book baseline
   validator (10/10 PASS, 0 deviations, incl. EPUB) + the EB-370 detector canaries
   (35 clean unchanged, 0 new FP) — not just the targeted unit tests.

3. **Severity classification matters, not just detection.** ~30 of the 36 were
   *standalone* roman-header paragraphs, only ~2 were true mid-prose welds. The detector
   was over-reporting standalone headers as body welds; teaching it page-edge-token
   awareness keeps the guard's `weld_total` honest (see [[eb370-header-bleed-batch-guard]]).

4. **The guard → re-extract → classify → fix loop works.** EB-370 (detector) found the
   symptom on-disk; EB-371 re-extracted with current code to separate **live defect**
   (On First Principles) from **stale artifacts** (To End All Wars, Wilsonianism, which
   the current pipeline already converts clean); EB-374 fixed the live defect. A flag on
   a stale on-disk artifact is a *lead*, not a confirmed current-pipeline defect — always
   re-extract before fixing. The EB-369 read-only fix made that re-extraction safe from
   the SQLite lock-hang.

## Verification record

On First Principles 36 → 0 welds; 10-book baseline 10/10 PASS (0 deviations);
full suite 1153 passed; detector corpus re-scan 35 clean unchanged; negative guards
(varying-content roman lists, one-off roman-lookalike words). Merged PR #199 (`cfc5a35`).
On First Principles added as the roman front-matter regression anchor.
