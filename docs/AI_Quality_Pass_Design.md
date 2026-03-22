# AI Quality Pass — Architecture Design

## Overview

A post-processing Claude API pass that runs after all regex-based cleanup phases, detecting and fixing issues that require contextual understanding. Integrates into the existing Convert-ToKindle pipeline alongside -UseClaudeChapters.

## Pipeline Position
PDF → Extract Text → clean_and_join() → fix_ocr_artifacts() (Phases 0-9)
→ [AI Quality Pass] ← NEW
→ detect_chapters() / apply_chapter_hints()
→ format_output() → Calibre → KFX

The pass runs AFTER regex cleanup but BEFORE chapter heading placement, so corrections are in place before the final structure is built.

## Three API Calls (per book)

### Call 1: Quality Scan (required)
**Purpose:** Score overall extraction quality and flag specific issues.
**Input:** 15-20 sampled paragraphs from evenly spaced positions in the text (first 10%, middle, last 10%, plus random).
**Prompt:** "You are a text extraction quality checker. These paragraphs were extracted from a PDF. Flag any issues: split words (e.g., 'traffi cking'), orphaned fragments, footnote numbers that should be stripped, running headers bleeding into text, garbled text, encoding artifacts. Return JSON."
**Output JSON:**
```json
{
  "quality_score": 85,
  "issues": [
    {"type": "split_word", "text": "traffi cking", "fix": "trafficking", "paragraph_index": 42},
    {"type": "orphaned_fragment", "text": "ience 21", "paragraph_index": 156},
    {"type": "footnote_number", "text": "5 They compete", "fix": "They compete", "paragraph_index": 78},
    {"type": "running_header", "text": "The State Reaction and", "paragraph_index": 203}
  ],
  "recommendations": ["Book has extensive ligature splits — consider re-extracting with pdfminer"]
}
```
**Cost:** ~$0.01 per book (small input, structured output)

### Call 2: Sub-heading Detection (conditional — only if quality_score < 90 or book has complex structure)
**Purpose:** Find section headings merged into body paragraphs.
**Input:** Paragraphs longer than 200 chars that contain potential heading patterns (short capitalized phrases followed by topic changes).
**Prompt:** "These paragraphs may contain section headings that were merged into body text during PDF extraction. Identify any embedded headings that should be on their own line. A heading is a short phrase (2-8 words) that introduces a new topic. Return the heading text and its position."
**Output JSON:**
```json
{
  "embedded_headings": [
    {"paragraph_index": 412, "heading_text": "The Territorial Type", "split_before": "The Territorial Type"},
    {"paragraph_index": 890, "heading_text": "A Typology of Illicit Networks", "split_before": "A Typology"}
  ]
}
```
**Cost:** ~$0.01-0.02 per book

### Call 3: Targeted Fixes (conditional — only if Call 1 finds fixable issues)
**Purpose:** Fix specific issues that Call 1 identified but couldn't resolve from samples alone.
**Input:** The actual paragraphs containing flagged issues, with surrounding context (1 paragraph before/after).
**Prompt:** "Fix these specific text extraction issues. For each paragraph, return the corrected text. Preserve all content — only fix extraction artifacts, don't edit the author's words."
**Output JSON:**
```json
{
  "fixes": [
    {"paragraph_index": 42, "original": "...tra ffi cking-oriented...", "corrected": "...trafficking-oriented..."},
    {"paragraph_index": 78, "original": "5 They compete with states...", "corrected": "They compete with states..."}
  ]
}
```
**Cost:** ~$0.01-0.03 per book (depends on issue count)

## Total Cost Per Book: $0.02-0.06

## Integration Points

### Python (pdf_to_balabolka.py)
- New function: `ai_quality_pass(paragraphs, log, api_key=None)`
- Runs after Phase 9, before chapter detection
- Accepts optional API key (falls back to environment variable ANTHROPIC_API_KEY)
- Returns modified paragraphs + quality report dict
- Skips entirely if no API key available (graceful degradation)

### PowerShell (EbookAutomation.psm1)
- New parameter: `-ValidateQuality` on Convert-ToKindle (or automatic if API key exists)
- Passes API key to Python script via `--api-key` or environment variable
- Logs quality score and issue count
- Quality report saved alongside output files as `{book}_quality_report.json`

### Quality Report Output
Saved as JSON alongside the KFX, containing:
- Quality score (0-100)
- Issues found and fixed
- Issues found but unfixable (flagged for human review)
- Recommendations
- API cost for this book

## Implementation Phases

### Phase 1: Quality Scan Only (MVP — build first)
- Implement Call 1 only
- Sample paragraphs, send to Claude, get quality score + issue list
- Log results but don't auto-fix yet
- This alone replaces the "silently marked clean" problem

### Phase 2: Auto-Fix Integration
- Implement Call 3 (targeted fixes)
- Apply fixes automatically when confidence is high
- Flag low-confidence fixes for review

### Phase 3: Sub-heading Detection
- Implement Call 2
- Split paragraphs at detected heading boundaries
- Add detected headings to the chapter structure

### Phase 4: Feedback Loop
- Store quality reports in book metadata cache (future)
- Use historical data to improve regex phases (if many books hit the same issue, add a new Phase)
- Track quality scores over time to measure pipeline improvement

## API Integration Pattern (reuse existing)
```python
import requests

def call_claude_api(prompt, system_prompt, max_tokens=2000):
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    return response.json()
```

## Sampling Strategy
- Total paragraphs in book: N
- Sample size: min(20, N * 0.10) — 10% up to 20 paragraphs
- Distribution: 3 from first 5%, 3 from last 5%, 14 evenly spaced from middle
- Always include: first paragraph, last paragraph, longest paragraph, shortest paragraph over 50 chars
- For Call 2 (sub-headings): only paragraphs > 200 chars with mixed-case patterns

## Error Handling
- API timeout: skip quality pass, log warning, continue with regex-only output
- API error: same — graceful degradation, never block conversion
- Invalid JSON response: retry once, then skip
- Rate limiting: add 1-second delay between calls

## Configuration
```json
{
  "ai_quality_pass": {
    "enabled": true,
    "auto_fix": true,
    "min_quality_score_for_skip": 95,
    "max_api_cost_per_book": 0.10,
    "model": "claude-sonnet-4-20250514"
  }
}
```
