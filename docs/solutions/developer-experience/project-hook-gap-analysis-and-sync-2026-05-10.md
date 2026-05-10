---
title: Project Hook Gap Analysis and Sync — EbookAutomation vs ClaudeInfra (EB-220)
date: 2026-05-10
category: docs/solutions/developer-experience/
module: EbookAutomation
problem_type: developer_experience
component: development_workflow
severity: medium
applies_when:
  - Onboarding a new project into the ClaudeInfra hook ecosystem
  - Auditing a project's .claude/settings.json against a reference project or global defaults
  - Applying session-continuity, output-compression, or cost-awareness hooks to a project that was missing them
tags: [hooks, settings, developer-experience, session-continuity, gap-analysis, qwen, infra-sync, claude-code]
---

# Project Hook Gap Analysis and Sync — EbookAutomation vs ClaudeInfra (EB-220)

## Context

When a project's `.claude/settings.json` is set up, it typically starts with only task-specific hooks
(e.g., a post-edit regression runner). Meanwhile, ClaudeInfra accumulates richer project-level hooks over
time — session continuity, token tracking, quality gates — that improve every session regardless of task
domain. Without a deliberate gap analysis, those improvements never propagate to sibling projects, leaving
them with cold-start sessions, no handoff artifacts, and no cost visibility.

The gap manifests as: sessions that restart from scratch without prior ticket/decision context, large tool
outputs that bloat the context window unchecked, no automatic prompt toward test coverage after code
changes, and no session-end artifact that the next session can load.

EbookAutomation reached this state: it had only `post-edit-test.ps1` (PostToolUse Edit|Write|MultiEdit)
as a project-level hook while ClaudeInfra had nine additional project-level hooks. EB-220 ran the gap
analysis and applied all Tier 1 + Tier 2 hooks in a single config-only commit (8bf3bc0, 2026-05-10).

## Guidance

**The gap analysis procedure:**

1. Read the target project's `.claude/settings.json` — list all existing hooks by event type.
2. Read `~/.claude/settings.json` — note what is already covered globally so you do not duplicate.
3. Read the reference project's (ClaudeInfra) `.claude/settings.json` — identify hooks present there but absent in the target.
4. For each gap hook, classify value as High/Medium/Low *for the target project's specific workflow*, not generically.
5. Apply Tier 1 (High) and Tier 2 (Medium) immediately. Skip Low or project-inappropriate hooks with a written rationale.

**Hook inheritance model (critical organizing principle):**

Claude Code applies hooks in layers: global `~/.claude/settings.json` fires for every project, then
project-level `.claude/settings.json` adds project-specific hooks on top. This means hooks that ClaudeInfra
added to global settings (e.g., `Invoke-HookHealthChecker`, `Invoke-MemoryDistiller`, `Invoke-PrDescriptionDrafter`)
are already effective in EbookAutomation without any project-level change. Only hooks that live in
ClaudeInfra's *project* settings need to be replicated.

**Value classification is project-specific.** The same hook can be Tier 1 in one project and Low in another:

| Hook | EbookAutomation | SecondBrain | Reason |
|------|----------------|-------------|--------|
| `AutoTestSuggester` | High | Skip | EB has `test_pipeline.py`; SB has no test suite |
| `SemanticSectionExtractor` | Low | High | SB has Obsidian vault workflow; EB does not |
| `SolutionsPropagator` | Medium | Medium | Both actively maintain `docs/solutions/` |
| `BashOutputParser` | Skip | Skip | EB test output already structured; SB is bash-light |

**What was applied to EbookAutomation (EB-220):**

```json
// .claude/settings.json additions
{
  "skillListingBudgetFraction": 0.03,
  "hooks": {
    "SessionStart": [
      {
        "hooks": [{
          "type": "command",
          "command": "pwsh -NoProfile -ExecutionPolicy Bypass -File \"F:\\Projects\\ClaudeInfra\\tools\\Invoke-SessionContextLoader.ps1\"",
          "timeout": 10,
          "statusMessage": "Loading prior session context..."
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "pwsh -NoProfile -ExecutionPolicy Bypass -File \"F:\\Projects\\ClaudeInfra\\tools\\Invoke-SessionDistiller.ps1\"",
          "timeout": 60,
          "statusMessage": "Qwen distilling session..."
        }]
      },
      {
        "hooks": [{
          "type": "command",
          "command": "pwsh -NoProfile -ExecutionPolicy Bypass -File \"F:\\Projects\\ClaudeInfra\\tools\\Invoke-SessionMemoryWriter.ps1\"",
          "timeout": 15,
          "statusMessage": "Writing session facts to memory..."
        }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "pwsh -NoProfile -ExecutionPolicy Bypass -File \"F:\\Projects\\ClaudeInfra\\tools\\Invoke-PreCommitReviewer.ps1\"",
          "timeout": 45,
          "statusMessage": "Qwen reviewing staged changes..."
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Read|Bash|Grep|Glob|WebFetch",
        "hooks": [{ "type": "command", "command": "...Invoke-ToolOutputCompressor.ps1", "timeout": 90 }]
      },
      {
        "matcher": "Grep",
        "hooks": [{ "type": "command", "command": "...Invoke-GrepResultRanker.ps1", "timeout": 45 }]
      },
      {
        "matcher": "Read",
        "hooks": [{ "type": "command", "command": "...Invoke-SolutionsPropagator.ps1", "timeout": 45 }]
      },
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "...Invoke-AutoTestSuggester.ps1", "timeout": 45 }]
      },
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{ "type": "command", "command": "...post-edit-test.ps1", "timeout": 120 }]
      },
      {
        "matcher": ".*",
        "hooks": [{ "type": "command", "command": "...Invoke-TokenBudgetSentinel.ps1", "timeout": 10 }]
      }
    ]
  }
}
```

