---
ticket: EB-242
phase: Phase 2 — Channel strategy
date: 2026-05-15
author: Joe Fowler (channel research dispatched to compound-engineering:research:best-practices-researcher)
status: Phase 2 complete — Phase 3-5 (content calendar, email capture, analytics) deferred to sub-tickets
related:
  - EB-241 (SEO discovery — provides validated audience hierarchy + MobileRead gateway-authority finding)
  - EB-242 Phase 1 positioning (docs/marketing/positioning-2026-05.md) — provides messaging pillars + brand voice rules this strategy must respect
  - EB-233 (design system — visual brand)
  - project-leafbind-design-constraint (memory file — load-bearing brand voice rule)
---

# leafbind.io — Phase 2 Channel Strategy

## Purpose of this document

This is the canonical reference for **where leafbind shows up, in what order, and at what cost**. Consult it before:

- Committing time to any marketing channel
- Spending money on any paid channel (Google Ads, Reddit Ads, etc.)
- Deciding whether a one-shot event (HN Show HN, Product Hunt) is worth the powder
- Evaluating any new channel opportunity that surfaces ("should we try X?")

Companion doc: `docs/marketing/positioning-2026-05.md` defines **what we say**; this doc defines **where we say it**. Both apply to every channel decision.

## Scope and limitations

This document is **Phase 2 of EB-242** and refines the 12-row channel table the ticket shipped with. Phase 3 (content calendar), Phase 4 (email capture), Phase 5 (analytics) are explicitly deferred to follow-up sub-tickets.

### Data-quality constraints

- **No paid keyword/ad tools.** Cost data is from public channel docs, vendor benchmark posts, and channel-specific retrospectives. Citations in §6.
- **Solo-operator realism.** This plan assumes Joe runs marketing alone at ~8-10 hr/week. "Hire a content marketer" plans were rejected.
- **EB-241 strategic findings are load-bearing.** MobileRead-as-gateway-authority, Reddit's Google-indexing block, the locked KFX SERP, and the Calibre-plugin-friction wedge all changed priorities vs the ticket's first draft. Changes are flagged in §1.

## 1. Channel-by-channel analysis with priority changes

Audience match scoring: **Tight** = Segment 1 (Kindle Scribe academic) directly addressable; **Loose** = some overlap but not concentrated; **Wrong** = wrong audience or wrong intent. Priority changes vs the EB-242 ticket's first-draft table are flagged.

