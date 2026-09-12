# EB-355 `-WhatIf` Read-Only Scan Driver — Build Plan

> **Provenance:** synthesized by the `design-whatif-scanner` adversarial design workflow (7 agents,
> all claims verified against live source + `config/settings.json` + `config/books-taxonomy.json`),
> then resolved by maintainer decisions (2026-06-02). This is the authoritative build spec.
>
> **GATE:** This produces a READ-ONLY `-WhatIf` migration manifest. It performs **NO** move/rename/
> delete/copy of anything under `F:\Books`. The actuator is Plan 5 and stays fenced. Do NOT run on the
> real library until the build passes the §4 TDD suite, the §2 read-only proof checklist is verified,
> and the maintainer gives an explicit go.

## Build verification (2026-06-02)
Built TDD via the `build-whatif-scanner` workflow (1 implementer + 3 read-only auditors + synthesis). Verdict: **GO (read-only)**. Adversarial verification caught one real defect (**M1**) that one auditor had marked PASS — the dedup `trash` guard used `has_any_metadata` (keeper-exists) instead of the correctly-computed `has_metadata_in_group`, so a zero-metadata sha-dup would be `trash` not `review`; fixed + regression-tested. Also fixed **N1** (a tautological `[M]` fragment test → real assertion), **F2** (`--out-dir`/`--root` now `.resolve()`d in `main`), **N2** (docstring). **F1** (`manifest.py write_manifest` non-atomic) documented as a known low deviation (output under `out_dir`, `_COMPLETE` sentinel makes partial state detectable). Final: scan suite **27 passed**, full `book_filer` **104**, full `tests/` **1026 passed / 4 skipped / 0 failures**; read-only grep shows only the 3 spec-permitted `os.replace` (atomic tmp→final under `out_dir`).

