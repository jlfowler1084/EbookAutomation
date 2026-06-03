# EB-367 — Running-header bleed (HTML path): investigation notes

Status: **diagnosis in progress — root cause narrowed to the chunked extraction path.**
No production code changed yet (project rule: diagnose across corpus before editing
heading/header logic). A failing characterization test exists:
`tests/test_eb367_header_bleed_html.py`.

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

## The decisive discrepancy (the real bug surface)
- DIRECT unchunked call: `extract_with_pdfminer_html(pdf, page_range=(0,60))` then
  `format_paragraphs_as_html(...)` -> **42 header paragraphs become 2** in the output.
  So SOMETHING in the format pass already removes them when run unchunked. (Mechanism not
  yet pinned — it is NOT A2 and NOT the column-path candidate stripper.)
- FULL pipeline (CLI `--mode kindle --html-extraction`): 662 > 500-page threshold triggers
  CHUNKED extraction (`_extract_chunked`, 4 x 200 pages; line ~5719). On this merged path the
  same format pass leaves **all ~310** headers.

=> The header-stripping that works on unchunked extraction FAILS on the chunked path used for
500+ page books. This is why the bug shows up specifically on large scanned books and keeps
recurring (EB-143, EB-174, EB-212, SCRUM-299 all targeted other facets).

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
