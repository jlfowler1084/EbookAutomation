---
title: SCRUM-299 Structural widgets emitted as body content
type: solution
status: phase-1-diagnostic
date: 2026-04-22
origin_ticket: SCRUM-299
related_tickets: [SCRUM-290, SCRUM-292, SCRUM-298]
tags: [pipeline, extraction, running-headers, page-anchors, calibre, kfx, diagnostic]
---

# SCRUM-299 — Structural widgets emitted as body content

Phase 1 diagnostic. The ticket reports two visible artifacts in the Dionysius KFX output:

- **Variant A** — running-header text (`"Dionysius the Areopagite: On the Divine Names and the C.E. Rolt Mystical Theology."`) injected mid-paragraph in body prose.
- **Variant B** — small "document icon" widgets annotated with Roman/Arabic page numbers rendering visibly on 7 of 12 VQA pages.

The ticket asks: *which pipeline stage introduces them, and should the fix be at source or at render?* Per the project's regression rule, no code is modified in this phase.

## TL;DR

1. **Both variants are introduced in extraction/HTML generation inside [`tools/pdf_to_balabolka.py`](../../tools/pdf_to_balabolka.py) — fix-at-source is the correct layer for both.** Calibre is a passive conveyor, not the introduction point.
2. **Shared root pattern** — both artifacts are structural elements emitted into body flow without a semantic tag that tells downstream stages they are navigation/chrome rather than content. Variant A lacks an active filter; Variant B lacks `epub:type="pagebreak"`.
3. **Variant A is currently Dionysius-specific** but the class-of-bug is real. Dionysius's running header (82 chars, mixed case) slips through *three* separate filters because it sits 1 character over the 80-char cap on one filter and fails ALL-CAPS regex gates on the other two. Any future book with a long mixed-case running header will exhibit the same symptom.
4. **Variant B is codebase-wide, not book-specific.** Every book in the pipeline emits the same orphan `<a id="page_N"></a>` form (6,979 occurrences across 21 test HTMLs; zero `epub:type`/`pagebreak` references anywhere in the code). VQA only flagged it on Dionysius because of visual perception differences, not because other books are immune.
5. **Proposed fix direction** — A2 (format-agnostic frequency filter, page-aware) + B1 (EPUB 3 pagebreak semantic on the anchor). The Atomic Habits corpus entry serves as a built-in false-positive canary for A2.

## Evidence

### Pipeline layer map

Artifact introduction points, traced through the code:

