---
date: 2026-04-28
parent_session: backlog-swarm-batch
related_pilot: INFRA-220 (ClaudeInfra) — protocol source
prior_pilot: SCRUM-309 followup (4-stream, validated)
streams: 4
coordinator_model: claude-opus-4-7[1m]
subagent_model: implementer (Sonnet)
---

# Parallelization Map — EB Backlog Swarm Batch (4 streams)

## Context

Joe asked the coordinator to find independent EB backlog tickets and run them as a parallel implementer swarm. After triage of 45 open EB tickets, four pass the disjoint-file-scope and no-cross-cutting-pipeline-mutation tests:

- **EB-205** — Install LAME so balcon emits .mp3
- **EB-181** — Decide `data/**` exemption scope in worktree-policy.json (judgment + ADR)
- **EB-88** — Bump pdfminer.six and pdfplumber pins
- **EB-30** — Create Claude + Codex review prompt templates

Excluded for this swarm: cross-cutting pipeline tickets (heading/TOC/footnote/VQA — historical regression hot zones), epics, business-research tasks, and tickets requiring interactive auth (EB-34).

Per Joe's instruction: subagents **commit and push within their worktree branch only**. The coordinator merges each branch into master after verification, to avoid worktree-policy hooks blocking direct master commits from subagents.

## Stream count

4 parallel streams, all independent (no rebase dependencies between them — fundamentally disjoint file scopes).

## Parallelization Map

| Stream | Worktree branch | Files touched (declared) | Depends on | Merge order | Intent summary |
|---|---|---|---|---|---|
| **A** | `worktree/EB-205-lame-mp3-encoder` | `tools/balcon/lame.exe` (new binary, optional), `tools/install-lame.ps1` (new), `docs/install/lame.md` (new); may reference `settings.json` only if balcon path config is required | none | 3rd | balcon's `-mp3` flag succeeds; a known-good prep-pack render produces a `.mp3` in `output/audiobooks/`; install procedure is repeatable on a fresh box; no edits to existing pipeline code. |
| **B** | `worktree/EB-181-worktree-policy-data-exemption` | `.claude/worktree-policy.json`, `docs/decisions/ADR-EB-181-data-exemption-scope.md` (new); CLAUDE.md only if narrow-stays decision is made | none | 1st | A clear decision (Option A broaden / Option B narrow / Hybrid) is recorded in an ADR; `worktree-policy.json` is updated to match (or explicitly left alone with rationale); no other policy fields changed. |
| **C** | `worktree/EB-88-bump-pdfminer-pdfplumber-pins` | `requirements.txt`, `dev-requirements.txt` (only if its pins also conflict) | none | 4th (last — biggest blast radius) | Pins resolve cleanly on a fresh Python 3.12 venv; full `test_pipeline.py` regression passes; `test_voice_tags.py` 88-test suite passes; no other deps changed. |
| **D** | `worktree/EB-30-review-prompt-templates` | `tools/review/claude-review-prompt.md` (new), `tools/review/codex-review-prompt.md` (new), `tools/review/review-brief-template.md` (new) | none | 2nd | Three new template files exist with the structure described in the ticket; templates include sample JSON fragments; no edits to existing files anywhere. |

## Shared interfaces (frozen before spawn)

These must NOT change in any stream. If a subagent needs to modify, it must stop and write `STATUS.md=BLOCKED_SHARED_INTERFACE`:

- `settings.json` (pipeline config) — Stream A may *only* edit if balcon requires a path entry; no other stream may touch it.
- `requirements.txt` — only Stream C may edit; A/B/D must not.
- `.claude/worktree-policy.json` — only Stream B may edit; A/C/D must not.
- `tools/review/` directory — only Stream D may add files; A/B/C must not create or edit anything inside.
- `module/EbookAutomation.psm1` — frozen for ALL streams. None should need to touch it.
- `tools/pdf_to_balabolka.py` — frozen for ALL streams.
- `feature-manifest.json` — frozen.
- `tests/expected_baselines.json` — frozen.

## Pre-spawn overlap check

```bash
# All 4 declared file sets are completely disjoint (different dirs / different files)
# No pre-spawn diff needed; runtime check is sufficient
```

## Runtime overlap check (per checkpoint return)

After each subagent's checkpoint, the coordinator runs:

```bash
git -C .worktrees/<branch_dir> diff master...HEAD --name-only
```

Reject the checkpoint with `DRIFT_DETECTED` if any file outside the declared list appears.

## Per-stream merge gate

| Stream | Gate (must pass before coordinator merges into master) |
|---|---|
| A (EB-205) | `python tools/test_pipeline.py --quick` passes; smoke test: a known WAV converts to a valid MP3 via balcon's `-mp3` path; `lame.exe` is discoverable by balcon (verified on coordinator's machine after merge, not inside the worktree). |
| B (EB-181) | ADR file exists and renders; `.claude/worktree-policy.json` parses as valid JSON; if narrow-stays, CLAUDE.md note is added. |
| C (EB-88) | Fresh `py -3.12 -m pip install -r requirements.txt` resolves cleanly in the worktree's isolated env; `python tools/test_voice_tags.py` passes 88/88; `python tools/test_pipeline.py --quick` passes. (Full corpus run is non-blocking — coordinator runs it post-merge.) |
| D (EB-30) | All three template files exist with the sections described in the ticket; each contains an explicit JSON sample fragment for output anchoring; no existing-file diffs. |

## Checkpoint commit definition

A checkpoint commit for each stream is:

1. Implementation files only (per declared Files-touched).
2. A `STATUS.md` at the worktree root (gitignored — internal status only) containing:
   - Stream label (A/B/C/D)
   - Files actually touched
   - Verification commands run + their exit codes
   - Any `BLOCKED_*` or `DRIFT_*` flags
3. Push of the worktree branch to origin (`git push -u origin worktree/EB-NNN-...`).
4. **No PR opened by subagent** — coordinator handles PR/merge.

## Merge protocol (coordinator-only)

Per Joe's instruction:

1. Verify each subagent's checkpoint diff against intent summary + declared files.
2. Run merge-gate checks listed above.
3. Merge order: B → D → A → C (lowest blast radius first; pin bump last to catch any regressions the other three streams might have introduced).
4. For each: `git checkout master && git merge --no-ff worktree/EB-NNN-... -m "Merge EB-NNN: ..."` then `git push origin master`.
5. After all 4 merge: full `python tools/test_pipeline.py` (not `--quick`) + `python tests/validate_against_baseline.py` as the final cross-stream regression gate.

## Risk register

- **EB-205** binary commit: if `lame.exe` is added to `tools/balcon/`, it's a binary in source control. Acceptable for this project (`tools/balcon/` already has bundled binaries). Subagent should explicitly call out the binary in its checkpoint.
- **EB-88** ResolutionImpossible: if the new pins also fail to resolve, the subagent must stop and report — do not silently downgrade to unpinned.
- **EB-181** judgment risk: this is a decision ticket. Subagent should produce a recommended decision but not finalize without surfacing the trade-off in the ADR; coordinator may flag for human approval before merging.
- **EB-30** schema drift: templates reference a JSON schema mentioned in EB-33 (not in this batch). Subagent must produce templates with placeholder/illustrative schemas, marking them as "to be finalized in EB-33."
