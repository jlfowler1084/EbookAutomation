---
date: 2026-05-15
ticket: EB-258
module: docs/marketing
tags: [seo, keyword-research, competitor-audit, serp-analysis, content-strategy, geo, ai-overview]
problem_type: research-workflow
---

# EB-258 — SEO Phase 1: patterns and learnings for future campaigns

## 1. Quote competitors' own docs — it's the strongest differentiation signal

The highest-leverage finding from the competitor audit was that **Calibre's manual explicitly states multi-column PDFs are unsupported** (v9.8.0: *"Complex, multi-column, and image-based documents are not supported."*).

This is more useful than any marketing claim leafbind could make:
- It's a primary-source citation, not a subjective comparison
- It can be linked directly from leafbind's `/convert/multi-column-pdf-kindle` page
- It's durable — Calibre's architecture means this limitation won't be fixed soon

**Pattern for future SEO work:** Before writing any comparison or positioning content, audit the competitor's own documentation for explicit limitations. "They say it themselves" beats "we say it's better."

---

## 2. SERP composition reveals intent more reliably than keyword categories

For "pdf footnotes kindle," the SERP is entirely publisher-focused (KDP help, Jutoh, kboards publishing forums). The *reader* use case ("my academic PDF has footnotes that break on conversion") has zero representation. This is a complete content vacuum even though the SERP is populated.

For "academic pdf to kindle," the top 10 are all generic converters — none addressing footnotes, multi-column, or chapter navigation. The "academic" qualifier in the keyword is invisible to every competitor.

**Pattern:** When a keyword contains a qualifier (academic, scribe, footnotes) but the SERP doesn't serve that qualifier, that's a higher-signal opportunity than raw volume numbers suggest. The entire SERP is mis-serving the query.

---

## 3. AI Overview detection via Playwright snapshot

To check if a keyword has an AI Overview without a manual browser session:
1. Navigate to the Google SERP via Playwright
2. Take a snapshot (`browser_snapshot`)
3. Look for `"Show more AI Overview"` button in the snapshot YAML

Confirmed for "convert pdf to kfx for kindle scribe" — AI Overview present. Not present for other tested keywords. This matters for GEO (AI Overview citations) — a page targeting a keyword with AI Overview eligibility should include 134–167-word standalone passage blocks per the SEO skill.

---

## 4. Parallel sub-agent pattern for competitor research

Running 4 competitors in parallel via `compound-engineering:research:best-practices-researcher` agents completed in ~100 seconds vs. sequential research which would have taken 400+ seconds (4× context-switch overhead).

Each agent received:
- The specific competitor URL(s) to research
- The product differentiators to look for gaps against  
- A structured output format to enable direct paste into the doc

**Pattern:** For competitive landscape research, pre-define the output format per agent and run all competitors simultaneously. The agents return structured markdown blocks that compose directly into the discovery doc with minimal editing.

---

## 5. Volume proxies when no paid tool is available

Without Ahrefs/SEMRush/Google Keyword Planner:
- **SERP populated vs. sparse** — a full 10-result SERP indicates ≥50 searches/month in most niches; a sparse/partial SERP (<5 results) often signals <50/month
- **Forum thread frequency** — keywords that generate recurring MobileRead threads over multiple years are durable, even if volume is low
- **SERP domination type** — if only forums rank (not tool pages), the keyword is either too new or too niche for content farms, meaning a well-optimized landing page faces minimal competition

Document estimates with wide ranges (+/-3×) and flag them as qualitative. Low-volume long-tail with near-zero competition often outperforms estimated mid-volume with content-farm competition for a new site.

---

## 6. MobileRead as a research primary source for Kindle queries

Reddit blocks Google's bot on r/kindlescribe, r/kindle, and similar subreddits. This means:
- MobileRead forum threads outrank equivalent Reddit threads in Google
- MobileRead user-pain language is the primary verbatim vocabulary for search queries
- A cite from MobileRead carries more SEO signal than a Reddit citation

For any future Kindle/ebook SEO research: start with MobileRead as the audience proxy, not Reddit. Reddit still has value for community engagement (direct conversion), but MobileRead is the durably indexed source.
