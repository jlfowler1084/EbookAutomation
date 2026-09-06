# Scan-Bench Benchmark Harness (EB-392)

Operator runbook for the 13-book scan-quality benchmark. Ticket EB-392, epic EB-391.
The CLI (`tools/scan_bench.py`) is implemented alongside this data; the subcommands and
flags below are the names the plan (`docs/plans/2026-09-05-001-feat-eb392-phase0-scan-bench-plan.md`)
fixes for it — treat this file as the contract, not as proof the tool already exists.

## What this is

A fixed 13-book corpus (`manifest.json`) that mirrors the production PDF-to-KFX conversion
path plus local-only VQA, so every later EB-391 phase is measured against the same books the
same way. No extraction, heading, OCR, or Calibre logic is exercised differently than
production — the harness calls `Convert-ToKindle` the way `Invoke-EbookPipeline`'s PDF branch
does (classify → `-UseOCR` per verdict → `-UseHtmlExtraction -NoCache`), never
`Invoke-EbookPipeline` itself (that entry point archives sources, runs TTS, and has no
timeout or output-dir control).

## manifest.json schema

**Run-wide fields:**

| Field | Meaning |
|---|---|
| `schema_version` | Manifest format version (currently `1`). |
| `ticket` | `EB-392`. |
| `created` | Date the manifest (or its sha256 values) was last captured. |
| `provider.base_url` / `.model` | The resolved local VQA target (`sb-vision` alias). |
| `provider.expected_min_n_ctx` / `.expected_total_slots` | Row-0 label gates: preflight fails a `row0*` VQA run below these. |
| `vqa.dpi` / `.max_pages` / `.batch_size` / `.fallback_enabled` | Pinned VQA invocation flags — batch size 8 for continuity with every prior sweep and `data/vqa_baseline_post_274/`. |
| `cloud_policy` | `off` for cloud-off runs; the harness overrides this per-run via `--cloud-as-configured`. |
| `timeouts.*` | Size-scaled defaults: `convert_base_s + size_mb * convert_per_mb_s` once size exceeds `convert_mb_threshold` MB, floored at `convert_scan_floor_s` for scan-classed books; `vqa_base_s + pages * vqa_per_page_s` for VQA. |

**Per-book fields (array `books`, in run order A1-A7 then B1-B6):**

| Field | Meaning |
|---|---|
| `id` | `A1`-`A7` (Track A: scanned/low-quality, the improvement target) or `B1`-`B6` (Track B: general quality, must not regress). |
| `track`, `title` | Human labels. |
| `source_path` | Absolute Windows path, literal — never globbed or `Test-Path`-expanded (one source has brackets in its filename). |
| `sha256`, `size_bytes` | Written by `preflight --write-sha`; used for the sha256-relocation fallback if a path goes missing. |
| `pages` | From pypdf, falling back to PyMuPDF; `null` if both fail. |
| `expected_class` | The `classify_source.py` verdict recorded at manifest-authoring time — a snapshot for interpretation, not a live re-check the harness re-derives per run (it re-runs the classifier itself each conversion). |
| `script` | `latin` or `non-latin`. Gates whether `score_text_layer_quality` (English-common-word based) is comparable (see Guardrails). |
| `known_failure` | One line, from the origin document's book-selection table, naming why this book is in the corpus. |
| `timeout_overrides` | Per-book `{convert_s, vqa_s}` overrides for books whose size/format blows the default formula (A2: 116 MB JBIG2 facsimile; A7: CCITTFax). |
| `expected_chapters` | Optional, nullable; curated by hand for acceptance books before Phase 4. `null` everywhere in Phase 0. |
| `toc_source` | `bookmarks` if the source PDF has a pypdf outline with >= 1 entry, else `none` (`manual` is reserved for hand-curated cases). |
| `interpretation_flags` | e.g. `code_heavy` on B6 — a real grader false-positive risk on legible code blocks (EB-353). |

## Run recipe (from the main working tree, never a worktree)

```
preflight --write-sha
run --label row0-convert --skip-vqa
# --- after SB-231 raises sb-vision to n_ctx >= 32768 with --parallel 1 ---
preflight --label row0-vqa
run --label row0-vqa --vqa-only --resume
run --label row0-cloud --cloud-as-configured
report row0-convert
report row0-vqa
report row0-cloud
promote --run-id <id> --label row0-convert --dest <worktree-checkout>
promote --run-id <id> --label row0-vqa     --dest <worktree-checkout>
promote --run-id <id> --label row0-cloud   --dest <worktree-checkout>
```

