# SCRUM-282 -- VQA Baseline Methodology: Standardize to KFX→Calibre Source

Model: SONNET
Justification: Multi-file implementation following a structured plan — 5 units touching `tools/visual_qa.py`, `tools/compare_vqa_reports.py`, 3 new test files, 6 baseline JSONs, `CLAUDE.md`, `feature-manifest.json`. Includes one destructive data step (U4) with a two-commit atomic protocol. Sonnet handles structured work with discipline well.

## Tickets

- **Primary:** SCRUM-282 -- VQA baseline methodology: standardize captures to KFX→Calibre source path
- **Blocks:** None (but enables re-inclusion of Atomic Habits in future SCRUM-280 R2 gate math)
- **Relates to:** SCRUM-274 (parent VQA provider work), SCRUM-275 (local provider Phase 2), SCRUM-279 (P1 `guided_json`), SCRUM-280 (P2 calibration — originated this drift finding), SCRUM-281 (fallback fingerprint routing — additive-fields pattern precedent), SCRUM-283 (cloud VLM evaluation)

## Estimated Scope

Multi-file change -- 5 implementation units, ~8 new or modified files plus 6 baseline JSON patches. Roughly 6 commits total (one per unit, with U4 split across two commits for rollback safety).

---

## Phase 0 -- Branch Setup

**Branch:** `worktree/SCRUM-282-vqa-baseline-methodology`
**Base:** `master`
**Worktree Mode:** create

Before any other work:

1. `git checkout master && git pull`
2. Create worktree: `git worktree add .worktrees/worktree-SCRUM-282-vqa-baseline-methodology -b worktree/SCRUM-282-vqa-baseline-methodology`
3. Change to worktree directory: `cd .worktrees/worktree-SCRUM-282-vqa-baseline-methodology`
4. Confirm branch: `git branch --show-current` should output `worktree/SCRUM-282-vqa-baseline-methodology`
5. Confirm clean state: `git status` should show no modifications
6. Verify `.claude/worktree-policy.json` exists and master is in `protected_branches`

Do not proceed to Phase 1 until all checks pass.

---

## Context

Read the full implementation plan at: `docs/plans/2026-04-20-001-feat-scrum-282-vqa-baseline-methodology-plan.md`

The plan is the source of truth for implementation details. The context below captures decisions made *during planning* that aren't self-evident from the plan and that would be re-derived (possibly differently) by an implementer starting from the plan alone.

**Design decisions made during planning:**

- **Field named `capture_pipeline`, not `source_format`.** The origin requirements doc at `docs/brainstorms/2026-04-20-scrum-282-vqa-baseline-methodology-requirements.md` proposed `source_format`, but `source_format` already exists in the repo with different, extension-derived semantics (`tools/test_pipeline.py:467`, `tools/pattern_db.py:162`, `module/EbookAutomation.psm1:6276`, and all 6 `test-corpus/*.baseline.json` files). A real downstream consumer — `tools/import_vqa_reports.py:92` — reads VQA baselines and derives format from the `book` field's extension, so adding a same-named field with pipeline-branch semantics would create silent conflation. Values are `"kfx-calibre"` / `"pdf-direct"`.
- **R1 audit compares `pages[].page_number` arrays, not `pages_total`.** `select_sample_pages()` in `tools/visual_qa.py:212` is deterministic on `(pages_total, bookmark_pages)` — coincidentally-matching page counts would pass a weaker audit with zero real signal. The sampled-pages check exercises the actual determinism surface.
- **U1 imports three Calibre helpers directly from `visual_qa.py`** — `convert_to_pdf`, `get_pdf_page_count`, `get_pdf_bookmarks`. Chosen over a new `--pdf-cache-dir` flag or refactoring to a shared helper module — smallest change, acceptable coupling. Unit tests monkeypatch these three to avoid invoking Calibre.
- **U3 warning uses normalized-stem matching** (4 steps: lowercase → non-alnum-to-space → strip ` - <author>` suffix → collapse whitespace). Exact-stem match would miss the motivating Atomic Habits case (PDF stem has underscores + no author; KFX stem has spaces + author suffix). The plan includes a worked example demonstrating the normalization triggers for that case.
- **U4 is two commits, not one.** Commit A = archive move; Commit B = promote validated re-capture. A temp-promote sequence validates in scratch space before either commit lands. This is the rollback guarantee.

