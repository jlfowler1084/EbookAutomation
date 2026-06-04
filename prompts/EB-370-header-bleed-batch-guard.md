# Session: EB-370 — Header-bleed batch guard (detector + batch gate + corpus sweep)

**Model:** SONNET
**Why Sonnet:** Bounded feature implementation against a complete, source-verified plan — THINK + DO, not deep architecture. The hard design decisions are already made and committed.

**Primary ticket:** EB-370 (Task, Medium) — relates to EB-367 (Done).
**Heads-up ticket:** EB-369 (pre-flight SQLite stale-lock hang) — UNFIXED. See Hidden Constraints.

**Plan (authoritative):** `docs/plans/2026-06-04-001-feat-eb370-header-bleed-batch-guard-plan.md`
**Design spec (origin):** `docs/superpowers/specs/2026-06-03-header-bleed-batch-guard-design.md`

**Estimated scope:** 4 implementation units, ~1 new Python module + 1 PowerShell wrapper + 1 PowerShell edit + tests + 2 fixtures + manifest entry.

---

## Phase 0 — Branch setup (do this first)

This is code + a committed test fixture (NOT docs/config), so per ADR-EB-181 and the global
worktree policy it MUST land on a worktree branch via PR — never direct to `master`.

1. Confirm `master` is current: `git -C F:\Projects\EbookAutomation status -sb` (should be up to date with origin; the spec `15f6f98` and plan `db6fd9a` are already on master).
2. Create the worktree: branch `feat/EB-370-header-bleed-batch-guard` under `.worktrees/feat-EB-370-header-bleed-batch-guard` (follow `~/.claude/skills/worktree-management/SKILL.md`). Verify `.worktrees/` is gitignored first.
3. Install/verify deps (`py -3.12 -m pip install -r requirements.txt` if needed) and run a clean-baseline `python -m pytest tests/` so you know the starting state.

---

## Standing rules (always apply)

- **Shell:** PowerShell (pwsh / PS 5.1+). Windows paths only. No bash `&`, no Unix paths.
- **Python:** `py -3.12`. Use `logging` (not `print`) for diagnostics; reconfigure stdout/stderr to UTF-8 on Windows. Machine output (JSON) and the human summary go to **stdout via `print()`**; logs/warnings go to **stderr via `logger`** — mirror `tools/compare_vqa_reports.py`.
- **Test after every change.** Run `python -m pytest tests/` after each unit. If a test goes PASS→FAIL, STOP and diagnose before stacking another change.
- **Run `regression-check` / `verify-manifest.ps1`** before and after, per CLAUDE.md.
- **Commit per unit** on the worktree branch; open a PR at the end. Subagents may commit within the worktree but MUST NOT merge to master.

## What NOT to do (session-specific prohibitions)

