---
title: Cloudflare cache purge fallback to query-string cache-bust when MCP token lacks scope
date: 2026-05-14
category: workflow-issues
module: deployment-verification
problem_type: workflow_issue
component: tooling
severity: medium
applies_when:
  - Running cache-sensitive audits or post-deploy verification against a Cloudflare-fronted hostname
  - The Cloudflare API token configured for the MCP server is a Free-plan token without `cache_purge` permission
  - You need a guaranteed cold-cache fetch and cannot wait for natural TTL expiry
tags: [cloudflare, cache-purge, leafbind, vercel, deploy-verification, mcp-tokens]
---

# Cloudflare cache purge fallback to query-string cache-bust when MCP token lacks scope

## Context

During the EB-230 Unit 9 Lighthouse + Core Web Vitals audit on `leafbind.io`, the pre-flight step required purging the Cloudflare edge cache for 8 URLs before running the cold-cache Lighthouse measurements. The Cloudflare MCP call failed with an authentication error because the token configured on the Free plan lacked the `cache_purge` scope. Without a cold fetch, Lighthouse would have measured warm-cache HTML on the home page and produced inflated SEO/CWV numbers that did not reflect a first-visit user.

## Guidance

When `mcp__cloudflare__execute` (or equivalent Cloudflare API call) returns a 4xx auth error on a purge request, fall back to **per-URL query-string cache-busting** with a unique timestamp suffix:

```bash
CB=$(date +%s)
curl -sS "https://leafbind.io/?cb=$CB"
curl -sS "https://leafbind.io/quality?cb=$CB"
curl -sS "https://leafbind.io/convert/pdf-to-kfx?cb=$CB"
```

Cloudflare's default cache key includes the query string, so each unique `?cb=<value>` is treated as a cache miss and pulls fresh content from origin. Use the **same** timestamp for the cold run and a **different** timestamp for the warm run if you need to measure both.

**Caveat — Vercel's edge cache is different.** Vercel's edge keys responses by path, not full URL, so the `?cb=` trick does NOT cache-bust at the Vercel layer. If a stale build is being served by Vercel's edge (e.g., a deploy alias did not promote), query-string busting will not help. You need to fix the underlying Vercel deploy promotion. The Cloudflare layer sits in front of Vercel only for hostnames you have proxied — the leafbind.io apex is `DNS only` to Vercel, so CF caching does not apply to leafbind.io specifically. CF caching does apply to `api.leafbind.io` which is proxied.

## Why This Matters

A stale-cache audit produces metrics that do not reflect what real users experience on first visit. Submitting those numbers to a Lighthouse-gated PR or to Google Search Console as a CWV claim is misleading. If the auditor cannot guarantee a cold cache, the audit verdict is invalid regardless of the numbers it produced — a false PASS is worse than a real FAIL because it commits the team to a number that does not exist in the wild.

The follow-up fix is to upgrade the Cloudflare API token scope (or move to a paid plan) so the proper `cache_purge` flow works. The query-string fallback is acceptable for one-off audits but should not become the standard verification pattern.

## When to Apply

- Cloudflare MCP returns an `authentication` or `permission_denied` error on a purge call
- The current CF token is known to be a Free-plan / no-purge-scope token
- You need a guaranteed cold-cache HTTP fetch from a Cloudflare-proxied hostname for a one-off measurement (audit, Lighthouse, regression check)
- Migration / paid-plan upgrade is not in scope for the current ticket

## Examples

**Before (purge attempt — fails on Free plan token):**

```python
# Cloudflare MCP execute call
result = cf.execute(
    "POST /zones/{zone_id}/purge_cache",
    body={"files": [
        "https://leafbind.io/",
        "https://leafbind.io/convert/pdf-to-kfx",
    ]}
)
# Returns: 403 {"errors":[{"code":10000,"message":"Authentication error"}]}
```

**After (query-string fallback — always works for one-off audits):**

```bash
# Lighthouse cold-cache run
CB=$(date +%s)
npx lighthouse "https://leafbind.io/?cb=$CB" \
  --preset=desktop \
  --throttling-method=devtools \
  --output=json --output-path=./lighthouse-home-cold
```

**Verify cache miss in response headers:**

```bash
curl -sSI "https://leafbind.io/quality?cb=$(date +%s)" | grep -i "cf-cache-status"
# Expected: cf-cache-status: MISS (first request to this unique URL)
# vs. without the ?cb=: cf-cache-status: HIT
```

## Related

- EB-230 Unit 9 PR: https://github.com/jlfowler1084/EbookAutomation/pull/68
- EB-230 closeout comment on the LCP/Perf gap that the cold-cache audit revealed
- Follow-up: upgrade Cloudflare API token to include `cache_purge` scope (separate ticket recommended)
- `deploy/VERCEL.md` for Vercel-side edge cache behavior (different keying than Cloudflare)
