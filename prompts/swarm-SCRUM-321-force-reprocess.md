---
ticket: SCRUM-321
type: subagent-swarm-stream
model: claude-sonnet-4-6
branch: worktree/SCRUM-321-force-reprocess-switch
worktree_dir: .worktrees/worktree-SCRUM-321-force-reprocess-switch
swarm_session: 2026-04-25
created: 2026-04-25
---

# SCRUM-321 — Add `-ForceReprocess` switch to `Invoke-EbookPipeline`

## Mission
Implement the deferred AC4 from SCRUM-317. Add a single `[string[]]$ForceReprocess` parameter to `Invoke-EbookPipeline` that selectively bypasses `Test-AlreadyProcessed` for files matching any wildcard pattern, with a single WARN log line per match.

## Parallelization Map (per INFRA-216 pilot)
- **Branch:** `worktree/SCRUM-321-force-reprocess-switch`
- **Files touched:** `module/EbookAutomation.psm1`, `tests/Add-ProcessedFile.Tests.ps1`
- **Dependencies:** none — fully independent of SCRUM-308, 300, 295.
- **Shared interfaces frozen:** none. The `Test-AlreadyProcessed` signature does not change; only its call site is wrapped.
- **Overlap risk:** zero. No other ticket in this swarm touches the PowerShell module.
- **Merge order:** any time. Independent of other streams.
- **Merge gate:** Pester suite green (existing 5 tests + 3 new = 8 pass).
- **Checkpoint commit:** the single `feat(SCRUM-321):` commit on the branch tip.
- **Intent summary (drift defense):** "Add an opt-in operator flag to bypass cache for matching filenames; one param, one log line, three tests. Anything bigger is wrong."

## Worktree setup
1. Branch: `worktree/SCRUM-321-force-reprocess-switch`
2. Directory: `.worktrees/worktree-SCRUM-321-force-reprocess-switch`
3. **No `mklink /J` junctions** to `archive/`, `output/`, `inbox/`, `processing/`. CLAUDE.md 2026-04-22 incident: ExitWorktree traverses junctions and wipes the source. This ticket does not need data-dir access — pure module + Pester work.

## Spec (verbatim from ticket)
1. Add `[string[]]$ForceReprocess` parameter to `Invoke-EbookPipeline` in `module/EbookAutomation.psm1`.
2. When set, `Test-AlreadyProcessed` returns `$false` for any file whose name matches any pattern in `$ForceReprocess` (use PowerShell `-like` wildcards).
3. Log a single WARN line per match, exact format:
   `Pipeline: -ForceReprocess matched '<filename>' against '<pattern>'; bypassing already-processed check`
4. Add 2-3 Pester tests in the existing `tests/Add-ProcessedFile.Tests.ps1`:
   - Wildcard pattern match → bypass returns `$false`
   - Non-matching file → bypass returns `$true` (cache check still active)
   - Empty `$ForceReprocess` → behaves identically to current code

## Drift watchpoints (HARD)
- **DO NOT** retrofit `-ForceReprocess` semantics onto sibling cmdlets (`Convert-PdfToKindle`, `Convert-PdfToAudiobook`, etc.). Scope is `Invoke-EbookPipeline` only.
- **DO NOT** rewrite `Test-AlreadyProcessed`'s body. The bypass should be a thin pre-check at the call site (the per-file loop inside `Invoke-EbookPipeline` that calls `Test-AlreadyProcessed` before processing). Wrap the call: if any pattern in `$ForceReprocess` matches the filename via `-like`, skip the call and emit the WARN line. Find the call site with `Grep` for `Test-AlreadyProcessed` in `module/EbookAutomation.psm1`.
- **DO NOT** introduce new dependencies, helper functions, or module-private state. This is a single param, a `-like` loop, and a `Write-EbookLog -Level Warn` call.
- If the natural implementation requires more than ~15 lines of changes in `EbookAutomation.psm1`, stop and ask the coordinator. That's the smell.

## Pre-merge gates
1. `Invoke-Pester tests/Add-ProcessedFile.Tests.ps1` — all tests green, including the 3 new cases.
2. Sanity-import the module: `Import-Module .\module\EbookAutomation.psm1 -Force` returns no errors.
3. Manual smoke (write the result to PR description): run `Get-Help Invoke-EbookPipeline -Parameter ForceReprocess` — confirm parameter is documented.

You do **not** need to run the full Python regression suite. This change does not touch the extraction pipeline.

## Commit + PR
- Use **PowerShell 7** (`pwsh`), not Windows PowerShell 5.
- Commit prefix: `feat:` (new switch). Single commit acceptable; split if Pester additions are large enough to warrant their own.
- Open PR titled `SCRUM-321: Add -ForceReprocess switch to Invoke-EbookPipeline`. Body must include the AC checklist with each box checked + linked to the proving evidence (test name, log line sample).
- **DO NOT** merge yourself. The coordinator session merges.

## CE compound step
After PR merges, write `docs/solutions/scrum-321-force-reprocess-switch.md` (1 page max). Cover: AC4-deferred origin from SCRUM-317, why `-like` wildcards over regex, the WARN-not-INFO log level decision (operator-visible deliberate bypass).

## Out of scope (explicit)
- Persistent "force list" config in `settings.json`. Operator passes the switch per-run; no state.
- Removing entries from `processed.txt` after a forced re-run. The cache is a record of past success; force is a one-time bypass.
- Glob/regex parity. PowerShell `-like` wildcards only (`*`, `?`).

## Reporting back
On PR open, post a single status update to the coordinator with:
- PR URL
- Pester results (X/X passing)
- Commit SHAs
- Any drift you encountered and how you held the line
