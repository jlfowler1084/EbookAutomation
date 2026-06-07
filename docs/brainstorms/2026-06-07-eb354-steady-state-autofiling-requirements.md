---
date: 2026-06-07
topic: eb354-steady-state-autofiling
---

# EB-354 — Steady-State Hermes Auto-Filer (EB-380) + Taxonomy Evolution (EB-381): Requirements

**Epic:** EB-354 (F:\Books reorganization + Hermes auto-filing enforcement).
**Type:** two child Stories — **EB-380** (auto-filer enforce loop), **EB-381** (taxonomy evolution). Both created, status **To Do**.
**Date:** 2026-06-07. **Status:** brainstorm → planning.
**Supersedes seed:** `docs/brainstorms/2026-06-07-eb354-steady-state-autofiling-seed.md`.
**Canonical design:** `docs/superpowers/specs/2026-06-01-fbooks-organization-and-hermes-enforcement-design.md` (§6.5 derivatives, §7 enforcement engine, §8 workflows, §9 rewiring, §10 ownership).
**Decision records:** ADR-0043 (Hermes Tiered Autonomy — ClaudeInfra/INFRA-491), ADR-0045 (actuator safety — ClaudeInfra/INFRA-552).
**Relates:** INFRA-515 (Hermes control-plane), EB-355 (filer foundation), EB-366 (Qwen classification tail). **Sequences before:** EB-379 (bulk import).

---

## 1. Problem & Goal

The one-time migration (EB-355 brain · EB-373 actuator · EB-375 apply · EB-378 harden) reorganized `F:\Books`
into the 12-section taxonomy and is **applied + finalized**. But there is **no enforcement for new arrivals**:
a book dropped into `F:\Books` today re-rots the structure. The library has no steady-state intake.

**Goal (EB-380):** a Hermes-scheduled loop that classifies new books staged in `F:\Books\_Inbox` and records
where each should be shelved — **fail-safe** (doubt → never a blind move). **Goal (EB-381):** a governed way for
the taxonomy to *grow* when a book fits no existing section.

**v1 is propose-only** — the canonical spec's prescribed accuracy break-in (§7: "runs propose-only into
`_Needs_Review` … also the ideal accuracy break-in period"). The cron **never moves a file**; it writes a proposal
queue and a digest. Destructive autonomous auto-move, Calibre adoption, and Qwen escalation are explicitly
**follow-on units** that layer on after the break-in proves accuracy.

## 2. Verified live state (2026-06-07 — recorded so planning does not re-assume)

- **`F:\Books`:** 12 sections + operational folders (`_Needs_Review`, `_Quarantine`, `_Trash_Pending`) present.
  **`_Inbox` does NOT exist yet** (`book_filer/scaffold.py: ensure_operational_layout` can create it).
  `Audio_Books` legitimately holds 36 files (format root, scan-excluded). **~11 migration stragglers remain**
  in emptied source folders: `Drug Cartels` (6), `Bible Study` (2), `Biographies` (1), `BookFinder` (1),
  `MarketScout` (1) — useful as the first real break-in sample.
- **Hermes** (`hermes-ubuntu` WSL distro, **Running**; CLI at `~/.local/bin/hermes`): 6 active crons —
  `karen-health-monitor` (14:30), `karen-trigger` (14:00), `karen-report-cleanup` (06:00),
  `qwen-nightly-trigger` (23:00), `qwen-feeder-sweep` (22:50), `qwen-nightly-recovery` (23:20).
  **No book-filing cron exists.** The proposed `0 3 * * *` slot is **clear** of every job. Established pattern:
  **no-agent cron → `.sh` → stdout delivered directly.**
- **ClaudeInfra** (main tree): `docs/operations/hermes-primary-crons.md`, `configs/hermes/`, and
  `configs/qwen-authorization.json` all present (control-plane is merged, not stuck in worktrees).
  **`configs/books-authorization.json` does NOT exist** — the EB-381 fence is greenfield, template =
  `qwen-authorization.json`.
- **Branch state:** local EbookAutomation `master` is **2 commits behind `origin/master`** (the seed-doc PR #216
  is not yet pulled locally). Fast-forward only (0 ahead). **Reconcile before implementation.**

## 3. Core decisions (resolved in brainstorm)

