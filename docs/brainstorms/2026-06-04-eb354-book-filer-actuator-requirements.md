# EB-354 — book_filer Actuator (in-place file-mover): Requirements & Design

**Epic:** EB-354 (F:\Books library reorganization + Hermes auto-filing enforcement).
**Type:** new child Story (to be created). **Date:** 2026-06-04. **Status:** brainstorm → planning.
**Decision record:** ADR-0045 (ClaudeInfra, INFRA-552), authored from this doc. (Originally mis-cited as "ADR-0043"; that number is the unrelated Hermes Tiered Autonomy ADR / INFRA-491, so the actuator safety model took the next free slot, ADR-0045.)

---

## 1. Problem & goal

The `book_filer` read-only `-WhatIf` brain (EB-355) computes a deterministic, strict-GREEN manifest
of where every file in `F:\Books` should live. Nothing executes it. The **actuator** is the
destructive step that applies a signed-GREEN manifest to physically reorganize `F:\Books`.

**Goal:** execute a fresh signed-GREEN manifest as **in-place moves**, fully reversible until an
explicit finalize, behind a verified backup — with zero hard-deletes and fail-closed safety.

## 2. Prerequisites (met)

- **EB-360** — reparse ancestry check fails *closed* (junctions / >260-char paths). **Merged.**
- **EB-359** — fragment grouping is folder-aware at the primitive. **Merged.**
- EB-365 — classifier at strict GREEN (gates the actuator). **Done.**

## 3. Core decisions (resolved in brainstorm)

| # | Decision | Choice |
|---|----------|--------|
| D1 | **Apply model** | **In-place move** within `F:\Books` (same-volume atomic renames). No copy tree. |
| D2 | **Backup gate** | **External mirror** on a separate physical disk, verified by file **count + sample sha256** against a proof manifest. Actuator **refuses to apply** on mismatch. |
| D3 | **Apply scope** | **Full manifest in one apply**: shelve 225, stage 409 → `_Needs_Review`, 44 → `_Trash_Pending`, 2 → `_Quarantine`. |
| D4 | **Undo lifetime** | One-command **reverse-replay** to exact original layout, available **until explicit `finalize`** (which purges the journal and lets `_Trash_Pending` retention proceed). |

## 4. Behavioral contract (requirements)

- **R1 — Modes.** `dry-run` (default; plan the moves, write the journal-preview, touch nothing) and
  `apply` (execute). Apply is never the default.
- **R2 — Manifest binding.** Apply executes exactly one manifest, and only if that manifest carries a
  **fresh signed GREEN** calibration verdict matched by stamp/hash. A manifest without a matching
  signed verdict is refused.
- **R3 — Backup gate (D2).** Before any move, verify the external-mirror proof manifest
  (count + sample sha256) against the live corpus; refuse to apply on any mismatch.
- **R4 — In-place moves (D1).** Each row moves its source to `destination_path` (shelve) or to the
  appropriate operational folder (`_Needs_Review` / `_Trash_Pending` / `_Quarantine`). Same-volume
  atomic rename; create destination dirs as needed.
- **R5 — Executable undo (D4).** Append a journal record (`src`, `dst`, action, sha, timestamp) as
  **each move commits**. `undo` reverse-replays to the exact original layout. `finalize` purges the
  journal and ends the undo window.
- **R6 — Idempotent / resumable.** Re-running apply resumes from the journal: an already-applied row
  (source absent, destination present with matching sha) is skipped. Crash mid-run leaves a consistent,
  resumable state.
- **R7 — Fail-closed.** Skip + log (never overwrite, never guess) on: a reparse point in the path
  (EB-360), a destination that already exists, an unresolved collision, a locked/missing/unreadable
  source. A skipped row is reported, not silently dropped.
- **R8 — No hard delete.** `trash` rows move to `_Trash_Pending` (30-day retention); nothing is ever
  `Remove-Item`/`unlink`-ed by the actuator. Finalize does not delete — retention does, separately.
- **R9 — Read-only safety for non-applied state.** `dry-run`, `undo` preview, and verification never
  mutate `F:\Books`.

## 5. Staged rollout (acceptance path)

1. **Dry-run** on the current corpus → review the planned journal; zero mutations.
2. **Subset apply on a COPIED library** (a throwaway copy of a slice of `F:\Books`) → exercise
   apply + undo + resume end-to-end off the real data.
3. **Full apply** on `F:\Books` only after: explicit approval + verified external backup (R3) +
   a fresh signed GREEN (R2) regenerated from latest `master`.
4. **Inspect** the reorganized library; `undo` if wrong; `finalize` when satisfied.

## 6. Scope boundaries / non-goals

- **No** review-rate reduction (EB-366 deferred) — the 409 `_Needs_Review` files are hand-sorted later.
- **No** Calibre library import / Hermes auto-filing enforcement (separate EB-354 work).
- **No** deletion logic — retention sweep of `_Trash_Pending` is out of scope (existing/separate).
- **No** new classification behavior — the actuator only executes a frozen signed manifest.

## 7. Success criteria

- A full apply produces the manifest's exact target layout; every move is journaled.
- `undo` restores the byte-for-byte original layout (verified by re-hash) before finalize.
- A re-run after interruption completes with no double-moves and no overwrites.
- Zero hard-deletes; zero moves across a reparse point; zero destination overwrites.
- Refuses to apply without a matching signed-GREEN manifest and a verified backup proof.

## 8. Open questions (for planning)

- Journal format & location (append-only JSONL under `data/...`? must survive a crash mid-write).
- `finalize` semantics: purge journal only, or also emit a closing audit record?
- Subset-selection for the copied-library rehearsal (which slice, how built).
- Destination-collision policy at apply time vs. the planner's `_disambiguate_destinations`
  (should already be collision-free; apply must still fail-closed if not).
- Concurrency: assume single-run (no parallel actuator); enforce a lock file.

## 9. References

- Brain: `tools/book_filer/scan.py`, `manifest.py`, `calibration.py`; signed verdict shape in
  `data/batch_reports/book_filer_whatif/20260603-184428/run-b/calibration-verdict-signed.json`.
- Compound: `docs/solutions/eb365-book-filer-format-tier-demotion-2026-06-03.md`.
- Safety primitives: `tools/book_filer/reparse.py` (EB-360), `fragments.py` (EB-359).
- Junction-delete hazard precedent: CLAUDE.md "Project-Specific Mistakes" (SCRUM-301 recovery).
