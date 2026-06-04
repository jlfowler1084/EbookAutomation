---
title: "feat(EB-354): book_filer actuator — in-place file-mover for the signed-GREEN manifest"
type: feat
status: active
date: 2026-06-04
origin: docs/brainstorms/2026-06-04-eb354-book-filer-actuator-requirements.md
---

# feat(EB-354): book_filer actuator — in-place file-mover

## Overview

Build the **actuator**: the write-model that executes a strict-GREEN `-WhatIf` manifest against
`F:\Books` as **in-place atomic-rename moves**, fully reversible until an explicit `finalize`, behind
a verified external backup and a manifest↔signed-GREEN binding. The read-model (`scan.py` brain) is
unchanged; the manifest is the frozen, signed boundary between them. No hard deletes; fail-closed on
any ambiguity.

## Problem Frame

`book_filer` computes a deterministic, signed-GREEN manifest of where every file in `F:\Books` should
live (EB-355 + EB-365), but nothing executes it — `scan.py` is read-only by construction and its undo
artifact is inert-by-design. The actuator is the missing, deliberately-gated destructive step. Because
the chosen apply model is **in-place move** (see origin §3, D1), the backup + journal are the entire
safety net, so the design is dominated by reversibility, idempotency, and fail-closed safety.

## Requirements Trace

Carried from origin (`docs/brainstorms/2026-06-04-eb354-book-filer-actuator-requirements.md` §4):

- **R1 — Modes.** `dry-run` (default; plan + journal-preview, zero mutation) and `apply` (execute). Apply never default.
- **R2 — Manifest binding.** Apply only a manifest carrying a **fresh signed GREEN** verdict matched by digest/stamp; refuse otherwise.
- **R3 — Backup gate.** Verify external-mirror proof (count + sample sha256) vs live corpus before any move; refuse on mismatch.
- **R4 — In-place moves.** Move source → `destination_path` (shelve) or to the operational folder (`_Needs_Review`/`_Trash_Pending`/`_Quarantine`); same-volume atomic rename; create dest dirs.
- **R5 — Executable undo.** Append a journal record as each move commits; `undo` reverse-replays to exact original layout; `finalize` ends the window.
- **R6 — Idempotent/resumable.** Re-run resumes from the journal; already-applied rows skipped; crash leaves a consistent, resumable state.
- **R7 — Fail-closed.** Skip + log (never overwrite/guess) on reparse point (EB-360), dest-exists, unresolved collision, locked/missing/unreadable source.
- **R8 — No hard delete.** `trash` → `_Trash_Pending` (retention); the actuator never deletes.
- **R9 — Read-only safety.** `dry-run`, undo-preview, and verification never mutate `F:\Books`.

Plus origin §5 staged rollout and origin §7 success criteria.

## Scope Boundaries

- No classification/scoring changes — the actuator only executes a frozen, signed manifest.
- No review-rate reduction (EB-366) — the 409 `_Needs_Review` files are hand-sorted later.
- No Calibre import / Hermes auto-filing — separate EB-354 work.
- No `_Trash_Pending` retention sweep / deletion — out of scope (separate/existing).

### Deferred to Separate Tasks

- **ADR-0043** (actuator safety-model decision record) — authored in the **ClaudeInfra** repo, ADR-00NN series, as a sibling task; this plan references it as the gating rationale, but the ADR file is not created in this repo.
- **First real full apply against `F:\Books`** — a gated operational event (backup + approval + fresh signed GREEN), not a code deliverable of this plan.

## Context & Research

### Build off `origin/master`, run from the main tree

- **Branch off `origin/master` (currently `a6b24a9`), not the local working-tree `master` (`7ae1a84`, ~25 commits behind).** Verified: `origin/master` contains EB-359 (`fragments.by_dir_stem`, folder-aware) and EB-360 (`reparse` fails closed: `except OSError: return True`). The local main tree is stale and still shows the pre-fix code.
- **Run the actuator from the main working tree, never a junctioned worktree** (CLAUDE.md SCRUM-301: `Remove-Item -Recurse` traverses junctions and deletes the *target*). Tests use synthetic `tmp_path` trees only — never `F:\Books`.

