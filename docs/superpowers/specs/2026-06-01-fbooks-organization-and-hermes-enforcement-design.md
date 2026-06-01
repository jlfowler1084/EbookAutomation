# F:\Books Organization + Hermes Auto-Filing Enforcement — Design Spec

- **Date:** 2026-06-01
- **Status:** Design — brainstorm approved; spec reviewed; 4 open decisions resolved (§12) and 5 review findings amended; pending ticket creation
- **Author:** Joe Fowler (with Claude)
- **Scope:** Reorganize `F:\Books` into a subject-first "bookstore" taxonomy, adopt Calibre as the metadata system-of-record, and stand up a Hermes-driven auto-filer that enforces the structure on new arrivals.
- **Spans:** EbookAutomation (book-domain), ClaudeInfra (Hermes control-plane), Plex (ingest source).
- **Ticket gate:** No code/data changes until the umbrella epic + child tickets exist (per INFRA-96). This spec is design-only and ticket-exempt.

---

## 1. Problem & Goals

`F:\Books` holds 757 files / 7.74 GB: **471 loose at the root**, 27 folders that mix four incompatible axes (subject, author, format, project), pervasive duplication, ~20–25% non-book files (tax/passport/insurance/resumes/junk), and several "books" that are actually exploded-EPUB debris or auto-split fragments.

**Goals**
1. A subject-first, bookstore-style 2-level taxonomy on disk, with author→title below subject.
2. Calibre as the metadata authority (IDs, ISBN, dedup, enriched metadata).
3. A safe, reversible one-time migration of the existing mess.
4. Hermes auto-files **new** arrivals into the correct shelf (auto-move high-confidence, queue ambiguous).
5. Non-books relocated out; duplicates collapsed; junk removed — none of it destructively.

**Non-Goals (deferred)**
- Web readers (Calibre-Web / Audiobookshelf) — user chose "Folders + Calibre," not full-stack.
- Quarterly density-audit automation.
- Remote serving of the library.

---

## 2. Architecture — the data model

Two roots, each authoritative for a different thing:

```
F:\Library\Calibre\        METADATA authority (Calibre managed library):
                           per-book Calibre ID, ISBN, dedup verdicts, enriched
                           title/author/year, and the hierarchical #genre column
                           that encodes the 12-section taxonomy.

F:\Books\                  PLACEMENT authority (filer-materialized subject tree).
                           The ONLY writer is the filer. The cross-project seam that
                           Plex (writes) and EbookAutomation (reads) already share.
    _Inbox\                  ALL ingest funnels here (Plex dl, BookFinder, manual, conversions)
    _Needs_Review\           ambiguous classification, fragments, low-confidence
    _Quarantine\             blocked: path too long, unreadable, reparse-point in chain, outside fence
    _Duplicates_Pending\     non-canonical copies awaiting keep/discard sign-off
    _Trash_Pending\          trashed files held 30 days; permanent purge is a separate, manually-approved op (§6.6); never hard-deleted inline
    _Migration_Manifests\    plan-<ts>.{csv,json} + undo-<ts>.ps1 + shelf-index.json
    01 History\ … 12 …\      the shelves
    Audio_Books\             format root (scan-excluded)

F:\Documents\              NON-LIBRARY: tax/admin/resumes/forms (scan-excluded, never shelved)
```

**Ingest flow (one book, apply path):** `_Inbox` → derivative check (§6.5) → `calibredb add` (→ Calibre ID, ISBN, dedup, metadata; Calibre takes ownership of the canonical copy) → filer reads clean metadata + `#genre` → computes sanitized canonical shelf path → **materializes every format Calibre holds for the book** into the shelf (copy or hardlink — §3; multiple formats co-locate under the Author folder, sharing the base name with distinct extensions) → writes manifest row(s) + `shelf-index.json` entry → the consumed `_Inbox` source is moved to `_Trash_Pending` (never hard-deleted). A failure at any step leaves the source in `_Inbox` untouched and routes a marker to `_Needs_Review`. **Note:** `calibredb add` mutates the library and assigns non-deterministic IDs, so it runs ONLY on approved apply — dry-run/plan manifests use a deterministic `planned_calibre_key` instead (§6.1).

