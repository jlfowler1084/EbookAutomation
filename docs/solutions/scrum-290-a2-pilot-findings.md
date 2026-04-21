---
title: SCRUM-290 A1 + A2 pilot batch findings
type: solution
status: compound
date: 2026-04-21
origin_ticket: SCRUM-290
related_tickets: [SCRUM-291, SCRUM-292, SCRUM-293, SCRUM-294, SCRUM-295, SCRUM-296, SCRUM-274, SCRUM-281, SCRUM-282, SCRUM-283, SCRUM-288, SCRUM-289]
tags: [batch, vqa, pipeline-health, diagnostic, regression]
---

# SCRUM-290 — A1 + A2 pilot batch findings and lessons

Compound-knowledge writeup of the SCRUM-290 diagnostic batch. The batch surfaced one blocking bug (SCRUM-293 — universal KFX failure from PowerShell shell misselection), reinforced two prior observations (SCRUM-291 page-labeling, SCRUM-292 degenerate VLM response), and produced three net-new observability concerns worth filing as follow-ups.

The batch is the first end-to-end pipeline + VQA run since the cloud-primary VQA stack (SCRUM-275..283) and standardized post-274 baselines shipped. Signal: the stack works; the observability around it does not.

## What was run

### A1 — VQA rerun against the 6-book regression corpus

Two passes against existing KFX files in `output/kindle/` compared to `data/vqa_baseline_post_274/`:

- **A1 full** — `visual_qa.py --full` (20 pages at 150 DPI). Partial-overlap compare warned about Lesson-5 drift because baselines are 8-page and candidates were 20-page.
- **A1 quick** — `visual_qa.py` default (8 pages at 100 DPI). Clean 100% overlap on 5 of 6 books.

Baseline model is Claude Sonnet 4.6 (the oracle established in SCRUM-282). Candidate model is the production cloud Qwen3-VL-30B-A3B-Instruct. The compare is effectively a re-run of SCRUM-283's evaluation methodology on the same corpus.

**A1 quick gate result:**

| Metric | Value | R2 threshold | Verdict |
|---|---|---|---|
| Corpus mean \|Δ\| (equal-weight) | 13.22 | < 15 | PASS |
| Max per-book mean \|Δ\| | 18.88 (Python) | < 20 | PASS |
| Detection misses | 0 across all books | — | PASS |
| Total cost | ~$0.08 | — | well under budget |

The candidate-higher-than-baseline pattern (Qwen scoring pages more leniently than Claude) is the known **SCRUM-288 grader-leniency gap**, bounded within the agreed 15 \|Δ\| threshold. Not a regression.

### A2 v1 — 10-book pipeline batch (FAILED)

Ran `batch_qa.py run test-corpus/a2-pilot --full --vqa` against 10 curated PDFs (see A2 corpus below).

**Result: 0 passed, 10 warnings, 0 failed, 0 errors. Top issue: "KFX conversion failed (10 books)." API cost: $0.00.** Every book's `kindle_conversion.duration_seconds: 0.4-0.5s` — too fast for Calibre to even start.

**Root cause:** `tools/batch_qa.py:693` and `tools/test_pipeline.py:613` invoked bare `"powershell"` instead of `"pwsh"`. On this machine, Windows PowerShell 5.1 has `Restricted` execution policy (all scopes `Undefined` → default applies), so `Import-Module` aborts instantly with `UnauthorizedAccess`.

Filed as **SCRUM-293 (High)**, one-line fix applied to both files, FF-merged to master via worktree (commit `12b6af3`).

### A2 v2 — 10-book pipeline batch (with fix)

Same command, fix applied. Ran 53m 11s.

**Result: 6 passed, 4 warnings, 0 failed, 0 errors. Top issue: "No chapters detected (2 books)." VQA avg 75.6, range 60-88.** Eight books got valid VQA scores; two did not (BERT timed out, Drug War Zone produced 0-byte KFX — see anomalies).

## A2 corpus

10 PDFs from `F:\Books` and subdirectories, curated for layout variety:

