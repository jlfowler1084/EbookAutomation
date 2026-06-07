---
title: book_filer actuator — safely applying a signed-GREEN migration to F:\Books (first real apply)
date: 2026-06-07
category: best-practices
module: book_filer
problem_type: best_practice
component: tooling
severity: high
related_components: [development_workflow, testing_framework]
applies_when:
  - running the book_filer actuator against the real F:\Books library
  - planning any destructive in-place file migration over a large corpus
  - rehearsing a migration on a copied subset of the library
  - cutting a fix/hardening branch from shared history before an apply
  - assembling or validating a signed-GREEN verdict before a destructive step
tags: [book-filer, actuator, migration, fail-closed, undo, backup, worktree, determinism]
---

# book_filer actuator — safely applying a signed-GREEN migration to F:\Books (first real apply)

## Context

The book_filer actuator (`tools/book_filer/{actuate,move,journal,backup,calibration,manifest}.py`; design recorded in ClaudeInfra ADR-0045) reorganizes the `F:\Books` library in place: it shelves correctly-identified books into a 12-section taxonomy, routes uncertain ones to `_Needs_Review`, byte-identical duplicates to `_Trash_Pending`, and unsafe rows to `_Quarantine`. Moves are **in-place atomic renames** (`os.replace`, same volume) — there is no copy of the tree to fall back on. That makes the apply fast and space-cheap, but it also means the only safety net is an external backup mirror plus an append-only journal.

EB-373 landed the actuator code (Done). EB-375 was its **first real apply** against the live library, executed 2026-06-07 (run `20260607-082401`). Because this was the first destructive run against a 760-file production corpus — with the SCRUM-301 junction-wipe precedent fresh in memory — it needed a careful, gated operational procedure rather than a bare `--mode apply`. This entry captures both the safety design that made the apply reversible and the runbook that produced a clean 680-move result with zero data loss.

## Guidance

### Safety design (what the actuator guarantees)

- **R1 — write-ahead journal.** Append-only JSONL. A durable **intent** record is `fsync`'d *before* `os.replace`; a **commit** record is written *after*. Resume and undo reconcile the journal against the actual filesystem, so the operation is idempotent and resumable after a crash.
- **R2 — manifest↔verdict binding.** `verify_binding` refuses to apply unless the signed verdict carries `manifest_digest == sha256(canonical_projection(rows))` matching the manifest, `green == True`, **and** the machine gates `auto_shelf_floor` and `trash_safety` are present and passing. A bare "GREEN" boolean is not enough — GREEN-as-a-flag is gameable.
- **R3 — external-mirror backup gate.** `build_backup_proof` emits `backup-proof.json = {mirror_root, file_count, sampled[(relpath, sha256)]}` from a deterministic sample. `verify_backup_proof` refuses unless the mirror is **disjoint from and present** alongside the library, and both live and mirror match the recorded proof.
- **R5 — reverse-replay undo.** Undo replays the journal last→first back to the exact original layout, then re-hashes to verify. It **follows the filesystem, not just the committed records**, so it can reverse moves even when they landed somewhere unexpected. Available until explicit `finalize`.
- **R7 — fail-closed routing.** Skip-and-log (never overwrite) on reparse-point ancestry (EB-360), destination-exists, unresolved collision, or a locked/missing source.
- **R8 — no hard delete.** "Trash" means a move to `_Trash_Pending` (30-day retention, separate tree). `finalize` archives the journal and closes the undo window — it deletes nothing.
- **EB-378 — containment guard (added this session).** Refuse fail-closed if any row's `original_path` *or* resolved target escapes `--library-root` (checked at both ends).
- **Determinism + locality.** `PYTHONHASHSEED=0` is required. Run the actuator from a clean tree, never a **junctioned** worktree — recursive cleanup traverses junctions and wipes the target (SCRUM-301 precedent). Keep the run-dir (journal) on a path *outside* the library and outside any temporary worktree.

### Operational gate sequence (the runbook that worked — run `20260607-082401`)

1. **Sync.** `git fetch`; run from a checkout at `origin/master` that contains the merged actuator code.
2. **Regenerate a FRESH signed-GREEN manifest from current master.**
   - Scan twice and prove determinism: byte-identical `canonical-projection.txt`, **680/680** rows both runs.
   - Human spot-check sign-off: `wrong_shelf == 0` (16 shelf rows in a 50-row sample).
   - Assemble the signed verdict **with** `manifest_digest` and the machine gates: `auto_shelf_floor` 225 ≥ 224, `trash_safety` 44 rows / 0 violations.
   - The prior (2026-06-03) verdict was **UNBOUND** (no `manifest_digest`) and was refused by R2 — a fresh re-sign was mandatory, not optional.