**Options considered and rejected:**

- **Hard-block on PDF-source captures when a KFX shadows** → rejected. Would require an override flag (`--allow-pdf-baseline` or similar) that itself becomes a foot-gun. Warning with normalized matching catches the mistake class without blocking legitimate first-time PDF baselines for books that haven't been converted yet.
- **Re-running the 5 in-parity baselines through Claude Vision for verification** → rejected. Audit-via-sampled-pages is zero-API-cost and sufficient. R6 backfill is gated on U1 exit 0.
- **Tracking Calibre version in baseline schema** → rejected (YAGNI per Scope Boundaries). Accepted as a known false-positive cause for audit mismatches. When mismatch occurs, operator re-runs the original baseline capture against the same KFX to confirm whether Calibre output changed before re-capturing Claude.
- **Exact-stem match for U3 warning** → rejected. Would miss the Atomic Habits case that motivated R7 in the first place.
- **Creating `tools/audit_vqa_baselines.py` as a new tool** → rejected. Extending `tools/compare_vqa_reports.py` with an `audit` subcommand reuses the existing `_stems()` / `_load()` helpers and avoids ~100 lines of duplication.

**Hidden constraints / gotchas:**

- **U4's existing smoke-run output at `output/kindle/Atomic Habits…James Clear_visual_qa_report.json`** (Apr 18 dated) is NOT a baseline. It lives in `output/kindle/`, not `data/vqa_baseline_post_274/`. U4 must not overwrite it — capture to a temp dir via `--output-dir` (or equivalent), not to `output/kindle/`. The plan's risk table explicitly clarifies this.
- **Pre-flight grep before U4.** Search `prompts/`, `docs/`, `tests/fixtures/` for hardcoded references to the OLD PDF-sourced Atomic Habits baseline filename (`Atomic Habits_ Tiny Changes, Remarkable Results_ An Easy & Proven Way to Build Good Habits & Break Bad Ones_visual_qa_report.json`). Fix stale references before committing the archive move, or they become dangling pointers.
- **U1 unit tests must not invoke Calibre.** Monkeypatch `convert_to_pdf`, `get_pdf_page_count`, `get_pdf_bookmarks` in the pytest fixtures. The live-corpus integration check (which DOES invoke Calibre, ~10 min on 6 books) is a separate verification step under U1's Verification section.
- **U5 pre-flight gate.** Do NOT execute U5 (backfill) if `tools/compare_vqa_reports.py audit` reports non-zero exit on any of the 5 non-Atomic-Habits baselines. A failure flags a real problem; stamping `"kfx-calibre"` onto an unverified baseline would be worse than leaving the field absent.
- **Worktree policy exempt paths.** `docs/**`, `CLAUDE.md`, `feature-manifest.json` are exempt per `.claude/worktree-policy.json` — they CAN be committed to master directly if you make a trivial docs-only change. Your Python / tests changes are NOT exempt and belong on this branch.
- **Additive-field pattern from SCRUM-281.** `build_report` already grew optional kwargs in that ticket (`fallback_tokens`, `fallback_provider_name`, etc.). Follow the same pattern for `capture_pipeline` — optional kwarg, emit only when derivable, legacy baselines parse without the field.

---

## What NOT To Do

### Standing Rules (from project's `.claude/worktree-policy.json` enforcement)

