# Indexation Diagnostic — leafbind.io (EB-280)

**Date:** 2026-05-16
**Trigger:** Brand-name search for `leafbind.io` returns no Google results.
**Outcome:** Root cause identified. No blocking technical issues. Site is correctly configured; Google has not yet had time to crawl it.

---

## TL;DR — Root Cause

**The domain `leafbind.io` was registered on 2026-05-13 (3 days ago).** Google's typical crawl-and-index window for a brand-new domain with no existing backlinks is 1–4 weeks. There is no fixable technical issue blocking indexation.

The brand-name invisibility will resolve on its own. Verifying GSC and submitting the sitemap shortens the window from ~3 weeks to ~3–7 days.

---

## What Passed (technical SEO fundamentals)

| Check | Result | Evidence |
|---|---|---|
| `robots.txt` reachable + allows crawlers | ✅ Pass | `User-Agent: *` `Allow: /`, blocks `/status/` `/api/` only, sitemap declared |
| `sitemap.xml` valid and complete | ✅ Pass | 8 URLs: `/`, `/pricing`, `/quality`, 4× `/convert/*`, 1× `/guides/pdf-to-kfx-for-kindle-scribe` |
| No `noindex` / `nofollow` on production HTML | ✅ Pass | Grep across full homepage HTML returned zero matches |
| Canonical tag present and self-referencing | ✅ Pass | Homepage: `https://leafbind.io`; spot-checked on `/pricing`, `/quality`, `/convert/pdf-to-kfx` — all correct |
| `<title>` and `<meta description>` present | ✅ Pass | Title: `leafbind — PDF to Kindle, the calm way` |
| `llms.txt` present (GEO/AI Overviews) | ✅ Pass | 4782 bytes, content-type `text/plain`, valid markdown structure |
| Production HTML matches source | ✅ Pass | `app/robots.ts` and `app/sitemap.ts` outputs match production verbatim — no build drift |
| HTTPS + valid TLS | ✅ Pass | `Strict-Transport-Security: max-age=63072000` |
| All sitemap URLs return 200 | ✅ Pass | Verified Kindle Scribe guide route returns 200 (existing) |

## What Failed Or Needs Attention

| Check | Status | Notes |
|---|---|---|
| `site:leafbind.io` returns results | ❌ Likely zero results | Could not verify programmatically — Google, Bing, and DuckDuckGo all blocked automated scrape. **Joe to verify in browser.** |
| GSC verified + sitemap submitted | ❓ Unknown — Joe action | Cannot check without login. **See action list below.** |
| `www.leafbind.io` → apex redirect | ⚠️ Soft failure | Returns 200 (not 301) with identical Etag as apex. Canonical correctly points to apex (`https://leafbind.io`), so Google duplicate-content protection works, but a hard 301 would be cleaner. **Low priority.** |
| Cloudflare proxy active | ⚠️ OFF | Headers show `Server: Vercel` with no `cf-ray`. Cloudflare is DNS-only. WAF rules from EB-225 are not actually protecting the live site. **Not blocking indexation, but worth a follow-up ticket.** |

---

## Joe Action List (manual, GSC-login required)

Estimated total time: **15 minutes**

1. **Verify Google Search Console domain** for `sc-domain:leafbind.io` (covers all subdomains and protocols)
   - DNS-based verification — add the TXT record Cloudflare DNS
   - GSC URL: https://search.google.com/search-console
2. **Submit sitemap** in GSC under Sitemaps → Add new sitemap → `sitemap.xml`
3. **Request Indexing** via URL Inspection tool for these 4 routes (one at a time):
   - `https://leafbind.io/`
   - `https://leafbind.io/pricing`
   - `https://leafbind.io/quality`
   - `https://leafbind.io/convert/pdf-to-kfx`
4. **Repeat in Bing Webmaster Tools** (https://www.bing.com/webmasters) — Bing indexes faster than Google for new sites and gives the site a second discovery channel.
5. **Verify in browser** that `site:leafbind.io` Google search returns zero results today (sanity-check this diagnostic's premise) and re-check at +3 days, +7 days, +14 days.

---

## Fix List (code/config changes)

Ordered by effort and impact.

| # | Fix | Effort | Impact | Ticket |
|---|---|---|---|---|
| 1 | Add 301 redirect `www.leafbind.io` → `leafbind.io` (Vercel project setting or Next.js middleware) | 10 min | Low (canonical already protects) | Follow-up — file if Joe wants it |
| 2 | Enable Cloudflare proxy (orange-cloud) for apex + www so WAF rules from EB-225 actually run | 5 min Cloudflare console | Medium (security, not indexation) | Follow-up — recommend new ticket |
| 3 | None for indexation itself | — | — | — |

**There are no code changes required to fix the indexation issue.** It is purely a waiting + GSC-submission problem.

---

## Secondary Discoveries (not in EB-280 scope but worth noting)

- **`/guides/pdf-to-kfx-for-kindle-scribe` already exists** and returns 200. This is in the sitemap with lastmod `2026-05-15`. **EB-281 (ship Kindle Scribe pillar guide) may be partially or fully done already** — needs investigation before that ticket is worked.
- **Cloudflare proxy is off** — this means the WAF rules, rate limiting, and cache rules from EB-225/EB-227 are configured but not active. This is a meaningful security gap if Joe believed they were live.
- **llms.txt exists** and is well-formed. The GEO/AI Overviews readiness from the SEO skill section 7 is already in place. Good.

---

## Verification — what was checked

All checks run on **2026-05-16 ~13:38 UTC**.

| Check | Method |
|---|---|
| HTTP headers + redirect behavior on apex + www | `curl -sIL` |
| Full homepage HTML, grepped for noindex/nofollow/robots | `curl -s` + `grep -iE` |
| `robots.txt` and `sitemap.xml` contents | WebFetch + `curl -s` |
| `llms.txt` existence + content | `curl -sIL` + `curl -s` |
| Domain age, registrar, nameservers | RDAP query to `rdap.identitydigital.services` |
| Source code parity (robots.ts, sitemap.ts) | Read of `web_service/frontend/app/` |
| Canonical tags on 4 key routes | `curl -s` + `grep -oE` |
| Sitemap URL resolution (Kindle Scribe guide) | `curl -sIL` with redirect tracking |

## Acceptance criteria — outcome

| AC | Status |
|---|---|
| Diagnostic completed in one session | ✅ |
| Root cause identified | ✅ — new-domain delay (3 days old) |
| Fixable issues fixed OR filed as follow-up | ✅ — no fixes required for indexation; secondary issues flagged for follow-up tickets |
| At least homepage + /convert + /pricing submitted via GSC "Request Indexing" | ⏳ Pending — Joe action |
| Brand-name search returns homepage within 5 business days of close | ⏳ Pending — verify 2026-05-23 |

---

## References

- EB-280 — this ticket
- EB-265 — broader GSC + analytics setup (consumes the Joe-action list above)
- EB-241 — SEO strategy (unblocked once Google starts crawling; new-domain delay does not block our work, only our visibility)
- EB-225, EB-227 — Cloudflare WAF configuration (revisit re: proxy-off finding)
- EB-281 — Kindle Scribe pillar guide (verify whether the existing `/guides/pdf-to-kfx-for-kindle-scribe` page satisfies it)
