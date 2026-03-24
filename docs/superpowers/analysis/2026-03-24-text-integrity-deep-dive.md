# Text Integrity Deep Dive -- 11 VQA-Failing Books

**Date:** 2026-03-24
**Source run:** `batch_20260324_100208` (VQA baseline)

## Summary

Investigated all 11 books with `text_integrity` below 70 in the VQA baseline. Deep-dived the top 5 worst scorers with source PDF comparison. Classified every problem by origin.

**Key finding:** The two dominant problems are **word merges** (4,969 occurrences across all 11 books) and **OCR debris** (2,911 occurrences). Both originate in the source PDFs, but the pipeline has opportunities to fix them.

## Per-Book Findings

### 1. Kabbalah (Ginsburg) -- VQA: 33, text_integrity: 37

**Origin: SOURCE_BAD**

| Problem | Count | Origin |
|---------|-------|--------|
| word_merges | 786 | SOURCE_BAD -- source PDF has no inter-word spaces |
| ocr_debris_sequences | 590 | SOURCE_BAD -- 19th century typeface + Hebrew badly OCR'd |
| bullet_dot_sequences | 85 | SOURCE_BAD -- OCR replaces Hebrew chars with bullet dots |
| scanner_timestamps | 2 | CLEANUP_MISS -- "Saturday, 29 September 2007 0045" in headings |

VQA flagged: garbled Hebrew text (`':l"M`, `THJSESSAY`), scanner timestamps as chapter headings, OCR letter confusion (B->8). Source pypdf extraction confirms: text is equally garbled at source level. This is a badly OCR'd 19th century book with Hebrew. No pipeline fix possible for the bulk of issues.

**Fixable:** Scanner timestamps (2 occurrences, regex cleanup). Everything else is source quality.

### 2. Into the Fringe (Turner) -- VQA: 36, text_integrity: 49

**Origin: LIKELY VQA MAPPING ERROR**

Source PDF is clean (pypdf shows 0 merges, 0 OCR debris at mid-page). But VQA report contains findings about "The Tempest" and "XAVIER UNIVERSITY LIBRARY" -- content from a different book entirely. The KFX conversion may have produced the wrong book's output, or the VQA evaluated the wrong file. HTML extraction output (417KB) appears reasonable in size.

The HTML analysis shows only 31 word merges and 20 OCR debris sequences -- far lower than the VQA score of 49 would suggest if it were the correct book. **This VQA score is unreliable** and should be re-evaluated.

**Fixable:** Re-run VQA on correct KFX file. Actual book quality likely much higher.

### 3. Unholy Alliance (Levanda) -- VQA: 52, text_integrity: 48

**Origin: SOURCE_BAD (word spacing)**

| Problem | Count | Origin |
|---------|-------|--------|
| word_merges | 259 | SOURCE_BAD -- pypdf shows 25-53 merges per sampled page |
| ocr_debris_sequences | 51 | SOURCE_BAD -- library stamps, OCR artifacts |
| repeated_headers | 1 | CLEANUP_MISS |

Source pypdf extraction shows words completely merged: `TheOccultMessiah103wassaid--taughtHitlereven-thingfrom...`. The PDF lacks proper inter-word spacing in its glyph positioning. pdfminer may handle spacing better than pypdf, but the extraction still shows 259 merges in the HTML output.

VQA flagged: OCR debris (`7r3r`, `J\ Bistory of 1`), library stamps OCR'd as text (`WBUR 90.9 1m`, `www.onpoinfradio.org`), footnote number corruption (`1^.` for `15.`), letter confusion (`Kllhn` for `Kuhn`, `ol` for `of`).

**Fixable:** Library stamp removal (regex for common patterns). Word spacing is a source issue.

### 4. Public Finance (Gruber) -- VQA: 44, text_integrity: 51

**Origin: CLEANUP_MISS + EXTRACTION_CORRUPT**

| Problem | Count | Origin |
|---------|-------|--------|
| printer_metadata | 796 | CLEANUP_MISS -- InDesign metadata not stripped |
| word_merges | 461 | EXTRACTION_CORRUPT -- source is clean (2-3 merges in pypdf) |
| repeated_headers | 35 | CLEANUP_MISS -- running headers leaked into body |

Source PDF is **clean** -- pypdf shows 2-3 word merges per page, well-formatted text. But the HTML has 796 InDesign printer metadata entries (`Gruber_5e_CH09_Printer.indd 269 16/11/15 6:07 PM`) and 461 word merges that don't exist in the source.

VQA flagged: printer metadata in body text, two-column layout merged incorrectly, sidebar boxes inserted inline, table content interleaved with body text. This is a **textbook with complex layout** (two columns, sidebars, tables) that the single-column extraction path can't handle.

**Fixable:**
- Printer metadata stripping (regex: `\w+_\d+e?_CH\d+_\w+\.indd\s+\d+.*$`)
- Running header removal (regex for repeated short lines)
- Column merging requires column-aware extraction path