| # | Channel | Audience match | Est. cost (2026) | Time to 1st signal | Brand-fit risk | **Priority** | Change vs ticket |
|---|---|---|---|---|---|---|---|
| 1 | **MobileRead organic** | Tight | $0 (time only) | 30-90 days (trust-building) | None | **P1** | **NEW** — ticket missed it; EB-241 named it gateway authority |
| 2 | **Organic SEO** (EB-241 pillars) | Tight | $0 (time only) | 60-90 days | None | **P1** | Unchanged |
| 3 | **Reddit organic** (in-platform engagement only) | Tight (r/kindlescribe, r/kindle, r/GradSchool) | $0 (time only) | 7-30 days | Low (90/10 discipline required) | **P1** for engagement; **SEO-signal value removed** | **Re-scoped** — still P1 for engagement; ranking-signal value downgraded per EB-241 (Reddit blocks Google bots on r/kindlescribe so threads do not durably rank) |
| 4 | **Bluesky (academic clusters)** | Tight — academic Bluesky now hosts hundreds of thousands of researchers | $0 | 30-90 days | None | **P1.5** | **Upgraded from P2** — postdoc/grad-student visibility on Bluesky is structurally better than X for our audience |
| 5 | **YouTube creator outreach** (Kindle Scribe reviewers, productivity YouTubers) | Tight | $0 in free credits + creator gifting; no upfront cash at our scale | 30-60 days from pitch | Low if creator scripts | **P2** | Unchanged. Direct outbound reply rates run 15-25% per industry benchmarks. |
| 6 | **Hacker News Show HN** | Loose (technical audience but not Scribe-specific) | $0 | One-shot; front-page = 10K-50K visits | Low — HN tolerates calm framing | **P2** (single shot) | Unchanged. Keep powder dry until landing page + onboarding survive 50K spike. |
| 7 | **Product Hunt launch** | Medium (PH audience is makers/PMs, not Scribe academics; but indirect SEO + 5K-30K visit spike has value) | $0 launch cost; 100-500 visits/month tail for Top-5 finishers | One-shot | Low — PH copy norms align | **P2** (single launch) | Unchanged. Same rule as HN: do it once, do it after landing page is hardened. |
| 8 | **Reddit Ads** | Medium-high (niche subreddit targeting works) | CPM $3-$12 on niche subs (30-50% below platform median for 50K-200K-member communities); CPC ~$0.40-$1.50 on hobby/niche | Immediate | Medium | **P3** (test small) | Unchanged. Worth $200-$500 test on r/kindlescribe + r/kindle once organic-traffic conversion is baselined. |
| 9 | **Newsletter / Substack collabs** (academic-tooling Substacks) | Medium-tight | Free swap → $500-$2,000 per placement; CPM $20-$50 for mid-size niche | 30-60 days | None | **P3** | **Downgraded from P2** — paid placement is uneconomic at $2.99-$14.99 unit economics. Swap-only is realistic but slow. |
| 10 | **Google Ads** | Wrong intent (KFX SERP = DRM-removal seekers per EB-241) | "pdf converter" avg Search CPC ~$2.69; Q1 2026 average up to $2.96 | Immediate | High — paid-search format pulls us toward "convert NOW" urgency conflicting with calm voice | **Skip** | **Downgraded from P3 defer to Skip** — EB-241 confirmed locked SERP; spending on locked-intent traffic is negative-ROI |
| 11 | **Twitter/X Ads** | Low — X is no longer where academics live (Bluesky migration) | $$ | Immediate | High — format pushes for engagement-bait | **Skip** | Unchanged |
| 12 | **Facebook/Instagram Ads** | Low — wrong demographic concentration | $$$ | Immediate | High — visual platforms force lifestyle framing | **Skip** | Unchanged |
| 13 | **TikTok** | Very low for academic Scribe segment | Time | 90+ days | High — TikTok format demands punchy/urgent = brand mismatch | **Skip** | Unchanged |

### Headline shifts vs the ticket's first-draft table

1. **MobileRead added as P1** (was missing entirely — the most consequential change)
2. **Reddit organic ranking-signal benefit removed**; in-platform engagement value retained at P1
3. **Bluesky upgraded** toward P1.5 (academic concentration is now documented)
4. **Google Ads moved Skip** (was P3 defer) — locked SERP makes spend negative-ROI
5. **Newsletter/Substack demoted to P3** (paid is uneconomic at our price points)

## 2. MobileRead-as-channel deep-dive

This is the single highest-leverage strategic finding from EB-241 Phase 1 — and it was missing from the EB-242 ticket entirely. It earns its own section.

### Is paid placement available?

**No.** MobileRead is a community forum (vBulletin), not a publisher. There is no advertising surface. The only way to be present on MobileRead is through participation.

### Promotion guidelines (from MobileRead's official rules)

- "Self-Promotion is ONLY allowed in the Self-Promotion forum." Posting promotional content elsewhere = deletion and potential ban.
- One thread per product. Bump no more often than every 7 days.
- URLs must be fully disclosed — no TinyURL or shorteners.
- No affiliate links.
- "Using the community solely as a promotion platform" without participating in discussions = spam, deletable, bannable.
- No explicit minimum account age in promotion rules, but moderators check posting history before treating a member as legitimate.

### What organic engagement looks like on MobileRead specifically

- Threads where Calibre, KFX-output plugin, KCC (Kindle Comic Converter), and KindleGen come up are recurring. They appear in subforums: `Amazon Kindle`, `Calibre`, `Conversion`. Tool-recommendation threads are common.
- The community is unusually technical compared to Reddit — answers tend to be detailed, multi-paragraph, with command-line snippets. A one-liner "use leafbind" reply will be ignored or flagged.
- **Threading norm**: reply with substance (explain the failure mode the user described, walk through the solution, then mention the tool as one option among several). Don't open new promotional threads outside the Self-Promotion subforum.

### Realistic cadence for solo operator

