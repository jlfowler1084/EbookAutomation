# Double-Column Batch QA Diagnostic Report

**Run ID:** batch_20260401_223051
**Date:** 2026-04-01
**Source folder:** `F:\Books\Double_Columned`
**Books processed:** 30 (28 active, 2 skipped)
**Duration:** 2m 38s
**Mode:** Quick (HTML extraction + structural checks, no KFX, no VQA)

---

## Section 1: Executive Summary

| Metric | Value |
|--------|-------|
| Total books | 30 |
| Passed | 28 (100% of active) |
| Warned | 0 |
| Failed | 0 |
| Errored | 0 |
| Skipped | 2 (study bibles >200 pages) |
| Pass rate | **100%** |

### Top 3 Findings

1. **Column detection works well (89% accuracy)** — 25/28 books correctly identified as multi-column. 3 false negatives at confidence 0.40-0.50 (below the 0.60 threshold).

2. **Column-aware extraction path is NEVER used** — All 28 books route through `html_extraction` (pdfminer). Despite correct multi-column detection, the converge loop's strategy order puts html_extraction first, and since pdfminer produces valid output for these digitally-native PDFs, column_aware extraction never triggers. This means multi-column detection is informational only — it doesn't change behavior.

3. **Heading detection is appropriate for academic papers** — 14/28 books show chapter_count=1 (title only). This is correct for academic papers which have numbered sections, not chapters. The heading classifier correctly avoids promoting section numbers to chapter-level headings.

### Skipped Books

Two study bibles exceeded the 200-page safety limit:
- **NKJV Study Bible** — 2,266 pages, 222 MB
- **Catholic Study Bible** — 2,584 pages, 203 MB

These would require dedicated processing with `--max-pages 0` and significant runtime.

---

## Section 2: Column Detection Scorecard

### Full Detection Table

| Filename | Multi-Col? | Confidence | Cols | Extraction Path | Status | Chapters | Words |
|----------|-----------|------------|------|-----------------|--------|----------|-------|
| 2604.01179v1.pdf | True | 1.00 | 2 | html_extraction | PASS | 3 | 3,826 |
| BERT_Pre_Training.pdf | True | 1.00 | 2 | html_extraction | PASS | 1 | 10,026 |
| BlackHole.pdf | True | 1.00 | 2 | html_extraction | PASS | 10 | 14,336 |
| Deep_Residual_Learning.pdf | True | 1.00 | 2 | html_extraction | PASS | 1 | 10,171 |
| Entanglement.pdf | True | 1.00 | 2 | html_extraction | PASS | 1 | 6,270 |
| gfs-sosp2003.pdf | True | 1.00 | 2 | html_extraction | PASS | 1 | 14,491 |
| Growth_of_Graph_States.pdf | True | 1.00 | 2 | html_extraction | PASS | 1 | 12,671 |
| High_Order_Structure.pdf | True | 1.00 | 2 | html_extraction | PASS | 4 | 6,188 |
| mapreduce-osdi04.pdf | True | 1.00 | 2 | html_extraction | PASS | 1 | 8,906 |
| Master_Equation.pdf | True | 1.00 | 2 | html_extraction | PASS | 1 | 4,917 |
| MIMO_Systems.pdf | True | 1.00 | 2 | html_extraction | PASS | 2 | 5,954 |
| Modularized_Neural_Network.pdf | True | 1.00 | 2 | html_extraction | PASS | 12 | 5,807 |
| Obfuscating_Code.pdf | True | 1.00 | 2 | html_extraction | PASS | 1 | 9,838 |
| Precision_Measurement.pdf | True | 1.00 | 2 | html_extraction | PASS | 3 | 5,028 |
| Quantum_Computer_Architecture.pdf | True | 1.00 | 2 | html_extraction | PASS | 12 | 15,704 |
| Quantum_Key.pdf | True | 1.00 | 2 | html_extraction | PASS | 13 | 10,102 |
| Reactor_Antineutrino_Spectra.pdf | True | 1.00 | 2 | html_extraction | PASS | 3 | 6,962 |
| Realization.pdf | True | 1.00 | 2 | html_extraction | PASS | 2 | 7,799 |
| Tetraquark_Resonant_States.pdf | True | 1.00 | 2 | html_extraction | PASS | 6 | 8,141 |
| Uncertainty_Relation.pdf | True | 1.00 | 2 | html_extraction | PASS | 9 | 10,104 |
| Photoexcitation_of_Ge.pdf | True | 0.86 | 2 | html_extraction | PASS | 1 | 8,602 |
| Covariance_Matrix.pdf | True | 0.75 | 2 | html_extraction | PASS | 1 | 4,884 |
| Multi-View-Encoders.pdf | True | 0.75 | 2 | html_extraction | PASS | 14 | 5,592 |
| QLearning.pdf | True | 0.75 | 2 | html_extraction | PASS | 1 | 6,738 |
| Quantum_Cloning.pdf | True | 0.75 | 2 | html_extraction | PASS | 1 | 5,230 |
| **Four_Wave_Mixing.pdf** | **False** | **0.50** | **1** | html_extraction | PASS | 1 | 2,958 |
| **Galactic_Constellations.pdf** | **False** | **0.50** | **1** | html_extraction | PASS | 2 | 3,310 |
| **NIPS-2012-imagenet-...Paper.pdf** | **False** | **0.40** | **1** | html_extraction | PASS | 1 | 5,811 |
| NKJV Study Bible... | N/A | 0.00 | 0 | — | SKIP | 0 | 0 |
| Catholic Study Bible... | N/A | 0.00 | 0 | — | SKIP | 0 | 0 |