## Resolved decisions (maintainer, 2026-06-02)
- **D1 — Output location:** `data/batch_reports/book_filer_whatif/<stamp>/` (worktree-EXEMPT per EB-181, so no PR friction for an exploratory artifact). MUST still be outside the scan root (it is).
- **D2 — Corpus freeze:** maintainer freezes `F:\Books` during the run; two live runs in fresh subprocesses + a count + sum-of-sizes guard that aborts on drift.
- **D3 — `.txt` excluded** for the first real run. `BOOK_EXTS = {".epub", ".pdf", ".mobi", ".azw3", ".azw"}` (NO `.txt` — avoids inflating review-rate with TTS artifacts; revisit later).
- **D4 — Primitives wrapped, not edited:** `scan.py` defensively wraps `fragments.py` (per-directory calls) and `reparse.py` (`\\?\` long-path + fail-CLOSED). Proper primitive fixes tracked in **EB-359** (fragments folder-blind) and **EB-360** (reparse fail-open).
- **Defaults:** `min_spot_check=50` (~60% shelf / 25% review / 15% non_library); `materialize_mode` from config (`copy`); undo artifact ships as inert commented `*.ps1.txt`; `PYTHONHASHSEED=0` pinned.

---

## 1. Scanner spec

**Create:** `tools/book_filer/scan.py` + `tests/book_filer/test_scan.py` (tests written FIRST).
**Reuse verbatim (no edits):** `manifest.py`, `dedup.py`, `fragments.py`, `identity.py`, `classify.py`, `metadata.py`, `pathsafe.py`, `reparse.py`, `config.py`, `taxonomy.py`, `calibration.py`.

### 1.1 Module constants
```python
TOOL_VERSION = "0.4.0"
BOOK_EXTS = {".epub", ".pdf", ".mobi", ".azw3", ".azw"}        # D3: .txt excluded
FRAGMENT_EXTS = {".xhtml", ".opf", ".ncx", ".css", ".jpg", ".jpeg", ".png", ".gif"}
_HASH_CHUNK = 1 << 20
# NO hardcoded operational-folder list — derive from config (config-derived skip, below).
_MUTATOR_RE = re.compile(r"(?i)\b(Move-Item|Remove-Item|Copy-Item|New-Item|mklink|"
                         r"Set-Content|Out-File|del|rmdir|rd)\b")   # G6 banned-content
```

### 1.2 Enumeration (`_iter_book_files`) — junction-safe, config-derived
Explicit `os.scandir` stack DFS. **No** `os.walk(followlinks=True)`, no `rglob`/`glob` descent. Rules:
1. **Reparse prune (G4):** before descending a dir, `has_reparse_in_ancestry(d)` → skip+log; AND per-child `entry.is_symlink()` or `_is_reparse_point(Path(entry.path))` before queuing a subdir. Build `os.lstat`/`open` targets with a `\\?\` extended-length prefix near MAX_PATH. **Any `OSError`/`AttributeError` from the reparse check → do NOT descend (fail-CLOSED).** (Wraps EB-360.)
2. **Skip set from config ONLY:** `{f.lower() for f in config.operational_folders}` (auto-includes `_inbox`, `_duplicates_pending`); `scan_exclude` matched by **resolved full path component** (resolve `library_root / name`, prune that exact subtree) — correctly excludes `F:\Books\Audio_Books` without over-matching `Audio_Books_Backup`.
3. Skip hidden/system (leading `.`, Windows hidden/system attr).
4. Skip the resolved `out_dir` subtree defensively.
5. **Skip zero-byte files** (`os.stat(p).st_size == 0`) IN THE LOOP — record a skipped-note, do NOT emit a book row (prevents the empty-file `sha:e3b0c442…` collision reaching dedup).
6. Collect into a flat list, then `sorted()` the **flat list** (scandir is unordered). Apply `--limit` after sort.
7. Fragment-ext files collected into a sibling `fragment_paths` list (no book pipeline).

### 1.3 Per-file pipeline (`_build_file_facts`) — never raises into the filer
`fmt = suffix.lower().lstrip(".")`; `sha,size = _hash_file(path)` (streamed `'rb'`, 1-MiB chunks; `OSError` → error row with `sha=""`, `work_key=str(path)` (unique), `action="review"`); `meta = extract_metadata(path)` (all-None for `.mobi/.azw*`); `cls = classify_name(name, taxonomy)` (wrapped defensively); `planned_key = planned_calibre_key(meta, sha)`; `work_key = planned_key`. `has_metadata = bool(meta.title and meta.author)`.

### 1.4 Manifest assembly (`build_manifest_rows`) — determinism-pinned
- Build `FileInfo(path, sha256, format, size, has_metadata, work_key)`; `plan_dedup` → path→`Member`.
- `duplicate_group_id` = **content-derived** `dup:<sha1(work_key).hexdigest()[:12]>` for multi-member groups; `None` for singletons (NOT a walk-order counter).
- `detect_fragment_sets` called **once per parent directory** (group candidate paths by `PureWindowsPath(p).parent`), verdicts merged (wraps EB-359).
- One `ManifestRow` per book file via `_resolve_action` (§1.5); then `rows.sort(key=lambda r: r.original_path)`.
- **`original_path` normalized** `str(Path(p).resolve())`, one separator form. Assert no two rows share `original_path`.
- **`taxonomy_version`** read from taxonomy JSON top-level `version` (live = 1); CLI `--taxonomy-version` overrides only if absent. Never a silent hardcoded `1`.
- `main` asserts `os.environ.get("PYTHONHASHSEED") == "0"`; the calibration driver sets it for both subprocess runs.

### 1.5 `_resolve_action` precedence (safety-first)
| Condition (in order) | action | review_required | canonical_reason |
|---|---|---|---|
| `facts.error is not None` | `review` | True | error string |
| `len(dest) > config.max_path_length` | `quarantine` | True | "destination exceeds max_path_length" |
| source OR destination reparse-in-ancestry | `quarantine` | True | "reparse point in source/destination (SCRUM-301)" |
| fragment verdict present | `review` | True | fragment reason |
| dedup `trash` AND ≥1 group member `has_metadata` | `trash` | False | member reason |
| dedup `trash` AND NO member `has_metadata` (sha-only) | `review` | True | "sha-only duplicate, no metadata anchor — review" |
| dedup `review` | `review` | True | member reason |
| `cls.disposition=="non_library"` | `review` | True | "non-library file" |
| `cls.disposition=="review"` | `review` | True | "low-confidence/ambiguous classification" |
| dedup `merge-format` | `merge-format` | False | member reason |
| `cls.disposition=="shelf"` | `config.materialize_mode` (`copy`) | False | §1.6 disambiguator |

`trash` means "would route to `_Trash_Pending`" — **never a delete**. Every non-empty `destination_path` must resolve under `config.library_root` AND pass reparse checks; else `quarantine`.

### 1.6 `destination_path` — content-derived, NO live-FS `unique_path` in dry-run
`-WhatIf` shelves nothing, so `pathsafe.unique_path` (keys off `dest.exists()`) is non-deterministic and would clobber colliding rows. **Never call it in dry-run.** Disambiguate from a stable content key: `isbn:`→`[ISBN <digits>]`, `meta:`→`""`, `sha:`→`[sha <8>]`; if two distinct-sha books still map to one slot, append each file's own `[sha <8>]`. `shelf-index.json` (dict keyed on `destination_path`) gets one entry per row, no clobber.

### 1.7 Output (under `<out-dir>` = `data/batch_reports/book_filer_whatif/<stamp>/`, atomic)
`plan-<stamp>.{csv,json,md}` (via `write_manifest`); `shelf-index.json`; `<stamp>-undo.ps1.txt` (commented/inert, G6); `determinism-report.md` + `determinism-diff.json`; `spot-check-sheet.{csv,md}`; `scan-summary.md`; `calibration-verdict.json`. Each artifact written `*.tmp`→`os.replace`. `_COMPLETE` sentinel written LAST. Refuse to overwrite an existing complete manifest for the same stamp unless `--force`. Out-dir default anchored via `Path(__file__).resolve().parents[N]` to repo root — never CWD.

### 1.8 CLI
`scan.py --root <dir> --out-dir <dir> --stamp <str> [--limit N] [--force] [--taxonomy-version N]`. `-WhatIf` is the ONLY mode; there is NO apply path in this module.

---

## 2. Read-only guarantees

### 2.1 Baked-in guards (all MUST ship)
- **G1** `_assert_output_outside_scan(scan, out)` runs FIRST (before any scandir): reject out inside scan, scan inside out (both directions, case-insensitive on resolved `.parts`), and reparse-in-scan-root-ancestry. Raises `UnsafeScanError(RuntimeError)`. (Single unified guard — no weaker inline check elsewhere.)
- **G2** every content open is `open(path, "rb", buffering=1<<20)` — never a write/append/plus mode on a scan path.
- **G3** ZERO occurrences targeting the scan root of: `os.rename/replace/remove/unlink/rmdir/removedirs/truncate/symlink/link/chmod/utime`, `shutil.move/copy*/rmtree`, `Path.unlink/rmdir/rename/replace/write_*/touch/symlink_to/hardlink_to`, `subprocess/os.system/os.popen`, `ctypes/win32file`. Only allowed writes: `out_dir.mkdir` + writes under `out_dir` (G1-gated) + `os.replace` for tmp→final.
- **G4** walk never follows links (scandir stack, `follow_symlinks=False`, reparse-checked, `\\?\`, fail-closed on OSError).
- **G5** per-file/per-dir `PermissionError`/`OSError`/`FileNotFoundError` → log+skip or error row; only `UnsafeScanError` is fatal.
- **G6** undo lines inert: before writing the undo artifact, assert every non-blank line starts with `#` and reject any uncommented `_MUTATOR_RE` match. Write as `*.ps1.txt`. (Banned-CONTENT, not just banned-call.)
- **G7** destination reparse + `library_root` containment on every non-empty `destination_path`.
- **G8** skip set derived ONLY from `config.operational_folders + scan_exclude`, lowercased, path-component matched.
- **G9** out-dir default anchored to repo root, never CWD-relative.
- **G10** atomic per-file writes (`*.tmp`→`os.replace`) + `_COMPLETE` sentinel last.
- **G11** zero-byte excluded from book rows; sha-only dedup `trash` (no metadata anchor) downgraded to `review`.
- **G12** `destination_path` / any `unique_path`/`compute_shelf_path` return is only `str()`-ified or `.exists()`-probed under a reparse guard — never passed to `open`/`mkdir`/`write_*`.

### 2.2 Read-only proof checklist (reviewer runs against the built module; any FAIL = do NOT run on F:\Books)
C1 no banned mutators in source · C2 no shell-out to movers/deleters · C3 every scan-path `open` is `"rb"`; writes only under (O) G1-gated · C4 no `write_*`/`mkdir` targets a scan path · C5 G1 runs first, both-directions+reparse · C6 walk doesn't follow links · C7 reparse wired (descent + scan-root + OSError fail-closed + long-path) · C8 metadata read-only/total · C9 `destination_path` never opened · C10 `unique_path` NOT called in dry-run · C11 `calibre_id is None` on every row · C12 per-item errors caught · C13 determinism (stamp injected, projection drops `calibre_id`+sorts, `PYTHONHASHSEED=0`) · C14 out-dir genuinely outside `F:\Books` · C15 no apply/actuation present · C16 generated `*.ps1.txt` content inert · C17 zero-byte excluded + sha-only trash downgraded · C18 calibration-harness validity (twice on same snapshot → identical projection; empty dir → 0 rows, 0 writes under root).

Reviewer grep one-liner (C1/C2/C16):
```powershell
Select-String -Path .\tools\book_filer\scan.py -Pattern 'os\.(rename|replace|remove|unlink|rmdir|removedirs|truncate|symlink|link|chmod|utime)|shutil\.(move|copy|copyfile|copytree|rmtree)|\.(unlink|rmdir|rename|replace|write_bytes|touch|symlink_to|hardlink_to)\(|subprocess|os\.system|os\.popen|ctypes|win32file'
```

---

## 3. Determinism + calibration flow
- **AUTO:** record corpus count + sum-of-sizes guard; scan run A → `proj_A = canonical_projection(rows_A)`; scan run B in a **fresh subprocess** → `proj_B` (real re-execution, not a double-call on one list); compare → `determinism-report.md` + `determinism-diff.json`; build stratified `spot-check-sheet.csv` + `scan-summary.md`.
- **HUMAN (irreducible):** maintainer marks `correct?` for every sampled row (legend: "mark `n` only if the disposition is wrong; a book sent to review is never wrong; a real book sent to non_library or shelved to the wrong section IS wrong"), spot-opens 2–3 files, then — only if deterministic ∧ zero wrong-shelf — supplies a non-empty `signed_off_by`.
- **Verdict:** `evaluate_calibration(projection_a, projection_b, spot_check, signed_off_by, min_spot_check=50)` → `calibration-verdict.json`. GREEN ⇔ deterministic ∧ `wrong_shelf_count==0` ∧ `len>=50` ∧ non-whitespace sign-off. RED → print `verdict.reason` verbatim, STOP, diagnose, fix, re-run Phase 1.
- **Sample sheet:** columns `# | disposition | section/subcategory | confidence | filename | dest-tail | correct? (blank) | note`; stratified deterministically (sort each stratum by `sha256`, take first N; never unseeded random); `trash`/`merge-format`/fragment mapped to `review` for spot-check purposes. Human marks land in a SEPARATE `spot-check-results.csv` so the blank template stays reproducible.

---

## 4. TDD test list (`tests/book_filer/test_scan.py`, write FIRST). [M] = mandatory.
1. **[M]** `test_trash_only_on_truly_identical_content` — every `trash` row shares exact sha256 with another member of its `duplicate_group_id`, and a kept row with that sha exists.
2. **[M]** `test_zero_byte_files_never_trashed` — ≥3 distinct 0-byte files → none emitted as book rows (or if surfaced, `review`, never `trash`).
3. **[M]** `test_fragment_set_does_not_span_two_folders` — same stem, 3 different parent dirs → no FragmentVerdict spans >1 parent. + `test_numbered_fragments_in_one_folder_still_detected` (no regression).
4. **[M]** `test_canonical_projection_byte_identical_across_two_runs` — run `run_scan` twice in fresh subprocesses → byte-identical projection. + `test_no_duplicate_original_path_rows` + `test_original_path_separator_normalized`.
5. **[M]** `test_immutability_snapshot_with_non_descended_junction` — tmp tree (.pdf/.epub/.mobi + nested dirs + a real junction); capture `{path:(size,mtime_ns,sha256)}` + listing before; `run_scan(out_dir=sibling outside tmp)`; assert every source file + listing unchanged, junction never descended (logged SKIP), then delete the out-dir and assert the junction TARGET survives. + dangling-junction variant + `test_unreadable_file_does_not_abort`.
6. `test_out_dir_inside_root_refused` — out inside root / ==root / root inside out / reparse-in-scan-root each raise `UnsafeScanError`; zero files written on refusal.
7. `test_undo_artifact_is_inert` — generated `*.ps1.txt`: every non-blank line starts `#`, no uncommented mutator.
8. `test_destination_never_materialized` — shelf rows under a fake tmp `library_root`; none of those dest paths exist; no section/author folders created.
9. `test_operational_and_audio_books_excluded` (real config: seed `_Duplicates_Pending\x.pdf`, `_Inbox\y.pdf`, `Audio_Books\z.mp3`) + `test_skip_match_is_case_insensitive` + `test_scan_exclude_no_substring_overmatch` (`Audio_Books_Backup` NOT pruned).
10. `test_distinct_books_same_shelf_path_get_distinct_destinations` + `test_shelf_index_one_entry_per_row`.
11. `test_over_length_destination_quarantined`.
12. `test_taxonomy_version_read_from_file` (== JSON `version`, not hardcoded).
13. `test_classify_deterministic_across_hashseeds` (or `main` refuses to run without `PYTHONHASHSEED=0`).
14. `test_duplicate_group_id_stable_across_runs` + `test_singletons_have_null_group_id`.
15. `test_empty_dir_yields_zero_rows_clean_exit` + `test_size_guard_aborts_on_count_or_size_change`.
16. `test_banned_content_grep_of_generated_undo` (self-test extends the C1/C2 grep to generated output).

**Acceptance:** all of the above green; full `tests/ -k book_filer` suite green (no regression to the 77 existing); the §2.2 checklist + grep one-liner pass.

---

## 5. ManifestRow field sourcing (gaps + stopgaps)
`original_path` (normalized resolve) · `sha256` (`_hash_file`; `""` on error) · `size` (`os.stat`; zero-byte excluded) · `calibre_id` = `None` always · `format` (suffix) · `author_sort` = `_author_sort()` heuristic **(flagged: not Calibre-grade; Plan-5 re-derives)** · `title` = `meta.title or Path(p).stem` **(flagged: stem crude)** · `duplicate_group_id` = content-derived `dup:<sha1(work_key)[:12]>` · `canonical_reason` = dedup reason else key-derived `[ISBN…]`/`[sha…]`/`""` · `classification_source` = `"rule"` or `"metadata"` (never `"llm"`) · `taxonomy_version` = JSON `version` · `tool_version` = `"0.4.0"` · `action`/`review_required` = `_resolve_action` (§1.5) · `undo_action` = commented no-op (`# would restore: …`), G6-asserted inert.

---

## 6. Build → run sequence
1. Build `scan.py` + `test_scan.py` TDD (synthetic fixtures + tmp junctions ONLY; never touches `F:\Books`).
2. Verify: §4 suite green + full book_filer suite green + §2.2 checklist/grep pass. Commit on `feat/EB-355-whatif-scan`.
3. **Maintainer go** → run on real (frozen) `F:\Books`: run A + run B (fresh subprocesses) → manifest + determinism report + scan-summary + spot-check sheet.
4. Maintainer marks the spot-check sheet + signs off → `evaluate_calibration` → GREEN/RED verdict. GREEN anchors the Plan 5 actuator design.