| # | Book | Source | Category | Size | A2 v2 status |
|---|------|--------|----------|------|:-:|
| 1 | BERT_Pre_Training.pdf | Double_Columned | Double-col ML paper | 0.7 MB | PASS |
| 2 | mapreduce-osdi04.pdf | Double_Columned | Double-col systems paper | 0.2 MB | PASS |
| 3 | Eberhard Kolb - The Weimar Republic (Routledge 2004) | Weimar Republic | Academic history | 1.3 MB | PASS |
| 4 | Howard Campbell - Drug War Zone (UT Press 2009) | Drug Cartels | Academic dense | 18.1 MB | PASS* |
| 5 | John J. Mearsheimer, Stephen M. Walt - The Israel Lobby | top-level | Political academic | 1.2 MB | PASS |
| 6 | CultureWarsOctober.pdf | Magazines | Magazine layout | 4.0 MB | PASS |
| 7 | Umberto Eco - Foucault's Pendulum | top-level (substitute) | Commercial fiction | 1.1 MB | WARN |
| 8 | G. K. Beale - Book of Revelation Commentary (1998) | top-level | Dense academic, Greek text | 101.4 MB | WARN |
| 9 | Monumental Christianity - John Patterson Lundy | top-level | Old scanned book | 81.7 MB | WARN |
| 10 | First Folio of Shakespeare (Norton Facsimile) - Compressed | top-level | Photographic facsimile | 116.6 MB | WARN |

\* Drug War Zone passed status but produced a 0-byte KFX (see anomaly 1 below).

Original picks for single-column-standard (NUREMBERG, Revolutionary Spring) were dropped at staging: NUREMBERG's source folder had only EPUBs; Revolutionary Spring is not a PDF; Tocqueville and Grattan top-level PDFs were 0-byte and 80-byte stubs from failed Anna's Archive downloads. Substituted with Foucault's Pendulum (fiction) and Mearsheimer's Israel Lobby (political academic). Substitutions turned out to be better-targeted variety coverage than the originals.

## Key results and per-book detail

### A2 v2 per-book

| Book | Status | Chapters | KFX size | VQA | Time |
|---|:-:|:-:|---:|:-:|---:|
| BERT_Pre_Training | PASS | 1 | 1.4 MB | timeout (300s) | 321s |
| mapreduce-osdi04 | PASS | 1 | 1.3 MB | 85 | 49s |
| Weimar Republic (Kolb) | PASS | 7 | 5.8 MB | 88 | 99s |
| Mearsheimer Israel Lobby | PASS | 2 | 0.6 MB | 79 | 58s |
| CultureWarsOctober | PASS | 2 | 2.0 MB | 88 | 62s |
| Drug War Zone (Campbell) | PASS | 25 | **0 MB** ⚠ | (skipped) | 119s |
| Foucault's Pendulum | WARN | 0 | 1.8 MB | 65 (uniform) | 101s |
| Monumental Christianity | WARN | 2 | 1.8 MB | 60 | 169s |
| First Folio (facsimile) | WARN | 1 | 8.1 MB | 66 | 928s |
| Beale Revelation Commentary | WARN | 0 | **1055 MB** ⚠ | 74 | 1285s |

### VQA score distribution

| Band | Count | Books |
|---|---:|---|
| 80-89 | 3 | CultureWars (88), Weimar (88), MapReduce (85) |
| 70-79 | 2 | Mearsheimer (79), Beale (74) |
| 60-69 | 3 | First Folio (66), Foucault (65), Monumental (60) |
| No VQA | 2 | BERT (timed out), Drug War Zone (0-byte KFX) |

Distribution aligns with prior predictions: digital-native books score 80+, scanned/facsimile books cluster 60-74, and extreme layouts (fiction with inconsistent typography, dense Greek commentary) hit the lower bands.

## Lesson 1 — Environmental preconditions are invisible until they break at scale

**Pattern:** A shell-invocation policy violation (bare `powershell` vs `pwsh`) produced 100% silent failure of a conversion phase, reported as 0.4s `kindle_conversion.success=false` with no diagnostic output. Every book's VQA was skipped, because VQA depended on KFX existing. Net result: aggregate batch reported WARN, not FAIL, despite pass rate of 0%.

**Why it worked as a pattern:** `test_pipeline.py --quick` skips the same code path, so the project's regression suite kept reporting green. The bug was exclusively triggered in full mode, in a batch context, on a machine where the default Windows PS 5.1 execution policy hadn't been overridden. Those three conditions all have to hold simultaneously; on any prior dev machine with a permissive PS 5.1 policy, the code appeared fine.