### Detection Accuracy

- **Known multi-column books:** 28 (all active books are from the Double_Columned folder)
- **Correctly detected as multi-column:** 25/28 = **89%**
- **False negatives:** 3 books (conf 0.40-0.50, below 0.60 threshold)

### Confidence Distribution

```
  80-100%: 21 ████████████████████████████████████████████
  60-80%:   4 ████████
  40-60%:   2 ████
  20-40%:   1 ██
   0-20%:   0
```

**Average confidence:** 0.90 (across 28 active books)

### False Negative List

| Book | Confidence | Source Type | Why Missed |
|------|-----------|-------------|------------|
| Four_Wave_Mixing.pdf | 0.50 | unknown | 4 pages, short paper — insufficient sampling |
| Galactic_Constellations.pdf | 0.50 | unknown | 4 pages, may have mixed layout |
| NIPS-2012-imagenet-...Paper.pdf | 0.40 | unknown | 9 pages, flagged `multi_column_not_routed` |

All three false negatives are classified as `source_type: unknown` rather than `multi_column`, suggesting the column layout analysis is borderline for these documents.

---

## Section 3: Extraction Quality by Path

### Critical Finding: Column-Aware Path Never Activates

| Extraction Path | Books | Avg Words/Page | Avg Text Score | Notes |
|----------------|-------|----------------|----------------|-------|
| html_extraction (pdfminer) | 28 | 824 | 95.3 | Only path used |
| column_aware (PyMuPDF) | 0 | — | — | Never triggered |
| legacy (pypdf) | 0 | — | — | Never triggered |

**Root cause:** The converge loop in `Invoke-EbookPipeline` tries strategies in order: `html_extraction → legacy → column_aware`. Since pdfminer's HTML extraction succeeds for all 28 books (producing valid text with 100% page completeness), the loop never falls through to column_aware.

### pdfminer Performance on Multi-Column PDFs

Despite not using column-aware extraction, pdfminer produces acceptable results:

- **Text layer scores:** 85-100 (mean 95.3) — all Tier 1
- **Completeness:** 100% across all 28 books
- **Words/page:** 627-1,191 (expected range for dense academic papers)
- **Ligature splits:** 0 across all books
- **Encoding errors:** 0 across all books
- **Double spaces:** 0-10 (negligible)

**Key question:** These metrics measure text extraction quantity, not reading order correctness. pdfminer may be merging columns (reading left-right across both columns instead of top-to-bottom per column), producing garbled output that nonetheless passes word count and completeness checks. **Manual spot-checking of a few extracted HTMLs is needed to verify reading order.**

---

## Section 4: Failure Catalog

### 4.1 Skipped Books (2)

| Book | Size | Pages | Issue | Fix Category |
|------|------|-------|-------|--------------|
| NKJV Study Bible | 222 MB | 2,266 | Exceeded --max-pages 200 | Dedicated run with no page limit |
| Catholic Study Bible | 203 MB | 2,584 | Exceeded --max-pages 200 | Dedicated run with no page limit |