- **Do NOT write anything to `F:\books`** — a directory-reorg job is running there this session. Reads are fine; writes are forbidden. The sweep reads source PDFs from `archive/`, not `F:\books`.
- **Do NOT touch the extraction hot path** — `tools/extract_tts_text.py` marking/rejoin logic and `module/EbookAutomation.psm1` extraction internals. EB-370 is a strictly **read-only** guard over the produced `_kindle.html`. Touching the hot path re-opens the regression-cascade surface this design deliberately avoids (see `docs/solutions/best-practices/pre-implementation-render-check-2026-04-22.md`).
- **Do NOT call `tests/recapture_baselines.py`** from the sweep — it overwrites `tests/expected_baselines.json`. Use `tools/test_pipeline.py` `run_extraction()` instead.
- **Do NOT junction data dirs (`archive/`, `output/`, `inbox/`, `processing/`) into the worktree.** Windows recursive delete traverses junctions and destroys the link target (recovered from this during SCRUM-301). Run the sweep from the **main working tree** (`F:\Projects\EbookAutomation\`) or set an `OUTPUT_DIR` env override — keep the worktree code-only.
- **Do NOT introduce a `pytest` marker** for the slow calibration tests — the repo has no marker config, so an unregistered marker only warns. Use env-gated skip (`RUN_CALIBRATION=1`), mirroring the existing PDF-dependent skip.
- **Do NOT add `config/settings.json` keys** — thresholds are CLI flags.

---

## Context (read before coding)

### Design decisions made during planning (and why)

- **Scan post-rejoin `_kindle.html`, read-only.** That's where welds become observable (the weld surface is `rejoin_html_fragments()` per the EB-367 solution doc). Format-time stripping is too late; pre-rejoin is too early.
- **HTML-observable discriminators only.** The EB-367 *fix* discriminates headers by `_margin_zone` (y-coordinate band), but that metadata is gone by the HTML stage. So the detector uses: a run of **2+ ALL-CAPS words** (letters + curly/straight apostrophes + hyphens), **±1–4 digit page-number adjacency**, **recurrence/density** (`distinct_pages >= 5 AND density >= 0.10`), and **normalized length `[6,40]`**. This is a regression *net over* the fix, not a reimplementation.
- **The length floor is 6, NOT A2's 15.** A2's 15-char floor is the literal reason it missed "PILGRIM PEOPLE" (14 chars) and the bug existed. Borrow A2's density gate (`extract_tts_text.py` `_mark_a2_running_headers`), lower the floor.
- **The 2+-ALL-CAPS-word rule structurally excludes the EXERCISE/SUMMARY/QUESTIONS false-positive class** (single words) that plagued the fix.
- **Glue-position classification.** Each `<p>` match is classified `standalone | glued-start | glued-end | mid-paragraph`. `weld_total` counts only glued-start/glued-end/mid-paragraph; `standalone` repeats go to an informational `standalone_repeats` bucket (a milder, different gap per SCRUM-299).
- **Exit codes via a `_compute_exit_code()` helper** so the JSON `exit_code` field equals the process return; precedence `3 > 2 > 1 > 0` (mirrors `compare_vqa_reports.py audit`).
- **Synthetic sensitivity fixture, not git-archaeology.** A small hand-crafted committed HTML fixture reproducing the EB-367 weld signature — deterministic, no PDF dependency, no fragile pre-fix checkout.
- **Coverage accounting** in the batch gate: report `books_in_batch` vs `artifacts_scanned` vs `artifacts_missing[]`; a missing `_kindle.html` is a loud WARN, never a silent "0 welds" pass (EB-149).

### Options considered and rejected

- **Fold into the VQA / baseline gate (spec Approach B)** — rejected: VQA is image/VLM + page-sampled (wrong altitude for a text defect); baseline validation doesn't run on arbitrary new batch output.
- **Inline assertion inside `extract_tts_text.py` (spec Approach C)** — rejected: awkward to emit batch-level reports/exit codes from the hot path; can't audit already-converted books; re-opens the regression-cascade surface.
- **`recapture_baselines.py` for the sweep** — rejected: mutates `expected_baselines.json`.

### Hidden constraints / gotchas

- **`argparse` default error exit is 2**, which collides with EB-370's "flagged" code. You MUST subclass `argparse.ArgumentParser` and override `error()` to `self.exit(3, ...)`. No existing tool does this — it's net-new. Add an explicit invalid-args test asserting exit 3.
- **Page anchors are `<a id="page_N"></a>`.** Filter anchor ids to `^page_(\d+)$` — `endnote_`, `noteref_`, `footnote_` ids also exist. `total_pages` = max page number seen (book span), fallback to distinct-anchor count if anchors are non-numeric/absent.
- **The corpus is the arbiter, not logical completeness** (EB-353, EB-355). Every heuristic clause is a new false-positive surface. If any rule makes a clean canary flag — Atomic Habits' 85-char repeating line, Python in Easy Steps' `window.mainloop()`, or EXERCISE/SUMMARY/QUESTIONS body labels — REVERT it, even if it looks logically sound. Use whole-token matching, never substring.
- **Bidirectional, ungameable calibration gate:** zero detections on the clean canaries AND positive detection on the synthetic weld fixture. A gate that flags everything (or nothing) is gameable.
- **Windows artifact matching:** use `-LiteralPath` for filenames containing `[...]`; match `$newKfx.BaseName` → `${BaseName}_kindle.html` in `output\kindle\.intermediates`.
- **EB-369 (UNFIXED) — SQLite stale-lock hang in pre-flight.** The calibration sweep re-extracts books, which runs pre-flight analysis. If extraction hangs on a SQLite lock during the sweep, that is **EB-369, not an EB-370 defect** — surface it, don't fight it. If it blocks calibration, complete the detector + unit tests + manifest (Units 1, 3, 4) and report the sweep (Unit 2 calibration) as blocked-on-EB-369 rather than forcing it.

---

## Phases (one per plan unit; execute in order, test-first)

**Phase 1 — Read-only audit (no edits).** Read the plan and the referenced files: `tools/compare_vqa_reports.py` (exit-code/JSON/logging patterns), `tools/extract_tts_text.py` `_mark_a2_running_headers` + page-anchor emission, `tests/test_eb367_header_bleed_html.py` (worktree path resolution), `tools/test_pipeline.py` `run_extraction`, `tools/run_overnight_batch.ps1`, `feature-manifest.json`, `tools/verify-manifest.ps1`. Confirm the plan's assumptions still hold; report any drift before coding.

**Phase 2 — Unit 1: Detector core + CLI** (`tools/check_header_bleed.py` + `tests/test_header_bleed_detector.py` + `tests/fixtures/header_bleed_*.html`). Test-first: write the synthetic-HTML scenarios and commit the two fixtures, then implement until green. Cover every scenario in the plan's Unit 1 (happy/edge/error/determinism, including invalid-args→3). Commit.

**Phase 3 — Unit 2: Sweep wrapper + calibration** (`tools/sweep_header_bleed.ps1` + env-gated calibration tests). Reuse `run_extraction()`; restrict to the 9 PDF baseline books + Pilgrim (Sherlock EPUB deferred). Run from main tree / `OUTPUT_DIR`. Calibration: determinism + zero-FP canaries + positive fixture. If EB-369 blocks, mark Unit 2 calibration blocked and continue. Commit.

**Phase 4 — Unit 3: Batch Phase 2.5 gate** (`tools/run_overnight_batch.ps1`). Insert between Phase 2 (pipeline) and Phase 3 (VQA); scan this-run `$newKfx` HTML; coverage accounting; status accumulator with precedence `3 > 2 > 1 > 0`; `exit $batchStatus` as the last line. Never abort mid-run. Verify by a small dry-run. Commit.

**Phase 5 — Unit 4: Manifest registration** (`feature-manifest.json`). Add `python_cli_modes[]` + `critical_files[]` entries (set `min_lines` ≈ 80% of the final module line count). Run `powershell -File tools\verify-manifest.ps1 -Verbose` → exit 0. Commit.

**Phase 6 — Ship.** Full `python -m pytest tests/` green; `RUN_CALIBRATION=1 python -m pytest tests/` green (or EB-369-blocked, noted); `verify-manifest.ps1` 0; regression-check clean. Push the worktree branch, open a PR referencing EB-370, and post a Jira link comment. Do NOT merge — main session holds merge authority. Use the `ship` skill.

---

## Report structure (end of session)

1. **What landed** — per unit, with the commit SHAs on the worktree branch and the PR URL.
2. **Test evidence** — paste the `pytest` summary lines (unit + calibration), the `verify-manifest.ps1` result, and the detector's exit code on the weld fixture (2) vs clean fixture (0).
3. **Calibration verdict** — determinism pass, zero-FP on canaries, positive on the fixture (or EB-369-blocked).
4. **Anything deferred / blocked** — especially EB-369 interference, and the EPUB sweep non-goal.
5. **Compounding** — note that a `docs/solutions/` entry on the header-bleed *guard* should follow (CE cycle step 5), to be done after merge.

---

## Invocation

```
claude --model sonnet "[EB-370] Header-bleed batch guard -- Read prompts/EB-370-header-bleed-batch-guard.md and follow the instructions"
```
or:
```
claude --model sonnet --prompt-file prompts/EB-370-header-bleed-batch-guard.md
```
