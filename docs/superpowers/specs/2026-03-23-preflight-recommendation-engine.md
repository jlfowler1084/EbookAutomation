# Unified Pre-Flight Recommendation Engine — Design Spec

**Date:** 2026-03-23
**Status:** Initial spec, pending implementation
**Jira:** SCRUM-86
**Prerequisites:** Conversion Profiles (SCRUM-82 / feature/conversion-profiles) must be merged first

---

## Overview

Replace the fragmented pre-flight analysis (classifier, pattern DB, font detector each making partial decisions independently) with a single orchestration layer that produces a complete conversion recipe before any extraction begins. The pipeline defaults to this recommendation — the user can override, but the default path should produce a clean, workable document every time.

## Philosophy

The pipeline should be **opinionated by default**. Today it's permissive — tries everything, hopes for the best. The new approach is prescriptive — analyze first, recommend the best path, follow it unless told otherwise. The difference between a tool and a product.

No guessing. No requiring the user to know which flags to set. A user runs `Convert-ToKindle -InputFile "book.pdf"` with zero flags and gets the best possible output for that specific document.

---

## Current State (What Exists)

| System | Question It Answers | Output | Used By |
|---|---|---|---|
| `classify_source.py` | "What kind of PDF is this?" | `digital_native`, `scan_with_text`, `scan_no_text` + confidence | Converge loop strategy selection |
| `pattern_db.py` | "What worked on this book before?" | Recommended extraction path + flags | Converge loop strategy selection |
| `detect_headings_font.py` | "Does this book have detectable chapters?" | Heading candidates with confidence | `Get-ChapterStructure` |
| Converge loop | "Which strategy sequence to try?" | Ordered list of extraction paths | `Invoke-ConvergeLoop` |

## The Gap

None of these systems produce a **complete conversion recipe**. They each inform one piece:
- Classifier says "this is a scan" but doesn't set the profile to `text-only`
- Pattern DB says "use legacy extraction" but doesn't disable Claude chapters for noisy fonts
- Font detector finds 2,040 candidates on Fruchtenbaum but doesn't tell the pipeline to skip Claude chapter detection and just use bookmarks
- No system assesses whether footnotes, index, or hyperlinks are viable (clean enough to preserve)

The user fills the gaps with manual flags: `-UseHtmlExtraction`, `-UseClaudeChapters`, `-Profile text-only`, `-NoIndex`. Every missing flag is a potential quality problem.

---

## Proposed Architecture

### New file: `tools/preflight_analysis.py`

One script, one call, one JSON output. Runs all analysis in <10 seconds and produces a complete conversion recipe.

### Analysis Steps (executed in order)

**Step 1: Source Classification** (existing logic, ~3s)
- File size per page ratio
- Text density sampling (pypdf)
- Image vs text objects (PyMuPDF)
- PDF producer metadata
- Output: `source_type`, `confidence`

**Step 2: Text Quality Assessment** (new, ~2s)
- Sample 5 body pages of extracted text
- Check OCR artifact rate: ratio of non-dictionary words, garbled character sequences (`T5RFIELDLD5P`), broken ligatures
- Check encoding quality: Unicode errors, replacement characters, mojibake patterns
- Output: `text_quality` (clean / moderate / poor), `ocr_artifact_rate` (0.0-1.0)

**Step 3: Chapter Structure Assessment** (existing + new, ~3s)
- Check PDF bookmarks: count, depth, quality (do titles look real or garbled?)
- Run font detector: heading count, noise ratio (candidates vs likely real headings)
- Check if bookmarks align with font-detected headings (high alignment = trustworthy)
- Output: `chapter_source` (bookmarks / font_detection / claude_needed / none), `chapter_confidence`

**Step 4: Content Element Viability** (new, ~2s)
- **Footnotes:** Sample the Notes/Endnotes section (if detected). Are note numbers sequential? Is the text readable or garbled? Viability: viable / degraded / unusable
- **Index:** Sample the Index section. Are page numbers parseable? Are entries structured? Viability: viable / degraded / unusable
- **Hyperlinks:** Check PDF `/Link` annotations. Are there any? Do they have valid URIs? Viability: viable / none
- **Images:** Check for embedded images. Count, total size. Are they decorative or content-bearing?
- Output: per-element viability scores

**Step 5: Historical Data Lookup** (~instant)
- Query pattern DB for this exact book (by title/author/hash)
- Query pattern DB for same publisher/format aggregate
- Query pattern DB for same `source_type` aggregate
- Output: `historical_recommendation` (extraction path + flags + confidence), or null

