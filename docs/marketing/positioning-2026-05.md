---
ticket: EB-242
phase: Phase 1 — Positioning & messaging
date: 2026-05-15
author: Joe Fowler
status: Phase 1 complete — Phase 2-5 (channels, content calendar, email, analytics) deferred to sub-tickets
related:
  - EB-241 (SEO discovery — provides validated audience hierarchy + pain language)
  - EB-233 (design system — provides visual brand the messaging must match)
  - EB-238 (LCP regression — partial close; TTFB residual in EB-249)
  - project-leafbind-design-constraint (memory file — load-bearing brand voice rule)
---

# leafbind.io — Phase 1 Positioning & Messaging

## Purpose of this document

This is the canonical reference for **what leafbind is, who it's for, and how it talks**. Consult it before:

- Writing or editing any public-facing copy (landing pages, pricing, conversion result screens, Stripe success page, error states)
- Drafting any external communication (Reddit posts, HackerNews launch, blogger outreach emails, Bluesky posts)
- Reviewing SEO content briefs (Phase 3 of EB-241)
- Evaluating new design or copy directions ("does this fit leafbind's voice?")

If a piece of copy contradicts this doc, the doc wins by default — but flag the conflict so we can decide whether to update the doc or change the copy.

## 1. Audience segments (priority order)

Validated against EB-241 SERP analysis and MobileRead forum surveying. Quotes are verbatim from threads cited in `docs/marketing/seo-discovery-2026-05.md` §2.

### Segment 1 (primary) — Kindle Scribe owners with academic or research PDFs

**Who they are**: Grad students, postdocs, researchers, working professionals who read papers and books on a Kindle Scribe. They've tried Amazon's Send-to-Kindle service and been disappointed by the formatting — broken column flow, lost footnotes, no chapter navigation, occasional missing covers, sometimes pages that won't highlight.

**Where they are**: MobileRead forums (the dominant Kindle Scribe technical authority for Google ranking), Reddit r/kindlescribe, r/kindle, r/academia, r/GradSchool, academic Bluesky.

**What they're searching for** (rank #1, #3, #5 in EB-241 ranked table):
- `convert pdf to kfx for kindle scribe`
- `academic pdf to kindle`
- `kindle scribe academic reading`

**Their pain in their own words** (MobileRead):
- *"Only some links in the resulting kfx file work… I also cannot highlight text on some pages, while other pages work fine."*
- *"the scribes landscape column mode not working… converted to azw3 and tried again, still not working with column mode."*
- *"converting academic PDF journal articles for Kindle"* (a thread title indexed for 10+ years — durable framing)
- *"Is the new Kindle Oasis good for reading PDF academic articles with footnotes on each page?"*

**Price sensitivity**: Willing to pay $2.99-$14.99 per conversion. They will not pay for a subscription. They will pay once for a tool that delivers on the academic-papers-with-footnotes promise.

**What we say to them**: "Convert PDFs to Kindle, beautifully." Multi-column academic papers, footnote linking that survives conversion, proper chapter detection. Concrete benefits, not vague quality claims.

### Segment 2 (secondary) — Casual Kindle owners converting non-Amazon ebooks

**Who they are**: Readers who buy or download ebooks outside Amazon (EPUBs from Kobo, Project Gutenberg, indie publishers) and want them on their Kindle. Smaller volume than Segment 1, less academic-specific.

**What they're searching for** (rank #16 — but mostly through generic "kfx converter" terms which are SERP-locked by competitors):
- `kfx vs epub for kindle scribe`
- `epub to kfx converter` (skip for v1 — SERP dominated by Epubor/UPDF content farms)

**What we say to them**: Same product, supporting role in messaging. They benefit from the same features but they're not who the hero copy speaks to first.

### Segment 3 (tertiary) — Writers and publishers handing off manuscripts

**Who they are**: Self-publishers and indie writers converting DOCX or InDesign-export PDFs to KFX with proper metadata (title, author, cover, series). Different need profile (metadata-heavy, expects publishing-grade output).

**Status**: Not addressed in current product positioning. Mentioned here so future product/positioning evolution can pick it up if traction emerges, but it should not dilute Segment 1 messaging now.

**What we say to them**: Nothing yet. Don't engineer for hypothetical demand.

## 2. Messaging pillars

Four pillars. Each pillar is: a) a one-line claim, b) where it appears, c) why it works for the audience, d) the evidence backing it.

### Pillar 1 — "Convert PDFs to Kindle, beautifully."

**Where**: Home page H1, OG image headline, primary page title across `/convert/*` pages.

**Why it works**: "Beautifully" is the differentiator. The category is dominated by "Convert PDF to Kindle online free" SEO-farm titles that promise nothing about quality. The word "beautifully" implicitly contrasts — implying that other converters are not beautiful, which is true.