### 5. Ezekiel II (Zimmerli) -- VQA: 51, text_integrity: 52

**Origin: SOURCE_BAD (Hebrew/Greek) + EXTRACTION_CORRUPT (word spacing)**

| Problem | Count | Origin |
|---------|-------|--------|
| ocr_debris_sequences | 1953 | SOURCE_BAD -- Hebrew/Greek transliterations garbled |
| word_merges | 1819 | MIXED -- source has some, pipeline amplifies |
| bullet_dot_sequences | 9 | SOURCE_BAD -- unrecognized Hebrew chars |

Source has 0-3 merges per sampled page in pypdf, but 1-15 OCR debris from Hebrew/Greek apparatus. The pipeline massively amplifies word merges (from ~3 to 1819), suggesting the HTML extraction introduces spacing errors for this book. The Hebrew/Greek scholarly apparatus (`:-rC:J`, `c,:-rn;`) is garbled at the source level and unfixable.

VQA flagged: garbled Hebrew (`'l'""!:III:'I' ofv 2`), OCR substitutions (`Eu1cie12` for `Ezechiel`), footnotes mid-paragraph, bullet-dot replacement chars for unrecognized glyphs.

**Fixable:** Word merge amplification is an extraction bug. Hebrew garbling is source quality.

### 6. Persecuting Society (Moore) -- VQA: 44, text_integrity: 60

**Origin: EXTRACTION_CORRUPT**

Source is clean (0 merges, 0 OCR debris in pypdf). HTML shows only 22 word merges and 3 Latin-1 artifacts. VQA score of 60 suggests moderate issues. Source pypdf shows unusual spacing: `purity an d danger` -- extra spaces within words, which is the inverse of word merging. The extraction may be incorrectly inserting spaces.

**Fixable:** Investigate space insertion logic for this book's font metrics.

### 7. Prompt Engineering (Tabatabaian) -- VQA: 53, text_integrity: 62

**Origin: EXTRACTION_CORRUPT**

Source is clean (2 merges in pypdf). HTML shows 307 word merges -- pipeline is introducing them. Source has styled chapter headers with small-caps (`rEal-World aPPliCations`), which is a formatting feature, not an error. The word merge detection regex may be over-counting small-caps as "merges."

**Fixable:** Word merge count may be inflated by small-caps styling. Actual text_integrity issue is moderate.

### 8. Beginning of Wisdom (Kass) -- VQA: 54, text_integrity: 67

**Origin: EXTRACTION_CORRUPT**

Source is clean (0 merges, 0 OCR debris). HTML shows 272 word merges and 165 OCR debris sequences introduced by the pipeline. This is a large book (713 pages, 1954KB HTML) where extraction is introducing errors not present in the source.

**Fixable:** Yes -- investigate extraction word-spacing logic.

### 9. Database Systems (Hellerstein) -- VQA: 53, text_integrity: 67

**Origin: EXTRACTION_CORRUPT**

Source has very sparse text per page (75 chars at mid-page -- this is a multi-column academic paper collection). HTML shows 647 word merges and 68 OCR debris sequences. The book contains academic papers with complex formatting (equations, tables, citations) that the extraction path struggles with.

**Fixable:** Partially -- may need column-aware extraction for academic papers.

### 10. Adult Children (Kritsberg) -- VQA: 41, text_integrity: 69

**Origin: SOURCE_BAD (word spacing)**

Source pypdf shows severe word merging: `RecoveryAProcessInteractiveRecoveryProcessChart77` -- completely merged text. HTML shows 360 word merges. The source PDF lacks inter-word spacing, similar to Unholy Alliance.

**Fixable:** No -- source quality issue. Pipeline could attempt heuristic word-splitting.

### 11. Tempest (Shakespeare) -- VQA: 40, text_integrity: 56

**Origin: SOURCE_BAD (edition quality)**

Source is relatively clean (0 merges, 1 OCR debris in pypdf). This is a Penguin edition with footnotes intermixed in the text. The VQA flagged footnote annotations merged with play dialogue (`69 neat's leather cowhide 75 not take too much`). HTML shows only 5 word merges and 9 OCR debris -- suggesting the issue is primarily **footnote layout** rather than text corruption.

**Fixable:** Partially -- footnote separation logic could be improved.

## Cross-Book Pattern Analysis

