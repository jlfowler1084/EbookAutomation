---
title: EB-377 Phase-3 50-book regression sweep - corpus gates, deterministic VQA, and provenance joins
date: 2026-06-07
ticket: EB-377
module: batch_qa, visual_qa, check_header_bleed, corpus_selection
tags: [batch-qa, vqa, qwen3-vl, header-bleed, corpus-selection, provenance, calibration, regression-sweep]
problem_type: regression-sweep
status: completed
related: [EB-367, EB-370, EB-372, EB-374, EB-382, EB-383, EB-384, EB-385, EB-386, EB-387, EB-388, EB-389, EB-390]
---

# EB-377 Phase-3 50-book regression sweep

## Outcome

The Phase-3 sweep answered the original question: the running-header bleed fixes
from EB-367, EB-370, EB-372, and EB-374 held across the 50-book corpus.

Run `batch_20260607_125616` processed 50 PDFs through PDF -> KFX -> local-Qwen
VQA with:

- 34 passed, 9 warned, 7 failed, 0 errors.
- 0 KFX failures, 0 coverage gaps.
- 0 paid VQA cost.
- 50/50 provenance records complete.

The header-bleed sweep reported 13 welds in one book, `BERT_Pre_Training.pdf`.
Manual HTML spot-check showed all 13 were repeated body-text references to
`OpenAI GPT` / `AI GPT`, not a running header welded into prose. That detector
false positive became EB-389. The two calibration anchors, Pilgrim People and
On First Principles, remained zero-weld.

The real follow-up backlog from the sweep is EB-382 through EB-388:
VQA-low render failures, chapter detection zero, formatting not preserved,
unlinked footnotes, one remaining ligature split, mixed multi-column routing,
and one isolated double-space artifact.

Primary artifacts:

- `data/batch_reports/batch_20260607_125616.{json,md,html}`
- `data/batch_reports/EB-377-provenance.json`
- `data/batch_reports/EB-377-findings-2026-06-07.md`
- `data/batch_reports/EB-377-vqa-determinism-pilgrim.json`

## Lessons Compounded

### 1. Real-data corpus selection is a different test tier

The TDD fixtures proved the selector logic, but the real `F:\books` pool exposed
the actual failure modes:

- duplicate basenames that would collide during staging;
- `_Needs_Review` skew that defeated the intended variety sample;
- 0-byte or undersized download stubs;
- split-facsimile fragments masquerading as books;
- title duplicates across different filenames;
- anchor duplicates under fresh-library names;
- content that survived folder-based exclusion because the same author/material
  appeared under other folders.

The practical pattern: keep selector unit tests, but always add a real-data smoke
that checks the final manifest directly: count, duplicate basenames, excluded
folder components, undersized files, fragment patterns, per-folder cap, and
human-reviewed filenames. Folder-level filtering is not content-level filtering.

### 2. Manifest review must inspect filenames, not just strata

The `--exclude-folder Goblin_Tricks` control worked exactly as implemented, but
it did not remove all unwanted content. Similar material re-entered through
`Magazines` and other paths. The final clean manifest used seed `309` plus
runtime exclusions for `Goblin_Tricks` and `Magazines`, then restaged exactly
the selected 50 PDFs.

That gate caught the issue before the expensive run. For future sweeps, treat the
reviewable manifest as a product artifact, not a log. The reviewer should inspect
actual source paths and filenames, then either approve them or rerun selection
with explicit, recorded exclusions.

### 3. VQA determinism depends on the resolved endpoint, not the intended config

Gate 9 initially failed with large deltas because the process resolved to a
stale local endpoint (`localhost:8000`) and model, not the intended R9700
endpoint (`192.168.1.33:8080`) and `Qwen3VL-30B-A3B-Instruct-Q4_K_M.gguf`.
Pinned to the intended endpoint/model, the determinism check passed bit-exact:
overall 77 vs 77, max page delta 0.

The reusable rule: determinism gates must log or otherwise prove the resolved
provider URL and model. Do not trust `config/settings.json` alone when environment
variables or `.env` can override it. If the resolved endpoint is a shared local
server, quiesce it or serve single-slot before trusting score deltas.

### 4. Calibration gates separate findings from measurement artifacts

Three checks prevented bad conclusions:

- The two clean header anchors were zero-weld before corpus findings were trusted.
- VQA was run twice on the same KFX and had to pass tolerance 0 before VQA scores
  became findings.
- Spot-checks opened both detector hits and VQA-flagged rendered KFX PNGs.

This is what separated the BERT header-bleed false positive from the real VQA-low
render failures. A detector flag is a lead; a calibrated, spot-checked flag is a
finding.

### 5. Provenance must carry the converter's emitted path

`Convert-ToKindle` does not reliably name KFX files from the source PDF stem. It
uses parsed title/author metadata, so `Raw Libgen Name.pdf` can become
`Clean Title - Author.kfx`. A provenance join that reconstructs output paths from
source stems will silently misclassify successful conversions as missing.

The EB-377 harness fix made `kindle_conversion.output_path` a first-class field in
the batch report. The provenance builder joins manifest source -> batch diagnostic
filename -> recorded KFX output path -> `.intermediates/<kfx-stem>_kindle.html`.
The 50-book run validating 0 coverage gaps is the proof that this join holds under
real metadata-derived names.

### 6. Cheap secondary scans should be provenance-scoped

The header-bleed sweep scans the `_kindle.html` intermediates produced by the
batch run, but the intermediates directory can contain stale files from older
runs. The safe pattern is not `glob("*_kindle.html")`; it is "for each manifest
entry, locate the recorded KFX output path, derive exactly that intermediate path,
and scan only that file."

That made the header result auditable: 50 intended books, 50 complete provenance
records, and one explainable detector false positive.

## Follow-up Tickets

- EB-382 - investigate VQA-low KFX render failures.
- EB-383 - chapter detection returns zero on converted books.
- EB-384 - preserve formatting when source has visible structure.
- EB-385 - convert detected footnote markers into links.
- EB-386 - remaining high ligature split artifact.
- EB-387 - improve mixed multi-column routing confidence.
- EB-388 - isolated double-space artifact in output text.
- EB-389 - header-bleed detector false positive on repeated body phrase.
- EB-390 - align local VQA endpoint/model config and override docs.

## Related

- `docs/superpowers/specs/2026-06-07-eb-phase3-50book-regression-sweep-design.md`
- `docs/superpowers/plans/2026-06-07-eb377-phase3-50book-sweep.md`
- `docs/solutions/eb367-running-header-bleed-html-path.md`
- `docs/solutions/eb370-header-bleed-batch-guard.md`
- `docs/solutions/eb374-roman-numeral-running-header-bleed.md`
- `docs/solutions/eb361-vqa-grader-determinism-self-check-2026-06-02.md`