| Artifact | Emitter | Site | Form |
|---|---|---|---|
| PAGE anchor (column path) | [`pdf_to_balabolka.py:6696`](../../tools/pdf_to_balabolka.py#L6696) | HTML generation | `<a id="page_{N}"></a>` |
| PAGE anchor (fallback path) | [`pdf_to_balabolka.py:7115`](../../tools/pdf_to_balabolka.py#L7115) | HTML generation | `<a id="page_{N}"></a>` |
| Running-header strip (Phase 0) | [`pdf_to_balabolka.py:3341–3402`](../../tools/pdf_to_balabolka.py#L3341) | Post-extraction | frequency-based, ALL-CAPS regex, `len < 80` gate |
| Running-header strip (Phase 0b) | [`pdf_to_balabolka.py:3404–3453`](../../tools/pdf_to_balabolka.py#L3404) | Post-extraction | merged-paragraph variant, ALL-CAPS gate |
| Running-header strip (column path) | [`pdf_to_balabolka.py:6574–6604`](../../tools/pdf_to_balabolka.py#L6574) | HTML generation | requires `_is_running_header_candidate` flag |

Grep confirms no semantic-pagebreak awareness anywhere in the module:

```
$ grep -c 'epub:type\|pagebreak\|pagelist\|page-list' tools/pdf_to_balabolka.py
0
```

### Variant A — why Dionysius slips through all three filters

The Dionysius running header, stripped of page number: `"Dionysius the Areopagite: On the Divine Names and the C.E. Rolt Mystical Theology."` — **82 characters, mixed case**.

| Filter | Gate | Why Dionysius slips through |
|---|---|---|
| Phase 0 (line 3363) | `len(line) > 80 or len(line) < 5 → skip` | 82 chars is 2 over the cap |
| Phase 0 (line 3351) | regex requires `[A-Z][A-Z\s\-:,\d\.]+` (ALL-CAPS) | mixed case — "the", "Areopagite", "Divine", "Names", "Mystical" are lowercase/title-case |
| Phase 0b (line 3433) | `caps_text == caps_text.upper()` | same ALL-CAPS constraint |
| Column path (line 6580) | requires `_is_running_header_candidate` flag from column extractor | Dionysius is single-column; flag never set |

Every current filter has an ALL-CAPS or ≤80-char envelope. Title-style mixed-case running headers that exceed 80 chars have no existing handler.

### Variant A — cross-corpus frequency scan

Top repeated `<p>` lines per corpus book (intermediate HTMLs on disk), computed by extracting all `<p>…</p>` bodies, stripping inner tags, and frequency-counting normalized text 5–200 chars:

| Book | Total `<p>` | Unique | Top repeat (`count × len chars, all-caps?`) | Is it a header? |
|---|---:|---:|---|---|
| Oil Kings | 3706 | 3675 | `5 × 21  no  FRUS 1969–76, VolE-4.` | No — endnote citation |
| Mexico | 1610 | 1602 | `3 × 19  no  Business Strategies` | No — sub-heading body |
| Atomic Habits | 2009 | 1963 | `4 × 85  no  1.1: Fill out the Habits Scorecard…` | No — repeated cheat-sheet item |
| Python in Easy Steps | 1915 | 1846 | `6 × 17  no  window.mainloop()` | No — code literal |
| **Dionysius** | **1312** | **1167** | **`145 × 82  no  Dionysius the Areopagite: On the Divine Names and the C.E. Rolt Mystical Theology.`** | **Yes** |

Dionysius's top-repeat rate (11% of all `<p>` tags) is an order of magnitude higher than any other book's top-repeat rate (≤0.3%). The 145 occurrences in a 148-page book track 1:1 with "header appears on nearly every page." No other current corpus book has a header-style repeat.

### Variant B — uniformity

```
$ grep -c '<a id="page_\d\+"></a>' output/kindle/
6,979 occurrences across 21 files, all books.
```

All 21 test HTMLs — including every corpus book with an intermediate on disk — use the identical orphan form. The anchor has no `epub:type`, no class, no text content. Calibre's EPUB/KFX conversion receives this as a bookmark-style named anchor. Kindle's KFX renderer surfaces orphan named anchors that lack `epub:type="pagebreak"` as the default page-list "document icon" widget.

### Why VQA flagged it on Dionysius but not earlier corpus runs

Hypothesis: the icon widget is emitted for every book, but the VLM treats it as expected chrome on pages with a clear chapter-start or heading above the margin anchor. On pages of pure body prose with no heading, the icon sits alone in the margin and the VLM surfaces it as a layout anomaly. Dionysius has long heading-less stretches (Section VI runs many pages without a chapter start), so the 7-of-12 flag rate is consistent with "always emitted, only noticed on heading-sparse pages." This is a hypothesis, not yet verified; see **Open questions** below.

## Layer introduction verdict

| Variant | Introduced at | Fix layer |
|---|---|---|
| A (running header) | Extraction — the three existing filters at `pdf_to_balabolka.py:3341 / 3404 / 6574` have envelopes that exclude long mixed-case headers | Fix at source |
| B (page-anchor icon) | HTML generation — the anchor emitter at `pdf_to_balabolka.py:6696 / 7115` uses a bare named anchor without `epub:type="pagebreak"` | Fix at source |

Neither fix belongs at the Calibre/KFX layer. Calibre faithfully passes through whatever HTML we give it.

## Proposed fix strategies

### Variant A — running-header filter

- **A1 (cheap, narrow) —** Widen Phase 0's envelope. Raise the 80-char cap to ~130 and add a mixed-case branch to the regex (e.g., `[A-Z][A-Za-z\s\-:,\d\.']{4,}`). Keep the ≥3-page frequency threshold. *Risk:* false positives on long repeated body lines (see Atomic Habits canary).
- **A2 (robust, format-agnostic) — RECOMMENDED.** Add a post-Phase-0 pass that is *format-agnostic*: for every `<p>` in the extracted stream, normalize and count occurrences grouped by PDF page number. If a normalized line appears on ≥N distinct pages with N = max(5, 10% of total pages) and length 10–200 chars, mark all-but-first as running-header and drop. This catches Dionysius (145 pages × one line) without needing ALL-CAPS or length gates. *Requires:* per-paragraph page-number provenance, which the pipeline already carries via `p.get('page_number')` in the column path — see `pdf_to_balabolka.py:6694`.
- **A3 (most robust, most code) —** Coordinate-based filter using PyMuPDF block bbox to detect "same text in same page-top region across ≥N pages." Rejected for Phase 1: too much surface area for a single-book symptom.

### Variant B — page-anchor semantic

- **B1 (targeted) — RECOMMENDED.** Change the emitter at [`pdf_to_balabolka.py:6696`](../../tools/pdf_to_balabolka.py#L6696) and [`:7115`](../../tools/pdf_to_balabolka.py#L7115) from `<a id="page_{N}"></a>` to the EPUB 3 semantic form: `<span epub:type="pagebreak" id="page_{N}" role="doc-pagebreak" title="{N}"></span>` (or `<a epub:type="pagebreak" …/>`). Calibre's EPUB pipeline recognizes `epub:type="pagebreak"` and routes the entry to KFX `page_list` metadata instead of inline body flow, which suppresses the icon widget on Kindle.
- **B2 (weak) —** CSS `a[id^="page_"] { display:none }`. Kindle strips most CSS; unreliable. Reject.
- **B3 (invasive) —** Remove inline anchors entirely and supply Calibre a `page-map.xml` at conversion time. High-risk; rejected.

### Integration note

A2 and B1 are independent and can ship together in one PR or as two tickets. They share no code.

## Validation plan (for the fix PR, not this phase)

Maps to the SCRUM-299 acceptance criteria:

1. **Root cause identified** — done in this document.
2. **Decision: source vs render** — source, for both variants. Documented.
3. **Dionysius re-run under VQA shows zero widget-bleed flags** — re-run `py -3.12 tools/visual_qa.py --input archive/C. E. Rolt - Dionysius….pdf --provider cloud --full` after the fix.
4. **At least one other corpus book passes the same check** — Atomic Habits is the strongest test: it has a legitimate 85-char repeating body line (`"1.1: Fill out the Habits Scorecard…"` × 4) that **must not** be false-positively stripped by the A2 filter. Passing criterion: A2 log shows 0 header-drops for Atomic Habits, and its VQA score does not regress. Python in Easy Steps is a secondary canary (has repeating code literals).
5. **Fixture for running-header-mid-body** — blocked on **SCRUM-298** (VQA batch truncation) per the ticket notes. The specific Dionysius page range (15–18) that captures the mid-paragraph injection cannot be VQA-asserted until SCRUM-298 is resolved. The fix itself does not require this; only the fixture does.

## Open questions

1. **Variant B cross-book visibility.** The hypothesis that icon widgets render on every book but go unflagged except on heading-sparse pages is unverified. Cheapest verification: render one page from Atomic Habits and one from Python via `ebook-convert … --pdf-page-numbers` and visually inspect the margins. If icons are present on those books' KFX too, B1's fix gives a uniform corpus-wide win; if not, there's a secondary factor (possibly NCX/toc.ncx metadata) that deserves investigation before B1 ships.
2. **A2 page-number provenance on non-column paths.** The column path carries `page_number` on each paragraph dict. Phase 0 operates on the flat `paragraphs` list and may lose per-paragraph page provenance. Before implementing A2, confirm page numbers are attached (or attachable) at the Phase 0 boundary across all three extraction paths (pdfminer / pypdf / PyMuPDF).

## Related

- [SCRUM-290](https://jlfowler1084.atlassian.net/browse/SCRUM-290) — A1/A2 pilot that provided the VQA baseline reports consulted here.
- [SCRUM-292](https://jlfowler1084.atlassian.net/browse/SCRUM-292) — Matcher 4 post-merge run that surfaced the Variant B icon-widget signal on Dionysius.
- [SCRUM-298](https://jlfowler1084.atlassian.net/browse/SCRUM-298) — VQA batch truncation; blocks the Variant A page-range fixture acceptance criterion only.