All scripts are referenced by absolute path to `F:\Projects\ClaudeInfra\tools\`. No copying needed —
the tools live in ClaudeInfra and are shared across projects by reference. This is a structural
cross-repo dependency by design.

**Lifecycle order:** `SessionStart` fires once at open. `PreToolUse`/`PostToolUse` fire on every matching
tool call. `Stop` fires once at session end. Global hooks fire before project hooks at each event.

**Implementation:** This is a single-file config change. `.claude/settings.json` is listed in `worktree-policy.json`
`exempt_paths`, so the `worktree-guard` hook allows direct-to-master commit without a worktree branch.
Use an `implementer` subagent for the write, then read-verify before committing.

## Why This Matters

Without session continuity hooks, every session opens cold. The model has no memory of which ticket was
active, which approach was decided, or which dead ends were already tried. This produces repeated
diagnostic loops — time spent re-establishing context that was already known.

Without the Stop distiller and memory writer, decisions made during a session exist only in that session's
transcript. They do not surface in subsequent sessions unless the user manually re-explains them. Over a
project lifetime, this accumulates into a pattern where the same architectural decisions get re-litigated.

Without output compression and token budget tracking, large tool outputs (test runner output, grep hits
across a full corpus, bash pipeline logs) silently fill the context window. The model degrades before the
user notices, and there is no signal that cost is accumulating.

Without the pre-commit reviewer, CRITICAL static analysis findings can reach the repo. For EbookAutomation
specifically, where heading detection changes cascade into TOC generation and Calibre compatibility, a
pre-commit catch is worth more than a post-merge rollback.

## When to Apply

- When onboarding a project that has been active for more than a few weeks but still has a minimal `.claude/settings.json` with only task-specific hooks.
- After ClaudeInfra adds a new project-level hook — audit all sibling projects for applicability within the same sprint.
- When a project reaches a threshold of sustained activity (more than one active ticket per week) — session continuity hooks pay for themselves at that volume.
- When a project acquires a real test suite — `AutoTestSuggester` immediately becomes Tier 1.
- When `docs/solutions/` is being actively maintained — `SolutionsPropagator` immediately becomes Tier 1.
- When repeated cold-start friction is observed in session notes or reported by the user — apply `SessionContextLoader` and `SessionDistiller` as a targeted fix even outside a full gap analysis.

## Examples

**Before (pre-EB-220):** EbookAutomation had only one project-level hook:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{
          "type": "command",
          "command": "powershell -ExecutionPolicy Bypass -File tools/hooks/post-edit-test.ps1",
          "timeout": 120,
          "statusMessage": "Running quick regression tests..."
        }]
      }
    ]
  }
}
```

**After (post-EB-220):** Eight additional hook entries across four lifecycle events, plus `skillListingBudgetFraction: 0.03`.
The existing `post-edit-test.ps1` entry is retained — new entries layer on top without displacing it.

The net change: a session opening on any EB ticket now loads prior context automatically, compresses large
grep/test output in flight, blocks CRITICAL pre-commit findings, surfaces relevant `docs/solutions/` entries
when reading related files, and writes a structured handoff artifact when the session closes — none of which
required writing new scripts, only wiring existing ClaudeInfra tools into the project config.

**SecondBrain parallel (session history):** SecondBrain ran the same gap analysis on the same day (2026-05-10)
and its results were handed to the EbookAutomation session as a starting point. This created a consistent
rollout pattern: derive the global/project split from SB's analysis, then re-classify each hook for EB's
specific workflow. The EB session did not re-derive the full hook list from scratch.

## Related

- EB-220: Apply INFRA hook parity to EbookAutomation (config commit: 8bf3bc0)
- INFRA-347: Invoke-SessionDistiller
- INFRA-349: Invoke-SessionContextLoader
- INFRA-350: Invoke-PreCommitReviewer
- INFRA-351: Invoke-PrDescriptionDrafter (global — fires on `gh pr create`)
- INFRA-352: Invoke-MemoryDistiller (global)
- INFRA-357: Invoke-SessionMemoryWriter
- INFRA-334: Invoke-ToolOutputCompressor
- INFRA-342: Invoke-GrepResultRanker
- INFRA-343: Invoke-TokenBudgetSentinel
- INFRA-345: Invoke-SolutionsPropagator
- INFRA-346: Invoke-AutoTestSuggester
- INFRA-360: Invoke-QwenSelfAssessment stale log fix (Phase 2 log consolidation missed the self-assessment reader)