### Relevant Code and Patterns

- `tools/book_filer/manifest.py` — `ManifestRow` (plain dataclass; `original_path`=move source [resolved], `destination_path`=target [`""` for review/quarantine], `action`, `sha256`, `duplicate_group_id`, `canonical_reason`, `planned_calibre_key`, `taxonomy_version`, inert `undo_action`). `canonical_projection(rows)` — the **deterministic anchor string** (drops `_VOLATILE={calibre_id}`, sorts by `original_path`, `json.dumps(sort_keys=True)`); hash this to bind a verdict to a manifest. `generate_undo_script` already iterates `reversed(rows)` — the reverse-replay ordering convention to mirror. `_atomic_write_text/_bytes` (tmp→`os.replace`).
- `tools/book_filer/scan.py` — `_resolve_action` action vocabulary → operational-folder mapping: `copy`/`hardlink`→shelve `destination_path`; `review`→`_Needs_Review`; `trash`→`_Trash_Pending`; `quarantine`→`_Quarantine`. `_spot_disposition` maps copy/hardlink→`shelf`, else→`review`. `_assert_output_outside_scan` (G1), `PYTHONHASHSEED=0` guard, `_hash_file`, `_iter_book_files` (junction-safe DFS), `_COMPLETE` sentinel written last, `argparse` shape. **`unique_path` is deliberately never called in dry-run** — collision resolution at apply time is the actuator's job.
- `tools/book_filer/calibration.py` — `CalibrationVerdict(deterministic, wrong_shelf_count, spot_check_size, signed_off_by, green, reason)`; **no manifest-binding field exists yet** (must add). The signed verdict at `data/batch_reports/book_filer_whatif/20260603-184428/run-b/calibration-verdict-signed.json` already records the extra machine gates (floor, trash-safety) the actuator should assert.
- `tools/book_filer/reparse.py` — `has_reparse_in_ancestry(path) -> bool` (fail-closed post-EB-360): call on **both source and destination ancestry** before every move; `True` = unsafe → skip/quarantine.
- `tools/book_filer/fragments.py` — `detect_fragment_sets` (folder-aware post-EB-359); fragments are always `review`, never moved/trashed.
- `tools/book_filer/pathsafe.py` — reuse `unique_path(dest)` (collision → `dest (2)`…), `compute_shelf_path`, `sanitize_component`. Over-length is open-coded in `_resolve_action` (`len(dest) > max_path_length` → quarantine); the manifest already encodes that as a `quarantine` action.
- `tools/book_filer/config.py` — `LibraryConfig`: `library_root=F:\Books`, `operational_folders` (incl. `_Needs_Review`/`_Trash_Pending`/`_Quarantine`/`_Duplicates_Pending`), `trash_retention_days=30`, `max_path_length=240`, `materialize_mode`.

### Institutional Learnings

- `docs/solutions/eb365-book-filer-format-tier-demotion-2026-06-03.md` — the actuator's gate is verbatim: **strict-GREEN signed verdict + external backup + approval + ADR-0043**. `evaluate_calibration()` does not encode floor/trash-safety; the **signed** artifact does — the actuator must assert those fields, not trust a bare verdict. Monotonic safety: prefer operations that can only fail *closed*.
- `docs/solutions/eb355-book-filer-classification-metadata-accuracy-2026-06-02.md` — "GREEN is gameable"; consume the signed verdict, don't re-derive GREEN. Collision/dest-exists checks must key off the same sanitized author/year/`planned_calibre_key` the manifest used.
- `docs/solutions/eb353-vqa-grader-code-false-positive-2026-06-02.md` — determinism-as-prerequisite: re-derive the projection at apply time and confirm byte-identity to the approved manifest before the first move; lock fail-closed branches with deterministic contract tests so they can't be silently removed.
- `docs/decisions/ADR-EB-181-data-exemption-scope.md` — `data/batch_reports/**` is worktree-exempt: the move journal + run reports land there and may be committed directly. Any actuator artifact that becomes a **regression-gate input** is NOT exempt → must ride a PR.
- `docs/superpowers/plans/2026-06-01-eb355-plan4-migration-core.md` — un-compounded source of the ManifestRow / dedup / trash-safety invariants; read before implementing.