**Single-writer rule:** only the filer writes the shelf tree. Plex's downloader and EbookAutomation's BookFinder are repointed to `_Inbox` so there is exactly one chokepoint (§9).

---

## 3. DECISION (resolved: COPY mode) — Shelf materialization

Calibre always owns its own file copies in `F:\Library\Calibre`. The shelf in `F:\Books` is a second on-disk view. How that view is materialized was **resolved at spec review to Copy mode** (Option A); hardlink remains a config-toggle option:

### Option A — Copy mode (RECOMMENDED default)
Shelf entries are independent file copies.
- **Pros:** fully decoupled; shelf can be genuinely read-only without affecting Calibre; Calibre may do anything to its copy; reconciliation is simple hash-comparison.
- **Cons:** ~2× disk (~8 GB total — negligible on a books drive); a Calibre-side file change requires a re-copy (handled by reconciliation).

### Option B — Hardlink mode (opt-in, space-efficient)
Shelf entries are NTFS hardlinks to the Calibre library files (same volume required).
- **NTFS reality:** all hardlinks share ONE MFT record — same data, timestamps, **read-only attribute, and ACL**. Therefore:
  - "Shelf is read-only" is **not** a shelf-only property; it applies to the Calibre name too.
  - Any in-place write through any name mutates the single underlying file (both views change).
  - A replace-style tool (delete+create) breaks the association; link count drops 2→1 (detectable).
- **Required contract (see §3.1).**

