---
module: docs/seo
tags: [seo, semrush, keyword-research, methodology, phase-1, aio, paa, serp-features]
problem_type: research-methodology
date: 2026-05-18
ticket: EB-308
---

# Include SERP Feature Columns (AIO/PAA/Featured Snippet) in Phase 1 Keyword Tables

## Problem

Phase 1 keyword tables in EB-241 captured the standard set: keyword phrase,
search volume, KD, CPC, intent classification, and primary-page mapping. They
did NOT capture SERP feature presence (AI Overviews, People Also Ask, featured
snippets, video carousels). This omission left a meaningful chunk of the
ranking strategy implicit — pages were authored assuming the goal was "position
#1 organic," when in reality 30-40% of the click flow on modern SERPs goes
through SERP features that have their own ranking criteria.

## Evidence

EB-308 Semrush trial sprint Session 3 (2026-05-18). Position Tracking on the
8 Phase 2 target keywords returned the SERP feature column for each tracked
keyword:

| SERP feature | Present on N of 8 tracked keywords |
|---|---|
| Organic (org) | 8/8 |
| AI Overviews (aio) | **8/8** |
| People Also Ask (rel) | **8/8** |
| Video carousel (vid) | 8/8 |
| Sitelinks (stl) | 8/8 |
| Related searches (res) | 6/8 |
| Images (img) | 1/8 (kindle scribe vs paperwhite only) |

Other Day 3 sweep findings reinforced this: `phrase_organic` on `does kindle
support epub` (KD 20) showed the same AIO + PAA presence in the SERP. The
pattern is consistent across the Kindle/EPUB niche — and likely across most
informational verticals as of 2026.

## What Worked (After the Fact)

Capturing SERP feature presence per keyword changes the authoring strategy:

- **AIO-present keywords:** the page that gets cited in the AI Overview captures
  click flow regardless of organic position. Authoring discipline: first-paragraph
  definitive answer using verbatim keyword phrasing, structured-data eligibility,
  citable standalone passages (~134-167 words per FAQ — the AIO citation
  eligibility band per `eb258-seo-phase1-patterns.md`).
- **PAA-present keywords:** question-format H3 anchors have a parallel ranking
  surface. Authoring discipline: include H3-format Q&A sections, wrap in
  `FAQPage` JSON-LD, ensure the H3 question text matches likely PAA query
  formulations.
- **Featured snippet present:** ~10-15% of search clicks go to the snippet
  position; structure copy as definition / list / table to match the snippet
  format.
- **Video carousel present:** organic position #2-3 may have lower CTR than
  expected because video results dominate above-the-fold real estate. Calibrate
  ranking gates accordingly (don't celebrate a position #3 finish if videos
  take rows 1-2).

## Implementation

When building Phase 1 keyword tables, add columns for each tracked SERP feature
relevant to the niche. For most informational/transactional niches, the
minimum set is:

| Column | Source |
|---|---|
| AIO | `phrase_organic` response `Sf` field; `tracking_position_organic` `Sf` per-date field |
| PAA (rel) | Same source |
| FSN (featured snippet) | Same source |
| VID (video carousel) | Same source |
| IMG (image pack) | Same source |

Each column is binary: present (1) / absent (0). Aggregate at table level:
"AIO present on N of K keywords" signals authoring priority.

For comprehensive SERP feature codes, see the `tracking_position_organic`
schema `serp_feature_filter` description (lists all 35+ feature codes).

## Cost

Free — SERP feature data is already returned in `phrase_organic` (~10
units/keyword) and `tracking_position_organic` (~100 units/keyword) responses.
The cost is in adding the columns to the Phase 1 doc template, not in fetching
the data.

## Authoring Implication

Pages should be authored for **all relevant SERP surfaces**, not just position
#1 organic. The EB-320 EPUB pillar plan was amended in R5b to encode this
discipline:

> Each FAQ H3 answer is structured for AIO citation eligibility: definitive
> first sentence answering the H3 question using the target phrasing verbatim,
> followed by 2-3 sentences of supporting context using verifiable facts. Each
> FAQ is wrapped in FAQPage JSON-LD so PAA capture is also eligible. Treat
> ~30-40% of expected click flow as AIO/PAA, not 100% position #1 — copy must
> be standalone-citable, not dependent on surrounding context.

Apply the same discipline to every Phase 3+ pillar / FAQ page.

## Counter-Evidence / When Not to Use

- **Transactional / conversion-focused pages** (`/convert/*`, `/pricing`, etc.):
  AIO/PAA citation matters less because the click intent is "land on the
  converter and use it." First-paragraph definitive answer is still useful but
  not load-bearing.
- **Very low-volume long-tail keywords (< 50/mo):** SERP feature presence data
  is noisy; capture the columns but don't authoring-optimize for them — the
  click flow won't justify the effort.

## See Also

- `[[phrase-related-broad-anchor-first-2026-05-18]]` — companion Phase 1
  methodology learning surfaced by the same trial sprint
- `[[semrush-position-tracking-day-1-2026-05-18]]` — third Phase 1 methodology
  learning from the same trial sprint
- `docs/solutions/eb258-seo-phase1-patterns.md` — AIO citation eligibility band
  (134-167 words) baseline
- `docs/seo/eb-241-semrush-trial-sprint-2026-05.md` — Session 3 source research
- `docs/plans/2026-05-17-001-feat-eb-320-epub-on-kindle-pillar-plan.md` — R5b
  amendment that codifies AIO/PAA authoring discipline for the first time