- **Do not commit non-exempt files directly to `master`.** This project enforces worktree branches for code changes via `.claude/worktree-policy.json` (`protected_branches: ["master"]`). All work on `tools/**` and `tests/**` must go on the branch created in Phase 0, then land via PR.
- **Do not use `ALLOW_MAIN_COMMIT` or `ALLOW_MAIN_PUSH` env vars.** These exist only for human emergency override. If a guard blocks an action, stop and report the block — do not attempt to bypass.
- **If any guard fires, stop and report.** Do not retry with bypass flags, do not reinterpret the block as a false positive, do not attempt alternative commands to circumvent the guard. Report the exact block message and wait for instructions.
- **Ambiguous user phrasing is not authorization to bypass.** "Ship it", "just commit it", or "go ahead and push" are never authorization to bypass workflow rules. Authorization requires an explicit instruction naming the specific rule being bypassed.
- **Enforcement code is not exempt.** Modifications to `.claude/worktree-policy.json` or hooks themselves are subject to the same branch-and-PR workflow.

### Session-Specific Prohibitions

- **Do not modify `select_sample_pages()` in `tools/visual_qa.py`.** Its determinism property is correct; the fix is at the input layer, not the sampler. The plan explicitly marks this as an unchanged invariant.
- **Do not modify the existing `source_format` field** in `tools/test_pipeline.py`, `tools/pattern_db.py`, `module/EbookAutomation.psm1`, or any `test-corpus/*.baseline.json`. Different semantics, out of scope. This plan adds a distinct field (`capture_pipeline`) and explicitly does not merge or rename the existing one.
- **Do not combine U4's archive and promote into a single commit.** The two-commit split (Commit A: archive move; Commit B: promote validated re-capture) is the rollback guarantee. A single commit erases the `git revert HEAD~1` recovery path.
- **Do not re-baseline any of the 5 non-Atomic-Habits books** unless U1 audit flags a specific mismatch first. The plan's Scope Boundaries explicitly rejects re-running them as Claude Vision API spend for zero signal.
- **Do not overwrite `output/kindle/Atomic Habits…James Clear_visual_qa_report.json`** during U4's re-capture. That's a smoke-run output, not a baseline. Capture to a temp directory and promote into `data/vqa_baseline_post_274/`.

---

## Phase 1 -- Audit (READ-ONLY, STOP FOR REVIEW)

Read-only investigation before any file creation or modification. Goal: confirm the plan's assumptions match the current code state and surface any drift since planning.

