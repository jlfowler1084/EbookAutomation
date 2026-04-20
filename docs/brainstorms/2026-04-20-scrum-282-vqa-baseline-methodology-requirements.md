---
date: 2026-04-20
topic: scrum-282-vqa-baseline-methodology
---

# SCRUM-282 — VQA Baseline Methodology: Standardize to KFX→Calibre Source

## Problem Frame

The VQA Claude baselines in `data/vqa_baseline_post_274/` are the oracle used to gate
regression on every local-provider smoke run. During SCRUM-280 Investigation (A), the
Atomic Habits baseline was found to have been captured from the original PDF source
(266 pages) rather than the KFX→Calibre path (272 pages). Because `select_sample_pages()`
is fully deterministic on `pages_total` and bookmark positions, the baseline sampled
`[1, 2, 3, 73, 92, 145, 158, 232]` while the live smoke sampled
`[1, 2, 3, 91, 94, 149, 152, 238]` — zero interior-page overlap, so direct |Δ|
comparison is unreliable. Atomic Habits was excluded from the SCRUM-280 R2 gate as a
result.

The 5 other books in the baseline set are believed to be in parity but have not been
programmatically verified, and the JSON schema has no field that records which source
path produced each baseline.

## Requirements

**Audit & Re-capture**
- R1. Audit all 6 baselines in `data/vqa_baseline_post_274/` by comparing the sampled
  page numbers (already stored in each baseline's `pages[].page_number` array) against
  a fresh `select_sample_pages()` run on the current KFX-derived PDF for that book.
  Exact sampled-page parity is required — this exercises the real determinism surface
  `(pages_total, bookmark_pages) → sample`, not just the page-count proxy. Any
  mismatch indicates a drifted baseline that must be re-captured or investigated.
- R2. Re-capture the Atomic Habits Claude baseline from the KFX→Calibre path so its
  `pages[].page_number` list matches future smoke runs.
- R3. Preserve the existing PDF-sourced Atomic Habits baseline in an archive
  subdirectory (not deleted) so the drift finding remains inspectable.
- R4. Re-run R1's sampled-pages audit after re-capture; confirm all 6 baselines produce
  exact `pages[].page_number` parity against a fresh KFX-derived sampler run.

**Schema & Capture-Time Safeguards**
- R5. Add a `source_format` field to every baseline JSON output (values: `"kfx"` or
  `"pdf"`), set by capture code based on which pipeline branch executed: `"kfx"` if
  Calibre conversion was invoked on the input; `"pdf"` if the PDF-skip branch was
  taken. This records actual provenance (the code path that produced the rendered
  pages), not the input file's extension — an extension-based label mis-classifies
  a `.pdf` that was itself derived from a KFX upstream.
- R6. Backfill `source_format` on the 5 in-parity baselines so the audit signal is
  consistent across all baselines (no null values after this ticket ships).
- R7. Emit a loud warning at baseline capture time when the input is a PDF *and* a
  matching KFX already exists at the conventional output path. The capture still
  proceeds; the warning flags the likely mistake without blocking legitimate PDF
  baselines for books that haven't been converted yet.

**Documentation**
- R8. Add a rule to the Visual QA section of `CLAUDE.md` stating that all Claude VQA
  baselines must be captured from the KFX source, not original PDFs, and documenting
  the `source_format` field semantics.

**Stem Consistency**
- R9. When re-capturing Atomic Habits from KFX, the new baseline's filename stem must
  match the stem produced by KFX-based smoke runs (e.g., `… - James Clear`) so
  `tools/compare_vqa_reports.py` finds it via stem lookup without manual aliasing.
  When archiving the old PDF-sourced baseline, **move** (not copy) it to the archive
  location so only one baseline per book remains discoverable in the active baseline
  directory.

## Success Criteria

- All 6 baseline JSONs show `source_format: "kfx"` after this ticket ships (via
  re-capture for Atomic Habits; via backfill for the other 5 once R1 audit confirms
  parity).
- Atomic Habits baseline's `pages[].page_number` list matches a fresh
  `select_sample_pages()` run against the current KFX-derived PDF exactly.
- The other 5 baselines pass R1's sampled-pages audit with zero mismatches.
- The re-captured Atomic Habits baseline's filename stem matches the stem produced by
  KFX-based smoke runs (verified by `compare_vqa_reports.py` finding it without manual
  aliasing).
- Running `visual_qa.py` against a PDF when a KFX exists at the expected path produces
  a visible warning in the log.
- `CLAUDE.md` Visual QA section includes the KFX-only baseline rule.
- SCRUM-280 R2 gate can include Atomic Habits in its math on the next re-run.

## Scope Boundaries

- **Not re-baselining** the 5 books believed in parity (pending confirmation by R1);
  audit via page-count diff is expected to confirm they are safe, and re-running them
  would burn Claude Vision API spend for no signal.
- **No hard block** on PDF-sourced captures when KFX exists — warning only. A hard block
  would require an override flag that itself becomes a foot-gun.
- **No richer provenance** beyond `source_format` (no file hash, no Calibre version,
  no capture-tool version). YAGNI until evidence of a second drift class appears.
- **No change to** `select_sample_pages()` — the determinism property is correct; the
  fix is at the input layer, not the sampler.
- **No change to** VQA rubric or scoring logic.

## Key Decisions

- **Audit via sampled-pages diff, not full re-run** — comparing `pages[].page_number`
  lists against a fresh `select_sample_pages()` run exercises the exact determinism
  surface that caused the Atomic Habits drift. Zero Claude API cost (sampler runs
  locally); only a local Calibre invocation per book is needed to refresh the
  KFX-derived PDF when `get_pdf_bookmarks()` has to re-read structure. Chosen over
  `pages_total` diff because coincidentally-matching page counts would otherwise pass
  audit with no real signal.
- **Warning, not hard block** — preserves the ability to baseline a book that hasn't
  been through Calibre yet (legitimate case), while catching the mistake class
  immediately when it happens. The `source_format` field makes drift programmatically
  detectable regardless.
- **Archive old Atomic Habits baseline** — preserves evidence of the drift for future
  reference at effectively zero cost. Overwriting loses the artifact that made this
  ticket possible. Archive is a **move**, not a copy, so stem-based lookup in
  `compare_vqa_reports.py` does not find two baselines for the same book.
- **`source_format` records the executed code path, not the input extension** — if
  Calibre conversion ran in this capture, `"kfx"`; if the PDF-skip branch ran, `"pdf"`.
  Extension-based labelling has the same failure mode it was designed to prevent
  (a KFX-derived intermediate PDF fed to `visual_qa.py` would be mis-labeled `"pdf"`
  even though the content came from the KFX pipeline).

## Dependencies / Assumptions

- Assumes the 5 non-Atomic-Habits baselines will pass R1's sampled-pages audit. A
  mismatch could indicate either source drift OR a Calibre-version / bookmark-extraction
  change downstream of capture; investigate cause before auto-re-capturing. If a
  book needs re-capture, R2/R3 scope expands to cover it; flag to user first.
- Assumes KFX files for all 6 books still exist in `output/kindle/` (verified during
  SCRUM-274 Phase 1 corpus rebuild).

## Outstanding Questions

### Resolve Before Planning

*None.*

### Deferred to Planning

- [Affects R3][Technical] Where should the archived old baseline live? Options:
  `data/vqa_baseline_post_274/.archive/` subdirectory vs
  `data/vqa_baseline_archive/` sibling directory. Minor; either works.
- [Affects R1][Technical] Should the audit run as a one-shot inline in the Atomic
  Habits re-capture session, or land as a small reusable `tools/audit_vqa_baselines.py`
  that can be re-run anytime a new baseline set is captured? Recommend the reusable
  tool since the cost is minimal and it becomes the mechanism for preventing a third
  drift class in future. **Note: this decision is coupled to the archive-location
  question above — a non-hidden sibling archive would be scanned by a naive glob and
  produce false-positive drift flags; resolve audit-tool scope first.**
- [Affects R8][Technical] Where in `CLAUDE.md` should the KFX-only baseline rule
  live — integrated into the existing Visual QA System section, or as a new
  "Baseline Capture Policy" subsection? Recommend integrating into the existing
  section to avoid section proliferation.
- [Affects R6][Technical] Backfill method for the 5 in-parity baselines: patch the
  JSON directly with `"source_format": "kfx"`, or re-run capture on each? Patch is
  cheaper and correct since audit has already proven parity; flag for planning.

## Next Steps

-> `/ce:plan` for structured implementation planning
