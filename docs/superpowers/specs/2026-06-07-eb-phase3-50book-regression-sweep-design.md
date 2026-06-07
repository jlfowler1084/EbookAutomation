---
ticket: EB-377
date: 2026-06-07
status: design-approved
topic: Phase-3 50-book header-bleed + quality regression sweep with full local-Qwen VQA
related: [EB-367, EB-370, EB-372, EB-374, EB-361, EB-353]
---

# Phase-3 50-Book Regression & Pattern Sweep — Design

## 1. Goal & success criteria

Run ~50 books through the full PDF→KFX pipeline with free local-Qwen Visual QA to:

1. **Confirm** the running-header-bleed fixes (EB-367/370/372/374) hold across a real corpus. No corpus baseline exists yet — the two reports in `data/batch_reports/header_bleed/` scanned 0 books. This run produces the first real signal.
2. **Discover** new failure patterns and rank what to fix next, using `batch_qa.py`'s failure-clustering and "observations" engine.

**Success = a committed findings document** that answers: (a) did the header-bleed fix hold corpus-wide? (b) what new patterns emerged, ranked by frequency × severity? (c) a prioritized fix list, each item filed as a child ticket under EB-377 — **with measurement artifacts (non-deterministic VQA, harness false positives) reported separately from real findings.**

## 2. Approach

**Chosen — A:** `tools/batch_qa.py run` is the heavy orchestrator. It already chains extraction → KFX (`run_kfx_conversion_for_book`) → local VQA (`run_visual_qa_for_book`) → failure-clustering (`analyze_patterns`, `batch_qa.py:1358`) → correlation observations (`detect_correlations`, `:1396`) → JSON/MD/HTML reports. That clustering engine *is* the new-pattern detector. Header-bleed is a cheap second scan of the `_kindle.html` intermediates `batch_qa` produces, via `tools/check_header_bleed.py`.

**Rejected — B:** `tools/run_overnight_batch.ps1` as primary. It wires header-bleed (Phase 2.5) and VQA (Phase 3) natively, but Phase 2 runs `Invoke-EbookPipeline`, **not** `batch_qa.py`, so it never produces the clustering/observations engine — exactly the signal we want. Reattaching clustering means re-running extraction. Not worth it.

## 3. Corpus composition — hybrid 11 / 39

**11 PDF anchors** (regression confirmation), sourced from `archive/`:

| # | Book | Why anchored |
|---|------|--------------|
| 1 | On First Principles | EB-374 roman-numeral header-bleed anchor (36 roman welds → 0) |
| 2 | Pilgrim People | EB-367 ALL-CAPS header-bleed anchor (310 welds → 0) |
| 3 | The Oil Kings | Endnote linking, dual numbering |
| 4 | Mexico's Illicit Drug Networks | OCR artifacts, ligatures |
| 5 | The Return of the Gods | Thematic / non-sequential chapters |
| 6 | Python in Easy Steps | Simple-structure canary |
| 7 | Atomic Habits | Dense formatting, callout boxes |
| 8 | Decline of the West | Long chapters, footnote pairing |
| 9 | Dionysius the Areopagite | SCRUM-299 running-header anchor |
| 10 | Reading Genesis After Darwin (Barton) | Diverse-author edited collection |
| 11 | Fate of Empires (Glubb) | Two-column layout anchor |

**39 fresh** from `F:\books` (464-file pool), selected by a script that:
- Excludes non-books (tax/resume/boarding-pass, `*.mp3`, `*.txt`, stray scripts), duplicate redownloads (`(1)`, `(2)` suffixes), and exploded-EPUB folders.
- Excludes non-`.pdf` (KFX/VQA is PDF-only — see §4).
- Samples for variety across file size and subject folder, with a **soft bias toward header-prone genres** (history / philosophy / academic) to stress the EB-374 fix. **No hard genre quota** unless the resulting manifest looks skewed.
- Uses a **fixed random seed** and records the **strata counts** (size buckets × subject folders) in `logs/batch-selection-2026-06-07.json`, so the 39 fresh picks are reproducible and explainable.