**Step 6: Recipe Generation** (computation only)
- Combine all signals into a single recommendation
- Priority: historical data (if high confidence) > content analysis > classification defaults

---

## Output Schema

```json
{
  "file": "path/to/book.pdf",
  "analysis": {
    "source_type": "scan_with_text",
    "source_confidence": 0.85,
    "text_quality": "moderate",
    "ocr_artifact_rate": 0.23,
    "total_pages": 1102,
    "file_size_mb": 340,
    "chapter_structure": {
      "source": "bookmarks",
      "bookmark_count": 42,
      "font_candidates": 2040,
      "font_noise_ratio": 0.98,
      "confidence": 0.90
    },
    "content_viability": {
      "footnotes": "degraded",
      "index": "unusable",
      "hyperlinks": "none",
      "images": "decorative",
      "block_quotes": "viable"
    },
    "historical": {
      "book_match": false,
      "publisher_match": false,
      "source_type_match": true,
      "recommended_path": "legacy",
      "confidence": 0.6
    }
  },
  "recommendation": {
    "profile": "text-only",
    "extraction_path": "legacy",
    "flags": {
      "UseClaudeChapters": false,
      "UseHtmlExtraction": false,
      "NoIndex": true,
      "NoFootnotes": true,
      "ApplyAIFixes": false
    },
    "chapter_strategy": "bookmarks_only",
    "estimated_time_seconds": 45,
    "confidence": 0.85,
    "reasoning": [
      "Source is scan_with_text (31.4 KB/page, OCR layer present)",
      "Text quality moderate — 23% OCR artifact rate",
      "42 PDF bookmarks present and readable — using bookmarks for chapters",
      "Font detection found 2040 candidates (98% noise) — skipping Claude chapter detection",
      "Index is unusable (OCR garbling in page numbers) — stripping",
      "Footnotes degraded (OCR artifacts in note text) — stripping",
      "Historical: legacy extraction scores best for scan_with_text format"
    ]
  }
}
```

---

## Recommendation Rules (Decision Tree)

```
IF source_type == scan_no_text:
    profile = text-only
    extraction = ocr
    chapters = none (OCR text has no structure)
    skip: footnotes, index, hyperlinks, AI fixes, Claude chapters

ELIF source_type == scan_with_text:
    IF text_quality == poor (artifact_rate > 0.30):
        profile = text-only
        extraction = legacy
        chapters = bookmarks_only (if available) else none
        skip: footnotes, index, hyperlinks, AI fixes
    ELIF text_quality == moderate (artifact_rate 0.10-0.30):
        profile = clean-read
        extraction = legacy
        chapters = bookmarks (if available) else claude
        skip: index (if unusable), footnotes (if degraded)
    ELSE (text_quality == clean):
        profile = full
        extraction = html (pdfminer)
        chapters = font_detection + claude confirmation
        keep: all viable elements

ELIF source_type == digital_native:
    profile = full
    extraction = html (pdfminer)
    chapters = font_detection + claude confirmation
    keep: all elements
    IF historical_data.confidence >= 0.7:
        use historical extraction_path instead

EPUB:
    profile = full (EPUB content is already clean)
    extraction = epub_html
    chapters = ncx/nav (if sufficient) else claude
    keep: all elements
```

These rules are the starting defaults. As the pattern database accumulates data, historical recommendations override the rules for specific books and publishers.

---

## Integration with Convert-ToKindle

```powershell
function Convert-ToKindle {
    param(
        # ... existing params ...
        [switch]$SkipPreflight,          # bypass pre-flight, use explicit flags only
        [switch]$IgnoreRecommendation    # run pre-flight but don't apply recommendation
    )

    # Step 1: Pre-flight analysis (unless skipped)
    if (-not $SkipPreflight) {
        $preflight = & $python "tools/preflight_analysis.py" --input $InputFile --format json
        $recipe = $preflight | ConvertFrom-Json

        if (-not $IgnoreRecommendation) {
            # Apply recommendation as defaults (user flags override)
            if (-not $PSBoundParameters.ContainsKey('Profile')) {
                $Profile = $recipe.recommendation.profile
            }
            if (-not $PSBoundParameters.ContainsKey('UseHtmlExtraction')) {
                # Set extraction path from recommendation
            }
            # ... etc for each flag

            Write-EbookLog "Pre-flight: $($recipe.recommendation.reasoning -join '; ')"
            Write-EbookLog "Pre-flight: recommended profile=$($recipe.recommendation.profile), path=$($recipe.recommendation.extraction_path)"
        }

        # Log any user overrides
        if ($PSBoundParameters.ContainsKey('Profile') -and $Profile -ne $recipe.recommendation.profile) {
            Write-EbookLog "Pre-flight: user override — profile $Profile (recommended: $($recipe.recommendation.profile))" -Level WARN
        }
    }

    # Step 2: Proceed with conversion using resolved settings
    # ... existing conversion logic, now with intelligent defaults ...
}
```

