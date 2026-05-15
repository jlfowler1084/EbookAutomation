---
ticket: EB-258
parent: EB-241
model: sonnet
created: 2026-05-15
author: Joe Fowler (handoff drafted in Opus session)
status: ready-to-execute
estimated_sessions: 1-2
---

# [EB-258] SEO Phase 1 — keyword research, SERP audit, competitor gap analysis

## Invocation

```powershell
claude --model sonnet --prompt-file prompts/EB-258-seo-phase1-research.md
```

## Session goal

Produce `docs/marketing/seo-discovery-2026-05.md` — the foundational SEO discovery doc that decides what content gets written next. This unblocks EB-259 (first pillar page) and informs the eventual r/kindlescribe Reddit posting strategy.

Research-only. **No code changes.** No new routes, no component edits, no config tweaks.

## Why this matters

leafbind.io has the SEO surface (4× `/convert/*` landing pages + `/quality`) but zero ranked organic traffic. Picking pillar-content topics by gut feel is the most expensive failure mode — each pillar piece is 1-2 sessions of writing work that compounds in damage if mis-targeted. This research locks the targeting before any prose ships.

## What's already shipped

- Marketing strategy doc: `docs/marketing/positioning-2026-05.md` (audience segments, voice rules)
- Channel strategy: `docs/marketing/channel-strategy-2026-05.md`
- UTM conventions: `docs/marketing/utm-conventions.md` (160 lines — see for source/medium/campaign taxonomy)
- Plausible analytics live on leafbind.io (EB-252 shipped 2026-05-15)
- Visual brand + 4 `/convert/*` SEO landing pages + `/quality` page (EB-230, EB-233, EB-243)

## Deliverable

One file: `docs/marketing/seo-discovery-2026-05.md` with three sections.

Commit direct to master (docs are exempt from worktree-policy per `exempt_paths`). One commit, no PR needed.

### Section 1 — Keyword research

Validate the 12 seed phrases from EB-241 using whichever free keyword tool is fastest to access:

- Google Keyword Planner (free with Google Ads account)
- Ahrefs free tier (10 lookups/day)
- Ubersuggest free tier
- Google Search Console (only once leafbind.io is verified — defer if not already done)

Seed phrases (validate each, add or drop based on real numbers):

```
kindle scribe kfx conversion
pdf to kfx without amazon
academic papers on kindle scribe
kfx footnote linking
multi-column pdf to kindle
convert pdf to kfx for kindle scribe
kindle scribe academic reading
best kfx converter for academic papers
kfx vs epub for kindle scribe
kindle scribe reflowable text
calibre alternative kfx
send to kindle pdf bad formatting
```

Filter to **KD < 30** and **monthly volume ≥ 50** where available. For each survivor, capture in a markdown table:

| Keyword | Monthly volume | KD | Intent | Maps to leafbind page |
|---|---|---|---|---|

Some seed phrases may be below tool detection threshold — note them anyway with `<50` or `n/a`. Low-volume long-tail keywords often have very low competition and convert disproportionately well, so don't discard them outright.

### Section 2 — SERP analysis

For the top 5-7 keywords from Section 1 (rank by intent + KD combo, not raw volume), screenshot the top 10 Google results. Per result, capture:

- Page format (long-form how-to / comparison / tool page / forum thread)
- Approximate word count
- Honest read: does the page actually answer the query, or is it shallow SEO-farm filler?
- Featured snippet presence (Y/N + snippet content if Y)
- AI Overview / GEO eligibility (Y/N — modern SEO requires planning for AI Overview surfaces)

Save screenshots to `docs/marketing/serp-2026-05/<keyword-slug>.png`. The screenshots are evidence; without them, the analysis is hand-wavy and future-you can't audit it.

### Section 3 — Competitor gap audit

For each competitor below, document what they currently rank for and where their content is shallow:

