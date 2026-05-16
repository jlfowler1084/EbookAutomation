# EB-241 Phase 1 — Keyword Discovery Execution Plan

**Date:** 2026-05-16
**Ticket:** EB-241 (Phase 1 only)
**Scope:** How we execute the discovery work the EB-241 ticket describes — produce the prioritized keyword list, SERP analysis, and competitor audit that the rest of the SEO program will consume.
**Deliverable of Phase 1:** `docs/marketing/seo-discovery-2026-05.md` (per EB-241 AC #1)

---

## TL;DR

Phase 1 is 4-6 hours of work split into 5 sub-phases. Most of it is autonomous (Claude executes), one decision is Joe-only (paid-tools vs free-path), and one is blocked by EB-280 (GSC must be verified for query data to flow). With the paid-tool path and GSC unblocked, the discovery doc lands in one focused session.

The output is a prioritized list of 30-50 long-tail Kindle Scribe keywords, each tagged with:
- SERP weakness score (which terms have winnable top-10)
- Monthly search volume
- Existing competitor coverage gap
- Recommended content type (pillar guide / comparison / `/convert/*` page)
- Priority tier (P0 = ship in next 2 weeks, P1 = ship in 4-6 weeks, P2 = backlog)

---

## Prerequisites

| Prerequisite | Status | Owner | Unblocks |
|---|---|---|---|
| GSC verified + sitemap submitted | ⏳ Joe — ~10 min browser work (see EB-280) | Joe | 1d. Real query data (vs guessed seeds) |
| Tooling decision (paid path vs free path) | ⏳ Joe — one-time decision | Joe | 1a-1c with quality fidelity |
| Indexation actually progressing | ⏳ ~3-7 days after Request Indexing | Google | 1d. GSC starts showing query impressions |
| Cloudflare proxy state stable | ✅ Done — apex+www are DNS-only and indexable | — | — |

**None of these block the planning work — only the execution of it.**

---

## 1a. Tooling Decision (Joe)

Two viable paths. Joe picks one.

### Path A — Paid tools (recommended)

| Tool | Purpose | Cost |
|---|---|---|
| LowFruits.io | SERP weakness scoring on 30-50 candidates | $30 one-time (lifetime credits) |
| Mangools KWFinder | Keyword difficulty + SERP snapshot | $30/mo, trial available |
| Keywords Everywhere | Volume data inline in Google SERPs | $15/year entry tier |
| Also Asked | "People Also Ask" tree harvest | Free tier sufficient |
| Ahrefs Webmaster Tools | Backlinks + own-domain audit | Free |
| Google Search Console | Real query/click data on our own domain | Free (blocked by EB-280) |

**Total cost: ~$50** for the first month, drops to ~$15/year after if Mangools trial is cancelled.

**Fidelity:** High. LowFruits' SERP weakness scoring is the single most valuable signal for a new-domain weak-SERP hunt.

**Execution time once tools are bought: ~3-4 hours.**

### Path B — Free path

| Tool | Substitute for | Method |
|---|---|---|
| Manual SERP review via Playwright | LowFruits | Claude fetches Google SERP for each candidate, classifies top-10 by domain type (forum/Reddit/low-DA blog = winnable) |
| Google autocomplete + PAA scraping | Mangools/Also Asked | Claude fetches Google for each seed, harvests autocomplete and "People Also Ask" branches |
| Manual volume estimation | Keywords Everywhere | Claude uses Google Trends API for relative interest; absolute volume left as a TBD |
| Ahrefs Webmaster Tools | Same as Path A | Free |
| GSC | Same as Path A | Free, blocked by EB-280 |

**Total cost: $0.**

**Fidelity:** Medium. SERP weakness scoring is manual and slower; absolute volume data is fuzzy.

**Execution time: ~5-6 hours.** Worth it only if Joe wants to defer the tool purchase decision.

**Recommendation: Path A.** $50 to compress 6 hours into 4 and increase output fidelity is a strong ROI for a step that determines the next 4-6 weeks of content production.

---

## 1b. Seed Expansion (Claude, ~30 min)

Start from EB-241's 12 seed phrases. Expand to 30-50 candidates using:

- **Google autocomplete** — for each seed, fetch Google's autocomplete suggestions (typed-prefix variants)
- **Also Asked / PAA** — for each seed, harvest 3-5 question-shaped variants
- **Synonym/proximity expansion** — programmatically swap entity terms ("kindle scribe" → "kindle paperwhite", "kfx" → "azw3", "academic" → "research" / "textbook" / "papers")
- **Long-tail compounding** — add modifiers like "free", "online", "best", "without amazon", "without losing formatting"

**Output:** raw candidate list in `scratch/keyword-candidates-raw.csv` with columns: `seed_phrase`, `expansion_source`, `expansion_method`.

**Owner:** Claude. No tool dependency.

---

## 1c. SERP Weakness Scoring (Path-dependent, 2-3 hours)

For each of the 30-50 candidates, score the SERP weakness — i.e., are the current top-10 winnable for a new domain?

**Path A (LowFruits):** Drop candidates into LowFruits.io. Filter to terms where ≥5 of top-10 are forum posts, Reddit threads, or DA<25 blogs. Tag each candidate with `serp_weakness_score` (1-10, 10 = most winnable).

**Path B (manual):** Claude fetches Google SERP for each candidate via Playwright, classifies each top-10 result by domain type, computes a weakness score using the same heuristic. Slower but produces the same data structure.

**Output:** `scratch/serp-weakness.csv` adding columns: `weakness_score`, `top10_breakdown` (forum/Reddit/low-DA/medium-DA/high-DA counts).

**Filter for next step:** keep terms with `weakness_score ≥ 6`. Discard the rest (they're not winnable for a new domain in <12 months).

---

## 1d. Volume + Intent Validation (1 hour)

For the surviving candidates from 1c:

**Path A:** Use Mangools KWFinder for monthly search volume. Use Keywords Everywhere as a sanity check.

**Path B:** Use Google Trends for relative interest; flag candidates where Trends shows zero/declining interest. Skip absolute volume; rely on relative interest + SERP weakness as a proxy.

**GSC data injection** (requires GSC unblocked): once GSC has 7+ days of impression data, cross-reference candidates against actual queries Google associates with leafbind.io. Promote any candidate that has real GSC impressions.

**Output:** `scratch/keyword-shortlist.csv` adding columns: `monthly_volume` (or `trend_score` for Path B), `intent_classification` (informational/commercial/transactional), `gsc_impressions_30d` (if available).

**Filter:** keep `monthly_volume ≥ 30 AND weakness_score ≥ 6`. Should yield 20-40 keywords for the prioritized list.

---

## 1e. Competitor Audit (1 hour)

For each shortlisted keyword, identify the top 3-5 competitors and audit their coverage gaps. This is the highest-leverage step — it tells us not just "what to write about" but "what to write that doesn't exist yet."

**Method:**
- For each P0-tier keyword: fetch the top-10 Google results, identify top 3-5 by relevance + DA
- For each competitor: note (a) what the page covers, (b) what the page misses, (c) how the leafbind page can differentiate
- Specific focus on: Kindle Scribe-specific content (most generic converters don't address Scribe), academic/research workflow (underserved), footnote linking quality (no one talks about this except us)

**Output:** `scratch/competitor-gaps.csv` per keyword: `top_competitors`, `their_content_strengths`, `their_content_gaps`, `differentiation_angle`.

**Owner:** Claude. WebFetch + analysis. No tool dependency.

---

## 1f. Synthesis Into Discovery Doc (1 hour)

Produce the actual EB-241 Phase 1 deliverable at `docs/marketing/seo-discovery-2026-05.md`. Structure:

```
# SEO Discovery — May 2026

## TL;DR
- N priority keywords identified
- Top 5 immediate content opportunities
- Recommended publishing order

## Methodology
- Tools used
- Filtering thresholds
- Data sources

## Prioritized Keywords (P0/P1/P2 tiers)
[Table: keyword | volume | weakness | intent | recommended page | priority]

## Top 5 Content Opportunities (next 2 weeks)
[Per opportunity: target keyword, recommended page type, competitor gap to exploit, draft outline]

## Competitor Landscape
[Per competitor: name, DA estimate, content strengths, gaps we can exploit]

## SERP Screenshots
[Per P0 keyword: screenshot of current top-10 with annotations]

## Recommended Next Steps
- Phase 2 (on-page audit) — apply learnings to existing /convert/* pages
- Phase 3 (content production) — write the top 5 from this list
- Phase 4 (link building) — Reddit + HN posts targeting the SERPs with the weakest first-page
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Kindle Scribe niche is *too* small (low absolute volume across all candidates) | Medium | Could pivot to "academic readers" broader frame | Quantify in 1d before committing to the niche |
| Top SERPs are dominated by Amazon/Reddit threads we can't outrank | Medium | Cuts winnable keyword count from 30-40 to 10-15 | Path A LowFruits scoring catches this in 1c; we don't waste effort on unwinnable terms |
| GSC stays empty for 3+ weeks (Google delays crawl) | Low | We can't do GSC-based query validation in 1d | EB-280 Joe-action shortens this; worst case we ship Phase 1 without GSC data and add it later |
| Mangools/LowFruits return inconsistent data | Low | Re-score in the other tool, take the lower of the two | Cross-check with manual SERP review on 3-5 random candidates |
| Joe doesn't approve tool purchase, must use Path B | Medium | Phase 1 takes 5-6 hours instead of 4 | Plan accommodates both paths; output schema is identical |

---

## Definition of Done

EB-241 Phase 1 is done when:

- [ ] `docs/marketing/seo-discovery-2026-05.md` committed
- [ ] 20-40 keywords prioritized in the doc with the full data set (volume, weakness, intent, competitor gaps)
- [ ] Top 5 content opportunities have draft outlines ready for Phase 3 execution
- [ ] At least 3 P0 SERPs screenshotted with annotations
- [ ] Competitor landscape section names at least 5 competitors with specific gap analysis

EB-241's Phase 2/3/4 unblock automatically once this lands.

---

## Handoff to Phases 2-4

Phase 1's output feeds:

- **Phase 2 (on-page audit)** — checklist applied to `/convert/*` pages with the new keyword targets
- **Phase 3 (content production)** — top 5 opportunities become 5 new tickets (one per article), each scoped like EB-281 was
- **Phase 4 (link building)** — the Reddit + HN posts target the keywords with the weakest SERPs identified in 1c

The existing EB-281 (Scribe pillar guide) already covers 1 of the likely Phase 3 pieces. Phase 1 will tell us if EB-281's keyword targeting is optimal or if it should be rescoped.

---

## Open Questions for Joe

1. **Path A or Path B?** (See section 1a — tool purchase decision)
2. **How many P0 keywords to commit to?** Default plan assumes top 5. If Joe wants top 10 or top 3, Phase 1 fidelity changes accordingly.
3. **Are there any keywords Joe wants explicitly excluded?** (e.g., we don't want to target "free PDF to KFX" because we want to position above the free tier; we don't want to target competitors' brand names directly, etc.)
4. **Does Joe want to add any seed phrases to EB-241's 12?** Now is the time — Phase 1b expansion uses these as the starting set.

---

## References

- EB-241 — parent SEO strategy ticket
- EB-280 — indexation diagnostic; GSC verification is the dependency for 1d
- EB-281 — Scribe pillar guide (already shipped; informs Phase 3 scope)
- EB-279 — homepage Kindle Scribe repositioning (already shipped; informs Phase 2)
- `~/.claude/skills/seo/SKILL.md` — SEO methodology (long-tail filter, citation-ready passage construction)
- EB-241 comment dated 2026-05-16 — modern tool recommendation stack
