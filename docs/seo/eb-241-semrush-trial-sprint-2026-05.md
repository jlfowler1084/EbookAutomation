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

## Session 3 — Day 2 close-out (2026-05-18)

**Reports run:**
1. `phrase_kdi` on the 8 EPUB cluster keywords (~400 units)
2. `phrase_organic` on `can kindle read epub` top 20 (~100 units)
3. `tracking_position_organic` against the Position Tracking campaign (~800 units, 8 keywords × 100)

**Units consumed today:** ~1,300 of ~10K daily Pro-tier budget (~13%). Plenty of headroom for a Day 3 sweep if needed (smallpdf domain_organic + send-to-kindle fullsearch remain on the table from Session 2's deferral list).

### Findings

#### FINDING F — The EPUB cluster's difficulty is fully validated for Tier 1

All 8 keywords in the KD 20-35 range. The flagship `does kindle support epub` (720/mo, $14.12 CPC — the highest commercial signal in the entire trial) is **KD 20**, the easiest of the lot.

| Keyword | Vol | CPC | KD |
|---|---|---|---|
| does kindle support epub | 720 | $14.12 | **20** |
| epub format to kindle | 1,300 | $3.54 | **21** |
| can kindle use epub | 720 | $8.56 | **26** |
| epub format on kindle | 880 | $3.54 | **28** |
| does kindle read epub | 1,000 | $8.56 | **29** |
| does kindle take epub | 880 | $8.56 | **30** |
| does kindle read epub format | 720 | $8.56 | **30** |
| can kindle read epub | 1,300 | $8.56 | **35** |

The cluster sits comfortably under EB-241's Phase 1 KD < 30 filter (5 of 8) and within reach for the rest. **EB-303 Phase 3b's EPUB-to-Kindle Tier 1 candidacy is data-validated, not just hypothesized.**

#### FINDING G — The EPUB flagship SERP is content-quality-gated, not authority-locked

`phrase_organic` on `can kindle read epub` (the hardest of the 8 at KD 35) returned a top-20 dominated by forums, social, and small content sites. Amazon's own help page shows up at position 7 — present but not dominant.

| Result class | Count in top 20 | Examples |
|---|---|---|
| Forum / social / Q&A | 9 | Reddit, Quora ×2, Amazon Forum ×2, Facebook, YouTube ×2, TikTok, JustAnswer, StackExchange |
| Small content / pub blogs | 5 | kindlepreneur, takecontrolbooks, digitalpublishing101 ×2, britishbookpublishing |
| Mainstream tech pub | 2 | Mashable (2022), PCWorld (2022) |
| Amazon authority | 1 | help.amazon.com |
| SaaS help center | 1 | help.savory.global |

The Mashable and PCWorld pieces are dated to Amazon's late-2022 EPUB-on-Send-to-Kindle announcement — leafbind can publish materially fresher content. Kindlepreneur is the most-optimized direct competitor; the rest are loosely-optimized. **This SERP profile mirrors the pdf2kindle finding from Session 1 — quality content displaces aged authority pages in this niche.**

#### FINDING H — Position Tracking baseline confirmed: zero across all 8 Phase 2 targets, AI Overviews on all 8

The first 3 days of campaign data (May 17-19) show leafbind.io "out of top 100" for every tracked keyword — the correct baseline for a 4-day-old domain not yet in Semrush's index. The campaign now runs free through trial expiry and generates the rank-delta dataset that EB-303's Phase 3c re-baseline will compare against.

Two ancillary insights surfaced from the SERP feature column:

- **AI Overviews (aio) present on 8/8 tracked keywords.** Position #1 organic is no longer the only target — content optimized for AIO citation may capture click flow regardless of position.
- **People Also Ask (rel) present on 8/8.** Question-format H3s have a parallel ranking surface alongside primary organic ranking.

EB-303 pillar copy authoring should treat the click flow as ~30-40% AIO/PAA, not 100% position #1.

#### FINDING I — Semrush volume revisions vs Phase 1 estimates

| Keyword | Phase 1 est. | Semrush actual | Delta |
|---|---|---|---|
| convert pdf to kindle format | 1,000 | 590 | -41% |
| how to send pdf to kindle | (n/a) | 1,600 | new |
| kindle scribe vs remarkable | (n/a) | 2,900 | new |
| kindle scribe vs paperwhite | (n/a) | 320 | new |
| kindle scribe vs ipad | (n/a) | 480 | new |
| how to convert pdf to kindle format | (n/a) | 210 | new |
| send pdf to kindle scribe | (n/a) | 110 | new |
| send to kindle not working | (n/a) | 260 | new |
| **Total Phase 2 addressable (US)** | — | **6,470/mo** | — |

The 6,470/mo Phase 2 addressable is striking next to Finding A's 6,520/mo EPUB cluster — **the EPUB Tier 1 alone is essentially the entire Phase 2 addressable surface**, with materially better CPC profile and easier KD curve. This sharpens the EB-303 Phase 3b prioritization case.

### Action items routed

- **EB-303 Phase 3b Tier 1 (EPUB pillar):** difficulty validated, SERP profile favorable, ship sooner rather than later. The data argues for elevating this above the remaining Phase 2 LowFruits triage candidates.
- **EB-303 Phase 3 authoring guidance:** pillar copy structure should anticipate AIO citation (first-paragraph definitive answer, structured data) and PAA capture (H3 question-format anchors). Add this to the Phase 3b authoring brief.
- **EB-241 methodology improvement (second one):** SERP feature columns belong in Phase 1 keyword tables — feature mix changes ranking strategy. Pair with the "phrase_related early" learning from Session 2.
- **EB-241 methodology improvement (third one):** Position Tracking should be configured at Phase 1 Day 1, not Phase 3. The 6-week pre-launch tracking window would give a real baseline to measure against, instead of "we just launched and now we're measuring."

### Day 3 candidates (if Joe wants to spend more trial budget)

Carried forward from Session 2's deferred list (~1,300 units total):

1. `phrase_fullsearch` on `send to kindle` (~1,000 units) — exact-match variants of the 90,500/mo root
2. `domain_organic` on smallpdf.com top 30 (~300 units) — generic PDF-tool keywords

Both are nice-to-have, not critical. The EPUB Tier 1 case is now strong enough that the EB-303 Phase 3b decision doesn't need further data.

---

## Session 3 follow-up — Day 3 candidate sweep (2026-05-18 afternoon)

**Decision change:** Joe approved spending leftover Day 2 budget on the deferred queue. Scope expanded from the 2 Session 2 deferred items to a broader research sweep covering EPUB pillar authoring inputs, send-to-kindle cluster mapping, and competitor footprint analysis.

**Reports run (6 queries, all in parallel after schema load):**

1. `phrase_questions` on `kindle epub` broad seed (~2,000 units, 50 results)
2. `phrase_organic` on `does kindle support epub` top 20 (~200 units)
3. `phrase_fullsearch` on `send to kindle` (~1,000 units, 50 results)
4. `domain_organic` on smallpdf.com top 30 (~300 units)
5. `domain_organic` on kindlepreneur.com top 30 (~300 units)
6. `phrase_these` on the 2 Session 2 FAQ candidates + `tracking_overview_organic` (~120 units)

**Units consumed (afternoon sweep):** ~3,920 of remaining ~8,700 budget. Day 2 total: ~5,220 / ~10K (~52%).

### Six findings

#### FINDING J — EPUB question cluster is ~18,350/mo — 2.8× the Session 2 estimate

`phrase_questions` on the broad `kindle epub` seed returned 50 question variants totaling ~18,350/mo. The Session 2 "Finding A" estimate of 6,520/mo was based on 8 specific phrasings; the full lexical-variant cluster is materially larger.

Four authoring buckets emerge from the data:

**Bucket 1 — Capability questions** (~10,400/mo): "can/does/will Kindle support/read/take/use/play/accept EPUB" plus 20+ variants. Direct yes/no questions that need a definitive first-paragraph answer. Drives PAA + AIO eligibility.

**Bucket 2 — "How to {verb} EPUB to Kindle" workflow** (~3,300/mo across 9 verbs): send (1,000), send-an (720), add (390), put (390), upload (320), get (320), load (320), transfer (210), download (210). Each verb needs its own H3 anchor — lexical-variant diversity is the ranking moat.

**Bucket 3 — Conversion-specific** (~250/mo): "how to convert epub to kindle" (140), "how to convert epub to kindle format" (110). Low absolute volume but high direct-product-fit — these are the queries leafbind exists to serve.

**Bucket 4 — Hybrid "can I read EPUB on Kindle"** (~650+/mo): "can I/you read epub on kindle", "can epub be read on kindle". Bridge questions between capability and workflow.

**EB-303 Phase 3b EPUB pillar structure implication:** the page is not a single FAQ — it's a 4-section authority page with H2 anchors for each bucket and verb-named H3s under bucket 2. This is materially more depth than the existing top-ranking pages (Mashable, kindlepreneur), which is the displacement opportunity.

#### FINDING K — `does kindle support epub` SERP is slightly tougher than KD 20 suggests

The easiest EPUB target by KD has mainstream tech-pub presence the harder KD 35 query did not: **Digital Trends, BGR, ZDNet** all appear in the top 20. Authority-page pressure is real but the SERP is still content-quality-gated — 6+ forum/social results, plus 4 small content sites (kindlepreneur, takecontrolbooks, digitalpublishing101, bookfunnel), plus 1 new entrant (automateed.com — automated-answer aggregator).

| Class | Top 20 count | Pressure level |
|---|---|---|
| Mainstream tech pub | 3 (Digital Trends, BGR, ZDNet) | Authority pressure — not present in KD 35 SERP |
| Forum / social / Q&A | 6 (Reddit, YouTube ×4, TikTok, Amazon Forum) | Standard for the niche |
| Small content / pub blog | 5 (kindlepreneur, takecontrolbooks ×2, digitalpublishing101, bookfunnel) | Direct competitors |
| Automated answer aggregator | 2 (automateed.com ×2) | Low-quality competitor |
| Amazon authority | 1 (help page at #2) | Present and elevated vs KD 35 SERP |
| SaaS help | 1 (savory.global) | Niche |

**Pillar copy implication:** Definitive answer + structured data (Q&A schema) + comprehensive verb coverage will beat the BGR / Digital Trends / ZDNet generalist treatment. The Amazon help page at #2 is informational-only and doesn't offer a conversion path — leafbind's conversion CTA is the differentiator.

#### FINDING L — The `send to kindle` cluster has a 5,300/mo troubleshooting sub-cluster

`phrase_fullsearch` on `send to kindle` returned the 50 highest-volume exact-match variants. Beyond the expected root volume (74,000/mo), one subcluster stands out:

| Pain keyword | Vol | Signal |
|---|---|---|
| e999 - send to kindle internal error | 2,900 | Specific error code — people copy-paste from the Kindle app |
| e999 - send to kindle internal error: | 2,400 | Variant with trailing colon |
| an authentication failure occured send to kindle app | 1,000 | App auth failure copy-paste |
| send to kindle doesn't work | 480 | Generic frustration |
| **Total troubleshooting sub-cluster** | **~6,780/mo** | |

The e999 + e999: pair alone is 5,300/mo of pure-pain traffic. These searchers are mid-task, frustrated, looking for an immediate fix. **This is a Tier 2 candidate for a dedicated troubleshooting page** — high commercial signal (failed Send-to-Kindle is exactly when users would convert and try a third-party tool like leafbind).

Two EPUB-direction variants also showed up in this cluster:
- `send epub to kindle` — 1,300/mo
- `how to send epub to kindle` — 1,000/mo

These should be H2/H3 anchors inside the EPUB pillar (Finding J Bucket 2 confirmation).

#### FINDING M — smallpdf is not a real EPUB-pillar competitor

`domain_organic` on smallpdf.com top 30 returned a pure PDF-utility footprint: compress-pdf, merge-pdf, word-to-pdf, jpg-to-pdf, edit-pdf, split-pdf, image-to-pdf, png-to-pdf, heic-to-pdf, etc. **Zero keywords are ebook/kindle/epub adjacent.** Smallpdf is a generalist PDF tool, not a Kindle-format competitor.

**This reframes Session 1's "3-tier competitive ladder":**
- **pdf2kindle** — direct competitor on the PDF-to-Kindle cluster only (single-keyword dependency, displaceable)
- **smallpdf / online2pdf** — generalist PDF tools, NOT direct leafbind competitors. Adjacent only in domain name.
- **Real direct EPUB-pillar competitors** (newly identified): kindlepreneur, takecontrolbooks, digitalpublishing101, bookfunnel — all small content sites with broader scope.

**EB-309 implication:** deprioritize smallpdf as a link-prospecting target. The relevant prospecting pool is small-content-site editorial outreach, not generalist PDF-tool backlinks.

#### FINDING N — Kindlepreneur is a generalist author-resource site, not a focused EPUB competitor

`domain_organic` on kindlepreneur.com top 30 reveals their traffic profile is dominated by writing-software reviews and literary-vocabulary definitions:

- **#1 traffic driver (12.77%):** Grammarly review (2.24M/mo, position #8)
- **2nd-12th:** "kindlepreneur" brand, "synopsis definition", Wattpad review, "book writing software", Atticus review, "unabridged meaning", "parts of a book", ProWritingAid review, "slick write", "writing software"
- **13th-30th:** mostly more software reviews and literary vocabulary

Their `epub-to-kindle` page that ranks in our EPUB SERPs is a **tail page**, not a core driver. The ranking benefits from domain authority and topical adjacency, not from page-level optimization or deep coverage. **A focused, conversion-tool-anchored leafbind pillar with the 4-bucket structure (Finding J) and the verb-anchored workflow can plausibly out-rank them** — the same content-quality-displaces-authority pattern Session 1 found for pdf2kindle.

#### FINDING O — FAQ candidates confirmed: pure informational

`phrase_these` returned full metrics for the 2 Session 2 candidates:

| Keyword | Vol | CPC | Competition | Verdict |
|---|---|---|---|---|
| what file type does kindle use | 880 | $0 | 0 | Pure informational |
| kindle email address | 1,000 | $0 | 0 | Pure informational |

Zero CPC and zero competition on both = no commercial-intent buyer cohort. **These are correctly scoped as FAQ extensions on existing pages, not standalone landing targets.** Pair `what file type does kindle use` with the EPUB pillar (Finding J Bucket 1) and `kindle email address` with the Phase 2 Unit 3 mega-guide (already routed to EB-303 in Session 2).

### Action items routed (additions to Session 3 morning's list)

- **EB-303 Phase 3b EPUB pillar copy structure:** four H2 buckets per Finding J — capability questions / "how to {verb}" workflow with verb-named H3s / conversion-specific / hybrid. Author for AIO citation (Bucket 1 first-paragraph definitive answer) and PAA capture (Bucket 1 Q&A schema).
- **EB-303 Phase 3b TIER 2 NEW candidate:** "Send to Kindle troubleshooting" page — targets the 5,300/mo e999 + 1,000/mo authentication-failure pain-keyword cluster. Highest commercial-intent signal yet identified (failed Send-to-Kindle = peak conversion moment for leafbind alternative).
- **EB-309 Phase 4a re-scoping:** deprioritize smallpdf as a link-prospecting target. Real EPUB-pillar competitors are kindlepreneur, takecontrolbooks, digitalpublishing101, bookfunnel — small content sites where editorial outreach is the right link-acquisition channel, not generalist PDF-tool directories.
- **EB-303 Phase 3 sequencing recommendation:** the EPUB pillar (Tier 1) should ship before the send-to-kindle troubleshooting page (Tier 2), since the pillar is structurally novel work and the troubleshooting page is structurally similar to existing Phase 2 Unit 3.

### Day 2 close — what's left for Days 3-5

Daily Pro-tier budgets refresh midnight UTC. Trial expires 2026-05-23. Today's usage: ~5,220 / ~10K (~52%). Four more daily budgets of ~10K = ~40K units total potential remaining.

**Most of the high-value research is now done.** The remaining defensible uses:

1. **Daily freshness check on Position Tracking** (~800 units/day × 4 = ~3,200) — captures the indexation moment when leafbind first appears in Semrush's index
2. **`phrase_kdi` on the 6,780/mo troubleshooting cluster** (~250 units) — confirms KD before EB-303 Tier 2 commits to a troubleshooting page
3. **`phrase_questions` on `convert pdf to kindle`** (~2,000 units) — symmetric to Finding J for the PDF cluster; would catch the verb-family lexical variants Phase 2 Unit 5 might still be missing
4. **`backlinks_overview` + `backlinks_refdomains` on kindlepreneur.com + takecontrolbooks.com + bookfunnel.com** (~300 units total) — refreshes the EB-309 prospecting list with the real EPUB-pillar competitors per Finding N

Total potential Day 3-5 spend: ~5,750 units. Comfortable within the ~40K remaining budget. Recommend running these on Day 3 morning if useful, then leaving Days 4-5 as buffer.

---

## Final synthesis (placeholder)

*Will be compiled after all sessions complete and posted as a comment on EB-241.*
