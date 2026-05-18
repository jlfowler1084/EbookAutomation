---
module: docs/seo
tags: [seo, semrush, position-tracking, methodology, phase-1, baseline]
problem_type: research-methodology
date: 2026-05-18
ticket: EB-308
---

# Configure Semrush Position Tracking at SEO Phase 1 Day 1, Not Phase 3

## Problem

The default expectation is to set up Position Tracking when ranking measurement
begins — typically Phase 3 (post-content-launch) or at the start of a re-baseline
window. This sequencing misses the most strategically valuable data: the
pre-launch baseline that proves rankings moved *because of* the content rather
than because of pre-existing momentum.

## Evidence

EB-308 Semrush trial sprint Session 3 (2026-05-18). Position Tracking was set
up only after the Phase 2 content build was already shipped and live for 4
days. Day-1 baseline showed "out of top 100" for all 8 tracked Phase 2 keywords
— the correct baseline for a newly-launched 4-day-old domain, but with no
pre-launch reference to measure ranking deltas against.

The lost-opportunity cost is concrete:

| Window | What pre-launch tracking would have shown |
|---|---|
| Phase 1 → Phase 2 close (~2 weeks) | Domain registration → first content live; useful for "did launching content cause an indexation event" |
| Phase 2 close → 14-day indexation gate | Indexation moment (first non-error `domain_rank` response); useful for measuring time-to-index |
| Indexation → first rank | Days from "in index" to "first SERP appearance"; useful for calibrating Phase 3 ranking-gate expectations |
| First rank → 60-day ranking gate | Ranking acceleration curve; useful for predicting where the 120-day stretch gate will land |

None of these windows are recoverable retroactively. By setting up Position
Tracking only at the Semrush trial sprint (4 days post-Phase-2-close), all four
windows were already collapsed.

## What Worked (After the Fact)

Setting up Position Tracking at all — better late than never. The 6-week
post-launch tracking window through trial expiry still produces useful ranking
delta data for EB-303 Phase 3c re-baseline.

What would have worked materially better: configuring the campaign at Phase 1
Day 1, with the planned Phase 2 keyword list, before any content was shipped.

## Implementation (For Future SEO Programs)

Add to Phase 1 setup checklist as a pre-Phase-2 prerequisite:

1. **Manual Semrush web UI step (~10 min, one-time, blocking Phase 2 launch):**
    - Log into Semrush web UI → Projects → Create Project for `<domain>`
    - Add Position Tracking tool
    - Configure with the Phase 2 target keyword list (typically 8-15 keywords)
    - Set tracking location matching primary market (US, UK, etc.)
    - Set device to desktop (mobile-{country} adds little SERP-position signal
      at most ranks; reserve for verticals where desktop/mobile divergence is
      known)
    - Save — daily tracking begins automatically
2. **Verify (5 min):** wait 24h, then call `tracking_overview_organic` via
   MCP to confirm the campaign returns data (will show all zeros for a new
   domain — that's the correct baseline)
3. **Document:** capture the campaign's compound ID (`{project_id}_{campaign_id}`,
   the format MCP expects) in a working doc — this is required for every
   subsequent MCP tracking query

## Cost

- Setup: 10 min one-time (manual Semrush web UI; cannot be MCP-automated —
  `tracking_research` MCP toolkit can READ tracking campaigns but not CREATE
  them)
- Per-query cost: 100 units per keyword for `tracking_position_organic`
  (8 keywords = ~800 units per snapshot); 100 units per request for
  `tracking_overview_organic` (overview metrics)
- Recommended cadence: weekly or bi-weekly snapshots during the 6-week
  post-launch indexation window; monthly thereafter

## Critical Caveat

**MCP cannot create Position Tracking campaigns.** The `tracking_research`
toolkit's `campaigns` report returns existing campaigns but the create-campaign
API is not exposed. Any AI-driven workflow must (a) explicitly flag this as a
manual Joe action, (b) block downstream Position Tracking work until the
manual step is done, (c) capture the campaign ID once configured for use in
all subsequent queries.

The MCP returns `campaigns` data in this shape:

```json
{
  "project_id": "29685400",
  "campaigns": [{
    "id": "29685400_4805618",
    "url": "leafbind.io",
    "type": "rootdomain",
    ...
  }]
}
```

The `id` field is the compound `{project_id}_{campaign_id}` format MCP
queries require — NOT the raw `campaign_id` shown in the Semrush web UI.

## Counter-Evidence / When Not to Use

- **Repurposing an existing domain that already ranks:** if the domain has
  pre-existing rankings, Position Tracking from Day 1 of a new content program
  captures useful baseline ("we ranked X for keyword Y before our content
  shipped") — still high-value.
- **Pure new-domain launch with no Phase 1:** if the SEO program starts at
  content launch (no Phase 1 discovery work), there is no "Day 1" before
  content — the tracking campaign should still be set up before the first
  Google submission, but the pre-launch tracking window is collapsed.

## See Also

- `[[phrase-related-broad-anchor-first-2026-05-18]]` — companion Phase 1
  methodology learning surfaced by the same trial sprint
- `[[serp-feature-columns-phase1-keyword-tables-2026-05-18]]` — companion Phase 1
  methodology learning surfaced by the same trial sprint
- `docs/seo/eb-241-semrush-trial-sprint-2026-05.md` — Session 3 source research
- `~/.claude/skills/semrush/SKILL.md` — Semrush MCP usage skill (does NOT
  currently cover Position Tracking specifics — update opportunity)
- `scratch/semrush-trial-2026-05/position-tracking-campaign.md` (gitignored) —
  the leafbind.io campaign's compound ID + tracked keyword list
