---
ticket: EB-252
date: 2026-05-15
author: Joe Fowler
status: active reference — update on every new channel/campaign first use
related:
  - EB-242 (channel strategy — defines the channels that use these UTMs)
  - docs/marketing/channel-strategy-2026-05.md (the 13-channel decision matrix)
---

# leafbind.io — UTM Tagging Conventions

## Purpose

Every external link that points back to `leafbind.io` from a Reddit post, MobileRead reply, Bluesky thread, HackerNews launch comment, Product Hunt page, YouTube description, or any other channel **must carry UTM parameters** before it ships. Without them, traffic source attribution is guesswork.

This doc is the canonical schema. **Consult it before composing any leafbind URL that will appear on a non-leafbind domain.**

Plausible reads `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, and `utm_term` automatically and surfaces them in the "Sources" dashboard. No additional instrumentation needed in the frontend.

## Schema

Five parameters, two required, three optional:

| Param | Required? | What it is | Example |
|---|---|---|---|
| `utm_source` | **Required** | Where the link is posted (one specific channel or property) | `mobileread`, `reddit-kindlescribe`, `bluesky` |
| `utm_medium` | **Required** | The general category of channel | `organic`, `ads`, `email`, `referral` |
| `utm_campaign` | **Required** | The marketing campaign or content piece this link is part of | `launch-2026-q3`, `pillar-pdf-to-kfx` |
| `utm_content` | Optional | Differentiator within a single campaign (e.g., A/B test variant, CTA position) | `header-cta`, `footer-link`, `variant-a` |
| `utm_term` | Optional | Search keyword (only meaningful for paid search; almost never used at leafbind) | (unused — keep for parity with industry conventions) |

All values are **lowercase with hyphens, no spaces, no underscores**. This is consistent with how Plausible displays them in the dashboard (which is case-sensitive) and matches search-engine-friendly URL conventions.

## Source taxonomy

The `utm_source` is the **most granular** field — it identifies the exact channel or property the link is posted to. Conservative naming: when in doubt, be more specific rather than less.

### Currently approved sources

| Source value | Where it's used |
|---|---|
| `mobileread` | Any post on mobileread.com forums |
| `reddit-kindlescribe` | Posts/comments in r/kindlescribe |
| `reddit-kindle` | Posts/comments in r/kindle |
| `reddit-calibre` | Posts/comments in r/calibre |
| `reddit-gradschool` | Posts/comments in r/GradSchool |
| `reddit-academia` | Posts/comments in r/academia |
| `bluesky` | Any post on Bluesky (academic clusters or otherwise) |
| `hackernews` | Show HN launch post + replies |
| `producthunt` | Product Hunt launch page + comments |
| `youtube-<creator-handle>` | A specific YouTube creator's video or description (e.g., `youtube-the-ebook-reader`) |
| `newsletter-<publication>` | A specific newsletter / Substack (e.g., `newsletter-academic-tooling`) |
| `blog-<domain>` | A blog reference (e.g., `blog-techlicious`, `blog-meyerperin`) |
| `email-receipt` | Post-purchase email link |
| `email-newsletter` | Outbound newsletter link (EB-251 if it ships) |
| `reddit-ads` | Reddit Ads paid placement |
| `direct-share` | Manually shared link with no channel attached (text message, DM, etc.) |

### Drift-prevention rule

**When you use a UTM `source` value for the first time, add it to this table in the same PR or commit.** Discovering an undocumented source value in the Plausible dashboard six months later means going back to track down what posting context it came from. Don't.

If you're posting in a channel that doesn't fit any approved source, name it descriptively, add the row, and ship. Examples that don't exist yet but would be valid: `discord-<server>`, `slack-<workspace>`, `forum-<domain>`.

## Medium taxonomy

The `utm_medium` is **categorical** — only four values are used:

| Medium value | Definition |
|---|---|
| `organic` | Unpaid, user-initiated channels: forums, social, blog posts where leafbind is mentioned organically |
| `ads` | Anything we paid for: Reddit Ads, Google Ads (if we ever reopen that), Twitter/X Ads (skipped per EB-242), newsletter sponsorships |
| `email` | Any email-driven link: post-purchase receipt, newsletter, customer outreach |
| `referral` | Earned third-party placements: YouTube creator videos, blog reviews, Product Hunt listing (the "free" tail traffic, not the launch-day spike which is `organic`) |

If a click doesn't fit one of those four, stop and rethink the framing. Adding new medium values requires explicit discussion — it's a small set on purpose.

## Campaign taxonomy

The `utm_campaign` ties multiple links together so the dashboard can show "all traffic from the Q3 2026 launch campaign" as one number. Convention: `<purpose>-<timeframe>` or `<piece-type>-<piece-name>`.

| Campaign value | What it groups |
|---|---|
| `launch-2026-q3` | Initial leafbind launch traffic across HN, Product Hunt, initial Reddit posts |
| `pillar-pdf-to-kfx` | All links pointing to the "PDF to KFX without Calibre" pillar page from external channels |
| `pillar-kindle-scribe-academic` | All links pointing to the "Kindle Scribe academic PDF workflow" pillar |
| `mobileread-orga` | MobileRead organic-mention traffic over its 4-month buildup (per EB-242 Phase 2 cadence) |
| `creator-outreach-2026-q3` | YouTube + blogger outreach campaign Q3 |

Same drift-prevention rule as sources: **add new campaigns to this table on first use.**

## Worked examples

Five concrete URLs you can copy-paste-adapt. All assume the destination is `https://leafbind.io/convert/pdf-to-kfx` for clarity, but the same pattern applies to any landing page.

