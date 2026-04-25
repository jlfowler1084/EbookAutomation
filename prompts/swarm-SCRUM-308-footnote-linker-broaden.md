---
ticket: SCRUM-308
type: subagent-swarm-stream
model: claude-sonnet-4-6
branch: worktree/SCRUM-308-footnote-linker-broaden
worktree_dir: .worktrees/worktree-SCRUM-308-footnote-linker-broaden
swarm_session: 2026-04-25
created: 2026-04-25
---

# SCRUM-308 — Broaden footnote linker for italicized + inline-joined bodies

## Mission
Extend two regex patterns in `tools/pdf_to_balabolka.py` so the footnote linker recognizes italic-wrapped footnote entries and inline-joined paragraphs. Mexico goes from 256 → ≥450 linked pairs. The other six corpus books regress zero.

## Parallelization Map (per INFRA-216 pilot)
- **Branch:** `worktree/SCRUM-308-footnote-linker-broaden`
- **Files touched:** `tools/pdf_to_balabolka.py` (lines ~11289, ~11390, inside `_link_footnote_divs` and `_link_inline_note_paragraphs`); `tests/expected_baselines.json` (re-baseline only, separate commit).
- **Dependencies:** none textual — your edits live ~6000 lines from any other stream's edits in the same file. **Coordinator-watch:** SCRUM-300 also edits `tools/pdf_to_balabolka.py` (line 5030, table extraction). Logical handoff: SCRUM-300's new HTML output must remain compatible with the regex you broaden here. If you discover during testing that table-aware HTML breaks your regex (unlikely — tables don't typically contain footnote refs), flag immediately.
- **Shared interfaces frozen:** the `_link_endnotes()` strategy contract — input HTML schema and the `(linked, unlinked)` return tuple. **Do not** alter this signature or the strategy ordering.
- **Overlap risk:** medium-low (same file, distant lines, distinct functions).
- **Merge order:** if SCRUM-300 has not yet merged, you can land first. If both are racing, serialize: 308 → 300 (308's regex changes settle first; 300 then validates against the post-308 baselines).
- **Merge gate:** full `python tools/test_pipeline.py` green on all 7 books (6-corpus + Dionysius); `python tests/validate_against_baseline.py` within tolerance; Mexico ≥ 450 linked pairs; baseline re-capture in a separate commit.
- **Checkpoint commit:** two commits — `fix(SCRUM-308):` for the regex change, `test(SCRUM-308):` for the baseline re-capture. Coordinator verifies both before merging.
- **Intent summary (drift defense):** "Two regex patterns get an optional `<em>` group; one inner-loop scans inline-joined paragraphs. Mexico goes from 256 to ≥450 linked pairs. Six other books regress zero. No structural changes to the linker."

## Worktree setup
1. Branch: `worktree/SCRUM-308-footnote-linker-broaden`
2. Directory: `.worktrees/worktree-SCRUM-308-footnote-linker-broaden`
3. **No `mklink /J` junctions.** CLAUDE.md 2026-04-22 incident.
4. You need corpus access to run regression. **Set env overrides** in your PowerShell session before invoking the pipeline:
   ```pwsh
   $env:ARCHIVE_DIR = 'F:\Projects\EbookAutomation\archive'
   $env:OUTPUT_DIR  = 'F:\Projects\EbookAutomation\output'
   ```
   These point to the main repo's data directories. **Do not symlink, junction, or copy** them into the worktree.

## Spec (verbatim from ticket)
### Blind spot 1 — italicized footnote bodies
`_link_footnote_divs` entry pattern at `tools/pdf_to_balabolka.py:11289`:
```python
entry_pat = re.compile(r'<p>(\d{1,4})(?:\.\s*|\s+(?=[A-Za-z"<]))')
```
`_link_inline_note_paragraphs` note pattern at `tools/pdf_to_balabolka.py:11390`:
```python
note_pat = re.compile(r'<p>(\d{1,4})\.\s')
```
Both require `<p>` followed immediately by a digit. `<p><em>N. Author, Title.</em></p>` is invisible. Mexico has 35 such orphans.

### Blind spot 2 — inline-joined footnote paragraphs
When pdfminer merges adjacent footnote lines, the result is e.g.:
```html
<p><a id="footnote_fn5_101"></a><a href="#noteref_fn5_101">102.</a> Marosi, "Mystery Man Blamed"; Duncan, interview. 103. Blancornelas, <em>El cártel</em>.</p>
```
Strategy 5's `note_pat` only matches `<p>N.` at paragraph starts, so embedded 103, 104, etc. never produce anchor targets. Mexico has ~173 such inline extras inside already-linked paragraphs.

### Approach
1. Extend `entry_pat` and `note_pat` to accept an optional leading `<em>` (and matching `</em>` tail):
   `<p>(?:<em>)?(\d{1,4})(?:\.\s*|\s+(?=[A-Za-z"<]))`
2. Add a second pass inside Strategy 4 / Strategy 5 that scans **within** already-matched footnote paragraphs for inline-joined entries, producing additional anchor targets.
3. **Do not change** the overall strategy ordering or fallthrough thresholds.

## Acceptance
- [ ] Mexico `footnote_linked_pairs` ≥ 450 (was 256), `footnote_unlinked` falls by the same magnitude.
- [ ] No other corpus book regresses on `tests/validate_against_baseline.py`. Tolerance: per-book baseline floor.
- [ ] `tests/expected_baselines.json` `__known_issues__` entry for Mexico is updated (removed or rewritten) to reflect the new floor.
- [ ] Baselines re-captured with `python tests/recapture_baselines.py` after the fix; new numbers locked.

## Drift watchpoints (HARD)
- **ADDITIVE ONLY — strict definition.** The only edits permitted are:
  1. Extending `entry_pat` regex at line 11289 with optional `<em>`.
  2. Extending `note_pat` regex at line 11390 with optional `<em>`.
  3. Adding a single inner-loop block inside the existing Strategy 5 logic to scan for inline-joined entries within already-matched paragraphs.
  4. Updating `tests/expected_baselines.json` (in a separate commit, see below).

  **NOT permitted:** extracting regexes to module-level constants, adding helper functions, renaming local variables, re-ordering strategies, refactoring `_link_endnotes` or any of its callees, "cleaning up" anything. Diff to `pdf_to_balabolka.py` should read as ~5–15 net lines added.
- **Regression is the gate, not the linked-pair count.** If Mexico hits 600 but Decline of the West loses 5 pairs, that's a fail. Stop and report — do not iterate on the regex trying to thread the needle alone.
- **No diagnostic re-baselining.** Do not run `recapture_baselines.py` mid-iteration to "see if my fix passes now." Use `python tests/validate_against_baseline.py --verbose` to inspect tolerance diffs. Re-capture is the **last** step, after all other gates pass, in a separate commit.
- **Do not** touch other linker strategies (`_link_per_page_footnotes` etc.) unless their regex explicitly needs the same `<em>` widening for the same reason — and even then, document each one in the PR.

## Pre-merge gates
1. `python tools/test_pipeline.py` — full 6-book regression. **Must pass with zero new failures.**
2. `python tests/validate_against_baseline.py` — all books within tolerance.
3. Mexico-specific: linked pairs ≥ 450 (paste the post-run numbers in PR body).
4. Re-capture baselines: `python tests/recapture_baselines.py` — commit the updated `tests/expected_baselines.json` in a **separate commit** with prefix `test(SCRUM-308): re-baseline after linker broadening`.

## Commit + PR
- Commit prefix: `fix(SCRUM-308):` for the regex change. `test(SCRUM-308):` for the baseline re-capture commit.
- Open PR titled `SCRUM-308: Broaden footnote linker for italic + inline-joined bodies`. Body must include:
  - Before/after numbers per book (full table — Mexico + 6 others)
  - The exact regex diff
  - Confirmation that no strategy ordering changed
- **DO NOT merge.** Coordinator merges.

## CE compound step
After PR merges, write `docs/solutions/scrum-308-footnote-linker-italic-inline.md`. Cover: the SCRUM-305 bisect → 308-spawning chain, why these two blind spots are corpus-wide and not Mexico-specific, the additive-only discipline, and which other books picked up extra pairs (likely Decline of the West, Oil Kings).

## Out of scope (explicit)
- Replacing pdfminer to avoid the inline-joined merge in the first place. That's an extraction-layer concern.
- Generalizing to "any HTML wrapper around a digit" — only `<em>` is in scope. Future ticket if other wrappers (`<i>`, `<span class="…">`) appear.
- Fixing footnote bleed (SCRUM-315). Different ticket, different file area.

## Reporting back
On PR open, post to the coordinator:
- PR URL
- Per-book linked-pair before/after table
- Whether you re-baselined (yes/no, and the commit SHA if yes)
- Any signals of premise drift you suppressed
