---
title: "EB-340 — Full-VQA batch sweep: conversion-quality findings"
date: 2026-05-29
ticket: EB-340
module: visual_qa, Convert-ToKindle, run_overnight_batch
tags: [vqa, qwen3-vl, conversion-quality, calibration, batch, large-file-coverage]
problem_type: investigation
status: findings-recorded
---

# EB-340 — Full-VQA batch sweep findings (2026-05-29)

## Goal

Run **full** visual QA (not the default 8-page partial sample) across a *diverse* set
of freshly-converted PDFs to find conversion-quality patterns that partial VQA misses,
now that the local **R9700 Qwen3-VL** endpoint makes VQA effectively free. Feeds the
EB-340 decision (auto-enable VQA on batch) and "where to go next" on conversion quality.

## Method

- **Corpus:** 12 source PDFs from `F:\Books`, chosen to span *technical type* (not topic):
  two-column academic CS (MapReduce, ResNet, ImageNet), finance/quant w/ code+equations,
  magazine layout, academic+footnotes, image-plate-heavy, image-heavy scan, a tiny short
  doc, and two large (>80 MB) books — one old scan, one modern technical. Confirmed with
  `classify_source.py` (mix of `digital_native` and `scan_with_text`).
- **Pipeline:** fresh `Convert-ToKindle -NoCache` (default HTML-extraction path, **no
  converge loop, zero cloud calls**) → local VQA `--provider local --fallback-enabled
  false --dpi 150 --max-pages 40`. Pure local, **$0 spend**.
- **Endpoint:** `Qwen3VL-30B-A3B-Instruct-Q4_K_M` (llama.cpp Vulkan) on
  `DESKTOP-488UQB2:8080`, restarted at **`--ctx-size 32768`** (the default 8192 overflows
  the hardcoded 8-image @150-DPI batch → `api_failure`).
- Artifacts: `logs/eb340-full-vqa-2026-05-29/` (manifest, per-book reports, run-summary).

### Harness/calibration notes (read before trusting numbers)
- **Grounding PASS:** the grader accurately reads real page content (verified against
  rendered pages — e.g. it correctly transcribes MapReduce's diagram and p06's code).
- **Determinism: directional only.** Re-scoring one book twice: overall 91 vs 92 (±1),
  but **per-page scores swing up to ±10** and *category labels change between runs*.
  → Trust **cross-book patterns**; do **not** treat individual page scores or single
  criticals as ground truth.
- **Grader severity inflation:** code/math pages are labelled "garbled and unreadable"
  even when characters are readable (structure lost); one snippet is restated as ~20
  duplicate criticals. → **Dedupe criticals per page; weight category scores over raw
  issue counts.**
- **Harness bugs found + fixed:** (1) KFX output is named from *metadata* (title–author),
  not source filename — initial detector false-negatived 6 successful conversions;
  (2) `Test-Path` on `[Wiley trading]…` treats `[...]` as a wildcard → needs `-LiteralPath`.

## Results (12/12 scored; mean 81.6; 274 pages; 22.7 min VQA wall-clock; $0)

| id | type | class | score | pages | dpi | trustworthy? |
|----|------|-------|------:|------:|----:|---|
| p01 two-col CS | digital | 91 | 31/31 | 150 | ✅ |
| p02 ResNet two-col | scan | 84 | 32/32 | 150 | ✅ |
| p03 ImageNet two-col | scan | 85 | 19/19 | 150 | ✅ |
| p04 magazine | scan | 83 | 40/96 | 150 | ✅ |
| p05 finance | digital | 79 | **4/548** | **72** | ❌ reduced |
| p06 quant+code | digital | 87* | 40/226 | 150 | ✅ (*see F2) |
| p07 academic | digital | 93 | 40/164 | 150 | ✅ |
| p08 image plates | digital | 89 | **4/577** | **72** | ❌ reduced |
| p09 image-heavy scan | scan | 73 | 40/341 | 150 | ✅ |
| p10 tiny doc | digital | 65 | 16/16 | 150 | ✅ |
| p11 large old scan | scan | 54 | **4/578** | **72** | ❌ reduced |
| p12 large technical | scan | 96 | **4/919** | **72** | ❌ reduced |

## Findings

