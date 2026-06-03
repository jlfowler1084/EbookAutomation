---
title: "feat(EB-355): Plan 5 — classification + metadata accuracy (chase GREEN)"
type: feat
status: active
date: 2026-06-02
origin: docs/brainstorms/2026-06-02-eb355-plan5-classification-metadata-accuracy-requirements.md
---

# feat(EB-355): Plan 5 — Classification + Metadata Accuracy

## Overview
The real-corpus `-WhatIf` run (`data/batch_reports/book_filer_whatif/20260602-182319/run-b/`) passed determinism but failed calibration (RED, 4 wrong-shelf at confidence 1.0). This plan improves the **deterministic** classifier and sanitizes embedded metadata so a read-only re-run can reach the GREEN gate. **No file is moved** (the actuator stays a later, gated plan). Builds on the now-merged #188 gate-hardening (`spot_index` header + shelf/review vocabulary), so the re-run's verdict is trustworthy.

## Problem Frame
`tools/book_filer/classify.py::classify_name(name, taxonomy)` scores by **substring** match (`keyword in text`) on the **filename only** (`text = name.lower()`), with no word-boundary check and no use of the embedded title that `extract_metadata` already pulls. Two failure modes result, both observed in the RED run:
1. **Substring collisions at confidence 1.0** — e.g. the Philosophy keyword `"knowledge"` matches inside *"unac**knowledge**d"* → a single spurious hit → 1/1 = confidence 1.0 → confidently mis-shelved (see origin: the 4 wrong-shelf rows).
2. **Cryptic filenames out-score descriptive titles** — libgen/Anna's-Archive filenames carry junk tokens while the descriptive embedded title is ignored.

Separately, destinations use raw embedded `author`/`year`, so junk (`svejk, josef`; implausible years) reaches `destination_path` **and** the `ManifestRow` — an apply-time naming risk even when the section is right.

> **Research caveat (must verify in Unit 1):** against the *current* taxonomy, `creature`/`island`/`supernatural` are NOT keywords — so the brainstorm's "→ Fiction" attributions are not literally reproducible as keyword rows. The RED run nonetheless shelved those titles to Fiction/Writing/Philosophy at conf 1.0, which means the real mechanism is substring/filename spurious matches. **Unit 1 reproduces each of the 4 against `classify_name` to capture the exact offending token before any fix.** (see origin + research)

## Requirements Trace
- **R1** — Classification is title-aware: the embedded metadata title is fed into `classify_name` as a source-aware signal, with the filename retained as fallback/secondary evidence. (origin §Goals.1)
- **R2** — Substring collisions are eliminated (word-boundary matching), so a keyword cannot match inside a larger word. (origin §Goals.1)
- **R3** — Metadata quality: implausible years and fake-uploader author names are sanitized **at the source** (`extract_metadata`) so `destination_path` and `ManifestRow` agree. (origin §Goals.2)
- **R4** — Deterministic-only; the read-only `-WhatIf` re-run stays byte-reproducible (no LLM). (origin §Decisions)
- **R5 (GREEN gate)** — re-run yields: determinism ∧ `wrong_shelf == 0` ∧ `auto_shelf_count (copy+hardlink) >= 224` on the same frozen corpus ∧ non-empty signer; **and** the separate trash-safety-invariant gate holds. (origin §Success criteria)

## Scope Boundaries
- No `F:\Books` mutation — read-only scans only.
- No LLM classification (deterministic-only this pass).
- No taxonomy re-architecture — only targeted, corpus-validated keyword adjustments if Unit 1 proves a specific additive keyword is needed.

### Deferred to Separate Tasks
- **File-moving actuator** — later plan, gated behind a GREEN re-run.
- **LLM classification fallback** for the residual hard tail — deferred; the gap Unit 5 documents becomes its scope.
- **Primitive fixes EB-359 (fragments folder-blind) / EB-360 (reparse fail-open)** — tracked separately; `scan.py` already wraps them defensively.

## Context & Research

