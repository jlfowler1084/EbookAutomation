# EbookAutomation API Call Registry

Documents every outbound API call in the project. Updated whenever a call is added or modified.

**Last audited:** 2026-03-25

| # | File | Function | Service | Model | Purpose | Trigger | Cost/Call |
|---|------|----------|---------|-------|---------|---------|-----------|
| 1 | `tools/pdf_to_balabolka.py` | `ai_detect_subheadings()` | Anthropic | haiku | Classify candidate paragraphs as subheadings | Auto (no bookmarks + API key) | ~$0.003-0.01 |
| 2 | `tools/pdf_to_balabolka.py` | `ai_rejoin_fragments()` | Anthropic | haiku | Verify page-boundary paragraph splits | Auto (API key + >=10 paragraphs) | ~$0.003-0.015 |
| 3 | `tools/pdf_to_balabolka.py` | `ai_quality_pass()` detect | Anthropic | haiku | Detect extraction artifacts in sampled text | Auto (API key + >=5 paragraphs + gate passes) | ~$0.006-0.015 |
| 4 | `tools/pdf_to_balabolka.py` | `ai_quality_pass()` verify | Anthropic | haiku | Verify automated fixes were correct | `--apply-ai-fixes` + issues found | ~$0.006-0.015 |
| 5 | `tools/pdf_to_balabolka.py` | `extract_text_vision()` | Anthropic Vision | sonnet | Full-page OCR for scanned PDFs (Tier 3) | `--use-vision` | ~$0.02-0.04/page |
| 6 | `tools/gemini_ocr.py` | `extract_text_gemini()` | Google Gemini | gemini-2.5-flash | Full-book OCR transcription (Tier 2.5) | `--use-gemini` | ~$0.50/book |
| 7 | `tools/gemini_ocr.py` | `remediate_pages_gemini()` | Google Gemini | gemini-2.5-flash | Re-extract low-quality pages | `--gemini-remediate` | ~$0.002/page |
| 8 | `tools/visual_qa.py` | `call_claude_vision()` | Anthropic Vision | sonnet | Evaluate rendered pages against QA rubric | `-ValidateVisual` / `--vqa` | ~$0.20-0.35/book |
| 9 | `module/EbookAutomation.psm1` | `Get-ChapterStructure` via `Send-ToClaudeAPI` | Anthropic | sonnet | Detect chapter/part headings from text | `-UseClaudeChapters` or auto | ~$0.05/book |
| 10 | `tools/email_to_kindle.py` | `send_file()` | Gmail SMTP | -- | Email ebook to Kindle | `-EmailToKindle` | $0.00 |
| 11 | `tools/foh_scraper.py` | `fetch_thread_page()` | HTTP GET | -- | Scrape FOH forum posts | Manual CLI | $0.00 |

## Model Selection Reference

| Task Type | Model Tier | Examples |
|-----------|-----------|----------|
| Binary classification (yes/no per item) | Haiku | Subheading detection, paragraph rejoin, artifact detection |
| Structured extraction with short context | Haiku | Quality scoring, fix verification |
| Multi-level structural reasoning | Sonnet | Chapter/part hierarchy detection |
| Vision + nuanced assessment | Sonnet | Visual QA rubric scoring, Vision OCR |
| Cost-effective OCR | Gemini Flash | Full-book transcription, page remediation |
| Data relay / search / SMTP | NO AI | Email delivery, forum scraping |

## Configuration

Model strings are defined in `config/settings.json` under `api_models`:

```json
"api_models": {
    "haiku":          "claude-haiku-4-5-20251001",
    "sonnet":         "claude-sonnet-4-20250514",
    "sonnet_latest":  "claude-sonnet-4-6",
    "gemini_flash":   "gemini-2.5-flash"
}
```

To switch models, edit `settings.json` -- no code changes needed.

<!-- Add new entries above this line. -->
