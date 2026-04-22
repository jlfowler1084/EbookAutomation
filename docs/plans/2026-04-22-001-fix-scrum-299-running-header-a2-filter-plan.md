---
title: SCRUM-299 Running-header A2 filter — extend pre-scan to HTML extraction path
type: fix
status: active
date: 2026-04-22
origin: docs/solutions/scrum-299-structural-widgets-as-body-content.md
---

# SCRUM-299 Running-header A2 filter — extend pre-scan to HTML extraction path

## Overview

Dionysius's source PDF produces 145 un-stripped `<p>Dionysius the Areopagite: On the Divine Names and the C.E. Rolt Mystical Theology.</p>` tags in our HTML extraction output. An existing frequency-based pre-scan in [`tools/pdf_to_balabolka.py:3262`](../../tools/pdf_to_balabolka.py#L3262) has the right length envelope (15–150 chars) and threshold (≥5 occurrences) to catch this exact pattern, but it does not appear to run on the HTML generation path that produced the Dionysius test output.

This plan scopes the fix to: confirm the root cause, extend the pre-scan's coverage to the HTML path (operating on `para_dicts` instead of the flat `paragraphs` string list), and guard against cross-corpus regressions — specifically Python's repeated code literals which would otherwise be false-positively stripped by a raw frequency filter.

## Problem Frame

See origin: `docs/solutions/scrum-299-structural-widgets-as-body-content.md` (Phase 2). Summary:

- Dionysius's 82-char mixed-case running header falls outside the Phase 0 envelope (80-char cap + ALL-CAPS regex at line 3341), and outside the column-path filter (not a `_is_running_header_candidate`).
- An OCR-path pre-scan at line 3262 already implements the correct format-agnostic frequency filter but operates on flat `paragraphs` lists, not on the `para_dicts` used by `extract_with_pdfminer_html` (line 5432) and `_extract_html_with_pymupdf_columns` (line 5015).
- Per Phase 2 evidence, our extraction produces 145 standalone `<p>header</p>` tags with zero mid-paragraph injections — the fix is filter coverage, not a complex text-ordering correction.

## Requirements Trace

- **R1.** The A2 filter strips the Dionysius running header from the extracted HTML (0 occurrences of the standalone header `<p>` in the generated intermediate). *(origin: SCRUM-299 revised acceptance criteria, item 2)*
- **R2.** Atomic Habits's 85-char repeating cheat-sheet line (`"1.1: Fill out the Habits Scorecard. Write down your current habits to become aware of"` × 4) is preserved — false-positive canary. *(origin: Phase 2 "Acceptance criteria — revised" item 3)*
- **R3.** Python in Easy Steps's repeating code literals (`window.mainloop()` × 6, `else:` × 3, etc.) are preserved — code-literal canary. *(origin: Phase 2 "Acceptance criteria — revised" item 4)*
- **R4.** Full regression suite `python tools/test_pipeline.py` passes with zero drops in existing metrics on all six corpus books. *(origin: CLAUDE.md regression rule + Phase 2 acceptance item 5)*

## Scope Boundaries

