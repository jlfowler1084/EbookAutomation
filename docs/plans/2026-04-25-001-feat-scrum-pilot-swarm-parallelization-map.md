---
date: 2026-04-25
parent_ticket: SCRUM-309 (closed) — followup swarm
related_pilot: INFRA-220 (ClaudeInfra) — protocol source
streams: 4
serial_baseline: SCRUM-316 (PR #18)
coordinator_model: claude-opus-4-7[1m]
subagent_model: implementer (Sonnet)
---

# Parallelization Map — SCRUM-309 Followup Pilot Swarm

## Context

The SCRUM-309 closure surfaced 9 followup tickets. After applying the project's regression-prevention rule (no parallel implementer dispatch on heading-detection / TOC / footnote / OCR code paths) and disjoint-file-scope analysis, 5 tickets are pilot-eligible:

- **Serial baseline (excluded from parallel batch):** [SCRUM-316](https://jlfowler1084.atlassian.net/browse/SCRUM-316) — metadata regex. Implemented serially by the coordinator session in worktree `worktree/SCRUM-316-metadata-series-prefix`. PR #18 open at <https://github.com/jlfowler1084/EbookAutomation/pull/18>. Establishes wall-clock baseline.
- **Parallel batch (4 streams):** SCRUM-313, SCRUM-317, SCRUM-318, SCRUM-319.

Excluded from this swarm:
- SCRUM-310, 311, 312 — investigation tickets, no implementer-checkpoint outcome.
- SCRUM-314, 315 — fall under the project regression-prevention rule (column extraction / footnote pairing). Diagnosis-first, not parallel dispatch.

## Stream count

4 parallel-eligible streams. Concurrency cap 3 (per INFRA-220 protocol); 4th queues until merge order frees its rebase target.

## Parallelization Map

| Stream | Worktree branch | Files touched (proposed) | Depends on | Merge order | Intent summary |
|---|---|---|---|---|---|
| **A** | `worktree/SCRUM-317-cache-poisoning-fix` | `module/EbookAutomation.psm1` (lines ~3097–3119 manifest helpers, ~3902 `Add-ProcessedFile` call site, plus ~3636 `Test-AlreadyProcessed` check) | SCRUM-316 (rebase on baseline) | 2nd | A book is added to `logs/processed.txt` only when the full requested chain (TTS + Kindle if enabled + MP3 if enabled) succeeded; partial successes do NOT mark the book processed. |
| **B** | `worktree/SCRUM-313-claude-chapter-json-parser` | `module/EbookAutomation.psm1::Get-ChapterStructure` (~line 4930) for parser tolerance + system-prompt update; `agents/structure-analysis/system-prompt.md` if used by chapter detection | SCRUM-316 (rebase on baseline) | 3rd | The chapter-detection JSON parser handles Claude responses that include conversational preamble or a single object instead of an array; failed parses fall back to PDF-bookmark mode rather than aborting; failed-parse raw responses are captured to `logs/chapter-detect-failures/`. |
| **C** | `worktree/SCRUM-318-vqa-evaluation-status` | `tools/visual_qa.py` (report-writer that sets `overall_score`/`overall_pass`); `tools/compare_vqa_reports.py` consumer; `tools/visual_qa_rubric.md` schema doc | none | 4th | VQA reports include an `evaluation_status` field; when status != `evaluated`, `overall_score` and `overall_pass` are `null` (not `0`/`false`); consumers handle the null case. |
| **D** | `worktree/SCRUM-319-vqa-payload-fallback` | `tools/visual_qa.py` (batch-loop + retry logic) | SCRUM-318 (rebase on C) | 5th (queued) | When a VQA cloud batch fails, the actual provider error is logged; a single-page-per-batch retry is attempted before giving up; for KFX > 30 MB or > 500 pages, DPI/page-count is auto-reduced on first attempt. |

Slug derivation: `<TICKET>-<3-to-5-word-summary-kebab>`.

## Shared interfaces (frozen before spawn)

The following must NOT change during the pilot. If a subagent needs to modify any of these, it MUST stop, write `STATUS.md=BLOCKED_SHARED_INTERFACE` with the file and reason, and return:

- `module/EbookAutomation.psm1::Export-ModuleMember` block at the bottom of the file. The set of exported function names is frozen.
- `module/EbookAutomation.psm1::Get-EbookConfig` and `Resolve-ProjectPath` (early-file helpers).
- `tools/visual_qa.py` JSON output schema for fields **other than** the new `evaluation_status` (Stream C may add the field; Stream D may not change the schema).
- `tools/visual_qa_rubric.md` page rubric (Stream C may extend with the new status field; no other edits).
- `feature-manifest.json` (no stream is permitted to modify it; the post-merge `verify-manifest.ps1` run is the consumer).
- All files matching `tests/expected_baselines.json` and `data/vqa_baseline_*` — frozen.

## Pre-spawn overlap check

Run on the coordinator before spawning any subagent:

```bash
cd /f/Projects/EbookAutomation
# Stream A vs Stream B (both touch module/EbookAutomation.psm1):
git diff master -- module/EbookAutomation.psm1 | head
# After both checkpoint commits:
git -C .worktrees/SCRUM-317-cache-poisoning-fix diff master...HEAD --name-only
git -C .worktrees/SCRUM-313-claude-chapter-json-parser diff master...HEAD --name-only
# Both are expected to list module/EbookAutomation.psm1 and nothing else.
# Compare line ranges per file to verify they are disjoint:
git -C .worktrees/SCRUM-317-cache-poisoning-fix log -p master..HEAD -- module/EbookAutomation.psm1 | grep -E '^@@' | head -20
git -C .worktrees/SCRUM-313-claude-chapter-json-parser log -p master..HEAD -- module/EbookAutomation.psm1 | grep -E '^@@' | head -20
```

If line ranges overlap (within ~20 lines of each other), pause and decide manually which stream merges first; the second rebases.

For Streams C and D (both touch `tools/visual_qa.py`), Stream D is queued until Stream C's PR is merged. Stream D then rebases on C's merge.

## Runtime overlap check (per stream return)

Coordinator runs after each subagent's checkpoint return:

```bash
git -C .worktrees/<branch_dir> diff master...HEAD --name-only
```

Compare against the stream's declared Files-touched cell. Any file outside the declared list → reject checkpoint with `SCAFFOLD_REJECT` or `DRIFT_DETECTED`.

## Merge gate

Order:

1. **SCRUM-316** (this session, baseline) — already in PR #18, awaiting user merge.
2. **Stream A** (SCRUM-317) — rebases on master post-316-merge if needed.
3. **Stream B** (SCRUM-313) — rebases on master post-A-merge if needed (same psm1 file).
4. **Stream C** (SCRUM-318) — independent file (`tools/visual_qa.py`); may merge any time after baseline.
5. **Stream D** (SCRUM-319) — queued until C merges; rebases on master post-C.

Post-merge verification between landings:
- Run `tools/verify-manifest.ps1` to confirm exported function counts and config keys still match.
- Run the quick test suite (`python tools/test_pipeline.py --quick`) after each psm1-touching merge.

## Checkpoint commit definition

A subagent's first commit must satisfy BOTH:

1. Modifies at least one production-code file in its declared Files-touched cell.
2. Exercises the core premise of its intent summary — typically an interface + a failing test, OR the smallest vertical slice that touches real behavior.

**Scaffold-only commits do NOT satisfy the checkpoint** (e.g., empty modules, test stubs only, comment-only edits, log-message-only edits, single-line constant edits with no test). The coordinator returns `SCAFFOLD_REJECT` and the subagent must land a substantive commit before continuing to Phase B.

For each stream, a passing checkpoint typically looks like:

- **A (SCRUM-317):** A new failing Pester test asserting "TTS:OK + Kindle:FAILED → not in processed.txt" plus the minimal `Add-ProcessedFile` guard to make it pass.
- **B (SCRUM-313):** A failing test asserting parser tolerance for one of the documented preamble responses, plus the smallest parser change to handle it.
- **C (SCRUM-318):** A failing test asserting `evaluation_status='api_failure'` + `overall_score=None` when all batches fail, plus the minimal report-writer change.
- **D (SCRUM-319):** A failing test asserting that a simulated batch-failure triggers a single-page retry, plus the minimal retry path.

## Hard constraints (from INFRA-220 — verbatim)

- `--no-verify` is forbidden anywhere. If a hook fails, write `STATUS.md=BLOCKED_HOOK_FALSE_POSITIVE` with hook name + full output.
- Subagents MUST NOT push to `main`. They push only to their declared branch.
- Subagents MUST NOT merge any PR. The user merges.
- Subagents MUST NOT spawn sub-subagents (no Task tool from inside an implementer).
- Subagents MUST NOT modify files outside their declared Files-touched list. If emergent need, write `STATUS.md=EMERGENT_SCOPE_NEEDED` with file and reason, return.
- Subagents MUST NOT invoke Atlassian MCP for tickets other than their own.
- gitleaks scan MUST run on staged files before each push: `gitleaks detect --no-git --source <staged-files>`. If findings, stop, write `STATUS.md=BLOCKED_SECRET_DETECTED`.
- Stage files by name (`git add module/EbookAutomation.psm1`); never `git add .` or `git add -A`.

## Coordinator audit per stream return (INFRA-221 compensating control)

```bash
# Reflog audit — catch any --no-verify usage
git -C .worktrees/<branch_dir> reflog --all | head -50 | grep -i 'no-verify' || echo "clean"

# Branch sanity
git -C .worktrees/<branch_dir> branch -a

# Main-delta audit — confirm no unexpected commits on main from this worktree
git -C .worktrees/<branch_dir> log origin/master..HEAD --all --oneline

# Scope check
git -C .worktrees/<branch_dir> diff master...HEAD --name-only
```

Any reflog `--no-verify` mention, unexpected branch, or commit on `master` from a worktree → STOP, escalate.
