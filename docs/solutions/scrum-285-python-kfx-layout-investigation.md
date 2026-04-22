---
title: SCRUM-285 Python in Easy Steps KFX layout investigation
type: solution
status: compound
date: 2026-04-22
origin_ticket: SCRUM-285
related_tickets: [SCRUM-281, SCRUM-282, SCRUM-283, SCRUM-274, SCRUM-290]
tags: [vqa, pipeline-output, kfx, calibre, diagnostic, grader-bias]
---

# SCRUM-285 — Python in Easy Steps KFX layout investigation

Phase 1 diagnostic. The ticket framed the low VQA score (~58) as a pipeline-output problem ("why does Python render so poorly through the current Calibre → KFX → PDF chain"). Phase 1 evidence flips the premise: the low score is **Claude-Sonnet-specific** and the current KFX **was produced by Calibre 3.26.1, not the installed Calibre 9.7**. Both of those shift the investigation's center of gravity.

## TL;DR

1. **Premise challenge** — SCRUM-285 cites cross-grader convergence (|Δ|=1.9 between Claude and Qwen-A3B, both ~58). This is not reproducible from the 19 archived VQA reports for this book. Mean Qwen-family score is ~86 across local, cloud A3B, and cloud Max. Mean Claude-Sonnet score is ~60. The real delta is ~26 points, not 1.9. Every non-Claude grader currently passes this book.
2. **Real quality finding (independent of grader)** — the KFX *does* have structural degradation: zero `<table>`, `<ul>`, `<ol>`, `<pre>`, or `<code>` elements in the 340 KB extracted HTML. Tables, bulleted lists, and code blocks were flattened to paragraph text. Headings and text content are intact (93 `<h2>` + 185 `<h3>`).
3. **Root cause** — **extraction-side, not Calibre-side.** Phase 2 re-converted the PDF on the current pipeline (Calibre 9.7, pdfminer) and the structural loss reproduces identically. The `publisher="calibre 3.26.1"` string in KFX metadata is inherited from the source PDF's own metadata and is **not** a reliable signal of the conversion tool. `pdfminer` — the default extraction path on this pipeline — flattens multi-cell table rows into single paragraphs (observed: `<p>** Exponent</p>` in place of a table row).
4. **Recommendation** — pilot a table-aware extraction path (PyMuPDF `find_tables`, or camelot/tabula) for technical books and compare structural preservation vs. the pdfminer baseline. This is a bounded experiment with a clear success metric (table count in extracted HTML > 0).
5. **Secondary recommendation** — investigate Claude-Sonnet's unique strictness on technical books. Either Claude is correctly seeing what other graders miss (grader-floor argument) or Claude is mis-weighting structural failures on technical content (grader-bias argument). SCRUM-283's methodology already treats Claude as the oracle; this book is a test case where the oracle may be miscalibrated.

## Evidence

### VQA score trend (19 historical reports)

| Grader family | Model | Report count | Min | Max | Mean | Pass? |
|---|---|---|---|---|---|---|
| Claude | `claude-sonnet-4-6` | 2 | 59 | 60 | 59.5 | FAIL |
| Qwen local | `qwen3.5-35b-a3b-fp8` | 11 | 70 | 100 | 86.5 | PASS |
| Qwen cloud A3B | `qwen/qwen3-vl-30b-a3b` | 3 (+1 auth fail) | 77 | 96 | 87.7 | PASS |
| Qwen cloud Max | `qwen/qwen-vl-max` | 1 | 94 | 94 | 94 | PASS |

Source: all `data/**/Python in easy steps*_visual_qa_report.json` files present on 2026-04-22. The ticket-cited `data/scrum281_corpus_smoke_hybrid/` directory does not exist in the working tree; the nearest replacement is `data/scrum290_a1_a2_pilot/a1/` which scored **90** on cloud A3B.

No grader within the Qwen family scores this book below 70. Only Claude Sonnet puts it below pass threshold.

### KFX-extracted HTML structural audit

Method: `ebook-convert` on `output/kindle/Python in easy steps, 2nd Edition - Mike McGrath.kfx` → HTMLZ → `index.html` (340,455 chars).

