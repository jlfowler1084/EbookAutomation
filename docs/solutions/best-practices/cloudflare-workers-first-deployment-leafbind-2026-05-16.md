---
ticket: EB-264
date: 2026-05-16
author: Joe Fowler
tags: [cloudflare-workers, wrangler, kv, turnstile, resend, leafbind, deployment-topology, first-of-kind]
module: cloudflare/contact-worker
problem_type: deployment-topology
related:
  - EB-264 (parent ticket — support inbox + on-site contact form)
  - leafbind-email-auth-stack-2026-05-16.md (the auth stack the Worker depends on)
  - EB-45 (Leafbind freemium web service — parent epic)
---

# First Cloudflare Worker on leafbind.io — `forms.leafbind.io` topology, KV-prefixed rate limiting, secrets pattern

This is the canonical reference for adding any future Cloudflare Worker to the leafbind.io zone. The patterns captured here are the load-bearing decisions that took the longest to get right during the EB-264 planning rounds (two rounds of multi-persona document-review) and during implementation — not the obvious infrastructure setup.

## The most important decision: dedicated subdomain, not path-sharing

**`forms.leafbind.io`** hosts the Worker, NOT `api.leafbind.io/contact`. This was the single most consequential choice in the plan and was a P0 correction during document-review.

**Why:** `api.leafbind.io` serves the production FastAPI conversion backend on the Hetzner VM (per `deploy/VERCEL.md`, `deploy/nginx.conf`, and `web_service/frontend/next.config.js` `NEXT_PUBLIC_API_URL`). If the Worker had been bound to `api.leafbind.io/contact`, every future CORS/cache/WAF rule change to that subdomain would touch both the Worker and the FastAPI backend. Path-pinning on a shared subdomain creates an ongoing shared-surface risk that compounds with each new rule.

**Provisioning pattern:**

1. Add a DNS A record for the new subdomain to a placeholder IP. RFC 5737 reserved space is the right choice — `192.0.2.1`. Mark it **proxied** (orange-cloud).
2. The Worker route binding (`pattern = "forms.leafbind.io/contact"` in `wrangler.toml`) intercepts before any origin server is consulted. The placeholder IP is never actually contacted.
3. If the route is ever removed without removing the DNS record, requests to `forms.leafbind.io` get a Cloudflare 1000-series origin error — fail-loud, not a silent fallthrough to some random origin.

**When to apply this pattern again:**

- Adding a new Worker for a different feature → use a new dedicated subdomain (e.g., `webhook.leafbind.io`, `auth.leafbind.io`), NOT a new path on an existing subdomain.
- Adding a second Worker for an extension of an existing feature → keep on the same subdomain only if the trust boundary and operational concerns are identical. Otherwise, new subdomain.

## KV namespace pattern: one namespace, key prefixes

**`CONTACT_KV`** is a SINGLE namespace with key prefixes (`rl:ip:`, `rl:email:`, `ack:`), NOT three separate namespaces.

**Why:** TTL semantics and quota limits are per-key, not per-namespace. Inspectability via `wrangler kv key list --prefix=rl:ip:` works as well as having a dedicated namespace. Earlier plan drafts had three namespaces; document-review flagged this as over-engineering for v1 volume.

**Provisioning:**

```powershell
wrangler kv namespace create CONTACT_KV
```

Returns an ID. Paste it into `wrangler.toml` at `kv_namespaces.id` (replacing the `PLACEHOLDER_KV_NAMESPACE_ID` literal). Commit the wrangler.toml — the namespace ID is not a secret.

**Key prefix table:**

