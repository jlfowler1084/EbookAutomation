---
name: test-pipeline
description: Use when validating pipeline output after any edit to pipeline Python files, heading detection, TOC generation, bookmark reconciliation, or footnote logic — or when asked to validate current state
---

# Test Pipeline

Run the full 5-book PDF-to-Kindle validation suite against the expected baselines.

## Steps

1. Run `python tests/validate_against_baseline.py` to execute the full pipeline on all 5 test books
2. Compare output against `tests/expected_baselines.json`
3. For each book, report:
   - Heading counts by level vs expected
   - TOC entry count and max nesting depth vs expected
   - Footnote linked pairs vs expected
4. Summarize as a pass/fail table:

| Book | Headings | TOC | Footnotes | Status |
|------|----------|-----|-----------|--------|

5. If ANY book fails, list the specific deviations
6. Do NOT proceed with other work if any book is failing — stop and report

## When to Run

- After ANY edit to pipeline Python files
- After modifying heading detection, TOC generation, bookmark reconciliation, or footnote logic
- When asked to validate current state
