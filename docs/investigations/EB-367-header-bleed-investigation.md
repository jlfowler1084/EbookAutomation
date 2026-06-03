# EB-367 — Running-header bleed (HTML path): investigation notes

Status: **FIXED (pending full-corpus regression sign-off).** Root cause corrected below.
Implemented in commit on branch `fix/EB-367-header-bleed`. Characterization test
`tests/test_eb367_header_bleed_html.py` goes 28 -> 0.

> CORRECTION (supersedes the "chunking-specific" hypothesis previously recorded here):
> the bug is NOT chunk-specific. The earlier direct `extract -> format` test simply
> SKIPPED the `rejoin_html_fragments()` step that the full pipeline runs before format.
> Re-running with the real order (`_mark_a2_running_headers` -> `rejoin_html_fragments`
> -> `format`) reproduces the weld identically with or without chunking. Credit: reviewer
> caught this by pointing at the STEP 1a2 / STEP 1b ordering (lines ~13070/13073) and the
> rejoin skip logic (line ~6447). Real surface: **headers are unmarked before rejoin, so
> rejoin welds them into body text; format-only stripping is too late.**

## Symptom
Full conversion of "Pilgrim People" (Lebeson, 1950; 662 pp; single-column; HTML path)
leaves the running header "PILGRIM PEOPLE [pagenum]" in the output ~310 times, often
welded into body paragraphs (e.g. `<p>PILGRIM PEOPLE ish traveler decided...` — the word
"Spanish" was split across the page break and the header spliced between "Span-" and "ish").
Second confirming book: Fruchtenbaum (Israelology) — 250 hits ("ISRAELOLOGY", "INTRODUCTION").

## Confirmed facts
1. Raw extraction (`extract_with_pdfminer_html`) produces the headers as paragraphs —
   ~42 per 60 pages, **mostly standalone** ("PILGRIM PEOPLE", "PILGRIM PEOPLE 3").
2. Every header paragraph has `_is_a2_running_header=None` and
   `_is_running_header_candidate=None`. A2 never marks them because:
   - `_mark_a2_running_headers` skips any paragraph with `len(text) < 15` (line ~6613).
     "PILGRIM PEOPLE" = 14 chars -> excluded from candidacy entirely.
   - With the page number, each full string is unique (1-2 pages) -> below the >=5-distinct-pages threshold.
3. The legacy Phase 0-0g ALL-CAPS detector (lines ~3622-4108) is in `extract_text()`
   (legacy TEXT path) only — it does NOT run on the HTML path.
4. The column-path candidate stripper (lines ~7114-7144) only processes paragraphs already
   flagged `_is_running_header_candidate` (set only on the multi-column PyMuPDF path) -> does
   not touch single-column pdfminer output.

## The real bug surface (corrected)
The variable was the **rejoin step**, not chunking:
- `extract -> format` (no rejoin): 42 header paragraphs -> 2. (This path is NOT what the
  pipeline runs; it skips rejoin, which is why the first measurement misled.)
- `extract -> _mark_a2_running_headers -> rejoin_html_fragments -> format` (the real order):
  42 -> **28 welded into body paragraphs**. Identical with or without chunking.

=> `rejoin_html_fragments` welds the running header into adjacent body text because the header
was never marked `_is_a2_running_header` (A2's 15-char floor + unique page numbers). Prior
fixes (EB-143/174/212, SCRUM-299) targeted other facets and never closed this short-ALL-CAPS,
unmarked-before-rejoin case.

## Implemented fix (PR #190)
Three coordinated changes in `tools/extract_tts_text.py`:
1. **Mark short ALL-CAPS headers before rejoin.** `_mark_a2_running_headers` admits
   candidates >=7 chars via `_is_short_allcaps_header` (every letter uppercase, >=5 letters),
   GATED on `_margin_zone` (top/bottom margin band, set at extraction from `y0_max`/`y0_min`
   vs page height). The existing >=5-distinct-pages AND >=10%-density thresholds still apply.
   The position gate is what keeps body-zone labels (EXERCISE/SUMMARY/QUESTIONS) — which can
   recur on >=10% of pages — from being marked.
2. **Rejoin skips `_is_a2_running_header` as the CURRENT paragraph**, not only as the next
   candidate, so a marked header is never the merge source.
3. **Number-required welded-prefix strip.** For headers welded into a paragraph start during
   per-page grouping, strip a confirmed all-caps pattern with a REQUIRED leading
   ("82 PILGRIM PEOPLE But ...") or trailing ("PILGRIM PEOPLE 7 clusively ...") page number.
   Requiring the number prevents stripping a legitimate sentence that opens with the title
   phrase ("PILGRIM PEOPLE should ...").

## Results
- Characterization test (`tests/test_eb367_header_bleed_html.py`, real mark->rejoin->format
  order, Pilgrim pp.1-60): **28 welded headers -> 0**.
- Full-book Pilgrim re-extraction: **310 -> ~0** (no-number within-page welds, if any, are the
  documented residual of requiring a page number in the prefix strip — accepted to avoid the
  legitimate-title-phrase false strip).
- Full 10-book baseline regression: **10 passed, 0 failed** (re-run after each prod-code change).
- SCRUM-299 A2 guards pass; new false-positive guards added (body-zone label not marked;
  no-number title-phrase not stripped).

## Regression anchor
`tests/test_eb367_header_bleed_html.py` (source PDF in `archive/`). Adding the full book to
`expected_baselines.json` was rejected as too slow for marginal coverage; the targeted
characterization + synthetic guards are the durable anchor for this class.

## Guardrails honored
- No data-dir junctions in the worktree (CLAUDE.md SCRUM-301). Ran tests against main-tree data
  via `ARCHIVE_DIR`/`OUTPUT_DIR` env overrides.
- False-positive protection: code literals, Atomic cheat-sheet, body-zone labels, and
  legitimate title-phrase sentences all verified safe; all 10 baselines green.