### External References

- None — local Python CLI with strong in-repo patterns; no external contract surface.

## Key Technical Decisions

- **Apply model = in-place move (D1).** `os.replace`/atomic rename within `F:\Books` (same volume). No copy tree.
- **Manifest↔verdict binding (R2).** Add `manifest_digest: str | None` (and `stamp`) to `CalibrationVerdict` / the signed sidecar = `sha256(canonical_projection(rows))`. Actuator re-derives the digest from the manifest it is about to apply and refuses unless a signed verdict records that digest, `green==True`, and the floor + trash-safety fields are present. Determinism gate re-checked at apply time (EB-353).
- **Journal = append-only JSONL (net-new).** One record per committed move (`seq`, `src`, `dst`, `action`, `sha256`, `ts`), `fsync`'d, written **before** the next move begins, via append (crash-safe: a torn final line is detected and ignored on resume). Reverse-replay (last→first) mirrors `generate_undo_script`.
- **Collision resolution at apply time.** Call `pathsafe.unique_path(dest)` only in `apply` (never dry-run); a destination that already exists and is NOT the expected source → **fail closed** (skip + log), do not overwrite.
- **Operational-folder routing.** Derive target from `action`: shelve→`destination_path`; `review`→`_Needs_Review/<original-relative>`; `trash`→`_Trash_Pending`; `quarantine`→`_Quarantine`. Reconcile the brainstorm naming with config (`_Duplicates_Pending` exists; confirm whether dedup-`trash` routes to `_Trash_Pending` or `_Duplicates_Pending`).
- **Idempotency key.** A row is "already applied" iff source absent AND destination present with matching `sha256`; such rows are skipped on resume (R6).
- **Single-run lock.** A lock file under the run dir; refuse concurrent apply/undo.
- **Artifacts under `data/batch_reports/book_filer_whatif/<stamp>/apply/`** (ADR-EB-181 exempt): `journal.jsonl`, `apply-report.md`, `backup-proof.json`.

## Open Questions

### Resolved During Planning

- Where is the determinism anchor? → `manifest.canonical_projection(rows)`; hash binds verdict↔manifest.
- Who resolves collisions? → the actuator (`unique_path` at apply time); `scan.py` never does.
- Where do artifacts live? → `data/batch_reports/...` (worktree-exempt), unless they become a gate input.
- Are EB-359/EB-360 present? → yes on `origin/master` (`a6b24a9`); build there, not stale local master.

### Deferred to Implementation

- Exact journal record schema/field names and the torn-line detection mechanism (resolve when writing the journal engine).
- Whether dedup-`trash` routes to `_Trash_Pending` vs `_Duplicates_Pending` — confirm against the Plan-4 migration-core contract while touching routing.
- `finalize` semantics: journal purge only vs. also emit a closing audit record.
- Subset-selection mechanism for the copied-library rehearsal (which slice, how built).
- Lock-file location/format and stale-lock handling.

## Output Structure

    tools/book_filer/
      actuate.py            # apply/undo/finalize driver + CLI (new)
      journal.py            # append-only JSONL journal: write/read/replay (new)
      backup.py             # external-mirror proof verification (new)
      move.py               # fail-closed single-file move primitive (new)
    tests/
      test_book_filer_actuate.py    # apply/undo/finalize integration (new)
      test_book_filer_journal.py    # journal crash-safety + resume (new)
      test_book_filer_backup.py     # backup-proof verification (new)
      test_book_filer_move.py       # fail-closed move primitive (new)
    data/batch_reports/book_filer_whatif/<stamp>/apply/   # runtime artifacts (journal.jsonl, apply-report.md, backup-proof.json)

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

