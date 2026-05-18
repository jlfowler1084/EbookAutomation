---
module: docs/seo
tags: [seo, semrush, keyword-research, methodology, phase-1, phrase-related]
problem_type: research-methodology
date: 2026-05-18
ticket: EB-308
---

# Run `phrase_related` on Broad Anchors First in SEO Phase 1, Not as Phase 3 Expansion

## Problem

Seed-based keyword research methodology — picking 10-20 candidate seed phrases
from product knowledge, then running volume/KD checks on each — consistently
misses entire semantic clusters. The Phase 1 discovery pattern (used in EB-241
Phase 1) generates a defensible keyword list but leaves significant addressable
volume unmapped because it cannot surface neighbors of unfamiliar anchors.

## Evidence

EB-308 Semrush trial sprint Session 2 (2026-05-17). Phase 1 (EB-241, completed
2026-05) seeded with PDF-to-Kindle-direction keywords exclusively. Phase 2
LowFruits triage surfaced the broader `send to kindle` root (90,500/mo) as a
Related-tab discovery but did NOT decompose it.

In Session 2, running `phrase_related` on the single broad anchor `send to
kindle` (~2,000 units, 50 results) surfaced an 8-keyword EPUB-direction cluster
totaling ~6,520/mo that neither Phase 1 nor Phase 2 LowFruits triage had
touched. Day 3 follow-up sweep on `phrase_questions` against the same anchor
expanded the cluster to ~18,350/mo across 50 question variants.

| Discovery method | Cluster surfaced | Volume found |
|---|---|---|
| Phase 1 seed-based (4-6 hours) | PDF-direction keywords | ~11,500/mo addressable |
| Phase 2 LowFruits Related-tab | Send-to-Kindle root identified | Root only, not decomposed |
| Session 2 `phrase_related` on broad anchor (15 min) | EPUB-direction sub-cluster | ~6,520/mo additional |
| Session 3 `phrase_questions` on same anchor (15 min) | Full lexical-variant expansion | ~18,350/mo total |

The EPUB cluster was a **strategic-grade discovery** — it triggered a new Tier 1
content candidate (EB-320 EPUB pillar) that the original Phase 1 methodology
would never have surfaced. Capability gap: leafbind already accepted EPUB
inputs in production; Phase 1's PDF-direction seed list could not reach there.

## What Worked

**Run `phrase_related` on 2-3 of the product's broadest verb-phrase anchors
BEFORE any seed-list expansion.** Pick anchors that describe what the product
*does* at the broadest level, not the specific transactional verb-phrases users
type.

For leafbind, the right Phase 1 anchors would have been:
- `send to kindle` (the broadest "outcome" verb-phrase)
- `convert pdf` (the broadest input-format verb-phrase)
- `read on kindle` (the broadest consumption verb-phrase)

For each anchor: `phrase_related` with `display_limit=40-50, display_sort=nq_desc`.
Sift the result for cluster patterns (group by intent, direction, format). Each
discovered cluster becomes a Phase 1 candidate before any per-keyword volume
checking.

This produces clusters that seed-based discovery cannot reach because the
clusters often share no surface vocabulary with the seed list. EPUB-direction
keywords (`does kindle support epub`, `can kindle read epub`) share zero stems
with PDF-direction keywords (`convert pdf to kindle`, `pdf to kfx`) — only the
shared anchor `kindle` is common, and the anchor `send to kindle` was the
bridge that exposed both.

## Implementation

1. **Anchor selection (5 min):** identify the 2-3 broadest verb-phrases that
   describe what the product does at the highest level. Avoid the transactional
   phrases users type — those are intent-end-states, not anchors.
2. **Cost budget (~5,000 units total):** ~40 units × ~40 results × 3 anchors
   = ~4,800 units. Materially cheaper than running `phrase_questions` on the
   seed list one-by-one.
3. **Sift discipline:** for each result set, group by intent direction (PDF→
   Kindle vs Kindle→PDF), format direction (EPUB↔KFX↔PDF), and intent type
   (informational/transactional/positional). Note which clusters have NO
   overlap with the existing seed list — those are the highest-leverage
   discoveries.
4. **Decision gate:** for each new cluster, run a single `phrase_kdi` batch
   (~50 units/line for 5-8 keywords = ~250-400 units) to confirm difficulty
   before committing the cluster to Phase 1 candidates. The full Phase 1
   `phrase_these` + `phrase_kdi` workflow then applies.

## Cost Comparison

| Approach | Phase 1 cost | Clusters surfaced |
|---|---|---|
| Seed-based only (12 seeds) | ~600 units (phrase_these) + ~600 units (phrase_kdi on shortlist) | 1 (the seed list itself, ~11,500/mo) |
| Broad-anchor-first (3 anchors) | ~4,800 units (phrase_related) + ~1,000 units (phrase_kdi triage) | 2-4 clusters (~25,000+/mo addressable, including unexpected EPUB cluster) |

The broad-anchor-first method costs ~5x more in unit budget but typically
surfaces 2-3 strategic-grade clusters per pass. On a 10K-unit daily Pro-tier
budget, both methods fit within a single session.

## Counter-Evidence / When Not to Use

- **Heavily commercial verticals:** if the product's broadest anchor is a
  high-commercial-intent keyword (e.g., "buy car insurance"), `phrase_related`
  will return mostly noise — competitor brand names, paid-search-fragmented
  variants, transactional-but-too-broad terms. Phase 1 seed methodology may be
  better for narrow targeting.
- **B2B / niche enterprise products:** broad anchors may not exist (the product
  may BE the anchor — e.g., "snowflake data warehouse"). Use the product's
  category + 1-2 adjacent product categories as anchors instead.

## See Also

- `docs/solutions/eb258-seo-phase1-patterns.md` — Phase 1 methodology baseline
  this learning amends
- `docs/seo/eb-241-semrush-trial-sprint-2026-05.md` — Session 2 + 3 source
  research with raw cluster discoveries
- `[[serp-feature-columns-phase1-keyword-tables-2026-05-18]]` — companion Phase 1
  methodology learning surfaced by the same trial sprint
- `[[semrush-position-tracking-day-1-2026-05-18]]` — third Phase 1 methodology
  learning from the same trial sprint
