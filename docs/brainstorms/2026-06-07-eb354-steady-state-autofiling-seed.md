# Steady-State F:\Books Auto-Filing — Brainstorm Seed

**Date:** 2026-06-07
**Status:** **SEED for a future `ce:brainstorm` session** — not yet brainstormed. This doc exists so a fresh session starts fully loaded; it captures context and **open questions**, and deliberately does **not** decide the design.
**Tickets:** EB-380 (auto-filer enforce loop), EB-381 (taxonomy evolution). **Relates:** INFRA-515 (Hermes control-plane), EB-355 (filer foundation), EB-366 (Qwen classification tail). **Sequences before:** EB-379 (bulk import).

---

## 1. Goal (user's framing, 2026-06-07)
> "Utilize the Hermes agent for a scheduled cron job that keeps the library organized and auto-files books. A staging location where I place all new books to be indexed; when the Hermes job runs, all entries get filed to their proper location. It's likely we'll need to create new folder categories — automate this too. Build this prior to the bulk import (EB-379)."

Two distinct deliverables fall out of this:
- **EB-380** — the steady-state **inbox→shelf auto-filer** (the enforce loop for *new arrivals*).
- **EB-381** — **taxonomy evolution**: a governed way to *create new categories* when a book fits none.

---

## 2. Where we are (current state)
- `F:\Books` is reorganized into the 12-section taxonomy (`01 History` … `12 Periodicals & Magazines`) + operational folders (`_Needs_Review`, `_Trash_Pending`, `_Quarantine`). The one-time migration is **applied + finalized** (EB-375). 760 files; pristine pre-apply mirror at `C:\Books`.
- **Built:** the `book_filer` read-only brain (`scan.py` classifier, determinism gate, calibration/signed verdict), the **actuator** (`actuate.py`: dry-run/apply/undo/finalize, write-ahead JSONL journal, external-mirror backup gate, EB-378 containment guard), and the `move`/`backup`/`journal`/`manifest`/`reparse`/`fragments`/`pathsafe`/`scaffold` modules.
- **NOT built (this is the work):** the **incremental** auto-filer (`Invoke-BookFileGuarded.ps1`); `_Inbox` does **not** exist on disk yet (`scaffold.ensure_operational_layout` can create it); the **Hermes cron** wiring (INFRA-515); the **taxonomy-evolution** automation.
- **Loose ends (non-blocking):** emptied original source folders (`Bible Study\`, `Conspiracy\`, …) still present (cosmetic); EB-376 (junk embedded metadata → wrong author subfolder); EB-366 (Qwen classification tail / review-rate reduction).

---

## 3. Canonical design — READ THESE FIRST
- **`docs/superpowers/specs/2026-06-01-fbooks-organization-and-hermes-enforcement-design.md`** — the authoritative spec:
  - **§7 Hermes enforcement engine** — the auto-file loop (cron → guarded wrapper → fence → ADR-0043 grant → propose-only-first → report).
  - **§8 workflows** — ③ calibrated inbox auto-file (core loop), ⑤ conversion-output → `_Inbox` completion hook (carries source Calibre ID), ⑦ reconciliation job.
  - **§6.5 source-vs-derivative** — KFX/TTS/audio attach to the source Calibre book, never re-ingested as new books.
  - **§9 ingest rewiring** — funnel BookFinder / Plex / conversions through `_Inbox`; **single-writer rule** (only the filer writes the shelf tree).
  - **§10 ownership** — EB owns book-domain logic + `books-taxonomy.json`; ClaudeInfra owns crons + `books-authorization.json` fence + ADR-0043 grant; Plex owns ingest repoint.
  - **§11 risks**, **§12 resolved decisions** (copy mode; EB umbrella epic; arXiv→09/Science; 30-day manual purge).
- **`docs/solutions/eb375-book-filer-actuator-first-apply-2026-06-07.md`** — actuator safety design (R1–R8) + the operational runbook + lessons.
- **ClaudeInfra** — ADR-0045 (actuator safety, Accepted), **ADR-0043** (Hermes Tiered Autonomy / INFRA-491 — the tier-grant governance auto-move needs).

---

## 4. The intended enforce loop (§7) — the starting point
- **Trigger:** no-agent cron (`0 3 * * *`) → `book-inbox-sweep.sh` → `pwsh … Invoke-BookFileGuarded.ps1`. Deterministic rules file the easy cases; ambiguous files escalate to a **Qwen agent-mode cron** that proposes `{section, subcategory, author, title, year, confidence}`.
- **Fence** (`books-authorization.json`, ClaudeInfra, modeled on `qwen-authorization.json`): section/subcategory **allowlist**, hard exclusions, confidence threshold, per-run cap, `F:\Books`-only path scope.
- **Guarded wrapper** `Invoke-BookFileGuarded.ps1` (EbookAutomation): `SupportsShouldProcess` + `-WhatIf`; **fail-safe** (any doubt → `_Needs_Review`, never a blind move — *inverse* of Karen's fail-open, because a wrong book move is destructive); reparse rejection + sanitize + long-path; **idempotent** (already-placed = no-op); JSONL log; `calibredb` for the ID; honors `materialize_mode`.
- **Autonomy gate:** auto-moving production files is *mutating* and outside current ADR-0043 grants → requires an explicit **fenced tier grant scoped to `F:\Books`** via a human-reviewed ClaudeInfra config PR. Until it lands, the filer runs **propose-only into `_Needs_Review`** (also the ideal accuracy break-in period).
- **On-demand:** a `SOUL.md` "file my book inbox" known-request → Telegram trigger.
- **Report:** Discord (`Send-DiscordWebhook.ps1`) / Telegram digest — "filed N, M to review, K dup-skipped."
- **Caveat:** live Hermes cron/`.env`/`SOUL.md` state lives inside the `hermes-ubuntu` WSL distro — **verify live state (`hermes cron list`) before building.**

---

## 5. The new concern — taxonomy evolution (EB-381)
The §7 design assumes a **fixed** section/subcategory allowlist. New subjects *will* arrive. A new shelf is a **permanent structural change** → favor **propose-then-approve** (Qwen/deterministic suggests a category with rationale + sample files; it queues for human approval; approval = a reviewed PR to `books-taxonomy.json` (EB) **and** `books-authorization.json` (INFRA fence); only then is it an auto-file target). Guard against taxonomy sprawl (merge/duplicate detection, min-evidence to propose).

---

## 6. Open questions for the brainstorm (the real decisions — do NOT pre-decide)
1. **Staging layout:** `F:\Books\_Inbox` with per-source subfolders (`_Inbox\BookFinder`, `_Inbox\Manual`, `_Inbox\Migration`)? Or a single drop?
2. **Cadence + split:** cron schedule; the deterministic-first vs Qwen-escalation boundary; per-run cap.
3. **Confidence threshold** and **how long to stay propose-only** (into `_Needs_Review`) before enabling auto-move.
4. **Calibre adoption:** does the filer *add to Calibre* (the metadata authority) + materialize the shelf, or shelf-place only for now? (`calibre_library = F:\Library\Calibre`; `materialize_mode = copy`.)
5. **Dedup** against the now-reorganized library (basename/sha/`planned_calibre_key`); **derivative handling** (§6.5).
6. **New-category queue + approval choreography** (EB-381): where proposals live; how the EB-taxonomy PR and the INFRA-fence PR land *together*; preventing sprawl.
7. **ADR-0043 grant scope:** exact fenced grant (F:\Books-only, caps, threshold); who authors the ClaudeInfra PR.
8. **Reconciliation cadence** (§8 ⑦): Calibre ↔ shelf drift detection.
9. **Reporting** channel + content.
10. **EB-379 flow:** confirm the bulk import stages into `_Inbox` and rides this loop (so EB-379 becomes "inventory + stage," not a parallel categorizer).

---

## 7. Hard constraints / guardrails (non-negotiable — from prior lessons)
- **Fail-safe:** doubt → `_Needs_Review`, never a blind move (a wrong book move is destructive).
- **Trash-not-delete:** `_Trash_Pending` (30-day), purge is separate + manually approved; nothing in the automated path hard-deletes.
- **Reparse-point rejection** across full ancestry (SCRUM-301 junction-wipe defense); no junctions; run from the main tree.
- **EB-378 containment:** never write outside `--library-root`.
- **Single-writer rule:** only the filer writes the shelf tree; all ingest funnels through `_Inbox`.
- **Determinism + calibration** before any live auto-move; **ADR-0043 fenced grant required**; the agent may not self-authorize.
- **Source-vs-derivative:** KFX/TTS/audio attach to the source, never re-ingested as new books.
- **Verify live Hermes state** before building (`hermes cron list`).

---

## 8. Suggested first steps for the brainstorm session
1. Read this seed + design spec §7–§12 + `docs/solutions/eb375-…`.
2. Verify live Hermes state (`hermes cron list`; does `books-authorization.json` exist yet?) and INFRA-515's current state.
3. Resolve the §6 open questions.
4. Decompose EB-380 + EB-381 into implementation units; produce a Parallelization Map (per INFRA-216).
5. Confirm the EB-379 sequencing (stage-into-`_Inbox`) and note it on EB-379.