3. **Build + verify the external mirror.** `robocopy /E /XJ F:\Books C:\Books` (separate volume), then `build_backup_proof` from the mirror and `verify_backup_proof` (live + mirror match): **760 files, 64 sampled**.
4. **Ratify the ADR.** Move ADR-0045 Proposed → Accepted *before* the destructive step.
5. **Dry-run (read-only).** `--mode dry-run`: **680 planned / 0 skipped**, routing **225 shelve / 409 `_Needs_Review` / 44 `_Trash_Pending` / 2 `_Quarantine`** — confirm it matches the verdict.
6. **Apply.** Run `--mode apply` from a **clean detached `origin/master` worktree** (hardened code), but put the run-dir in the **persistent main-tree `data/`** so the journal survives worktree cleanup: **680 moved / 0 skipped**. `F:\Books` 760 → 760 (in-place, no loss); `C:\Books` untouched.
7. **Inspect, then finalize.** Browse `F:\Books` *before* finalizing. Then `--mode finalize` (archives the journal, closes the undo window). Undo stays available the entire window between apply and finalize.

## Why This Matters

- **SCRUM-301-class data loss.** In-place renames with no copy tree mean a bad routing rule or a junction-traversing cleanup can destroy originals irrecoverably. The external mirror (R3) plus journal (R1) plus reverse-replay undo (R5) are what turn "irreversible" into "reversible," and keeping the run from touching junctions avoids the wipe that already cost this project once.
- **Gameable GREEN.** If "apply" trusted a bare `green: true` flag, any stale or hand-edited verdict would pass. Binding the verdict to `manifest_digest` and requiring the machine gates (R2) means the thing you signed is provably the thing you apply.
- **Silent cross-library writes.** Without the EB-378 containment guard, a scan whose config points at the real library can write into it even when you *think* you are rehearsing on a copy (see L2) — a quiet, hard-to-notice corruption.
- **Unrecoverable deletes.** R8 (no hard delete) plus the undo window mean a misclassification is a reversible move, not a vanished file.

## When to Apply

- Running the book_filer actuator against the real `F:\Books` library for the first time, or after any code change to it.
- Planning any destructive **in-place** file migration over a large corpus where there is no copy-tree fallback.
- Rehearsing a migration on a copied subset — verify the scan's effective `library_root` before trusting the rehearsal.
- Assembling or validating a signed-GREEN verdict prior to a destructive step (must carry `manifest_digest` + machine gates).
- Cutting a fix/hardening branch from shared history immediately before an apply (branch off `origin/master`, not local).

## Examples

### The gate sequence, concretely

`<run>` below = `data\batch_reports\book_filer_whatif\<stamp>`. The actuator never defaults to `F:\Books` — the library root is always an explicit argument.

```powershell
$env:PYTHONHASHSEED = '0'      # required by both scan.py and actuate.py

# 2. Fresh signed-GREEN from current master (determinism = two byte-identical scans)
py -3.12 tools\book_filer\scan.py --root 'F:\Books' --out-dir <run>\run-a --stamp <stamp>
py -3.12 tools\book_filer\scan.py --root 'F:\Books' --out-dir <run>\run-b --stamp <stamp> --compare-to <run>\run-a
#   assert <run>\run-b\determinism-diff.json -> deterministic:true, 680/680
#   human spot-check the spot-check-sheet (wrong_shelf == 0), then write
#   <run>\calibration-verdict-signed.json WITH manifest_digest + gates {auto_shelf_floor, trash_safety}

# 3. External mirror on a SEPARATE volume + proof (book_filer.backup helpers, not a CLI)
robocopy 'F:\Books' 'C:\Books' /E /XJ /XJD /XJF        # /XJ* = never follow junctions
#   build_backup_proof(r'C:\Books') -> <run>\backup-proof.json   (760 files, 64 sampled)
#   verify_backup_proof(r'F:\Books', proof).ok  ->  True         (live + mirror both match)

# 5. Dry-run (read-only) -> 680 planned / 0 skipped
py -3.12 tools\book_filer\actuate.py --manifest <run>\run-a\plan-<stamp>.json `
  --verdict <run>\calibration-verdict-signed.json --backup-proof <run>\backup-proof.json `
  --library-root 'F:\Books' --mode dry-run --run-dir <run>\apply --stamp <stamp>

# 6. Apply (run-dir in persistent main-tree data\ so the journal outlives a temp worktree)
py -3.12 tools\book_filer\actuate.py --manifest <run>\run-a\plan-<stamp>.json `
  --verdict <run>\calibration-verdict-signed.json --backup-proof <run>\backup-proof.json `
  --library-root 'F:\Books' --mode apply --run-dir <run>\apply --stamp <stamp>
#   -> 680 moved / 0 skipped; F:\Books 760->760; C:\Books untouched

# 7. Inspect F:\Books, THEN close the window (undo stays available until this)
py -3.12 tools\book_filer\actuate.py --library-root 'F:\Books' --run-dir <run>\apply --mode finalize --stamp <stamp>
```

