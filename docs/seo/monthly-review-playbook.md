# Monthly SEO Review Playbook — leafbind.io

**Purpose:** Codify the recurring monthly check across GSC, Ahrefs Webmaster Tools, and Plausible so the analytics install pays off. Without this checklist the data flows in and nobody looks at it.

**Schedule:** First of each month. First review: **2026-06-15** (≈30 days after Phase 1 GSC verification 2026-05-14, when data should be flowing).

**Time budget:** ~35 min total.

**Source tickets:** EB-265 (this install), EB-252 (Plausible wiring), EB-241 (SEO research), EB-259 (PDF-to-KFX pillar page).

---

## 1. Google Search Console — 10 min

URL: https://search.google.com/search-console

### Performance (last 28 days)
- [ ] Total clicks vs prior month — direction + magnitude
- [ ] Total impressions vs prior month — direction + magnitude
- [ ] Average CTR — note any month-over-month drop > 0.5pp
- [ ] Average position — note any move > 2 positions
- [ ] **Top 20 queries by impressions** — paste to working notes for synthesis below
- [ ] **Top 5 queries with CTR < 2%** — these are title/meta tweak candidates (you're showing up, but the snippet isn't compelling)
- [ ] **New queries this month** — queries that didn't exist last month; signal of expanding topical reach

### Indexing › Pages
- [ ] Indexed page count vs sitemap (target: all 16 indexed)
- [ ] Any new "Crawled — currently not indexed" entries? Investigate (duplicate canonical, thin content, redirect chain)
- [ ] Any new "Discovered — currently not indexed" entries? Usually self-resolves; flag if same URL persists >2 months

### Sitemaps
- [ ] Status still "Success"
- [ ] "Discovered pages" matches expected URL count
- [ ] Last read date within the last 30 days

### Core Web Vitals (Mobile + Desktop)
- [ ] Any URLs flagged "Poor" or "Needs improvement"? File ticket if so (cross-reference EB-249 perf work)

---

## 2. Ahrefs Webmaster Tools — 10 min

URL: https://ahrefs.com/webmaster-tools

### Site Audit
- [ ] Health Score change vs prior month
- [ ] **New errors** (4xx, 5xx, broken internal links) — file fix ticket per error class
- [ ] **New warnings** (broken outbound links from "Crawl external links" setting) — file linkrot fix ticket
- [ ] Any new orphan pages (in-sitemap but no internal links pointing to them)

### Backlinks
- [ ] **New referring domains** since last review — note source, anchor text, follow status
- [ ] **Lost backlinks** since last review — investigate if from a meaningful source
- [ ] Domain Rating (DR) change — directional, slow-moving

### Organic Keywords (where leafbind ranks)
- [ ] Total keywords vs prior month
- [ ] **Top 10 keywords by traffic value** — paste to working notes for synthesis below
- [ ] **Position changes** of EB-259 target keywords (PDF to KFX, Kindle Scribe PDF, etc.)
- [ ] **Keyword gaps** vs competitors (free tier has limited competitor data — note candidates for paid Ahrefs trial if signal is strong)

---

## 3. Plausible Analytics — 5 min

URL: https://plausible.io/leafbind.io

### Traffic
- [ ] Total unique visitors vs prior month
- [ ] **Top 10 pages by visits** — paste to working notes for synthesis below
- [ ] **Top 5 referrers** (note share of "Direct / None" — high direct often means organic + email + bookmarks; not actionable but worth tracking)
- [ ] Bounce rate / Visit duration on pillar pages

### Conversion funnel (when wired — pending Phase 2 of EB-265)
- [ ] Upload → conversion start rate
- [ ] Conversion start → success rate
- [ ] Success → download rate
- [ ] Pricing page → checkout button click rate
- [ ] Checkout → Stripe success rate (cross-reference Stripe dashboard)

### Outbound link clicks
- [ ] Top destinations — are users leaving to a specific external resource (Calibre, Amazon)? Signal for what to elaborate on internally.

---

## 4. Synthesis — 10 min

Cross-reference the working notes from sections 1–3:

- [ ] **Query-page alignment**: For each top-impression query (GSC), is the landing page (Plausible) the one that ranks (Ahrefs)? If GSC says users search "PDF to KFX" but Plausible shows /pricing as the top entry page, the URL ranking for that query may have changed — investigate.
- [ ] **CTR gap → title/meta opportunity**: Each query in section 1's "CTR < 2%" list → propose a title/meta tweak in a ticket comment.
- [ ] **Long-tail opportunity**: Each new Ahrefs keyword (section 2) that isn't currently in the sitemap → potential new page or expansion of existing page. Triage 2-3 per month max.
- [ ] **Content gap vs EB-259**: Ahrefs surfaces queries leafbind ranks for or *nearly* ranks for. Compare to EB-259 PDF-to-KFX pillar page coverage. If a query is in the top 20 but not addressed by EB-259, propose pillar-page expansion or a new dedicated page.
- [ ] **Pillar performance check**: How is `/convert/pdf-to-kfx` performing? It's the primary SEO target. If position is stagnant, content needs refresh (new examples, updated screenshots, internal links from newer guides).

---

## 5. Outputs

- [ ] **File 1-3 tickets** for the highest-value findings (CTR fix, new content, broken link, pillar refresh). Tag with `seo-review-{yyyy-mm}` label.
- [ ] **Snapshot the metrics** in a brief note at `docs/seo/review-snapshots/{yyyy-mm}.md` — 5-line summary: clicks, impressions, CTR, top query, top page. Lets future-you spot trends without re-pulling raw data.
- [ ] **Update this playbook** if any section's check turned out to be noise or any meaningful new check should be added. The playbook is a living doc.

---

## Reference: data lag and freshness

| Source | First data | Useful breadth | Lag to query change |
|---|---|---|---|
| GSC Performance | 3-7d | 30+ days | 2-3 days |
| GSC Indexing | 7-14d | 30+ days | 5-7 days |
| AWT Site Audit | Within hours | Updated weekly | Until next audit |
| AWT Backlinks | 24-72h | Continuous | 24-72h |
| AWT Organic Keywords | 7-30d | 90+ days | 7-14 days |
| Plausible | Real-time | Continuous | Immediate |

Implications:
- A monthly cadence is right for GSC and AWT (faster-than-monthly mostly shows noise).
- Plausible could be checked more often, but the conversion-funnel signal needs a month of volume to be statistically meaningful on a low-traffic site.
- For a brand-new site (< 90 days), expect most metrics to be small or zero in early months. Track *direction*, not *absolute values*, until volume builds.