**Month 1**: Account creation. Fill profile. Post 4-6 high-quality answers in `Calibre` and `Conversion` subforums on questions where leafbind is **not** mentioned. Goal: establish posting history as a knowledgeable Calibre/KFX user.

**Months 2-3**: Continue 1-2 substantive replies per week. Watch for "what do you use to convert PDF to KFX for Scribe?" / "Calibre KFX plugin won't install on Mac, alternatives?" threads. When one appears organically, reply with a comparison (Calibre + KFX plugin, Send-to-Kindle, then leafbind as a no-install option) — never lead with leafbind, never make it sound like an ad.

**Month 4+**: One thread in the Self-Promotion subforum announcing leafbind for those who want to discuss the tool itself. Cross-link from forum profile signature (allowed by rules — short URL in sig is normal).

**Cadence guardrail**: Don't post leafbind mentions more than ~1 in every 8-10 forum replies. The MobileRead mods are long-tenured; they recognize patterns.

### Conversion logic (the why)

- **Direct referral traffic**: Visitors clicking from a forum reply convert at a higher rate than ad clicks because they arrived through a peer recommendation.
- **SEO ranking signal**: MobileRead threads rank on Google for technical Kindle queries. EB-241 found MobileRead outranking Reddit because Reddit blocks Google's bot on r/kindlescribe. A leafbind mention inside a high-ranking MobileRead thread inherits some of that ranking weight.
- **Authority transfer**: MobileRead is the gateway-trust source. A tool that's discussed civilly there is treated by downstream communities (Reddit, Bluesky, YouTube reviewers doing research) as "legitimate." This is the highest-leverage signal we can earn cheaply.

## 3. Recommended 90-day channel mix

**Working assumption**: ~8-10 hr/week of marketing effort. SEO pillar work and MobileRead participation run in parallel because they have different rhythms (SEO = focused writing sessions; MobileRead = short daily check-ins).

### Month 1 (Weeks 1-4) — Foundation + presence

| Week | SEO (EB-241 plan) | Community | Other |
|---|---|---|---|
| 1 | Draft pillar #1: "PDF to KFX without Calibre" | Create MobileRead account; post 2 helpful answers; observe r/kindlescribe + r/kindle without posting | Audit landing page for HN-readiness |
| 2 | Publish pillar #1; internal linking | 2 MobileRead replies; lurk r/GradSchool for PDF/Kindle threads | Bluesky account, follow 50 academic accounts |
| 3 | Draft pillar #2: "Kindle Scribe academic PDF workflow" | 2 MobileRead replies; first Reddit comment in r/kindle (helpful, no leafbind link) | Bluesky: 3-5 posts (no promotion) — share a Kindle Scribe academic-PDF tip |
| 4 | Publish pillar #2 | 2 MobileRead replies; second helpful Reddit comment | Build target list: 10-15 YouTube creators who review Kindle Scribe |

### Month 2 (Weeks 5-8) — First mentions, soft outreach

| Week | SEO | Community | Other |
|---|---|---|---|
| 5 | Draft pillar #3 | First leafbind mention in a MobileRead thread IF organic opportunity arises (must be unsolicited, in a comparison context) | Pitch 3 YouTube creators (calm, no-commission gifting / free unlocks) |
| 6 | Publish pillar #3; build comparison page vs Calibre | 1-2 MobileRead replies; Reddit: 1 leafbind mention in a "what tool do you use" thread on r/kindle if it appears | Bluesky: post pillar #1 + #2 with academic framing |
| 7 | Draft FAQ page (academic-PDF-to-Scribe questions from search console + EB-241 keywords) | MobileRead self-promotion subforum: post 1 thread announcing leafbind | Pitch 3 more YouTube creators |
| 8 | Publish FAQ | r/kindlescribe: first comment (helpful, no leafbind link yet) | Newsletter outreach: identify 3 academic-tooling Substacks for free-swap pitch |

### Month 3 (Weeks 9-12) — Spike events

