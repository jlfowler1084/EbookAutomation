[EB-230] Phase 3 Unit 9 — Lighthouse + Core Web Vitals audit + fixes

## Model Tier
**Sonnet** — Runs pre-flight checks, executes Lighthouse audit, applies inline fixes if needed,
writes a structured results PR. No planning required — the acceptance criteria are fixed.

## Plan
Full implementation plan: `docs/plans/2026-05-14-001-feat-eb230-phase3-seo-landing-pages-plan.md`
(Unit 9, lines 1007–1059)

Units 0–8 are merged. This unit closes R3, R4, and R5.

## Branch
```powershell
git checkout master && git pull origin master
git worktree add .worktrees/EB-230-unit9-lighthouse -b worktree/EB-230-unit9-lighthouse
```
All fixes (if any) go into this worktree. Do NOT open separate worktrees per fix.

---

## Step 1 — Purge Cloudflare cache, then verify production is serving the new code

**Do this before the curl checks below.** Even with query-string cache-busts, CF can serve
stale HTML page shells if `Cache-Control: public` is set on the response. A stale-cached
pre-Unit-7 page would make the JSON-LD grep check below falsely pass, causing the entire
audit to run against the wrong content.

Use the Cloudflare MCP to purge these URLs immediately after deployment:
```
zone: leafbind.io
purge URLs:
  https://leafbind.io/
  https://leafbind.io/quality
  https://leafbind.io/convert/pdf-to-kfx
  https://leafbind.io/convert/academic-pdf-to-kindle
  https://leafbind.io/convert/pdf-footnotes-kindle
  https://leafbind.io/convert/multi-column-pdf-kindle
  https://leafbind.io/sitemap.xml
  https://leafbind.io/robots.txt
```

Wait ~10 seconds after purge, then run the four verification checks. If any fails,
STOP and report to the user. Do not attempt to fix deployment from inside this unit.

```bash
# All 4 must pass before proceeding
curl -sI https://leafbind.io/convert/pdf-to-kfx | grep -i "200 OK"
curl -s https://leafbind.io/sitemap.xml | grep -c "<url>"          # expect 7
curl -s https://leafbind.io/convert/pdf-to-kfx | grep -c "application/ld+json"  # expect 3
curl -sI https://leafbind.io/quality | grep -i "200 OK"
```

If sitemap returns fewer than 7 `<url>` entries, the build did not deploy cleanly.
If `application/ld+json` count is not 3 on `/convert/pdf-to-kfx`, Unit 7 is not live.
If both look right but curl returns stale content, run the CF purge again and re-check.

---

## Step 2 — Cloudflare cache-miss: force cold-cache Lighthouse runs

**DevTools "Disable cache" is NOT sufficient** — it only bypasses the browser cache.
Cloudflare's edge cache is upstream and will still serve hot content.

Two options (use whichever is available):

**Option A — Query string cache-bust (always works):**
Append `?cb=<unix-timestamp>` to each URL per run. Cloudflare treats each unique URL as a cache miss.
```
https://leafbind.io/?cb=1747212000
https://leafbind.io/quality?cb=1747212000
https://leafbind.io/convert/pdf-to-kfx?cb=1747212000
```
Use the same timestamp for the cold-cache run; use a different timestamp for the warm-cache run.

**Option B — Cloudflare MCP purge (cleaner):**
Use the Cloudflare MCP to purge the three target URLs before each cold run:
```
zone: leafbind.io
purge URLs:
  https://leafbind.io/
  https://leafbind.io/quality
  https://leafbind.io/convert/pdf-to-kfx
```

Warm-cache run: run Lighthouse again on the same URLs immediately after (without purging).

---

## Step 3 — Lighthouse harness (pinned invocation)

Install once: `npm install -g lighthouse`

Run for each page — cold cache first, then warm cache immediately after:

```bash
# Cold cache (after CF purge or with ?cb= suffix)
npx lighthouse "https://leafbind.io/?cb=TIMESTAMP" \
  --preset=desktop \
  --throttling-method=devtools \
  --output=html,json \
  --output-path=./lighthouse-home-cold \
  --chrome-flags="--headless"

npx lighthouse "https://leafbind.io/quality?cb=TIMESTAMP" \
  --preset=desktop \
  --throttling-method=devtools \
  --output=html,json \
  --output-path=./lighthouse-quality-cold \
  --chrome-flags="--headless"

npx lighthouse "https://leafbind.io/convert/pdf-to-kfx?cb=TIMESTAMP" \
  --preset=desktop \
  --throttling-method=devtools \
  --output=html,json \
  --output-path=./lighthouse-pdf-to-kfx-cold \
  --chrome-flags="--headless"

# Warm cache (same URLs, immediately after, no purge)
npx lighthouse "https://leafbind.io/quality?cb=TIMESTAMP" \
  --preset=desktop \
  --throttling-method=devtools \
  --output=html,json \
  --output-path=./lighthouse-quality-warm \
  --chrome-flags="--headless"
```

