# EB-355 Plan 5 (re-scoped) — Classification + Metadata Accuracy — Requirements

- **Date:** 2026-06-02
- **Ticket:** EB-355 (Plan 5, re-scoped from "the actuator" to "classification + metadata accuracy first")
- **Status:** requirements (brainstorm output) — ready for `ce:plan`
- **Branch:** `feat/EB-355-plan5-classification` (off `origin/master`)

## Problem / context
The real-corpus `-WhatIf` run (`data/batch_reports/book_filer_whatif/20260602-182319/run-b/`) over 680 files passed the **determinism** gate (GREEN) but the **calibration** gate is **RED**: 4 of ~16 sampled auto-`copy` rows were mis-shelved, all at confidence 1.00. Root cause is a **signal problem, not a confidence problem**: `tools/book_filer/scan.py` `_build_file_facts` classifies on the cryptic *filename* (`classify_name(name, ...)`) and ignores the descriptive embedded *metadata title* it already extracts. Examples: *When Genius Failed* (LTCM finance) → Writing/Publishing; *The Creature from Jekyll Island* (Federal Reserve) → Fiction; *Unacknowledged* (Greer) → Philosophy; *The Unseen Realm* (Heiser, biblical) → Fiction.

Two adjacent issues block trusting/automating the gate and a future apply:
- **Metadata quality:** destinations use raw embedded `author/title/year` (`_destination_path`), so junk like author `svejk, josef` and year `101` is an apply-time naming risk even when the section is correct.
- **Gate vocabulary mismatch (false-GREEN risk):** the spot-check sheet emits `disposition = manifest action` (e.g. `copy`), but `evaluate_calibration` counts wrong-shelf only when `disposition == "shelf"`. An automated ingestion of the raw sheet would under-count and false-GREEN. The current RED verdict is correct only because it was computed with a manual `copy→shelf` mapping.
- **CSV usability:** the spot-check header begins with `#`, which PowerShell `Import-Csv` treats as a comment, corrupting scripted ingestion.

The migration "brain" (manifest, dedup, fragments, calibration, scan) is built and proven read-only-safe; it just needs an accurate classifier and clean metadata before any file moves.

## Goals
1. **Title-aware deterministic classification** — feed the embedded metadata title into the classifier (blended with the filename), and clean up keyword collisions (e.g. `creature`/`island`/`supernatural` must not auto-map to Fiction).
2. **Metadata quality** — sanitize implausible/junk embedded `author`/`year` before they reach `destination_path` (fake uploader names; out-of-range years).
3. **Gate hardening (pre-automation)** — make the calibration vocabulary consistent (`copy`/`hardlink` → `shelf`) and the spot-check CSV machine-ingestible (`#` → `spot_index`), each with a regression test.
4. **Re-measure** — re-run the read-only `-WhatIf` (two-run A/B) and report the new calibration verdict; iterate toward GREEN.

## Decisions (from brainstorm 2026-06-02)
- **Classifier strategy: deterministic only.** Title-aware keyword classifier + keyword-collision cleanup. **No LLM** in this plan (preserves the determinism gate, zero API cost per api-governance). An LLM fallback for the residual hard tail is explicitly deferred (see Non-goals / Deferred).
- **Success bar: zero wrong-shelf AND an exact auto-shelf floor.** Define `auto_shelf_actions = {copy, hardlink}`. GREEN requires (a) determinism, (b) `wrong_shelf == 0` in the spot-check, (c) `auto_shelf_count >= 224` (the current baseline, 224/680) **when run against the same frozen corpus**, and (d) a non-empty signer. The auto-shelf floor prevents the degenerate "route everything to `review`" path that would be technically GREEN but useless. **Trash safety invariants are a separate required gate** (see Success criteria), not folded into wrong-shelf.
- **Conservatism:** when the title+filename signal is ambiguous, route to `review` (always safe) rather than shelve with a guessed section — but not so aggressively that the auto-copy floor is missed.

## Non-goals / deferred
- **The file-moving actuator** (copy/trash/quarantine execution) — stays a later plan, gated behind a **GREEN** re-run. This plan moves nothing.
- **LLM-assisted classification** for the residual hard tail — deferred; the gap left by the deterministic classifier becomes the documented case for it.
- **No `F:\Books` mutation** anywhere — read-only scans only.
- Calibre integration, reconciliation (the later EB-355 plans) — unchanged and out of scope here.

## Success criteria
- Re-run `-WhatIf` (two-run A/B, frozen library) yields **GREEN** = determinism ∧ `wrong_shelf == 0` (spot-check) ∧ `auto_shelf_count (copy + hardlink) >= 224` (baseline, same frozen corpus) ∧ signer. If deterministic-only cannot reach zero wrong-shelf while holding the auto-shelf floor, the residual mis-shelves are documented (titles + why) as the scope of a later LLM pass — and the actuator stays gated.
- **Trash safety invariants — a separate, independent required gate** (not part of wrong-shelf): every `trash` row must remain byte-identical (sha256) to a non-trash sibling, carry a `duplicate_group_id`, and have a metadata anchor — 0 violations (as in the 2026-06-02 run). Both this gate AND the GREEN gate above must hold before the actuator is unlocked.
- Gate hardening: a wrong `copy` spot-check row increments `wrong_shelf_count` (regression); spot-check CSV ingests cleanly via PowerShell `Import-Csv` (regression).
- Metadata sanitization: implausible year (e.g. `101`) and known fake-uploader author names (e.g. `svejk, josef`) no longer flow into `destination_path`; real metadata is preserved (regression for both directions).
- Determinism preserved (the whole approach stays gate-safe — no nondeterministic inputs).

## Constraints
- Read-only `F:\Books`; deterministic; Windows/PowerShell; Python 3.12.
- Work off `origin/master` in a fresh worktree (local master is behind + has unrelated WIP).
- Reuse existing primitives where possible (the `book_filer` package already has a junk-metadata guard in `tools/book_filer/metadata.py` — extend rather than fork).

## Evidence
- RED verdict + manifest: `data/batch_reports/book_filer_whatif/20260602-182319/run-b/calibration-verdict.json` (`deterministic=true, green=false, wrong_shelf_count=4`).
- Confirmed wrong-shelf rows (spot-check #): 1, 6, 9, 30 — all `copy` at confidence 1.0.
- Related primitive-defect follow-ups: EB-359 (fragments folder-blind), EB-360 (reparse fail-open).
