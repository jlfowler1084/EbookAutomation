# VQA Quality Baseline -- 37 Structurally-Passing Books

**Date:** 2026-03-24
**Run ID:** `batch_20260324_100208`
**Mode:** Full (HTML + KFX + Visual QA), parallel 2

## Summary

| Metric | Value |
|--------|-------|
| Books processed | 37 |
| KFX conversion succeeded | 35 (95%) |
| VQA scored | 34 (92%) |
| Average VQA score | 57.9 |
| Median VQA score | 58 |
| Score range | 33 - 81 |
| Estimated API cost | ~$1.36 (34 books x ~$0.04) |
| Duration | 111 minutes |

### Key Finding

**Structural extraction quality != visual output quality.** Of 37 books that passed structural checks (text extracted, chapters detected), only 5 (15%) scored above 70 on Visual QA. The pipeline extracts text well but the Kindle conversion output has significant quality issues.

## Score Distribution

| Tier | Range | Count | Pct | Meaning |
|------|-------|-------|-----|---------|
| A (Excellent) | 85+ | 0 | 0% | Ready for Kindle, minimal issues |
| B (Good) | 70-84 | 5 | 15% | Usable, some minor quality issues |
| C (Needs Work) | 55-69 | 14 | 41% | Readable but noticeable problems |
| D (Poor) | <55 | 15 | 44% | Significant quality issues |

## Category Averages (weighted per rubric)

| Category | Weight | Average | Below 70 | Assessment |
|----------|--------|---------|----------|------------|
| page_layout | 10% | 89.9 | 0/27 | Strong |
| cover_images | 10% | 89.9 | 0/33 | Strong |
| heading_formatting | 20% | 88.7 | 1/34 | Strong |
| paragraph_flow | 20% | 84.6 | 0/34 | Good |
| text_integrity | 25% | 75.9 | 11/33 | Weak -- systemic issue |
| toc_navigation | 15% | 66.8 | 4/14 | Weakest -- systemic issue |

## Systemic Weakness Analysis

### 1. TOC & Navigation (avg 66.8, weakest category)

The lowest average across all categories. Only 14 of 34 books received TOC scores (the rubric may skip it for books without detected TOC). Of those 14, 4 scored below 70. Key issue: many books lack a functional TOC in KFX output, or the TOC entries don't match actual chapter locations.

**Impact:** 15% weight in overall score. Fixing TOC generation for these books would raise their overall scores by ~5-8 points each.

### 2. Text Integrity (avg 75.9, highest book count below 70)

11 of 33 scored books had text_integrity below 70. This is the highest-impact category:
- 25% weight in overall score
- Issues include: garbled characters, OCR artifacts, encoding errors, missing or corrupted text passages
- Affects the widest range of books

**Impact:** 25% weight. The single most impactful category to fix. Improving text_integrity from 50 to 80 on the bottom 11 books would raise their overall scores by ~7.5 points each.

## Tier B Books (Good, 70-84)

| Score | Book |
|-------|------|
| 81 | The Return of the Gods (Jonathan Cahn) |
| 78 | Demons (Michael S. Heiser) |
| 76 | Decline of the West (Oswald Spengler) |
| 74 | Designing Data-Intensive Applications (Kleppmann) |
| 71 | The PowerShell Scripting & Toolmaking Book |

These 5 books are the current "gold standard" -- the pipeline produces usable Kindle output for them. Common traits: clean digital PDFs, clear chapter structure, minimal footnotes.

## Tier D Books (Poor, <55) -- Worst Category Detail

| Score | Book | Worst Category |
|-------|------|----------------|
| 33 | Kabbalah (Ginsburg) | text_integrity=37 |
| 36 | Into the Fringe (Turner) | text_integrity=49 |
| 40 | The Tempest (Shakespeare) | text_integrity=56 |
| 40 | qabbalahphilosop00myer | cover_images=75 |
| 41 | Adult Children of Alcoholics | text_integrity=69 |
| 44 | Public Finance (Gruber) | text_integrity=51 |
| 44 | Formation of a Persecuting Society | text_integrity=60 |
| 51 | Ezekiel II (Zimmerli) | text_integrity=52 |
| 51 | Scytl Election Results User Guide | page_layout=79 |
| 52 | Unholy Alliance (Levanda) | text_integrity=48 |
| 53 | Prompt Engineering (Tabatabaian) | text_integrity=62 |
| 53 | Readings in Database Systems | text_integrity=67 |
| 53 | Rhetorical Function of Ezekiel (Renz) | heading_formatting=70 |
| 54 | Artful Relic (Casper) | paragraph_flow=70 |
| 54 | Beginning of Wisdom (Kass) | text_integrity=67 |

Text integrity is the dominant weakness in Tier D -- 10 of 15 books have it as their worst or second-worst category.

## KFX Conversion Failures (2 books)

| Book | Notes |
|------|-------|
| Cooper - The Oil Kings | KFX conversion failed (Calibre error) |
| Coulter - Occult Holidays | KFX conversion failed (Calibre error) |

These books extracted HTML successfully but Calibre couldn't produce KFX. VQA was skipped for both.

## VQA Cost Tracking Note

The batch report shows $0.00 API cost, but VQA durations (100-200s per book) confirm real API calls were made. The `visual_qa.py` cost tracking field isn't being populated in the report JSON. Estimated actual cost: ~$1.36 (34 books x ~$0.04/book).

## Recommendations

### Priority 1: Fix text_integrity (highest impact)

Text integrity affects the most books (11 below 70) and has the highest rubric weight (25%). Root causes to investigate:
- OCR artifacts surviving the cleanup pass
- Encoding errors in extracted text
- Missing or garbled characters from font mapping issues
- Page numbers or headers leaking into body text

### Priority 2: Fix TOC generation

TOC navigation has the lowest average (66.8) and 15% weight. Many books either lack a TOC entirely in KFX output or have TOC entries that don't navigate correctly. The `Get-ChapterStructure` heading detection feeds directly into Calibre's TOC -- improving chapter detection would improve TOC quality.

### Priority 3: Investigate KFX conversion failures

2 of 37 books (5%) failed KFX conversion entirely. These need Calibre error log analysis to determine root cause.

### Priority 4: Establish VQA regression baseline

The 5 Tier B books should be added to the test corpus as VQA regression targets. Any pipeline change should verify these books maintain their scores.

## Projected Impact

| Fix | Books Affected | Avg Score Increase | New Tier B+ Count |
|-----|---------------|-------------------|-------------------|
| Text integrity cleanup | 11 | +7-8 points | ~8-12 |
| TOC generation fix | 4-10 | +5-8 points | ~10-15 |
| Combined | ~15 | +10-15 points | ~15-20 |

A realistic target after text_integrity and TOC fixes: **40-55% of books in Tier B or above** (up from current 15%).