**Evidence**: The MobileRead pain quotes (broken links, broken highlights, broken column mode) are all aesthetic-functional failures. Users are not asking for "another converter" — they're asking for one that works.

**Watch out for**: Don't escalate to "perfectly" or "flawlessly" — those are subscription-software promises. "Beautifully" carries weight without overclaiming.

### Pillar 2 — "No ads. No malware. Pay once."

**Where**: Pricing page sub-headline, footer trust signal, "Why leafbind?" comparison sections on `/convert/*` pages.

**Why it works**: This is the direct contrast with the visible SEO competition. Smallpdf, iLovePDF, PDFCandy and the long tail of clones are ad-monetized and many users associate the entire category with malware risk before they click. "Pay once" also forecloses subscription anxiety — important because the academic audience has subscription fatigue from journals, software, and streaming.

**Evidence**: Project memory `project-leafbind-design-constraint` records the user's explicit framing: *"not something that makes the user feel like they are going to install malware."* That's the load-bearing trust signal.

**Watch out for**: Don't use this as a fear hook ("Avoid malware!"). State it as a fact about leafbind, not a warning about the category.

### Pillar 3 — "Made for serious readers."

**Where**: Tagline candidate, About-page hero, Reddit/HN post framings, blogger outreach pitch.

**Why it works**: Owns the academic / intentional reader audience. "Serious" is calibrated — it's confident without being elitist. It says "we know who you are" without saying "and you're better than other readers." The audience self-identifies with it.

**Evidence**: EB-241's audience hierarchy puts Segment 1 (academic, research) first by intent rank, search volume, and SERP softness. The phrase positions the product to win that segment without alienating Segment 2.

**Watch out for**: Don't moralize. "Serious" describes the use case, not the moral worth of the user. Avoid "for people who really read."

### Pillar 4 — "Your file is never stored after conversion."

**Where**: Privacy section on home page, conversion result screen confirmation, security section in FAQ.

**Why it works**: Files are personal. Books are personal. Academic papers are sometimes under embargo. The trust required to upload a personal file to a stranger's server is non-trivial — make it cheap by removing the data-retention question.

**Evidence**: Stripe-payment + personal-file upload is a higher-trust ask than typical SaaS. Project memory records this as load-bearing: *"the whole business model depends on users trusting the site enough to upload a personal ebook and enter payment details."*

**Watch out for**: This must actually be true. If retention behavior changes, this pillar changes. Don't sand-bag a future product decision by overpromising here.

## 3. Brand voice rules

Each rule is: a) the rule, b) why, c) a DO example, d) a DON'T example.

### Rule 1 — Calm, confident, never urgent

**Why**: Urgency-marketing patterns ("Limited time!", "Only 3 spots left!", countdown timers, popup overlays) are the exact signal that triggers the "sketchy free-tool" pattern-match the design constraint warns against. The audience came to convert a file; their attention is the urgency, ours doesn't need to be.

**DO**: "Pay once. No subscription. Free tier always available."
**DON'T**: "Limited time: 50% off — only today!" Even if true, this signal kills trust.

### Rule 2 — Specific over generic

**Why**: Specificity reads as competence. Generic copy reads as templated. The audience is technical — they can tell.

**DO**: "Multi-column academic papers with footnotes that survive conversion."
**DON'T**: "Fast, reliable conversion for all your documents."

### Rule 3 — Honest about limits

**Why**: Trust is earned by acknowledging trade-offs. Hiding the free tier's file-size limit until checkout breeds resentment. Stating it up front breeds respect.

**DO**: "Free tier: up to 20 MB per file. Paid tiers up to 200 MB. Why? Compute cost."
**DON'T**: "Convert any PDF instantly!" (then 19 MB cap surfaces after upload).

### Rule 4 — No fake social proof

**Why**: Stock testimonials, vague "10,000+ users" badges, fictional 5-star reviews — all readable as fake by the audience. Better to have no testimonial than a fake one.

**DO**: When real testimonials exist, attribute them. Until then, let the product do the talking.
**DON'T**: *"'Best converter I've ever used!' — Sarah, grad student"* (no Sarah, no review).

### Rule 5 — Match jargon to audience layer

**Why**: Speaking to a grad student about "KFX containers" is fine — they came here because they know what KFX is. Speaking to the same person about "lexer-based document tokenization" is showing off, not communicating. Speaking to a casual reader about "fixed-format vs reflowable KFX" without explanation is gatekeeping.

**DO**: On `/convert/multi-column-pdf-kindle` (technical surface): "Multi-column PDFs use coordinate-based layout that breaks Send-to-Kindle's text flow. We extract column order before conversion."
**DO**: On home page (broad surface): "Academic papers stay readable. Footnotes still work. Chapters show up in the menu."
**DON'T**: Either copy on either surface.

### Rule 6 — One primary CTA per page

