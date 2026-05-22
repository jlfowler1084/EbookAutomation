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

## Session 4 — Day 4 close-out (2026-05-20)

**Reports run (9 queries — 4 from the carried-forward Day 3-5 list + 2 follow-ups from leftover budget + 1 schema-recovery probe):**

1. `phrase_kdi` on the troubleshooting cluster (4 keywords, ~200 units)
2. `phrase_questions` on `convert pdf to kindle` top 50 (~1,960 units)
3. `backlinks_overview` × 3 EPUB-pillar competitors (kindlepreneur, takecontrolbooks, bookfunnel, ~30 units)
4. `backlinks_refdomains` × 3 same competitors, top 50 each (~300 units)
5. `campaigns` discovery on project 29685400 (~100 units — recovery probe; the prior `position-tracking-campaign.md` noted only the inner ID `4805618`, but the API requires the composite `29685400_4805618`)
6. `tracking_position_organic` Day 4 snapshot — 8 Phase 2 keywords (~800 units)
7. `phrase_kdi` on Phase 2 FAQ candidates + EPUB-direction send variants (~200 units — leftover-budget follow-up)
8. `phrase_organic` on `e999 - send to kindle internal error` top 20 (~200 units — leftover-budget follow-up sizing the EB-303 Tier 2 opportunity)

**Units consumed today:** ~3,790 of ~10K Day 4 Pro-tier budget (~38%).

### Findings

#### FINDING P — `convert pdf to kindle` question family is REVERSE-direction-dominated by 2:1

The `phrase_questions` run surfaced 50 question variants. After tagging direction:

| Direction | Top-50 keyword count | Combined monthly volume |
|---|---|---|
| REVERSE (Kindle → PDF) | ~32 | ~2,380/mo |
| FORWARD (PDF → Kindle) | ~12 | ~1,140/mo |
| AMBIGUOUS | ~6 | ~120/mo |

The highest-volume single question — `how to convert kindle books to pdf` (320/mo) — is reverse direction. The top 5 highest-volume forward-direction questions are all variants of `how to convert pdf to kindle [format/file]` totaling ~860/mo combined.

**This is materially worse than Day 1 Finding 3.** Day 1 measured shared-keyword direction split at ~44% reverse from `domain_domains` shared-keywords. Today's `phrase_questions` data shows the question-format SERP is **~67% reverse by volume** — searchers asking with question-phrasing skew Kindle→PDF much more than searchers using verb-phrasings like "send".

**EB-303 Phase 2 Unit 5 action:** the existing "eat-the-bounce" paragraph is necessary but probably insufficient on its own. The page should add an explicit, conversion-friendly **"Wrong direction? Here's how to convert Kindle to PDF instead →"** section pointing to Calibre's official extraction docs (or a leafbind-authored short guide). Pre-empting bounce with a real outbound recommendation captures user goodwill and turns a 67%-reverse intent stream into an asset: visitors who came wrong-direction may bookmark or return when they need the forward direction.

**EB-303 Phase 3 sequencing:** a dedicated `/guides/convert-kindle-to-pdf` reverse-direction page is now a defensible Tier 2-or-Tier 3 candidate. Capturing the 2,380/mo reverse-direction volume even at position-5 traffic share = ~100/mo organic visits with non-trivial conversion potential to leafbind's main service via "now do the opposite" CTA.

#### FINDING Q — Troubleshooting cluster KD validates EB-303 Tier 2 commit

| Keyword | Volume | KDI |
|---|---|---|
| e999 - send to kindle internal error | 2,900 | **16** |
| e999 - send to kindle internal error: (with colon) | 2,400 | **15** |
| an authentication failure occured send to kindle app | 1,000 | 0 (no SERP signal) |
| send to kindle doesn't work | 480 | **25** |

All measurable variants sit in the KD 15-25 band — easier than even the EPUB Tier 1 cluster (KD 20-35). The auth-failure variant's `KD=0` means Semrush has insufficient SERP signal to score it (per the skill's "KD=0 = no data, NOT easy" guidance), not that it's trivial. Treat that 1,000/mo as needing manual SERP review before counting.

**EB-303 Phase 3b Tier 2 troubleshooting page is data-validated** — KD comfortable, 4,780/mo of measurable addressable traffic in the e999 + doesn't-work bucket alone.

#### FINDING R — The e999 SERP is WIDE OPEN — highest-leverage opportunity in the trial dataset

`phrase_organic` on `e999 - send to kindle internal error` (the flagship 2,900/mo query):

| Result class | Count in top 20 | Notes |
|---|---|---|
| Forum / Q&A / social | 13 | Reddit, Amazon Forum ×5, GitHub ×2, MobileRead, Quora, TikTok ×2 |
| Small troubleshooting blogs | 5 | bitrecover, docgenie, macsonik, comingsoonwp, axeetech |
| Amazon authority | 1 | Amazon UK help (not US Amazon Help) at position #15 |
| Authoritative tech publication | 0 | none |
| Conversion-tool competitor | 0 | none |

The SERP is dominated by user frustration threads (Reddit + Amazon Forum) and 5 small SEO-grab troubleshooting blogs that monetize via display ads. **No authoritative source. No comprehensive fix guide. No competitor combines troubleshooting + conversion-tool alternative.**

This is the highest-leverage opportunity in the entire trial dataset. A leafbind-authored troubleshooting page that:

