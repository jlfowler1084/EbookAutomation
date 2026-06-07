# EB-380 — Steady-State Propose-Only Hermes Auto-Filer (v1, Phase 1)
# Model: SONNET
# Justification: Multi-file, cross-repo implementation following a structured, fully-reviewed plan. Sonnet handles structured plan execution well; the hard design decisions are already resolved in the plan.

## Tickets

- **Primary:** EB-380 — Steady-state auto-filer: Hermes-fed `_Inbox`→shelf enforce loop (`Invoke-BookFileGuarded.ps1`)
- **Blocks:** EB-379 (bulk import — stages into `_Inbox` and rides this loop)
- **Relates to:** EB-354 (epic), EB-381 (taxonomy evolution — sibling), INFRA-515 (Hermes control-plane), EB-366 (Qwen tail). Origin: `docs/brainstorms/2026-06-07-eb354-steady-state-autofiling-requirements.md`

## Estimated Scope

Deep, cross-repo. **Phase 1 only (7 units):** ~3 new files in EbookAutomation (`tools/book_filer/inbox.py`, `scripts/Invoke-BookFileGuarded.ps1`, plus 2 test files) + config/script edits, and 1 new no-agent cron script in **ClaudeInfra** (`configs/hermes/scripts/book-inbox-sweep.sh`). U8 (confirm/mover) is **explicitly out of scope** (Phase 2, separate plan).

---

## Phase 0 -- Branch Setup

**Branch:** `feat/EB-380-steady-state-autofiler`
**Base:** `master`
**Worktree Mode:** create

Before any other work:

1. `git checkout master && git pull`
2. Create worktree: `git worktree add .worktrees/feat-EB-380-steady-state-autofiler -b feat/EB-380-steady-state-autofiler`
3. Change to the worktree directory.
4. Confirm branch: `git branch --show-current` → `feat/EB-380-steady-state-autofiler`
5. Confirm clean state: `git status` shows no modifications.
6. Install deps if needed: `py -3.12 -m pip install -r requirements.txt -r dev-requirements.txt`.

