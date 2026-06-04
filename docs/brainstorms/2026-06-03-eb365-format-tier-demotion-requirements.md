# EB-365 — Format-Tier Demotion (GREEN-minimal): Requirements & Design

**Ticket:** EB-365 (Story, under epic EB-354). **Follow-up to:** EB-355 Plan 5 (merged `f4c9367`).
**Date:** 2026-06-03. **Status:** pending user approval → planning.
**Scope class:** deterministic, no-LLM, read-only. Gates the (separate, later) file-moving actuator.

---

## 1. Context

`book_filer`'s read-only `-WhatIf` brain classifies a 680-file `F:\Books` corpus. After Plan 5
the last A/B run (`20260602-212244`) was **RED-with-1**: deterministic YES, auto-shelf 228 (≥224
floor), trash-safety 0 violations, but **1 confident wrong-shelf** in the 50-row spot-check —
spot-check **#32**, *Theological Dictionary of the New Testament*, auto-shelved to
*09 Technology, Science & Reference / Reference & Encyclopedic* instead of *03 Religion*.

The deterministic classifier ([`tools/book_filer/classify.py`](../../tools/book_filer/classify.py))
scores by keyword **hit-count** (`confidence = best_hits / total`), matched on word boundaries.

### 1.1 Verified root cause (characterized against the real artifact, not assumed)

Reading the prior run's operator-local full plan artifact (`plan-20260602-212244.json` — **not** part
of the committed durable subset at `9f3ccad`; see the EB-355 durability note — read-only, no gated
corpus scan), the **3** files auto-shelved into *Reference & Encyclopedic* decompose as summarized
below:

| # | Title | Matched keywords | conf | True home (latent) |
|---|---|---|---|---|
| 1 | *The Encyclopedia of Ancient Giants in North America* | `encyclopedia` | 1.0 | ~07 Fringe (no keyword) |
| 2 | *Encyclopedia of Chart Patterns* (Bulkowski) | `encyclopedia` | 1.0 | ~05 Finance (no keyword) |
| 3 | **#32** *Theological Dictionary of the New Testament* | `dictionary` (title+name) + **`publishing`** (filename boilerplate, e.g. "…Eerdmans Publishing…") | 0.667 | 03 Religion |

