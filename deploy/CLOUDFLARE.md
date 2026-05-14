# Cloudflare API Token — Cache Purge Scope (EB-234)

This document covers the Cloudflare API token rotation required so that the
Cloudflare MCP server can purge edge cache for the `leafbind.io` zone via
`POST /zones/{zone_id}/purge_cache`. Without this scope, automated audit
workflows (e.g. `prompts/EB-230-unit9-lighthouse-cwv.md`) cannot get a clean
cold-cache baseline and have to fall back to `?cb=<timestamp>` query-string
busting — which does not invalidate the actual Cloudflare edge cache and
hides certain stale-content failure modes.

Companion artifacts:
- `.mcp.json` — Cloudflare MCP server entry (HTTP transport, OAuth).
- `deploy/VERCEL.md` — production deploy verification ritual; purge_cache is
  used inside that ritual after each promote.
- `docs/solutions/workflow-issues/cloudflare-cache-purge-fallback-querystring-2026-05-14.md`
  — the retired workaround being replaced by this token-scope upgrade.

Zone ID: `20967fb38b4e1feb6dfc01e4407d7225` (leafbind.io).

---

## Why

The Cloudflare API token currently authenticated by the MCP server has
read-heavy zone permissions (`#zone:read`, `#dns_records:edit`, `#waf:read`,
`#zone_settings:edit`, etc.) but no `#cache_purge` permission. Calling the
purge endpoint with that token returns `10000: Authentication error`. The
fix is a one-time token-scope upgrade in the Cloudflare dashboard.

Cache Purge by URL is available on the Cloudflare Free plan, so this is a
permission change, not a billing change. Free-plan limit: 1000 purges/day,
well within audit cadence.

---

## Diagnostic — confirm the gap before rotating

Before rotating, confirm the gap is real:

```
mcp__cloudflare__execute
  POST /zones/20967fb38b4e1feb6dfc01e4407d7225/purge_cache
  body: {"files": ["https://leafbind.io/"]}
```

Expected (current, broken state): error `10000: Authentication error`.
Expected (after rotation): `200` with `result.id` returned.

If the diagnostic already returns 200, the token is already correctly
scoped and no rotation is needed — skip ahead to the verification step.

---

## Steps to rotate the token

Token creation requires the Cloudflare dashboard. You cannot create or
rotate an API token via MCP.

1. Open https://dash.cloudflare.com/profile/api-tokens.
2. Click **Create Token**.
3. Choose **Get started** under **Custom token** (do not use one of the
   pre-built templates — they include scopes you don't need).
4. **Token name:** `leafbind-mcp-cache-purge` (or any name you'll recognize
   later).
5. **Permissions** — add the following rows. Preserve any scopes the current
   token already grants if you are creating a single replacement token; the
   ones listed below are the minimum needed for the existing leafbind.io
   workflows plus the new purge scope:
   - **Zone — Cache Purge — Purge** (this is the new one)
   - Zone — Zone — Read
   - Zone — DNS — Edit
   - Zone — Zone Settings — Edit
   - Zone — Cache Rules — Edit (if you tune cache rules via MCP)
   - Zone — Workers Routes — Edit (only if you manage workers from MCP)
6. **Zone Resources:** Include — **Specific zone** — `leafbind.io`.
   Do not grant `All zones from an account` unless you have a deliberate
   reason — the principle of least privilege applies here.
7. **Client IP Address Filtering:** leave blank unless you are issuing the
   token for a fixed-IP deploy host.
8. **TTL:** leave blank (no expiry) or set a reminder to rotate annually.
9. Click **Continue to summary** → review → **Create Token**.
10. Copy the token value. **You will only see it once.** Cloudflare does not
    let you retrieve it later — only revoke and reissue.

---

## Where to update the token after creation

The Cloudflare MCP server in this repo is configured at `.mcp.json`:

```json
"cloudflare": {
  "type": "http",
  "url": "https://mcp.cloudflare.com/mcp"
}
```

This is an HTTP-transport MCP entry that uses **OAuth** for authentication
(not a static bearer token in `.mcp.json` or an environment variable). On
first use the MCP server walks you through an OAuth handshake in your
browser; the access it gets is bound to whatever scopes the Cloudflare
account / token grants for the API surface it exercises.

Because the auth is OAuth-driven, the rotation flow is:

1. Create the new token in the dashboard with `Cache Purge` included (steps
   above). The new token is for **your records / break-glass use** — you do
   not paste it into `.mcp.json`.
2. In a Claude Code session, re-run the OAuth flow for the Cloudflare MCP
   server so it re-authenticates against the updated account permissions.
   In practice this happens automatically on the next MCP call if Cloudflare
   has surfaced the new scope to the connected app; if not, run
   `/mcp` → reconnect `cloudflare`, or revoke the prior connection at
   https://dash.cloudflare.com/profile/applications and reconnect.
3. Never commit the raw token value. `.env`, `.env.*`, `*.key`, `*.pem`,
   and `secrets/**` are all blocked by the project's credential-write
   guard; `.mcp.json` is committed but only contains the URL, not secrets.

If a future change moves Cloudflare MCP off OAuth onto a static bearer token
(e.g. switching to `cloudflare/mcp-server-cloudflare` self-hosted), the
token would belong in `.env` under a key like `CLOUDFLARE_API_TOKEN` and
referenced from `.mcp.json` via `${env:CLOUDFLARE_API_TOKEN}`. That is not
the current shape.

---

## Verification command — run after rotation

Run this through the Cloudflare MCP. A successful purge returns `200` with
a `result.id` UUID.

```
mcp__cloudflare__execute
  POST /zones/20967fb38b4e1feb6dfc01e4407d7225/purge_cache
  body: {"files": ["https://leafbind.io/"]}
```

Expected response shape:

```json
{
  "success": true,
  "status": 200,
  "result": { "id": "<uuid>" },
  "errors": []
}
```

If you still see `10000: Authentication error` after rotation:
- Confirm the new token's Zone Resources include `leafbind.io` (not just
  "All zones from an account" without the specific zone listed).
- Confirm `Cache Purge → Purge` is in the permission list, not just
  `Cache Rules → Edit` (different permission).
- Re-run the OAuth handshake for the Cloudflare MCP server so it picks up
  the rotated permissions.
- If the MCP server is caching an old OAuth grant, revoke the prior grant
  at https://dash.cloudflare.com/profile/applications and reconnect.

---

## Pre-audit gate — confirm token scope before running a Lighthouse audit

Before kicking off `prompts/EB-230-unit9-lighthouse-cwv.md` (or any future
audit that depends on a true cold-cache baseline), run the verification
command above. If it returns anything other than `200`, fix the token
scope before the audit, not during it — query-string busting is no longer
an acceptable fallback (see the retired solution doc linked in the Why
section).