**Worktree safety (SCRUM-301):** do NOT create `mklink /J` junctions inside the worktree to reach `archive/`/`output/`/`inbox/`/`F:\Books`. Run any pipeline/scan scripts from the **main tree** (`F:\Projects\EbookAutomation\`), or set env overrides — never junctions (a recursive worktree cleanup follows them and wipes the target).

Do not proceed to Phase 1 until all checks pass.

---

## Context

Read the full implementation plan at: `docs/plans/2026-06-07-001-feat-eb380-steady-state-autofiler-plan.md`. It is authoritative for per-unit files, approach, and test scenarios. Also read the origin requirements doc and the canonical design spec (`docs/superpowers/specs/2026-06-01-fbooks-organization-and-hermes-enforcement-design.md` §7–§10). Below is the context that shaped the plan and won't be obvious from the unit list alone.

**Design decisions made during planning:**
- **Propose-only v1.** The cron classifies `F:\Books\_Inbox` arrivals into a tiered queue and **moves nothing**. This is both the spec's prescribed accuracy break-in and the **ADR-0043 Tier-T2 ceiling** (propose, never auto-apply). Autonomous auto-move is **T3 — a new ADR**, not this work.
- **Architecture = thin PS guard wrapper + Python inbox driver.** `scripts/Invoke-BookFileGuarded.ps1` is the guarded cron entry point; `tools/book_filer/inbox.py` is a **new** driver that **imports** `book_filer` primitives (`classify.classify_name`, `scan._build_file_facts`/`_destination_path`, `move.plan_move`, `scaffold`, `reparse`, `identity`, `config`). It does **NOT** call `scan()`.
- **Queue lives OUTSIDE `F:\Books`** at `data/batch_reports/book_inbox_sweep/inbox-proposals.jsonl`.
- **Three tiers** (`propose`/`ambiguous`/`no_match`) + `derivative_parked`; monotonic, fail-closed (doubt → lower tier).
- **Discord digest** via ClaudeInfra's `tools/Send-DiscordWebhook.ps1 -ProjectName EbookAutomation`, called from the Windows worker.
- **Cron** clones ClaudeInfra `configs/hermes/scripts/qwen-feeder-sweep.sh`.

**Options considered and rejected:**
- Calibrated auto-move v1 / full pipeline in one push → rejected (propose-only break-in first).
- Telegram digest → rejected for v1 (outbound from a no-agent cron is unshipped, INFRA-502; Discord is proven).
- Reusing `scan()` for the inbox → rejected (`scan()` skips `_Inbox`; import primitives into a new driver).
- Trusting `shelf-index.json` as the dedup oracle → rejected (**no live producer** — only stale whatif copies exist; derive the key-set from the **live shelf** each sweep, fail-closed if absent).
- The gated `actuate.py` apply for confirm → rejected (needs a signed-GREEN whole-corpus manifest an inbox slice lacks; Phase 2's confirm will use `move.py` + its own journal).

**Hidden constraints / gotchas (verified landmines — each cost a prior incident):**
- `scan()` **skips `_Inbox`** (it's in `config.operational_folders`, pruned by `_build_skip_set`). Walk `_Inbox` explicitly.
- The G7 containment guard checks `config.library_root` (scan.py:491), **NOT** the `--library-root` arg. **Assert `config.library_root == --library-root` (normalized) and fail-closed**, or `-LibraryRoot` validation is decorative.
- `classify.py:132` confidence is `best_hits / total` (a **keyword-collision ratio**, not a wrong-shelf probability). U6 must **validate the confidence↔wrong-shelf correlation** before trusting thresholds; a ~20-file pass is *provisional*, graduation needs ~150+ live observations.
- **CRLF in the `.sh` → exit 64 → silent 3am loss** (INFRA-482). LF-only (`configs/hermes/.gitattributes`), forward-slash Windows paths (`F:/...`, never `\`, never `/mnt/f`).
- **Dot-source `$NoRun` scope leak → silent exit-0 no-op.** Snapshot the run decision + args **before any dot-source**; **verify artifacts, not exit codes**; add an entry-point child-process regression; **test-fire the cron on an already-handled cycle** before cutover.
- **No existing cron crosses into EbookAutomation** — verify `pwsh.exe` in `hermes-ubuntu` can reach `F:/Projects/EbookAutomation/...`, enforce **wrapper-on-master before cron activation**, and reject any `.ps1` path resolving under `.worktrees/`.
- Junction/reparse hazard (SCRUM-301): reparse-reject across **full ancestry** on every source; never create junctions; keep the run-dir outside `F:\Books`.

---

## What NOT To Do

### Standing Rules

- **Do not commit code directly to `master`.** All code changes go on the Phase-0 worktree branch and land via PR. (Docs/config-only single-file changes may go direct to master per the project policy, but this work is code — use the branch.)
- **If any guard/hook fires, stop and report.** Do not retry with bypass flags, do not reinterpret a block as a false positive, do not run alternative commands to circumvent it. Report the exact message and wait.
- **Ambiguous phrasing is not authorization to bypass.** "ship it" / "just commit" / "go ahead" never authorizes bypassing the worktree or PR workflow. Bypass requires an explicit instruction naming the specific rule.
- **Never `--no-verify`, never skip signing, never force-push** without an explicit instruction naming that bypass.
- **Run the test suite after every code change** (`python -m pytest tests/`). If a test fails, STOP and diagnose before stacking another fix.

### Session-Specific Prohibitions

- **DO NOT build U8 / Phase 2 (confirm/mover).** No `confirm.py`, no `Confirm-BookProposals.ps1`, no accept-list, no journal, no move logic. Only emit a **forward-compatible queue schema** with a reserved `accepted` sentinel + passive `taxonomy_version`.
- **DO NOT add any confirm/move parameter to the cron or the wrapper.** Auto-move is T3 (new ADR). The wrapper exposes **no** path that moves a file. Carry the comment barrier `# AUTO-MOVE IS T3 — do NOT add confirm invocation without a new ADR`.
- **DO NOT let the cron move a single file.** v1 is propose-only — the success criterion is *zero cron moves*.
- **DO NOT write the proposal queue inside `F:\Books`** (the codebase guards reject it).
- **DO NOT call `scan()` over `_Inbox`**, **DO NOT trust `shelf-index.json`**, and **DO NOT trust the `--library-root` arg** without the `config`-equality assertion.
- **DO NOT touch the migration actuator (`actuate.py`)** or its signed-manifest/backup gate.
- **DO NOT use Telegram** for the digest (Discord only in v1).
- **DO NOT register/activate the Hermes cron (U7)** until the wrapper has landed on `master` and you've verified `pwsh` reachability.

---

## Phase 1 -- Audit (READ-ONLY, STOP FOR REVIEW)

Read and confirm against the actual code before writing anything:

1. Read the plan + origin requirements + canonical design §7–§10.
2. Confirm the `book_filer` import surface exists with the expected signatures: `classify.classify_name`, `scan._build_file_facts`/`_destination_path`, `move.plan_move`/`execute_move`, `scaffold.ensure_operational_layout`/`_ensure_safe_dir`, `reparse.has_reparse_in_ancestry`, `config.load_library_config`/`LibraryConfig`, `identity.planned_calibre_key`, `taxonomy.load_taxonomy`.
3. Confirm `config/settings.json` `library` block (`library_root`, `operational_folders` incl. `_Inbox`, `scan_exclude`, `materialize_mode`) and `BookFinder.output_root` (~:189).
4. Confirm there is **no live `shelf-index.json` producer** (only stale whatif/debug copies) → the dedup oracle must be derived live.
5. Confirm the cron clone target (ClaudeInfra `configs/hermes/scripts/qwen-feeder-sweep.sh`) and `Send-DiscordWebhook.ps1 -ProjectName EbookAutomation`.

**Success criteria:** every import target + config key confirmed; the dedup-oracle gap confirmed; the cron + Discord patterns located.

**STOP.** Report findings (and any drift from the plan) before proceeding.

---

## Phase 2 -- U1: Config delta + `_Inbox` per-source scaffold

Add `ensure_inbox_subfolders(config)` to `tools/book_filer/scaffold.py` (creates `_Inbox\{BookFinder,Manual,Conversions,Migration}` via `_ensure_safe_dir`, reparse-checked). Do **not** re-add existing `library` keys. Define the run-dir (`data/batch_reports/book_inbox_sweep/`) outside the library.

**Success criteria:** subfolders created idempotently; junctioned `_Inbox` refused; existing config untouched. **STOP.** Report.

## Phase 3 -- U2: Inbox-scoped Python driver (`book_filer/inbox.py`) [TEST-FIRST]

The core. Per the plan's U2: assert `config.library_root == --library-root` first; take the `O_EXCL` lock (distinct loud refusal, not exit 0); walk `_Inbox` (eligibility: skip in-flight `.crdownload/.part/.tmp/.!qB` + zero-byte + settle-window; short-circuit unchanged `(path,size,mtime)`); per file reparse-check source → classify → tier (monotonic) → `_destination_path` → dedup vs the **live shelf oracle** (fail-closed if missing) → derivatives → `derivative_parked`; **upsert by sha** into the queue; tombstone `stale`/`superseded`. Emit Phase-1 states only + reserved `accepted` sentinel. **Moves nothing.**

**Success criteria:** full U2 test-scenario set in `tests/test_book_filer_inbox.py` passes (happy/tiers, in-flight skip, idempotency, supersede, stale, reparse→quarantine, lock-refuse, live-oracle dedup fail-closed, containment refuse). **STOP.** Report.

## Phase 4 -- U3 + U4: Guarded wrapper + Discord digest

`scripts/Invoke-BookFileGuarded.ps1` (`[CmdletBinding(SupportsShouldProcess)]`, snapshot-run-decision-before-dot-source, `-LibraryRoot` normalized+validated, `PYTHONHASHSEED=0`, `-WhatIf`, `-SweepNow`, **artifact-verify not exit-code**, auto-move comment barrier). Add the Discord digest via `Send-DiscordWebhook.ps1 -ProjectName EbookAutomation` (best-effort; no secret leak; heartbeat). Test via `tests/test_invoke_book_file_guarded_ps1.py` (pytest-drives-pwsh, **child-process entry-point regression**).

**Success criteria:** child-process fire writes the queue artifact; tampered `-LibraryRoot` refused; driver failure is loud; webhook never leaks; best-effort holds. **STOP.** Report.

## Phase 5 -- U5: §9 ingest rewiring (parallelizable)

Repoint `BookFinder.output_root` → `_Inbox\BookFinder` (config + `tools/book_downloader.py` + `EbookAutomation.psm1` fallbacks); add the scan-exclusion filter (skip `_`-prefixed, `Audio_Books`, `F:\Documents`) to `Scan-BooksFolder.ps1` + `Invoke-TesseractKindleBatch.ps1`; re-run the literal-path audit.

**Success criteria:** BookFinder resolves to `_Inbox\BookFinder`; scanners skip operational/non-library folders; audit clean. **STOP.** Report.

## Phase 6 -- U6: Tests + calibration gate

Determinism (run twice, `PYTHONHASHSEED=0`, byte-identical projection, oracle held fixed). Calibration **two-stage**: (a) set *provisional* thresholds on a representative sample + **validate confidence↔wrong-shelf correlation** (redefine HIGH as a conjunction if the bare ratio doesn't predict); (b) note graduation needs ~150+ live, per-section coverage. Lock the silent-no-op + moves-nothing regressions.

**Success criteria:** determinism green twice; provisional thresholds set with a recorded wrong-shelf signal; correlation validated or HIGH redefined. **STOP.** Report — this gates the (separate) Phase-2 confirm work.

## Phase 7 -- U7: Hermes cron (Target repo: ClaudeInfra — separate worktree + PR)

**Only after the EbookAutomation wrapper PR has landed on `master`.** In ClaudeInfra: create `configs/hermes/scripts/book-inbox-sweep.sh` (LF; `pwsh.exe -NoProfile -NonInteractive -File F:/Projects/EbookAutomation/scripts/Invoke-BookFileGuarded.ps1`). Verify `pwsh` reachability to the EbookAutomation tree; deploy `cp` → `~/.hermes/scripts/`; `cat -A | tail -1` ends `$`; register `hermes cron create "0 3 * * *" --no-agent --script book-inbox-sweep.sh --name book-inbox-sweep --deliver local`. Pre-invoke `.ps1`-exists check rejects `.worktrees/` paths.

**Success criteria:** `hermes cron list` shows the job (LF verified); a **test-fire on an already-handled cycle** is a clean no-op that produced an artifact + Discord heartbeat; a broken `.ps1` path alerts loudly. **STOP.** Report.

---

## Pre-Flight Environment Checks

- Python 3.12 (`py -3.12`), `pwsh` 7, `book_filer` importable.
- For U7 only: `hermes-ubuntu` WSL distro Running; `hermes` CLI at `~/.local/bin/hermes`; ClaudeInfra `configs/discord-webhooks.json` has an `EbookAutomation` webhook; `pwsh.exe` reachable from WSL to `F:/Projects/EbookAutomation/...`.

## Rollback Procedures

- v1 moves nothing, so the blast radius is config + a cron. To roll back: `hermes cron delete book-inbox-sweep` (or disable), `git revert` the config repoint (U5), and delete the run-dir queue. No `F:\Books` data is mutated by Phase 1.

## Cross-Project Coordination

- **Affected projects:** EbookAutomation (U1–U6), ClaudeInfra (U7).
- **Shared interface:** the `book-inbox-sweep.sh` ↔ `Invoke-BookFileGuarded.ps1` contract (args, `-LibraryRoot`, exit codes, queue path). Freeze it before building either side.
- **Coordination:** land the EbookAutomation wrapper on `master` BEFORE registering the ClaudeInfra cron. Two separate PRs.

## Smoke Test

- After U7: `hermes cron run book-inbox-sweep` on an already-handled `_Inbox` → expect a clean no-op that still writes the queue artifact + posts a Discord heartbeat. A silent exit 0 with no artifact = the dot-source/CRLF failure class — investigate, do not declare done.

---

## Phase N -- Verification

- **Static:** `python -m pytest tests/` green; the driver source contains no `os.replace`/`shutil.move`/`unlink` in the cron path (moves-nothing invariant); the wrapper snapshots the run decision before any dot-source; the queue path resolves outside `F:\Books`.
- **Runtime:** a child-process `pwsh -File` fire of the wrapper against a synthetic `_Inbox` produces a correct tiered queue and zero moves.

## Phase N+1 -- Commit and Push

Prefer **one commit per unit** (U1…U7) for a clean history. **STOP before committing** — report all files. After approval, push the branch with `-u origin feat/EB-380-steady-state-autofiler`. **STOP before opening the PR** (the main session holds merge authority).

---

## Verification Checklist

- [ ] All work happened in the `.worktrees/feat-EB-380-steady-state-autofiler` worktree
- [ ] No commits to `master`; no `--no-verify`/force-push/bypass
- [ ] Phase 1 audit completed before any file creation
- [ ] **Zero cron moves**; U8/Phase-2 NOT built; no confirm path on the cron/wrapper
- [ ] Queue written outside `F:\Books`; dedup oracle derived live; `config==-LibraryRoot` asserted
- [ ] `python -m pytest tests/` green; determinism gate green twice
- [ ] U7 cron registered only after the wrapper landed on `master`; LF verified; test-fired on a handled cycle
- [ ] Branches pushed but PRs NOT opened

---

## Report Structure

At each STOP gate: **Findings**, **Assumptions changed** (anything contradicting the plan), **Options** (if a decision point), **Recommendation**. At completion also: **Commit hashes** and **Out-of-scope findings** (follow-up tickets).

---

## Invocation

```
claude --model sonnet "[EB-380] Implement Phase 1 of the steady-state propose-only auto-filer -- Read prompts/EB-380-steady-state-autofiler.md and follow the instructions"
```
or:
```
claude --model sonnet --prompt-file prompts/EB-380-steady-state-autofiler.md
```