1. Definitively explains e999 causes (whitelist + email auth + file format + size)
2. Walks through diagnostic fixes step-by-step (Amazon's own help page is unfocused and at #15)
3. Offers leafbind as the "skip Send-to-Kindle entirely" alternative when fixes don't work

...would plausibly hit top-3 within months of indexation, on a query with peak commercial intent (failed Send-to-Kindle = exact moment user would try a third-party tool).

**EB-303 Phase 3b sequencing — REVISED:** based on R (peak commercial signal + wide-open SERP), the troubleshooting page may actually be the higher-EV Tier-1 launch than the EPUB pillar. Both are defensible. The EPUB pillar wins on volume (~18,350/mo combined per Day 2 Finding J), the troubleshooting page wins on conversion intent (failed-flow capture = highest-converting moment). Decision arguably belongs in EB-303 planning, not the trial sprint — flagged for explicit prioritization there.

#### FINDING S — EPUB workflow-verb variants are harder than the EPUB capability cluster

| Keyword | Volume | KDI | Cluster bucket (per Day 2 Finding J) |
|---|---|---|---|
| send epub to kindle | 1,300 | **57** | Bucket 2 (workflow verbs) |
| how to send epub to kindle | 1,000 | **47** | Bucket 2 (workflow verbs) |

These are ~25-30 KD points harder than the EPUB capability questions (`does kindle support epub` at KD 20, `does kindle read epub` at KD 29). The Day 2 hypothesis that EPUB-pillar workflow verbs share the capability cluster's easy difficulty is **partially incorrect**. Expect EPUB-pillar ranking to come in two waves:

- **Wave 1 (months 1-3 post-launch):** capability questions (Bucket 1) — KD 20-35, easier SERP profile
- **Wave 2 (months 3-12 post-launch):** workflow verbs (Bucket 2) — KD 47-57, requires accumulated topical authority

This doesn't invalidate the EPUB pillar — the page should still have H3 anchors for both capability questions and workflow verbs. But the early-ranking expectation should be set against Wave 1 only, not the full 18,350/mo cluster.

#### FINDING T — Phase 2 FAQ candidates: clean split

| Keyword | Volume | CPC | KDI | Recommendation |
|---|---|---|---|---|
| kindle email address | 1,000 | $0 | **24** | Could be a short dedicated landing page, not just FAQ extension |
| what file type does kindle use | 880 | $0 | 40 | FAQ extension on EPUB pillar (per Day 2 routing) |

`kindle email address` at KD 24 + 1,000/mo + pure informational intent is a legitimate easy-win short-page candidate. The original Day 2 routing was "FAQ extension on Phase 2 Unit 3 mega-guide" — but at this KD level, an extracted standalone short page (~500-800 words) would rank faster and capture full traffic share rather than splitting it across an FAQ block.

#### FINDING U — The 3 EPUB-pillar competitors have 3 DIFFERENT backlink profiles — EB-309 needs 3 outreach playbooks

| Competitor | AS | Ref domains | Profile | Top-tier link drivers |
|---|---|---|---|---|
| kindlepreneur.com | **42** | 6,237 | Editorial / SaaS author-resource | Adobe (1), Apple (1), Microsoft (10), Pinterest (6), Forbes (4), Harvard (1), Wikipedia (3), Substack (470) |
| takecontrolbooks.com | 30 | 1,727 | Academic / technical publisher | Princeton (1), Penn State (4), Utah (2), UPenn (2), JHU (2), Engadget (60), CNET (11), Macrumors (31), O'Reilly (150) |
| bookfunnel.com | 38 | 14,584 | Mass author-marketing platform | Goodreads (2,030), Linktree (1,866), Substack (35,876!), Patreon (52), Wattpad (2), Wordpress.org (80), Bit.ly (19), Zapier (152) |

Three distinct link-acquisition playbooks:

- **kindlepreneur model = editorial outreach.** High-quality tech-publication mentions, Substack newsletter ecosystem, occasional Forbes/Harvard cite. Slow to build, high authority per link.
- **takecontrolbooks model = academic + technical publisher cross-linking.** .edu domain heavy (Princeton, Penn State, UPenn, JHU, Dartmouth, BYU, Yale, Utah, Georgetown, Apache, Ubuntu), tech-pub deep links (O'Reilly 150 — likely review citations of the publisher's own books). Hard to replicate without being an academic publisher.
- **bookfunnel model = author-marketing infrastructure.** Goodreads + Linktree + Substack (35K backlinks!) + Wordpress.org + Patreon + Wattpad — this is the indie-author publishing stack. The links are driven by *users of the platform* mentioning the platform, not editorial outreach.

**EB-309 implication:** the previous "30 quality targets" AC needs to differentiate by playbook. For leafbind's conversion-tool positioning, the kindlepreneur model is the right analog — editorial outreach to tech publications (Engadget, Lifehacker, MakeUseOf, Digital Trends), tier-2 small content sites (kindlepreneur, takecontrolbooks themselves as link prospects), and Substack newsletter writers in the ebook/reading vertical. The bookfunnel model is structurally not replicable for a conversion utility.

#### FINDING V — Position Tracking Day 4: still zero, AIO universal, SERP composition stable

5-day snapshot (2026-05-17 → 2026-05-21) confirms:

- **All 8 tracked keywords:** out of top 100 every day. Indexation hasn't begun (expected — site is 8 days old).
- **AI Overview (`aio`):** present on 8/8 keywords every day. Strategic implication unchanged from Day 2 Finding H — pillar copy must be AIO-citation-optimized.
- **PAA (`rel`):** present on 8/8 every day. Question-format H3 anchors remain the parallel ranking surface.
- **Minor SERP-feature drift:** `adb` (Google Ads bottom) dropped from `how to convert pdf to kindle format` after 2026-05-18; `res` (Related searches) dropped from `send pdf to kindle scribe` after 2026-05-19. No strategic implication — feature presence varies daily.

The tracking campaign continues running free through trial expiry. Day 5 (2026-05-21) will be the last day of trial-billed snapshots; if EB-303 wants ongoing tracking after the trial, the campaign must be checked against Semrush's free-tier campaign retention policy.

### Methodology note — campaign ID format

The Position Tracking schema requires `campaign_id` in the format `{project_id}_{tracking_id}`, not the bare tracking ID. The Day 2 capture in `position-tracking-campaign.md` listed the inner ID alone; an initial call with `4805618` returned `campaign not found`. Recovery: call `campaigns(project_id='29685400')` to discover the composite ID `29685400_4805618`. Updated note now lives in `position-tracking-campaign.md` (or should — TODO update that file with the corrected format).

### Action items routed

- **EB-303 Phase 2 Unit 5:** add explicit "Wrong direction? Here's how to convert Kindle → PDF →" section pointing to Calibre extraction docs or a short leafbind-authored guide. The eat-the-bounce paragraph alone is undersized against the 67%-reverse question-format intent.
- **EB-303 Phase 3 NEW Tier 2-or-3 candidate:** dedicated `/guides/convert-kindle-to-pdf` reverse-direction page targeting the ~2,380/mo Kindle→PDF question cluster. Routes user to Calibre, mentions leafbind for the forward direction.
- **EB-303 Phase 3b sequencing — DECISION POINT:** EPUB pillar (volume play, ~18,350/mo) vs Send-to-Kindle troubleshooting page (commercial-intent play, peak conversion moment, wide-open SERP). Both defensible Tier 1 candidates. EB-303 needs to pick the launch sequence; recommend troubleshooting page first if conversion-rate-to-paid-tier matters more than top-of-funnel traffic for the next 90 days.
- **EB-303 Phase 3b EPUB pillar:** set Wave 1 / Wave 2 ranking expectations explicitly per Finding S. Capability questions rank in months 1-3, workflow verbs in months 3-12.
- **EB-303 Phase 2 FAQ extension → consider extraction:** `kindle email address` (1,000/mo, KD 24) may deserve a short standalone landing instead of an FAQ block on Unit 3.
- **EB-309 Phase 4a re-scoping — REVISED:** differentiate the link-acquisition AC by playbook. Target the kindlepreneur model (editorial outreach to tech publications + Substack newsletter integration); deprioritize bookfunnel-style mass-platform link acquisition as structurally non-replicable for a conversion utility.
- **EB-308 (this ticket):** update `scratch/semrush-trial-2026-05/position-tracking-campaign.md` with the corrected composite campaign ID format. Final synthesis still pending (one more day in trial window — Day 5 2026-05-21).

### What's left for Day 5 (final trial day)

After the evening sweep below, Day 4 totaled ~6,200 of ~10K (~62%). Day 5 plan unchanged:

1. **Final Position Tracking snapshot** (~800 units) — captures the last trial-billed day before campaign retention questions kick in
2. **`phrase_organic` on `e999 - send to kindle internal error:` (with colon, 2,400/mo) and `send to kindle doesn't work` (480/mo)** (~200 units) — sizes the rest of the troubleshooting cluster's competitive landscape
3. **Final synthesis writeup + EB-241 comment** (free) — wrap the sprint formally

Total Day 5 spend: ~1,000 units.

---

## Session 4 evening sweep — corrections (2026-05-20 evening)

**Reports run (4 queries — exploring new candidates that emerged from the morning sweep):**

1. `phrase_questions` on `kindle to pdf` broad seed (~2,000 units) — map the reverse-direction question family for Finding P's proposed guide candidate
2. `phrase_organic` on `how to convert kindle books to pdf` top 20 (~200 units) — size the SERP competitive landscape for the highest-volume reverse-direction question
3. `phrase_organic` on `kindle email address` top 20 (~200 units) — confirm Finding T's standalone-landing recommendation
4. `domain_rank` retry on leafbind.io (~10 units, ERROR 50) — capture any indexation since Day 1

**Units consumed (evening):** ~2,410. Day 4 total: ~6,200 / 10K (~62%).

### Two material corrections to earlier findings

#### CORRECTION 1 (downgrades FINDING T) — `kindle email address` is NOT a standalone-landing candidate

The morning sweep flagged `kindle email address` (1,000/mo, KD 24) as "easier than expected" — recommended extracting to a short dedicated landing rather than the original FAQ-extension routing. **The SERP audit invalidates this.**

| Result class | Count in top 20 |
|---|---|
| Amazon first-party (sendtokindle/email landing + 2× Help + Forum + KDP) | **5/20** |
| Publishing-tool help docs (BookSirens, Prolific Works, NetGalley) | 3/20 |
| Forum / Q&A / video | 5/20 |
| Tech blog / general-info authority (WikiHow, AskDaveTaylor, Cloudwards) | 4/20 |
| Paid conversion tool | 1/20 (Epubor at #20) |

**Amazon owns position #1 with their dedicated `amazon.com/sendtokindle/email` landing.** Plus 2 more Amazon Help pages, Amazon Forum, and KDP Community in the top 20. This is a first-party canonical-answer SERP — Semrush's KD 24 understates the difficulty because the difficulty signal is domain-authority-based, but in product-feature-lookup SERPs the vendor's own product page is the inevitable #1.

**Revised recommendation:** keep `kindle email address` as the originally-scoped Day 2 FAQ extension on Phase 2 Unit 3 mega-guide. A leafbind standalone page cannot displace Amazon at "find my Kindle email address" — that's literally a feature of Amazon's product.

**Methodology learning:** KD scores are misleading on product-feature-lookup queries. Future Phase 1 work should flag any keyword where the obvious first-party vendor owns the canonical answer page (Amazon for Kindle features, Google for Workspace features, etc.) and SERP-audit before trusting KD.

#### CORRECTION 2 (downgrades FINDING P's reverse-direction guide candidate) — reverse-direction SERP is NOT wide-open

The morning sweep flagged a dedicated `/guides/convert-kindle-to-pdf` reverse-direction page as a defensible Tier 2/3 candidate based on volume (~2,380/mo) and the "wrong direction" intent stream. **The SERP audit shows competitive density that invalidates the candidacy.**

SERP for `how to convert kindle books to pdf` (320/mo — highest-volume reverse-direction question, top 20):

| Result class | Count in top 20 | Examples |
|---|---|---|
| Authority brand landing | 1/20 | **Adobe Acrobat at #1** (adobe.com/uk/acrobat/resources/kindle-to-pdf.html — dedicated landing page) |
| Paid conversion tool vendors | **6/20** | Wondershare ×2, Smallpdf, Epubor, EaseUS, PDFMate, Systools |
| Forum / Q&A / social | 8/20 | Reddit, JustAnswer, Quora, Amazon Forum, Facebook, KDPCommunity ×2, MobileRead, SuperUser |
| Small blog | 1/20 | joelhooks.com (Calibre tutorial) |
| Video | 2/20 | YouTube ×2 |

**This is the OPPOSITE of the e999 SERP.** The e999 query had ZERO authority brands and ZERO conversion-tool vendors in the top 20 — wide-open. The reverse-direction query has Adobe at #1 AND six entrenched paid conversion vendors competing aggressively. Smallpdf, Wondershare, EaseUS, PDFMate, Systools, and Epubor have each published dedicated landing pages with established SEO moats. A leafbind reverse-direction page would be fighting Adobe + 6 vendors simultaneously.

**Revised recommendation:** **drop** the `/guides/convert-kindle-to-pdf` standalone page from the EB-303 candidate list. The 67%-reverse intent on the `convert pdf to kindle` SERP is still real, but the right response is the **eat-the-bounce + outbound redirect** modification to Unit 5 (Finding P's first half), not a competing reverse-direction landing page.

**Methodology learning:** the morning sweep's recommendation jumped from "intent contamination is real" to "build a competing page" without auditing the competitive density of the alternative-direction SERP. A SERP audit on any new candidate page should be a hard gate, not a follow-up. Add this to Phase 1 process checklist.

### Confirmed (no correction needed)

#### FINDING W — reverse-direction question cluster total ≈ 2,450/mo (confirms Finding P's volume estimate)

Direction tagging of the 50 `kindle to pdf` `phrase_questions` results gives:

| Direction | Volume share | Top variants |
|---|---|---|
| FORWARD (PDF → Kindle) | ~9,400/mo across ~35 questions | `how to send pdf to kindle` (1,600), `how to add pdf to kindle` (880), `how to put pdf on kindle` (880), etc. |
| REVERSE (Kindle → PDF) | ~2,450/mo across ~12 questions | `how to download kindle books to pdf` (390), `how to convert kindle books to pdf` (320), `how to download a kindle book to pdf` (320), `how to convert kindle to pdf` (260), etc. |

Note this differs from Finding P's `convert pdf to kindle` seed (which surfaced 67% reverse because the verb "convert" itself is reverse-biased in user intent). The `kindle to pdf` seed surfaces both directions in their natural ratio — forward dominates by ~4:1, but reverse is still material at 2,450/mo.

**Net implication:** Unit 5's eat-the-bounce + outbound redirect addition is now data-validated as the right response to reverse intent (not a competing page). The Unit 5 modification should be sized as a meaningful section (~250-400 words), not a token disclaimer, given the 2,450/mo reverse-direction stream.

### Action items added/revised

- **EB-303 Phase 2 Unit 5:** REAFFIRMED — add eat-the-bounce + outbound redirect section, ~250-400 words, with explicit Calibre link. **DROP** the previously-floated separate `/guides/convert-kindle-to-pdf` page candidate (SERP too dense).
- **EB-303 Phase 2 Unit 3 FAQ:** REAFFIRMED original Day 2 routing — `kindle email address` stays as FAQ extension, not standalone landing.
- **EB-241 methodology improvement (fourth one):** **SERP audit before promoting any candidate page.** KD alone is insufficient for product-feature-lookup queries (Amazon owns canonical answers) AND for queries where dedicated conversion-tool vendors have entrenched landing pages. Add SERP-audit-before-candidacy to the Phase 1 process checklist.

---

## Session 4 final sweep — overlooked Phase 2 forward-direction targets + EB-309 anchor data (2026-05-20 late evening)

**Reports run (5 queries — addressing decision-relevant gaps in the morning + evening sweeps; pulled forward 2 of 3 Day 5 plan items):**

1. `phrase_organic` on `how to send pdf to kindle` top 20 (~200 units) — the 1,600/mo forward-direction flagship, NOT currently a Phase 2 anchor
2. `phrase_kdi` on top 6 forward-direction `kindle to pdf` questions (~300 units) — measures KD on 5,040/mo of forward-direction volume Unit 5 doesn't currently target
3. `phrase_organic` on `e999 - send to kindle internal error:` (with colon, 2,400/mo) top 20 (~200 units) — Day 5 plan item, pulled forward
4. `phrase_organic` on `send to kindle doesn't work` (480/mo) top 20 (~200 units) — Day 5 plan item, pulled forward
5. `backlinks_anchors` on kindlepreneur.com top 30 (~300 units) — EB-309 outreach pattern intelligence per Finding U's "editorial-outreach analog" classification

**Units consumed (final sweep):** ~1,200. Day 4 total: ~7,400 / 10K (~74%).

### Findings

#### FINDING X — Forward-direction question family KD scan: mixed difficulty, one true easy

| Keyword | Volume | KDI | Comment |
|---|---|---|---|
| how to send a pdf to kindle | 720 | **28** | **Easiest measurable in the set** — send-verb is the easy pattern |
| how to send pdf to kindle | 1,600 | **32** | Highest volume in the entire forward-direction family; moderate KD but DENSE SERP (Finding Y) |
| how to put pdf on kindle | 880 | **38** | Moderate; H3 candidate |
| how to load pdf in kindle | 480 | 41 | Harder tail |
| how to add pdf to kindle | 880 | **44** | Harder than expected — Adobe + Smallpdf own this anchor variant |
| how to upload pdf to kindle | 480 | 0 (no SERP signal) | Per skill guidance: KD=0 = no data, NOT easy. Needs manual SERP audit before counting. |

**Combined measurable forward-direction volume: ~3,560/mo across 5 keywords** (the KD=0 480-vol entry excluded). For reference, Phase 2 Unit 5's current primary anchor `convert pdf to kindle format` is 590/mo (per Day 2 Finding I) — Unit 5 is targeting **~17% of the addressable forward-direction lexical-variant volume.**

**The send-verb pattern (`how to send`) is uniformly easier than other verbs** (KD 28-32 vs add/load/put/upload at 38-44+). This mirrors the Day 2 EPUB Finding S pattern — workflow-verb lexical diversity matters for ranking, but the specific verb choice matters too.

#### FINDING Y — `how to send pdf to kindle` (1,600/mo) SERP is DENSE — KD 32 understates pressure

| Result class | Top 20 count | Notes |
|---|---|---|
| Amazon first-party | **5/20** | sendtokindle/email landing (#1), sendtokindle landing (#3), Amazon Help (#14), Amazon UK Forum (#6), Amazon Forum (#8) |
| Authority brand landing | 1/20 | **Adobe Acrobat dedicated landing (#4)** — same pattern as the reverse-direction SERP |
| Authority tech publication | 3/20 | TechRadar (#11), ZDNet (#16, #20) |
| Paid conversion tool vendors | 3/20 | Smallpdf (#10), Wondershare ×2 (#17, #18) |
| Forum / Q&A / social | 5/20 | Reddit, Quora, Facebook, TikTok, plus 2 Amazon Forum already counted |
| Video | 4/20 | YouTube ×4 |

**This is the THIRD example today of KD-underestimating-difficulty when entrenched vendors own dedicated landing pages.** Amazon owns positions 1+3 (sendtokindle landing pages — first-party canonical answers), Adobe at #4, TechRadar + ZDNet authority tech pubs present, plus 3 paid conversion vendors. The KD-32 score reflects domain-authority computation, not the realistic SERP-displacement difficulty.

**Realistic ranking ceiling: top-10.** Positions 5-9 are forum/social/video — displaceable. Top-3 against Amazon's first-party + Adobe's dedicated landing is implausible regardless of content depth.

**Strategic implication for Unit 5:** the 1,600/mo `how to send pdf to kindle` query IS worth targeting as a Unit 5 H1/H2 anchor — capturing position 5-9 at 1,600/mo = ~80-160 visits/mo (~10× the current `convert pdf to kindle format` 590/mo top-10 capture rate). But size the expectation against position-5 traffic share, not position-1.

#### FINDING Z — e999 with colon variant is IDENTICAL to bare e999 SERP

Direct comparison: the `e999 - send to kindle internal error:` (2,400/mo) top-20 SERP is bit-identical to the bare `e999 - send to kindle internal error` (2,900/mo) SERP I ran in the morning sweep. Same 20 URLs in same order. **The colon is a typo proxy of the same query — Google de-duplicates them at the SERP level.**

Recombined volume: e999 cluster is **5,300/mo with a single SERP profile**, not two separate competitive landscapes. The EB-303 Tier 2 troubleshooting page only needs to rank for the bare-variant — Google will serve the same SERP to both query phrasings.

#### FINDING AA — `send to kindle doesn't work` (480/mo) SERP is LESS wide-open than e999

| Result class | Top 20 count |
|---|---|
| Amazon first-party | 4/20 (sendtokindle/email at **#3**, Amazon Forum ×3) |
| Publishing-tool help | 5/20 (NetGalley ×2, Libby ×2, MyBookCave) |
| Forum / Q&A / social | 9/20 (Reddit, Facebook ×2, Quora, MobileRead, Hacker News, JustAnswer ×2) |
| Paid conversion tool vendor | 1/20 (Swifdoo at #12) |
| Video | 2/20 |

**Amazon's sendtokindle/email landing is at position #3 here, vs position #15 on the e999 SERP.** The generic "doesn't work" query surfaces Amazon's authoritative product landing page; the error-code-specific e999 query doesn't.

**Implication for EB-303 Tier 2 troubleshooting page:** anchor on the e999-specific keywords (where Amazon's authority signal is weakest), with `send to kindle doesn't work` as a secondary H3 anchor only — NOT the primary target. The page title should foreground "e999" / "internal error" / specific-error-code language.

#### FINDING BB — Kindlepreneur's link-acquisition playbook: TOOLS + CONTENT TITLES + AUTHOR ATTRIBUTION (EB-309 strategy)

Top 30 anchor texts on kindlepreneur.com reveal a 3-vector organic-link pattern:

| Vector | Example anchors | Mechanism |
|---|---|---|
| **TOOL_LINK (4 anchors, 73 domains)** | "kindle best seller calculator", "amazon sales rank calculator", "book description generator", "booktagger.com" | Free utility tools → other sites link to the tool by name when recommending it |
| **CONTENT_TITLE (6 anchors, 56 domains)** | "how to get book reviews without begging", "how to title a book", "save the cat story structure definition and beat sheet", "scrivener review", "how to make an audiobook", "deep dive into typesetting" | Long-tail article titles → sites that reference the article use the title as anchor text |
| **AUTHOR_ATTRIBUTION (2 anchors, 112 domains)** | "dave chesson", "dave chesson has pulled together a useful list" | Personal brand → mentions of the founder/author create non-replicable link signal |

Plus visible-but-non-actionable patterns:
- Brand mentions ("kindlepreneur") at 39K backlinks across 861 domains — this is just earned brand awareness; not a strategy
- SPAM_PBN (3 anchors, ~1,000 backlinks combined — Telegram SEO link networks) — kindlepreneur isn't fully clean either. EB-309 doesn't need to compete with this volume.

**EB-309 strategic insight: leafbind IS the tool.** The TOOL_LINK vector is structurally available to leafbind because the product itself is a free conversion utility. The replicable acquisition path:

1. **Make the tool linkable** — distinctive URL pattern, named feature labels, clear "this is the leafbind PDF-to-KFX converter" framing on the homepage so referencing sites have something to anchor on
2. **Title pillar pages to be quoted** — Phase 2 + Phase 3 titles should be memorable and distinctive (avoid generic "How to send PDFs to your Kindle" titles — prefer "The PDF-to-Kindle field guide for Kindle Scribe owners" or similar)
3. **Author byline + personal brand** — Joe should byline pieces, develop Substack / podcast / X / Bluesky presence in the ebook-conversion niche. The "dave chesson" anchor pattern (419 backlinks across 111 domains) is a non-replicable competitive moat for kindlepreneur — leafbind needs its own version.

**EB-309 Phase 4a AC revision:** target 15-20 quality editorial links across the 3 vectors (TOOL_LINK, CONTENT_TITLE, AUTHOR_ATTRIBUTION). Skip directory submissions and any anchor-text-stuffed link-buying. The kindlepreneur anchor data shows volume-stuffed approaches (PBN networks at ~1K backlinks/anchor) coexist with clean editorial wins but don't substitute for them.

### Action items added/revised

- **EB-303 Phase 2 Unit 5 — NEW H1/H2 anchor:** add `how to send pdf to kindle` (1,600/mo, KD 32) as a primary anchor. Currently un-targeted despite being 2.7× the volume of the existing primary target.
- **EB-303 Phase 2 Unit 5 — secondary H3 anchors:** add `how to send a pdf to kindle` (720/mo, KD 28 — easiest measurable), `how to put pdf on kindle` (880/mo, KD 38). Defer `how to add` / `how to load` (KD 41-44) and `how to upload` (KD=0, needs manual SERP review).
- **EB-303 Phase 3b Tier 2 troubleshooting page — title language:** anchor on e999 / "internal error" / specific-error-code phrasings. De-emphasize `send to kindle doesn't work` (Amazon's #3 on that SERP is harder to displace than the e999-specific SERP).
- **EB-303 Phase 3b Tier 2 troubleshooting page — combined target volume:** e999 cluster is 5,300/mo across both phrasings (colon-de-duplicated per Finding Z), plus the auth-failure variant at 1,000/mo (KD=0, manual SERP review needed), plus `send to kindle doesn't work` 480/mo as secondary anchor. Total realistic addressable: ~5,300-6,800/mo on a single page.
- **EB-309 Phase 4a — REVISED with concrete vectors:** target 15-20 editorial links across 3 vectors (TOOL_LINK, CONTENT_TITLE, AUTHOR_ATTRIBUTION). Drop directory submissions and any volume-stuffed approaches. Joe-byline + personal-brand development is the long-leverage move; tool framing on the leafbind homepage is the short-leverage move.
- **EB-241 methodology improvement (fifth one):** Day 4 surfaced **3 separate examples** of KD-understating-SERP-difficulty when entrenched vendors own dedicated landing pages (`kindle email address` Amazon, `how to convert kindle books to pdf` Adobe + 6 vendors, `how to send pdf to kindle` Amazon + Adobe). The pattern is: any query Google interprets as a product-feature lookup will surface vendor-owned canonical answer pages that out-rank content authority. **Add to Phase 1 process: explicitly flag product-feature-lookup queries and apply a +20 KD penalty before scoring.**
- **EB-308 budget summary:** Day 4 ~7,400 / 10K (~74%). Day 5 collapses to just the EB-241 final synthesis comment (no further API calls needed). Position Tracking re-run on Day 5 is not necessary — today's snapshot already captured 5 days of data.

### What's left for Day 5 (final trial day, 2026-05-21)

- **EB-241 final synthesis comment** — post the trial-sprint synthesis as a comment on the parent SEO program ticket. No API calls.
- **Optional:** one more Position Tracking snapshot purely for "did indexation finally begin" check (~800 units). Low-EV since 5 days of "out of top 100" is unambiguous — leafbind isn't in Semrush's index after 8 days, and one more day won't change the picture. Defer unless Joe specifically wants the data point.

---

## Final synthesis

Sprint window: 2026-05-17 → 2026-05-20 (Day 1 → Day 4). Trial expiry: 2026-05-23. Total units consumed: ~17,500 across 4 days of a ~40K trial budget (~44%). All four daily caps were respected, no surprise rate-limit hits.

The sprint was designed as 3 sessions of expensive Pro-tier reports across Days 1-3 of the trial; in practice it ran across 4 days (5 sessions counting the same-day Session 2 continuation per the [[feedback-split-daily-refresh-resources]] insight from Day 1) because each day's findings opened new questions worth measuring. Position Tracking is running free through trial expiry; the campaign has 5 days of "out of top 100" baseline for all 8 Phase 2 targets, confirming Semrush hasn't indexed leafbind.io yet (site is 8 days old as of Day 4).

### The five highest-leverage outcomes

#### 1. EPUB-on-Kindle pillar is data-validated as a Tier 1 EB-303 candidate

The Day 2 `phrase_related` run on `send to kindle` (90,500/mo root) surfaced an 8-keyword EPUB-direction cluster totaling ~6,520/mo that Phase 1 keyword discovery missed entirely. Day 2 afternoon's `phrase_questions` on the broader `kindle epub` seed expanded this to **~18,350/mo across 50 question variants**, organized in 4 authoring buckets: capability questions (~10,400/mo, KD 20-35, Wave 1 ranking expectation), workflow verbs (~3,300/mo, KD 47-57, Wave 2), conversion-specific (~250/mo, direct product-fit), and hybrid (~650/mo, bridge). The flagship `does kindle support epub` has the highest commercial signal in the entire trial dataset ($14.12 CPC, KD 20).

#### 2. Send-to-Kindle troubleshooting page is the alternative Tier 1 candidate — opposite tradeoff

The e999 error cluster is **5,300/mo on a single SERP** (colon variants dedupe — Finding Z), with KD 15-25 across all measurable variants. The SERP is **the most wide-open opportunity surfaced in the entire trial**: zero authoritative sources in top 20 (Amazon UK Help at #15 only), 13 forum/Q&A results, 5 small SEO-grab troubleshooting blogs, and ZERO conversion-tool competitors. The user intent at search time is peak commercial — a failed Send-to-Kindle is exactly when users would try a third-party tool like leafbind.

**EB-303 Phase 3b decision point:** EPUB pillar (volume play, 18,350/mo, harder KD curve) vs troubleshooting page (commercial-intent play, 5,300/mo, easier KD, peak conversion moment). Both defensible Tier 1. Recommend troubleshooting page first if conversion-rate-to-paid-tier matters more than top-of-funnel traffic for the next 90 days; EPUB pillar first if the priority is establishing topical authority in the Kindle/ebook niche broadly.

#### 3. Phase 2 Unit 5 needs significant anchor expansion AND a reverse-direction redirect section

The Day 4 final sweep measured KD on the forward-direction question family for the first time. `how to send pdf to kindle` (1,600/mo, KD 32) is **2.7× the volume of Unit 5's current primary target** (`convert pdf to kindle format`, 590/mo) and isn't currently a Phase 2 anchor. `how to send a pdf to kindle` (720/mo, KD 28) is the easiest measurable in the family. Combined measurable forward-direction volume is ~3,560/mo across 5 keywords — Unit 5 currently targets ~17% of its addressable lexical-variant surface.

Separately, intent contamination is real and quantified: 67% reverse-direction (Kindle→PDF) on the `convert pdf to kindle` question SERP, ~25% reverse on the natural `kindle to pdf` seed. Unit 5 needs an explicit eat-the-bounce + outbound-Calibre-link section (~250-400 words) — NOT a competing reverse-direction page, since the reverse-direction SERP is dominated by Adobe at #1 plus 6 entrenched paid conversion vendors (Wondershare, Smallpdf, EaseUS, PDFMate, Systools, Epubor).

#### 4. Competitive landscape reframed three times during the sprint

Phase 1's competitor hypothesis (Reddit + goodreader + calibre-ebook + the-ebook-reader) was 25% correct — only Reddit appeared in measured SERPs (Day 1). Real direct competitors:

- **pdf2kindle.com** — single-keyword-dependent (50% of their traffic on one query), structurally displaceable (Day 1)
- **smallpdf / online2pdf** — generalist PDF tools with ZERO ebook/kindle/epub keywords; NOT direct competitors despite earlier framing (Day 2 afternoon)
- **EPUB-pillar competitors** (kindlepreneur, takecontrolbooks, digitalpublishing101, bookfunnel) — small content sites, structurally displaceable per the SERP content-quality-gating pattern (Day 2 afternoon)

#### 5. EB-309 link-acquisition strategy now has concrete vectors instead of "30 quality targets"

Day 4 final sweep's `backlinks_anchors` on kindlepreneur (the editorial-outreach analog) revealed 3 organic-link acquisition vectors:

- **TOOL_LINK** (free tools other sites reference by name) — leafbind IS the tool; structurally available without outreach if the product page is link-anchorable
- **CONTENT_TITLE** (distinctive long-tail article titles used as anchor text) — Phase 2 + Phase 3 pillar pages should have memorable, link-anchorable titles
- **AUTHOR_ATTRIBUTION** (founder-named anchors — "dave chesson" earned 419 backlinks across 111 domains) — Joe needs to develop personal-brand presence (Substack / podcast / Bluesky)

Plus the negative finding: kindlepreneur, takecontrolbooks, and bookfunnel each have STRUCTURALLY DIFFERENT backlink profiles (editorial / academic-publisher / mass-author-platform — Day 4 Finding U). The bookfunnel model is not replicable for a conversion utility. EB-309 outreach should focus on the kindlepreneur model only.

### Methodology improvements (5 — for future SEO sprints)

1. **`phrase_related` on broad anchors AT START of Phase 1**, not as Phase 3 expansion. The 6-hour Phase 1 + LowFruits triage that birthed EB-241 never surfaced the EPUB cluster; one `phrase_related` call on `send to kindle` did. (Day 2)

2. **SERP feature columns in Phase 1 keyword tables.** AIO presence on all 8 Phase 2 keywords + universal PAA means click flow is ~30-40% AIO/PAA, not 100% position #1. This changes content structure (first-paragraph definitive answer for AIO citation, Q&A schema for PAA) and ranking strategy. (Day 2 afternoon)

3. **Position Tracking at Phase 1 Day 1, not Phase 3.** A 6-week pre-launch tracking window gives a real baseline; "we just launched and now we're measuring" gives no rank-delta dataset. (Day 2 afternoon)

4. **SERP audit before promoting any candidate page** — hard gate, not a follow-up. Surfaced because the morning sweep promoted both `kindle email address` (turned out Amazon owns canonical) and a reverse-direction guide candidate (turned out Adobe + 6 vendors own that SERP). (Day 4 evening, Corrections 1 + 2)

5. **+20 KD penalty for product-feature-lookup queries.** Three separate Day 4 SERP audits showed KD understating difficulty when entrenched vendors (Amazon, Adobe) own dedicated landing pages. Semrush's KD computes against domain-authority signal; first-party canonical answers out-rank content authority regardless of competitor KD. (Day 4 final sweep, Findings Y + AA reinforce Corrections 1 + 2)

### Action items routed to other tickets

**To EB-303 (Phase 3 content prioritization):**

- Phase 3b Tier 1 decision: **pick** EPUB pillar vs troubleshooting page launch sequence (both validated; recommend troubleshooting page first per conversion-intent argument)
- Phase 2 Unit 5 expansion: add `how to send pdf to kindle` (1,600/mo) as primary H1/H2 anchor; add `how to send a pdf to kindle` + `how to put pdf on kindle` as H3s
- Phase 2 Unit 5 reverse-direction section: ~250-400 words eat-the-bounce + outbound Calibre link
- Phase 2 Unit 3 mega-guide: cross-check coverage against `phrase-questions-pdf-to-kindle.csv` for missing H3 anchors on high-volume variants (`how to load`, `how to upload`, `how to read pdf on kindle` etc.)
- Phase 2 Unit 5 content depth audit vs pdf2kindle's one-pager (Day 1 Finding 2)
- Phase 3 authoring guidance: pillar copy must support AIO citation (first-paragraph definitive answer + structured data) and PAA capture (Q&A schema + Q-format H3s)
- Phase 3b Tier 2 troubleshooting page anchor language: e999-specific / "internal error" / error-code phrasings (Amazon's authority is weakest there). De-prioritize `send to kindle doesn't work` (Amazon's sendtokindle/email landing is at #3 on that SERP).
- Phase 3b Tier 2 troubleshooting page realistic scope: 5,300/mo e999 cluster as primary + 1,000/mo auth-failure as secondary (KD=0, manual SERP review first) + 480/mo "doesn't work" as tertiary
- Phase 3b TIER 2 FAQ extensions (NOT standalone landings): `kindle email address` (1,000/mo, on Unit 3) + `what file type does kindle use` (880/mo, on EPUB pillar)
- Phase 3 sequencing: EPUB pillar before troubleshooting page is the volume call; troubleshooting page before EPUB pillar is the conversion call

**To EB-309 (Phase 4 link distribution):**

- Phase 4a AC revision: target 15-20 editorial links across 3 vectors (TOOL_LINK / CONTENT_TITLE / AUTHOR_ATTRIBUTION)
- Drop directory submissions and volume-stuffed link acquisition
- Drop smallpdf as a link-prospecting target (Day 2 Finding M — generalist PDF tool, not ebook-adjacent)
- Prioritize the kindlepreneur model (editorial outreach + Substack ecosystem); deprioritize the bookfunnel model (author-platform mass linking — structurally non-replicable for a utility tool)
- Joe-byline + personal-brand development is the long-leverage AUTHOR_ATTRIBUTION vector
- Tool-framing on the leafbind homepage is the short-leverage TOOL_LINK vector

**To EB-241 (parent SEO program):**

- Add the 5 methodology improvements to the Phase 1 process checklist for future SEO sprints (e.g. SecondBrain SB autobook SEO, future tools)
- Position Tracking campaign continues running free post-trial — establish review cadence (weekly during Phase 3 launch window, monthly thereafter)

**To EB-308 (this ticket):**

- Mark Done after Day 5 final synthesis comment lands on EB-241
- Update `position-tracking-campaign.md` campaign-ID format (already done — composite `29685400_4805618`)

---

## Draft EB-241 comment (post 2026-05-21)

The comment below is the digest version of the synthesis above, sized for Jira readability. To post: copy from the marker line to the next marker line, paste as a new comment on EB-241.

> -----BEGIN EB-241 COMMENT-----

## EB-308 Semrush trial sprint — final synthesis (4 days, ~17,500 units)

**Sprint window:** 2026-05-17 → 2026-05-20. **Trial expiry:** 2026-05-23. **Full doc:** `docs/seo/eb-241-semrush-trial-sprint-2026-05.md`. **Raw artifacts:** `scratch/semrush-trial-2026-05/`.

### Top 5 outcomes

**1. EPUB-on-Kindle pillar validated as Tier 1 EB-303 candidate** — ~18,350/mo across 50 question variants in 4 authoring buckets (capability KD 20-35 / workflow verbs KD 47-57 / conversion-specific / hybrid). Flagship `does kindle support epub` has highest commercial signal in entire trial ($14.12 CPC, KD 20). Phase 1 missed this entire cluster — discovered Day 2 via `phrase_related` on the 90,500/mo `send to kindle` root.

**2. Send-to-Kindle troubleshooting page is the alternative Tier 1 candidate (opposite tradeoff)** — e999 error cluster is **5,300/mo on a single SERP** with KD 15-25. SERP is the most wide-open opportunity in the trial: zero authoritative sources, 13 forum/Q&A in top 20, 5 small SEO-grab blogs, ZERO conversion-tool competitors. Peak commercial intent (failed Send-to-Kindle = exact moment user wants a third-party tool). **EB-303 decision point: EPUB pillar (volume) vs troubleshooting page (conversion) for first Tier 1 launch.**

**3. Phase 2 Unit 5 needs significant anchor expansion + reverse-direction redirect** — `how to send pdf to kindle` (1,600/mo, KD 32) is **2.7× current Unit 5 primary target volume** and not currently anchored. Plus: 67% reverse-direction intent contamination on the `convert pdf to kindle` SERP needs a ~250-400 word eat-the-bounce + Calibre-outbound section. NOT a separate reverse-direction page (Adobe + 6 entrenched paid vendors own that SERP).

**4. Competitive landscape reframed three times during the sprint** — Phase 1's competitor guesses were 25% correct (Reddit confirmed, others not). Real direct competitors: pdf2kindle (single-keyword-dependent, displaceable), small content sites (kindlepreneur / takecontrolbooks / bookfunnel) for EPUB pillar. Smallpdf and online2pdf are generalist PDF tools with zero ebook-adjacent keywords — NOT direct competitors.

**5. EB-309 link-acquisition has concrete vectors now** — Day 4 `backlinks_anchors` on kindlepreneur revealed 3 organic-link patterns: **TOOL_LINK** (leafbind IS a tool — structurally available), **CONTENT_TITLE** (distinctive article titles as anchor text), **AUTHOR_ATTRIBUTION** (Joe-byline + personal brand). Drop directory submissions and volume-stuffed approaches. Drop the bookfunnel-style author-platform model — structurally non-replicable for a conversion utility.

### 5 methodology improvements for future SEO sprints

1. **`phrase_related` on broad anchors AT START of Phase 1** — single call surfaced the 18,350/mo EPUB cluster that 6 hours of Phase 1 work missed
2. **SERP feature columns in keyword tables** — AIO on 100% of Phase 2 keywords means content structure (first-paragraph definitive answer + Q&A schema) is a ranking factor, not optional
3. **Position Tracking at Phase 1 Day 1, not Phase 3** — needs 6-week pre-launch baseline to be useful
4. **SERP audit before promoting any candidate page** — hard gate; KD alone is insufficient
5. **+20 KD penalty for product-feature-lookup queries** — 3 separate examples in Day 4 of Semrush KD understating difficulty when Amazon / Adobe own dedicated landing pages

### Routed to other tickets

- **EB-303 Phase 3:** EPUB-vs-troubleshooting Tier 1 decision; Unit 5 anchor expansion (`how to send pdf to kindle` + 2 H3s); Unit 5 reverse-direction section; FAQ extensions (`kindle email address`, `what file type does kindle use`); Phase 3 authoring guidance for AIO + PAA
- **EB-309 Phase 4:** AC revised to 15-20 editorial links across TOOL_LINK / CONTENT_TITLE / AUTHOR_ATTRIBUTION vectors; drop bookfunnel-style mass-platform model; drop smallpdf prospecting
- **EB-241 (this ticket):** add 5 methodology improvements to Phase 1 process checklist; establish Position Tracking review cadence (weekly during Phase 3 launch, monthly after)
- **EB-308:** ready to close after this comment lands

### Position Tracking status (running through trial expiry)

5-day baseline (2026-05-17 → 2026-05-21): all 8 Phase 2 keywords "out of top 100" — leafbind not yet in Semrush index (site is 8 days old as of Day 4). Campaign continues free; rank-delta dataset begins when indexation starts.

> -----END EB-241 COMMENT-----

---

## Day 5 (2026-05-21) action checklist

- [x] Post the draft EB-241 comment above to https://jlfowler1084.atlassian.net/browse/EB-241 — DONE 2026-05-22 (comment 19299)
- [x] Transition EB-308 to Done — DONE 2026-05-22. Comment: "Sprint complete. Final synthesis posted to parent EB-241. Full doc: `docs/seo/eb-241-semrush-trial-sprint-2026-05.md`. ~17,500 of ~40K trial budget consumed; all 5 methodology improvements logged. 5 Tier-1/2 action items routed to EB-303 (content); 4 action items routed to EB-309 (links). Position Tracking campaign continues free post-trial; indexation not yet begun (site is 8 days old)."
- [ ] (Optional, ~800 units) Final Position Tracking snapshot for the "did indexation finally begin" check — low EV but cheap; only run if curious about the 9-day data point
- [ ] (Optional) Snapshot the `scratch/semrush-trial-2026-05/` directory state — consider whether to keep all CSVs, archive them, or move the most-referenced ones into `docs/seo/`

---

## Post-trial Position Tracking retention — VERIFIED (2026-05-22)

Closes the open question raised in Session 4 Day 4 ("if EB-303 wants ongoing tracking after the trial, the campaign must be checked against Semrush's free-tier campaign retention policy").

**Verdict: the campaign survives the trial → free-tier downgrade, provided the trial is *cancelled* (lapses to free) rather than the account deleted.**

- Semrush free plan retains **1 project** and **up to 10 tracked keywords**; keywords beyond 10 go inactive on downgrade.
- Our campaign (Project `29685400` / Campaign `4805618`) tracks **8 keywords** in a **single project** — both within free-tier limits, so the campaign and its accumulated rank history persist.

**Caveats:**
1. Update cadence likely drops from daily (Pro/trial) to a slower free-tier refresh. History is preserved; refresh rate slows. Acceptable for EB-303 Phase 3c (~2026-06-27 re-baseline) and EB-309 Phase 4d, which are periodic.
2. Confirm only the one leafbind project exists. The trial allowed up to 5 projects; the free plan keeps 1. If a second project was created, verify the leafbind project is the retained one.

**Action for Joe:** cancel the paid trial (stop the auto-charge) before 2026-05-23 — do NOT delete the account. The 5-day baseline + ongoing free-tier snapshots remain available to the downstream re-baseline tickets.

Sources: [Semrush Help — Position Tracking limits](https://help.semrush.com/FAQ/en/articles/4576328-what-are-the-limits-of-position-tracking), [Semrush — free account capabilities](https://www.semrush.com/blog/what-can-i-do-with-a-free-account-from-semrush/).
