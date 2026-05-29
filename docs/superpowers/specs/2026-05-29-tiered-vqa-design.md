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
2. **Low DPI** — default 100 DPI, auto-reduced to **72 DPI / 4 pages** for large files
   (`_apply_large_file_dpi_reduction`, `_LARGE_FILE_REDUCED_DPI = 72`,
   `_LARGE_FILE_REDUCED_MAX_PAGES = 4`). Fine rendering issues (footnote superscripts,
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
- **Mode (b) — detection failure:** the model misses issues that Claude catches —
  **there is no "disagreement" to trigger on, because the local model never flagged it.**

This is why the Claude fallback is fingerprint-gated. The design implication is
load-bearing: **coverage and accuracy are independent axes.** Running full-page
coverage on a model that over-scores produces more confident-looking reports that are
still wrong. Mode (b) specifically means a disagreement-only adjudication trigger will
miss issues entirely — so the Full tier adds a **blind audit slice** (below).

## Approach: a two-stage, risk-tiered VQA policy

A policy layer routes each job to a VQA tier in **two stages**, because some risk
signals only exist after conversion:

1. **Pre-conversion tier decision** — from `classify_pdf` + preflight signals.
2. **Post-conversion escalation** — bump the tier upward (never downward) when the
   *conversion* itself reveals risk: KFX/AZW3 format fallback, OCR fallback fired,
   conversion/rendering warnings, or poor intermediate quality. (VQA-response
   truncation is **not** a conversion signal — it is an `OutputTruncatedError` from the
   vision provider during evaluation, handled by Full-coverage retry/chunking, not by
   `escalate_tier`.)

No new detection is needed — `classify_pdf` (`tools/classify_source.py`) already emits
the required signals. **`vqa_policy` consumes the raw `classify_pdf` result directly**,
not the trimmed preflight `source_classification` subset, because that subset does not
reliably expose `needs_paid_tier` (it appears only in preflight's failure-default
block). Signals consumed:

- `classification` (e.g. `scan_no_text`), `confidence`
- `flags.needs_ocr`, `flags.likely_two_column`, `flags.needs_paid_tier`
- `signals.text_density_per_page`
- preflight OCR-artifact ratio and text-quality score

### Tier matrix

| Tier | Trigger | Coverage | DPI | Depth | Adjudicator |
|------|---------|----------|-----|-------|-------------|
| **Light** | `digital_native`, confidence ≥ 0.85, text density ≥ 750–1000 chars/pg, text quality ≥ 85, OCR-artifact rate < 0.05, no flags | current ≤8-page sample | 100 | single-pass | none |
| **Standard** | default — incl. missing / low-confidence signals | ~20–30 pages | 150 | single-pass | fingerprint → Claude |
| **Full** | any `scan_no_text`, `needs_ocr`, `needs_paid_tier`, `likely_two_column`, text quality < 50, OCR-artifact rate ≥ 0.30, **or any post-conversion warning** | **all pages** | 200 | two-pass + converge loop | Claude on disagreement **+ blind audit slice** |

Thresholds start conservative (above) and live in `config/settings.json` under a new
`visual_qa.tiers` block. Standard is the safe default: missing or low-confidence
signals route to Standard, never silently down to Light.

This honors the conversion-time concern: clean digital books (the fast majority) stay
Light; GPU time and the Claude adjudicator concentrate on scans and problematic PDFs.

### Components

- **`vqa_policy` (new):** pure function
  `decide_tier(classify_result, preflight_result, config) -> TierDecision` and a
  separate `escalate_tier(tier_decision, conversion_signals) -> TierDecision`. No I/O,
  unit-testable. Returns tier name, the resolved knobs (coverage mode, DPI, pass count,
  adjudicator policy), `tier_reason`, and `tier_signals`.
- **`visual_qa.py` (extend):** accept a `TierDecision` (or `--tier`). `select_sample_pages`
  gains a full-coverage mode (return all pages) for the Full tier.
- **Streaming tier-aware chunking (replaces `_apply_large_file_dpi_reduction`):** on the
  Full tier, do **not** drop to 72 DPI / 4 pages, and do **not** render the whole book
  into memory first. Today `render_pages_to_png` accumulates every page's PNG bytes in
  one list before batching ([visual_qa.py:360](../../../tools/visual_qa.py)); at 200 DPI
  across all pages that blows memory/disk/time. Instead **render → evaluate → release per
  chunk**, where chunks are sized by *rendered image bytes* to fit the provider's
  image-bytes limit. Images are freed after each chunk's evaluation. If a chunk fails to
  render or evaluate, record partial coverage rather than silently shrinking the request.
- **Blind audit slice (Full tier):** even when the local pass looks clean, send a small
  capped Claude sample — first / body / back + ~5% random pages, capped at 10 — to
  counter mode-(b) detection failure where there is no disagreement to trigger on. The
  random selection MUST be **deterministic**: seed from a stable source (source-file
  hash + tier-config version), and record the seed and the resolved audit page list in
  the report so calibration runs are repeatable.
- **Batch integration (EB-340):** `run_overnight_batch.ps1` / module call site reads the
  per-book classify+preflight output, passes the pre-conversion tier, then applies
  post-conversion escalation. VQA enabled by default for the batch.
- **Cost reporting (EB-341):** fix the fallback cost-reporting bug first so tier-aware,
  provider-separated cost accounting is correct before changing what runs. Introduce a
  **canonical authoritative total** `token_usage.total_estimated_cost_usd` (local +
  Claude), while preserving the per-provider breakdown. Both consumers currently read
  only the single primary `estimated_cost_usd` field — the CLI summary
  ([visual_qa.py:1423](../../../tools/visual_qa.py)) and DB persistence
  ([EbookAutomation.psm1:2321](../../../module/EbookAutomation.psm1)) — and must be
  updated to read/write the canonical total. This matches EB-341's AC on CLI + DB
  under-reporting.

### Data flow

```
inbox PDF
  → preflight_analysis + classify_pdf        (existing — risk signals)
  → vqa_policy.decide_tier()                 (new — pre-conversion tier + knobs)
  → conversion → KFX  (emits conversion_signals: format fallback / OCR / warnings)
  → vqa_policy.escalate_tier()               (new — bump tier on post-conversion risk)
  → caller passes --tier-decision-json       (source signals cross into visual_qa.py)
  → visual_qa.run_visual_qa(tier knobs)      (extended — stream render→eval→release per chunk)
  → [Standard/Full] fingerprint/disagreement → Claude
  → [Full] deterministic blind audit slice → Claude
  → _visual_qa_report.json (tier + 3-way coverage + adjudicator + canonical total cost)
```

## Coverage accounting (fixes a latent bug)

Today `build_report` is called with `len(page_images)` as `pages_sampled`
([visual_qa.py:1144](../../../tools/visual_qa.py)), i.e. the *rendered* count, not the
*requested* count. A render-failure drop (requested → rendered) is therefore invisible
and `coverage_status` can still read "complete." Replace with an explicit 3-way split,
recorded in the report for all tiers:

- `pages_requested` — `len(select_sample_pages(...))` (or all pages for Full)
- `pages_rendered` — `len(page_images)`
- `pages_evaluated` — pages that returned valid results
- `coverage_mode` — `sample` | `full`
- `coverage_status` — `complete` only when `evaluated == requested`; else `partial`

## Report additions

Add to `_visual_qa_report.json`: `vqa_tier`, `tier_reason`, `tier_signals`,
`coverage_mode`, `requested_dpi`, `effective_dpi`, `adjudicator_status`,
`pages_adjudicated`, `adjudicator_trigger_counts` (disagreement vs blind-audit),
`audit_seed` + `audit_pages` (for repeatable calibration), and under `token_usage`:
**provider-separated cost totals** (local vs Claude) plus the canonical
`total_estimated_cost_usd` (EB-341).

## CLI & source-signal handoff contract

Make `--tier light|standard|full|auto` canonical (`auto` = let `vqa_policy` decide).
De-emphasize / alias the existing `--full` (today it means 20 pages @ 150 DPI), which
conflicts with the new Full tier (all pages @ 200 DPI). Document the rename to avoid
silent behavior change for anyone scripting `--full`.

**Handoff problem:** `visual_qa.py` today receives only the converted artifact
(`--input <kfx>` + DPI/provider), and the overnight batch passes nothing more
([run_overnight_batch.ps1:162](../../../tools/run_overnight_batch.ps1)). So `--tier auto`
cannot see `classify_pdf` / preflight signals from those entry points. Resolution:

- Add an explicit handoff arg. Preferred: `--tier-decision-json <path>` — the caller
  (batch / module) runs `vqa_policy.decide_tier` against the source PDF it already has,
  and passes the resolved decision. Alternatives `--classify-json` / `--preflight-json`
  let `visual_qa.py` compute the tier itself; `--source-input <pdf>` lets it run the
  classifiers directly.
- **Standalone fallback:** when `--tier auto` is given with **no** source signals,
  `visual_qa.py` resolves to **Standard** explicitly (logged), never Light. It never
  guesses Full/Light without evidence.
- EB-340 wiring: the batch computes the decision pre-conversion, applies post-conversion
  escalation, and passes `--tier-decision-json` so the source signals reach VQA.

## Error handling

- Tier decision degrades safely: missing / low-confidence classify output → **Standard**,
  never Light.
- Tier-aware chunking respects the image-bytes ceiling by *batching*, never by reducing
  DPI or dropping pages on the Full tier; any unavoidable drop is recorded as `partial`.
- Claude adjudicator / blind-audit failure (no API key, rate limit) is non-fatal:
  `adjudicator_status: unavailable`, local result stands, flagged un-adjudicated.

## Testing

- Unit tests for `decide_tier` across each signal combination (clean digital,
  `scan_no_text`, two-column, OCR-artifact-heavy, missing signals → Standard) and for
  `escalate_tier` (each post-conversion warning bumps to Full, never downgrades;
  VQA-response truncation is **not** an escalation input).
- `select_sample_pages` full-coverage mode returns all pages; streaming chunking respects
  the image-bytes ceiling and releases images per chunk; render failure produces
  `partial`, not false `complete`.
- Handoff: `--tier auto` with no source signals resolves to Standard (logged);
  `--tier-decision-json` is honored end-to-end from the batch.
- Determinism: same source hash + tier-config version → identical `audit_pages`; the
  seed and page list are recorded in the report.
- Cost: `total_estimated_cost_usd` equals local + Claude; CLI summary and DB persistence
  read the canonical total, not the primary-only field.
- **Calibration re-baseline (mandatory, per CLAUDE.md):** changing what VQA evaluates
  invalidates `data/vqa_baseline_*`. Per the Calibration Sessions rule — run twice on the
  same input (determinism), run against a known-good book (zero false positives), and
  spot-check findings against source before re-capturing. VQA baseline files are
  worktree-gated test fixtures (EB-181) and must land via PR.

## Proposed ticket split

1. **EB-341** (blocker) — fix fallback cost-reporting bug; add canonical
   `total_estimated_cost_usd` + provider-separated breakdown; update CLI summary
   (visual_qa.py:1423) and DB persistence (EbookAutomation.psm1:2321) to read the total.
   Must land first.
2. **New — VQA policy/tiering layer** — `vqa_policy.decide_tier` + `escalate_tier`,
   `visual_qa.tiers` config block, `visual_qa.py` knob override, `--tier` CLI +
   `--tier-decision-json` (and `auto`→Standard standalone fallback), 3-way coverage
   accounting + report fields. Keystone.
3. **New — Full-coverage execution** — full-page sampling mode + 200 DPI + **streaming**
   render→eval→release chunking (by rendered image bytes) replacing
   `_apply_large_file_dpi_reduction`. *Failure mode: memory / rendering / image-bytes
   limits.*
4. **New — Claude adjudication & blind audit** — disagreement trigger + deterministic
   capped blind-audit slice (seeded, recorded) for the Full tier. *Failure mode: trust /
   false-confidence.*
5. **EB-340** — auto-enable tier-aware VQA on overnight batch; compute the decision
   pre-conversion, apply post-conversion escalation, pass `--tier-decision-json`
   (consumes 2–4).
6. **New — Calibration re-baseline** — re-capture and validate `data/vqa_baseline_*` under
   the new tier behavior; verify over-scoring does not mask regressions.

(Items 3 and 4 are split because they have distinct failure modes — rendering/limits
vs trust/accuracy — and can be reviewed and validated independently.)

## Out of scope (YAGNI)

- No changes to the rubric content or the converge-loop algorithm beyond relaxing the
  cost ceiling for the Full tier.
- No new vision provider; reuse the EB-339 local provider and existing Claude fallback.
- No re-architecture of preflight/classify; they are consumed as-is (`vqa_policy` reads
  raw `classify_pdf` output).