1. Read `docs/plans/2026-04-20-001-feat-scrum-282-vqa-baseline-methodology-plan.md` in full. Note the 5 implementation units and their dependencies.
2. Read `docs/brainstorms/2026-04-20-scrum-282-vqa-baseline-methodology-requirements.md` for origin context (explains why `capture_pipeline` departs from origin's `source_format`).
3. Read `tools/visual_qa.py`:
   - Confirm `select_sample_pages()` at ~line 212 matches plan's signature expectations.
   - Confirm `convert_to_pdf()` at ~line 118, `get_pdf_page_count()` at ~line 166, `get_pdf_bookmarks()` at ~line 186 exist and are importable.
   - Confirm capture dispatch at ~lines 608-614 branches on input extension (`.pdf` / `.kfx` / `.azw3` / `.epub`).
   - Confirm `build_report` (baseline JSON writer) location and current keys.
4. Read `tools/compare_vqa_reports.py`:
   - Confirm `_stems()` at ~line 94 and `_load()` at ~line 123.
   - Verify the existing CLI layout (argparse + subcommand pattern) to mirror when adding `audit`.
5. List `data/vqa_baseline_post_274/` contents — confirm 6 baseline JSONs exist and one has `"book"` ending in `.pdf` (Atomic Habits).
6. List `output/kindle/*.kfx` — confirm all 6 KFX files exist with the stems the plan expects.
7. Inspect `.claude/worktree-policy.json` — confirm `docs/**`, `CLAUDE.md`, `feature-manifest.json` are in `exempt_paths` and `tools/**` / `tests/**` are NOT.
8. `grep -r "Atomic Habits_ Tiny Changes" docs/ prompts/ tests/ tools/` — record any hardcoded references to the OLD PDF-sourced baseline filename (Phase 5 U4 pre-flight will need to resolve these).
9. Confirm `docs/solutions/scrum-281-fallback-fingerprint-routing.md` Lesson 2 describes the additive-fields pattern you'll mirror in U2.

**Success criteria:**
- All file paths and line numbers referenced in the plan's "Relevant Code" section match what's on disk.
- The existing `source_format` field usage is confirmed in the 4 locations the plan names.
- Any hardcoded references to the old Atomic Habits baseline filename are catalogued for Phase 5.
- No blockers discovered that would invalidate the plan's approach.

**STOP.** Report findings before proceeding to Phase 2.

---

## Phase 2 -- U1: Baseline Audit Subcommand + Regression Fixtures

Implement Implementation Unit 1 from the plan. U1, U2, U3 are parallelizable; you can choose any order for Phases 2-4.

**Files to touch:**
- Modify: `tools/compare_vqa_reports.py`
- Create: `tests/test_baseline_audit.py`
- Create: `tests/fixtures/vqa_baseline_audit/atomic_habits_drift.json`
- Create: `tests/fixtures/vqa_baseline_audit/partial_overlap.json`
- Create: `tests/fixtures/vqa_baseline_audit/clean_parity.json`

**Implementation steps:**
1. Add the `audit` subcommand to `compare_vqa_reports.py` per the plan's U1 Approach.
2. Import `convert_to_pdf`, `get_pdf_page_count`, `get_pdf_bookmarks`, `select_sample_pages` from `tools/visual_qa.py`.
3. Implement the exit-code logic (0 all-parity / 1 any-skipped-only / 2 any-mismatch).
4. Create the 3 fixture JSONs with minimal baseline shape (`book`, `pages_total`, `pages[].page_number`).
5. Write pytest cases that monkeypatch the 4 imported `visual_qa.py` helpers — NO Calibre invocation in unit tests.
6. Cover the test scenarios enumerated in the plan's U1 Test Scenarios section.
7. Run `pytest tests/test_baseline_audit.py` — must pass before commit.
8. Run `python tools/compare_vqa_reports.py` in existing default mode — must still work (integration scenario in the plan).
9. Run the live-corpus integration check: `python tools/compare_vqa_reports.py audit` against the current `data/vqa_baseline_post_274/`. Record the result — it will preview what U4 and U5 need.

**Success criteria:**
- `pytest tests/test_baseline_audit.py` passes on all 3 fixtures.
- Existing smoke-comparison CLI path unchanged.
- Live-corpus audit produces a parity report. Expected: Atomic Habits mismatch (that's the bug); the other 5 should pass. If any of the other 5 fails, STOP and report before proceeding to Phase 5 — this is the Calibre-version / latent-drift case the plan's risks table covers.

**STOP.** Commit with message `feat(scrum-282): add baseline audit subcommand to compare_vqa_reports`. Report audit findings before proceeding.

---

## Phase 3 -- U2: `capture_pipeline` Field + Code-Path Derivation

Implement Implementation Unit 2 from the plan.

**Files to touch:**
- Modify: `tools/visual_qa.py` (capture dispatch ~608-614; `build_report`)
- Create: `tests/test_capture_pipeline_derivation.py`

**Implementation steps:**
1. At the dispatch branch point in `visual_qa.py`, capture which branch executes into a local variable (e.g., `capture_pipeline = "kfx-calibre"` if Calibre ran, `"pdf-direct"` if PDF-skip branch ran).
2. Thread the value through to `build_report` as an additive optional kwarg. Default to `None`; only emit the field in JSON output when the kwarg was set (follow `docs/solutions/scrum-281-fallback-fingerprint-routing.md` Lesson 2).
3. Write tests covering all 5 scenarios enumerated in the plan's U2 Test Scenarios section — especially AZW3/EPUB → `"kfx-calibre"` (pipeline-branch, not input-extension) and legacy-baseline parsing (field absent → no crash).
4. Do NOT touch the existing `source_format` field anywhere in the repo.

**Success criteria:**
- `pytest tests/test_capture_pipeline_derivation.py` passes.
- `tools/compare_vqa_reports.py audit` (from Phase 2) still loads legacy and new-format baselines without error.
- A manual capture against a `.kfx` input produces a JSON with `"capture_pipeline": "kfx-calibre"`.

**STOP.** Commit with message `feat(scrum-282): record capture_pipeline provenance on VQA baselines`. Report before proceeding.

---

## Phase 4 -- U3: KFX-Shadow Warning with Normalized Stem Matching

Implement Implementation Unit 3 from the plan.

**Files to touch:**
- Modify: `tools/visual_qa.py` (capture dispatch PDF branch; add `_normalize_book_stem()` helper)
- Create: `tests/test_pdf_kfx_warning.py`

**Implementation steps:**
1. Implement `_normalize_book_stem(stem: str) -> str` with the 4-step rule from the plan's U3 Approach (lowercase → non-alnum-to-space → strip trailing ` - <author>` → collapse whitespace).
2. Before the PDF-skip branch completes, compare the input PDF's normalized stem against normalized stems of `output/kindle/*.kfx`. If any match, emit `logging.warning(...)` naming both paths.
3. Do NOT block capture; do NOT raise; do NOT require an override flag.
4. Write isolated unit tests for `_normalize_book_stem()` (8+ inputs, idempotency check: `f(f(x)) == f(x)`).
5. Write integration-style tests for the warning firing — especially the Atomic Habits worked example (PDF underscored stem vs KFX spaced+author stem both normalize to the same string, warning fires).

**Success criteria:**
- `pytest tests/test_pdf_kfx_warning.py` passes.
- Manual run: invoking `visual_qa.py` against the actual Atomic Habits PDF (stem `Atomic Habits_ Tiny Changes, …, Break Bad Ones`) produces a warning referencing the KFX at `output/kindle/Atomic Habits Tiny Changes, …, Break Bad Ones - James Clear.kfx`.
- A `.kfx` input produces no warning.
- Capture still succeeds regardless of whether the warning fired.

**STOP.** Commit with message `feat(scrum-282): warn at capture when PDF input shadows existing KFX`. Report before proceeding.

---

## Phase 5 -- U4: Archive + Re-capture Atomic Habits (Temp-Promote, Two Commits)

Implement Implementation Unit 4 from the plan. **This is the destructive phase** — read the plan's U4 Approach in full before starting.

**Dependencies:** U1 (Phase 2) and U2 (Phase 3) must be complete. The audit subcommand validates the re-capture; the `capture_pipeline` field must be written by the new Atomic Habits baseline.

### Phase 5a -- Pre-flight (NO state changes)

1. Confirm drifted PDF-sourced baseline exists at `data/vqa_baseline_post_274/Atomic Habits_ Tiny Changes, Remarkable Results_ An Easy & Proven Way to Build Good Habits & Break Bad Ones_visual_qa_report.json`.
2. Confirm exactly one Atomic Habits KFX at `output/kindle/Atomic Habits Tiny Changes, Remarkable Results An Easy & Proven Way to Build Good Habits & Break Bad Ones - James Clear.kfx`.
3. `grep -r "Atomic Habits_ Tiny Changes" docs/ prompts/ tests/ tools/` — resolve any stale references before committing. These would become dangling pointers after the rename.

### Phase 5b -- Capture to scratch + validate

4. Invoke re-capture to a temp directory (NOT `output/kindle/` — that contains a smoke-run output from Apr 18 that must not be overwritten):
   ```bash
   mkdir -p /tmp/scrum-282-recapture
   python tools/visual_qa.py --provider claude --input "output/kindle/Atomic Habits Tiny Changes, Remarkable Results An Easy & Proven Way to Build Good Habits & Break Bad Ones - James Clear.kfx" --output-dir /tmp/scrum-282-recapture
   ```
   (If `--output-dir` isn't a valid flag on `visual_qa.py`, capture to a temp dir via `cd` first, or redirect the output file after capture.)
5. Verify the temp file's `capture_pipeline` field reads `"kfx-calibre"` and its `book` field ends in `.kfx`.
6. Run the audit subcommand against the temp file. If it reports mismatch or error, **HALT** — do not mutate the active baseline directory. Investigate before retrying.

### Phase 5c -- Commit A: Archive move

7. `git mv "data/vqa_baseline_post_274/Atomic Habits_ Tiny Changes, Remarkable Results_ An Easy & Proven Way to Build Good Habits & Break Bad Ones_visual_qa_report.json" "data/vqa_baseline_post_274/.archive/Atomic Habits_ Tiny Changes, Remarkable Results_ An Easy & Proven Way to Build Good Habits & Break Bad Ones_visual_qa_report_pdf-source.json"`
   (Create `.archive/` directory first via `mkdir -p data/vqa_baseline_post_274/.archive` — confirm via `ls -la` that the dot-prefix is preserved.)
8. Commit: `chore(scrum-282): archive PDF-sourced Atomic Habits baseline`.

### Phase 5d -- Commit B: Promote validated re-capture

9. Move the validated temp file into `data/vqa_baseline_post_274/` at the KFX-derived stem:
   ```bash
   mv "/tmp/scrum-282-recapture/Atomic Habits Tiny Changes, …, Break Bad Ones - James Clear_visual_qa_report.json" "data/vqa_baseline_post_274/"
   ```
10. Re-run `python tools/compare_vqa_reports.py audit` against the full active baseline directory. Confirm exit 0 on all 6 baselines.
11. Commit: `feat(scrum-282): re-capture Atomic Habits from KFX path`.

**Success criteria:**
- `data/vqa_baseline_post_274/.archive/` contains the PDF-sourced baseline with `_pdf-source` suffix.
- `data/vqa_baseline_post_274/` contains a new baseline at the KFX-derived stem with `"capture_pipeline": "kfx-calibre"`.
- `python tools/compare_vqa_reports.py audit` returns exit 0.
- Future smoke-run compare (existing `compare_vqa_reports.py` default mode) finds the new baseline by stem without manual aliasing.

**STOP.** Report commit hashes A and B before proceeding.

---

## Phase 6 -- U5: Backfill + CLAUDE.md + feature-manifest

Implement Implementation Unit 5 from the plan.

**Pre-flight gate:** U5 does not execute unless Phase 5's final `audit` run exited 0. If any of the 5 non-Atomic-Habits baselines failed audit, STOP and report — do NOT backfill `"kfx-calibre"` onto an unverified baseline.

**Files to touch:**
- Modify: 5 JSONs in `data/vqa_baseline_post_274/` (Decline of the West, Mexico Illicit, Oil Kings, Python in easy steps, Return of the Gods — NOT Atomic Habits, which already has the field from U4)
- Modify: `CLAUDE.md` (Visual QA System section ~line 164)
- Modify: `feature-manifest.json`

**Implementation steps:**
1. Patch each of the 5 baseline JSONs in place by adding `"capture_pipeline": "kfx-calibre"` adjacent to the existing `book` field. Preserve all other fields byte-for-byte.
2. In `CLAUDE.md` Visual QA section, add a terse rule: all Claude VQA baselines must be captured from the KFX→Calibre path, not original PDFs. Reference the `capture_pipeline` field and `compare_vqa_reports.py audit`. Note that `capture_pipeline` is distinct from the existing extraction-pipeline `source_format` field.
3. Register `compare_vqa_reports.py` in `feature-manifest.json` as a new top-level entry with `subcommands: ["compare", "audit"]` (follow the pattern of other multi-subcommand tools in the file).
4. Run `powershell -File tools/verify-manifest.ps1 -Verbose` — must report no removed features and the new `audit` subcommand registered.
5. Re-run `python tools/compare_vqa_reports.py audit` one more time — must still exit 0 after the field additions.

**Success criteria:**
- `git diff` of the 5 baselines shows ONLY the new `capture_pipeline` field added; no whitespace changes, no other field modifications.
- `CLAUDE.md` diff scoped to the Visual QA section.
- `verify-manifest.ps1` passes.
- `tools/compare_vqa_reports.py audit` still exits 0.

**STOP.** Commit with message `feat(scrum-282): backfill capture_pipeline on in-parity baselines + docs`. Report before proceeding.

---

## Phase 7 -- Verification

### Per-file verification

- **Static:**
  - `tools/compare_vqa_reports.py` has an `audit` subcommand; imports from `visual_qa.py` are explicit at the top of the file.
  - `tools/visual_qa.py` has `_normalize_book_stem()` helper and `capture_pipeline` threaded through `build_report`.
  - `_normalize_book_stem()` has unit tests covering the 8+ input cases from U3's test scenarios.
  - The 6 baselines in `data/vqa_baseline_post_274/` all have `"capture_pipeline": "kfx-calibre"`.
  - `.archive/` subdir exists with the PDF-sourced Atomic Habits baseline + `_pdf-source` suffix.
  - `CLAUDE.md` has the new baseline-capture rule.
  - `feature-manifest.json` has the new entry.

- **Runtime:**
  - `pytest tests/test_baseline_audit.py tests/test_capture_pipeline_derivation.py tests/test_pdf_kfx_warning.py` — all three pass.
  - `python tools/compare_vqa_reports.py audit` — exit 0.
  - `python tools/compare_vqa_reports.py` (default smoke-comparison mode) — still works, unchanged behavior.
  - `powershell -File tools/verify-manifest.ps1 -Verbose` — no removed features.

---

## Phase 8 -- Push and Report

**STOP before pushing.** Report all commits to the strategist.

After approval:

1. Push: `git push -u origin worktree/SCRUM-282-vqa-baseline-methodology`
2. **STOP before opening PR.** Report the pushed branch URL.

(The strategist will either open the PR themselves or authorize the Sonnet session to run `gh pr create`.)

---

## Rollback Procedures

U4 is the only destructive step. Rollback paths:

- **Between Phase 5c and 5d** (after archive commit, before promote commit): `git revert HEAD` restores the original baseline. Zero loss.
- **After Phase 5d** (both commits landed, later issue detected): `git revert HEAD~1..HEAD` atomically restores both the original baseline and the archive state. Zero loss.
- **Mid-re-capture failure** (Phase 5b): capture wrote to a temp dir, so nothing to revert. Investigate and retry.

---

## Cross-Project Coordination

This work is scoped to EbookAutomation. No shared interfaces touched (Supabase tables, vault paths, hook contracts). No coordination needed with SecondBrain, CareerPilot, or ClaudeInfra.

---

## Verification Checklist

- [ ] Branch was created via `git worktree add` in Phase 0 and all work happened in the worktree
- [ ] No commits to master were made for non-exempt files
- [ ] No `ALLOW_MAIN_COMMIT` or `ALLOW_MAIN_PUSH` env vars were used
- [ ] Phase 1 audit was completed read-only before any file creation
- [ ] `pytest` passes on all three new test files
- [ ] `tools/compare_vqa_reports.py audit` exits 0 on all 6 baselines
- [ ] `powershell -File tools/verify-manifest.ps1 -Verbose` passes
- [ ] U4 landed as exactly two commits (archive, then promote) — not one
- [ ] `output/kindle/Atomic Habits…_visual_qa_report.json` from Apr 18 is unchanged (smoke-run output, not a baseline)
- [ ] Branch is pushed but PR is NOT yet opened

---

## Report Structure

At each STOP gate, report back with:
1. **Findings** — What was discovered or changed
2. **Assumptions changed** — Anything that contradicts the plan or this prompt
3. **Options** — If a decision point was reached, what are the alternatives
4. **Recommendation** — Your recommended path, with rationale

At final completion, also include:
5. **Commit hashes** — For each commit made (expect 6: U1, U2, U3, U4-archive, U4-promote, U5)
6. **Out-of-scope findings** — Anything that warrants a follow-up ticket

---

## Invocation

```
claude --model sonnet "[SCRUM-282] VQA baseline methodology -- Read prompts/SCRUM-282-vqa-baseline-methodology.md and follow the instructions"
```

Alternative (inline via @-expansion):

```
claude --model sonnet "@prompts/SCRUM-282-vqa-baseline-methodology.md"
```