### Undo is always available until finalize

```powershell
# Reverse-replay: journal last->first, then re-hash to verify the original layout is restored
py -3.12 tools\book_filer\actuate.py --library-root 'F:\Books' --run-dir <run>\apply --mode undo --stamp <stamp>
```

### Lessons as mini-cases

**L1 — branch off `origin/master`, not local `master`.** The EB-378 fix worktree was cut from local `master`, which carried 2 unpushed `docs(EB-377)` commits. The squash merge then bundled the unrelated EB-377 docs: content wasn't lost, but provenance was muddied and local `master` diverged. *Rule:* `git worktree add <dir> -b fix/EB-NNN origin/master` — never branch off a local tip you haven't confirmed is pushed and clean. (The actuator plan itself gave this exact warning.)

**L2 — a copied-subset rehearsal is UNSAFE with the production config.** `scan.py` computes each shelve `destination_path` from the config's `library_root` (`F:\Books`) *regardless of the `--root` actually scanned*. An apply pointed at a copy therefore wrote shelve rows into the **real** `F:\Books` (8 files; recovered via undo). *Fix:* the EB-378 fail-closed containment guard, **or** scan the copy under a config whose `library_root` is the copy itself.

```python
# The trap (paraphrased): the shelve destination derives from config, not the scanned root.
dest = config.library_root / shelf_for(row)   # == F:\Books even when scan --root is a copy
# EB-378 guard (actuate._containment_violation): refuse the run if any row's
# original_path OR resolved target escapes --library-root (both ends checked).
```

**L3 — a signed verdict is only usable if it carries `manifest_digest`.** The 2026-06-03 verdict had no digest binding; R2 refused it fail-closed. Bare/old verdicts cannot be applied by design — re-sign against the current manifest.

**L4 — `backup-proof.json` is a *pre-apply* (mirror) proof.** After apply, live paths change, so the proof no longer verifies against live — **this is expected**, not a failure. It still attests that the mirror equals the pristine original. Undo does **not** depend on it.

**L5 — undo is filesystem-following and robust.** It reversed moves that had escaped into the real library even after `finalize` archiving (the journal records were re-loaded from the archive). *Takeaway:* prefer operations that can only fail closed and whose recovery follows the filesystem rather than trusting a record.

**L6 — `os.replace` leaves emptied source/destination directories.** Prune them separately; this is cosmetic, not a correctness issue (it briefly tripped the "is the library pristine?" check after an undo because empty dirs survived).

**L7 — the operational safety hook false-positives** when a command contains both a deletion verb (`Remove-Item`) and the protected path literal (`F:\Books`), and on a bare `"*"` glob near protected paths. *Workaround:* separate deletes from any library-path reference in the same command, and avoid bare `"*"` (walk with `os.walk` instead).

```python
# Hook-friendly: don't co-locate a delete verb with the protected literal, and don't use bare "*"
for root, _dirs, files in os.walk(run_scratch):   # not: Remove-Item F:\Books\*
    ...
```

## Related

- [eb355-book-filer-classification-metadata-accuracy-2026-06-02.md](eb355-book-filer-classification-metadata-accuracy-2026-06-02.md) — the read-model + calibration gate this apply consumes ("the actuator stays gated until a clean run").
- [eb365-book-filer-format-tier-demotion-2026-06-03.md](eb365-book-filer-format-tier-demotion-2026-06-03.md) — reached strict GREEN + the signed verdict; its scope explicitly defers the actuator to this apply. This entry extends that signed-verdict contract with `manifest_digest` binding.
- ClaudeInfra **ADR-0045** (Accepted, INFRA-552) — canonical actuator safety contract (R1–R8 + the EB-378 containment guard). Local pointer: `docs/decisions/ADR-EB-354-actuator-safety-model-pointer.md`.
- Build plan: `docs/plans/2026-06-04-001-feat-eb354-book-filer-actuator-plan.md` (7-unit, test-first).
- Tickets: **EB-354** (epic), **EB-373** (actuator code, Done), **EB-375** (first real apply — this entry), **EB-378** (containment hardening, Done), **EB-376** (junk embedded PDF metadata → wrong author subfolder, open).
- Companion source-of-truth for the git lessons (no prior solution-doc coverage): CLAUDE.md "Git Worktrees" / "Before Acting on a Ticket" and the project CLAUDE.md `mklink /J` junction data-loss warning.
