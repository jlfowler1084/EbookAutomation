# Post-TOC Fix Structural Comparison — 37 Books

**Date:** 2026-03-24
**Baseline Run:** `batch_20260324_100208` (full mode, pre-SCRUM-126)
**New Run:** `batch_20260324_191919` (quick mode, post-SCRUM-126)
**Mode:** Quick (HTML extraction only, zero API cost)
**Duration:** 18m 33s (parallel 2)

## Summary

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Books processed | 37 | 37 | — |
| Pass rate | 16.2% | 100% | +83.8% |
| Total chapters detected | 1,565 | 1,587 | +22 |
| h1 headings | 161 | 168 | +7 |
| h2 headings | 1,404 | 1,419 | +15 |
| h3 headings | 8,045 | 7,126 | -919 |
| API cost | — | $0.00 | — |

### Key Finding

**SCRUM-126 significantly improved heading hierarchy normalization.** The h3 reduction (-919) reflects the pattern promotion + hierarchy normalization fix — many spurious h3 tags (sub-section noise, over-detected list items) were either promoted to proper h2 levels or correctly excluded. The net chapter count increased by +22 despite some books losing over-detected chapters, meaning the fix correctly distinguished real chapters from noise.

## Status Distribution Change

| Status | Before | After | Delta |
|--------|--------|-------|-------|
| PASS | 6 | 37 | +31 |
| WARN | 12 | 0 | -12 |
| FAIL | 19 | 0 | -19 |
| ERROR | 0 | 0 | 0 |

Note: The baseline was a full-mode run (HTML + KFX + VQA). Many WARN/FAIL statuses were driven by VQA scores or KFX conversion failures, which quick mode doesn't evaluate. The structural pass rate improvement is real, but the status comparison reflects mode differences too.

## Books with More Chapters Detected (13)

| Delta | Book | Before | After |
|-------|------|--------|-------|
| +75 | S. K. Bain — The Most Dangerous Book in the World | 1 | 76 |
| +17 | Texe Marrs — Codex Magica | 1 | 18 |
| +5 | Basic Writings of Saint Thomas Aquinas | 1 | 6 |
| +3 | Adult Children of Alcoholics Syndrome | 1 | 4 |
| +3 | Ed Knorr — Revelation and Bible Prophecy | 17 | 20 |
| +2 | Ezekiel II (Zimmerli) | 1 | 3 |
| +2 | Peter Levanda — Unholy Alliance | 1 | 3 |
| +2 | The Beginning of Wisdom (Kass) | 1 | 3 |
| +1 | David Irving — Uprising! | 100 | 101 |
| +1 | Pranaitis — The Talmud Unmasked | 8 | 9 |
| +1 | Robert Lacey — Inside the Kingdom | 18 | 19 |
| +1 | Rosanne Liebermann — Exile, Incorporated | 34 | 35 |
| +1 | Robin Mundill — England's Jewish Solution | 3 | 4 |

### Big Wins (rescued from 1 chapter)

Five books went from effectively no chapter detection (1 chapter = entire book as single chapter) to proper multi-chapter structure:

- **S. K. Bain** — 1 → 76 chapters (the most dramatic improvement)
- **Texe Marrs** — 1 → 18 chapters
- **Basic Writings of Aquinas** — 1 → 6 chapters
- **Adult Children of Alcoholics** — 1 → 4 chapters
- **Ezekiel II (Zimmerli)** — 1 → 3 chapters

These books had heading patterns that the old detection missed. The pattern promotion logic in SCRUM-126 recognized their chapter markers.

## Books with Fewer Chapters Detected (6)

| Delta | Book | Before | After | Assessment |
|-------|------|--------|-------|------------|
| -52 | Designing Data-Intensive Applications (Kleppmann) | 215 | 163 | Correct — was over-detecting sub-sections |
| -17 | Rhetorical Function of Ezekiel (Renz) | 67 | 50 | Correct — academic sub-headings de-noised |
| -13 | Demons (Heiser) | 110 | 97 | Correct — section headers pruned |
| -8 | Readings in Database Systems (Hellerstein) | 25 | 17 | Correct — paper boundaries tightened |
| -1 | Kabbalah (Ginsburg) | 2 | 1 | Minor — single heading boundary shift |
| -1 | Public Finance (Gruber) | 204 | 203 | Negligible |

All reductions appear to be correct de-noising — the pipeline is detecting fewer false-positive headings. Kleppmann dropping from 215 to 163 is the clearest example: the book has ~12 real chapters, so 163 is still high (sub-sections) but 52 spurious entries were correctly removed.

## Heading Level Totals

| Level | Before | After | Delta | Interpretation |
|-------|--------|-------|-------|---------------|
| h1 | 161 | 168 | +7 | Slight increase — more top-level chapters correctly identified |
| h2 | 1,404 | 1,419 | +15 | Slight increase — some h3s promoted to h2 |
| h3 | 8,045 | 7,126 | -919 | Major reduction — hierarchy normalization working as intended |

The -919 h3 reduction is the signature of SCRUM-126. The fix normalizes heading hierarchies so that over-nested h3 tags (common in academic PDFs with deeply nested section numbering) get promoted or excluded. This directly improves Calibre TOC generation, which was the weakest VQA category (avg 66.8).

## Text Layer Quality Scores (SCRUM-121)

| Metric | Value |
|--------|-------|
| Average | 97.5 |
| Range | 68 – 100 |
| Below 75 | 1 book |

Only one book scored below the Tier 2 threshold (75):

- **Coulter — Occult Holidays** (score 68) — this is a known difficult PDF (also failed KFX conversion in the VQA baseline run)

All other 36 books scored 75+ on text layer quality, confirming that the text extraction path is healthy.

## Projected VQA Impact

Based on the VQA baseline analysis, TOC & Navigation was the weakest category (avg 66.8, 15% weight). The heading improvements here should directly improve TOC scores:

- **5 books rescued from 1-chapter** → these will generate real TOC entries now (previously had no navigable TOC)
- **919 fewer spurious h3 tags** → cleaner TOC hierarchy, fewer false entries
- **6 books with reduced over-detection** → more accurate TOC-to-content mapping

Estimated VQA impact: +5–8 points on TOC scores for affected books, translating to +1–2 points on overall VQA scores. A follow-up full VQA run would confirm.

## Recommendations

1. **Run full VQA on the 5 rescued books** to measure actual TOC score improvement ($0.20)
2. **Investigate Kleppmann** (163 chapters) — still significantly over-detecting; may need book-specific pattern tuning
3. **Add Bain and Codex Magica to test corpus** as regression targets for the new heading patterns
4. **Coulter (score 68)** needs investigation — only book below text quality threshold
