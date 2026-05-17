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

## Session 2 — same-day continuation close-out (2026-05-17)

**Decision change from plan:** Joe asked to continue Session 2 on Day 1 rather than waiting for Day 2 (rationale: trial credits refresh daily and don't bank — unused credits are lost). Once Session 1 ran clean (no cap-surprise), the "split for safety" justification was empirically retired. The "split for reflection" justification remained partially intact, but for **research/data-collection** (not synthesis), reflection happens after collection — so continuing same-day was the higher-EV choice. Saved as feedback memory ([[feedback-split-daily-refresh-resources]]).

**Reports run:**
1. `phrase_questions` on `pdf to kindle`, top 30 by volume
2. `phrase_related` on `send to kindle` (90,500/mo root), top 40 by volume
3. `domain_organic` on pdf2kindle.com, top 30 by traffic
4. `tracking_research` discovery (probe Position Tracking availability)

**Units consumed today:** ~9,280 of ~10K daily Pro-tier budget. Stopped before pushing into Session 3 — diminishing-returns curve and tomorrow's fresh budget make further today-work low-EV.

### Findings that genuinely reshape EB-303 Phase 3 scope

#### FINDING A — The EPUB→Kindle cluster is the biggest single opportunity yet discovered

Phase 1 seeded on PDF-to-Kindle keywords exclusively. Phase 2 LowFruits surfaced the 90,500/mo `send to kindle` root but didn't decompose it. Semrush `phrase_related` on that root surfaced eight EPUB-direction keywords totaling ~6,520/mo, none of which leafbind currently targets:

| Keyword | Vol | CPC (intent signal) |
|---|---|---|
| can kindle read epub | 1,300 | $8.56 (high commercial) |
| epub format to kindle | 1,300 | $3.54 |
| does kindle read epub | 1,000 | $8.56 |
| does kindle take epub | 880 | $8.56 |
| epub format on kindle | 880 | $3.54 |
| can kindle use epub | 720 | $8.56 |
| does kindle read epub format | 720 | $8.56 |
| does kindle support epub | 720 | $14.12 (highest commercial signal in entire trial) |

leafbind already accepts EPUB inputs (per CLAUDE.md). The product capability exists; the content doesn't. Recommend **EB-303 Phase 3b adds an EPUB-to-Kindle pillar page** (or a dense FAQ cluster on the existing converter pillar) as the highest-priority new content target. **This single cluster dwarfs Phase 2's combined ~11,500/mo addressable.**

Direction note: most of these are informational ("does Kindle support EPUB?") with high CPC suggesting commercial intent. The answer page should explain Kindle's EPUB story honestly (Amazon dropped MOBI for EPUB in late 2022 for send-to-kindle), then position leafbind as the path for EPUBs that don't behave well via Send-to-Kindle.

#### FINDING B — pdf2kindle.com is structurally displaceable

`domain_organic` on pdf2kindle.com shows their entire site traffic concentrated on a single keyword:

- `pdf to kindle format` (1,000/mo, position #2): **50% of their entire site traffic**
- All other keywords combined: 50% of traffic, spread across ~28 keywords
- Top non-money keyword: `transformar pdf a kindle` (Spanish, 170/mo) at 16%

Their AS 11 + ~30% spam backlinks + single-keyword dependency means: **out-rank them on ONE keyword and capture half their organic traffic.** Phase 2 Unit 5 is already targeting this keyword; the action item is **content depth audit** — verify Unit 5's content meaningfully out-depths pdf2kindle's one-pager. If not, expand Unit 5 before launching Phase 3.

#### FINDING C — Two new FAQ candidates at >800/mo each

- **`what file type does kindle use`** (880/mo) — pure informational. FAQ extension on existing converter pillar OR a dedicated short page. Pairs naturally with the EPUB cluster (Finding A).
- **`kindle email address`** (1,000/mo) — pure informational, Send-to-Kindle workflow specific. FAQ extension on Phase 2 Unit 3 (mega-guide).

#### FINDING D — Position Tracking requires manual Semrush web UI setup

`tracking_research` MCP toolkit can READ existing tracking campaigns but cannot CREATE them. The Semrush web UI Projects feature is the only path to set up Position Tracking. **User action required (~10 min, one-time):**

1. Log into Semrush web UI → Projects → Create Project for `leafbind.io`
2. Add Position Tracking tool
3. Configure the 8 Phase 2 target keywords (from EB-303 § Phase 3c table)
4. Set tracking location to US
5. Save — daily tracking begins automatically

Once configured, the MCP can query `tracking_position_organic` (~800 units for 8 keywords) for daily snapshots until trial expires. Defer this setup to Joe; not blocking for the rest of the sprint.

#### FINDING E — Phase 2 Unit 3 mega-guide scope justified by data

`phrase_questions` on `pdf to kindle` surfaced 30+ variant phrasings totaling ~10,000/mo. The 3,000-4,000-word Unit 3 mega-guide scope is justified by the lexical-variant diversity — Google's intent classifier needs to see specific phrasings to attribute traffic. Action: cross-check Unit 3 against the variants in `phrase-questions-pdf-to-kindle.csv` to confirm coverage. Specifically watch for: `how to put pdf to kindle` (320/mo), `how to load pdf in kindle` (480/mo), `how to upload pdf to kindle` (480/mo), `how to read pdf on kindle` (390/mo) — these are the variants most likely to need explicit H3 anchors.

### Methodology learning — for future SEO sprints

Phase 1's seed-based methodology consistently misses entire semantic clusters. `phrase_related` on a single broad anchor keyword (`send to kindle`) surfaced the EPUB cluster that 4-6 hours of Phase 1 work + LowFruits triage never touched. **Future SEO discovery should run `phrase_related` on broad anchors AT THE START** (Phase 1 step 1b), not as a Phase 3 expansion. Recommended seed anchors for similar product launches: the product's broadest verb-phrase (`send to kindle`, `convert pdf`, `read on kindle`), then decompose. This is the highest-leverage Phase 1 methodology improvement surfaced by the sprint.

### Action items routed to other tickets

- **EB-303 Phase 3b — NEW TIER 1:** EPUB-to-Kindle pillar page or dense FAQ cluster targeting the 8-keyword ~6,520/mo cluster. Higher priority than the Phase 2 LowFruits triage candidates. Update EB-303 description to reflect this.
- **EB-303 Phase 3b TIER 2 additions:** `what file type does kindle use` (880/mo) + `kindle email address` (1,000/mo) — FAQ extensions.
- **EB-303 Phase 2 Unit 5 amendment:** content depth audit vs pdf2kindle's one-pager. If Unit 5 isn't meaningfully deeper, expand BEFORE Phase 3 launches.
- **EB-303 Phase 2 Unit 3 amendment:** lexical-variant audit against `phrase-questions-pdf-to-kindle.csv`. Add H3 anchors for any high-volume phrasing not currently covered.
- **EB-308 (this ticket) Position Tracking:** manual Semrush web UI setup needed by Joe (~10 min). Defer Day 3 query until campaign is configured.
- **EB-241 final synthesis:** include "phrase_related early" methodology learning as a permanent Phase 1 process improvement.

### Session 3 — what's still on the table

If Joe chooses to spend Day 2 or Day 3 budget:

1. **`phrase_kdi` on the 8 EPUB keywords** (~400 units) — confirm difficulty before committing to Phase 3 content.
2. **`phrase_organic` on `can kindle read epub`** (~100 units) — see who currently ranks; if it's all Amazon authority pages, the difficulty is high regardless of KD.
3. **`phrase_fullsearch` on `send to kindle`** (~1,000 units) — exact-match variants of the 90,500/mo root that `phrase_related` missed (related ≠ variant).
4. **`domain_organic` on smallpdf.com top 30** (~300 units) — see what generic PDF-tool keywords they rank on; might reveal more leafbind-adjacent opportunities.
5. **Position Tracking** — IF Joe completes the manual setup, can query via MCP (~800 units).

Recommended Session 3 priority order: 1 → 2 → 5. Total budget: ~1,300-1,500 units. Highly compatible with Day 2's fresh 10K budget.

---

## Session 3 — Day 3 close-out (placeholder, optional)

*Will be filled after Session 3 runs if needed.*

---

## Final synthesis (placeholder)

*Will be compiled after all sessions complete and posted as a comment on EB-241.*