- **Smallpdf** (smallpdf.com/pdf-to-kindle, smallpdf.com/blog) — top-of-funnel volume, likely weak on KFX specifics
- **iLovePDF** (ilovepdf.com) — generic PDF tool brand
- **PDFCandy** (pdfcandy.com)
- **Calibre docs** (manual.calibre-ebook.com) — strong technical authority, but Calibre's KFX support is plugin-only and the docs reflect that
- **Amazon's Send-to-Kindle help page** — high domain authority but optimized for Amazon's flow, not for "better quality"
- **Kindle blogs** (the-ebook-reader.com, goodereader.com) — review-oriented, light on how-tos
- Anyone else ranking for ≥ 3 of the seed phrases (surfaced by Section 1)

For each: 2-3 sentences on what they own + the specific gap leafbind can exploit. **The gap is the opportunity — not "we do it better," but "they don't cover this at all."**

## Acceptance criteria (per EB-258 ticket)

- [ ] `docs/marketing/seo-discovery-2026-05.md` committed with all three sections
- [ ] ≥ 8 of 12 seed keywords have validated volume + KD numbers (or explicit `<50`/`n/a` flags)
- [ ] ≥ 5 SERP screenshots in `docs/marketing/serp-2026-05/`
- [ ] Competitor audit covers ≥ 5 competitors with explicit gap statements
- [ ] Pillar-page recommendations: which 2-3 of the 6 EB-241 Phase 3 pillar candidates have highest ROI, with one-sentence rationale each. (The 6 candidates: PDF-to-KFX guide, Scribe vs iPad, KFX vs EPUB, multi-column, footnote linking, free vs paid comparison.)
- [ ] "Next-actions" section closes the doc: which sub-tickets to file next

## Out of scope (deliberate)

- Writing pillar content — that's EB-259 (already filed, blocked by this ticket)
- Google Search Console setup — do if it's a 10-min side task, otherwise defer
- Backlink research — Phase 4 territory, separate ticket
- On-page audit of existing `/convert/*` pages — Phase 2 territory, can run in parallel

## Skills to use

- **`seo` skill** (`~/.claude/skills/seo/SKILL.md`) — load first. Covers technical SEO, content briefs, GEO/AI Overview considerations.
- **`compound-engineering:research:best-practices-researcher` agent** — useful for the competitor audit. Delegate per-competitor research to parallel sub-agents to keep main context clean.

## Constraints / gotchas

1. **Brand voice constraint** (from `docs/marketing/positioning-2026-05.md`): leafbind is "calm, confident, never urgent." When evaluating SERP competitors, note when they violate this (e.g., "Convert PDFs Now! 100% Free! No Signup!") — that aesthetic gap is part of leafbind's differentiation.
2. **Worktree-policy exemption** for docs: this ticket commits direct to master. Do NOT create a worktree branch — adds friction with no merge gate value.
3. **Vercel deploy issue (EB-257)**: irrelevant to this ticket since docs don't deploy via Vercel. But be aware: until EB-257 ships, any frontend ticket that follows (like EB-259) will need manual `vercel promote` after merge.

## When done

1. Commit + push the doc and screenshots to master
2. Post a Jira comment on EB-258 with the doc link and a 3-bullet summary of findings
3. Transition EB-258 to Done
4. Unblock EB-259 in Jira (the "blocked by" link from EB-258 → EB-259 will surface this automatically once EB-258 is Done)
5. Add a `ce:compound` entry under `docs/solutions/` if any cross-cutting SEO learnings emerged worth preserving for the next campaign

## References

- Parent ticket: [EB-241](https://jlfowler1084.atlassian.net/browse/EB-241)
- This ticket: [EB-258](https://jlfowler1084.atlassian.net/browse/EB-258)
- Blocks: [EB-259](https://jlfowler1084.atlassian.net/browse/EB-259) (first pillar page)
- Sibling phase tickets: EB-250 (content calendar), EB-251 (email capture), EB-252 ✅ shipped (analytics)
- Marketing positioning: `docs/marketing/positioning-2026-05.md`
- Channel strategy: `docs/marketing/channel-strategy-2026-05.md`
- Brand visual system: `docs/solutions/eb233-design-system-decisions.md`