| Element | Count | Expectation for technical book | Verdict |
|---|---|---|---|
| `<h1>` | 0 | 1 (title) | collapsed — chapters start at h2 |
| `<h2>` | 93 | ~chapter count | consistent with book outline |
| `<h3>` | 185 | ~subsection count | consistent |
| `<h4>` | 0 | some expected | collapsed |
| `<table>` | **0** | dozens (operator tables, type tables, method tables) | **structural loss** |
| `<ul>` | **0** | many (bullet tutorials are the book's signature) | **structural loss** |
| `<ol>` | **0** | many (step-by-step instructions) | **structural loss** |
| `<pre>` | **0** | dozens (Python code blocks) | **structural loss** |
| `<code>` | **0** | inline code throughout | **structural loss** |
| anchor targets | 0 | 50+ (106-entry source outline) | **navigation loss** |

Text content survives: 'operator precedence' appears twice, 'Exponent' appears six times, 'Contents' appears 22 times. The information is in the file; the *markup* is not.

### Source PDF sanity check

`C:\Users\Joe\Downloads\[In easy steps] Mike McGrath - Python in easy steps (2018, In Easy Steps Limited) - libgen.li.pdf`:

- 297 pages (KFX rendered to 198; Kindle reflow is expected)
- Valid embedded outline with **106 entries**, clean chapter numbering (`1 Getting started`, `2 Performing operations`, …)
- Metadata title matches: "Python in easy steps, 2nd Edition"

The source has the structure the KFX lacks. The loss happened in or after extraction/conversion, not in the source.

### Calibre version drift

The current KFX metadata reports `publisher="calibre 3.26.1 [https://calibre-ebook.com]"`. The installed Calibre is **9.7** (`calibre 9.7, Windows-11-10.0.26200-SP0`). The production KFX pipeline has been rebuilt many times since 3.26.1 shipped; KFX table/list/code handling specifically has been an area of ongoing improvement.

The KFX in `output/kindle/` is dated `Mar 24 2026`. The file predates SCRUM-274's pipeline work and has not been re-converted since.

## Hypothesis matrix (post-Phase-2)

| Hypothesis | Status | Evidence |
|---|---|---|
| H1 — Upstream extraction (pdfminer) flattens tables/lists/code into paragraphs before Calibre | **Confirmed** | Phase 2 re-conversion on Calibre 9.7 + pdfminer produces identical structural loss (0 tables, 0 lists, 0 pre/code); extracted HTML shows `<p>** Exponent</p>` where a table row should be |
| H2 — Calibre 3.26.1 KFX output profile flattens structural markup | **Refuted** | Both old KFX (pre-Phase-2) and new KFX (Calibre 9.7) have identical zero counts for table/list/code elements; `publisher="calibre 3.26.1"` string is sourced from PDF metadata, not conversion tool |
| H3 — Claude-Sonnet grader is uniquely strict on technical content | **Likely** | 19-report trend shows Claude is an outlier by ~26 points; every Qwen grader passes this book; Claude's page-3 "only 'Contents' heading renders" finding coexists with 'Contents' appearing 22 times in the underlying HTML |
| H4 — Font embedding fails on monospace code | Not directly tested, likely moot | `--embed-all-fonts` is active; no `<code>` markup from extraction means fonts have no semantic hook to attach to regardless |
| H5 — VQA sample page selection hits uniquely-bad pages | Not supported | Both A3B-local and A3B-cloud score the same 8-page sample much higher than Claude; same pages would produce similar scores if they were simply bad |

**Confirmed combined cause:** H1 (pdfminer flattens tables into `<p>` sequences at extraction time) × H3 (Claude is the only grader that penalizes the result hard enough to fail it).

## Recommendations

### R1 — ~~Re-convert with Calibre 9.7 and measure~~ (REFUTED by Phase 2)
Executed. Re-conversion on Calibre 9.7 with pdfminer extraction produces identical structural loss (0 tables, 0 lists, 0 pre/code in KFX-extracted HTML). The Calibre-version hypothesis is not supported. See Phase 2 section.

### R1b — Pilot a table-aware extraction path for technical books
Replacement for R1. The root cause is `pdfminer` flattening tabular text into paragraph sequences. Pilot options:

1. **PyMuPDF `page.find_tables()`** — already a dependency (`PyMuPDF column-aware` is extraction path #3). Used today for multi-column layouts; extend to table detection on technical books and emit `<table>`/`<tr>`/`<td>` during HTML generation.
2. **camelot-py / tabula-py** — purpose-built table extractors. Heavier dependency footprint; better accuracy on bordered tables.
3. **Post-extraction heuristic reconstruction** — detect `<p>` sequences where content matches `<short-token> <word>` at consistent positions and rewrite as `<table>`. Cheap, imperfect, language-agnostic.

Success metric for the pilot: re-extracted HTML has `<table>` count > 0 on this book, and the operator precedence section renders as a structured table in the subsequent KFX.

Open as a follow-up implementation ticket. Scope one extraction path per ticket, not all three at once.

### R2 — Claude-Sonnet grader calibration on technical books
Claude is the SCRUM-283 oracle but is an outlier on this book by ~26 points vs. the Qwen family. Two possible readings:

- Claude is correctly strict about semantic-markup loss that Qwen underweights.
- Claude is over-penalizing VQA-render artifacts (e.g. a TOC page that renders empty in the VQA capture step even though the underlying HTML has TOC entries).

SCRUM-284 ("detect DocVQA-shaped failures beyond fingerprint coverage") is the closest tracking ticket; this finding should be linked there as a concrete repro case. Either reframes or extends SCRUM-284's scope.

### R3 — Treat ticket-cited convergence claims as evidence, not premise
The SCRUM-285 premise (`|Δ|=1.9 between Claude and Qwen-A3B, both ~58`) does not reproduce from archived reports. Either the underlying `scrum281_corpus_smoke_hybrid` report set was excluded from git (likely — the directory is gitignored per the data-dir policy) or the ticket was filed against a specific config not reflected in the archived reports. Future VQA tickets that assert convergence claims should quote the exact report path so premises are verifiable.

See also the memory note: *"Plan data-dir git-tracking check"* — before designing around a ticketed premise, check whether its supporting artifacts are git-tracked.

## What is not in scope for Phase 1

- Re-running the full pipeline on the fresh source PDF (produces the comparison data for R1 but is a separate unit of work).
- Per-page visual comparison of KFX-rendered PDF vs. source PDF to identify exact pages where structure collapses.
- Investigation of the other 5 books in the regression corpus. The ticket scopes to Python specifically; generalization across technical books is explicitly a non-goal.

## Next-step decision point

1. **If re-conversion on Calibre 9.7 recovers structure** → R1 is the fix; SCRUM-285 closes with a note to re-baseline VQA after re-conversion; optionally open a follow-up to audit all 6 books for Calibre-version drift in their KFX output.
2. **If re-conversion does not recover structure** → the loss is upstream (our extraction engine); re-open a deeper investigation with pdfminer/pypdf/pymupdf diagnostics on the raw PDF.
3. **In either case** → R2 (Claude-grader calibration) is a separate concern worth filing distinct from the book-quality issue.

## Phase 2 — Re-conversion experiment (2026-04-22)

### Method

1. Backed up existing KFX (`/tmp/scrum285/python_calibre_3.26.1.kfx`, 940 KB, Mar 24 2026).
2. Copied source PDF from `C:\Users\Joe\Downloads\...\Python in easy steps...pdf` to `inbox/Python in easy steps, 2nd Edition - Mike McGrath.pdf`.
3. Ran `Convert-ToKindle -InputFile ... -UsePdfminer` via the EbookAutomation module on Calibre 9.7.
4. Re-extracted the new KFX via `ebook-convert` → HTMLZ → `index.html` using the same method as Phase 1.

### Pipeline log highlights

- Text extraction: 15.1 s (pdfminer), 331 KB clean HTML
- Rule-based fixes applied: 755 whitespace, 214 heading, 4 orphan-fragment
- Calibre conversion: 27.1 s (`--output-profile kindle_pw3 --embed-all-fonts`, `--level1-toc //h:h2`)
- 193 images extracted from PDF (vs 0 in old KFX — pipeline has improved image handling since Mar 24)
- New KFX: 7.9 MB (vs 940 KB old — 8× increase driven by 193 embedded page images)

### Structural audit — side by side

| Element | Old KFX (Calibre 3.26.1 `publisher` tag) | New KFX (Calibre 9.7, pdfminer) | Delta |
|---|---|---|---|
| HTML size | 340 KB | 371 KB | +9% |
| `<h2>` | 93 | 93 | 0 |
| `<h3>` | 185 | 121 | -64 (re-classification) |
| `<table>` | **0** | **0** | no change |
| `<ul>`/`<ol>`/`<li>` | **0** | **0** | no change |
| `<pre>`/`<code>` | **0** | **0** | no change |
| `<img>` | 0 | 193 | +193 (images preserved) |

### Smoking gun — operator precedence table

In both old and new KFX, the extracted HTML contains this sequence:

```html
<p class="class_sn1">// Floor division</p>
<p class="class_sn1">** Exponent</p>
<p class="class_sn1">The operators for addition, subtraction, multiplication...</p>
```

Each row of the source PDF's operator table (`**` column 1, `Exponent` column 2) has been concatenated into a single paragraph string and emitted as `<p>`. This is pdfminer's default behavior: it extracts positioned text boxes and emits them in reading order without table-row awareness. Neither Calibre version creates or destroys the table structure — it is never emitted by the extraction stage.

### Refuted hypothesis

The `publisher="calibre 3.26.1"` string embedded in the old KFX's metadata does not indicate the conversion tool. It is passed through from the source PDF's own metadata (the PDF was DRM-stripped with calibre 3.26.1 long before it reached this pipeline). Both the old KFX and the new KFX carry the same publisher tag despite being produced by different Calibre versions.

### Conclusion for SCRUM-285

- The VQA-measured "layout degradation" is the downstream effect of pdfminer extraction flattening tables (and likely code blocks / bullet lists by the same mechanism).
- Calibre is *not* the layer that loses structure, so profile-tuning Calibre will not improve the output.
- The fix lives in the extraction stage. See R1b.
- SCRUM-285 can close as diagnosed: confirmed root cause (extraction-side flattening), recommended path forward (pilot table-aware extraction for technical books), and surfaced a secondary concern (R2 — Claude-grader outlier behavior on this corpus).

### Follow-up tickets to open

1. **R1b implementation** — evaluate PyMuPDF `find_tables()` on Python in Easy Steps; gate on whether extracted HTML has `<table>` count > 0.
2. **R2 investigation** — link to SCRUM-284 (DocVQA-shaped failures). Concrete repro case: Python in Easy Steps with ~26-point Claude-vs-Qwen split. Either confirms Claude's strictness is correct (and we need to act on it across the corpus) or surfaces Claude-specific VQA-render artifacts that need filtering.