**Why**: From EB-233's AI-slop checklist (already enforced as PASS in production). Multiple competing CTAs is an AI-tell signal. The audience came to do one thing — surface that one thing, get out of the way.

**DO**: Home page = upload form (the one CTA). Pricing page = buy buttons (the one CTA cluster). `/convert/*` pages = upload form (the one CTA), with optional `/quality` link as supplementary.
**DON'T**: Hero CTA + secondary "Or watch a demo!" + tertiary newsletter signup + quaternary "View pricing" — pick one.

## 4. Antipatterns explicitly rejected

These are inherited from `project-leafbind-design-constraint` and EB-233's AI-slop checklist. Recorded here so the messaging layer doesn't reintroduce what the design layer rejected.

| Antipattern | Why we reject it |
|---|---|
| Urgency timers, "Limited time" copy, scarcity claims | Trust-killing pattern of the SEO-farm competition |
| Fake testimonial blocks, stock-photo "happy users" | Reads as fake to a technical audience; better silent than false |
| Aggressive download CTAs that aren't downloads | Smallpdf antipattern — bait-and-switch |
| Popup overlays on first paint (newsletter, cookie banner past minimum) | Hostile to attention; first-paint discipline matters |
| Subscription anchoring ("Just $9.99/month!") | Audience has subscription fatigue; we are not a subscription |
| Vague benefit copy ("best", "amazing", "incredible") | Specificity is the brand; vague claims weaken trust |
| Autoplay video, autoplay audio, autoplay anything | Reads as ad-monetized; we are not |
| Gradient-mesh / glassmorphism / generic Tailwind defaults | Already rejected by EB-233 design system; messaging must match |
| Affiliate-disclosure-shaped trust signals where no affiliate exists | Don't manufacture trust signals — earn them |
| AI-generated stock illustration as hero imagery | The audience can tell; lean on type + brand mark instead |

## 5. Application guide

### When writing landing-page copy

1. Identify which segment this page primarily serves (usually Segment 1).
2. Pick the most relevant pillar — usually Pillar 1 for hero, Pillar 2 in a comparison/trust section, Pillar 3 for tagline, Pillar 4 in privacy section.
3. Apply Rules 1–6 to every line. Rule 2 (specific over generic) is the most violated — read your draft and ask "could this same sentence appear on a competitor's site?" If yes, rewrite.
4. Single primary CTA only.

### When writing external posts (Reddit, HN, Bluesky)

1. Lead with the user's pain, not our solution. ("I've been frustrated by X" beats "I built Y").
2. Don't say "I built this for you." The audience decides whether it's for them.
3. Disclose authorship cleanly. Don't pretend to be a neutral user reporting a discovery.
4. Anchor to a specific use case from Section 1's pain quotes — those are the audience's own words and they recognize them.

### When writing the Stripe success page or conversion result screen

1. Pillar 4 (file-not-stored) belongs here — it's the moment trust pays off.
2. Confirm what was delivered (specific filename, specific format).
3. Set expectations for support if conversion failed (acknowledge it can happen, route them to a recovery path).

### When the doc and a draft conflict

The doc wins by default. But:
- If the conflict surfaces a real audience insight we missed, update the doc before shipping the copy.
- If the conflict is just creative impatience, the doc still wins.
- Both options are OK. Silent override of the doc is not.

## 6. What this Phase 1 deliverable does NOT cover

Per the EB-242 ticket scope, Phase 1 produces the positioning doc only. The following are explicitly **deferred** to follow-up sub-tickets:

| Phase | Deliverable | Status |
|---|---|---|
| Phase 2 | Channel strategy decision matrix (refined with actual costs) | Defer to new sub-ticket |
| Phase 3 | Content calendar Months 1–3 | Defer to new sub-ticket |
| Phase 4 | Email capture + nurture (newsletter tool decision) | Defer to new sub-ticket |
| Phase 5 | Plausible/Umami analytics + UTM convention | Defer to new sub-ticket |

Phase 2's channel table in the EB-242 ticket body is a reasonable starting point (organic SEO + Reddit organic as P1; HN Show + Bluesky + YouTube outreach as P2; Google/Reddit Ads as P3 deferred). The follow-up ticket should refine it with current costs and commit a final table.

## References

- `docs/marketing/seo-discovery-2026-05.md` — EB-241 Phase 1 keyword research; provides the audience hierarchy + MobileRead pain quotes cited above
- `docs/solutions/eb233-design-system-decisions.md` — visual brand and AI-slop checklist that the messaging must match
- `~/.claude/projects/F--Projects-EbookAutomation/memory/project_leafbind_design_constraint.md` — load-bearing trust constraint
- [EB-242 ticket](https://jlfowler1084.atlassian.net/browse/EB-242) — original scope with first drafts of audience segments, pillars, voice rules
- [EB-241 ticket](https://jlfowler1084.atlassian.net/browse/EB-241) — sibling SEO strategy ticket