**Sherlock Holmes EPUB is excluded** from this sweep. `batch_qa.py` guards KFX conversion to PDFs (`tools/batch_qa.py:1145`, `if not quick and ext == 'pdf':`), so an EPUB would extract but never get KFX or VQA. Run EPUB coverage separately if wanted.

## 4. Key codebase facts (verified)

- **CLI:** `python tools/batch_qa.py run <folder> --full --vqa --parallel 2`. `run` is a subparser (`tools/batch_qa.py:2881`).
- **`--full` is overloaded.** `batch_qa.py --full` = "include KFX conversion." `visual_qa.py --full` (different tool, `tools/visual_qa.py:1430`) = "20 pages at 150 DPI." We want both: `batch_qa.py --full` for KFX, and `visual_qa.py --full` for calibrated VQA.
- **PDF-only KFX guard:** `tools/batch_qa.py:1145`.
- **VQA call today:** `run_visual_qa_for_book` (`tools/batch_qa.py:718`) runs `visual_qa.py --input <kfx> --verbose` with a hard **300s** timeout and no page/dpi/provider/fallback args — so it uses config defaults (8 pages, 100 DPI, provider `local`, fallback **on**).
- **`visual_qa.py` flags exist:** `--provider {claude,local,cloud}`, `--dpi`, `--max-pages`, `--full`, `--fallback-enabled` (`type=lambda x: x.lower() != "false"`).
- **Config (`config/settings.json:78-100`):** `visual_qa.provider = "local"`, `local_base_url = "http://192.168.1.33:8080/v1"`, `fallback.enabled = true`.
- **Intermediate HTML canonical path:** `output\kindle\.intermediates\<kfx-basename>_kindle.html` (`module/EbookAutomation.psm1:2364`; matches `run_overnight_batch.ps1:156`). The KFX path runs `Convert-ToKindle -NoCache`, so this is the current-pipeline artifact — scan this, **not** `batch_qa`'s preliminary HTML.
- **`--max-pages` is a skip filter, not VQA sampling:** in `batch_qa.py`, `max_pages` skips any PDF whose page count exceeds N (`tools/batch_qa.py:852-860`). This run passes **no** `--max-pages` (default `0` = no skip) so large books are not silently dropped. VQA page depth is controlled independently by `visual_qa.py --full`.
- **R9700 status:** green now — `/v1/models` → `Qwen3VL-30B-A3B-Instruct-Q4_K_M.gguf`.

## 5. Execution contract

| # | Item | Spec |
|---|------|------|
| 1 | Batch command | `python tools/batch_qa.py run processing\batch-2026-06-07 --full --vqa --parallel 2` |
| 2 | VQA concurrency | `threading.Semaphore(1)` around the `visual_qa.py` subprocess in `run_visual_qa_for_book`. Extraction/KFX stay at parallel 2; only one VQA request hits the R9700 at a time → trusted, uncontended scores. |
| 3 | Calibrated VQA | `run_visual_qa_for_book` invokes `visual_qa.py --input <kfx> --verbose --full --provider local --fallback-enabled false`. 20 pages @ 150 DPI. |
| 4 | Free / local-only | `--fallback-enabled false` passed **exactly** (lowercase). Claude fallback OFF; run is $0. The values that silently leave fallback ON are `0`, `no`, `off`, or omitting the flag. |
| 5 | VQA timeout | Raise the `run_visual_qa_for_book` subprocess timeout 300s → **900s** (20-page two-pass on local Qwen is slower). |
| 6 | Header-bleed scan | After the batch, scan **only the 50 KFX basenames recorded in the provenance index** (`output\kindle\.intermediates\<basename>_kindle.html`) with `tools/check_header_bleed.py` — **never a bare `*_kindle.html` glob**, which would pull stale intermediates from prior runs into EB-377. A missing intermediate is recorded as a **coverage gap**, not silently skipped. |

## 6. Preflight gates (fail-fast, before the overnight run)

