# Risk-Tiered Visual QA — Design

**Date:** 2026-05-29
**Status:** Design (pending implementation plan)
**Related tickets:** EB-339 (local R9700 Qwen3-VL primary — shipped), EB-340 (auto-enable VQA on batch — open), EB-341 (fallback cost-reporting bug — open, blocker)

## Problem

The current visual QA system (`tools/visual_qa.py`) was designed under a per-image
API cost constraint (OpenRouter pricing). Three design decisions exist *only* to
ration that cost:

1. **Page sampling** — `select_sample_pages` evaluates 8 pages (max 20) of an entire
   book, deliberately blind to the rest. Issues on un-sampled pages are invisible,
   and a clean report says nothing about coverage.
2. **Low DPI** — default 100 DPI, auto-reduced further for large files
   (`_apply_large_file_dpi_reduction`). Fine rendering issues (footnote superscripts,
   ligatures, diacritics, small-caps) are hard to detect at this resolution.
3. **Cost-capped convergence** — `converge_loop.cost_limit_per_book_usd: 2.0` halts
   iteration on money, not quality, before reaching `target_score: 85`.

EB-339 made the local R9700 Qwen3-VL endpoint the primary provider, so per-image cost
is effectively zero. The opportunity: make VQA more thorough where it pays off —
**without** blanketing every job with expensive full coverage, since conversion time
is still a real cost.

## Critical constraint: local model score-inflation

`tools/analyze_vqa_mode_classification.py` documents two failure modes of the local
Qwen vision model, measured during SCRUM-280:

- **Mode (a) — grading bias:** the model detects issues but inflates scores
  (consistently 80–100).
- **Mode (b) — detection failure:** the model misses issues that Claude catches.

This is why the Claude fallback is fingerprint-gated. The design implication is
load-bearing: **coverage and accuracy are independent axes.** Running full-page
coverage on a model that over-scores produces more confident-looking reports that are
still wrong. More thorough VQA on the high-risk tier therefore *retains a Claude
adjudicator*, rather than trusting the local model's pass/fail alone.

## Approach: a risk-tiered VQA policy layer

Introduce a single policy layer that reads the **existing** pre-conversion signals and
routes each job to a VQA tier. No new detection is needed — `classify_pdf`
(`tools/classify_source.py`) and the preflight stage already emit the required signals:

- `classification` (e.g. `scan_no_text`)
- `flags.needs_ocr`, `flags.likely_two_column`, `flags.needs_paid_tier`
- per-signal text density, confidence
- preflight OCR-artifact ratios and text-quality scores

### Tier matrix

| Tier | Trigger (from existing signals) | Coverage | DPI | Depth | Adjudicator |
|------|--------------------------------|----------|-----|-------|-------------|
| **Light** | clean digital, high text density, no flags | current ≤8-page sample | 100 | single-pass | none |
| **Standard** | normal book, minor preflight warnings | ~20–30 pages | 150 | single-pass | fingerprint → Claude |
| **Full** | `scan_no_text`, `needs_ocr`, `likely_two_column`, OCR-artifact-heavy, or conversion warnings | **all pages** | 200 | two-pass + converge loop | Claude on disagreement / low confidence |

This honors the conversion-time concern: the cheap, fast majority (clean digital books)
stays Light; GPU time and the Claude adjudicator are spent only on scans and
problematic PDFs where false negatives are expensive.

### Components

- **`vqa_policy` (new):** pure function `decide_tier(classify_result, preflight_result, config) -> TierDecision`.
  Returns the tier name and the resolved knobs (coverage mode, DPI, pass count,
  adjudicator policy). Isolated and unit-testable with no I/O. Thresholds live in
  `config/settings.json` under a new `visual_qa.tiers` block.
- **`visual_qa.py` (extend):** accept a `TierDecision` (or `--tier`) that overrides the
  sampling/DPI/pass knobs currently read from flat config. `select_sample_pages` gains
  a full-coverage mode (return all pages) for the Full tier.
- **Batch integration (EB-340):** `run_overnight_batch.ps1` / module call site reads the
  per-book classify+preflight output and passes the tier through, with VQA enabled by
  default for the batch.
- **Cost reporting (EB-341):** fix the fallback cost-reporting bug first so tier-aware
  cost accounting is correct before changing what runs.

### Data flow

```
inbox PDF
  → preflight_analysis + classify_pdf  (existing — produces risk signals)
  → vqa_policy.decide_tier()           (new — maps signals → tier + knobs)
  → conversion → KFX
  → visual_qa.run_visual_qa(tier knobs) (extended — coverage/DPI/passes per tier)
  → [Full/Standard] Claude adjudicator on disagreement
  → _visual_qa_report.json (records tier + coverage_status)
```

## Trust model (decided)

Full tier: local full-coverage pass, then send only disagreement / low-confidence pages
to Claude as adjudicator. Catches the over-scoring blind spot while keeping paid cost
confined to the few high-risk books.

## Error handling

- Tier decision degrades safely: if classify/preflight output is missing or low
  confidence, default to **Standard** (never silently skip to Light on unknown input).
- Full-coverage rendering of large books must respect the existing image-bytes ceiling —
  batch pages per request rather than reducing DPI; never silently truncate coverage.
  `coverage_status` in the report must reflect any partial coverage.
- Claude adjudicator failure (no API key, rate limit) is non-fatal: report records
  `adjudicator: unavailable` and the local result stands, flagged as un-adjudicated.

## Testing

- Unit tests for `vqa_policy.decide_tier` across each signal combination (clean digital,
  scan_no_text, two-column, OCR-artifact-heavy, missing signals → Standard default).
- `select_sample_pages` full-coverage mode returns all pages and respects the
  image-bytes batching ceiling.
- **Calibration re-baseline (mandatory, per CLAUDE.md):** changing what VQA evaluates
  invalidates `data/vqa_baseline_*`. Per the Calibration Sessions rule — run twice on the
  same input (determinism), run against a known-good book (zero false positives), and
  spot-check findings against source before re-capturing baselines. VQA baseline files
  are worktree-gated test fixtures (EB-181) and must land via PR.

## Proposed ticket split

1. **EB-341** (blocker) — fix fallback cost-reporting bug. Must land first.
2. **New — VQA policy/tiering layer** — `vqa_policy`, config `tiers` block, `visual_qa.py`
   knob override. Keystone; everything plugs into it.
3. **EB-340** — auto-enable tier-aware VQA on overnight batch.
4. **New — Full-coverage + DPI** — full-page sampling mode + higher DPI, gated to Full tier,
   with image-bytes batching.
5. **New — Calibration re-baseline** — re-capture and validate `data/vqa_baseline_*` under
   the new tier behavior; verify over-scoring does not mask regressions.

## Out of scope (YAGNI)

- No changes to the rubric content or the converge-loop algorithm beyond relaxing the
  cost ceiling for the Full tier.
- No new vision provider; reuse the EB-339 local provider and existing Claude fallback.
- No re-architecture of preflight/classify; they are consumed as-is.
