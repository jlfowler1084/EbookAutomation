# ADR-EB-181: data/** exemption scope in worktree-policy

- **Status:** Proposed (pending coordinator review)
- **Date:** 2026-04-28
- **Ticket:** EB-181
- **Related:** SCRUM-306, INFRA-213

## Context

The SCRUM-306 audit examined all 71 non-merge master commits in the window between
policy activation (`a705ca4`, 2026-04-09) and `core.hooksPath` being wired (2026-04-23).
Of 38 violations, 9 involved `data/` files outside the two currently-exempt subtrees:

- `data/vqa_baseline_post_274/**` — 5 commits (SCRUM-282): initial baseline tracking,
  Atomic Habits re-capture from KFX path, five-book backfill with `capture_pipeline`
  provenance, PDF-sourced archive, and one unticketed "Stray Baseline" commit.
- `data/scrum290_a1_a2_pilot/**` — 1 commit (SCRUM-290): 14 pilot comparison JSON files.
- `data/scrum283_unit4_gate_result_a3b.json` and `data/scrum283_unit5b_gate_result_max.json`
  — 1 commit (SCRUM-283): cloud VLM gate results committed as unit close-out evidence.

In all cases the developer treated `data/` as broadly exempt because the data was
"capture output, not code." The hook was not wired at the time, so no enforcement
occurred. The question is whether the exemption policy should be retroactively
broadened to match that actual usage pattern, or kept narrow with explicit documentation
of the constraint.

The VQA baseline files in `data/vqa_baseline_post_274/` are the critical case: they are
read at runtime by `compare_vqa_reports.py audit` to assess page-sample parity, and they
feed the cloud VQA grader's regression gate. A corrupted or silently-updated baseline
file can cause false passes or false failures across the entire 6-book test corpus. This
makes them functionally equivalent to test fixtures — the kind of file that benefits from
PR review before landing on master.

## Decision

**Option B — Keep narrow.** The `exempt_paths` in `.claude/worktree-policy.json` are
unchanged. The two existing exemptions (`data/batch_reports/**` and `data/debug/**`) remain
the only `data/` subtrees that bypass worktree enforcement. All other `data/` content —
including VQA baselines, pilot comparison results, and gate result files — must ride a
worktree branch and receive PR review before landing on master.

No changes to `worktree-policy.json` are required by this decision.

## Consequences

### Positive
- VQA baselines remain subject to PR review. A corrupted or accidentally-regressed
  baseline cannot silently land on master without the coordinator seeing the diff.
- The "Stray Baseline" commit (`d16b5b3`) is correctly identified as a workflow failure,
  not a policy gap. Broadening would have normalized that behavior rather than correcting it.
- Policy intent stays clear: operational outputs (batch reports, debug logs) are exempt;
  research artifacts and test fixtures are not.
- The boundary is simple to explain: if a file under `data/` feeds a test assertion or
  a grader comparison, it belongs in a PR, not a direct master commit.

### Negative
- Developers capturing VQA baselines mid-ticket must create a worktree branch (or work
  in an existing one), commit there, and open a PR rather than committing directly to master.
  This adds roughly one step of friction to capture workflows.
- The `data/scrum*` one-shot research directories (SCRUM-283, SCRUM-290) are edge cases
  that feel low-risk but still require a worktree. This may feel bureaucratic for data
  that has no downstream consumers.

## Alternatives Considered

### Option A — Broaden to data/**
Add `data/**` as a single exempt path, matching actual observed usage.

**Pros:** Zero friction for any capture or research commit; removes the category of
"forgot to use worktree for data" violations entirely.

**Cons:** VQA baselines would bypass review. Given that these files feed the regression
gate, a silent update could mask a real pipeline regression (or introduce one). The
"Stray Baseline" (`d16b5b3`) — an unticketed, unreviewed baseline update — is exactly
the foot-gun this option would permanently enable. The audit found 9 of 38 violations
were data files; fixing the policy to eliminate friction is only appropriate if the
friction is truly unnecessary, which it is not for baselines.

### Option B — Keep narrow (chosen)
Leave `exempt_paths` as-is. Document the constraint explicitly in `CLAUDE.md`.

**Pros:** Baseline integrity is protected by PR review. Policy is consistent: operational
outputs are exempt, test fixtures are not. Constraint is now documented so future
developers understand it is intentional, not an oversight.

**Cons:** See Consequences / Negative above.

### Hybrid — Add specific named subtrees
Add patterns like `data/scrum*/**` and keep `data/vqa_baseline_*/**` non-exempt.

**Pros:** Would reduce friction for research/pilot data while preserving review for VQA
baselines.

**Cons:** The naming pattern `data/scrum*/**` is time-bound and would decay as ticket
prefixes change (e.g., `data/eb*/**`). Maintaining a growing list of exemption patterns
for one-off research directories is operational overhead with minimal benefit — those
commits are low-frequency and the worktree workflow is not materially more burdensome
for a one-file gate-result commit. The Hybrid option adds complexity without a
proportional gain in developer convenience.

## References
- SCRUM-306 (audit ticket — EA master-commit enforcement gap)
- INFRA-213 (root-cause — hooksPath unwired during policy window)
- `tools/scrum-306-audit.md` (detailed per-commit violation table)
- `tools/scrum-306-audit.json` (machine-readable audit data)
