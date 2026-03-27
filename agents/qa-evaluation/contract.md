# QA Evaluation Agent — Contract

## Identity

| Field | Value |
|-------|-------|
| Agent Name | QA Evaluation |
| Version | 1.0.0 |
| Owner | EbookAutomation pipeline |
| Claude Model | claude-sonnet-4-6 (default) |
| Max Tokens | 8192 (large — must return per-page JSON for up to 20 pages) |
| Prompt File | `agents/qa-evaluation/system-prompt.md` |
| Legacy Prompt File | `tools/visual_qa_rubric.md` (predecessor — will be replaced) |

## When to Invoke

| Scenario | Trigger | Who Calls |
|----------|---------|-----------|
| Pipeline conversion with VQA | `Convert-ToKindle -ValidateVisual` or `Invoke-EbookPipeline -ValidateVisual` | `Test-ConversionQuality` → `visual_qa.py` (automated) |
| Converge loop iteration | Each iteration of `Invoke-ConvergeLoop` evaluates the latest output | `Invoke-ConvergeLoop` → `Test-ConversionQuality` (automated) |
| Manual spot-check | Developer evaluating a specific converted file | Developer via `Test-ConversionQuality` (manual) |
| Batch evaluation | Quality scoring across test corpus | `batch_qa.py --vqa` (automated) |

## Input Contract

The agent receives its input as a Claude Vision API request, NOT as a standard text-only message. The input consists of:

### Required: Page Images

PNG images of rendered ebook pages, sent as base64-encoded image content blocks. Each image is preceded by a text label identifying the page number:

```
--- Page 1 ---
[image: base64 PNG of page 1]
--- Page 3 ---
[image: base64 PNG of page 3]
...
```

### Image Specifications

| Parameter | Quick Mode (default) | Full Mode |
|-----------|---------------------|-----------|
| DPI | 100 | 150 |
| Max pages | 8 | 20 |
| Batch size | 5 pages per API call | 5 pages per API call |
| Estimated cost | $0.04–0.07 | $0.20–0.35 |

### Page Selection Strategy

Pages are selected by `visual_qa.py`'s `select_sample_pages()` function, prioritized as:
1. Page 1 (cover/title)
2. Pages 2–4 (front matter/TOC)
3. First page of each chapter (from PDF bookmarks)
4. 1 random body page per ~50 pages
5. Last 2 pages (back matter)

The agent does NOT control page selection — it evaluates whatever pages are provided.

### Input Assembly

The system prompt is loaded from `agents/qa-evaluation/system-prompt.md` and sent as the `system` parameter. Page images and the evaluation instruction are sent as the `messages[0].content` array (multimodal: text + image blocks).

```python
payload = {
    "model": model,
    "max_tokens": 8192,
    "system": rubric_text,  # loaded from system-prompt.md
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "--- Page 1 ---"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
            {"type": "text", "text": "--- Page 3 ---"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
            {"type": "text", "text": "Evaluate all pages above against the rubric. Return ONLY valid JSON..."}
        ]
    }]
}
```

## Output Contract

### Success: JSON Object

A JSON object (no markdown fences, no surrounding text) containing:

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
          "description": "Cover image slightly pixelated at edges",
          "suggestion": "Re-render at higher DPI if source allows"
        }
      ]
    }
  ]
}
```

### Per-Page Object Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| page_number | int | yes | The page number as labeled in the input |
| page_type | string | yes | One of: `cover`, `toc`, `front_matter`, `chapter_start`, `body`, `back_matter` |
| score | int (0–100) | yes | Weighted average of applicable category scores |
| pass | boolean | yes | Whether the page meets the pass threshold |
| issues | array | yes | Array of issue objects (may be empty for clean pages) |

### Per-Issue Object Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| category | string | yes | One of: `text_integrity`, `heading_formatting`, `paragraph_flow`, `toc_navigation`, `cover_images`, `page_layout` |
| severity | string | yes | One of: `critical`, `major`, `moderate`, `minor` |
| description | string | yes | Human-readable description of the specific issue |
| suggestion | string | no | Actionable remediation suggestion |

### Failure Modes

| Condition | Agent Returns | Pipeline Action |
|-----------|--------------|-----------------|
| API call fails | Exception raised | Log error, skip VQA for this book, continue pipeline |
| No pages rendered | N/A (agent not called) | Log warning, skip VQA |
| Partial batch failure | Results from successful batches only | Merge available results, note incomplete evaluation |
| JSON parse error | Raw text (unparseable) | `visual_qa.py` logs error, returns score 0 |

## Downstream Consumers

| Consumer | What It Uses | How |
|----------|-------------|-----|
| `Invoke-ConvergeLoop` | `overall_score`, `overall_pass` | Decides whether to accept conversion or iterate with different strategy |
| `Test-ConversionQuality` | Full report object | Logs summary, writes `_visual_qa_report.json` alongside output file |
| `batch_qa.py` | `score`, `category_scores`, `api_cost_usd` | Aggregates across batch for quality reports and trend analysis |
| Pattern database | `category_scores`, `top_issues` | Historical quality tracking per book, publisher pattern detection |
| Converge loop strategy selection | `top_issues[].category` | Identifies which categories need improvement, informs next iteration strategy |

## Relationship to Structural QA

This agent handles **visual quality evaluation** (AI-powered, image-based, costs money).

**Structural QA** (`batch_qa.py`, `test_pipeline.py`) handles rule-based text analysis: chapter counts, ligature splits, footnote linking, heading hierarchy. Structural QA is deterministic, free, and runs on every conversion.

The two systems are complementary:
- Structural QA catches mechanical failures (zero chapters detected, broken footnotes)
- QA Evaluation Agent catches perceptual failures (text looks wrong, headings not visually distinct, layout broken)

A book can pass structural QA and fail visual QA (looks bad despite correct structure) or vice versa.

## Boundaries

### This Agent MUST NOT:
- Modify any files on disk
- Call any other agents
- Make decisions about whether to re-run the pipeline (that's the converge loop's job)
- Attempt to fix issues it identifies
- Evaluate text quality from raw text (that's a different function in `pdf_to_balabolka.py`)
- Access the source PDF — it only sees rendered page images of the output

### This Agent DOES NOT KNOW ABOUT:
- How the text was extracted (pdfminer, pypdf, OCR, Gemini)
- What extraction tier produced this output
- The converge loop or iteration strategy
- Other agents in the pipeline
- The source file format or quality
- Cost constraints or API budgets

This isolation is intentional. The agent evaluates the output purely on its visual merits, without bias from knowing the extraction method or iteration count.

## Cost Profile

| Mode | Pages | DPI | Typical Cost | Use Case |
|------|-------|-----|-------------|----------|
| Quick | 8 | 100 | $0.04–0.07 | Default for all conversions |
| Full | 20 | 150 | $0.20–0.35 | Major milestones, shipping to users, quarterly quality checks |

**Cost discipline rule:** Quick mode is the default. Full mode requires explicit opt-in (`--full` / `-FullVQA`). Never auto-include full VQA in prompts or pipeline defaults without explicit justification.