### Relevant Code and Patterns (source-verified)
- `tools/book_filer/classify.py` — `classify_name(name: str, taxonomy) -> Classification`; `text = name.lower()`; scoring loop `if keyword in text` (substring); returns `Classification(disposition, section, subcategory, confidence, source)`; disposition logic: non_library short-circuit → no-match review → tie/`confidence < confidence_threshold` (0.34) review (keeps best section) → else shelf. **Edit sites:** signature (add `title`), source-aware scored text, and `keyword in text` → boundary-aware phrase matching.
- `config/books-taxonomy.json` — 12 sections; keyword sets are raw substrings (e.g. `"war "`, `"knowledge"`). The only *verified* existing mis-map is `"knowledge"` (Logic & Epistemology) ⊂ "unacknowledged".
- `tools/book_filer/metadata.py` — `BookMetadata(title, author, year, isbn, series, series_index)`; `_GARBAGE_PLACEHOLDERS`, `_KNOWN_BAD_PDF_TOOLS`, `_clean_field`, `_year_from` (`\d{4}`, **unbounded**). **Edit site:** bound `_year_from`, add an author scrub mirroring `_clean_field`.
- `tools/book_filer/scan.py` — `_build_file_facts` calls `classify_name(path.name, taxonomy)` at the title-aware fix site (metadata already extracted one line above); `_destination_path` + the `ManifestRow` construction both read `meta.author/title/year` (sanitize at source to fix both); `_spot_disposition`/`_build_spot_check` (#188, copy/hardlink→shelf) and the `--compare-to`/`canonical-projection.txt` two-run flow are present and must stay green.
- `tools/book_filer/calibration.py` — `evaluate_calibration(...)`; wrong_shelf counts `disposition == "shelf" and not correct`.
- Test conventions — `tests/test_book_filer_classify.py` (module-level `TAX = load_taxonomy()`, assert on `.disposition/.section/.subcategory/.confidence`); `tests/test_book_filer_metadata.py` (`_make_epub`/`_make_pdf` artifacts); `tests/test_book_filer_scan.py` (`_make_real_epub` for filename-vs-title divergence, `run_scan` subprocess, `_load_rows`).

### Institutional Learnings (docs/solutions)
- **EB-353 (high):** adding a logically-sound classifier guardrail *regressed the canary* — every new rule is a new false-positive surface. **Validate against a fixed labeled set after EVERY rule change; revert regressions even if "correct."**
- **EB-353 (high):** a metric *asserted* deterministic was load-dependent. **Prove the re-run is deterministic (run twice, diff) before trusting the gate** — deterministic-only/no-LLM is what protects this.
- **SCRUM-282 (med-high):** `source_format`-style same-name/different-semantics field collisions are a known landmine. **Grep the whole repo before introducing any new metadata field name** (e.g. a "title-source" flag).
- **SCRUM-299 + render-check (med):** brittle thresholds (year bounds, char caps, blocklists) are the exact "fixed 1, broke 4" class. **Eyeball the `-WhatIf` output across the inventory before committing thresholds.**
- **Gap:** there are **no `book_filer` docs/solutions entries** (Plans 1-4 uncompounded) → Unit 6 compounds the first one.

## Key Technical Decisions
- **Word-boundary matching over taxonomy deletion.** The root cause is substring matching, not bad keywords. Fix `classify_name` to match on word boundaries (regex `\b`/token-set), which generalizes beyond the 4 known cases. Rationale: a per-keyword deletion game is the EB-353 false-positive treadmill; a matching-semantics fix is one change validated against the whole corpus.
- **Title-aware = source-aware blend, not blind concatenation.** Score the embedded title as primary evidence and the filename as secondary/fallback evidence. A plain `title + " " + filename"` string does **not** make title evidence "win" under the current hit-count confidence math; it can leave publisher/acquisition filename junk with equal weight. Rationale: many corpus files have no parseable metadata, so filename fallback must remain, but a metadata-rich title should not be drowned out by `libgen`/publisher/source boilerplate. If title and filename produce cross-section conflict, prefer `review` over a guessed shelf.
- **Keyword-collision cleanup includes source/boilerplate context.** Word-boundary matching fixes true substring bugs (`knowledge` inside `unacknowledged`), but it will not fix whole-word junk such as `publishing` in `Random House Publishing Group`. Unit 1 must capture those mechanisms explicitly; Units 2/3 may add narrow source-text cleanup or keyword constraints where characterization proves the issue.
- **Sanitize metadata at the source (`extract_metadata`/`metadata.py`), not in `_destination_path`.** Rationale: the analyst confirmed `meta.author/title/year` flow into BOTH the destination and the `ManifestRow` (and into `planned_calibre_key`); fixing at the source keeps all three consistent.
- **Deterministic-only.** No LLM; preserves the determinism gate that the whole calibration depends on.
- **Corpus-validated, not logic-validated.** After Units 2/3/4, re-run `-WhatIf` and treat the spot-check + the 4-case labeled set as the arbiter; revert any rule that regresses them.

## Open Questions

### Resolved During Planning
- **Matching mechanism:** word-boundary (regex `\b` token match) rather than naive substring. (Decision above.)
- **Title blend order:** source-aware title-primary scoring; filename remains secondary/fallback, not equal-weight blind concatenation.
- **Sanitization layer:** in `metadata.py` at extraction, not at destination.
- **No new schema field if avoidable:** sanitize values in place (no "title_source"/"sanitized" flag) to dodge the SCRUM-282 field-collision landmine; if a flag becomes necessary, grep the repo first.

### Deferred to Implementation
- **Exact offending token per mis-shelf** — discovered in Unit 1 (characterization), not assumed.
- **Year plausibility bounds** (lower ≈ 1450, upper ≈ current year + 1) — final values set after eyeballing the Unit 5 inventory output (brittle-threshold caution).
- **Fake-author detection rule** — curated handle blocklist (`svejk`, …) vs shape heuristics (single all-lowercase token, contains digits); choose the minimal rule that catches the observed cases without rejecting real authors; validate on the inventory.
- **Whether the auto-shelf floor (224) holds** after word-boundary matching routes more low-signal files to `review` — measured in Unit 5; if the floor breaks, that tension is reported (it may mean the deterministic ceiling is below the floor → documents the LLM-tail case).

## Implementation Units

- [ ] **Unit 1: Characterize the 4 mis-shelves (diagnose before editing)**

**Goal:** Reproduce each known wrong-shelf against `classify_name` and capture the EXACT offending token/mechanism, as characterization tests. Gate the fix on real evidence (project Regression-Prevention rule + calibration discipline).
**Requirements:** R1, R2 (evidence for).
**Dependencies:** none.
**Files:** Test: `tests/test_book_filer_classify.py`
**Approach:** For each of the 4 real input strings (the filenames from the RED run's spot-check rows 1/6/9/30 — When Genius Failed, Creature from Jekyll Island, Unacknowledged, The Unseen Realm), call `classify_name(<real filename>, TAX)` and record current `(disposition, section, confidence)` and the matching keyword. Confirm/deny each premise (e.g. prove `"knowledge"` ⊂ "unacknowledged" → Philosophy). Document any case that is actually `review` today (so the fix target is "stays review / becomes correct", not "stops being Fiction"). Treat these as characterization evidence: permanent post-fix tests should assert **correct-or-review**, not preserve the wrong behavior.
**Patterns to follow:** `test_book_filer_classify.py::test_marxism_primary_source_goes_to_politics`.
**Test scenarios:**
- Characterization: each of the 4 filenames → capture the *current* classification and the offending keyword/source text, with a comment naming the mechanism. These can start as temporary/xfail characterization assertions during Unit 1, but must be converted to permanent **correct-or-review** regressions by Units 2-3 rather than committed as tests that preserve wrong behavior.
**Verification:** Each of the 4 mechanisms is documented as a test; the offending token is named for each.

- [ ] **Unit 2: Word-boundary keyword matching in `classify_name`**

**Goal:** Eliminate substring collisions — a keyword matches only as a whole word/phrase, not inside a larger word.
**Requirements:** R2.
**Dependencies:** Unit 1.
**Files:** Modify: `tools/book_filer/classify.py`; Test: `tests/test_book_filer_classify.py`
**Approach:** Replace `keyword in text` with boundary-aware phrase matching. Avoid a naive `rf"\b{re.escape(kw)}\b"` implementation for raw taxonomy entries: some keywords contain punctuation, spaces, or intentional trailing whitespace (`"war "`), and `\b` after non-word characters can fail unexpectedly. Normalize keyword/text whitespace, trim taxonomy keywords before matching, and use custom alphanumeric boundaries such as `(?<![a-z0-9])... (?![a-z0-9])` or an equivalent token/phrase matcher. Preserve multi-word phrase keywords (`"federal reserve"`). Keep scoring/confidence/disposition semantics stable except where Unit 1 proves a source/keyword collision needs narrow cleanup. Sort target iteration and ranked tie-breaks explicitly so the implementation does not rely on set insertion order.
**Execution note:** Test-first — the Unit 1 characterization tests for substring cases (e.g. "unacknowledged") flip from Philosophy to not-Philosophy.
**Patterns to follow:** existing `classify_name` structure; `_NUMBERED_RE`-style precompiled regex in `fragments.py`.
**Test scenarios:**
- Happy path: "unacknowledged" no longer matches `"knowledge"` → not Philosophy (review or correct).
- Edge: a legitimate whole-word match still classifies (e.g. a real "knowledge"-titled epistemology book still → Philosophy).
- Edge: multi-word phrase keyword (`"federal reserve"`) still matches across the space.
- Regression: the entire existing `tests/test_book_filer_classify.py` suite stays green (no section flips for currently-correct cases).
**Verification:** Unit 1 substring-collision characterizations flip; existing classify suite green.

- [ ] **Unit 3: Title-aware classification (signature + call site)**

**Goal:** Score the descriptive embedded title as primary evidence, with filename fallback/secondary evidence, so metadata-rich files classify on real title text without letting filename junk dominate.
**Requirements:** R1.
**Dependencies:** Unit 2.
**Files:** Modify: `tools/book_filer/classify.py` (signature), `tools/book_filer/scan.py` (`_build_file_facts` call site); Test: `tests/test_book_filer_classify.py`, `tests/test_book_filer_scan.py`
**Approach:** Widen to `classify_name(name, taxonomy, title: str | None = None)`. Implement source-aware scoring rather than blind concatenation: classify title evidence first when present; use filename evidence as fallback/secondary support; if title and filename create a cross-section conflict, route to `review` unless Unit 1 establishes a narrow, deterministic cleanup that removes the filename boilerplate. Update `scan.py::_build_file_facts` to pass `meta.title`. Keep backward-compatible default (filename-only) so all existing callers/tests pass.
**Execution note:** Test-first — a `_make_real_epub` fixture whose filename is cryptic but whose embedded title is descriptive classifies via the title.
**Patterns to follow:** `_make_real_epub` in `tests/test_book_filer_scan.py` (filename-vs-title divergence); existing classify tests.
**Test scenarios:**
- Happy path (unit): `classify_name("xyz123.epub", TAX, title="A History of the Weimar Republic")` → History; `classify_name(same, TAX)` (no title) → review/unchanged.
- Integration (scan): a `_make_real_epub` with cryptic filename + descriptive title → `_load_rows` shows the correct `section` (filename-only would have mis-shelved/reviewed).
- Conflict path: title evidence points to one section and filename boilerplate points to another; result is correct section only if the boilerplate cleanup removes the conflict, otherwise `review` (never wrong shelf).
- Edge: empty/None title → exactly today's filename-only behavior (no regression).
- The 4 known cases (combined with Unit 2): each now classifies to the correct section OR routes to `review` — never the wrong shelf. (The R5 regression.)
**Verification:** The 4-case labeled set is correct-or-review; existing suites green.

- [ ] **Unit 4: Metadata-quality sanitization at the source**

**Goal:** Reject implausible years and fake-uploader author names in `extract_metadata` so junk never reaches `destination_path`, the `ManifestRow`, or `planned_calibre_key`.
**Requirements:** R3.
**Dependencies:** none (parallel to 2/3).
**Files:** Modify: `tools/book_filer/metadata.py`; Test: `tests/test_book_filer_metadata.py`
**Approach:** Bound `_year_from` to a plausible range (reject outside ≈[1450, current_year+1] → `None`). Add an author scrub (mirroring `_clean_field`) that nulls obvious non-author handles. Start with a minimal curated exact/blocklist rule for observed handles like `"svejk"` / `"svejk, josef"`; do **not** ship broad shape heuristics such as "single all-lowercase token" or "contains digits" unless Unit 5 corpus evidence proves they are needed and tests preserve plausible real authors. Apply both in `extract_metadata` so all downstream sites agree.
**Execution note:** Test-first; both directions (junk → None, real → preserved).
**Patterns to follow:** `_clean_field` / `_GARBAGE_PLACEHOLDERS` in `metadata.py`; metadata tests `test_pdf_literal_none_author_is_scrubbed`.
**Test scenarios:**
- Happy path: real author "Andrew Scott Cooper" + year 2011 preserved.
- Edge/junk: year `101`, `9999`, `0000` → `None`; author `"svejk, josef"` (and other observed handles) → `None`.
- Edge: real authors that superficially look odd are NOT over-rejected (guard against the brittle-threshold/SCRUM-299 failure mode) — include at least one lowercase/plural-name example the rule must keep.
- Regression: existing `metadata.py` junk-guard tests stay green.
**Verification:** Junk year/author nulled; real metadata preserved; existing metadata suite green.

- [ ] **Unit 5: Read-only re-run + calibration measurement (corpus validation)**

**Goal:** Re-run the two-run `-WhatIf` over the frozen corpus and produce a fresh verdict against the R5 GREEN gate; this is the corpus-level arbiter for Units 2-4.
**Requirements:** R4, R5.
**Dependencies:** Units 2, 3, 4.
**Files:** none (read-only execution + a results note under `data/batch_reports/book_filer_whatif/<stamp>/`).
**Approach:** From a clean checkout off updated `master`, run A then B (`--compare-to`, `PYTHONHASHSEED=0`) into `data/batch_reports/book_filer_whatif/<stamp>/{run-a,run-b}` (out-dir outside `F:\Books`). Compute: determinism (A==B), `auto_shelf_count(copy+hardlink)`, the trash-safety invariant (every trash byte-identical + anchor + dup_group_id, 0 violations), and build the spot-check sheet. Maintainer marks `correct?` + signs → `evaluate_calibration`. Compare auto-shelf count vs the 224 floor. **Caution (EB-353):** confirm determinism by the two-run diff before reading the gate.
**Execution note:** Read-only; requires a frozen `F:\Books` and the maintainer for spot-check marks + sign-off (irreducibly human). Per learnings, eyeball the inventory output before finalizing the Unit-4 thresholds.
**Test scenarios:** Test expectation: none — this is a read-only measurement run, not a code unit. (The behavior it exercises is covered by Units 1-4 unit/integration tests + the #188 gate tests.)
**Verification:** A fresh `calibration-verdict.json`: ideally GREEN (det ∧ wrong_shelf==0 ∧ auto_shelf>=224 ∧ signer) with trash-safety intact. If not GREEN while holding the floor, the residual mis-shelves are documented (titles + mechanism) as the LLM-tail scope, and the actuator stays gated.

- [ ] **Unit 6: Compound the first `book_filer` solution (close-out)**

**Goal:** Capture the classification/metadata-accuracy solution + the calibration methodology in `docs/solutions/` (none exist for `book_filer` yet).
**Requirements:** process (CE compound).
**Dependencies:** Unit 5.
**Files:** Create: `docs/solutions/<category>/eb355-book-filer-classification-metadata-accuracy-2026-06-02.md` (with frontmatter: module, tags, problem_type).
**Approach:** Document the substring-vs-word-boundary root cause, title-aware blend, source-level metadata sanitization, the work_key blast radius, and the corpus-validated-not-logic-validated discipline. Link the RED→(re-run) verdict delta.
**Test scenarios:** Test expectation: none — documentation.
**Verification:** A discoverable `docs/solutions/` entry exists for `book_filer`.

## System-Wide Impact
- **Interaction graph:** `classify_name` is called only from `scan.py::_build_file_facts`; signature change is backward-compatible (default `title=None`). `extract_metadata` feeds `_destination_path`, the `ManifestRow`, AND `identity.planned_calibre_key`.
- **Work_key / dedup blast radius (important):** sanitizing `author`/`year` changes `planned_calibre_key` (`meta:author|title|year`), which changes dedup grouping → potentially `trash`/`merge-format`/`review` decisions AND the canonical projection (determinism). **Unit 4 must include a test that dedup grouping + the trash-safety invariant + determinism remain sound when an author/year is sanitized** (e.g. two copies whose only differing field was a junk year must still group correctly).
- **Auto-shelf floor parity:** word-boundary matching will reclassify many files corpus-wide (not just the 4) — some currently-shelved low-signal files may drop to `review`, pressuring the 224 floor. This is the central success-bar tension, measured in Unit 5.
- **Determinism:** all changes are deterministic (regex/string ops, bounded ints); no new nondeterministic inputs. The two-run gate stays valid.
- **Unchanged invariants:** the #188 gate vocabulary (`_spot_disposition`, `_build_spot_check`, `evaluate_calibration`), the read-only guarantees (G1-G12), and `-WhatIf`-only (no actuator) are untouched and must stay green.

## Risks & Dependencies
| Risk | Mitigation |
|------|------------|
| New classification rule regresses currently-correct books (EB-353 treadmill) | Corpus-validated: re-run `-WhatIf` + the 4-case labeled set after each rule change; revert regressions even if logically sound |
| Metadata sanitization changes `work_key` → breaks dedup/trash-safety or determinism | Explicit Unit-4 test for dedup grouping + trash invariant + determinism under sanitized author/year |
| Brittle year/author thresholds over-reject real metadata ("fixed 1, broke 4") | Keep rules minimal + conservative (false-null degrades to filename); eyeball inventory output in Unit 5 before finalizing |
| Word-boundary matching drops auto-shelf below the 224 floor | Measured in Unit 5; if the deterministic ceiling < floor, report it as the documented LLM-tail case rather than weakening the gate |
| New metadata field-name collision (SCRUM-282) | Avoid new fields; sanitize in place. If a flag is unavoidable, grep `EbookAutomation.psm1`/`test_pipeline.py`/`pattern_db.py`/baselines first |

## Sources & References
- **Origin document:** [docs/brainstorms/2026-06-02-eb355-plan5-classification-metadata-accuracy-requirements.md](docs/brainstorms/2026-06-02-eb355-plan5-classification-metadata-accuracy-requirements.md)
- RED run artifact: `data/batch_reports/book_filer_whatif/20260602-182319/run-b/calibration-verdict.json`
- Gate-hardening: PR #188 (`f72b894`) — `_spot_disposition`/`spot_index`
- Learnings: `docs/solutions/eb353-vqa-grader-code-false-positive-2026-06-02.md`, `docs/solutions/scrum-282-vqa-baseline-methodology.md`, `docs/solutions/scrum-299-structural-widgets-as-body-content.md`
- Related: EB-359 (fragments folder-blind), EB-360 (reparse fail-open) — wrapped defensively in `scan.py`