| Problem Type | Books Affected | Total Occurrences | Primary Origin | Pipeline-Fixable? |
|-------------|---------------|-------------------|----------------|-------------------|
| **word_merges** | 11/11 | 4,969 | 5 SOURCE_BAD, 6 EXTRACTION_CORRUPT | Partially -- 6 books have clean source but pipeline introduces merges |
| **ocr_debris_sequences** | 11/11 | 2,911 | Mostly SOURCE_BAD | No for source OCR; Yes for scanner timestamps/metadata |
| **printer_metadata** | 1/11 | 796 | CLEANUP_MISS | **Yes** -- simple regex strip |
| **bullet_dot_sequences** | 3/11 | 95 | SOURCE_BAD | No -- Hebrew/special char OCR artifacts |
| **repeated_headers** | 6/11 | 54 | CLEANUP_MISS | **Yes** -- detect and strip repeated short lines |
| **scanner_timestamps** | 1/11 | 2 | CLEANUP_MISS | **Yes** -- regex for day/date/time patterns |
| **latin1_artifacts** | 1/11 | 3 | ENCODING_MANGLE | **Yes** -- encoding normalization |
| **ligature_splits** | 2/11 | 2 | CLEANUP_MISS | Already handled -- count is minimal |

## Origin Classification Summary

| Origin | Books | Description |
|--------|-------|-------------|
| SOURCE_BAD | 5 | Kabbalah, Unholy Alliance, Ezekiel II (Hebrew), Adult Children, Tempest (footnotes) |
| EXTRACTION_CORRUPT | 5 | Public Finance, Persecuting Society, Prompt Engineering, Beginning of Wisdom, Database Systems |
| CLEANUP_MISS | 3 | Public Finance (metadata), Kabbalah (timestamps), multiple (headers) |
| VQA_ERROR | 1 | Into the Fringe (wrong book evaluated) |

**Pipeline-fixable: 7 of 11 books have at least some fixable issues.**
**Fully pipeline-fixable: 4 books** (Persecuting Society, Prompt Engineering, Beginning of Wisdom, partially Public Finance) where the source is clean but the pipeline introduces errors.

## Prioritized Fix Recommendations

### Fix 1: Word-spacing regression in HTML extraction (6 books, ~3,500 occurrences)
**Impact: HIGH -- affects 6 books where source text is clean**
**Location:** `pdf_to_balabolka.py` -- `extract_with_pdfminer_html()` or `rejoin_html_fragments()`
**Complexity:** Moderate

Six books have clean source PDFs (0-3 merges in pypdf) but the pipeline HTML shows hundreds of word merges. This is a systematic spacing bug in the pdfminer extraction path. The font-metric-based word boundary detection is failing for certain font configurations.

Books affected: Public Finance (461), Prompt Engineering (307), Beginning of Wisdom (272), Database Systems (647), Persecuting Society (22), Ezekiel II (partially, 1819)

Expected VQA improvement: +8-12 points for these books (4 could reach Tier B)

### Fix 2: InDesign printer metadata stripping (1 book, 796 occurrences)
**Impact: MEDIUM -- affects 1 book significantly, likely more in future batches**
**Location:** `pdf_to_balabolka.py` -- add to cleanup pass
**Complexity:** One-liner regex

Regex: `r'\w+_\d+e?_CH\d+_\w+\.indd\s+\d+.*?(?:AM|PM)'` -- strip InDesign/QuarkXPress metadata that leaks into extracted text. Found in Gruber's Public Finance (textbook publisher workflow artifact).

Expected VQA improvement: +5 points for affected books

### Fix 3: Running header/footer detection and removal (6 books, 54 occurrences)
**Impact: MEDIUM -- affects 6 books**
**Location:** `pdf_to_balabolka.py` -- `clean_and_join()` or post-extraction cleanup
**Complexity:** Moderate

Detect repeated short text sequences (5-50 chars, appearing 4+ times at regular intervals) and remove them. These are running headers/footers that leaked into body text.

Expected VQA improvement: +2-3 points for affected books

### Fix 4: Scanner timestamp removal (1 book, 2 occurrences)
**Impact: LOW -- but the timestamps appear as chapter headings, breaking TOC**
**Location:** `pdf_to_balabolka.py` -- cleanup pass
**Complexity:** One-liner regex

Regex: `r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*,?\s+\d{1,2}\s+\w+\s+\d{4}\s+\d{4}'` -- strip scanning device timestamps.

### Fix 5: Re-evaluate Into the Fringe VQA (1 book)
**Impact: HIGH for this book -- score is likely wrong**
**Location:** Batch QA mapping or Calibre conversion
**Complexity:** Investigation needed

The VQA report for Turner's "Into the Fringe" contains findings about Shakespeare's "The Tempest" -- wrong book evaluated. Need to verify KFX conversion output mapping.

## If All Pipeline-Fixable Issues Were Resolved

| Metric | Current | Projected |
|--------|---------|-----------|
| Books with text_integrity >= 70 | 22/33 | 27-28/33 |
| Average text_integrity | 75.9 | ~80 |
| Books in VQA Tier B+ | 5/34 | 9-12/34 |

The 5 SOURCE_BAD books (Kabbalah, Unholy Alliance, Ezekiel II Hebrew, Adult Children, Tempest footnotes) cannot be improved without better source PDFs or OCR re-processing.