The mechanism is **not** "generic out-weighed specific." For #32 there is *no* competing Religion
signal at all: the keyword is `theology` but the title says `theologi**cal**` (word-boundary regex
correctly refuses the partial — the same rigor that killed Plan 5's `"eco"`⊂"second" substring bug),
and `testament` / `new testament` are not keywords anywhere. The lone **form word** `dictionary`
wins uncontested; `publishing` is publisher boilerplate leaking from the source filename, not a
subject signal.

**Generalizable bug class:** `dictionary` / `encyclopedia` / `handbook` / `atlas` describe a book's
*form*, not its *subject*. They live in the *Reference & Encyclopedic* subcategory, which sits under
a *subject* section (Technology/Science) — so any "Dictionary/Encyclopedia of <unknown subject>"
wrongly implies Technology. All 3 cases above are instances; #32 is the only one the spot-check
happened to sample, but #1 and #2 are latent mis-shelves of the same class.

---

## 2. Goal & non-goals

**Goal.** Close the #32-class confident mis-shelf deterministically, then re-run the read-only
`-WhatIf` (two-run A/B via `--compare-to`) to **strict GREEN**.

**GREEN gate (unchanged from Plan 5).** determinism (byte-identical `canonical-projection.txt`
across run A and B) ∧ `wrong_shelf == 0` (human spot-check) ∧ `auto_shelf_count(copy+hardlink) ≥ 224`
on the frozen corpus ∧ non-empty signer; **plus** the separate trash-safety invariant (every `trash`
row byte-identical sha256 + metadata anchor + `dup_group_id`, 0 violations).

**Non-goals (explicitly deferred — see §8 scope reconciliation).**
- LLM-assisted classification tail.
- Reducing the ~60% auto-`review` rate (406/680).
- Adding new subject keywords (`testament`, broadened `theolog*`, etc.) — declined as keyword
  treadmill (EB-353 lesson); a deterministic structural rule is preferred over per-book keywords.
- Any write to `F:\Books` (the actuator stays gated).

---

## 3. The rule (behavioral contract)

Introduce a **format keyword tier**: subject-agnostic form words. Initial set:
`{encyclopedia, dictionary, handbook, atlas}` (the current *Reference & Encyclopedic* keyword set).

Introduce a small **boilerplate / non-topical token set** for the demotion test. Initial set:
`{publishing}` (publisher boilerplate that leaks from source filenames; extends the existing
`_SOURCE_BOILERPLATE_PHRASES` concept to token granularity).

For a file, let `M` = the **union** of all keywords that match its boilerplate-cleaned filename
*or* its metadata title (name-hits ∪ title-hits). Define:

```
subject_evidence = M − format_keywords − boilerplate_tokens
```

**Demotion guard.** If `M ∩ format_keywords ≠ ∅` (at least one **form** word matched) **and**
`subject_evidence` is empty (everything that matched was form/boilerplate), route the file to
`review` with reason `"format-only: no subject evidence"`, never auto-shelf. The would-be `section` /
`subcategory` are retained on the row for audit. **Any file with ≥1 subject-tier match — or with no
form-word hit at all — classifies exactly as today** (zero behavior change → zero regression for that
majority).

The format-hit precondition matters: without it, a `publishing`-only book (`M = {publishing}`, which
is boilerplate, so `subject_evidence = {}`) would be wrongly demoted, contradicting the rule that
`publishing` stays a usable classifier keyword. Requiring a form word scopes the guard to exactly the
"Form-word of <no-subject>" bug class.

Worked cases:
- #32: `M = {dictionary, publishing}` → `M ∩ format = {dictionary} ≠ ∅`, `subject_evidence = {}`
  → **review** ✓ (`publishing` excluded from subject evidence — the correction that makes the rule fire).
- Encyclopedias #1/#2: `M = {encyclopedia}` → form hit, `subject_evidence = {}` → **review** ✓
- "Python … Handbook": `M = {python, handbook}` → `subject_evidence = {python}` → classify as today ✓
- `publishing`-only title (no form word): `M = {publishing}` → `M ∩ format = ∅` → **not** demoted;
  classifies as today (this is the §4.1 dual-use case — `publishing` stays a valid keyword) ✓
- A title matching no keyword: already `review` under existing logic — unaffected.

`publishing` remains a valid classifier keyword for genuine self-publishing books; the exclusion
applies **only** to the demotion guard's subject-evidence test, not to scoring, and the guard only
fires when a form word is also present.

---

## 4. Components & changes

### 4.1 Taxonomy ([`config/books-taxonomy.json`](../../config/books-taxonomy.json))
- Add top-level `"format_keywords": ["encyclopedia", "dictionary", "handbook", "atlas"]`
  (mirrors the existing `non_library_keywords` pattern — one auditable place).
- Add top-level `"boilerplate_keywords": ["publishing"]` (non-topical tokens for the guard).
- Bump `"version": 1 → 2` (recorded per-row as `taxonomy_version`; a rule change must be
  attributable across runs).
- The four form words **remain** in *Reference & Encyclopedic* — the format list is an **overlay
  flag, not a removal**, so a Reference shelf is still reachable when a section-09 subject co-occurs.

### 4.2 Taxonomy loader ([`taxonomy.py`](../../tools/book_filer/taxonomy.py))
- Parse `format_keywords` and `boilerplate_keywords` into `frozenset[str]` fields on `Taxonomy`
  (lowercased, normalized consistently with the index). Default to empty sets when absent
  (backward-compatible with a v1 file).

### 4.3 Classifier ([`classify.py`](../../tools/book_filer/classify.py))
- **Matched-keyword accounting (required).** `_score_text` (line ~62) currently returns only a
  `Counter[(section, sub)]`, which discards keyword identities. Add a helper (e.g.
  `_collect_matches`) — or extend `_score_text` — to also return the set of matched keywords, so the
  guard can compute `subject_evidence`. Counts and ranking are unchanged.
- Add `reason: str | None = None` to the `Classification` dataclass.
- Apply the demotion guard after scoring and the existing non-library / tie / threshold logic, as a
  final check before any `shelf` return. When it fires: `disposition="review"`,
  `reason="format-only: no subject evidence"`, `section`/`subcategory` retained, `confidence`
  carried through for the audit row.
- Boundary, title-primary, source-boilerplate-strip, and tie→review logic are otherwise untouched.

### 4.4 Scan / manifest ([`scan.py`](../../tools/book_filer/scan.py))
- The single call site (`classify_name`, ~line 413) keeps its signature.
- `_resolve_action`'s review branch (~line 562) currently always emits
  `"low-confidence/ambiguous classification"`. Change it to prefer the classification-supplied
  reason: `facts.cls.reason or "low-confidence/ambiguous classification"`, so the demotion reason
  reaches the manifest/spot-check for audit. (This is the one place the design touches scan.py;
  it is **not** a no-op — noted per review.)
- `taxonomy_version` bump propagates automatically into every row.

---

## 5. Determinism

No new nondeterminism is introduced: no LLM, no network, fixed frozensets, and scoring already uses
a deterministic `(-hits, section, sub)` sort (not `Counter.most_common`). The byte-identical A/B
projection gate is preserved by construction. `PYTHONHASHSEED=0` continues to apply.

---

## 6. Floor safety (validated, not assumed)

From the prior run's `plan.json`: only **3** files auto-shelved into *Reference & Encyclopedic*, and
all 3 demote under the corrected rule. Worst case **228 → 225 ≥ 224** — the floor holds even if every
Reference shelf demotes. Realistically the broader corpus may contain other format-only shelves
outside this subcategory; the gated A/B run (§7) is the authoritative floor measurement. A
**watch-item** for that run: confirm no legitimate Writing/Publishing shelf whose sole evidence is
`publishing` + a form word is demoted in a way that (combined) drops the floor below 224.

---

## 7. Testing & verification

### 7.1 Unit (TDD, written first — per Plans 3–5)
- **#32 regression (pinned):** `classify_name("…Theological Dictionary of the New Testament…",
  tax, title="Theological Dictionary of the New Testament")` → `disposition == "review"`,
  `reason == "format-only: no subject evidence"`.
- **Format-only siblings:** bare "Encyclopedia of X" / "Atlas of Y" (X/Y not keywords) → `review`.
- **No-regression — co-occurrence:** "Python … Handbook" → still `shelf` (has subject evidence).
- **No-regression — pure subject:** a handful of pure-subject titles classify identically to today.
- **Boilerplate exclusion:** a title with a form word whose only *other* match is `publishing`
  (e.g. `dictionary` + `publishing`) → `review` (guards the exact #32 correction).
- **Publishing-only (precondition guard):** a title whose only match is `publishing` (no form word)
  → classifies as today, **not** demoted — locks the `M ∩ format_keywords ≠ ∅` precondition and the
  §4.1 dual-use guarantee.
- **Taxonomy v2 load:** `format_keywords` / `boilerplate_keywords` parse into frozensets; a v1 file
  (no keys) still loads with empty sets.
- **Reason wiring:** a demoted row surfaces the format-only reason through `_resolve_action`.
- **Determinism:** existing two-run guard remains green.

### 7.2 Gated GREEN run (manual; requires explicit "frozen + go")
1. Unit suite green (`python -m pytest tests/`); `feature-manifest.json` re-verified.
2. On explicit **"frozen + go"**: read-only `-WhatIf` ×2 (A/B `--compare-to`) on the frozen 680-file
   corpus, `PYTHONHASHSEED=0`. **No `F:\Books` writes.**
3. Verify: determinism YES; `auto_shelf_count ≥ 224`; trash-safety 0 violations.
4. Regenerate the spot-check sheet; **human signs off** `wrong_shelf == 0` on the **new** sample.
5. GREEN → EB-365 done; open the separate actuator ticket (backup + clean GREEN + approval +
   ADR-0045 gate it). If a *new* mis-shelf surfaces in the fresh sample → triage it as a new finding
   (likely another format-class case or a genuinely new one); do not silently re-baseline.

---

## 8. Scope reconciliation with EB-365

EB-365 was filed as "LLM-assisted classification tail + keyword precedence → strict GREEN" and also
named review-rate reduction. This design narrows the **active** scope to a **deterministic,
GREEN-minimal sub-scope** (format-tier demotion) because:
- Closing #32 is the *only* thing the GREEN gate requires; review-rate reduction is a goal, not a
  gate condition, and is the riskier half (promoting `review`→`shelf` can introduce new wrong-shelves).
- The LLM tail's value is review-rate reduction, which is deferred.

**Action:** re-scope EB-365 to this deterministic sub-scope and **defer the LLM-assisted tail +
review-rate reduction to a follow-up ticket** (to be created, Relates EB-365). The actuator remains
gated behind EB-365 reaching strict GREEN.

---

## 9. References
- Compound: [`docs/solutions/eb355-book-filer-classification-metadata-accuracy-2026-06-02.md`](../solutions/eb355-book-filer-classification-metadata-accuracy-2026-06-02.md)
- Plan 5: [`docs/plans/2026-06-02-001-feat-eb355-plan5-classification-metadata-accuracy-plan.md`](../plans/2026-06-02-001-feat-eb355-plan5-classification-metadata-accuracy-plan.md)
- Prior runs (evidence committed `9f3ccad`): `data/batch_reports/book_filer_whatif/{20260602-182319,20260602-212244}/run-b/`
- Primitive follow-ups already filed: EB-359 (fragments folder-blind), EB-360 (reparse fail-open).
