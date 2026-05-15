---
date: 2026-05-15
ticket: EB-249
module: web_service/frontend
tags: [lighthouse, ttfb, lcp, performance, measurement-methodology, vercel, cloudflare, lantern]
problem_type: perf-diagnosis
related_tickets: [EB-238, EB-233, EB-240]
---

# EB-249 Phase 1 — TTFB ~2.4s on leafbind marketing pages: diagnosis

## TL;DR

**The 2.4s TTFB is a Lighthouse measurement artifact, not a real server bottleneck.**

Real-network TTFB on `/`, `/pricing`, and `/convert/pdf-to-kfx` is **75–130ms warm** (a 20–30× gap vs Lighthouse's reported 2.4s). The site is correctly statically prerendered, Vercel edge cache is hitting (`X-Vercel-Cache: HIT`), and **Cloudflare is not actually proxying leafbind.io traffic** — the orange-cloud is off, so the "Cloudflare-to-Vercel relay" premise in the ticket doesn't apply.

The uniform 2.4s TTFB pattern that initially looked like systemic infrastructure overhead is the signature of **Lantern simulated throttling** (Lighthouse mobile default), which applies a math-based RTT/throughput projection multiplier — not real Chrome DevTools throttling. Lantern uniformly inflates fast origins.

**Recommended Phase 2:** no code change. Re-measure with `--throttling-method=devtools` and/or pull CrUX field data; if real LCP ≤ 1900ms, close EB-249 as "methodology corrected; infra healthy" and update the EB-238 close-out doc with the lesson.

## Methodology

Phase 1 followed a parallel hypothesis-driven investigation pattern (4 read-only qa-agents, one per hypothesis from the ticket, dispatched concurrently). Each agent worked from a self-contained brief, returned a verdict + confidence, and acknowledged what it couldn't verify.

| Hypothesis | Verdict | Confidence |
|---|---|---|
| H1 — Lighthouse simulated-4G projection inflation | **LIKELY** | HIGH |
| H2 — RSC server rendering overhead | UNLIKELY | HIGH |
| H3 — Cloudflare → Vercel relay overhead | UNLIKELY (premise flawed) | HIGH |
| H4 — Render-blocking CSS bundle | UNLIKELY | HIGH |

## Findings

### H1 — Lighthouse throttling artifact (LIKELY)

**Real-network curl timing breakdown from Joe's Windows desktop, 3 runs per URL:**

| URL | Run 1 TTFB (cold) | Run 2 TTFB (warm) | Run 3 TTFB (warm) | Warm avg |
|---|---|---|---|---|
| `/` | 251ms | 132ms | 123ms | ~128ms |
| `/pricing` | 144ms | 83ms | 80ms | ~82ms |
| `/convert/pdf-to-kfx` | 223ms | 86ms | 96ms | ~91ms |

Run-1 elevation reflects TLS handshake overhead (45–55ms `appconnect`); warm runs are pure edge-cache hits.

**Gap vs Lighthouse-reported TTFB:** 19–30× warm. Even cold-run TTFB is ~10× under Lighthouse's 2.4s figure. The magnitude is the diagnostic — Lighthouse Lantern applies a `mobileSlow4G` projection (RTT multiplier + throughput cap) that systematically inflates TTFB on CDN-fronted origins located close to the test machine.

**Why uniform TTFB across 3 routes is consistent with H1, not infra overhead:** A fast, uniformly-prerendered origin produces uniform real TTFB (~80–130ms). Lantern applies the same projection multiplier uniformly. Both patterns mirror each other — the uniformity is not the smoking gun for infra overhead it initially appeared to be.

**Capture methodology used by EB-238:** Not documented in the repo. No `lighthouserc.json`, no npm script, no CI config. Only PNG screenshots in `data/debug/lighthouse-unit9/`. Most likely PageSpeed Insights UI or Lighthouse CLI defaults — both use Lantern simulated throttling by default.

**What we couldn't verify:** Cannot re-run Lighthouse with `--throttling-method=devtools` in this environment (no Chrome available). Cannot confirm whether Lighthouse's measurement origin is geographically distant from the serving Vercel PoP (Cleveland — `cle1`).

### H2 — RSC server rendering overhead (UNLIKELY)

**All three pages are statically prerendered at build time.** Evidence from `web_service/frontend/.next/prerender-manifest.json`:

- `/`, `/pricing`, `/convert/pdf-to-kfx` all appear with `"initialRevalidateSeconds": false` — infinite cache, prerendered at build, never re-generated on request.

**Per-page rendering signature:**

| Page | `dynamic` | `revalidate` | Async fetches | Dynamic API used | Mode |
|---|---|---|---|---|---|
| `/` | unset (auto) | unset | none | none | **SSG** |
| `/pricing` | unset (auto) | unset | none | none (`BuyButtons` is a client island) | **SSG** |
| `/convert/pdf-to-kfx` | unset (auto) | unset | none | none | **SSG** |

**Root layout / marketing layout:** Both sync, no data fetching. Only `next/font/google` wiring (Newsreader, DM Sans, IBM Plex Mono — all `preload: false` per EB-238 Strategy A).

**Middleware:** None at the frontend root.

**Next.js version:** `next@^16.2.6` (Next 16, React 19). Default Vercel serverless/edge split. No `output: 'export'` / `'standalone'`.

**Conclusion:** RSC overhead is not the cause. Pages are correctly static. Even if every request hit a serverless function, RSC for static content should be sub-100ms.

### H3 — Cloudflare-Vercel relay overhead (UNLIKELY — premise flawed)

**Key finding: Cloudflare is NOT actually proxying leafbind.io.** The DNS records still point at Cloudflare's nameservers, but the orange-cloud is off (per `web_service/frontend/VERCEL.md` instructions). Header evidence:

- **No `CF-Cache-Status` header** on any response.
- **No `Server: cloudflare`** — server header is `Vercel` on all responses.
- `X-Vercel-Id` shows `cle1::` (Cleveland Vercel edge) on both `leafbind.io` and the direct `*.vercel.app` URL — same PoP serves both.

**Timing comparison (median of 3 runs):**

| URL | DNS | Connect | TLS appconnect | TTFB | Total |
|---|---|---|---|---|---|
| `leafbind.io/` | 0.004s | 0.014s | 0.051s | **0.085s** | 0.088s |
| `leafbind.io/pricing` | 0.004s | 0.013s | 0.047s | **0.087s** | 0.096s |
| `leafbind.io/convert/pdf-to-kfx` | 0.004s | 0.014s | 0.049s | **0.075s** | 0.084s |
| `*.vercel.app/` direct (runs 2–3) | 0.004s | 0.013s | 0.050s | **0.078s** | 0.078s |
| `*.vercel.app/pricing` direct | 0.004s | 0.014s | 0.050s | **0.077s** | 0.077s |
| `*.vercel.app/convert/pdf-to-kfx` direct | 0.004s | 0.014s | 0.049s | **0.072s** | 0.072s |

The 6ms median difference between `leafbind.io` and the direct Vercel URL is well within noise. **There is no Cloudflare relay penalty because Cloudflare is not in the path.**

**`X-Vercel-Cache: HIT` (Age 98–238s)** confirms Vercel's edge cache is serving the prerendered HTML directly. `X-Nextjs-Prerender: 1` and `X-Nextjs-Stale-Time: 300` are present.

**What we couldn't verify:** Multi-region timing — Lighthouse's measurement origin may not be near the `cle1` Vercel PoP. Geographic mismatch between Lighthouse's runner and the serving edge could explain a portion of the gap independent of Lantern projection. Field data via CrUX would resolve this.

### H4 — Render-blocking CSS (UNLIKELY)

CSS does not affect TTFB; it affects element render delay (the 282–342ms residual). H4 would only matter if TTFB recovery left the residual blocking LCP target — which is moot given H1.

**Findings anyway:** Single CSS import seam (`app/layout.tsx` imports `globals.css` only). `globals.css` is 27 lines: three Tailwind directives + one `@layer base` block with 14 CSS custom properties. No fragmented imports. Tailwind content globs are tightly scoped. No FOUC inline styles, no manual `<style>` tags, no plugins. The three `next/font/google` instances inject `@font-face` declarations into the critical CSS chunk (~2–4KB), but all use `preload: false` and `display: swap`.

**Conclusion:** CSS bundle is lean. Not a contributor.

## Synthesis & root cause

**Primary cause:** Lighthouse Lantern simulated throttling inflates TTFB on CDN-fronted prerendered origins. The "2.4s TTFB" reported by `lcp-breakdown-insight` is not a measurement of actual server response time — it is a projection.

**Secondary observation (worth fixing):** The ticket premise assumed Cloudflare was proxying leafbind.io. It is not. Future perf hypotheses for this site should not include CF-Vercel relay overhead unless the orange-cloud is re-enabled.

**The infrastructure is healthy:**
- Pages are SSG (prerender-manifest confirms)
- Vercel edge cache is hitting (`X-Vercel-Cache: HIT`)
- TLS, connect, and DNS are all sub-50ms warm
- CSS bundle is lean
- No middleware overhead
- No render-blocking JS in critical path beyond what Next.js produces by default

## Recommended Phase 2

**Phase 2 is a measurement-methodology fix, not a code change.**

1. **Re-measure with devtools throttling.** Run Lighthouse CLI with `--throttling-method=devtools` against the 3 baseline anchor pages on production. Devtools throttling uses real Chrome network emulation (TC-style packet shaping) instead of Lantern math projection. Capture artifacts to a Phase 2 results section in this doc.

2. **Pull CrUX field data.** Open PSI for `https://leafbind.io/` and switch to the "Real Users" tab (Chrome UX Report p75). This is the ground truth — actual visitor experience, not synthetic.

3. **Decision gate:**
   - If devtools-throttled LCP and CrUX p75 LCP are both ≤ 1900ms on `/` and `/pricing`, and ≤ 2000ms on `/convert/pdf-to-kfx`: **close EB-249** as "methodology corrected; infrastructure healthy."
   - If real-user p75 LCP is above target despite low real-network TTFB: investigate render-delay residual (open a follow-up ticket scoped to the secondary bottleneck).

4. **Update EB-238 close-out doc** (`docs/solutions/eb233-design-system-decisions.md`) with:
   - Production Lighthouse re-measurement using devtools throttling
   - The CrUX p75 numbers
   - A lesson note: "Lantern TTFB on CDN-fronted prerendered origins is not actionable. Use devtools throttling or field data."

## Acceptance criteria status

| AC (from EB-249) | Status |
|---|---|
| Phase 1 diagnosis doc committed | This file — pending commit |
| Phase 2 fix deployed | Reframed: measurement methodology change, not code fix |
| Production Lighthouse meets EB-238 targets on 3 anchor pages | Pending re-measure with devtools throttling |
| CLS remains 0 | Already true per EB-238 Strategy A measurements |
| Perf score on `/` returns to ≥ 99 | Pending — currently 96 per EB-238 doc; likely Lantern-inflated as well |
| `docs/solutions/eb233-design-system-decisions.md` Lighthouse table updated | Pending Phase 2 |

## Lessons recorded

1. **Lantern simulated throttling can produce a uniform "infrastructure-overhead-shaped" TTFB pattern on a fast origin.** When 3 different routes show within-1% TTFB at >2s, the first instinct is "systemic infra overhead" — but a fast origin under Lantern produces the same pattern. **Always run real-network curl timing as a sanity check before believing Lighthouse TTFB on a CDN origin.**

2. **Hypothesis premises must include a current-state recon step.** H3 assumed Cloudflare was in the path. It wasn't. The ticket would have been more useful with a `curl -I` against the production URL pre-included to confirm the proxy chain. Future perf tickets should include a "headers as of [date]" baseline so hypothesis 1 is "where does the request actually go."

3. **"Near-identical" across pages can argue either direction.** EB-238's hand-off doc said "near-identical TTFB makes cold-start less likely" — true. It also concluded "TTFB is the real residual bottleneck" — premature. The differential test (one page improved, two didn't, on Strategy A) was a good signal that fonts weren't the bottleneck. But "TTFB is the bottleneck" required confirming the TTFB measurement was real before scoping fix work.

4. **Document measurement methodology in the solution doc.** EB-238 captured Lighthouse numbers but didn't record the throttling method, the test origin, or whether it was PSI vs CLI. That's how a Lantern artifact propagated downstream as an actionable ticket.

## References

- Predecessor: EB-238 close-out (commit `7ba8e33`, doc section in `docs/solutions/eb233-design-system-decisions.md`)
- Strategy A: commit `6fa1797` (`fix(EB-238): disable next/font preload to recover LCP regression`)
- Cloudflare not-in-path discovery: see `web_service/frontend/VERCEL.md` (orange-cloud off per deployment guide)
- Next.js prerender manifest: `web_service/frontend/.next/prerender-manifest.json` (confirms SSG)
- Lighthouse Lantern docs: https://github.com/GoogleChrome/lighthouse/blob/main/docs/throttling.md (simulated vs devtools throttling)
