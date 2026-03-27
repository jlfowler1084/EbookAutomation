# Structure Analysis Agent — Contract

## Identity

| Field | Value |
|-------|-------|
| Agent Name | Structure Analysis |
| Version | 1.0.0 |
| Owner | EbookAutomation pipeline |
| Claude Model | claude-sonnet-4-6 (default) / claude-opus-4-6 (complex books) |
| Max Tokens | 4096 |
| Prompt File | `agents/structure-analysis/system-prompt.md` |

## When to Invoke

| Scenario | Trigger | Who Calls |
|----------|---------|-----------|
| Pipeline conversion | `Convert-ToTTS -UseClaudeChapters` or `Convert-ToKindle` auto-detection | `Get-ChapterStructure` (automated) |
| Manual diagnostics | Developer investigating chapter detection issues on a specific book | Developer via `Invoke-StructureAgent` (manual) |
| Pre-flight check | Evaluating a book's convertibility before committing to full pipeline | `preflight_analysis.py` or developer |
| Batch evaluation | Testing detection accuracy across test corpus | `Invoke-BatchQA` / test harness |

## Input Contract

The agent accepts a single user message containing one or both sections:

### Required: Text Samples

Raw extracted text, either:
- Full text (for books <9000 words)
- Three-zone sampled text (for longer books): front 3000 words + 8 body samples of 500 words + last 2000 words

### Optional: Font Candidates

Output from `detect_headings_font.py`, formatted as a labeled section prepended to the text samples. When present, the agent treats these as primary evidence and uses text samples for confirmation.

### Input Assembly (pseudocode)

```
input = ""
if font_candidates exist:
    input += format_font_candidates(candidates)
    input += "\n\n"
input += "TEXT SAMPLES:\n\n" + sampled_text
```

## Output Contract

### Success: JSON Array

A raw JSON array (no markdown fences, no surrounding text). Each element:

```json
{
  "title": "Chapter 1: The Beginning",
  "level": 2,
  "is_back_matter": false,
  "page_estimate": 15,
  "confidence": 0.92,
  "notes": ""
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| title | string | yes | Exact heading text, preserving original capitalization |
| level | int (1–3) | yes | 1=Part/Book/Volume, 2=Chapter, 3=Sub-section |
| is_back_matter | boolean | yes | True for Notes, Bibliography, Index, Appendix, Glossary |
| page_estimate | int | no | Approximate page number (from position in text or font candidate data) |
| confidence | float (0.0–1.0) | yes | Detection confidence. Pipeline ignores entries below 0.50 |
| notes | string | no | Explanation for ambiguous entries or special handling |

### Failure Modes

| Condition | Agent Returns | Pipeline Action |
|-----------|--------------|-----------------|
| API call fails | `$null` | Log warning, skip chapter detection, fall back to regex headings |
| No chapters detected | Empty array `[]` | Log warning, fall back to regex headings |
| JSON parse error | `$null` (after parse failure) | Log error, fall back to regex headings |

## Downstream Consumers

| Consumer | What It Uses | How |
|----------|-------------|-----|
| `Convert-ToTTS` → `pdf_to_balabolka.py` | Title + level | Writes chapter hints JSON → `--chapter-hints` flag → `apply_chapter_hints()` fuzzy matching |
| `Convert-ToKindle` → `pdf_to_balabolka.py --mode kindle` | Title + level | Same hints JSON → Markdown heading output (`#` / `##`) for Calibre TOC detection |
| `Invoke-ConvergeLoop` | Cached hints JSON | Reuses iteration-1 detection for subsequent iterations (avoids redundant API calls) |
| Batch QA reports | Title + confidence | Quality metrics — average confidence, detection count vs. expected |

## Boundaries

### This Agent MUST NOT:
- Modify any files on disk
- Call any other agents
- Make decisions about TTS voices, Kindle formatting, or audio production
- Assess text quality or suggest OCR fixes
- Return anything other than the JSON array (no commentary, no markdown)

### This Agent DOES NOT KNOW ABOUT:
- Balabolka, balcon.exe, or any TTS technology
- Calibre, KFX, or Kindle formatting
- The FOH scraper or brief generation
- Other agents in the pipeline
- The user's preferences for voice tagging

This isolation is intentional. The agent's accuracy comes from focusing entirely on document structure.
