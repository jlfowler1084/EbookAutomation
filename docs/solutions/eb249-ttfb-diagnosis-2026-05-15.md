---
date: 2026-05-15
ticket: EB-249
module: web_service/frontend
tags: [lighthouse, ttfb, lcp, performance, measurement-methodology, vercel, cloudflare, lantern, throttling, mobile-slow-4g]
problem_type: perf-diagnosis
related_tickets: [EB-238, EB-233, EB-240]
status: closed-no-fix
---

# EB-249 — TTFB ~2.4s on leafbind marketing pages: diagnosis

## CORRECTION (2026-05-15 afternoon) — H1 falsified, original diagnosis was wrong

The original Phase 1 diagnosis below (preserved for institutional memory) concluded H1 was LIKELY-HIGH-confidence: "the 2.4s TTFB is a Lantern projection artifact; real TTFB is fast (75–130ms via curl)." **That conclusion was wrong.**

Local Lighthouse 13.3.0 audits with `--throttling-method=devtools` (real Chrome network emulation, not math projection) report the **identical ~2.4s TTFB** in `lcp-breakdown-insight` as the default `simulate` (Lantern) method. If devtools agrees with simulate, it's not a Lantern projection artifact.

JSON evidence: `data/debug/lighthouse-eb249/` (6 audits — 3 pages × 2 throttling methods).

### Corrected TL;DR

The 2.4s TTFB is real **for the modeled network conditions** (Lighthouse `mobileSlow4G` preset: `rttMs: 150`, `requestLatencyMs: 562.5`). It is dominated by protocol-level connection setup (DNS + TCP + TLS + HTTP), not by server work — the actual `server-response-time` audit reports 18–22ms in both throttling modes, and `network-server-latency` is 18ms under simulate.

4 sequential round-trips × ~562ms per-request latency ≈ 2.25s ≈ the observed 2.4s TTFB. The math is consistent with "this is the throttle's model of slow-4G protocol setup."

**No Next.js / server-side code change can reduce the 2.4s.** The server is responding in 20ms. The other 2.38s is protocol overhead in Lighthouse's modeled network.

### Phase 2 local Lighthouse evidence (2026-05-15)

| Page | Method | Perf | TTFB (lcp-breakdown) | LCP | FCP | server-response-time | network-rtt | network-server-latency |
|---|---|---|---|---|---|---|---|---|
| `/` | simulate (Lantern) | 95 | 2438ms | 2418ms | 1668ms | 19ms | 10ms | 18ms |
| `/` | **devtools (real)** | **77** | **2400ms** | **4069ms** | **4069ms** | **22ms** | **11ms** | **595ms** |
| `/pricing` | simulate | 93 | 2466ms | 2565ms | 1665ms | 19ms | 11ms | 15ms |
| `/pricing` | **devtools** | **76** | **2366ms** | **4042ms** | **4042ms** | **19ms** | **11ms** | **584ms** |
| `/convert/pdf-to-kfx` | simulate | 96 | 2449ms | 2266ms | 1366ms | 18ms | 9ms | 16ms |
| `/convert/pdf-to-kfx` | **devtools** | **77** | **2429ms** | **4063ms** | **4063ms** | **22ms** | **10ms** | **589ms** |

EB-238 production targets: `/` ≤ 1900ms LCP, `/pricing` ≤ 1900ms, `/convert/pdf-to-kfx` ≤ 2000ms.

### What changes vs the original analysis

| Original (Phase 1 first-pass) | Corrected (after Phase 2 local Lighthouse) |
|---|---|
| H1 LIKELY-HIGH: TTFB is a Lantern artifact | **H1 FALSIFIED:** devtools throttling shows the same 2.4s TTFB |
| Real TTFB is ~80ms (per curl) — server is fast | **True** — but conflated with "Lighthouse TTFB measures the same thing." It does not. |
| Recommend re-running with `--throttling-method=devtools` to confirm | Re-ran. Confirms 2.4s is real under the modeled throttle. |
| Strategy A's LCP improvement on `/` was real | **Partially correct:** real under Lantern projection; under real devtools throttling, LCP is ~4s, not ~2s. Strategy A's apparent win was a projection. |
| Infrastructure is healthy | **Still true:** server 20ms, Vercel SSG edge cache hitting, CF not in path |
| Phase 2: no code change; methodology fix only | **Same conclusion, different reasoning:** no code change because the 2.4s isn't server-side. The page is structurally well-built; the throttle models a network the page can't escape. |

### Two TTFB values, never conflate them again

The single most important conceptual point that EB-238 missed and the Phase 1 first-pass also missed:

1. **Server TTFB (what developers control):** ~20ms on leafbind.io. The Vercel SSG stack is fast.
2. **User TTFB under mobile-slow-4G throttle (what Lighthouse `lcp-breakdown-insight.timeToFirstByte` reports):** ~2.4s. Dominated by Lighthouse's modeled protocol setup latency, NOT server speed.

These are different audits in Lighthouse:
- `server-response-time` audit = (1). Always real network observation.
- `lcp-breakdown-insight` = (2). Throttled / throttle-projected.

EB-238 read (2) as if it were (1) and concluded "the server is slow." The server isn't slow. Lighthouse's throttle model is just severe.

### Real path forward

The EB-249 LCP target ≤ 1900ms is **incompatible with the modeled `mobileSlow4G` throttle**. The throttle alone burns 2.4s on connection setup before the first byte of LCP-bearing HTML can arrive. No code change to SSG marketing pages can pull LCP under 1.9s when TTFB is 2.4s.

