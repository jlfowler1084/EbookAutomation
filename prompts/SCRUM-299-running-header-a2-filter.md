# SCRUM-299 Running-header A2 filter — extend OCR pre-scan to HTML extraction path
# Model: SONNET
# Justification: Plan-driven change to one file (tools/pdf_to_balabolka.py) plus one new test file. Regression-sensitive area per project CLAUDE.md — Sonnet handles structured, plan-driven work with well-defined test scenarios well.

## Tickets

- **Primary:** SCRUM-299 — Running header leaks into KFX body as un-stripped paragraphs (Phase 0 filter envelope gap)
- **Blocks:** None
- **Relates to:** SCRUM-301 (separate end-matter raw-HTML bleed, discovered during Phase 2), SCRUM-285 (prior related diagnostic), SCRUM-290, SCRUM-292, SCRUM-298 (upstream VQA context from Phase 1)

## Estimated Scope

Single-file implementation (`tools/pdf_to_balabolka.py`) + one new test file (`tests/test_scrum_299_running_header_a2.py`). 3 implementation units plus worktree setup + commit.

---

## Phase 0 — Branch Setup

**Branch:** `worktree/SCRUM-299-running-header-a2-filter`
**Base:** `master` (this project's default branch — not `main`)
**Worktree Mode:** create

Before any other work:

1. `git checkout master && git pull`
2. Confirm `.worktrees/` is gitignored: `git check-ignore .worktrees/` should return `.worktrees/`. If not, stop and report.
3. Create worktree: `git worktree add .worktrees/SCRUM-299-running-header-a2-filter -b worktree/SCRUM-299-running-header-a2-filter`
4. Change to worktree directory: `cd .worktrees/SCRUM-299-running-header-a2-filter`
5. Confirm branch: `git branch --show-current` → `worktree/SCRUM-299-running-header-a2-filter`
6. Confirm clean state: `git status` shows no modifications.

Do not proceed to Phase 1 until all checks pass.

---

## Context

Read the full implementation plan at: `docs/plans/2026-04-22-001-fix-scrum-299-running-header-a2-filter-plan.md`

Also read the origin diagnostic: `docs/solutions/scrum-299-structural-widgets-as-body-content.md` — **the Phase 2 section is authoritative**; Phase 1's recommendations were superseded.

This ticket was originally scoped to a two-variant bug (running-header bleed + anchor-icon widgets). Phase 2 render-check discovered that Variant B is a source-PDF artifact (XEP RenderX "Index of Pages of the Print Edition" widgets baked in by the publisher) and that `tools/visual_qa.py:663` skips Calibre when given a PDF input — our pipeline was never exercised by the reported VQA run. Ticket was descoped to A2-only. This prompt covers only the A2 running-header filter.

### Design decisions made during planning

- **Extend the existing OCR-path pre-scan at `tools/pdf_to_balabolka.py:3262`, do not invent a new filter.** The pre-scan's normalization + threshold shape is correct. It just doesn't reach the HTML extraction path (`extract_with_pdfminer_html` at line 5432, `_extract_html_with_pymupdf_columns` at line 5015). Those paths operate on `para_dicts` (list of dicts with `page_number` on each), not the flat `paragraphs` string list the pre-scan operates on.
- **Mirror the column-path filter at `pdf_to_balabolka.py:6574`** (the `_is_running_header_candidate` grouping). Same data structure (`para_dicts`), same page-grouping semantics, same mark-and-skip pattern. That is the structural template to follow.
- **Threshold: ≥5 distinct pages**, specifically tuned to protect Atomic Habits's 4-page cheat-sheet repeat. Minimum normalized length 15 chars (matches the OCR pre-scan).
- **Code/pre exclusion is required**, not optional. Python in Easy Steps has `window.mainloop()` appearing 6 times — it clears the ≥5 threshold and would false-positive-strip without the exclusion.

### Options considered and rejected

- **B1 anchor-semantic change (`<a epub:type="pagebreak">`).** Ruled out in Phase 2. Variant B is a source-PDF artifact; our anchor emission was never the problem. No code change to `pdf_to_balabolka.py:6696` or `:7115`.
- **Widening Phase 0's ALL-CAPS regex at line 3341.** Ruled out. Too risky for cross-corpus regressions per CLAUDE.md (heading-filter changes cascade into TOC/Calibre behavior), and does not solve the format-agnostic class-of-bug.
- **Coordinate-based bbox filter via PyMuPDF.** Deferred. Too much surface area for a single-book symptom; the format-agnostic filter is sufficient.
- **Refactoring the OCR pre-scan out of `fix_ocr_artifacts` into a shared helper.** Out-of-scope for this plan. If a clean extraction is obvious during Unit 2, you may do it as minor cleanup, but it is not required and should not delay Unit 2.

### Hidden constraints or gotchas

- `fix_ocr_artifacts` WOULD catch the Dionysius header if it ran. `pyspellchecker==0.9.0` is in `requirements.txt` and confirmed installed, so the function is not early-returning on an import failure. The problem is reach, not gating — `fix_ocr_artifacts` is invoked on the flat-`paragraphs` text path only (4 call sites at lines 10740, 10803, 12399, 12670), never on the HTML extraction path.
- **Python's `window.mainloop()` × 6 is the single most important regression canary.** If the `para_dicts` structural flag for code is absent on one of the two HTML paths, fall back to a text heuristic (parens, semicolons, trailing `()`, balanced brackets) — do NOT lower the threshold to compensate.
- **Atomic Habits's cheat-sheet line appears on 4 distinct pages.** The ≥5 threshold is specifically tuned to protect it. Do not relax to ≥4 without discussion.
- Per CLAUDE.md regression rule: **never stack multiple fixes without testing between each one.** If Unit 2's implementation causes a test to fail, stop, diagnose the specific failure, and report before attempting a second change.
- This project uses **PowerShell (pwsh), not bash**. The test suite runs via `python tools/test_pipeline.py`. Manifest verification: `powershell -File tools/verify-manifest.ps1 -Verbose`.
- Branch name is `master`, not `main`. The PostToolUse hook runs `test_pipeline.py --quick` after edits to pipeline files — expect that side effect.

---

## What NOT To Do

### Standing Rules

- **Do not commit to `master` directly.** All work happens on `worktree/SCRUM-299-running-header-a2-filter`. Commits land via PR per project policy.
- **Do not skip hooks (`--no-verify`), bypass signing, or otherwise circumvent pre-commit / pre-push enforcement.** If a hook fails, investigate the underlying cause and fix it. Do not retry with bypass flags.
- **Do not force-push.** If you need to rewrite a commit on this branch, stop and ask.
- **Do not modify `.gitignore`-matched files** (`.worktrees/`, `.claude/settings.local.json`, etc.).
- **If any guard or hook fires, stop and report the exact message.** Do not reinterpret the block as a false positive or attempt alternative commands to circumvent it.
- **Ambiguous phrasing is not authorization to bypass rules.** A general "go ahead" does not satisfy the requirement for an explicit bypass instruction. When in doubt, stop and ask the strategist: "This would require bypassing [specific rule]. Do you want me to proceed?"

### Session-Specific Prohibitions

- **Do not modify `<a id="page_N"></a>` anchor emission** at `tools/pdf_to_balabolka.py:6696` or `:7115`. Variant B was superseded in Phase 2 — source-PDF artifact, out of scope.
- **Do not widen Phase 0's ALL-CAPS regex** (line 3341) or Phase 0b's ALL-CAPS gate (line 3404). Regression risk; not the right fix for this class-of-bug.
- **Do not touch heading detection, TOC generation, bookmark reconciliation, footnote linking, or OCR cleanup.** CLAUDE.md regression-sensitive boundaries.
- **Do not run a Dionysius VQA re-run.** The original "Dionysius VQA zero widget-bleed flags" acceptance criterion was dropped because the icons are source-PDF artifacts, not pipeline output.
- **Do not rewrite the OCR-path pre-scan at line 3262 in place.** Only extend its reach.
- **Do not change `tools/visual_qa.py`.** The `input_ext == ".pdf"` branch at line 663 is correct behavior; leave it.
- **Do not widen scope to SCRUM-301** (end-matter raw-HTML bleed). Separate ticket, separate investigation.

---

## Phase 1 — Audit (READ-ONLY, STOP FOR REVIEW)

Before writing any code or tests:

1. **Read the plan in full:** `docs/plans/2026-04-22-001-fix-scrum-299-running-header-a2-filter-plan.md`.
2. **Read the origin diagnostic's Phase 2 section:** `docs/solutions/scrum-299-structural-widgets-as-body-content.md` (scroll past Phase 1 — the Phase 2 banner notes Phase 1 is superseded).
3. **Reproduce the current state:** run the equivalent of:
   ```
   grep -c '<p>\s*Dionysius the Areopagite: On the Divine Names and the C.E. Rolt Mystical Theology.\s*</p>' output/kindle/C_E_Rolt_*_test_dionysius.html
   ```
   Expect **145** on the current master HEAD. This is the baseline you are fixing.
4. **Inspect the existing OCR pre-scan:** [`tools/pdf_to_balabolka.py:3262-3339`](../tools/pdf_to_balabolka.py#L3262). Understand the three normalization variants (`_prescan_candidates`, `_prescan_nonum_candidates`, `_prescan_leading_candidates`) and thresholds (≥5 / ≥3 / ≥3).
5. **Inspect the column-path filter (the structural template):** [`tools/pdf_to_balabolka.py:6574-6604`](../tools/pdf_to_balabolka.py#L6574). Note the mark-and-skip pattern at line 6600.
6. **Inspect both HTML extraction entrypoints:** [`tools/pdf_to_balabolka.py:5015`](../tools/pdf_to_balabolka.py#L5015) (`_extract_html_with_pymupdf_columns`) and [`tools/pdf_to_balabolka.py:5432`](../tools/pdf_to_balabolka.py#L5432) (`extract_with_pdfminer_html`). Find the `<p>` emission sites in each.
7. **Grep for the `para_dicts` code/pre flag:** `grep -nE 'is_code|is_pre|is_monospace|_is_code|code_block' tools/pdf_to_balabolka.py | head -30`. Report what exists. If no flag exists on both paths, report it — the implementation will need the text-heuristic fallback described in Hidden Constraints.
8. **Locate the nearest regression tests:** `ls tests/` and identify the most similar test module to mirror (`validate_against_baseline.py` is the expected template).

### Success criteria

- You can explain out loud why Dionysius's 82-char mixed-case header slips Phase 0 + Phase 0b + column-path but would be caught by the OCR pre-scan (if it ran on the HTML path).
- You have identified both `<p>` emission sites and confirmed `para_dicts` carries `page_number` on every dict in both paths.
- You have reported whether a code/pre flag exists on `para_dicts` (names + files + lines) or, if absent, what text-heuristic you will use.

**STOP.** Report findings before proceeding to Phase 2.

---

## Phase 2 — Unit 1: Failing test

Write `tests/test_scrum_299_running_header_a2.py` per the plan's Unit 1 spec. Use existing test patterns (`tests/validate_against_baseline.py`).

### Requirements

- Test 1: Runs the Dionysius source PDF through the appropriate HTML extraction entrypoint (call it directly — do not run the full pipeline). Asserts `count_of_standalone_header_p_tags == 0`. **This test must fail on the worktree's current state** before any code change.
- Test 2 (canary): Runs Atomic Habits extraction and asserts the 4-occurrence cheat-sheet line (`"1.1: Fill out the Habits Scorecard. Write down your current habits to become aware of"`) is preserved. This test must pass on the current state.

### Success criteria

- `py -3.12 -m pytest tests/test_scrum_299_running_header_a2.py::test_dionysius_header_stripped -x` fails with a count-of-145 assertion error.
- `py -3.12 -m pytest tests/test_scrum_299_running_header_a2.py::test_atomic_cheatsheet_preserved -x` passes.

**STOP.** Report both test results before proceeding.

---

## Phase 3 — Unit 2: Implement A2 filter

Add `_mark_a2_running_headers(para_dicts)` to `tools/pdf_to_balabolka.py` and wire it into the two HTML extraction paths' `<p>` emission loops.

### Approach

Per the plan, mirror the column-path filter at line 6574 structurally:

1. Iterate `para_dicts`.
2. Skip entries flagged as code/pre (from Phase 1 audit) OR entries matching the text-heuristic fallback (parens, trailing `()`, semicolons, balanced brackets).
3. Skip headings (`p.get('heading_level')` or equivalent).
4. Skip entries with normalized length < 15 chars.
5. Normalize via the same three regex shapes the OCR pre-scan uses (raw, trailing-num-stripped, leading-num-stripped).
6. Group by normalized text → set of distinct `page_number`s.
7. For groups where `len(distinct_pages) >= 5`, mark matching dicts with `_is_a2_running_header = True`. Keep the first occurrence unmarked (follows column-path convention at line 6599) OR mark all (document the choice in the commit message either way).
8. In each HTML-emission loop, add a skip when `p.get('_is_a2_running_header')` is True.
9. Log the strip count with the same shape as the OCR pre-scan (`log(f"  A2 filter: stripped N running-header paragraphs across M patterns")`).

### Success criteria

- Both Unit 1 tests pass.
- Log output from a Dionysius extraction run shows `A2 filter: stripped ≥140` paragraphs.
- Log output from Atomic Habits and Python extractions either shows `A2 filter: stripped 0` or omits the line entirely.

**STOP.** Report the filter implementation site (line range), log output from each of the three test books, and any deviations from the plan.

---

## Phase 4 — Unit 3: Cross-corpus regression verification

Run the full project regression suite and confirm no other corpus book regresses.

### Required commands

1. `py -3.12 tools/test_pipeline.py` — full regression suite across all six corpus books.
2. `powershell -File tools/verify-manifest.ps1 -Verbose` — feature manifest verification per CLAUDE.md.
3. `py -3.12 -m pytest tests/test_scrum_299_running_header_a2.py -v` — new tests.

### Metrics to verify (per CLAUDE.md § Testing)

- Endnote link count has not decreased for any book.
- Chapter detection count is unchanged for every book.
- No body text has been tagged as headings.
- `<<PAGE:N>>` markers survive all processing phases.

### Success criteria

- `test_pipeline.py` exits clean with PASS on all six corpus books.
- `verify-manifest.ps1` reports no removed functions, files, or config keys.
- Python in Easy Steps's HTML intermediate still contains `window.mainloop()` × 6.
- Atomic Habits's HTML intermediate still contains the cheat-sheet line × 4.

**STOP.** Report test results and metrics diff versus baseline. If any metric regresses, **do not stack a second fix** — diagnose the specific failure and report it per CLAUDE.md.

---

## Phase 5 — Commit and Push

**STOP before committing.** Report all files to the strategist.

Expected file set:
- `tools/pdf_to_balabolka.py` (modified)
- `tests/test_scrum_299_running_header_a2.py` (created)

After approval:

1. Stage specifically named files (do not `git add -A`): `git add tools/pdf_to_balabolka.py tests/test_scrum_299_running_header_a2.py`
2. Commit:
   ```
   git commit -m "[SCRUM-299] fix: extend OCR pre-scan to HTML path for long mixed-case running headers

   Adds _mark_a2_running_headers(para_dicts) mirroring the existing column-path
   filter at pdf_to_balabolka.py:6574. Wired into both HTML extraction
   entrypoints (extract_with_pdfminer_html, _extract_html_with_pymupdf_columns).
   Threshold ≥5 distinct pages protects Atomic Habits's 4-page cheat-sheet
   canary; code/pre exclusion protects Python's window.mainloop() × 6 canary.

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
   ```
   Adjust the Co-Authored-By line to match the actual model you run as.
3. Push: `git push -u origin worktree/SCRUM-299-running-header-a2-filter`
4. **STOP before opening a PR.** The strategist opens the PR.

---

## Verification Checklist

- [ ] Branch was created via `git worktree add` and all work happened in `.worktrees/SCRUM-299-running-header-a2-filter/`.
- [ ] No commits were made to `master`.
- [ ] No `--no-verify` or hook-skip flags were used.
- [ ] Phase 1 audit completed before any file creation.
- [ ] Unit 1 test was written and confirmed FAILING before Unit 2's implementation.
- [ ] Unit 2 implementation mirrors the column-path filter pattern, not a from-scratch design.
- [ ] Python `window.mainloop()` × 6 preserved in the HTML intermediate.
- [ ] Atomic Habits cheat-sheet × 4 preserved in the HTML intermediate.
- [ ] `test_pipeline.py` passes on all six corpus books.
- [ ] Branch is pushed but PR is NOT yet opened.

---

## Report Structure

At each STOP gate, report back with:
1. **Findings** — what was discovered or changed.
2. **Assumptions changed** — anything that contradicts the plan or this prompt (especially around code/pre flag presence, `para_dicts` shape across paths, or threshold behavior).
3. **Options** — if a decision point was reached, what the alternatives are.
4. **Recommendation** — your recommended path, with rationale.

At final completion, also include:
5. **Commit hashes** — for each commit made.
6. **Out-of-scope findings** — anything that warrants a follow-up ticket. (Example: if you notice SCRUM-301's raw-HTML end-matter bleed has a pattern worth capturing, note it but do NOT fix it here.)

---

## Invocation

```
claude --model sonnet "[SCRUM-299] Running-header A2 filter -- Read prompts/SCRUM-299-running-header-a2-filter.md and follow the instructions"
```

Or, if using file-based invocation:

```
claude --model sonnet --prompt-file prompts/SCRUM-299-running-header-a2-filter.md
```
