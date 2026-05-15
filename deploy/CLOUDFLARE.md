# Cloudflare API Token — Cache Purge Scope (EB-234)

This document covers the Cloudflare API token used to purge edge cache for the
`leafbind.io` zone via `POST /zones/{zone_id}/purge_cache`. Without `Cache Purge`
scope, automated audit workflows (e.g. `prompts/EB-230-unit9-lighthouse-cwv.md`)
cannot get a clean cold-cache baseline and have to fall back to `?cb=<timestamp>`
query-string busting — which does not invalidate the actual Cloudflare edge cache
and hides certain stale-content failure modes. That fallback has been retired;
edge purge is now the only acceptable cache-miss method.

Companion artifacts:
- `.mcp.json` — Cloudflare MCP server entry (HTTP transport, OAuth — used for
  read-heavy zone/DNS/WAF inspection only, not for cache purge).
- `deploy/VERCEL.md` — production deploy verification ritual; purge_cache is
  used inside that ritual after each promote.
- `docs/solutions/workflow-issues/cloudflare-cache-purge-fallback-querystring-2026-05-14.md`
  — the retired workaround being replaced by this token-scope upgrade.

Zone ID: `20967fb38b4e1feb6dfc01e4407d7225` (leafbind.io).

---

## Why a static API token instead of the MCP OAuth grant

The hosted Cloudflare MCP server at `https://mcp.cloudflare.com/mcp` uses an
OAuth flow that grants the connected app a fixed bundle of scopes when you
consent. In practice that default grant is **read-only on `cache_purge` and
`waf` write** — calls to `POST /zones/{id}/purge_cache` and WAF-write endpoints
come back with `10000: Authentication error` even after re-consent. Cloudflare
does not currently expose a scope toggle on the hosted-MCP consent screen, so
there is no way to widen the OAuth grant from inside Claude Code.

The canonical operational path is therefore:
- Hosted MCP retained for read-heavy zone/DNS/WAF inspection.
- A **static API token** with `Zone WAF: Write` + `Cache Purge` scopes,
  stored in Bitwarden, used directly against the REST API for write-side
  operations (cache purge, WAF rule edits).

Reference: memory `reference_cloudflare_mcp_oauth_scope.md` captures the
discovery that the hosted-MCP OAuth flavor in use doesn't expose scope
selection. Cache Purge by URL is available on the Cloudflare Free plan, so
this is a permission/auth-flavor change, not a billing change. Free-plan
limit: 1000 purges/day, well within audit cadence.

---

## Token creation (one-time, in the Cloudflare dashboard)

Token creation requires the Cloudflare dashboard — you cannot create or rotate
an API token via MCP.

1. Open https://dash.cloudflare.com/profile/api-tokens.
2. Click **Create Token** → **Custom token** → **Get started**.
3. **Token name:** `Cloudflare leafbind-auth` (this name is what `bw get
   password` looks up; if you rename, also update the Bitwarden item name and
   any caller scripts).
4. **Permissions:** add at minimum
   - **Zone — Cache Purge — Purge**
   - **Zone — WAF — Edit** (a.k.a. `Zone WAF: Write`)

   Optional extras if this token is replacing other read-only inspection
   tokens: `Zone — Zone — Read`, `Zone — DNS — Edit`, `Zone — Zone Settings
   — Edit`, `Zone — Cache Rules — Edit`. Principle of least privilege —
   only add what the workflow actually needs.
5. **Zone Resources:** Include — **Specific zone** — `leafbind.io`. Avoid
   `All zones from an account` unless intentional.
6. **Client IP Address Filtering:** leave blank unless issuing for a
   fixed-IP deploy host.
7. **TTL:** leave blank, or set a reminder to rotate annually.
8. **Continue to summary** → review → **Create Token**.
9. Copy the token value (Cloudflare shows it once; revoke + reissue is the
   only recovery).

---

## Storing and retrieving the token

The token lives in Bitwarden:

- **Item name:** `Cloudflare leafbind-auth`
- **Field:** Password
- **Folder/collection:** match your existing convention; no special
  requirements.

The token is never committed to git, never pasted into `.env` / `.env.*`,
never written to a file in the repo, and never echoed in tool output.
`.env`, `.env.*`, `*.key`, `*.pem`, and `secrets/**` are all blocked by the
project's credential-write guard regardless.

### How automation reads the token