| Week | SEO | Community | Other |
|---|---|---|---|
| 9 | Pillar #4 + internal links audit | Continue 1-2 MobileRead replies/week | Final HN landing-page prep |
| 10 | — | — | **Show HN launch** (Monday or Tuesday, 9am ET). Stay at desk all day to answer comments. |
| 11 | Pillar #5; capture HN-validated language into copy | r/kindle: first leafbind mention if relevant thread exists | Reddit Ads test: $200 budget, r/kindlescribe + r/kindle, two creatives, run 1 week |
| 12 | — | — | **Product Hunt launch** prep / execute (mid-month, before holidays). Activate Bluesky/MobileRead network for upvotes from existing supporters only — do not solicit cold votes. |

**Out of 90 days**: 5 SEO pillars live, ~24 substantive MobileRead replies + 1 self-promo thread, 1 HN launch, 1 PH launch, 1 Reddit-Ads test, 5-10 Bluesky posts, 6 YouTube pitches, 3 newsletter pitches. All achievable solo at ~10 hr/week.

## 4. Execution notes for the top 3 priorities

### P1a — MobileRead organic

- **Account-creation order**: Sign up with the real name or a stable handle that matches the Bluesky/HN/PH accounts. Profile signature: one short line + a non-shortened leafbind.io URL (rules permit URLs in sig but not shorteners).
- **First 5 posts**: All replies, never new threads. Answer real technical questions in `Calibre` and `Conversion` subforums. Topics that win: ligature fixes in OCR'd PDFs, Calibre heading-detection regex, KFX plugin install failures on macOS — i.e., the exact problems leafbind's pipeline solves but where the answer is genuinely "here's the Calibre-only path."
- **First leafbind mention rule**: Only in a thread where someone explicitly asks "what tools do you use" or "is there an alternative to Calibre + KFX plugin." Mention Calibre + KFX plugin first, Send-to-Kindle second, leafbind third. Disclose maker status: "(disclosure: I built leafbind)".
- **Bump cadence**: No more often than every 7 days, and only for the single Self-Promotion subforum thread. Outside that subforum: zero promotional bumps, ever.

### P1b — Organic SEO (EB-241 plan)

- The EB-241 Phase-3 pillar pieces (5 pillars over 90 days) are confirmed the right move.
- **Refinement**: Write each pillar with the MobileRead thread structure in mind — a pillar should answer the exact question someone might post in `Conversion` subforum. That makes it linkable from a MobileRead reply, which compounds into both direct referrals and ranking signal.
- Add comparison-page content vs Calibre + KFX plugin explicitly. EB-241 finding: Calibre install friction is the wedge. Landing pages must show the wedge in screenshots, not prose.

### P1c — Reddit organic (engagement, not SEO)

- **Reframed expectation**: Treat Reddit as a flywheel for direct conversions (engaged readers clicking through) and brand-recognition, **not** as an SEO play. EB-241 showed Reddit's bot blocks limit Google indexing on r/kindlescribe and similar.
- **Subreddit order of operations**: r/kindle (large, more permissive) → r/kindlescribe (smaller, sharper audience) → r/GradSchool and r/academia (off-topic if not careful — only post when a PDF/Kindle-Scribe-workflow thread organically appears).
- **90/10 discipline**: Reddit retired the formal 9:1 rule but mods still scan posting history. The account needs 8-10 helpful comments in unrelated threads (book recommendations, general Kindle Scribe usability questions) before the first leafbind mention.
- **Disclosure pattern**: When leafbind comes up, lead with "I built this so I'm biased, but —" then a useful comparison. r/kindlescribe mods (as with most niche subs) tolerate maker-disclosed mentions in answer threads; they remove top-level promotional posts.
- **Never DO**: Post a "Show r/kindlescribe: I made leafbind" thread. That gets removed on most niche subreddits and burns the account.

## 5. Out-of-scope flags (surface, don't commit)