Per-row apply decision (the fail-closed move primitive, R4/R7):

| Condition on a row | Outcome |
|---|---|
| reparse point in source OR destination ancestry (`has_reparse_in_ancestry`) | **skip + log** (never move through a junction) |
| source missing AND destination present w/ matching sha | **skip** (already applied — idempotent resume) |
| source missing AND no matching destination | **skip + log** (anomaly; do not guess) |
| source locked/unreadable | **skip + log** |
| destination exists and is not the expected source | `unique_path()` if policy allows, else **skip + log**; never overwrite |
| all clear | create dest dirs → `os.replace(src, dst)` → **append journal record (fsync) before next row** |

Apply orchestration: verify lock → verify manifest↔signed-GREEN binding (R2) → re-derive + confirm determinism (EB-353) → verify backup proof (R3) → for each row (manifest order) route by `action` and run the move primitive → write `apply-report.md`. Undo: read `journal.jsonl`, reverse-replay `dst→src` through the same fail-closed primitive, verify restored layout by re-hash. Finalize: end the undo window (purge/close journal); never deletes.

## Implementation Units

- [ ] **Unit 1: Manifest↔signed-GREEN binding**

**Goal:** A manifest can be cryptographically bound to a signed GREEN verdict, and the actuator can verify that binding.

**Requirements:** R2

**Dependencies:** None

**Files:**
- Modify: `tools/book_filer/calibration.py` (add `manifest_digest`/`stamp` to `CalibrationVerdict`; helper to compute digest from a projection string)
- Modify: `tools/book_filer/manifest.py` (expose a `manifest_digest(rows)` = `sha256(canonical_projection(rows))` helper)
- Test: `tests/test_book_filer_calibration.py` (extend)