The pattern is **Bitwarden CLI fetch into a process-scoped variable, used
once as a Bearer header, then discarded**.

For interactive Claude Code sessions, the user pre-unlocks the vault and
writes the session key to a gitignored helper file:

```powershell
bw unlock --raw | Set-Content debug\bw-session.txt -NoNewline
```

`debug\bw-session.txt` is gitignored. Subagents that need the token then
run, per PowerShell invocation (shell state does not persist between tool
calls):

```powershell
$env:BW_SESSION = (Get-Content debug\bw-session.txt -Raw).Trim()
$cfToken = bw get password "Cloudflare leafbind-auth"
$headers = @{
    Authorization  = "Bearer $cfToken"
    "Content-Type" = "application/json"
}
# ...use $headers in Invoke-RestMethod / Invoke-WebRequest...
$cfToken = $null
Remove-Variable cfToken -ErrorAction SilentlyContinue
```

Guardrails for callers:
- Never `Write-Output`, log, or echo `$cfToken`.
- Never include the token in error messages — sanitize response bodies
  before reporting if you need to surface an error.
- Treat the token like a webhook signing secret: visible only inside the
  one tool call that uses it.

For non-interactive deploy hosts, the same pattern applies but `BW_SESSION`
is typically fed in from a CI secret or a long-lived service-account
unlock — out of scope for this doc; see ClaudeInfra secrets policy.

---

## Verification command — run after rotation or before audits

Use the static token via direct REST (not via MCP). A successful purge
returns HTTP 200 with `success: true`.

```powershell
$env:BW_SESSION = (Get-Content debug\bw-session.txt -Raw).Trim()
$cfToken = bw get password "Cloudflare leafbind-auth"
$headers = @{ Authorization = "Bearer $cfToken"; "Content-Type" = "application/json" }
$body = '{"files": ["https://leafbind.io/"]}'
$resp = Invoke-RestMethod -Method Post `
    -Uri "https://api.cloudflare.com/client/v4/zones/20967fb38b4e1feb6dfc01e4407d7225/purge_cache" `
    -Headers $headers -Body $body
$resp.success     # expect: True
$resp.result.id   # expect: a non-empty job/zone identifier
$cfToken = $null; Remove-Variable cfToken
```

Expected response shape:

```json
{
  "success": true,
  "errors": [],
  "messages": [],
  "result": { "id": "<purge-job-or-zone-id>" }
}
```

WAF write smoke-test (verifies the second scope on the same token without
making a real rule change — list endpoint round-trip):

```powershell
$env:BW_SESSION = (Get-Content debug\bw-session.txt -Raw).Trim()
$cfToken = bw get password "Cloudflare leafbind-auth"
$headers = @{ Authorization = "Bearer $cfToken" }
Invoke-RestMethod -Method Get `
    -Uri "https://api.cloudflare.com/client/v4/zones/20967fb38b4e1feb6dfc01e4407d7225/firewall/rules" `
    -Headers $headers | Select-Object -ExpandProperty success
$cfToken = $null; Remove-Variable cfToken
```

If purge returns `10000: Authentication error` (HTTP 403):
- Confirm the new token's Zone Resources include `leafbind.io` (not "All
  zones from an account" without the specific zone listed).
- Confirm `Cache Purge → Purge` is in the permission list (it's a separate
  permission from `Cache Rules → Edit`).
- Confirm the Bitwarden item is named exactly `Cloudflare leafbind-auth`
  and the **Password** field holds the token (not a Note).
- Confirm `bw status` reports `unlocked` after loading `BW_SESSION`. If it
  still reports `locked`, the session file is stale — re-unlock the vault.

---

## Pre-audit gate — confirm token scope before running a Lighthouse audit

Before kicking off `prompts/EB-230-unit9-lighthouse-cwv.md` (or any future
audit that depends on a true cold-cache baseline), run the verification
command above. If it returns anything other than `success: true` + HTTP
200, fix the token scope before the audit, not during it — query-string
busting is no longer an acceptable fallback (see the retired solution doc
linked in the Why section).

---

## What is NOT the fix path

Earlier iterations of this doc proposed re-running the Cloudflare MCP OAuth
handshake to "pick up the rotated permissions." That path was investigated
and discarded: the hosted MCP grant in use does not expose `cache_purge` or
`waf:write` as toggleable scopes on the consent screen, so re-consent
produces the same read-only grant. Use the static-token + REST path
documented above instead.