### 4.2 False Negatives — Column Detection (3)

| Book | Size | Pages | Confidence | Issue | Fix Category |
|------|------|-------|-----------|-------|--------------|
| Four_Wave_Mixing.pdf | 0.3 MB | 4 | 0.50 | Below 0.60 threshold | Column detection improvement |
| Galactic_Constellations.pdf | 4.8 MB | 4 | 0.50 | Below 0.60 threshold | Column detection improvement |
| NIPS-2012...Paper.pdf | 1.4 MB | 9 | 0.40 | Below 0.60 threshold + flagged | Column detection improvement |

### 4.3 Unlinked Footnotes (14 books)

Academic papers frequently have numbered references in `[1]` style which the footnote linker may not match. This affects 14/28 books but is severity=medium and does not cause failures.

| Books affected | Severity | Fix Category |
|---------------|----------|--------------|
| 14 | medium | Footnote detection regex update (EB-73) |

### 4.4 Multi-Column Not Routed (1 book)

| Book | Confidence | Issue |
|------|-----------|-------|
| NIPS-2012...Paper.pdf | 0.40 | Detected as possibly multi-column but not routed to column extractor |

---

## Section 5: Recommended Next Steps

### Priority 1: Verify Reading Order (Manual Spot-Check)

**Impact: HIGH** — The batch shows 100% pass rate, but we cannot confirm reading order correctness from metrics alone.

**Action:** Manually inspect extracted HTML for 3-5 books with highest confidence (e.g., gfs-sosp2003.pdf, mapreduce-osdi04.pdf, BlackHole.pdf). Check whether text flows top-to-bottom within each column or merges across columns.

If reading order is correct: pdfminer handles these digitally-native double-column PDFs well, and column_aware extraction is unnecessary for this document class.

If reading order is garbled: the converge loop needs modification to prefer column_aware when `is_multicolumn=True AND column_confidence >= 0.60`.

### Priority 2: Fix Converge Loop Strategy Order for Multi-Column PDFs

**Impact: MEDIUM-HIGH** — Currently column_aware extraction is dead code for any PDF where pdfminer succeeds.

**Action:** When `detect_column_layout()` returns `is_multicolumn=True` with confidence >= 0.60, the converge loop should try `column_aware` FIRST (before html_extraction). The recommended strategy order from classification already reflects this (`column_aware → html_extraction → legacy`) but the converge loop ignores it.

### Priority 3: Improve Column Detection for Short Papers

**Impact: LOW** — Only 3/28 false negatives, all with 4-9 pages.

**Options:**
- Lower threshold from 0.60 to 0.50 (would catch 2 more books but risk false positives)
- Increase sampling pages for short documents (current sampling may miss column layout on 4-page papers)
- Add per-book corrections via EB-73 for known false negatives

### Priority 4: Process Study Bibles Separately

**Impact: LOW** (for column detection assessment) — These are the most complex double-column documents but require dedicated handling.

**Action:** Run with `--max-pages 0` and `--parallel 1` on a long timeout, or add chunked processing for >500-page PDFs.

### Priority 5: Academic Reference Linking

**Impact: LOW** — 14 books have unlinked footnotes. Academic papers use `[1]`-style references rather than superscript footnotes. The footnote linker's regex may need a separate pattern for bracketed reference styles.

---

## Appendix: Raw Statistics

| Metric | Value |
|--------|-------|
| Batch run ID | batch_20260401_223051 |
| Books total | 30 |
| Books passed | 28 |
| Books skipped | 2 |
| Pass rate (active) | 100% |
| Column detection true positives | 25/28 (89%) |
| Column detection false negatives | 3 |
| Average confidence score | 0.90 |
| Books using PyMuPDF column path | 0 |
| Books using pdfminer (html_extraction) | 28 |
| Books using legacy pypdf | 0 |
| Average words/page | 824 |
| Average text layer score | 95.3 |
| Top failure category #1 | Unlinked footnotes (14 books, medium) |
| Top failure category #2 | Multi-column not routed (1 book, low) |
| Top failure category #3 | Extraction failed / skipped (2 books, critical — study bibles) |
