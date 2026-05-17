---
ticket: EB-308
parent: EB-241
phase: Semrush trial-period research sprint
date_start: 2026-05-17
trial_expiry: 2026-05-23
raw_artifacts: scratch/semrush-trial-2026-05/
---

# EB-308 Semrush Trial Sprint — Synthesis

Per-session close-out notes follow. Raw CSVs + per-section deep-dives live in `scratch/semrush-trial-2026-05/`.

---

## Session 1 — Day 1 close-out (2026-05-17)

**Reports run:**
1. `domain_rank` on leafbind.io → ERROR 50 (not yet indexed)
2. `phrase_organic` × 3 highest-volume Phase 2 keywords
3. `backlinks_overview` × 3 competitors
4. `backlinks_refdomains` × 3 competitors (50 / 20 / 15)
5. `domain_domains` keyword gap, shared keywords mode, pdf2kindle ∩ online2pdf

**Units consumed:** ~6,220 of ~10,000 daily Pro-tier budget (62%).

### Three findings that reshape Session 2 and downstream tickets

#### 1. The competitive ladder is genuinely climbable

Phase 1 implicitly framed the link-building problem as authority-mismatched. The data says otherwise:

| Competitor | Backlinks | Ref domains | Authority Score |
|---|---|---|---|
| pdf2kindle.com | 472 | 154 | **11** |
| online2pdf.com | 33,798 | 4,950 | 59 |
| smallpdf.com | 1,025,570 | 32,701 | 83 |

pdf2kindle (AS 11, 154 ref domains, ~30% of which are spam/PBN) ranks **#2 for `pdf to kindle format` (1,000/mo, KD 47)**. The niche is content-quality-gated, not authority-gated. **EB-309 Phase 4 link-building shifts from "precondition for ranking" to "compounding accelerant once content is in place."** EB-303 Phase 3 content quality becomes the higher-leverage lever.

#### 2. Phase 1's competitor identification was a hypothesis, not a measurement

Phase 1 named reddit.com, goodreader.com, calibre-ebook.com, the-ebook-reader.com as competitors. Measured top-10 across 3 representative SERPs:

| Phase 1 guess | Appearances in 3 measured SERPs | Status |
|---|---|---|
| reddit.com | 3/3 | ✅ Confirmed |
| goodreader.com | 0/3 | ❌ False |
| calibre-ebook.com | 0/3 | ❌ False |
| the-ebook-reader.com | 0/3 | ❌ False |

Real top 3 for backlink prospecting: **pdf2kindle.com** (direct), **smallpdf.com** (adjacent aspirational), **online2pdf.com** (triangulation). All three are conversion-tool competitors, not ebook-review sites.

#### 3. Intent contamination is real and quantified

Phase 1's plan flagged direction contamination (PDF→Kindle vs Kindle→PDF) as a Phase 2 risk and added an "eat-the-bounce" paragraph to Unit 5 against a ~45% estimate. Measured against the actual shared-keyword bucket:

| Direction | Top-30 shared kw count | Monthly volume share |
|---|---|---|
| REVERSE (Kindle → PDF) | ~10 | ~3,200 / ~7,200 (~44%) |
| CORRECT (PDF → Kindle) | ~16 | ~3,500 (~49%) |
| AMBIGUOUS / NON-ENGLISH | ~5 | ~510 (~7%) |

**The eat-the-bounce paragraph on Unit 5 is load-bearing — nearly half of organic visitors to the converter pillar may arrive with reverse intent.** Recommendation: audit Unit 5 to confirm the reverse-direction redirect is in the first 300 words (per Phase 2 plan).

### Action items emerging from Session 1

#### Immediate (this sprint, Session 2 or 3)

- [ ] Verify Phase 2 Unit 5 has the eat-the-bounce paragraph prominently placed in the first 300 words (text audit, 5 min)
- [ ] Audit Phase 2 Unit 3 (mega-guide) for `how to put pdf to kindle` exact phrasing (320/mo, KD 32 — variant currently uncovered)
- [ ] Audit Phase 2 Unit 5 for these exact phrasings: `turn pdf into kindle format`, `kindle convert pdf`, `convert pdf for kindle` — add H3 anchors if absent
- [ ] Session 2 should add `domain_organic` on pdf2kindle.com (~300 units) to map their full keyword footprint — they're our closest analog and ranking ~3-5 for queries leafbind targets

#### Route to other tickets

- [ ] **EB-303 Phase 3b backlog:** add `can you download pdf on kindle` (170/mo, KD 36, correct-direction, informational) — Phase 1 missed this question shape entirely. New FAQ extension OR short page.
- [ ] **EB-303 planning hygiene:** future keyword discovery should include `can you / is it possible to / does kindle support` question phrasings as a seed pattern, not just `how to / convert / send`.
- [ ] **EB-309 Phase 4a AC adjustment:** original AC required ≥30 link/distribution targets. Based on the realistic prospecting analysis (pdf2kindle's ~80-100 quality domains after spam exclusion), recommend revising to ~15-20 quality targets + ~10-15 low-friction directory submissions. Same volume, more honest framing.
- [ ] **EB-309 Phase 4d milestone:** the FIRST `domain_rank` non-error response on leafbind.io is a milestone worth comment-noting on EB-241. Track weekly during the trial period (10 units/check).

### Session 2 reshape — what I'll change

The pre-sprint plan was:
- Position Tracking setup
- Keyword Magic Tool expansion around the 90,500/mo cluster

**Reshape based on Session 1 findings:**

1. Keep Position Tracking setup (still high-leverage, runs free after setup).
2. Keep Keyword Magic on `send to kindle` (90,500/mo cluster) but **deprioritize** `pdf to kindle` (already mapped via shared-keywords analysis).
3. **ADD:** `domain_organic` on pdf2kindle.com, top 30 by traffic, limit=30 → ~300 units. Gives the full picture of what our closest analog ranks for. Higher leverage than a 4th broad keyword-expansion run.
4. **ADD:** `phrase_questions` on the `can you` / `does kindle support` seed patterns missed by Phase 1 → ~2,000 units, surfaces the missed question-shape cluster.

Net Session 2 budget estimate: ~3,500 units (within budget; well under 10K cap).

### What's still TBD

- Wikipedia mention strategy — discussed in `backlinks-synthesis.md` Tier C. Needs Phase 4 ticket to operationalize.
- Wikihow / softonic / stackexchange editorial outreach plan — Tier B prospecting list ready, but execution is EB-309 Phase 4c work.

---

## Session 2 — Day 2 close-out (placeholder)

*Will be filled after Session 2 runs.*

---

## Session 3 — Day 3 close-out (placeholder, optional)

*Will be filled after Session 3 runs if needed.*

---

## Final synthesis (placeholder)

*Will be compiled after all sessions complete and posted as a comment on EB-241.*