**Resolved:** **Copy mode** is the selected default; `materialize_mode: copy|hardlink` remains in config for an opt-in switch. (§12 #1)

### 3.1 The materialization contract (applies to whichever mode)
1. **No tool opens a shelf or library book file for in-place write.** Transforms (Calibre convert, OCR, TTS, the EbookAutomation pipeline) READ the file and EMIT new outputs into `_Inbox`/`processing`. EbookAutomation already complies (inbox→processing→output). Calibre "convert" adds a new format file, not an in-place mutation. Calibre "embed metadata into book files" / "polish" is **disabled by default** (it mutates in place).
2. **Shelf files are read-only.** Copy mode: set read-only on the shelf copy (true isolation). Hardlink mode: read-only is shared defense-in-depth; if an intentional Calibre metadata embed is ever needed, the filer clears RO, lets Calibre update, re-sets RO, and re-verifies.
3. **Verify on materialize.** Hardlink mode: assert link count == 2 and both names share the same file ID (`fsutil file queryFileID`, `fsutil hardlink list`). Copy mode: assert shelf hash == Calibre file hash.
4. **Reconciliation job (the §6 sync phase) is mandatory in both modes.**

---

## 4. The taxonomy

Subject-first, 2 levels, then Author (Last, First) → Title. Display labels below; **canonical on-disk folder names strip `/` and non-ASCII separators** (§7).

| # | Section | Subcategories |
|---|---------|---------------|
| 01 | History | World Wars (WWI, WWII, Weimar); Russia, Soviet & Eastern Europe; Revolution & Political Upheaval; Modern & 20th-Century General; United States & Americas; Military History |
| 02 | Philosophy | Ancient & Classical; Modern & Continental; Ethics & Political Philosophy; Logic & Epistemology; Eastern & Comparative |
| 03 | Religion & Bible Study | Bible Study & Commentary; Theology & Doctrine; Christianity (History & Denominations); Comparative Religion & World Faiths; Apologetics & Devotional |
| 04 | Politics & Society | Marxism & Socialist Theory; Political Ideologies & Geopolitics; Economics & Political Economy; Government & International Relations; Middle East & Foreign Policy |
| 05 | Finance & Investing | Stock Market & Trading; Investing & Personal Finance; Economics (Markets & Theory); Money, Banking & Macro; Business & Entrepreneurship |
| 06 | Fiction & Literature | Classic & Literary Fiction; Austen & 19th-Century Novel; Poetry & Drama; Genre Fiction (SF/Fantasy/Mystery); Literary Criticism |
| 07 | Conspiracy, Esoterica & Fringe | Conspiracy & Hidden History; Esoteric, Occult, Kabbalah & Theosophy; Secret Societies (Freemasonry, Illuminati); UFO & Paranormal; Prophecy & Apocalyptic |
| 08 | Biography & Memoir | Historical & Political Figures; Military & War; Religious & Philosophical Figures; Literary & Artistic Lives; Memoir & Autobiography |
| 09 | Technology, Science & Reference | Programming & Software; Systems, Cloud & IT Admin; Science & Academic Papers; AI & Prompt Engineering; Reference & Encyclopedic |
| 10 | How-To, Hobbies & Practical | Crafts, Hobbies & Music; Home, Garden & Aquatics; Health, Fitness & Cooking; Career & Job Search (how-to); Recovery & 12-Step |
| 11 | Writing & Children's Books | Writing the Children's Book; Craft of Writing (General); Publishing & Self-Publishing; Picture Books & Read-Alouds (study) |
| 12 | Periodicals & Magazines | `<Publication Title>` → `<Year/Issue>` |

**Placement rule (prevents bikeshedding):** file by the *subject of the book*, not topic adjacency. History of the USSR → 01/Russia. Marx's *Capital* → 04/Marxism. Biography of Lenin → 08. When genuinely split, shelve by the book's nature and tag the second axis in Calibre.

### 4.1 Sensitive cluster — neutralized
The `Goblin_Tricks` folder (26 files) + ~35 loose files are a Khazar-thesis / ethno-religious cluster. **No euphemism survives and no loaded string becomes a path.** Files shelve by their actual nature with neutral catalog labels:
- Scholarly history (e.g. Dunlop, *History of the Jewish Khazars*) → **01 History** (neutral metadata tag "Jewish History" optional for findability).
- Mainstream political critique (e.g. Mearsheimer & Walt, *The Israel Lobby*) → **04 Politics & Society / Middle East & Foreign Policy**.
- Polemical / origin-thesis tracts → **07 / Conspiracy & Hidden History** (no special folder).
- `Goblin_Tricks` dissolves; the quoted subcategory is removed entirely.

---

## 5. Naming, identifiers & path safety

### 5.1 Naming convention
- Base: `Author Last, First - Title (Year).ext` → `Cooper, Andrew Scott - The Oil Kings (2011).pdf`
- Series: `Author Last, First - [Series ##] Title (Year).ext` (volume number sorts reading order)
- Author = `Last, First` (matches Calibre `author_sort` + Audiobookshelf). 2 authors comma-joined; 3+ → `Surname et al`; editors → `Surname (ed.)`.
- Folder layout: `<Section>\<Subcategory>\<Author Last, First>\<base name>.ext`.

### 5.2 Collision-safe identifier
When `Author - Title (Year)` collides (editions, translations, volumes, study Bibles, redownloads), append in priority order until unique:
1. Edition/volume tag — `[Vol 2]`, `[NIV]`, `[2nd ed]`
2. `[ISBN 978…]`
3. `[#<calibreID>]`
4. `[<short sha256, 8 hex>]`
Least-ambiguous available wins; the chosen disambiguator is recorded in the manifest (`canonical_reason`).

### 5.3 Path-safety rules
- **Sanitize:** strip/replace `\ / : * ? " < > |` and non-ASCII separators (e.g. `·`); collapse `Title: Subtitle` → `Title - Subtitle`; trim trailing dots/spaces; guard reserved names (CON/PRN/AUX/NUL/COM1–9/LPT1–9).
- **Long paths:** enable `LongPathsEnabled=1`; the filer additionally computes full destination length and, if over limit, **truncates the Title only** (never Section/Subcategory/Author/extension/disambiguator), appending an ellipsis marker, and records the truncation in the manifest.
- **Collisions:** ` (2)`, ` (3)` suffix via the reused `_unique_path()` logic.
- **Reparse-point rejection (hard rule):** before any read or write, resolve the full source AND destination paths and walk **every ancestor component from the drive root to the leaf**; if **any** component is a reparse point (junction, symlink, mount point — `IO.FileAttributes.ReparsePoint`), **refuse**, log, and route to `_Quarantine`. This is stricter than prefix-matching and directly defends against the SCRUM-301 junction-traversal wipe (CLAUDE.md "mklink /J" warning). The filer itself never creates junctions.

---

## 6. Migration — staged, gated, reversible

Each phase emits a manifest (§6.1) + a generated `undo-<ts>.ps1`. **Phases 3–6 are propose-only on the first full run** (plan to manifest, no moves); execution is a second `--apply` pass from the *approved* manifest, run in batches.

| # | Phase | Risk | Gate |
|---|-------|------|------|
| 0 | **Full backup of `F:\Books`** to a second physical location via `robocopy /MIR /XJ /XJD /XJF` (exclude all junctions/symlinks) + a skipped-reparse-points manifest; verify file count + sample hashes; scaffold operational folders + `F:\Documents` + `F:\Library\Calibre`; add config block | none | backup + count verified |
| 1 | Inventory + sha256 + embedded-metadata extract + classify (rule→metadata→LLM) + dup-group detect → **emit full plan manifest** with deterministic `planned_calibre_key` (**no `calibredb add` against the real library**; an optional disposable staging library may aid dedup detection and is then discarded) — no moves | read-only | — |
| 2 | **Calibration gate:** run Phase 1 twice; compare **normalized** output (§6.2) for determinism; human review + spot-check; tune taxonomy/rules; re-run until green | none | **sign-off** |
| 3 | Extract **unambiguous** non-books → `F:\Documents`. (Potential book-fragments are NOT touched here — see §6.3) | low | propose→approve |
| 4 | Dedup collapse: filer selects canonical (records `canonical_reason`), others → `_Duplicates_Pending` | medium | propose→approve |
| 5 | **Fragment attribution** (exploded-EPUB, First-Folio, AA workbooks); only after attribution does confirmed debris → `_Trash_Pending`; reassembly candidates → `_Needs_Review` | medium | propose→approve |
| 6 | Apply: `calibredb add` survivors (assigns the real `calibre_id`, fills the manifest) → materialize **all formats** into shelves (§3), in **per-section batches** | high | propose→approve (batched) |
| 7 | Normalize 35 audiobooks → `Audio_Books\Author Last, First\Title (Year)\` with zero-padded chapters | low | propose→approve |
| 8 | Rewire automation (repo-wide literal-path audit, §9); run EbookAutomation test suite | low | tests green |
| 9 | **Reconciliation job** stood up; deploy enforcement (filer + fence + crons) — propose-only until ADR grant lands (§8) | low | — |

**Phase order rationale:** "shrink then sort" — pull non-books (Phase 3) and collapse duplicates (Phase 4) *before* the expensive materialize (Phase 6), so a duplicate can't be shelved into three sections and the reviewed manifest is the real one.

### 6.1 Manifest schema (CSV + JSON, one row per file)
`original_path, destination_path, sha256, size, planned_calibre_key, calibre_id, isbn, format, section, subcategory, author_sort, title, year, duplicate_group_id, canonical_reason, classification_confidence, classification_source {rule|metadata|llm}, taxonomy_version, tool_version, action {move|copy|hardlink|trash|quarantine|review|merge-format}, undo_action, review_required`.
Plus `_Migration_Manifests\shelf-index.json` mapping `shelf_path ↔ (calibre_id, format) ↔ sha256` (used by reconciliation, §6.4). `planned_calibre_key` (deterministic: ISBN → else normalized `author+title+year` → else sha256) is set in plan manifests; the real `calibre_id` is filled only on approved apply (Phase 6). `action: trash` routes to `_Trash_Pending`, never an inline hard-delete (§6.6); `merge-format` attaches a format-twin to an existing Calibre book instead of creating a new one (§6.4).

### 6.2 Determinism gate — timestamp hygiene
Byte-identical comparison runs against a **normalized canonical projection** of the manifest: generation timestamps, temp/run IDs are excluded; rows are sorted by a stable key (`original_path`); `taxonomy_version` + `tool_version` are treated as fixed inputs, not variable output. The human-facing manifest keeps real timestamps; only the normalized projection is compared. This prevents both false failures (timestamp noise) and false passes (nondeterministic row ordering hiding real drift).

### 6.3 Non-book boundaries & fragment-before-trash
- **Unambiguous non-books** (tax/admin/insurance/passport/boarding-pass/resumes/forms) → `F:\Documents` (Phase 3, never deleted).
- **arXiv-style papers** → shelve under **09 / Science & Academic Papers** by default; route to `_Needs_Review` only when a paper is actually a dataset, manual, or other non-library artifact (then → `F:\Documents` or trash per attribution). (Decision resolved, §12 #3.)
- **Fragments** (exploded-EPUB `.xhtml/.opf/.ncx/.css`/images, First-Folio pieces, AA workbook `-1..-N`) are **not** classified as junk in Phase 3. In Phase 5, **fragment attribution** runs first: determine whether the fragments are the only recoverable parts of a damaged book. Only confirmed-redundant debris (a whole copy exists) → `_Trash_Pending`; reassembly candidates → `_Needs_Review`. Nothing that could be a book's only surviving content is trashed before attribution.
- **Ambiguous anything** → `_Needs_Review`. Never silently shelved or deleted.

### 6.4 Calibre ↔ shelf reconciliation (ongoing job)
Calibre DB is the metadata source; the filer materializes the shelf from it. The reconciliation job (scheduled, and on-demand after Calibre edits):
1. For each Calibre book **format**: compute the **expected** shelf path from current metadata + `#genre` (one shelf file per `(book, format)`; all formats co-locate under the Author folder, sharing the base name with distinct extensions). If the materialized path differs (metadata changed), move the shelf entry to the new path; the stale path → `_Trash_Pending`.
2. Every shelf file must map to **exactly one** `(Calibre ID, format)` pair via `shelf-index.json`. Orphans (no Calibre book) → `_Needs_Review`.
3. **Integrity:** hardlink mode — verify link count == 2 and same file ID; copy mode — verify shelf hash == Calibre file hash. Broken/drifted → re-materialize from Calibre, or `_Quarantine` on repeated failure.
4. Calibre book deleted → its shelf entries → `_Trash_Pending`.

### 6.5 Source-vs-derivative rule (conversion outputs)
EbookAutomation conversion outputs (KFX, TTS MP3, intermediate `.txt`/balabolka artifacts) are **derivatives** of a source book already (or being) cataloged — not new books. The completion hook (§8 ⑤) passes the **source Calibre ID** (or source path) with the artifact, and the filer's `_Inbox` derivative check routes by kind:
- **KFX / alternate ebook format** → attached as a *format* to the source Calibre book (`merge-format`), materialized beside the source under the same Author/base name. Never a new book record.
- **Audiobook MP3** → placed under `Audio_Books\<source author>\<source title>\`, tagged `derivative` and linked to the source Calibre ID; not ingested as a text book.
- **Intermediate TTS `.txt` / balabolka artifacts** → not library items; not ingested.
A derivative arriving with **no source link** → `_Needs_Review` (never auto-promoted to a fresh source). This breaks the re-ingest loop: a derivative can never be re-classified as an independent source and re-converted.

### 6.6 Trashing vs purge
`_Trash_Pending` is a holding area, not deletion. Every migration/filer action only ever **trashes** (moves into `_Trash_Pending` with a manifest row + undo entry). **Permanent purge** is a *separate, manual, manifest-backed* operation (`Invoke-BookTrashPurge.ps1`) that lists everything older than the retention window (**30 days**), requires explicit human approval, and logs exactly what it deleted. It runs **on demand only** — never on a schedule, never inline with filing. Nothing in the automated path hard-deletes.

---

## 7. Hermes enforcement engine (ongoing)

Built on Hermes' actual capabilities (local Qwen brain, zero API cost; `terminal` over pwsh interop), following the established **agent-invokes-a-tested-wrapper** pattern (Karen model) — never raw `Move-Item`.

- **Trigger:** no-agent cron `0 3 * * *` → `book-inbox-sweep.sh` → `pwsh.exe -NoProfile -NonInteractive -File <Invoke-BookFileGuarded.ps1>`. Deterministic rules file the easy cases; ambiguous files escalate to an agent-mode cron where Qwen proposes `{section, subcategory, author, title, year, confidence}`.
- **Fence** (`books-authorization.json`, ClaudeInfra-owned, modeled on `qwen-authorization.json`): section/subcategory allowlist, hard exclusions (a passport app can never resolve to a shelf), confidence threshold, per-run cap, and the `F:\Books`-only path scope.
- **Guarded wrapper** `Invoke-BookFileGuarded.ps1` (EbookAutomation-owned book-domain logic): `[CmdletBinding(SupportsShouldProcess)]`, `-WhatIf`; **fail-safe** (any doubt → `_Needs_Review`, never a blind move — inverse of Karen's fail-open because a wrong move is destructive); enforces §5.3 (reparse-point rejection, sanitize, long-path); reuses `_sanitize_filename`/`_unique_path`; idempotent (already-placed = no-op); JSONL log; routes through `calibredb` for the ID; honors `materialize_mode`.
- **Autonomy gate:** auto-moving production files is *mutating*, outside current ADR-0043 grants (T0 Karen, T2 Qwen). Requires an explicit **fenced tier grant scoped to `F:\Books`** via a human-reviewed config PR in ClaudeInfra. Until it lands, the filer runs **propose-only** into `_Needs_Review` (also the ideal accuracy break-in period).
- **On-demand:** a `SOUL.md` "file my book inbox" known-request → Telegram trigger.
- **Report:** Discord (`Send-DiscordWebhook.ps1`) / Telegram digest — "filed N, M to review, K dup-skipped."
- **Caveat:** live Hermes cron/.env/SOUL.md state lives inside the `hermes-ubuntu` WSL distro; verify live state (`hermes cron list`) before building.

---

## 8. Workflows — in scope vs deferred

**In scope:** ① one-shot migration ② dedup pass ③ calibrated inbox auto-file (core enforce loop) ④ Calibre adoption + metadata enrichment ⑤ EbookAutomation conversion-output → `_Inbox` completion hook **carrying the source Calibre ID** (reuses the qbit-finished pattern EB-352 mirrors); derivatives attach to the source book per §6.5 — never re-ingested as new books ⑥ audiobook normalize ⑦ reconciliation job.
**Deferred:** Audiobookshelf / Calibre-Web servers; quarterly density-audit cron.

---

## 9. Automation rewiring (Phase 8) — authoritative literal-path audit

A repo-wide literal-path audit is part of Phase 8. Confirmed code touchpoints to repoint/exclude:

| File | Change |
|------|--------|
| `config\settings.json:189` | `BookFinder.output_root` → `F:\Books\_Inbox\BookFinder` |
| `tools\book_downloader.py:42` (`DEFAULT_OUTPUT_ROOT`) | default → `_Inbox\BookFinder`; prefer reading config |
| `module\EbookAutomation.psm1` (~L6955/L7093 BookFinder fallback) | fallback → `_Inbox\BookFinder` |
| `Scan-BooksFolder.ps1:14,37` | read shared config; add exclusion filter (skip `_`-prefixed, `Audio_Books`, `F:\Documents`) |
| `Invoke-TesseractKindleBatch.ps1:37` | same exclusion filter |
| `tools\scan-image-density.py:9` | usage-example reference only (default is `inbox`); update doc example |

**Shared config block** (extend `config\settings.json`): `library_root`, `audio_root`, `documents_root`, `operational_folders[]`, `scan_exclude[]`, `materialize_mode`. Exclusion rule = any top-level folder starting `_`, plus the explicit deny-list. Re-run the audit (grep `F:\Books`) as a Phase-8 gate to catch anything missed.

---

## 10. Ownership & Jira

**Repo ownership** (per the agreed split — book-domain logic near the ebook tooling; Hermes governance in ClaudeInfra):

| Repo | Owns |
|------|------|
| **EbookAutomation** (book-domain) | filer/classifier/migration tooling, `books-taxonomy.json` (classification vocabulary), Calibre integration, metadata extraction, manifest + undo engine, reconciliation job, the 5 automation touchpoints, conversion completion-hook |
| **ClaudeInfra** (Hermes control-plane) | cron registration, `SOUL.md` known-request, `books-authorization.json` fence, **ADR-0043 tier grant** |
| **Plex** (ingest source) | route public-domain downloader output to `_Inbox` |

**Jira:** one umbrella **epic** (tracks the cross-repo migration contract) with three child tickets:
- **EB-### (child):** book-domain implementation + migration.
- **INFRA-### (child):** Hermes scheduling, autonomy grant, fence config.
- **PLEX-### (child):** ingest repoint.

Each child gets its own ticket before implementation; code lands on worktree branches.

---

## 11. Dependencies & risks

**Dependencies:** Calibre desktop + `calibredb` CLI installed; `LongPathsEnabled=1`; same-volume `F:\Library\Calibre` and `F:\Books` (for hardlink mode); EbookAutomation metadata-extraction helper exposed to the filer; verified live Hermes state.

**Risks & guardrails**
- **Destructive move at 757-file scale** → Phase 0 full backup (`robocopy /XJ`, junctions excluded); trash-only with a separate manual purge (§6.6); fail-safe wrapper; `-WhatIf`; idempotent; propose-only first runs.
- **Junction/reparse traversal wipe** (SCRUM-301) → reparse-point rejection across full ancestry (§5.3); no junctions created; run from main tree, not a worktree junction.
- **Hardlink shared-attribute foot-gun** → copy-mode default; if hardlink, the §3.1 contract + link-count verification + reconciliation.
- **Classification accuracy unproven** → determinism gate + calibration sign-off before any live move; embedded-metadata extraction beyond filename.
- **Governance** → ADR-0043 fenced tier grant required before live auto-move; agent may not self-authorize.
- **Duplication cascade** → dedup (Phase 4) precedes materialize (Phase 6).
- **Fragment mis-filing** → fragment attribution before any trash (§6.3).
- **Two-scheme collision** (Plex flat Author/Title vs subject tree) → resolved: subject-first wins; Plex output funnels through `_Inbox` so the filer re-files it.
- **Derivative re-ingest loop** (KFX/TTS/audio re-classified as new source books) → source-vs-derivative rule (§6.5); derivatives attach to the source Calibre book, never re-enter as fresh sources.
- **Calibre ID nondeterminism in dry-runs** → plan manifests use a deterministic `planned_calibre_key`; `calibredb add` (and the real `calibre_id`) happen only on approved apply (§6.1, Phase 6).
- **Backup following a junction** → Phase 0 `robocopy /XJ /XJD /XJF` excludes reparse points and logs a skipped-reparse manifest.

---

## 12. Decisions — resolved at spec review
1. **Materialization mode:** ✅ **Copy mode** (`materialize_mode` toggle retained for opt-in hardlink). (§3)
2. **Umbrella epic board:** ✅ **EB** umbrella epic, with **INFRA** + **PLEX** children. (§10)
3. **arXiv papers:** ✅ default **09 / Science & Academic Papers**; only true non-library artifacts (dataset/manual/etc.) → `_Needs_Review` → `F:\Documents` or trash. (§6.3)
4. **`_Trash_Pending` retention:** ✅ **30 days**; purge is **manual + separately approved** at first, never scheduled (§6.6).