| Prefix | Purpose | Example | TTL |
|---|---|---|---|
| `rl:ip:<bucket>` | Per-IP rate limit (with IPv6 `/64` bucketing for IPv6 addresses) | `rl:ip:1.2.3.4:486370` | 3600s |
| `rl:email:<sha256>:<bucket>` | Per-email rate limit (sha256 of lowercase email — never plaintext) | `rl:email:a3b1...:486370` | 3600s |
| `ack:<sha256>` | Auto-ack throttle (don't re-acknowledge the same sender repeatedly) | `ack:a3b1...` | 86400s |

`<bucket>` is `floor(unix_seconds / 3600)` — fixed-window. Known limitation: at the hour boundary, an attacker can get 10 requests in ~2 seconds (5 before, 5 after). Accepted for v1; upgrade to sliding window if abuse materializes.

## Secrets pattern: three secrets, all via `wrangler secret put`

The Worker uses three secrets, NONE in the repo:

| Secret | Source | Format |
|---|---|---|
| `TURNSTILE_SECRET_KEY` | Cloudflare Dashboard → Turnstile → leafbind.io site → Secret Key | `0x4AAA...` |
| `RESEND_API_KEY` | Resend dashboard → API Keys | `re_...` |
| `SUPPORT_INBOX_ADDRESS` | Operator-provided literal | `support@leafbind.io` |

**`SUPPORT_INBOX_ADDRESS` is stored as a secret even though it's not actually secret.** This is intentional — pulling it from secret store means rotating the destination (e.g., to `help@leafbind.io`) doesn't require a code change and redeploy. It's a "configuration as secret" pattern.

**Operator workflow for setting secrets:**

```powershell
cd cloudflare\contact-worker
wrangler secret put TURNSTILE_SECRET_KEY    # paste secret from Turnstile dashboard
wrangler secret put RESEND_API_KEY          # paste re_... from Resend
wrangler secret put SUPPORT_INBOX_ADDRESS   # paste: support@leafbind.io
```

Each command prompts interactively for the value. The values are encrypted at rest in Cloudflare's backend.

**Local-dev placeholders** live in `cloudflare/contact-worker/.dev.vars` (NOT in the repo — gitignored at both the worker level and the root `.gitignore`):

```
TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA  # Cloudflare's "always-passes" test key
RESEND_API_KEY=re_placeholder
SUPPORT_INBOX_ADDRESS=support@leafbind.io
```

The `1x0000000000000000000000000000000AA` is a well-known Cloudflare test key for Turnstile that always returns valid in development.

## Turnstile site key is public — handle as public, but not careless

The Turnstile **site key** (used in the frontend, visible in HTML source) is public by design — only the **secret key** (used in the Worker for siteverify) is private.

**Pattern for the public site key:**

- Set `NEXT_PUBLIC_TURNSTILE_SITE_KEY` in Vercel environment variables for the leafbind project.
- Reference in frontend code via `process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? ""`.
- DO NOT hardcode in the source — the site key changes per environment (dev/preview/prod could in principle differ), and inlining couples deploys.

**If the site key env var is missing,** the contact form falls into the "no Turnstile token" path (line 117-119 of ContactForm.tsx). The Worker rejects with `"Bot challenge token missing."` and the frontend shows the user a graceful "Bot check failed" message. Not silent — fail-loud at the recipient.

## CORS pattern: explicit origin allowlist, no wildcard

The Worker's OPTIONS preflight handler (`src/index.ts`) explicitly allows two origins: `https://leafbind.io` and `https://www.leafbind.io`. NOT `*`.

**Why:** the Worker holds a Resend API key and KV access. A wildcard CORS allows any origin to attempt to POST a contact submission (subject to Turnstile and rate-limit, but still — defense in depth wants origin-scoped CORS as a first filter).

**When adding a new allowed origin** (e.g., for a future blog at `blog.leafbind.io`):

1. Update the origin allowlist in `src/index.ts`.
2. Bump `compatibility_date` only if you needed a new Workers runtime feature.
3. Redeploy.

## Test pattern: vanilla vitest + in-memory KV mock, not vitest-pool-workers

The plan called for `@cloudflare/vitest-pool-workers`. The 0.8.71 release has an API incompatibility with vitest 2.1.9 (`startCurrentRun` not found). EB-264 implementation switched to **standard vitest with in-memory KV mocks**.

**Why this works:** the Worker's business logic (sanitize, rate-limit, turnstile siteverify, send chain) is testable in pure TypeScript without needing the actual Workers runtime. The only Workers-runtime-specific concerns are: `request.headers.get("CF-Connecting-IP")` (mock the Request), KV (mock with a Map-backed object), and `fetch()` to siteverify/Resend (mock with a stubbed global).

**62 tests** in 4 files cover every plan-enumerated scenario: XSS, CRLF, over-cap input, IPv6 `/64` bucket aggregation, case-variant email rate-limit bucketing, network-timeout fail-closed on Turnstile, single-use replay rejection.

**For full Workers-runtime integration testing**, the pattern is `wrangler dev` (runs the Worker locally on a real runtime against a local KV) + `curl` against `http://localhost:8787/contact`. See `cloudflare/contact-worker/vitest.config.ts` comments for the recipe.

**If the `@cloudflare/vitest-pool-workers` API stabilizes in a future release**, migration from in-memory mocks is straightforward — the test files import nothing runtime-specific that would break under the pool.

## Deployment workflow (operator action sequence)

This is the canonical "first Worker deploy on leafbind" runbook. For EB-264 specifically and for any future Worker on this zone.

1. **`wrangler login`** — opens browser OAuth flow. One-time per machine.
2. **Verify zone access:** `wrangler whoami` should list `leafbind.io` under accessible zones (the OAuth flow grants account-scoped access).
3. **Create KV namespace:** `wrangler kv namespace create CONTACT_KV`. Copy the returned `id` value into `cloudflare/contact-worker/wrangler.toml` at `kv_namespaces.id` (replace the placeholder). **Commit and push** that change.
4. **Provision Turnstile widget:** Cloudflare Dashboard → Turnstile → Add Site. Fields: Site name `leafbind contact`, Domain `leafbind.io`. Widget mode: **Managed** (Cloudflare picks visible/invisible based on risk). Get the Site Key (`0x4AAA...`) and Secret Key (`0x4AAA...` — different prefix? confirm in dashboard).
5. **Set Vercel env var** `NEXT_PUBLIC_TURNSTILE_SITE_KEY` (the site key from step 4) for Preview AND Production environments. Re-deploy the frontend so the var bakes into the build.
6. **Put Worker secrets** (from `cloudflare/contact-worker/` directory):
   ```
   wrangler secret put TURNSTILE_SECRET_KEY    # paste from step 4
   wrangler secret put RESEND_API_KEY          # paste re_... from Resend
   wrangler secret put SUPPORT_INBOX_ADDRESS   # paste: support@leafbind.io
   ```
7. **Dry-run deploy:** `wrangler deploy --dry-run` — confirms build succeeds, surfaces any wrangler.toml issues without touching production. Specifically verify the route binding shows `forms.leafbind.io/contact` and the KV binding shows the namespace ID (not the placeholder).
8. **Live deploy:** `wrangler deploy`. Confirms the route binding and reports the Worker URL.
9. **Verify route binding:**
   ```
   curl -X OPTIONS https://forms.leafbind.io/contact -H "Origin: https://leafbind.io" -i
   ```
   Expect 204 with full CORS headers. Then a positive POST:
   ```
   curl -X POST https://forms.leafbind.io/contact \
     -H "Origin: https://leafbind.io" \
     -H "Content-Type: application/json" \
     -d '{"name":"smoke","email":"smoke@test.local","topic":"general","message":"smoke","turnstile_token":"1x00000000000000000000AA"}'
   ```
   Expect 200 `{"ok":true}` (the `1x...AA` test token is the always-pass key for development).
10. **Regression check:** `curl https://api.leafbind.io/health` — must return 200. FastAPI backend untouched.

## Anti-patterns to avoid

- **Do not bind a Worker route on `api.leafbind.io/*`.** That subdomain is reserved for the FastAPI backend. Every shared-surface CORS/cache/WAF change becomes a multi-system risk.
- **Do not skip `--dry-run` on first deploy.** A misconfigured route can shadow the wrong path; dry-run surfaces this without production impact.
- **Do not commit `.dev.vars`.** Add to `.gitignore` BEFORE creating the file. Verify with `git check-ignore`.
- **Do not log `env` or sensitive headers.** The Worker's logging discipline (in `src/index.ts`) strips `turnstile_token` and `email` from error logs.
- **Do not flip the apex `leafbind.io` from DNS-only (grey-cloud) to proxied (orange-cloud).** It's intentionally DNS-only to Vercel; flipping breaks Vercel's TLS/edge behavior.
- **Do not commit secrets in `wrangler.toml`.** The file is checked into the repo; secrets go via `wrangler secret put` to Cloudflare's encrypted store.
- **Do not adopt `@cloudflare/vitest-pool-workers` until its API stabilizes** (last checked 2026-05-16, v0.8.71 incompatible with vitest 2.1.9). Vanilla vitest + in-memory mocks covers the business logic; `wrangler dev` covers runtime integration.

## Quota and ceiling awareness (Cloudflare Workers free tier)

- **KV writes:** 1,000/day. Each accepted contact submission writes 2-3 keys (rate-limit IP, rate-limit email hash, ack). Effective ceiling: ~333-500 accepted submissions/day. ABOVE the Resend daily cap (100 submissions × 2 mails = 200 sends/day), so Resend trips first.
- **Worker requests:** 100,000/day. Trivially out of reach at v1 volume.
- **KV reads:** 100,000/day. Out of reach.
- **CPU time:** 10 ms per request. Worker logic (HTTP fetch to Turnstile siteverify + KV reads/writes + Resend fetch) is well under this.

If the contact form ever hits these limits, the Worker should NOT fail open — KV write failures specifically must fail closed (reject the submission with a generic 500 error) to prevent rate-limit bypass via quota exhaustion.

## Secret-rotation reminders

- **`RESEND_API_KEY`**: rotate every 90 days. Calendar reminder: 2026-08-14. Compromise blast radius: ability to send mail authenticated as leafbind.io.
- **`TURNSTILE_SECRET_KEY`**: rotate every 90 days. Calendar reminder: 2026-08-14. Compromise blast radius: spoofed siteverify replies (token-replay attacks).
- **`SUPPORT_INBOX_ADDRESS`**: change when destination changes (e.g., new email alias). Low rotation cadence by design.

Rotation procedure: generate new secret in source (Resend / Turnstile dashboard), `wrangler secret put` the new value (overwrites the old), verify with a live OPTIONS+POST sequence (step 9 above), then revoke the OLD secret in its source dashboard. Order matters: never revoke before the new one is live, otherwise inflight requests fail.

## Operator status at time of writing (2026-05-16)

The Worker code is committed (`3eb7786`, `9b3c72c`). Deployment has NOT yet happened — `wrangler login`, KV namespace creation, Turnstile widget setup, and three `wrangler secret put` invocations are pending operator action. The placeholder values in `wrangler.toml` (`PLACEHOLDER_KV_NAMESPACE_ID`) MUST be replaced before `wrangler deploy` is run. The `forms.leafbind.io` A record was provisioned at 192.0.2.1 (RFC 5737 reserved) during EB-264 Unit 1 and is awaiting the route binding.

When deployment completes, follow steps 9 and 10 above for live verification. The Phase 8 E2E smoke test in the EB-264 plan covers the full integration including the Resend send and Gmail forward.

## Related references

- `cloudflare/contact-worker/wrangler.toml` — declarative config
- `cloudflare/contact-worker/src/types.ts` — Env interface (all secret bindings)
- `cloudflare/contact-worker/src/index.ts` — entry, OPTIONS preflight, POST chain
- `docs/solutions/best-practices/leafbind-email-auth-stack-2026-05-16.md` — the email auth side of this stack
- EB-264 plan: `docs/plans/2026-05-15-003-feat-eb264-contact-form-and-worker-plan.md`
- EB-278 (DMARC quarantine follow-up — created 2026-05-16, due 2026-06-15)