- Running-header **paragraph stripping only** — no changes to heading detection, TOC generation, bookmark reconciliation, or footnote linking (CLAUDE.md regression-sensitive boundaries).
- **No new extraction path** added. The fix extends existing filter logic.
- **No changes to `<a id="page_N"></a>` anchor emission** (B1 was superseded in Phase 2; SCRUM-299's B portion is out-of-scope entirely).
- **No changes to source-PDF quality handling** — the XEP-embedded print-edition icon widgets remain out-of-scope.

### Deferred to Separate Tasks

- **End-matter raw-HTML bleed** — tracked in [SCRUM-301](https://jlfowler1084.atlassian.net/browse/SCRUM-301). Separate mechanism, separate ticket.
- **Variant B (source-PDF icon widgets)** — Phase 2 determined this is a source-PDF artifact; no ticket needed unless we decide to add source-quality rejection in a future scope.

## Context & Research

### Relevant Code and Patterns

- [`tools/pdf_to_balabolka.py:3262-3339`](../../tools/pdf_to_balabolka.py#L3262) — existing `_prescan_fragments` logic inside `fix_ocr_artifacts`. This is the algorithm we're extending. Note: it operates on a flat `paragraphs` string list.
- [`tools/pdf_to_balabolka.py:3341-3453`](../../tools/pdf_to_balabolka.py#L3341) — Phase 0 / Phase 0b ALL-CAPS filters (the envelope gaps identified in Phase 2).
- [`tools/pdf_to_balabolka.py:6574-6604`](../../tools/pdf_to_balabolka.py#L6574) — column-path `_is_running_header_candidate` filter. Its shape is the closest template for a `para_dicts`-oriented filter: groups by normalized text, page-counts, threshold ≥3 distinct pages.
- [`tools/pdf_to_balabolka.py:5015`](../../tools/pdf_to_balabolka.py#L5015) and [`tools/pdf_to_balabolka.py:5432`](../../tools/pdf_to_balabolka.py#L5432) — HTML generation entry points that bypass `fix_ocr_artifacts`. These paths produce `para_dicts` with `page_number` on each dict (lines 5060, 5283, 5414, 5527, 5539).
- `tools/test_pipeline.py` — project regression harness. Must pass unchanged.

### Institutional Learnings

- [`docs/solutions/scrum-285-python-kfx-layout-investigation.md`](../solutions/scrum-285-python-kfx-layout-investigation.md) — related Python corpus book; its `window.mainloop()` repeats are the primary code-literal canary for R3.
- [`docs/solutions/scrum-299-structural-widgets-as-body-content.md`](../solutions/scrum-299-structural-widgets-as-body-content.md) — Phase 1 + Phase 2 diagnostic. Origin document for this plan.

### External References

Not applicable. The algorithm shape (frequency-based text filter with page-diversity threshold) has strong local patterns — no external research warranted.

## Key Technical Decisions

- **Operate on `para_dicts`, not flat strings.** The column-path filter at line 6574 is the template: iterate `para_dicts`, group by normalized text, count distinct `page_number`s, threshold. `para_dicts` carry `page_number` natively — this resolves the "page-number provenance" open question from Phase 2 cleanly for the HTML extraction paths. *(see origin: Phase 2 Open questions)*
- **Reuse the existing normalization from the OCR pre-scan** (`re.sub(r'\s+', ' ', s).strip()` + the `_nonum`/`_leadnum` variants). This keeps behavior consistent with the pre-scan that already works on the text-output path.
- **Add a code-literal exclusion.** The `para_dicts` produced by HTML paths carry structural flags (`is_code`, `is_pre`, or similar — to be confirmed during implementation). Skip paragraphs with code/pre flags from the frequency grouping so Python's `window.mainloop()` × 6 is not stripped.
- **Threshold: ≥5 distinct pages** (stricter than the column path's ≥3). Atomic Habits's 85-char cheat-sheet line appears on 4 distinct pages; a ≥5 threshold protects it explicitly, and Dionysius's 145 pages clear it by a wide margin.
- **Minimum normalized length: 15 chars.** Matches the existing OCR pre-scan. Protects very short matches (e.g., Python's `else:` at 5 chars is already below 15 and safe; `window.mainloop()` at 17 chars would need the code-literal exclusion from the previous decision).
- **Apply the filter post-extraction, pre-HTML-emission.** Modify `para_dicts` by marking flagged duplicates with a skip flag (`_is_running_header_a2 = True`) and have the HTML emitter skip flagged dicts. Mirrors the existing column-path pattern at line 6600.

## Open Questions

### Resolved During Planning

- **Page-number provenance across extraction paths at the filter boundary:** Resolved. The HTML paths (`extract_with_pdfminer_html`, `_extract_html_with_pymupdf_columns`) produce `para_dicts` with `page_number` on every dict. The flat-`paragraphs` path already has a working pre-scan; no changes there. The A2 filter operates on `para_dicts` only.
- **Which existing filter template to follow:** Resolved. The column-path `_is_running_header_candidate` pattern at line 6574 is the closest template — same data structure, same page-grouping semantics.
- **Threshold selection:** Resolved. ≥5 distinct pages, chosen specifically to protect Atomic Habits's 4-page cheat-sheet line. Trade-off documented in Risks.

### Deferred to Implementation

- **Exact name of the code/pre flag on `para_dicts`.** Implementation should `grep` for `is_code`, `is_pre`, `is_monospace`, or equivalent on the dict structure. If no such flag exists, the filter may need to inspect the text for common code-literal markers (parens, semicolons, `()` suffix) — fallback heuristic.
- **Exact integration point for the A2 filter.** Either inline in the HTML generation functions (before `<p>` emission) or as a pre-pass helper. Implementer to pick the seam that minimizes duplication between the two HTML paths.
- **Whether the text-output pre-scan at line 3262 can be refactored into a shared helper.** Out of scope for this plan; if the implementer sees a clean extraction during Unit 2, they may do it as a minor cleanup, but it's not required.

## Implementation Units

- [ ] **Unit 1: Characterize current behavior with a failing test**

**Goal:** Prove the root cause and establish a regression-preventing test before any code change.

**Requirements:** R1.

**Dependencies:** None.

**Files:**
- Create: `tests/test_scrum_299_running_header_a2.py`
- Test evidence artifact: `output/kindle/C_E_Rolt_…_test_dionysius.html` (already on disk — 145 occurrences observable)

**Approach:**
- Add a pytest test module that runs the Dionysius PDF through the HTML extraction entrypoint and asserts 0 standalone `<p>Dionysius the Areopagite: On the Divine Names and the C.E. Rolt Mystical Theology.</p>` occurrences in the output.
- Second test in the same module: assert that a known clean-canary run (Atomic Habits or a small synthetic fixture) does not regress — count of a representative non-header paragraph stays constant.
- Run the test. It should FAIL on main, confirming R1 is violated today.

**Execution note:** Test-first. Do not modify `pdf_to_balabolka.py` in this unit — Unit 1 is purely characterization.

**Patterns to follow:**
- `tests/validate_against_baseline.py` — existing regression-style test that reads a generated HTML and asserts on its content.
- Python unittest / pytest conventions used elsewhere in `tests/`.

**Test scenarios:**
- Happy path: running `extract_with_pdfminer_html` (or the main orchestrator that invokes it) on Dionysius produces HTML whose `<p>` tag count for the exact header string equals 0. *Expected to FAIL in Unit 1 (main branch state).*
- Regression canary: running the same entrypoint on Atomic Habits preserves a representative cheat-sheet line (`"1.1: Fill out the Habits Scorecard…"`). *Expected to PASS in Unit 1.*

**Verification:**
- Test file exists and imports cleanly.
- Running the Dionysius test case produces a clear assertion failure naming the 145-count.
- Running the Atomic Habits canary passes.

- [ ] **Unit 2: Extend frequency pre-scan to HTML extraction path**

**Goal:** Add a `para_dicts`-oriented frequency filter that mirrors the existing OCR pre-scan and column-path filter, and apply it before HTML `<p>` emission in both HTML extraction paths.

**Requirements:** R1, R2, R3.

**Dependencies:** Unit 1 (failing test must exist first).

**Files:**
- Modify: `tools/pdf_to_balabolka.py` (add A2 filter, wire it into the two HTML extraction paths' `<p>` emission sites)
- Test: `tests/test_scrum_299_running_header_a2.py` (the Unit 1 test now passes for R1)

**Approach:**
- Introduce a helper (preferred name-shape: `_mark_a2_running_headers(para_dicts)`) that:
  1. Iterates `para_dicts`.
  2. Skips entries flagged as code/pre (see Deferred-to-Implementation), headings, or below the 15-char minimum.
  3. Normalizes text via the same regex shapes as the OCR pre-scan (raw / trailing-num-stripped / leading-num-stripped).
  4. Groups by normalized text → set of distinct `page_number`s.
  5. For groups with ≥5 distinct pages, marks matching dicts with `_is_a2_running_header = True` (skip first occurrence if we want to preserve one; or mark all — implementer choice, documented in the PR).
- Wire call site(s): call the helper just before the `<p>` emission loop in `extract_with_pdfminer_html` and `_extract_html_with_pymupdf_columns`. In those loops, skip dicts where `_is_a2_running_header` is True — same pattern as the existing column-path skip at line 6600.
- Log the count of stripped headers (match existing log shape: `f"  A2 filter: stripped N running-header paragraphs across M normalized patterns"`).

**Patterns to follow:**
- [`tools/pdf_to_balabolka.py:6574-6604`](../../tools/pdf_to_balabolka.py#L6574) — column-path `_is_running_header_candidate` filter. Same data structure, same grouping semantics.
- [`tools/pdf_to_balabolka.py:3262-3308`](../../tools/pdf_to_balabolka.py#L3262) — OCR-path pre-scan normalization. Reuse the regex shapes.

**Test scenarios:**
- Happy path: Dionysius HTML output contains 0 `<p>Dionysius the Areopagite...</p>` occurrences after the filter.
- Regression canary (R2): Atomic Habits HTML output preserves the 4-occurrence cheat-sheet line (`"1.1: Fill out the Habits Scorecard…"`).
- Regression canary (R3): Python in Easy Steps HTML output preserves the 6-occurrence code literal `window.mainloop()`.
- Edge case: a synthetic `para_dicts` with 5 identical paragraphs across 5 distinct pages → all but first marked for skip. Count-of-stripped log line is emitted.
- Edge case: 5 identical paragraphs on the SAME page → not marked (distinct-page count is 1, below threshold).
- Edge case: paragraph flagged as code/pre that appears on ≥5 pages → not marked (code exclusion).

**Verification:**
- Unit 1's Dionysius test now passes.
- Atomic Habits and Python canary tests pass.
- Log output confirms the A2 filter reports the expected count for Dionysius (≥140 stripped paragraphs).

- [ ] **Unit 3: Cross-corpus regression verification**

**Goal:** Prove that the A2 filter does not regress any of the six corpus books beyond the expected stripping of Dionysius headers.

**Requirements:** R4.

**Dependencies:** Unit 2.

**Files:**
- Run: `python tools/test_pipeline.py` (existing regression harness)
- Run: `powershell -File tools/verify-manifest.ps1` (feature manifest verification per CLAUDE.md)
- Optionally: `powershell -File tools/test_columns.ps1` if column-path tests exist

**Approach:**
- Execute the full project regression suite. Record baseline metrics before Unit 2 is merged (from the last passing run on master) and compare.
- Metrics to watch per CLAUDE.md testing section: endnote link count (no decrease), heading classification (no body-text-as-heading), chapter detection count, PAGE marker survival.
- Run visual-QA against any KFX the harness produces (or a targeted subset) to detect unexpected downstream rendering differences.

**Execution note:** If any test-corpus metric regresses, stop and diagnose before attempting a second fix (CLAUDE.md testing section: "never stack multiple fixes without testing between each one").

**Patterns to follow:**
- `CLAUDE.md` § Testing — lists the required post-change validation steps verbatim.

**Test scenarios:**
- Full regression suite exits clean on all six corpus books.
- Endnote link count ≥ baseline for each corpus book.
- Chapter detection count unchanged for each corpus book.
- PAGE markers survive all processing phases (existing harness assertion).

**Verification:**
- `test_pipeline.py` reports PASS for all test cases.
- `verify-manifest.ps1` reports no removed functions, files, or config keys.
- Dionysius extraction (via the test entrypoint) shows a log line confirming the A2 filter stripped ≥140 running-header paragraphs.

## System-Wide Impact

- **Interaction graph:** The A2 filter operates strictly within the HTML extraction path (two functions). It does not touch heading detection, TOC generation, bookmark reconciliation, footnote linking, or OCR cleanup. No new entry points, no callback changes.
- **Error propagation:** No new failure modes. The filter is a pure in-memory mutation over `para_dicts`; if it raises, it raises the same way the existing column-path filter does (log and continue, no crash).
- **State lifecycle risks:** None. The mark-and-skip pattern mirrors the existing column-path filter precisely.
- **API surface parity:** The existing OCR pre-scan at line 3262 remains in place and continues to serve the flat-`paragraphs` text path. Parity across the two paths is improved, not broken.
- **Integration coverage:** Cross-corpus `test_pipeline.py` run (Unit 3) is the integration coverage for this change.
- **Unchanged invariants:** `<a id="page_N"></a>` anchor emission unchanged. Phase 0 / Phase 0b ALL-CAPS filters unchanged. Column-path filter unchanged. The A2 filter is additive.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Threshold ≥5 strips Python's `window.mainloop()` (6 occurrences, short code literal) → regresses R3 | Code/pre exclusion check in the A2 helper. Unit 2 test scenario explicitly covers this. |
| Code/pre flag doesn't exist on `para_dicts` in one of the two HTML paths | Implementer fallback: inspect text for common code-literal markers (parens, semicolons, balanced brackets, trailing `()`) as a heuristic. Documented in Deferred-to-Implementation. |
| Atomic Habits cheat-sheet line happens to appear on 5+ distinct pages in some future edition of the book → false-positive strip | Threshold ≥5 is tuned for current corpus. If a future test corpus book has a 5+-page legitimate repeat, threshold may need to be raised to ≥6 or the exclusion list extended. Documented, not fixed preemptively. |
| A2 filter and column-path filter double-mark the same paragraph | The two paths are mutually exclusive (column-path runs only on column-aware extraction). No double-marking risk under current code. If paths merge in the future, a no-op second mark is fine. |
| Running the full regression suite surfaces an unrelated failure | Out of scope here. Any new failure triggers a separate investigation per CLAUDE.md regression rule. |

## Documentation / Operational Notes

- Update commit message to reference SCRUM-299 per project convention.
- No CLAUDE.md update needed — the fix follows existing patterns.
- Once Unit 3 passes, the `docs/solutions/scrum-299-structural-widgets-as-body-content.md` diagnostic is ready to be superseded by a `ce:compound` knowledge-compounding write-up (separate workflow, not in this plan).

## Sources & References

- **Origin document:** [docs/solutions/scrum-299-structural-widgets-as-body-content.md](../solutions/scrum-299-structural-widgets-as-body-content.md) — Phase 1 + Phase 2 diagnostic.
- **Jira:** [SCRUM-299](https://jlfowler1084.atlassian.net/browse/SCRUM-299) — descoped to A2-only after Phase 2.
- **Related new ticket:** [SCRUM-301](https://jlfowler1084.atlassian.net/browse/SCRUM-301) — end-matter raw-HTML bleed (separate class-of-bug).
- **Related prior plan:** [docs/plans/2026-04-20-001-feat-scrum-282-vqa-baseline-methodology-plan.md](2026-04-20-001-feat-scrum-282-vqa-baseline-methodology-plan.md) — VQA pipeline baseline conventions used in Unit 3 verification.