Never run capture from a worktree: `archive/`, `test-corpus/a2-pilot/`, `inbox/`, `processing/`,
and `output/` are gitignored data directories that only exist in the main tree, and junctioning
them into a worktree has previously destroyed the main tree's data on worktree cleanup. Code
lands via PR before the run; the run itself executes from `F:\Projects\EbookAutomation\`.

## Row 0 has three parts, at the same commit — and why

1. **`row0-convert`** — conversion metrics only, cloud off, capturable under any server regime.
2. **`row0-vqa`** — the VQA half. `sb-vision` currently serves `n_ctx` 8192; the grader assumes
   32768. Grading at 8192 forces batch size 1 and truncates dense pages, producing rows that
   `compare` would refuse against any later baseline. **SB-231** (SecondBrain repo) raising the
   window to >= 32768 with `--parallel 1` (single-slot, for determinism) is a hard prerequisite
   for this label; preflight enforces it for any `row0*` VQA run.
3. **`row0-cloud`** — a cloud-as-configured comparator (Claude quality pass/rejoin/sub-headings,
   Gemini scan fallback, VQA Claude fallback, all as currently wired) captured now because after
   Phase 1 the Anthropic/Gemini call sites become opt-in and this comparator can no longer be
   produced from master. Expected cost: on the order of one dollar for all 13 books.

## Two-stage flow and gate policy

Stage 1 converts all 13 books (manifest order), recording metrics from the intermediate HTML and
conversion log regardless of what happens later. Stage 2 opens with the VQA **determinism gate**
(`vqa_determinism_check.py`, identical flags, `--tolerance 0`) run against this run's B1 (Oil
Kings) output — or the first successfully converted book of any track if B1 failed, recorded in
`run-meta.json`. Gate exit code decides what happens next:

- **0** — server is reproducible; grade every converted book; the gate's own run 1 doubles as
  B1's graded row (it is not re-graded).
- **1** — grading is skipped for every row (`vqa_skipped_untrusted_grader`); the harness prints
  the single-slot remediation and exits 1. `--grade-untrusted` is the explicit opt-in for
  exploratory (non-`row0*`) runs only — it grades anyway and marks `vqa_trusted: false`.
- **2** — provider unreachable; every row `vqa_skipped_provider_down`.

A per-book re-probe (`/v1/models` + `/props`) precedes every VQA call; a mismatch against
`run-meta.json` (served id, `n_ctx`, `total_slots`, `model_path`) marks that row and all later
rows `provider_drift` with `vqa_trusted: false`. A post-run canary re-run and re-probe on the gate
subject closes the stage.

## Directory layout

```
data/scan_bench/
  manifest.json          tracked — this file
  README.md              tracked — this file
  baselines/<label>/     tracked — promoted allowlist only (run-meta.json, run-summary.json,
                          report.md, vqa/<id>/*_visual_qa_report.json, determinism/**/*.json,
                          manifest.snapshot.json)
  runs/<run-id>/         GITIGNORED (data/scan_bench/runs/**) — everything a run produces:
                          kfx/, logs/, vqa/, determinism/, run-meta.json, run-summary.json
```

Raw runs stay local so a `git pull` after a baseline-data PR merges never collides with
in-progress run output, and so `Convert-ToKindle`'s `.intermediates/*.html` and `images/*.png`
never reach a PR by accident. `scan_bench promote --run-id <id> --label <label> [--dest <dir>]`
is the only path from `runs/` into `baselines/`, and it copies the allowlist above — nothing
else, including no `.kfx` or `.intermediates/` files.

## Disk expectations

Facsimile-class outputs (A2 First Folio, A1 Monumental Christianity) can produce ~1 GB of
combined KFX/intermediate-HTML/render-PNG output per run under `runs/<run-id>/`. Budget disk
accordingly before a full 13-book run; `runs/` is never committed, but it is not automatically
pruned either.

## Garble finding — definition

A **garble finding** is a VQA issue whose `category` or `description` falls in the garbled / OCR
/ illegible / extraction-failure family (per the EB-340 canary convention and
`docs/solutions/eb353-vqa-grader-code-false-positive-2026-06-02.md`). The Oil Kings (B1) canary
is expected to produce **zero** garble findings on every trusted graded row; any garble finding
on B1, or a B1 overall score below 85, is a run-level WARN, and a hard failure for `promote` of a
`row0*` label.

## Interpretation guardrails

- **Degenerate grader**: per-book stddev of non-cover-page scores below 2 means the grader is not
  discriminating between pages — treat the run's scores as uninformative, not as a finding.
- **EB-353 lens**: a low score on B6 (code-heavy) is *suspect* — the grader has a known
  false-positive pattern on legible code blocks — while a low score on an old scan (Track A) is
  *likely real*. Do not apply the same prior to both.
- **Non-Latin text quality is not comparable**: `score_text_layer_quality` is English-common-word
  based; A7's score is recorded but flagged `not_comparable_text_quality`, never compared to a
  Latin-script book or used as a pass/fail gate.
- **Single-page deltas are not findings**: only book-level aggregates (mean, stddev, coverage)
  cross the bar for a reported regression; one page moving a few points between runs is noise.
- **Never compare rows with different server regimes**: `n_ctx`, `total_slots`, `model_path`, and
  `batch_size_effective` must match between two rows before any score delta means anything;
  `compare` marks a mismatch `not_comparable` rather than emitting a number.
