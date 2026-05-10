---
title: VQA batch truncation — surfacing coverage loss in the report (EB-149)
type: solution
status: compound
date: 2026-05-10
last_updated: 2026-05-10
origin_ticket: EB-149
related_tickets: [SCRUM-279, SCRUM-292, SCRUM-319]
tags: [vqa, truncation, coverage, output-tokens, silent-failure, report-schema]
---

# VQA batch truncation — surfacing coverage loss in the report (EB-149)

## Problem

The VQA pipeline sends pages in batches to a vision LLM. When a batch exceeds the
model's output-token budget, `OutputTruncatedError` fires and the entire batch is
dropped. The report's `pages_sampled` field was set to the count of *rendered* pages,
not the count of *evaluated* pages — so a run that lost 8 of 20 pages still reported
`pages_sampled: 20`. Downstream consumers (Matcher 4 statistical rule, baseline
comparison, batch QA aggregation) operated on a partial dataset as if it were complete.

Evidence from SCRUM-292: Dionysius run lost pages `[18, 20, 24, 25, 29, 32, 34, 36]`
(entire batch 2) but the report showed `pages_sampled: 20`.

## Solution shipped in EB-149

Three new fields added to the report JSON:

| Field | Type | Meaning |
|-------|------|---------|
| `pages_sampled` | int | Existing. Pages rendered and *sent* for evaluation (unchanged). |
| `pages_evaluated` | int | **New.** Pages that returned valid results. |
| `coverage_status` | string | **New.** `"complete"` when `pages_evaluated >= pages_sampled`, `"partial"` otherwise. |
| `truncation_events` | list | **New.** One entry per `OutputTruncatedError` batch that had unrecovered pages. |

Each `truncation_events` entry:
```json
{
  "batch_index": 2,
  "pages_lost": [18, 20, 24, 25, 29, 32, 34, 36],
  "finish_reason": "length",
  "output_tokens": 4096
}
```

`coverage_status` is intentionally broader than `truncation_events`: it signals any
coverage gap (truncation, parse failure, provider rejection), while `truncation_events`
specifically identifies `OutputTruncatedError` as the root cause.

## Approach decision (deferred options)

**Adaptive batch-size retry** — DEFERRED. `OutputTruncatedError` is a *model output*
issue (the model generated too many tokens). This is distinct from the SCRUM-319
single-page retry which addresses *payload-size* failures (provider rejecting the
request due to too many images/bytes). Halving the batch size does not guarantee the
model's output will be shorter; a single dense page can still cause truncation. The
right mitigation — if needed — is reducing `max_tokens` budget per call or
instructing the model to be more concise. Separate ticket if this becomes a pattern.

**Fail-loud gate** — IMPLEMENTED as `coverage_status: "partial"`. Operators can filter
reports on this field. No hard pipeline failure: partial results are still more useful
than nothing, and the existing `evaluation_status: "api_failure"` path already handles
the zero-pages case.

**Reduce default batch size** — NOT CHANGED. Default of 8 pages is tuned against the
corpus. Reducing it increases API call count and cost for all books without guaranteeing
fewer truncation events (the output-token issue is per-model-call, not per-image-count).

## Implementation details

- `OutputTruncatedError` added to `llm_providers/__init__.py` exports so `visual_qa.py`
  can `isinstance`-check it without reaching into the internal module.
- `_truncation_attempts` accumulates raw events during the batch loop. After the loop,
  events are resolved against `all_pages_results` so that pages recovered by the
  SCRUM-319 single-page retry are *not* reported as lost.
- **Python double-import trap**: test files must import `OutputTruncatedError` via
  `from llm_providers.local_provider import ...` (not `from tools.llm_providers.local_provider import ...`).
  Both paths resolve to the same `.py` file but create different class objects;
  `isinstance()` returns `False` across the two paths.

## Operator guidance for `coverage_status`

When reading a VQA report:

- `coverage_status: "complete"` — all rendered pages returned results. Score is
  representative of the sampled pages.
- `coverage_status: "partial"` — some pages were lost. The score was computed from
  only `pages_evaluated` pages. Check `truncation_events` for root cause.
  Re-run with `--provider claude` (which does not use guided JSON and is not
  susceptible to this truncation pattern) to get full coverage if needed.

Batch-QA aggregation scripts should filter on `coverage_status` before computing
corpus-level quality statistics.
