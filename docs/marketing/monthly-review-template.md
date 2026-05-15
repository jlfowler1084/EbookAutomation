---
ticket: EB-252
date: 2026-05-15
author: Joe Fowler
status: active template — copy to docs/marketing/reviews/YYYY-MM-review.md at month end
related:
  - EB-242 (channel strategy — what these numbers measure)
  - EB-252 (analytics + UTM — where these numbers come from)
  - docs/marketing/channel-strategy-2026-05.md
  - docs/marketing/utm-conventions.md
---

# leafbind monthly review — template

## How to use this template

At the **end of each month**, copy this file to `docs/marketing/reviews/YYYY-MM-review.md` (e.g., `2026-08-review.md` for the August review), fill in the numbers and notes, commit it directly to master, and reference it in any planning conversation that month.

**Cadence guardrail:** don't read more than 3 months of reviews in a single planning session. Trying to optimize too many months at once breeds noise-chasing. The whole point of capping at 4 numbers is to keep signal-to-noise high.

**The first review** is due at the end of Month 1 post-Phase-3 launch (the EB-250 content calendar kicks off Phase 3).

---

# leafbind monthly review — YYYY-MM

## The four numbers

| Metric | Value | Δ vs last month | Notes |
|---|---|---|---|
| Organic traffic (pageviews) | N | ±N% | Sources breakdown below |
| Paid conversions (count) | N | ±N | UTM-attributed Stripe purchases |
| Average order value | $N | ±$N | From Stripe dashboard |
| Return-customer rate within 7 days | N% | ±N pts | Customers who buy again within 7 days of first purchase |

## Source breakdown (organic traffic)

Pull from Plausible Sources dashboard. Top 5-10 sources by visit count, with the medium and campaign attached. Example shape:

| Source | Medium | Campaign | Visits | Conversions |
|---|---|---|---|---|
| mobileread | organic | mobileread-orga | N | N |
| reddit-kindlescribe | organic | launch-2026-q3 | N | N |
| (direct) | — | — | N | N |
| hackernews | organic | launch-2026-q3 | N | N |
| google | organic | — | N | N |

## Source breakdown (paid)

(Only fill in if Reddit Ads test ran this month — otherwise N/A.)

| Source | Medium | Campaign | Spend | Conversions | CAC |
|---|---|---|---|---|---|
| reddit-ads | ads | launch-2026-q3 | $N | N | $N |

## What worked this month

1-3 bullets. Look for:
- Surprising channel performance (a small effort yielding outsized results)
- Content that landed (a Reddit comment that got upvoted heavily, a MobileRead thread that got bookmarked, a pillar that ranked faster than expected)
- Customer behavior signal (a return-customer rate spike, a particular SKU buying disproportionately)

## What didn't work

1-3 bullets. Look for:
- Channels that underdelivered relative to time invested
- Content that fell flat (low engagement, no organic shares, no SEO signal)
- Attempts that broke the brand voice rules in [`positioning-2026-05.md`](positioning-2026-05.md) and need to be unwound

## Adjustments for next month

1-3 bullets. **Bias toward changes, not additions.** Adding more channels when the existing ones aren't working is the classic anti-pattern. Cut something, refine something, or double down — don't just stack.

Examples of good adjustments:
- "Drop r/academia (zero engagement after 3 helpful comments) — re-invest that hour in r/GradSchool"
- "Shift one of the Bluesky posts each week to be a question rather than a tip"
- "Pause the YouTube creator outreach — replies are 0/3, signal is clear"

Examples of bad adjustments:
- "Try Pinterest" (new channel before existing ones are working — see EB-242 channel-strategy decision matrix)
- "Add daily Twitter posts" (channel was explicitly Skipped per EB-242 — re-litigating the decision)
- "Increase pillar piece cadence to 2/month" (probably unsustainable for solo operator)

## Cross-reference

If any adjustment requires updating a strategy doc:
- Positioning changes → update `docs/marketing/positioning-2026-05.md`
- Channel re-prioritization → update `docs/marketing/channel-strategy-2026-05.md`
- Content calendar changes → update the EB-250 calendar doc (TBD path)

Apply the doc-vs-draft conflict protocol from positioning-2026-05.md §5.4: the doc wins by default, but a monthly review surfacing a real strategic gap is exactly the kind of conflict that triggers a doc update before the next month's execution.

## Sign-off

Reviewed by: Joe Fowler
Date filled: YYYY-MM-DD
Next review due: end of next month
