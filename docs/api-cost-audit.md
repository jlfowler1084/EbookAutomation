# EbookAutomation API Cost Audit

**Date:** 2026-03-25
**Audited by:** Claude (Opus 4.6)

## Summary

| Metric | Value |
|--------|-------|
| Total API call sites | 11 |
| Paid AI call sites | 8 |
| Free/no-cost call sites | 3 |
| Services used | Anthropic Claude, Google Gemini, Gmail SMTP |
| Models in use | Haiku (4 calls), Sonnet (3 calls), Gemini Flash (2 calls) |

## Monthly Cost Estimates (10 books/month)

| Scenario | Before | After | Savings |
|----------|--------|-------|---------|
| Auto-triggers only (no opt-in flags) | $1.50-3.00 | $0.45-0.90 | ~70% |
| + Gemini full-book on 2 scanned PDFs | $2.50-4.00 | $1.45-1.90 | ~50% |
| + Visual QA on all books | $3.50-6.50 | $2.45-3.90 | ~40% |
| Maximum (all features, all books) | $10-20 | $5-10 | ~50% |

## Changes Implemented

### Haiku Downgrades (4 calls)

| Function | Task Type | Why Haiku Suffices |
|----------|-----------|-------------------|
| `ai_detect_subheadings()` | Binary classification | Simple yes/no per candidate paragraph |
| `ai_rejoin_fragments()` | Binary classification | Join or don't join, short context window |
| `ai_quality_pass()` detect | Structured extraction | Pattern matching with structured JSON output |
| `ai_quality_pass()` verify | Same as detect | Same reasoning, same output format |

### Rules-Based Quality Gate

Added regex pre-check before `ai_quality_pass()`. Checks sampled paragraphs for 7 known artifact patterns (camelCase splits, ligatures, control chars, encoding garble, spaced letters, repeated chars, hyphen splits). If zero artifacts found, skips the AI call entirely.

Expected impact: eliminates 50-80% of quality pass API calls on well-extracted books.

### Config-Driven Models

All model strings moved to `config/settings.json` -> `api_models` section. No more hardcoded model IDs in Python or PowerShell code.

## What Stays on Sonnet (Justified)

| Call | Justification |
|------|--------------|
| `Get-ChapterStructure` | Multi-level part/chapter/section hierarchy requires reasoning |
| Visual QA rubric scoring | Vision capability + nuanced 6-category assessment |
| Claude Vision extraction (Tier 3) | Premium OCR, explicit opt-in, last resort |

## Future Opportunities

| Opportunity | Potential Savings | Effort |
|-------------|------------------|--------|
| Cache AI results in pattern_db (subheadings, rejoin, chapters) | Eliminates re-run costs | M |
| Gemini Flash as VQA backend | ~5-10x cheaper per book | L |
| Reduce VQA default max_pages from 20 to 12 | ~40% per VQA run | S |