### 1. Helpful comment on r/kindlescribe (organic, no specific campaign)

```
https://leafbind.io/convert/pdf-to-kfx?utm_source=reddit-kindlescribe&utm_medium=organic&utm_campaign=launch-2026-q3
```

### 2. Reply in a MobileRead thread (organic, mobileread-orga campaign)

```
https://leafbind.io/convert/pdf-to-kfx?utm_source=mobileread&utm_medium=organic&utm_campaign=mobileread-orga
```

### 3. HackerNews Show HN post body link

```
https://leafbind.io/?utm_source=hackernews&utm_medium=organic&utm_campaign=launch-2026-q3
```

### 4. Reddit Ads creative (paid)

```
https://leafbind.io/?utm_source=reddit-ads&utm_medium=ads&utm_campaign=launch-2026-q3&utm_content=variant-a
```

(Use `utm_content` to differentiate creatives in an A/B test — `variant-a`, `variant-b`. Plausible aggregates them under one campaign so you can compare CTR.)

### 5. YouTube creator video description link

```
https://leafbind.io/?utm_source=youtube-the-ebook-reader&utm_medium=referral&utm_campaign=creator-outreach-2026-q3
```

(Replace `the-ebook-reader` with the actual creator's slug. Document the slug in the source taxonomy table on first use.)

## Stripe attribution

Plausible captures UTMs at pageview time. But Stripe Checkout opens on `checkout.stripe.com` — a different domain — and stops the same-session pageview tracking. So a naive setup loses the source attribution at the moment of purchase.

The pattern that works:

1. On the leafbind page where the "Buy" button lives, **read the UTM params from `window.location.search`** when the page loads.
2. Pass them to the Stripe Checkout Session creation as `client_reference_id` or in the Checkout Session `metadata` field.
3. Stripe stores them on the resulting `payment_intent` and `customer` records.
4. When the Stripe webhook fires `checkout.session.completed`, the metadata is in the event — read it and emit a Plausible custom event (`Stripe Purchase Complete` with the metadata as props).

**Implementation note**: this requires a small backend change in the Stripe webhook handler. **Not in scope for this ticket** — file a follow-up if needed. For now, attribution lives at the pageview level (Plausible Sources dashboard), which is the dominant attribution surface anyway.

## Monthly review

A 4-number review at the end of each month captures whether the strategy is working. Template lives at [`docs/marketing/monthly-review-template.md`](monthly-review-template.md). Save filled-in reviews at `docs/marketing/reviews/YYYY-MM-review.md`.

## When this doc and a draft URL conflict

Same protocol as positioning-2026-05.md §5.4: **this doc wins by default**, but a draft URL exposing a real schema gap should trigger a doc update before the link ships.

Silent override is the failure mode this convention is designed to prevent.

## References

- [EB-252 ticket](https://jlfowler1084.atlassian.net/browse/EB-252) — parent ticket
- [EB-242 channel strategy](https://jlfowler1084.atlassian.net/browse/EB-242) — `docs/marketing/channel-strategy-2026-05.md`
- [Plausible UTM docs](https://plausible.io/docs/utm-tags) — how Plausible reads UTM tags
- [Plausible Stripe integration patterns](https://plausible.io/docs/custom-event-goals) — for the deferred webhook attribution
