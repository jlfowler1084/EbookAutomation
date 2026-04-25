# Visual QA Rubric — Ebook Conversion Quality Evaluation

You are evaluating the visual rendering quality of a converted ebook (KFX/AZW3/EPUB). You will receive PNG images of sampled pages from the book. Evaluate each page against the categories below, then produce an overall assessment.

## Evaluation Categories

### 1. Text Integrity (25%)
- No garbled, mojibake, or encoding-artifact characters
- No missing text or truncated paragraphs
- No OCR debris (random symbols, stray characters between words)
- Ligatures render correctly (fi, fl, ff, ffi, ffl)
- Special characters (em-dashes, smart quotes, ellipses) display properly
- No corrupted Unicode (replacement characters, boxes)

### 2. Heading Formatting (20%)
- Chapter titles are visually distinct from body text (larger, bolder, or different style)
- Heading hierarchy is consistent (Part > Chapter > Section)
- Headings have appropriate spacing above and below
- No body text styled as headings (false positives)
- No headings styled as body text (missed headings)
- Chapter numbering (if present) is consistent and sequential

### 3. Paragraph Flow (20%)
- Consistent paragraph spacing throughout
- No mid-sentence line breaks or orphaned words
- Proper indentation (first-line indent OR block spacing, consistently applied)
- No widow/orphan disasters (single lines stranded at page top/bottom)
- Hyphenation is reasonable (no excessive or mid-word breaks)
- Text flows naturally — no jarring jumps or gaps

### 4. TOC & Navigation (15%)
- Table of Contents page is present (if applicable — check early pages)
- TOC entries match actual chapter titles in the book
- TOC hierarchy reflects the book's structure (Parts > Chapters > Sections)
- Page numbers or links in TOC appear functional
- No duplicate or phantom TOC entries
- No footnote references misidentified as TOC entries

### 5. Cover & Images (10%)
- Cover image renders (not blank, not missing, not a text-only page)
- Cover is not distorted, stretched, or cropped incorrectly
- Inline images (if any) are not overlapping text
- Image resolution is acceptable (not pixelated beyond recognition)
- No large blank rectangles where images should be

### 6. Page Layout (10%)
- Reasonable margins on all sides (text not running off edges)
- No giant blank voids in the middle of pages
- Consistent formatting across pages (font size, style, margins)
- Headers/footers (if present) are correctly positioned
- No text overlapping or clipping at page boundaries
- Running headers/page numbers properly stripped (no "Chapter 3 | 47" in body text)

## Scoring Instructions

For each page, assign:
- **score**: 0-100 (weighted by the categories above)
- **pass**: true if score >= 70, false otherwise
- **page_type**: one of "cover", "toc", "front_matter", "chapter_start", "body", "back_matter"

For each issue found, provide:
- **category**: one of "text_integrity", "heading_formatting", "paragraph_flow", "toc_navigation", "cover_images", "page_layout"
- **severity**: "critical" (renders unreadable), "moderate" (noticeable quality issue), "minor" (cosmetic/nitpick)
- **description**: specific description of the issue
- **suggestion**: actionable fix suggestion (reference HTML tags, CSS, or extraction logic where possible)

## Output Format

Return valid JSON with this exact structure:

```json
{
  "pages": [
    {
      "page_number": 1,
      "page_type": "cover",
      "score": 85,
      "pass": true,
      "issues": [
        {
          "category": "cover_images",
          "severity": "minor",
          "description": "Cover image has slight compression artifacts at bottom edge",
          "suggestion": "Re-extract cover at higher DPI or from alternate source"
        }
      ]
    }
  ],
  "overall_score": 82,
  "overall_pass": true,
  "category_scores": {
    "text_integrity": 90,
    "heading_formatting": 75,
    "paragraph_flow": 85,
    "toc_navigation": 80,
    "cover_images": 70,
    "page_layout": 90
  },
  "summary": "One-paragraph overall assessment of the book's rendering quality, highlighting the most important issues and strengths.",
  "top_issues": [
    {
      "category": "heading_formatting",
      "severity": "moderate",
      "description": "Inconsistent heading font between chapters",
      "affected_pages": [5, 23, 41],
      "suggestion": "Check HTML heading tags for inline style overrides"
    }
  ]
}
```

## Important Notes

- Evaluate what you SEE in the rendered pages, not what you think the source might contain
- A blank or nearly-blank page is not necessarily an error — it may be a section divider
- Academic books may have footnotes, bibliography sections, and dense formatting — this is expected
- Score relative to what a commercially published ebook looks like on a Kindle
- If a page has no issues, return an empty issues array and a high score
- The "top_issues" array should contain the 3-5 most impactful issues across all pages, with affected_pages listing every page where each issue appears

## Report Metadata: `evaluation_status` Field (SCRUM-318)

Every VQA report JSON emitted by `visual_qa.py` includes a top-level `evaluation_status` field.
Downstream consumers (agents, CI gates, compare scripts) must read this field before
interpreting `overall_score` and `overall_pass`.

| Value | Meaning | `overall_score` | `overall_pass` |
|---|---|---|---|
| `evaluated` | All (or some) API batches succeeded; pages were scored normally. | Integer 0–100 | Boolean |
| `api_failure` | Every API batch failed (network error, auth error, timeout, etc.); no pages were scored. | `null` | `null` |
| `conversion_failure` | The KFX→PDF or PDF→PNG conversion step failed before any pages could be evaluated. | `null` | `null` |
| `no_pages_sampled` | The page-sampling step returned an empty list (e.g. zero-page PDF); nothing to evaluate. | `null` | `null` |

**Consumer contract:** When `evaluation_status != "evaluated"`, both `overall_score` and
`overall_pass` are `null` (Python `None`). Consumers must NOT treat `overall_pass=null` as
`False` or `overall_score=null` as `0`. A `null` score means the evaluation did not run, not
that the book failed quality checks. Use `evaluation_status` as the authoritative discriminant.
