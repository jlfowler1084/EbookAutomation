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
2. **Real quality finding (independent of grader)** — the KFX *does* have structural degradation: zero `<table>`, `<ul>`, `<ol>`, `<pre>`, or `<code>` elements in the 340 KB extracted HTML. Tables, bulleted lists, and code blocks were flattened to paragraph text during the original KFX production. Headings and text content are intact (93 `<h2>` + 185 `<h3>`).
3. **Root cause for the structural loss** — the current KFX was produced by an old Calibre version (`publisher="calibre 3.26.1"` embedded in KFX metadata). The installed Calibre is 9.7. The semantic-markup loss is consistent with older Calibre KFX profiles flattening tables/lists into paragraphs.
4. **Recommendation** — re-convert on Calibre 9.7 with `--output-profile kindle_pw3 --embed-all-fonts` and compare. This is a bounded experiment, not a refactor.
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

## Hypothesis matrix

| Hypothesis | Status | Evidence |
|---|---|---|
| H1 — Upstream extraction (pdfminer/pypdf/pymupdf) is losing structure before Calibre | Unlikely on its own | Source PDF has 106-entry outline and rich structure; textual content survives extraction; headings were preserved into HTML |
| H2 — Calibre 3.26.1 KFX output profile flattens tables/lists/code into paragraphs | **Likely** | HTML from current KFX has zero structural elements despite text survival; consistent with older Calibre KFX behavior |
| H3 — Claude-Sonnet grader is uniquely strict on technical content | **Likely** | 19-report trend shows Claude is an outlier; every Qwen grader passes this book; Claude's page-3 "only 'Contents' heading renders" finding coexists with 'Contents' appearing 22 times in the underlying HTML |
| H4 — Font embedding fails on monospace code | Not directly tested | `--embed-all-fonts` is active; no `<code>` markup means fonts couldn't have been applied even if embedded |
| H5 — VQA sample page selection hits uniquely-bad pages | Not strongly supported | Both A3B and A3B-cloud score the same 8-page sample much higher than Claude; same pages would produce similar scores if the pages were simply bad |

**Most likely combined cause:** H2 (old Calibre KFX profile flattened structural markup) × H3 (Claude is the only grader that penalizes the result hard enough to fail it).

## Recommendations

### R1 — Re-convert with Calibre 9.7 and measure
Bounded experiment. Drop the fresh source PDF into the pipeline and run full conversion on current tooling. Compare KFX-extracted HTML structural audit (this doc's method) between old and new output. Expected outcome: `<table>`, `<ul>`, `<ol>`, `<pre>` counts rise from zero. If they do, the book's VQA score across all graders should recover; if not, the loss is deeper than Calibre 3.26.1.

Open as a follow-up implementation ticket.

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