| # | Decision | Choice |
|---|----------|--------|
| D1 | **v1 scope** | **Propose-only MVP** — deterministic classify, **no moves**, no `calibredb`, no Qwen, no ADR grant. |
| D2 | **Staging layout** | **Per-source `_Inbox` subfolders** (`_Inbox\BookFinder`, `_Inbox\Manual`, `_Inbox\Conversions`, `_Inbox\Migration`). Follows §9 which already repoints `BookFinder.output_root → _Inbox\BookFinder`. |
| D3 | **Proposal mechanism** | **No-move JSONL queue** written **OUTSIDE the library** at `data/batch_reports/book_inbox_sweep/inbox-proposals.jsonl` (repo path) + digest. Files **stay in `_Inbox`**. A separate human-run confirm command drains approved rows. **Correction (verified):** the queue must NOT live under `F:\Books\_Migration_Manifests` — `_assert_output_outside_scan` (scan.py:95) and `_run_dir_conflict` (actuate.py:123) reject run artifacts inside `library_root`. An optional read-only export under `_Migration_Manifests` is fine for operator visibility, but it is not the authoritative queue. |
| D4 | **Threshold policy** | **Three-tier**: `propose` (≥HIGH, auto-move-ready later) / `ambiguous` (LOW–HIGH, best-guess + alternatives) / `no-match` (<LOW or no section → EB-381 candidate). The **numbers are calibrated** against live `_Inbox` data — not guessed. |
| D5 | **Cadence** | Daily **`0 3 * * *`**, **no per-run cap** in v1 (nothing moves, no API called). |
| D6 | **Reporting** | **Discord for v1** via the proven `Send-DiscordWebhook.ps1`; **Telegram fast-follow** once INFRA-502 outbound dispatch from a no-agent cron is proven. (Reverses the initial Telegram pick — feasibility found no-agent-cron→Telegram outbound is unshipped; every live no-agent cron uses Discord.) |
| D7 | **EB-381 seam** | v1 **detects + flags** `no-match` only; EB-381 owns the propose→approve→cross-repo-PR governance and consumes those flags. |
| D8 | **Confirm step** | `Confirm-BookProposals` is **human-run** (never in the cron). **Correction (verified):** it reuses the **`move.py` move primitive + a fresh inbox-scoped journal** (journaled, reversible, reparse-safe, idempotent) — NOT `actuate.py`'s gated apply, which refuses without a signed-GREEN whole-corpus manifest (`verify_binding`, actuate.py:214) and an external backup proof (`verify_backup_proof`, :230) that an incremental inbox slice cannot supply. The doc must not claim the actuator's signed-manifest/backup guarantees for inbox moves. Human-authorized ⇒ **no ADR-0043 *autonomy* grant required**, BUT the `books-authorization.json` fence's **path-scope + hard-exclusion rules are data-safety controls that apply to ALL movers** (cron and human) once the fence exists — see security findings. The auto-move follow-on = letting the cron invoke this path autonomously, which is when the ADR-0043 grant becomes the additional prerequisite. |
| D9 | **v1 proof vs mover** | The **propose loop** (U1/U2/U4/U6/U7) is the break-in proof and ships first. **U3 `Confirm-BookProposals` is a separate unit gated on U6 calibration** — it lands right after thresholds calibrate, NOT as part of the v1 acceptance gate (a propose-only proof must not depend on a mover). |

## 4. The v1 loop

```
Hermes no-agent cron (0 3 * * *)
   └─ book-inbox-sweep.sh            (ClaudeInfra-owned)
        └─ pwsh -NoProfile -NonInteractive -File Invoke-BookFileGuarded.ps1   (EbookAutomation-owned)
             ├─ scaffold _Inbox\<source>\ if missing
             ├─ for each ELIGIBLE file in _Inbox\** (skip in-flight: .crdownload/.part/.tmp + settle-window):
             │    ├─ reparse-ancestry check on SOURCE → junction? → _Quarantine, never classify
             │    ├─ deterministic classify (IMPORT book_filer primitives — see R3; scan() itself skips operational folders)
             │    ├─ dedup vs shelf index (shelf-index.json: basename/sha/planned_calibre_key) → duplicate? flag, note canonical
             │    ├─ derivative check (§6.5) → v1 has no source link (no calibredb) → ALL KFX/TTS/audio → ambiguous/review
             │    └─ append ONE tiered row to the proposals queue (OUTSIDE F:\Books — see D3)   ← FILE DOES NOT MOVE
             └─ emit digest (swept / proposed / ambiguous / no-match / dup / derivative)

(separate, human-run, NOT in the cron)
Confirm-BookProposals  → drains rows marked accepted → moves via move.py primitive + fresh inbox journal (reversible)
                         ^ this is the seam the future autonomous auto-move unit will invoke under an ADR-0043 grant
                           (NOT actuate.py's signed-manifest/backup-gated apply — see D8)
```

