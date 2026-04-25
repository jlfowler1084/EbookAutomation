---
ticket: SCRUM-300
type: subagent-swarm-stream
model: claude-sonnet-4-6
branch: worktree/SCRUM-300-table-extraction-pilot
worktree_dir: .worktrees/worktree-SCRUM-300-table-extraction-pilot
swarm_session: 2026-04-25
created: 2026-04-25
---

# SCRUM-300 — Pilot table-aware PDF extraction (PyMuPDF `find_tables`)

## Mission
Pilot **one** approach (PyMuPDF `page.find_tables()`) for table-aware extraction on Python in Easy Steps. Measure structural preservation against the pdfminer baseline. **Pilot = additional path, not replacement.** Do not auto-route, do not replace pdfminer as default.

## Parallelization Map (per INFRA-216 pilot)
- **Branch:** `worktree/SCRUM-300-table-extraction-pilot`
- **Files touched:** `tools/pdf_to_balabolka.py` (line ~5030, `_extract_html_with_pymupdf_columns`); a new opt-in flag/parameter; possibly a single new helper for table-to-HTML emission. **No edits below line ~10000** (where the footnote linker lives — SCRUM-308's territory).
- **Dependencies:** none textual — your edits live ~6000 lines from SCRUM-308's edits in the same file. **Coordinator-watch:** the HTML you emit for tables must remain compatible with the rest of the pipeline, including the (possibly broadened) footnote linker. Python in Easy Steps has minimal footnotes, so this is a low-probability collision.
- **Shared interfaces frozen:** the extraction-path return signature (HTML string + page-marker schema) — **do not** change. Downstream stages (heading classifier, TOC builder, footnote linker) consume this contract.
- **Overlap risk:** medium-low (same file, distant lines, distinct functions).
- **Merge order:** if both 308 and 300 are racing, serialize 308 → 300. You then validate against post-308 baselines.
- **Merge gate:** full `python tools/test_pipeline.py` green on all 7 books; `<table>` count > 0 in KFX-extracted HTML for Python in Easy Steps; the 5 non-Python corpus books take the **existing** extraction paths (the new path is opt-in only — verify by inspecting the per-book chosen-path log).
- **Checkpoint commit:** `feat(SCRUM-300):` on the new path; `test(SCRUM-300):` if regression cases added. Coordinator verifies the opt-in routing is real before merging.
- **Intent summary (drift defense):** "Pilot ONE approach (PyMuPDF find_tables) on ONE book (Python in Easy Steps). Opt-in path, not default. If pilot fails, open a sibling ticket — do NOT try camelot/tabula/heuristics in this PR."

## Worktree setup
1. Branch: `worktree/SCRUM-300-table-extraction-pilot`
2. Directory: `.worktrees/worktree-SCRUM-300-table-extraction-pilot`
3. **No `mklink /J` junctions.** CLAUDE.md 2026-04-22 incident.
4. Set env overrides for corpus access:
   ```pwsh
   $env:ARCHIVE_DIR = 'F:\Projects\EbookAutomation\archive'
   $env:OUTPUT_DIR  = 'F:\Projects\EbookAutomation\output'
   ```

## Spec (verbatim from ticket)
Extend the existing PyMuPDF code path (the current "column-aware" extraction path #3 in `pdf_to_balabolka.py`) to:
1. Detect pages containing tables via `find_tables()`.
2. Emit `<table>`/`<tr>`/`<td>` markup for detected tables during HTML generation.
3. Preserve non-table content via the existing extraction flow.

The new path should be **opt-in** — selected via a flag or pre-flight signal, not auto-applied.

## Success metric
1. Re-extract Python in Easy Steps through the new path.
2. Convert extracted HTML to KFX via existing Calibre 9.7 pipeline.
3. Extract KFX back to HTML and run the audit from `docs/solutions/scrum-285-python-kfx-layout-investigation.md`.
4. **Pass:** `<table>` count > 0 in the KFX-extracted HTML AND the operator-precedence section renders as a structured table (spot-check around source page 35).
5. **Secondary:** VQA re-score on the new KFX. Expect Claude-Sonnet score to improve from ~60 toward pass; expect Qwen family to hold or improve modestly. (VQA needs `OPENROUTER_API_KEY`, already set.)

## Regression gate (per project CLAUDE.md)
Extraction changes affect all downstream stages. **Before merging:**
1. `python tools/test_pipeline.py` — full 6-book regression.
2. Endnote link count has not decreased on any book.
3. No body text newly tagged as headings.
4. Chapter detection count correct on all 6.
5. PAGE markers survive all processing phases.

**Any regression on the other 5 books blocks the change.**

The five non-Python regression books MUST run through the **existing** pdfminer/pypdf paths, not the new table-aware path. The new path is opt-in. If the regression numbers move because you accidentally routed the other books through PyMuPDF tables, you've blown scope — fix the routing, not the regression.

## Drift watchpoints (HARD)
- **PILOT, not integration.** This ticket creates an additional, opt-in extraction path. **Do not**:
  - Make PyMuPDF tables the default for any book.
  - Add auto-routing heuristics ("if PDF has X, use tables-mode") to the pre-flight analyzer.
  - Refactor the three existing extraction paths.
  - Touch column detection logic.
- **One book's improvement, not corpus-wide rollout.** Python in Easy Steps is the proving case. Pilot succeeds = `<table>` markup survives Calibre round-trip on Python; pilot fails = open a sibling ticket for the next approach (camelot/tabula or heuristic reconstruction). **Do not expand this ticket** to try multiple approaches.
- **Do not** generalize to code blocks or bullet lists. Same root cause, separate tickets.
- If Calibre 9.7 strips or mangles the `<table>` markup, that's a pilot-fail signal — document it in the PR and **do not** start patching Calibre's import settings to make tables survive. Open a new ticket.
- **Do not** install new heavy dependencies (camelot-py, tabula-py, ghostscript, java). PyMuPDF is already a dependency. If you find yourself reaching for camelot, stop — that's a sibling ticket.

## Pre-merge gates
1. `python tools/test_pipeline.py` — full 6-book regression, zero new failures.
2. Python in Easy Steps re-extracted via new path: `<table>` count > 0 in KFX-extracted HTML, paste the count in PR body.
3. Spot-check screenshot of operator-precedence section in rendered KFX PDF (attach to PR).
4. VQA re-score on new Python KFX (paste numbers; pass-threshold improvement is secondary, not gating).
5. **The pre-flight analyzer must NOT auto-route any of the other 5 corpus books to the new path.** Verify by running test_pipeline against all 6 — capture the chosen extraction path per book in the log and paste in PR.

## Commit + PR
- Commit prefix: `feat(SCRUM-300):` for the new extraction path. `test(SCRUM-300):` if you add regression cases.
- Open PR titled `SCRUM-300: Pilot table-aware extraction via PyMuPDF find_tables`. Body must include:
  - Pilot success: yes/no with evidence
  - Per-book regression table (all 6)
  - Confirmation that the path is opt-in (link to flag/setting)
  - Per-book extraction path actually used (proving no auto-routing)
- **DO NOT merge.** Coordinator merges.

## CE compound step
After PR merges (or after a fail-and-spawn-sibling decision), write `docs/solutions/scrum-300-table-aware-pilot.md`. Cover: the SCRUM-285 → 300 chain, why pdfminer flattens tables, why we picked PyMuPDF first, the structural-preservation results, and which sibling ticket (if any) to open for the next approach.

## Out of scope (explicit)
- camelot-py, tabula-py, post-extraction heuristic reconstruction. **Sibling tickets only.**
- Auto-routing for technical content. Follow-up if pilot succeeds.
- Code blocks, bullet lists. Separate tickets.
- Replacing pdfminer as default extraction.
- VQA pass-threshold gate. Secondary metric only — pilot is judged on `<table>` survival, not VQA score.

## Reporting back
On PR open, post to the coordinator:
- PR URL
- Pilot result: PASS / FAIL
- Per-book regression table
- Whether pilot-fail → sibling ticket should be opened (and which approach)
- Any drift you suppressed
