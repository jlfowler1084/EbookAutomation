---
title: Render intermediate outputs before choosing the layer to fix a pipeline bug
date: 2026-04-22
category: best-practices
module: ebook-automation
problem_type: best_practice
component: development_workflow
severity: medium
applies_when:
  - A bug report points at visible output (VQA flag, user screenshot, baseline miss) but doesn't say which pipeline stage introduced it
  - A plan or ticket proposes a fix at one layer without evidence the artifact was introduced there
  - Two apparently-different symptoms get grouped as "same class-of-bug" without per-stage isolation
tags: [pipeline, diagnostic, regression, workflow, opus-sonnet-handoff]
---

# Render intermediate outputs before choosing the layer to fix a pipeline bug

## Context

Pipeline bugs can surface as visual artifacts in the final output (KFX, rendered PDF, VQA PNG) without any indication of which stage introduced them. Extraction, HTML generation, Calibre conversion, and source-PDF rendering all feed into the same pixel. If the ticket or plan assumes a specific layer is responsible without verifying it, the fix will either miss the real bug or touch the wrong code — sometimes both.

[SCRUM-299](https://jlfowler1084.atlassian.net/browse/SCRUM-299) is the canonical example. The ticket reported two variants framed as one "class-of-bug":

1. Running-header text appearing mid-paragraph in KFX body.
2. Anchor-icon widgets with page numbers visible in KFX margins.

Phase 1 diagnostic assumed both came from our pipeline's HTML emission and proposed two code changes (A2 frequency filter + B1 anchor-semantic change). Phase 2 render check — performed **before any code touch** — refuted the root-cause assignment for Variant B entirely and downgraded Variant A's severity. B1 was dropped; A2 was the whole fix.

## Guidance

Before implementing a plan to fix a pipeline bug, render the intermediate artifact each pipeline stage produces and grep the artifact for the reported symptom. Only start coding once you have located the introduction layer — or confirmed the bug is not in your pipeline at all.

Concrete sequence for this project's PDF extraction pipeline:

1. **Check whether the report exercised your pipeline.** Trace the run command in the ticket back to code. For VQA runs: `tools/visual_qa.py:663` — when the `--input` path has a `.pdf` suffix, Calibre is skipped entirely and Poppler rasterizes the source PDF directly (`capture_pipeline = "pdf-direct"`). Any artifact visible on the VQA PNGs from a PDF input is a property of the source PDF, not your pipeline.
2. **Render the source.** `pdftoppm -r 150 -f <page> -l <page> -png <source.pdf> <out_prefix>`. If the artifact is visible on the source PNG, it was baked in by the publisher's toolchain (e.g., XEP RenderX embeds "Index of Pages of the Print Edition" widgets on each page).
3. **Grep your extracted HTML.** `output/kindle/<BookName>_test_*.html` is cheap to re-grep. Classify each occurrence of the offending string as standalone `<p>`, glued to start/end of a paragraph, or truly mid-paragraph. Different classifications point at different fix layers.
4. **Render a control book's KFX.** For each cross-corpus hypothesis, convert one clean-book KFX to PDF via `ebook-convert <book>.kfx out.pdf` and extract a few mid-chapter pages. If the claimed "uniform across corpus" artifact isn't on the control book, the hypothesis is wrong.
5. **Only then open the editor.**

## Why This Matters

Wild goose chases in regression-sensitive code are the #1 time sink for this project (per `CLAUDE.md` § Regression Prevention). Phase 1 of SCRUM-299 proposed changing the `<a id="page_N"></a>` anchor emitter to use `epub:type="pagebreak"` — a cross-corpus change that would have touched every book's KFX output, forced a baseline re-capture, and not solved the reported symptom. The render check found the artifact in the source PDF in about 90 seconds of actual work, saving days of implementation, regression, and rollback.

The render-check also uncovered a separate class-of-bug (raw HTML anchor markup visible in Atomic Habits end-matter, tracked as [SCRUM-301](https://jlfowler1084.atlassian.net/browse/SCRUM-301)) that would have stayed hidden until a user reported it. The cost of doing the check is one bash session; the return includes bugs you didn't know you had.

## When to Apply

- Before implementing any `ce:plan` that proposes a fix at a specific pipeline stage. If the plan's "root-cause assignment" section is based on code reading alone — no render evidence — run the render check first.
- When a ticket or VQA report shows visual artifacts without per-stage attribution.
- When two symptoms are grouped as "same class-of-bug" — verify per-stage introduction points separately before accepting the grouping.
- When an Opus-planning session is about to hand off to a Sonnet-execution session. Adding render evidence to the handoff prompt tightens the Sonnet session's task and shrinks its own context budget (Sonnet spent ~10 minutes on Phase 1 audit + Phase 3 implementation on this ticket — the plan was tight enough to keep the execution under a single session).

## Examples

### SCRUM-299 Phase 2 render check — what the evidence looked like

**Variant B disproof (three parallel observations, ~3 minutes of work):**

```bash
# Observation 1: visual_qa.py bypass for PDF input
grep -n 'input_ext.*pdf\|skip.*convert' tools/visual_qa.py
# → tools/visual_qa.py:663: if input_ext == ".pdf": skip Calibre

# Observation 2: Source PDF renders the icons directly
pdftoppm -r 150 -f 20 -l 22 -png "archive/C. E. Rolt - Dionysius..." /tmp/out
# → small rectangles with "16", "18" in left margin of /tmp/out-020.png

# Observation 3: Clean book doesn't exhibit the artifact
ebook-convert "output/kindle/Atomic Habits...kfx" /tmp/atomic.pdf
pdftoppm -r 150 -f 46 -l 48 -png /tmp/atomic.pdf /tmp/atomic_mid
# → margins clean on /tmp/atomic_mid-046.png (no icons, no widgets)
```

Three observations from three different angles all pointing the same way: Variant B is a source-PDF artifact from XEP RenderX, not our pipeline. B1 ruled out.

**Variant A downgrade (one Python classification, ~1 minute):**

```python
# Count how the offending string appears in our extracted HTML
re.findall(r'<p[^>]*>\s*<HEADER>\s*</p>', text)                 # → 145 standalone
re.findall(r'<p[^>]*>[^<]+?<HEADER>[^<]+?</p>', text)           # → 0 mid-paragraph
re.findall(r'<p[^>]*>\s*<HEADER>\s+[A-Za-z][^<]+?</p>', text)   # → 0 glued-start
re.findall(r'<p[^>]*>[^<]+?\s+<HEADER>\s*</p>', text)           # → 0 glued-end
```

All 145 occurrences are clean standalone `<p>` tags. The "cutting through prose mid-paragraph" symptom in the original user screenshot was a source-PDF rendering anomaly, not an extraction reordering bug. A2's scope shrinks from "rebuild the extractor" to "extend the existing pre-scan's reach."

### Counter-example — what skipping the render check costs

Without Phase 2, the implementation session would have landed B1 (anchor-semantic change):

- Touches every book's KFX output → baseline re-capture forced.
- Does not fix the reported Dionysius symptom (source-PDF artifact).
- Still needs A2 afterwards anyway.
- Three days of work → one failed rollout → back to square one.

The render check cost ~15 minutes of bash and prevented all of that.

## Related

- [docs/solutions/scrum-299-structural-widgets-as-body-content.md](../scrum-299-structural-widgets-as-body-content.md) — Phase 1 + Phase 2 diagnostic (Phase 2 section supersedes Phase 1 root-cause).
- [docs/plans/2026-04-22-001-fix-scrum-299-running-header-a2-filter-plan.md](../../plans/2026-04-22-001-fix-scrum-299-running-header-a2-filter-plan.md) — CE plan derived from the Phase 2 evidence.
- [prompts/SCRUM-299-running-header-a2-filter.md](../../../prompts/SCRUM-299-running-header-a2-filter.md) — Sonnet handoff prompt.
- [SCRUM-299](https://jlfowler1084.atlassian.net/browse/SCRUM-299) — shipped via PR #10 (merge commit `6948fae`).
- [SCRUM-301](https://jlfowler1084.atlassian.net/browse/SCRUM-301) — separate class-of-bug uncovered by the render check (end-matter raw HTML).
- [SCRUM-303](https://jlfowler1084.atlassian.net/browse/SCRUM-303) — baseline drift discovered during SCRUM-299 Phase 4.
- `CLAUDE.md` § Regression Prevention — the rule this practice operationalizes ("analyze current behavior across ALL test books first. Do NOT edit code until you've reported the diagnosis").