**Approach:**
- `manifest_digest(rows)` hashes the existing `canonical_projection(rows)`. The signed verdict records the digest; `verify_binding(manifest_rows, verdict)` returns True only if digest matches, `green is True`, and the floor + trash-safety fields are present (assert, don't trust a bare verdict).
- Back-compat: `manifest_digest` defaults `None`; an unbound verdict fails verification (fail-closed).

**Execution note:** Test-first.

**Patterns to follow:** `canonical_projection`, `evaluate_calibration` shape.

**Test scenarios:**
- Happy path: a verdict whose `manifest_digest` matches the rows + `green=True` + floor/trash-safety present → verify passes.
- Edge: identical rows in any order → identical digest (built on the already-sorted projection).
- Error: digest mismatch → fails. Missing floor/trash-safety field → fails. `green=False` → fails. `manifest_digest=None` → fails.

**Verification:** binding verification passes only for a matching, fully-gated signed verdict.

- [ ] **Unit 2: External-mirror backup-proof verification**

**Goal:** Refuse to apply unless a verified external backup of the live corpus exists.

**Requirements:** R3

**Dependencies:** None

**Files:**
- Create: `tools/book_filer/backup.py`
- Test: `tests/test_book_filer_backup.py`

**Approach:**
- A `backup-proof.json` records the mirror root, file count, and a deterministic sample of `(relpath, sha256)`. `verify_backup_proof(live_root, proof)` recomputes count + the same sample against `live_root` and returns pass/fail with the mismatch reason. Sampling is deterministic (sorted, fixed stride) so re-runs agree. Fail-closed: any missing sample file, count drift, or sha mismatch → fail.

**Execution note:** Test-first; synthetic `tmp_path` "live" + "mirror" trees.

**Patterns to follow:** `_hash_file`; deterministic stratified sampling in `scan._build_spot_check`.

**Test scenarios:**
- Happy path: mirror identical to live (count + all sampled sha match) → pass.
- Edge: large corpus → only sampled files hashed; deterministic across two calls.
- Error: mirror missing a sampled file → fail; count drift → fail; one sampled sha differs → fail (names the file).

**Verification:** verification passes only for a count-and-sample-matching mirror.

- [ ] **Unit 3: Fail-closed single-file move primitive**

**Goal:** Move one file safely, or refuse — never overwrite, never traverse a reparse point.

**Requirements:** R4, R7

**Dependencies:** None (composes EB-360 reparse, EB-359 fragments policy, pathsafe)

**Files:**
- Create: `tools/book_filer/move.py`
- Test: `tests/test_book_filer_move.py`

**Approach:**
- `plan_move(src, dst, *, allow_unique=True)` → a decision (`move`/`skip`, with reason) following the decision matrix above: `has_reparse_in_ancestry` on src+dst ancestry; dest-exists handling via `unique_path` or skip; locked/missing source. `execute_move(decision)` creates dest dirs and `os.replace`. Pure decision is separated from the side effect so dry-run reuses `plan_move`.

**Execution note:** Test-first; junction tests use the `mklink /J` + `os.rmdir(link)`-in-`finally` teardown pattern (never delete the target).

**Patterns to follow:** `reparse.has_reparse_in_ancestry`, `pathsafe.unique_path`, `tests/test_book_filer_scan.py` junction create/teardown.

**Test scenarios:**
- Happy path: clean src→dst on the same volume → file at dst, gone from src; dirs created.
- Edge: dest exists (different content) → `unique_path` dst when allowed; → **skip** when not; original never overwritten.
- Error/fail-closed: reparse point in src ancestry → skip+reason; reparse in dst ancestry → skip; dangling junction in path → skip (EB-360); locked/missing source → skip+reason.
- Integration: a real NTFS junction inside the tmp tree is never traversed; target contents unchanged after the test (snapshot).

**Verification:** every unsafe condition yields skip+reason; only clean rows move; no overwrite ever.

- [ ] **Unit 4: Append-only JSONL journal + idempotent resume**

**Goal:** Every committed move is durably recorded; a re-run resumes without double-moving.

**Requirements:** R5 (record), R6

**Dependencies:** Unit 3

**Files:**
- Create: `tools/book_filer/journal.py`
- Test: `tests/test_book_filer_journal.py`

**Approach:**
- `append(record)` writes one JSON line and `fsync`s before returning (so the move that follows is always preceded by a durable record). `read(path)` parses records and **ignores a torn final line** (crash mid-write). `already_applied(row)` = source absent AND dest present w/ matching sha. Resume filters the manifest against the journal + idempotency key.

**Execution note:** Test-first; simulate a torn final line by truncating the file.

**Patterns to follow:** `_atomic_write_*` (for non-append artifacts); reverse-replay order from `generate_undo_script`.

**Test scenarios:**
- Happy path: append N records → `read` returns N in order.
- Edge: truncated/torn final line → `read` returns N-1, no raise.
- Idempotency: a row whose dst exists w/ matching sha and src is gone → `already_applied` True → skipped on resume.
- Integration: apply 3 rows, "crash" after 2 (journal has 2), resume → only the 3rd moves; no double-move.

**Verification:** journal survives torn writes; resume never re-moves an applied row.

- [ ] **Unit 5: Apply driver + CLI (dry-run/apply, routing, artifacts)**

**Goal:** Orchestrate a full-manifest apply (or dry-run) with all gates, routing, and reports.

**Requirements:** R1, R2, R3, R4, R6, R8, R9

**Dependencies:** Units 1–4

**Files:**
- Create: `tools/book_filer/actuate.py` (driver + `argparse`)
- Test: `tests/test_book_filer_actuate.py`

**Approach:**
- CLI: `--manifest <plan-*.json>`, `--verdict <signed-verdict.json>`, `--backup-proof <json>`, `--mode dry-run|apply` (default dry-run), `--run-dir`, `--lock`. Order: acquire lock → `verify_binding` (R2) → re-derive projection + confirm determinism (EB-353) → `verify_backup_proof` (R3) → resume-filter (Unit 4) → per row, route by `action` to a target path and run the move primitive (Unit 3), appending the journal (Unit 4) → write `apply-report.md`. Dry-run runs `plan_move` only (no side effects, R9) and writes a journal-preview. `PYTHONHASHSEED=0` guard mirrored from `scan.py`. `trash`→`_Trash_Pending`, never delete (R8).

**Execution note:** Test-first; subprocess `run_apply` harness mirroring `run_scan`; synthetic library under `tmp_path`.

**Patterns to follow:** `scan.main` argparse + `PYTHONHASHSEED` guard + exit codes; `run_scan` subprocess harness; `_snapshot` immutability assertions.

**Test scenarios:**
- Happy path (apply): a 4-row synthetic manifest (shelve/review/trash/quarantine) → each file lands in the right target; journal has 4 records; `apply-report.md` summarizes.
- R1/R9: dry-run mutates nothing (`_snapshot` before==after); emits a journal-preview.
- R2: missing/mismatched verdict binding → refuse (non-zero exit), no moves.
- R3: backup-proof fails → refuse, no moves.
- R8: a `trash` row goes to `_Trash_Pending`; nothing is deleted.
- Edge: `PYTHONHASHSEED!=0` → refuse (mirror scan guard).
- Integration: interrupt after 2 of 4 (kill), re-run → completes the remaining 2 only.

**Verification:** apply realizes the manifest's target layout with every gate enforced; dry-run is inert.

- [ ] **Unit 6: Undo reverse-replay + finalize**

**Goal:** Restore the exact original layout from the journal, until an explicit finalize.

**Requirements:** R5, R8

**Dependencies:** Units 3–5

**Files:**
- Modify: `tools/book_filer/actuate.py` (`undo`, `finalize` subcommands)
- Test: `tests/test_book_filer_actuate.py` (extend)

**Approach:**
- `undo`: read `journal.jsonl`, reverse-replay each record `dst→src` through the same fail-closed move primitive, verify the restored layout by re-hash against the journal's recorded `sha256`. `finalize`: end the undo window (purge/close the journal; optional closing audit record). Neither deletes anything (`_Trash_Pending` retention is separate).

**Execution note:** Test-first.

**Test scenarios:**
- Happy path: apply then undo → working tree byte-identical to the pre-apply snapshot (re-hash match).
- Edge: undo when a `dst` was independently moved/removed → skip+log that record, continue; report incompleteness (fail-closed, no guess).
- R8: finalize purges the journal but deletes no files; `_Trash_Pending` contents untouched.
- Integration: apply → undo → re-apply → undo (round-trips) all consistent.

**Verification:** undo restores the original layout exactly; finalize closes the window without deletion.

- [ ] **Unit 7: Staged-rollout integration + safety regressions**

**Goal:** Prove the dry-run → subset-on-a-copy → (gated) full-apply path and lock the safety invariants.

**Requirements:** R6, R7, R9 + origin §5/§7

**Dependencies:** Units 1–6

**Files:**
- Test: `tests/test_book_filer_actuate.py` (extend), `tests/test_book_filer_move.py` (extend)
- Modify: `feature-manifest.json` (only if new exported symbols/config keys are catalogued surfaces)

**Approach:**
- End-to-end on a synthetic copied-library slice: dry-run (inert) → apply → verify layout → undo → verify restore → re-apply → finalize. Deterministic contract tests pin each fail-closed branch and the no-hard-delete invariant so they can't be silently removed (EB-353).

**Execution note:** Test-first; junction safety via the `os.rmdir(link)` teardown pattern; `_snapshot` immutability.

**Test scenarios:**
- Integration: full dry-run→apply→undo→re-apply→finalize round-trip on a multi-folder synthetic library.
- Safety contract: explicit tests asserting (a) no `Remove-Item`/`unlink` path exists in apply/undo, (b) every fail-closed branch routes to skip+log, (c) reparse/junction never traversed.
- Determinism: re-deriving the projection at apply time is byte-identical to the approved manifest; drift → refuse.

**Verification:** the staged path works end-to-end; safety invariants are test-locked; manifest verification (if touched) passes.

## System-Wide Impact

- **Interaction graph:** new write-model alongside the read-model; the only shared surface is the manifest + `canonical_projection` (Unit 1 reads it) and the safety primitives (reparse/fragments/pathsafe). `scan.py` is unchanged.
- **Error propagation:** every per-row failure is fail-closed (skip + journal/report), never an overwrite or partial-destroy; the driver aggregates skips into `apply-report.md`.
- **State lifecycle risks:** crash mid-apply → journal + idempotency key make resume safe; torn journal line tolerated; lock file prevents concurrent runs.
- **API surface parity:** `CalibrationVerdict` gains an optional `manifest_digest` (defaulted) — existing call sites and the existing signed verdict remain valid; an unbound verdict simply fails the new binding check.
- **Integration coverage:** apply/undo/resume and junction-safety are only provable by integration tests on synthetic trees, not unit mocks.
- **Unchanged invariants:** the read-only brain, determinism projection, dedup/trash-safety planning, and `scan.py` artifacts are untouched; the actuator only consumes their output.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| In-place move corrupts/loses data on crash | Atomic `os.replace`; journal `fsync` before next move; idempotent resume; verified external mirror gate (R3); undo reverse-replay. |
| Stale local `master` used → builds on pre-fix reparse/fragments | Plan mandates branching off `origin/master` (`a6b24a9`); verified both fixes present. |
| Junction traversal deletes target (SCRUM-301) | Run from main tree only; fail-closed reparse check on src+dst; junction tests use `os.rmdir(link)` teardown. |
| Applying an unverified/altered manifest | R2 binding: digest must match a signed, fully-gated GREEN verdict; determinism re-checked at apply time. |
| Net-new journal/undo engine has no prior art | Treated as primary design risk; deterministic contract tests lock crash-safety, idempotency, and reverse-replay. |
| Operational-folder naming mismatch (`_Trash_Pending` vs `_Duplicates_Pending`) | Reconcile against Plan-4 migration-core contract while implementing routing (deferred question). |

## Documentation / Operational Notes

- **ADR-0043** (ClaudeInfra ADR-00NN) records the four decisions + rationale (in-place + backup + journal-undo + finalize as one coherent safety story); author as a sibling task before the first real apply.
- On a successful first real apply, compound a `docs/solutions/` entry (the actuator's crash-safety + idempotency design).
- The **first real full apply** is a gated operational event: branch-current signed GREEN + verified external mirror + explicit approval; not part of this code plan.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-06-04-eb354-book-filer-actuator-requirements.md](../brainstorms/2026-06-04-eb354-book-filer-actuator-requirements.md)
- Related code: `tools/book_filer/{manifest,scan,calibration,reparse,fragments,pathsafe,config}.py`
- Compounds: `docs/solutions/eb365-book-filer-format-tier-demotion-2026-06-03.md`, `eb355-book-filer-classification-metadata-accuracy-2026-06-02.md`, `eb353-vqa-grader-code-false-positive-2026-06-02.md`
- Migration-core contract: `docs/superpowers/plans/2026-06-01-eb355-plan4-migration-core.md`
- Worktree/data exemption: `docs/decisions/ADR-EB-181-data-exemption-scope.md`
- Signed verdict exemplar: `data/batch_reports/book_filer_whatif/20260603-184428/run-b/calibration-verdict-signed.json`
- Jira: EB-354 (epic), new actuator Story (to create); EB-365 (gate, Done), EB-360/EB-359 (safety prereqs, merged)