- **Wikipedia / Wikibooks Calibre or KFX article edit** — adding leafbind as a third-party tool in the relevant Wikipedia article's external-links section. Wikipedia's reliable-source and notability rules are strict. High effort, uncertain payoff, brand-safe.
- **Academic library guide outreach (LibGuides)** — university library guides often list ebook conversion tools for grad students. Email outreach to 5-10 university librarians could land leafbind in front of exactly Segment 1, with high authority transfer. Out of scope because cadence and personalization exceed solo bandwidth in the first 90 days.
- **Calibre / MobileRead plugin ecosystem partnership** — some Calibre plugin maintainers have email contact. A "leafbind handles the cases our plugin doesn't" cross-link agreement would be high-leverage. Worth a single exploratory email after Month 3, not part of the structured plan.
- **Affiliate program for YouTube reviewers** — standard creator outreach is gifting/free-unlocks at our stage; building a formal affiliate program (with tracking, payouts, terms) is premature until conversion baseline is established.

## 6. What this Phase 2 deliverable does NOT cover

Per the EB-242 ticket scope, Phase 2 produces the channel decision matrix only. The following are explicitly **deferred** to follow-up sub-tickets:

| Phase | Deliverable | Sub-ticket needed |
|---|---|---|
| Phase 3 | Content calendar Months 1-3 (which specific Reddit posts when, which Bluesky threads when, which MobileRead opportunities to watch) | Yes |
| Phase 4 | Email capture + nurture (newsletter tool decision: Buttondown vs. Listmonk vs. defer) | Yes |
| Phase 5 | Plausible/Umami analytics setup + UTM convention documented in `docs/marketing/utm-conventions.md` | Yes |

The 90-day plan in §3 is a strategic skeleton. Phase 3 turns it into an executable content calendar with specific post drafts, send times, and review checkpoints.

## Sources

Channel cost data, community-rule data, and audience-migration data:

- [Reddit Ads CPC and CPM Benchmarks (Stackmatix, 2026)](https://www.stackmatix.com/blog/reddit-ads-cpc-cpm-benchmarks)
- [Reddit Ads Cost and Pricing Guide 2026 (Stackmatix)](https://www.stackmatix.com/blog/reddit-ads-cost-pricing-guide-2026)
- [Google Ads Benchmarks 2026: CPC by Industry (Digital Applied)](https://www.digitalapplied.com/blog/google-ads-benchmarks-2026-cpc-ctr-cvr-industry)
- [Google Ads Statistics 2026 (Searchlab)](https://searchlab.nl/en/statistics/google-ads-statistics-2026)
- [MobileRead Promotion Posting Guidelines (official thread)](https://www.mobileread.com/forums/showthread.php?t=90052)
- [MobileRead Self-Promotions Subforum](https://www.mobileread.com/forums/forumdisplay.php?f=226)
- [Product Hunt Launch ROI: Real Numbers from 2026 (Uprows Hub)](https://uprowshub.com/campaigns/blog/product-hunt-launch-roi)
- [Product Hunt Launch 2026 Algorithm + Strategy (Review Sell)](https://www.reviewsell.com/blog/product-hunt-launch-upvotes-2026/)
- [Reddit vs Hacker News 2026: Tech Marketing (Teract)](https://www.teract.ai/resources/reddit-vs-hackernews-tech-marketing-2026)
- [How to launch a dev tool on Hacker News (Mark Epear)](https://www.markepear.dev/blog/dev-tool-hacker-news-launch)
- [How to absolutely crush your Hacker News launch (Onlook)](https://onlook.substack.com/p/launching-on-hacker-news)
- [As academic Bluesky grows (Science / AAAS)](https://www.science.org/content/article/academic-bluesky-grows-researchers-find-strengths-and-shortcomings)
- [The Researcher's Guide to Bluesky (Ned Potter)](https://www.ned-potter.com/blog/the-researchers-guide-to-bluesky)
- [Influencer Outreach for B2B and SaaS (Stackmatix)](https://www.stackmatix.com/blog/influencer-outreach-b2b-saas)
- [Reddit Marketing 2026: The 9:1 Rule (Teract)](https://www.teract.ai/resources/reddit-subreddit-marketing-2026)
- [Reddit's Self-Promotion Rules 2026 (KarmaGuy)](https://karmaguy.io/en/blog/reddit-self-promotion-rules)
- [How Much Do Newsletter Ads Cost (beehiiv)](https://www.beehiiv.com/blog/newsletter-sponsorship-cost)
- [Cost of sponsorships across various newsletters (The Newsletter Newsletter)](https://thenewsletternewsletter.substack.com/p/cost-of-sponsorships-across-various)