---

## Key Design Principles

1. **Recommendation is the default.** User runs `Convert-ToKindle -InputFile "book.pdf"` with no flags -> pre-flight runs -> recommendation applied automatically. The user gets the best output without knowing anything about extraction paths, profiles, or flags.

2. **Explicit always wins.** Any flag the user sets overrides the recommendation. `-Profile full` on a scanned PDF? The pipeline respects it and tries. It might produce garbage, but the user asked for it.

3. **Transparent reasoning.** The log shows WHY the recommendation was made: "Source is scan_with_text, 23% OCR artifact rate, index unusable — recommending text-only profile." The user can learn from this and adjust next time.

4. **Fast.** Pre-flight must complete in <10 seconds for any document. It samples, it doesn't exhaustively analyze. A 1000-page book should take the same time as a 100-page book.

5. **Accumulating intelligence.** Every conversion result feeds back into the pattern database. The first time you convert a publisher's book, you get rule-based defaults. The second time, you get data-driven recommendations. The tenth time, the system knows exactly what works.

6. **Graceful override.** `-SkipPreflight` bypasses the entire system. `-IgnoreRecommendation` runs the analysis (logged for reference) but doesn't apply it. Both are escape hatches for power users.

---

## Content Viability Assessment — Detail

The viability check is the genuinely new piece. Everything else (classification, font detection, pattern DB) exists. Here's how viability works:

### Footnote Viability

Sample the first 10 endnotes from the Notes section:
- **viable:** >80% of notes have sequential numbers, readable text, no garbled characters
- **degraded:** 50-80% readable, some OCR artifacts but mostly parseable
- **unusable:** <50% readable, garbled numbers, broken text

### Index Viability

Sample 20 index entries:
- **viable:** entries have recognizable structure (term + page numbers), numbers are parseable
- **degraded:** some entries garbled, page numbers partially broken
- **unusable:** entries are garbled OCR noise (like Ezekiel's index)

### Hyperlink Viability

Check PDF `/Link` annotations:
- **viable:** links exist with valid URIs
- **none:** no link annotations found

### Detection Approach

Use existing PyMuPDF/pypdf to read the relevant sections. For footnotes and index, the back-matter detection in `format_paragraphs_as_html()` already identifies these sections — we just need to sample and assess quality rather than extract.

---

## Migration Path

1. **Phase 1** (this spec): `preflight_analysis.py` produces recommendations. `Convert-ToKindle` applies them as defaults. All existing flags and behaviors work unchanged.

2. **Phase 2** (future): Pre-flight powers the converge loop's strategy selection. Instead of hardcoded strategy sequences, the loop starts with the pre-flight recommendation and only deviates if the first attempt fails.

3. **Phase 3** (future): Pre-flight feeds the web service (SCRUM-51). Upload a PDF -> instant analysis -> show the user what they'll get + recommended profile -> convert with one click.

---

## Dependencies

- **Conversion Profiles** must be merged first (provides `--Profile` and `--No*` flags that the recommendation sets)
- `classify_source.py` — existing, will be inlined or called
- `detect_headings_font.py` — existing, will be called
- `pattern_db.py` — existing, will be queried
- PyMuPDF, pypdf, BeautifulSoup — all already installed

---

## Files Summary

| File | Change |
|---|---|
| `tools/preflight_analysis.py` | NEW — unified analysis + recommendation engine |
| `module/EbookAutomation.psm1` | MODIFY — `Convert-ToKindle` auto-applies pre-flight recommendation; new `-SkipPreflight` and `-IgnoreRecommendation` switches |
| `config/settings.json` | MODIFY — optional preflight config block for tunable thresholds |
| `tools/classify_source.py` | NO CHANGE — called by preflight, not modified |
| `tools/detect_headings_font.py` | NO CHANGE — called by preflight, not modified |
| `tools/pattern_db.py` | NO CHANGE — queried by preflight, not modified |
