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

## Next steps for the focused implementation session
1. Pin the unchunked stripper: instrument `format_paragraphs_as_html` to find which pass
   reduces 42 -> 2 on the direct call (candidate: heading classification / repeated-short-caps
   handling). Then determine why the chunked-merge defeats it (likely a per-chunk state reset,
   page-number namespace, or an ordering difference in the merged para_dicts).
2. Implement the chosen fix (owner-approved): position-based running-header detection on the
   single-column pdfminer path — mark top-margin (top ~12-15%, y0_max/page_height) short
   paragraphs that repeat across >=3 pages as `_is_running_header_candidate` at extraction
   time (mirrors the existing bottom-zone footnote detection at lines ~6250-6289, which already
   uses page_heights + y0). This routes them into the existing 7114-7144 stripper and is robust
   to chunking because it operates per-page within each chunk. Secondary: lower the A2
   number-stripped floor from 15 to ~7 chars so short titles ("PILGRIM PEOPLE"=14,
   "ISRAELOLOGY"=11, "INTRODUCTION"=12, "ATOMIC HABITS"=13) are also caught.
3. Make the characterization test chunking-aware (force chunk_size small or test via the
   chunked entry point) so it reproduces the 310, not the unchunked 2.
4. Add "Pilgrim People" (or a page subset) to `tests/expected_baselines.json` as the permanent
   anchor for "short ALL-CAPS title + running header on single-column HTML path" — the class the
   corpus currently does NOT cover.
5. Full 10-book corpus regression (`tests/validate_against_baseline.py`,
   `tools/test_pipeline.py`) with zero PASS->FAIL; preserve endnote/heading/TOC/PAGE-marker
   invariants. Re-run the full Pilgrim conversion and confirm 310 -> ~0.

## Guardrails
- Do NOT junction data dirs into the worktree (CLAUDE.md SCRUM-301 warning). Run pipeline/tests
  against the main-tree data via absolute paths or env overrides.
- False-positive protection is essential: any position/frequency change must keep Python in Easy
  Steps code literals, Atomic Habits cheat-sheet, and all current baselines green.