**How to apply (reusable):**

- For any pipeline that calls a shell subprocess, centralize invocation in a helper (`run_powershell(...)`, `run_sh(...)`) so policy decisions are made in one place. Currently this project has **two** call sites hardcoding `["powershell", ...]`; a single helper would have eliminated the bug class.
- For any gating phase in a batch runner, fail loud (`FAIL` not `WARN`) when the phase has 100% failure rate. Silent WARN at scale masks infrastructure breakage as data quality concern — the exact opposite of what humans expect.
- Match the global shell policy to the project's automated tests. If the rule is "always use pwsh," the test suite should verify it by running a trivial `pwsh -Command "Get-Date"` smoke during setup.

**Anti-pattern to avoid:** Relying on per-machine PS execution policy being permissive. This bug was dormant on dev machines for an unknown period because the policy was set there; it only surfaced on a fresh environment with Windows defaults. Environmental assumptions migrate silently across machines.

## Lesson 2 — VLM degenerate-response pattern is broader than SCRUM-292's original watch criterion

**Pattern:** The SCRUM-292 "uniform 50-score" watch criterion was too narrow. A2 v2 produced two more degenerate responses at different plateau values:

| Book | Pages | Scores | Interpretation |
|---|---|---|---|
| Foucault's Pendulum | 8 | all exactly 65 | Zero variance at rubric midpoint-65 |
| MapReduce | 8 | 7 at 85, 1 at 85 | 100% at 85 — zero variance at 85 |

Combined with SCRUM-292's original observation (Mexico Illicit A1: 7 pages at 50), the pattern across three observed books has plateau values at **50, 65, 85**. The common feature is not the value — it's the lack of variance across diverse page types.

**Why it works:** The VLM emits a characteristic "flat response" when it can't meaningfully discriminate. The exact plateau depends on prompt framing, model version, input-sample entropy. Detecting "flat response" is therefore better done by **per-book score variance** than by **exact value match**. Foucault at 65×8 is as degenerate as Mexico at 50×7 — the shared failure is zero standard deviation on non-cover pages.

**How to apply (reusable):**

- Update SCRUM-292 watch criterion to: *book-level per-page score standard deviation < 2 on non-cover pages* (or similar threshold). Value-agnostic, detects the true pattern.
- Add this as a fingerprint to `tools/visual_qa_fallback_fingerprints.json` so the fallback detector re-evaluates flat-response books against Claude. This extends SCRUM-281's fallback routing with a variance-based trigger.
- Keep the "uniform 50" specific check too; it's a historical variant worth catching.

**Anti-pattern to avoid:** Designing watch criteria by exact value match when the failure mode is structural (zero variance). Value matches only catch yesterday's version; structural checks catch tomorrow's.

## Lesson 3 — Observability gaps at the batch layer mask real pipeline health

**Pattern:** Three distinct observability issues surfaced in A2 v2, each masking different signals:

1. **0-byte KFX false success** (Drug War Zone). `Calibre` returned exit 0 with a KFX path, batch_qa accepted it, but `os.path.getsize(kfx_path) == 0`. Status reported PASS. VQA skipped silently because a subsequent `os.path.isfile` check in `run_visual_qa_for_book` probably treated the empty file as missing. No diagnostic trace of the discrepancy.
2. **VQA subprocess timeout at hard 300s cap** (BERT). A 13-page ML paper should take ~30s for VQA. 300s → the timeout is masking something (network hang? deadlock?). Book passed overall because batch status doesn't weigh VQA missing-data as a failure.
3. **VQA cost field always zero** (`api_cost_usd: 0.0` for every book). Matches what I saw on the canary. `run_visual_qa_for_book` pulls `report.get('cost_usd', report.get('api_cost_usd', 0))`, but `visual_qa.py` emits `estimated_cost_usd` in the summary and `api_cost_usd` is not in the report. One-line fix.

**Why it matters:** Each of these represents "batch says PASS but reality has a gap." The batch report is the interface humans use to decide next steps; if it lies about VQA running, cost, or KFX validity, wrong decisions follow.

**How to apply (reusable):**