## 5. Behavioral contract — EB-380 v1 (requirements)

**Trigger & wrapper**
- **R1.** A **no-agent** Hermes cron (`0 3 * * *`) runs `book-inbox-sweep.sh`, which invokes
  `pwsh -NoProfile -NonInteractive -File Invoke-BookFileGuarded.ps1 -LibraryRoot F:\Books`. (ClaudeInfra owns the
  cron + `.sh`; EbookAutomation owns the `.ps1`.) `[CmdletBinding(SupportsShouldProcess)]`, supports `-WhatIf`.
  **On-demand:** the same wrapper is also invokable ad-hoc ("sweep now" — human / Discord / SOUL-triggered) so a
  just-dropped book is classified immediately rather than waiting for 03:00 (the seed/spec already envision this).
- **R2.** **Scaffold (idempotent).** Ensure `_Inbox` + per-source subfolders (D2) exist.
  **Correction (verified):** `scaffold.ensure_operational_layout` creates `_Inbox` itself (it iterates
  `config.operational_folders`) but does **not** create the per-source children — a new
  `ensure_inbox_subfolders(config)` helper (reusing `_ensure_safe_dir`) is needed, and scaffold must
  reparse-check the `_Inbox` ancestry before creating anything.

**Classify & propose (no move)**
- **R3.** For each **eligible** file under `_Inbox\**`, compute
  `{section, subcategory, author, title, year, confidence, classification_source}` **deterministically**. **No Qwen in v1.**
  **Correction (verified):** `scan.py` *skips* `_Inbox` (it's in `operational_folders`, pruned by `_build_skip_set`/`_iter_book_files`)
  and is a whole-corpus manifest engine with no single-file API. v1 therefore builds a **new inbox-scoped driver** that
  **imports** the deterministic primitives (`classify_name`, file-facts, shelf-path computation, `reparse.has_reparse_in_ancestry`)
  and runs them over `_Inbox` — it is *not* a call to `scan()`. **Eligibility:** skip in-flight files
  (`.crdownload/.part/.tmp/.!qB`, zero-byte) and require a settle window (mtime age) so a 3am sweep never hashes a
  mid-download file. **Source reparse check** (full ancestry) runs *before* classify; a junction in the source chain → `_Quarantine`.
- **R4.** Append **exactly one** row per file to the proposals queue (D3 path, **outside** `F:\Books`) carrying: tier (D4),
  proposed shelf path, confidence, rationale, source subfolder, dedup verdict, derivative verdict, file sha, size, mtime.
  **The file is not moved.** **Idempotent**: re-running yields the same row; already-queued/accepted rows are not duplicated.
  **Correction (verified):** "keyed by sha+path" is underspecified for an active inbox — a rename changes path, an edit
  changes sha. The key + supersede rule (e.g. key on `sha`, carry `path`; a content edit retires the stale row) is a
  **planning decision** (§10). The nightly sweep should **short-circuit unchanged files** (path,size,mtime) rather than
  re-hash the whole growing backlog.
- **R5.** **Dedup & derivative routing.** Before proposing, check each file against the **already-shelved library**.
  **Correction (verified):** `dedup.py: plan_dedup` only compares files *within a single scan batch* — it does not read
  the 760 shelved files. v1 must load a **shelf index** (`_Migration_Manifests\shelf-index.json`, or a re-hash of the
  shelf) as the dedup oracle (basename/sha/`planned_calibre_key`); `duplicate` rows are flagged, never proposed as new books.
  **Derivative routing (§6.5) is inert in v1:** the source Calibre ID comes from the §8⑤ completion hook, which is
  out of scope here — so **all** KFX/TTS/audio inbox files route to `ambiguous`/review (the "attach to source" branch
  activates only with the completion-hook + Calibre unit). **Confirm-time collision:** if an accepted row's destination
  already exists, route to `_Duplicates_Pending` (honor the dedup verdict) — do **not** fall through to the actuator's
  `allow_unique` rename, which would silently mint a `Title (1)` phantom copy.

**Safety (inherited from the migration's hard-won primitives)**
- **R6.** **Fail-safe.** Any error, ambiguity, or below-threshold result **never** produces a move; worst case the
  file stays in `_Inbox` and is surfaced in the digest. (Inverse of Karen's fail-open — a wrong book move is destructive.)
- **R7.** **Path safety even though v1 does not move.** Reparse-point rejection across full ancestry (EB-360) on **both**
  the source (R3 — before classify) **and** any emitted destination; sanitize + long-path (§5.3); **EB-378 containment** —
  the queue must **never** emit a proposed destination outside `--library-root`. `-LibraryRoot` itself must be validated
  against the canonical `config/settings.json` value before it is trusted as the containment boundary (it arrives as a
  string across the `.sh → pwsh` seam).

**EB-381 seam & the confirm executor**
- **R8.** **No-match flagging (detect-only).** Files matching no section/subcategory above LOW → tier `no-match`,
  with grouping metadata (sample files, evidence) for later clustering. Counted in the digest. v1 **does not create
  categories** and does not write to `books-taxonomy.json` / `books-authorization.json`.
- **R9.** **`Confirm-BookProposals` (human-run, D8).** Reads rows a human marked accepted and executes them via the
  **`move.py` move primitive** with a fresh inbox-scoped write-ahead journal (reversible), containment, reparse rejection,
  and idempotency. **Re-verify before moving:** re-hash the source and confirm it still matches the row's `sha` (the file
  could have been swapped between propose and confirm); on mismatch → `_Needs_Review`. Refuse (don't silently skip) an
  accepted `merge-format`/derivative row (`route_target` returns `None` for it). Never moves a non-accepted row. Not wired
  into the cron. **(See D8: this is NOT `actuate.py`'s signed-manifest/backup-gated apply.)**

## 6. Implementation units (decomposition)

Full INFRA-216 Parallelization Map (frozen interfaces, files-touched, merge gates) is produced in `ce:plan`.
This is the unit breakdown + dependency order.

| Unit | Owner | Summary | Depends on |
|------|-------|---------|------------|
| **U1** | EB | **Config delta only** — the shared block already exists (`config/settings.json:198-205`, bound by `LibraryConfig`). Real delta: add per-source `_Inbox\<source>` subfolders to scaffold + confirm `scan_exclude` covers `F:\Documents`/`Audio_Books`. Do NOT re-add existing keys. | — |
| **U2** | EB | `Invoke-BookFileGuarded.ps1` **propose path** (R3–R8): classify, dedup/derivative verdicts, tiered JSONL queue, fail-safe, idempotent, `-WhatIf` | U1 |
| **U3** | EB | `Confirm-BookProposals` **human-run executor** (R9) over the `move.py` move primitive + inbox journal. **Separate unit, gated on U6 calibration — NOT a v1-proof dependency (D9).** | U2, U6 |
| **U4** | EB | **Discord digest** (D6) via `Send-DiscordWebhook.ps1`; Telegram fast-follow | U2 |
| **U5** | EB | **§9 rewiring**: repoint BookFinder output → `_Inbox\BookFinder` (`config/settings.json:189`, `tools/book_downloader.py:42`, `EbookAutomation.psm1` fallbacks); add scan-exclusion filter (skip `_`-prefixed, `Audio_Books`, `F:\Documents`) to `Scan-BooksFolder.ps1` + `Invoke-TesseractKindleBatch.ps1`; re-run literal-path audit | U1 |
| **U6** | EB | Tests + **calibration gate**: pytest for wrapper + queue schema; run-twice determinism (`PYTHONHASHSEED=0`, normalized compare); spot-check to set the three-tier thresholds | U2 |
| **U7** | INFRA | Hermes cron wiring: `book-inbox-sweep.sh` no-agent cron `0 3 * * *` in `hermes-ubuntu`; register via hermes-cron-authoring; verify `hermes cron list`; wire **Discord** webhook; **pre-invoke `.ps1`-exists check + non-zero-exit alert** (silent 3am failure = re-rot) | U2, U1 |

**EB-381 units — NOT in v1 scope** (high-level only; detailed design deferred to its own brainstorm, gated on break-in data):

| Unit | Owner | Summary |
|------|-------|---------|
| **T1** | EB | No-match **aggregation**: cluster queued `no-match` rows into candidate categories (min-evidence, merge/duplicate detection) → proposal records |
| **T2** | EB + INFRA | **Propose→approve governance**: human review → **paired PRs** (`config/books-taxonomy.json` [EB] + `configs/books-authorization.json` [INFRA fence]) **land together**; only then an auto-file target |
| **T3** | EB | Sprawl guards + lifecycle: section-vs-subcategory granularity; merge/split/rename of existing categories |

**Order (v1 propose-loop proof):** `U1 → U2 → (U4, U6, U5) → U7`. **U3 (confirm/mover) is gated after U6 calibration** and ships as a separate post-proof unit: `U6 (calibrated) → U3`. EB-381 `T1+` only after v1 ships and produces real `no-match` data.

## 7. Staged rollout (acceptance path)

1. Build **U1 + U2**; seed `_Inbox` with the ~11 migration stragglers + a few fresh books → run wrapper `-WhatIf`
   → inspect the JSONL queue. **Zero moves.**
2. **U6 calibration:** run twice, confirm determinism, spot-check tier assignments, tune the three-tier thresholds.
3. Wire **U7** cron (propose-only); confirm `hermes cron list` shows it; let it run; verify the **Discord** digest.
4. (Post-calibration) Exercise **U3** `Confirm-BookProposals` on a small accepted batch (human-run) → verify journaled, reversible moves.
5. **Break-in period → measurable exit criterion** before enabling the auto-move follow-on: e.g. `propose`-tier
   wrong-shelf rate ≤ ~2% over a ≥2-week live window with ≥N proposals (or an explicit user go/no-go by a set date) —
   determinism-green alone is insufficient. On graduation, the **auto-move follow-on** adds the ADR-0043 fenced grant
   scoped to `F:\Books` + `books-authorization.json` + cron-invoked confirm.

## 8. Scope boundaries / non-goals (v1)

- **No autonomous moves** — the cron never moves; only human-run `Confirm-BookProposals` moves. Auto-move is a
  follow-on unit, gated on ADR-0043 + `books-authorization.json` + measured break-in accuracy.
- **No Calibre adoption** — no `calibredb add`, no materialize-all-formats (spec §3/§8④ deferred). v1 proposes shelf paths only.
- **No Qwen escalation** — deterministic-only (EB-366 / agent-mode cron deferred).
- **No reconciliation job** (§6.4 / §8⑦) — nothing is materialized to reconcile yet.
- **No taxonomy creation** — EB-381 is detect-and-flag only in v1. **Acknowledged:** automated category *creation* (the
  user's explicit "automate this too") is intentionally deferred to EB-381 because a new shelf is a permanent structural
  change warranting human-in-loop governance. **Trigger to revisit:** once a threshold of `no-match` rows accumulates OR
  the EB-379 import lands (whichever first) — so the governance half isn't indefinitely gated on data only this loop produces.
- **No `_Trash_Pending` purge** — manual + separate (§6.6), unchanged.
- **No EB-379 bulk import** — separate Story; it stages into `_Inbox` and rides this loop (becomes "inventory + stage," not a parallel categorizer).

## 9. Success criteria (v1)

- A cron sweep classifies every `_Inbox\**` file and writes **exactly one** tiered queue row each; **zero files moved by the cron**.
- The sweep is **idempotent** — re-running produces no duplicate rows and stable proposals.
- Duplicates and derivatives are correctly flagged (never proposed as new books); **fail-safe holds** — no proposed
  destination ever resolves outside `--library-root` (EB-378 containment); reparse/long-path inputs are rejected, not guessed.
- `Confirm-BookProposals` (human-run) moves an accepted batch into the correct shelves — **journaled and reversible** —
  and never moves a non-accepted row.
- The **Discord** digest accurately reports swept / proposed / ambiguous / no-match / dup / derivative counts.
- **Determinism gate green** (twice-run normalized match); three-tier thresholds **calibrated** against a live sample.
- **Calibration sample adequate + representative** — at least the tool's `min_spot_check` floor (≈20), seeded with fresh clean-metadata arrivals, not only the ~11 biased migration stragglers; and a **correctness signal distinct from determinism** (human-judged wrong-shelf rate on the `propose` tier) is recorded. Determinism-green alone never authorizes the auto-move follow-on.
- **(U5)** BookFinder output resolves to `_Inbox\BookFinder` and the scan-exclusion filter skips `_`-prefixed folders, `Audio_Books`, and `F:\Documents` — verified by a targeted test.

## 10. Outstanding Questions

### Resolve Before Planning
- *(none — all product decisions resolved in §3: v1 scope (D1), staging (D2), proposal mechanism (D3), threshold
  policy (D4), cadence (D5), reporting = Discord (D6), EB-381 seam (D7), confirm-via-move.py (D8), and confirm/mover
  as a separate post-calibration unit (D9). Ready for planning.)*

### Deferred to Planning
- [Affects R4][Technical] Final JSONL queue schema + idempotency key (`sha` vs `planned_calibre_key`); row lifecycle states (`proposed → accepted → executed`).
- [Affects R1/U7][Needs research — INFRA] Telegram dispatch from a **no-agent** cron — does INFRA-485 dispatch cover cron stdout, or does `book-inbox-sweep.sh` post directly? Verify against live Hermes wiring.
- [Affects R1/U7][Technical] The **frozen cross-repo interface** between `book-inbox-sweep.sh` and `Invoke-BookFileGuarded.ps1` (args, `-LibraryRoot` passing, exit codes, log/queue path contract). Define in the `ce:plan` Parallelization Map before either side is built.
- [Affects R9/U3][Technical] Whether `Confirm-BookProposals` calls `actuate.py` apply directly or a thin inbox-specific wrapper around the move primitive.
- [Affects D4/U6][Technical] The actual HIGH/LOW threshold numbers — calibrate against a seeded `_Inbox` sample during planning/implementation.
- [Affects R9/U3][Technical] Confirm reuses `move.py` (ungated). Confirm no inbox-scoped signed/backup gate is needed, or design a lighter inbox gate (the actuator's `verify_binding`/`verify_backup_proof` require a whole-corpus signed manifest an inbox slice lacks).
- [Affects R4][Technical] Idempotency key + supersede rule under rename/edit, and the nightly short-circuit on `(path,size,mtime)` to avoid re-hashing a growing backlog.
- [Affects R3][Technical] In-flight settle window + transient-extension exclusion list (`.crdownload/.part/.tmp/.!qB`).
- [Affects R5][Technical] Shelf dedup-oracle freshness post-finalize (re-hash the shelf vs trust `shelf-index.json`).
- [Affects R1/U7][Technical] WSL `hermes-ubuntu` → Windows `pwsh` invocation + path translation; a pre-invoke `.ps1`-exists check; and a **non-zero-exit alert** — a silent 3am failure means the library re-rots with no signal.
- [Affects backlog][Technical] `_Inbox`/queue growth lifecycle + digest treatment of aged-unactioned rows (a separate "aging backlog (N, oldest D days)" line vs re-spamming the nightly delta).

### Deferred to a dedicated EB-381 brainstorm (gated on break-in data)
- Auto-propose vs human-initiated-only; where proposals queue (`_Needs_Review/_Proposals` lane vs JSONL vs Jira);
  merge/split/rename of existing categories; how Calibre tags relate to shelf sections; cross-repo PR choreography
  (EB taxonomy + INFRA fence landing atomically).

## 11. References

- Seed: `docs/brainstorms/2026-06-07-eb354-steady-state-autofiling-seed.md`.
- Canonical design: `docs/superpowers/specs/2026-06-01-fbooks-organization-and-hermes-enforcement-design.md` (§6.5, §7, §8, §9, §10, §11, §12).
- Actuator (reused by R9/U3): `docs/brainstorms/2026-06-04-eb354-book-filer-actuator-requirements.md`; `tools/book_filer/actuate.py`, `move.py`, `backup.py`, `journal.py`, `manifest.py`, `scaffold.py`.
- Classifier brain (reused by R3): `tools/book_filer/scan.py`, `calibration.py`.
- Safety primitives: `tools/book_filer/reparse.py` (EB-360), `fragments.py` (EB-359); EB-378 containment.
- Compound: `docs/solutions/eb375-book-filer-actuator-first-apply-2026-06-07.md`.
- Fence template: ClaudeInfra `configs/qwen-authorization.json`; governance: ADR-0043 (Hermes Tiered Autonomy), ADR-0045 (actuator safety).

## Next Steps

`Resolve Before Planning` is empty → **`-> /ce:plan`** for structured implementation planning + the full INFRA-216 Parallelization Map.