Extract scores from the JSON outputs:
```bash
cat lighthouse-quality-cold.report.json | node -e "
  const r = JSON.parse(require('fs').readFileSync('/dev/stdin','utf8'));
  const c = r.categories;
  const a = r.audits;
  console.log('SEO:', c.seo.score * 100);
  console.log('LCP:', a['largest-contentful-paint'].displayValue);
  console.log('TBT (INP proxy):', a['total-blocking-time'].displayValue);
  console.log('CLS:', a['cumulative-layout-shift'].displayValue);
"
```

---

## Step 4 — Acceptance criteria

Report cold-cache numbers for all three pages. Acceptance gates apply to cold-cache only.

| Metric | Target | Stop-the-line threshold |
|--------|--------|------------------------|
| SEO score | ≥ 95 | < 80 → escalate to user |
| LCP | < 2.5s | > 5s → escalate to user |
| TBT (Lighthouse INP proxy) | < 200ms | > 1000ms → escalate to user |
| CLS | < 0.1 | > 0.25 → escalate to user |
| Performance | ≥ 80 | < 60 → escalate to user |

**Stop-the-line conditions (escalate, do not auto-fix):**
- LCP > 5s, SEO < 80, or any Lighthouse "Failed audit" with severity high
- Unexpected page content (wrong page loads, 404 inside frame)
- Pre-flight checks failed (Step 1)

**Fix inline in this worktree:**
- LCP 2.5–5s: add `loading="eager"` + `fetchpriority="high"` to the LCP image; convert large PNGs to WebP
- Missing `alt` on any `<img>`: add descriptive alt text
- Missing `width`/`height` on `<img>` causing CLS: add explicit attributes
- Render-blocking CSS (unlikely given Tailwind JIT): defer or inline critical CSS
- Missing meta description on any page (check Lighthouse SEO audit)

**INP note:** Lighthouse reports TBT as a synthetic INP proxy. Real INP comes from Chrome User
Experience Report (CrUX), which requires 28 days of real traffic. For a new site with no traffic,
treat Lighthouse INP as a smoke test, not the SLA. Note this explicitly in the PR description.

---

## Step 5 — JSON-LD Rich Results validation (closes R3 evidence loop)

For each of the 5 new pages, validate structured data using the Schema.org validator:
```
https://validator.schema.org/#url=https://leafbind.io/quality
https://validator.schema.org/#url=https://leafbind.io/convert/pdf-to-kfx
https://validator.schema.org/#url=https://leafbind.io/convert/academic-pdf-to-kindle
https://validator.schema.org/#url=https://leafbind.io/convert/pdf-footnotes-kindle
https://validator.schema.org/#url=https://leafbind.io/convert/multi-column-pdf-kindle
```

Use the Playwright MCP to screenshot each validator result page.
Expected: green "Detected items" for SoftwareApplication on all 5; FAQPage and HowTo on the 4
convert pages. "Detected but not eligible for rich results" for SoftwareApplication is acceptable.
Zero "Missing required field" errors is the pass condition.

---

## Step 6 — Write the results PR

Single PR for this unit. Do not spawn separate worktrees per fix.
If fixes were applied, include them in the same commit as the report artifacts.

**PR body must include:**

1. Pre-flight verification results (pass/fail for each curl check)

2. Lighthouse scores table — cold and warm for all three pages:

```
| Page | LCP cold | LCP warm | CLS | TBT | SEO | Perf |
|------|----------|----------|-----|-----|-----|------|
| / (home) | | | | | | |
| /quality | | | | | | |
| /convert/pdf-to-kfx | | | | | | |
```

3. Rich Results validation: pass/fail per page with Playwright screenshot paths

4. Fixes applied (if any): which file, what changed, which metric it addressed

5. INP caveat: "Lighthouse TBT used as INP proxy. Real CrUX INP unavailable until site accumulates
   28 days of field data."

6. R4/R5 verdict: PASS or PARTIAL (with explanation if partial)

---

## Step 7 — GSC sitemap submission (if not done post-#66 merge)

If Google Search Console submission hasn't been completed yet:
1. Open https://search.google.com/search-console → leafbind.io property
2. Sitemaps → Add sitemap → enter `sitemap.xml` → Submit
3. Verify "Success" and 7 URLs discovered
4. URL Inspection → request indexing for each of the 5 new pages
Record submission confirmation in the PR description.

---

## Key constraints
- Cache-miss and cache-hit numbers are reported separately — never average them
- Rich Results screenshots go into the PR description (not committed to the repo)
- If Playwright MCP is unavailable for Rich Results screenshots, paste the validator output as text
- `next build` must still exit 0 after any fixes (run it before committing)
- Do not touch existing page content beyond targeted fixes — no copy changes in this unit

## Invocation
```
claude --model sonnet "[EB-230] Unit 9: Lighthouse + CWV audit -- Read prompts/EB-230-unit9-lighthouse-cwv.md and follow the instructions"
```