1. **R9700 reachable** — `GET http://192.168.1.33:8080/v1/models` returns the Qwen3-VL model. If down: bring it up, or fall back to cloud OpenRouter Qwen (documented paid fallback). Default stays local/free.
2. **`visual_qa.enabled:false` does not block explicit invocation** — confirmed by the smoke test (the config flag gates auto-VQA in the main pipeline, not direct `visual_qa.py` calls).
3. **VQA determinism** — `python tools/vqa_determinism_check.py --input <kfx> --provider local --dpi 150 --max-pages 20 --runs 2 --tolerance 0`. (This tool forces fallback off internally and takes neither `--full` nor `--fallback-enabled`.) Bit-exact reproducibility required; drift = metric flagged non-deterministic and reported separately, not as a finding.
4. **Baseline sanity** — extract Pilgrim People + On First Principles and require `weld_total == 0` on both. Any weld on a clean anchor = harness regression; stop and investigate before the big run.
5. **Smoke test** — one header-bleed anchor + one fresh book end-to-end (extraction → KFX → VQA → reports) before committing 2-4 hours.

## 7. Required code changes (small)

All on a feature worktree branch (`feat/EB-377-phase3-sweep-harness`), merged via PR **before** the run. The batch itself runs from the **main working tree**, never a worktree — per the CLAUDE.md junction-deletion hazard, pipeline runs that touch `archive/`, `output/`, `processing/` stay in the main tree.

1. **`tools/batch_qa.py` — `run_visual_qa_for_book`:**
   - Add `visual_qa.py` args `--full --provider local --fallback-enabled false`.
   - Add a module-level `threading.Semaphore(1)` acquired around the subprocess call.
   - Raise the timeout 300 → 900.
   - Do **not** reuse `max_pages` for VQA sampling — in `batch_qa.py` it already means "skip PDFs over N pages" (`:852`). A future per-call VQA-sampling override needs a separate `vqa_args` / `vqa_mode` param.
   - Unit test: assert the constructed argv contains the four flags and the semaphore serializes (mock subprocess).

2. **`tools/select_batch_corpus.py` (new):** build the 11/39 manifest from `archive/` + `F:\books`, emit a reviewable `logs/batch-selection-2026-06-07.json`, and copy the 50 PDFs into `processing/batch-2026-06-07/`. Copy — never junction.

3. **`tools/build_batch_provenance.py` (new) + synthesis:** after the run, join by KFX basename to produce a per-book artifact index — source path + SHA-256, staged path, KFX path, intermediate-HTML path, VQA-report path, header-report path, coverage status — then emit the findings markdown merging `failure_clusters` + `observations` + header-bleed welds + VQA scores. Lossy `batch_qa` aggregate JSON is *not* the join key.

## 8. Harness validation (Calibration-Sessions discipline)

Per global CLAUDE.md: validate the harness before treating output as findings.
- **Run-twice determinism** — preflight §6.3.
- **Known-good baseline** — preflight §6.4 (clean anchors must show 0 welds).
- **Spot-check** — manually verify 2-3 VQA-flagged pages against the actual PNGs and 2-3 header-bleed welds against the HTML before any finding is escalated to a child ticket.

## 9. Deliverables & artifacts

- `logs/batch-selection-2026-06-07.json` — reviewable corpus manifest.
- `data/batch_reports/batch_<ts>.{json,md,html}` — `batch_qa` diagnostics + clusters + dashboard.
- `data/batch_reports/header_bleed/*.json` — per-book weld reports.
- Per-book VQA reports (`<kfx-basename>_visual_qa_report.json`).
- Provenance index (JSON) + findings synthesis at `data/batch_reports/EB-377-findings-2026-06-07.md` (primary deliverable). A `docs/solutions/` compounding entry follows only if a reusable lesson emerges.
- Child EB tickets for each prioritized fix, linked to EB-377.

## 10. Risks

- **R9700 availability** — single point of failure; cloud fallback exists.
- **Calibre KFX flakiness at 50×** — tolerated; captured as `KFX_FAILED` cluster data, not a run-killer (`tools/batch_qa.py:704-711` already treats 0-byte KFX as failure).
- **Disk** — staging ~50 PDFs is transient (~2-5 GB); cleaned after.
- **Runtime** — ~2-4 hours at parallel 2 with serialized VQA.

## 11. Out of scope

- EPUB/MOBI coverage (separate run).
- Any pipeline *fixes* — this run measures and ranks; fixes are downstream child tickets.
- Changing VQA defaults in `config/settings.json` (we pass flags per-run; config stays untouched).