### F1 — CRITICAL: silent large-file / long-book coverage collapse
4 of 12 books (>30 MB **or** >500 pages) were **silently auto-reduced to 4 pages @ 72 DPI**,
overriding `--max-pages 40 --dpi 150` (the `_apply_large_file_dpi_reduction` guard in
`visual_qa.py`). Consequence: their scores are statistically meaningless — **p12 scored 96
and p11 scored 54, both from 4 of ~600–900 pages**. This blind spot exists in partial *and*
"full" VQA. **Long/large books are effectively un-QA'd today.** This is the strongest driver
for the streaming render→eval→release chunker in the tiered-VQA design, and a precondition
for trusting VQA-driven converge on big books.

### F2 — CRITICAL: code & equation conversion failure (grounded)
Code/math-heavy books fail the HTML-extraction path:
- **Code blocks lose structure** — line breaks, indentation and monospace are dropped;
  statements merge onto single lines (verified on p06 p58: a 4-line import sequence
  collapsed into one). Readable characters, destroyed formatting.
- **Equations become `(cid:N)` garbage** — pdfminer can't map math glyphs (verified on
  p06 p51: `(cid:2)`, `C1 ¼ eC 1 ¼ … W 0`, rotated axis labels reversed).
- The **overall score (87) masked** the category failure (`text_integrity=42`). A
  partial/pass-fail VQA would miss this entirely.
- Fix direction: preserve `<pre>`/code blocks in extraction; route math/figure pages to
  Gemini OCR (Tier 2.5) or MathML.

### F3 — Conversion-robustness failures only the convert→VQA sweep can see
- **p12** (83 MB technical): KFX conversion **failed** — *"Enhanced Typesetting not
  supported for this book"* → AZW3 fallback. Real Kindle-Previewer limitation on large
  complex books.
- **p11** (81 MB scan): 81 MB source → **1.75 MB KFX** — scanned page images dropped
  (text-only), losing the book's visual content.
- **p10** (Crowley): book **title mis-extracted as "joel"** — metadata bug.
- None of these are visible to VQA-on-already-converted-KFX; only the end-to-end sweep
  surfaces them.

### F4 — Scan/OCR handling under-escalates
`scan_with_text` books score lower (p09=73, p11=54). p09 (Zeitgeist): the **classifier
recommended `ocr,gemini`** but the default path didn't escalate → OCR garbling (`KKKKK`,
reversed letters, `(cid:N)`). Bibliography/reference and list-block pages (magazine
p83–94, Zeitgeist refs) consistently flag fragmented text. Fix: honor the classifier's
OCR/Gemini recommendation in the default conversion path.

### F5 — Issue taxonomy (526 issues; treat counts as directional)
Dominant *real* themes by phrase frequency: **OCR (101), garbled (55), footnote (41),
misaligned (29), cut-off (23), margin (19)**. The "not clearly separated / visual gap"
grader tic is only 21/526 — modest. Category distribution: text_integrity 323,
paragraph_flow 126, heading_formatting 31, page_layout 27, cover_images 17, toc 2.

## EB-340 decision input

- **Cost/latency (AC):** VQA is genuinely **free** locally and **~1.9 min/book** at deep
  (40-page, 150 DPI) coverage — auto-enabling on batch is viable on cost/latency grounds.
- **Blockers before flipping `visual_qa.enabled=true`:**
  1. Server must run **≥32k context** (8k overflows at useful DPI/batch — silent
     `api_failure`). Make `-Ctx 32768` the default in `serve-qwen-vl.ps1`.
  2. **F1 large-file collapse** must be fixed (streaming chunker) or "full VQA" silently
     skips long/large books and their scores mislead converge.
- **Node-down behavior:** local-only ties the batch to the R9700 being up. Recommend
  **skip-and-warn** (never hard-fail a conversion because the VQA node is down).
- **Converge interaction:** not exercised here (we ran first-pass to expose defects). The
  defects found (code/math/scan) are exactly what converge would chase — but converge
  needs reliable scores, which F1 + grader noise currently undermine on big books.

## Recommended next tickets
1. **Streaming full-coverage VQA** (fix F1: replace large-file DPI/page reduction with
   render→eval→release chunking; honor `--max-pages`/`--dpi`).
2. **Preserve code blocks + math in extraction** (F2: `<pre>`/monospace retention; math →
   Gemini OCR/MathML).
3. **Auto-escalate scans to OCR/Gemini per classifier recommendation** (F4).
4. **Default `serve-qwen-vl.ps1 -Ctx 32768`**; document the 8k overflow.
5. **Grader hardening**: dedupe per-page criticals; calibrate code/math severity;
   category-score gating over raw critical counts.
6. **Metadata title extraction bug** (F3 p10 "joel").