- For every phase in a batch runner, define a specific postcondition check and assert it explicitly. `kfx_size_bytes > 0` should be required for KFX-success. Otherwise Calibre's self-reported exit code is the source of truth, which is a weak invariant.
- Surface subprocess-timeout as a distinct status from subprocess-error and from subprocess-success-with-no-data. All three currently collapse to "VQA not run" which carries zero diagnostic value.
- Field-name drift between the emitter (`visual_qa.py`'s `estimated_cost_usd`) and the consumer (`batch_qa.py`'s `api_cost_usd` lookup) is silent. A shared schema file or a TypedDict would catch this at edit time.

**Anti-pattern to avoid:** Assuming subprocess exit code 0 = success. Calibre, like many tools, can print success and produce 0-byte output. The batch runner has to verify the artifact.

## Observations worth filing (candidate tickets)

| # | Observation | Suggested ticket | Priority |
|---|---|---|---|
| O1 | Drug War Zone KFX success but 0-byte output; VQA silently skipped | SCRUM-294 | Medium |
| O2 | BERT_Pre_Training VQA timed out at exactly 300s | SCRUM-295 | Medium |
| O3 | Beale KFX is 1055 MB from 101 MB source (10x bloat) | SCRUM-296 | Low |
| O4 | VQA cost field always 0 in batch_qa reports | Add to SCRUM-293 follow-up scope or new ticket | Low |
| O5 | SCRUM-292 watch criterion too narrow (misses 65-plateau, 85-plateau) | Update SCRUM-292 description with corrected criterion | — |
| O6 | Chapter detection returns 0 on Foucault (fiction) and Beale (scan) — both are WARN due to this | Pre-existing known gap — not new, but now quantified | — |
| O7 | `batch_qa.py` is non-recursive; subfolder books are skipped | Already noted earlier in session — separate small ticket candidate | Low |

## Recommendation on SCRUM-290 close-out

Close **partial PASS** per the now-familiar *"close partial over force-pass"* pattern. Acceptance criteria met:

- ✓ A1 VQA rerun completed for all 6 books
- ✓ A1 comparison artifact produced (with methodology caveat — Lesson-5 page-overlap drift flagged and understood as baseline sampling-mode mismatch, not VQA stack drift)
- ✓ 10 pilot PDFs staged (with 2 substitutions)
- ✓ A2 v2 completed without runtime errors (after SCRUM-293 fix)
- ✓ JSON + MD + HTML batch reports produced
- ✓ Results in pattern DB (run ID `batch_20260421_102832`, future `batch_qa.py compare` works)
- ✓ Top 5 findings surfaced and categorized (this document)
- ✓ Decision: continue vs remediate (below)

Residuals to file as new tickets:

- **SCRUM-294** (Medium) — `batch_qa.py` should verify `kfx_size_bytes > 0` before accepting Calibre exit 0
- **SCRUM-295** (Medium) — BERT VQA 300s timeout root cause investigation
- **SCRUM-296** (Low) — Beale KFX 10× bloat; Calibre conversion efficiency

Residuals to update on existing tickets:

- **SCRUM-292** — broaden watch criterion from "uniform 50" to "zero-variance on non-cover pages"; document three observations (Mexico 50, Foucault 65, MapReduce 85)
- **SCRUM-291** — no recurrence in A2 v2 corpus; keep ticket open pending more data

**Next diagnostic batch:** defer until the residual tickets above are addressed. After: widen corpus beyond 10 books, add a double-column-fiction case (Foucault was accidentally this — need more), and add books from `F:\Books` subdirectories once `batch_qa.py` supports recursion.

## References

- Results corpus: `data/scrum290_a1_a2_pilot/` (A1 full + A1 quick + A2 v1 log + A2 v2 log)
- A2 v2 batch reports: `data/batch_reports/batch_20260421_102832.{json,md,html}`
- VQA per-book reports (A2 v2): `output/kindle/*_visual_qa_report.json`
- Pilot source PDFs: `test-corpus/a2-pilot/`
- SCRUM-293 fix commit: `12b6af3`
- Global shell policy: `~/.claude/CLAUDE.md` ("ALWAYS use `pwsh` ... never `powershell`")
- Related solution docs:
  - `docs/solutions/scrum-283-cloud-vlm-evaluation.md` (grader-leniency framework this batch reuses)
  - `docs/solutions/scrum-281-fallback-fingerprint-routing.md` (fallback corpus this batch extends)
  - `docs/solutions/scrum-274-phase5-closeout.md` (partial-close pattern this batch applies)