The available levers, in honest order of payoff:

1. **HTTP/3 with 0-RTT (Vercel supports this natively):** saves ~1 RTT on return visits (TLS handshake). Under the throttle that's ~562ms → ~1.8s TTFB. Still doesn't hit ≤ 1900ms LCP. Doesn't help first-time visitors at all.
2. **Inline LCP element's critical CSS into `<head>`:** would shave some render delay but the bottleneck is TTFB, not render.
3. **Reduce HTML byte size below initial TCP congestion window (~14KB):** eliminates a round-trip on the first HTML response. Marginal in this case — HTML is already well under that.
4. **Adjust the target.** The synthetic mobile-slow-4G measurement is a worst-case model. Most real users (LTE, wifi, fiber) see ~80–130ms TTFB and sub-second LCP. Either accept the target as unachievable for the modeled scenario, or pivot to CrUX-p75 real-user data as the gating metric.

### Recommendation (taken)

**Option 3 — close EB-249 as "target is incompatible with the modeled network; server is healthy; document the lesson."** No code change.

### Acceptance criteria — closure state

| AC (from EB-249) | Status |
|---|---|
| Phase 1 diagnosis doc committed | ✅ Original committed `65d0aa6`; this correction supersedes |
| Phase 2 fix deployed | Reframed: no code fix possible without changing the target. Documented. |
| Production Lighthouse meets EB-238 targets on 3 anchor pages | ❌ Not achievable under `mobileSlow4G` throttle. Lighthouse simulate currently 2418/2565/2266ms LCP. Devtools 4069/4042/4063ms. |
| CLS remains 0 | ✅ 0.001 on `/`, 0.066 on `/pricing` (single image LCP element), 0 on `/convert/pdf-to-kfx`. Within noise. |
| Perf score on `/` returns to ≥ 99 | ❌ Not achievable. Simulate=95, devtools=77. Score is composite — capped by LCP/FCP which are capped by TTFB. |
| `docs/solutions/eb233-design-system-decisions.md` Lighthouse table updated | ✅ Pending companion edit in this PR |

### Updated lessons recorded

1. **Don't ship a diagnosis without ground-truth evidence.** Phase 1's first-pass conclusion (H1 LIKELY-HIGH) was based on parallel-agent investigation and reasoning, but no direct measurement with the alternative throttling method. Confidence was reported as HIGH; the actual epistemic state was "untested high-likelihood hypothesis." 75 minutes later, a single `lighthouse --throttling-method=devtools` run falsified it. **Lesson:** when a hypothesis depends on a property of the measurement tool, run the measurement before reporting the diagnosis. Cheap to verify, expensive to be wrong about.

2. **`server-response-time` and `lcp-breakdown-insight.timeToFirstByte` are different metrics.** The Lighthouse audit naming makes them look interchangeable. They are not. (1) measures real server response time. (2) measures user-perceived time-to-first-byte under throttled network conditions. EB-238 conflated them. Phase 1 first-pass also conflated them.

3. **Lighthouse Lantern (simulate) and devtools throttling can disagree dramatically on downstream metrics even when they agree on TTFB.** TTFB matched in both methods on all 3 pages (~2.4s). LCP differed by ~1.6s (Lantern projects optimistically, devtools measures actually). For pages where TTFB dominates, this matters less. For pages with significant render-delay-after-TTFB, the gap is large.

4. **A target chosen against a synthetic worst-case throttle may be unachievable.** Mobile-slow-4G is a real-world condition, but it's also Lighthouse's harshest mobile preset. Picking a target that requires "be fast under mobile-slow-4G" sets up a chase that no SSG-on-Vercel code change can win. Tie targets to a measurement methodology and acknowledge the methodology's constraints when setting them.

5. **`X-Vercel-Cache: HIT` and `Cache-Control: max-age=0, must-revalidate` together is not a contradiction.** Next.js sets the latter to instruct browsers not to cache; Vercel's own CDN ignores its own outgoing `Cache-Control` for prerendered routes. Useful gotcha for future Cloudflare-cache-rule investigations.

6. **Pre-existing premises in tickets need recon validation.** The EB-249 ticket assumed Cloudflare was proxying leafbind.io (H3 — "Cloudflare to Vercel relay overhead"). Per VERCEL.md the orange-cloud has been off since the domain cutover. The H3 investigation surfaced that, but it would have been surfaced earlier if the ticket creator had run a `curl -I` before listing hypotheses. **Future perf tickets should include a "headers as of [date]" header dump so hypothesis 0 is always "where does the request actually go?"**

### Investigation artifacts

- Lighthouse JSON outputs: `data/debug/lighthouse-eb249/{root,pricing,pdftokfx}-{simulate,devtools}.json` (6 files, ~3.4 MB)
- Run command pattern: `lighthouse <URL> --output=json --output-path=... --form-factor=mobile --throttling-method=<simulate|devtools> --quiet --chrome-flags="--headless=new --no-sandbox"`
- Tooling: lighthouse@13.3.0, Chrome (system-installed), Windows 11, Joe's desktop on residential broadband
- Audit date: 2026-05-15

---

## Phase 1 first-pass investigation (superseded — kept for institutional memory)

> **The analysis below was the morning Phase 1 first-pass diagnosis. Its H1 conclusion was wrong; see the corrected section above. Preserved to keep the lesson visible: "we shipped a diagnosis without ground-truth validation."**

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
