---
title: "feat: EB-324 Wave 1 — Post-Conversion Result Page Action Cluster"
type: feat
status: active
date: 2026-05-19
origin: docs/brainstorms/2026-05-19-eb-324-post-conversion-action-cluster-requirements.md
---

# EB-324 Wave 1 — Post-Conversion Result Page Action Cluster

## Overview

After a user uploads a PDF to leafbind.io and conversion completes, today's result page (`web_service/frontend/app/(app)/status/[id]/page.tsx`) is a dead-end: Download + "← Convert another file" and nothing else. Wave 1 makes the page productive — adds Send-to-Kindle for EPUB outputs, on-page re-convert to other formats (MOBI free, KFX premium with token), a stay-in-place page model with parent/child jobs, a coarse TTL countdown, and the infrastructure (schema, refund flow, rate-limiting, telemetry) to make all of that safe and durable.

Wave 2 (multi-format-on-upload) is a sibling ticket gated on Wave 1 telemetry — **out of scope for this plan**.

## Problem Frame

Three user-facing problems flow from the current terminal result page (see origin: `docs/brainstorms/2026-05-19-eb-324-post-conversion-action-cluster-requirements.md`):

1. **Output format is chosen silently.** A `FormatSelector` exists in `web_service/frontend/components/UploadZone.tsx:110` but is visually de-emphasized, defaulting to EPUB.
2. **No action besides "download" is reachable.** Kindle email delivery and premium-format upgrade both require leaving the page.
3. **No path to convert the same file to another format.** Source files persist for 1h (free) / 24h (premium) per `web_service/config.py:97-98` but the result page exposes no way to re-use them.

Combined effect: uploading feels transactional rather than productive, and the freemium upsell is weaker than it could be because the moment of greatest user attention (conversion complete) terminates the session.

## Requirements Trace

(Numbering matches the origin requirements document. Wave 2 requirements R7–R10 are out of scope.)

**Result-page action cluster:**
- **R1.** Result page presents Download, Send-to-Kindle (EPUB only), and convert-to-another-format actions on done jobs within retention window
- **R2.** Re-convert re-uses already-uploaded source (no re-upload), gated by TTL + (premium) credit availability
- **R2.1.** Stay-in-place page model with parent/child jobs and `children[]` in status response
- **R2.2.** Frontend polling continues for in-flight children after parent reaches `done`
- **R2.3.** `jobs` table gains nullable `parent_job_id` column (indexed) + `list_children()` helper
- **R2.4.** Source-data lifetime: source-copy at dispatch (chosen — see Key Technical Decisions)
- **R2.5.** Integration test for parent-TTL-elapses-while-child-running race
- **R2.6.** Premium re-convert collects token via existing `<TokenField>` on the result page
- **R2.7.** Child jobs persist `compute_token_hash(token).hex()` (hex-encoded HMAC-SHA256) in the existing `jobs.token_hash TEXT` column; `token_store.refund_token(token_hash_hex)` decodes hex → bytes for the BLOB join against `tokens.token_hash`, then atomically re-enables or writes a `refund_ledger` row

**Send-to-Kindle:**
- **R3.** Send-to-Kindle surfaces success/failure inline; known fingerprints link to EB-322
- **R3.1.** Recipient validated server-side: RFC-5322 parse + normalize + domain must be exactly `kindle.com` or `free.kindle.com`
- **R3.2.** Frontend state contract (idle/sending/success-collapsed/failure-known/failure-generic/duplicate-guard); success copy defers to R3.5
- **R3.3.** Output validated server-side: format allowlist (EPUB-eligible for leafbind today; MOBI/KFX never), **25 MiB raw cap** (calibrated against Resend's 40 MB post-base64 ceiling — see Key Technical Decisions), per-job_id binding (no separate output_id in Wave 1)
- **R3.4.** Server-side abuse prevention: 60s idempotency on `(job_id, normalized_recipient)`; output read from `job_store` only; recipient normalization rejects display-name + plus-aliasing
- **R3.5.** Approved-sender UX: form shows the From address with a link to Amazon's Personal Document Settings; success copy qualifies arrival on the approved-sender status; failure-known surfaces approved-sender check first
- **R3.6.** Resend webhook handler at `POST /webhooks/resend` MUST verify Svix signatures using the raw request body and emit graded delivery telemetry. Handles at least `email.delivered`, `email.bounced`, `email.failed`, `email.delivery_delayed`. Correlation is by Resend message ID stored on the job at send time — **never by recipient email**. Raw webhook payloads MUST NOT be logged. Webhook status represents *mail-provider* delivery (Resend → Amazon's MX), **not** Kindle-library delivery — Amazon-side E999 is still invisible to us and remains out of scope

**Retention-expired state:**
- **R4.** Disabled-state copy when TTL elapsed; "Convert another file" stays available
- **R4.1.** `GET /status/{job_id}` returns `expires_at`, `source_present`, `output_present` (gates re-convert and Send-to-Kindle independently)
- **R5.** Existing 404 path in `ConversionStatus.tsx:51-67` preserved

**Cross-wave UX standards:**
- **R11.** *(Deferred to standalone ticket per plan-review P1-15.)* Format-selector visibility on the upload page. Moved out of Wave 1 to prevent it from suppressing the post-conversion re-convert engagement signal that gates Wave 2. Files as a follow-up ticket alongside EB-324; ships after the Wave 1 measurement window completes (informed by actual re-convert telemetry).
- **R12.** Telemetry capture for the event types in Unit 9 (graded send-to-Kindle delivery + re-convert + expired-action — format-selector engagement deferred with R11)
- **R13.** Rate-limit enforcement on `/reconvert/*` and `/send-to-kindle/*`: app-level (slowapi) load-bearing + Cloudflare WAF defense-in-depth (single combined rule, see Key Technical Decisions); trusted client-IP via `CF-Connecting-IP`

## Scope Boundaries

- **Wave 2 (R7–R10 multi-format-on-upload)** is out of scope. Sibling ticket opened only if Wave 1 telemetry hits ≥15% engagement sustained across weeks 3–4 of a four-week post-launch window.
- **R6 (failure-state "try a different format")** removed entirely (not Wave 1, not Wave 2). Failure-mode UX gets its own ticket once telemetry shows what actually fails.
- **In-progress UX** (progress bar, time estimate, email-me-when-done) is **EB-315** — intentionally not in this plan.
- **Send-to-Kindle troubleshooting page** is **EB-322** — R3 links to it but does not implement it.
- **Premium EPUB→KFX quality regression** is **EB-321** — independent.
- **30-day premium retention as a product move** is a hypothetical sibling ticket only if Wave 1 telemetry shows users hitting the TTL wall on re-convert.
- **Amazon-side E999 / unapproved-sender inbound-mail bounce parsing** is intentionally deferred. The Resend send-side webhook IS wired in Wave 1 (Unit 10) and provides graded mail-provider delivery telemetry (`delivered_to_mail_server`, `bounced`, `failed`, `delivery_delayed`). What's out of scope is reading the *async reply mail* Amazon sends to our From address when delivery fails post-acceptance (E999, unapproved-sender post-April-2025) — that requires an inbound mailbox + parser, which is its own follow-up if user-reported silent failures materialize.

### Deferred to Separate Tasks

- **Cloudflare WAF rule consolidation/deployment**: The current `/stripe/webhook` rule (EB-225/EB-236) must be merged with new path matchers (`/reconvert/*`, `/send-to-kindle/*`, `/webhooks/resend`) into a single combined rule on Free plan. Deploy-side task with a Cloudflare API token holding WAF write scope — runs alongside but is not part of the code PR.
- **Resend domain + sender configuration**: provision the chosen From address (e.g., `kindle@send.leafbind.io`) in the Resend dashboard with a sending-access-only API key restricted to `leafbind.io`. Implementer verifies this exists before Unit 4 deploys.
- **Resend webhook endpoint registration**: register `https://api.leafbind.io/webhooks/resend` in the Resend dashboard and capture the Svix signing secret into `/etc/web_service.env` as `WEB_RESEND_WEBHOOK_SECRET` before Unit 10 deploys.
- **R11 — FormatSelector visibility fix**: file as a standalone ticket (e.g., EB-324a) and ship after the four-week Wave 1 measurement window completes. Holding R11 prevents suppression of the post-conversion re-convert engagement signal that gates Wave 2.

## Context & Research

### Relevant Code and Patterns

| Concern | Pattern reference |
|---|---|
| FastAPI route handlers | `web_service/routes/convert.py`, `routes/recover.py` — `Form(...)` inputs, `HTTPException(detail={"error", "code"})`, `billing_executor` for blocking I/O, `asyncio.create_task(dispatch_job(...))` for fire-and-forget |
| SQLite migrations | `web_service/job_store.py:48-83` — `_LATER_COLUMNS` list + `_apply_migrations()` with `BEGIN IMMEDIATE` (idempotent, serializes uvicorn workers); migration-race tests at `tests/test_web_job_store_migration_race.py` |
| Atomic single-use consume (mirror for refund) | `web_service/token_store.py:374-385` — `BEGIN IMMEDIATE` + `UPDATE WHERE used=0 AND ...` shape |
| Token hash | `web_service/crypto.py:127` — `compute_token_hash(token: str) -> bytes` (HMAC-SHA256). Stored as `BLOB` in `tokens.token_hash` (primary key). Stored as `hex()` string in the existing `jobs.token_hash TEXT` column (per P0-1 plan-review resolution — reuses existing column rather than colliding). Refund correlation decodes hex → bytes for the BLOB join. |
| Status response | `web_service/routes/status.py:12-49` |
| Cleanup sweep | `web_service/job_queue.py:_cleanup_job:156-163`, `_cleanup_after_download` in `routes/download.py:106-112` |
| Frontend status polling | `web_service/frontend/components/ConversionStatus.tsx:24-29` — `setInterval(poll, 5000)` with stop condition |
| Frontend API client | `web_service/frontend/lib/api.ts` — `ApiError extends Error` with `status` field; `getStatus`, `startConversion` patterns |
| Token entry component | `web_service/frontend/components/TokenField.tsx` — reuse for premium re-convert per R2.6 |
| Format selector | `web_service/frontend/components/FormatSelector.tsx` — reuse for re-convert chooser |
| Recovery-events telemetry pattern | `web_service/recovery_events_store.py:55-60` — `_VALID_EVENT_TYPES` whitelist + `log_event()` fire-and-forget |
| FastAPI tests | `tests/test_web_endpoints.py:21-67` — `TestClient` + `tmp_path` DB fixture + `dispatch_job` mocked via `AsyncMock` |
| TTL race regression pattern | `tests/test_web_sweeps.py` — add R2.5 alongside |
| Three-layer billing test model (to mirror for Send-to-Kindle) | mocked unit + signed-event e2e + manual script per `web_service/docs/stripe-verification.md` |

### Institutional Learnings

- **Resend email stack already DKIM-aligned for leafbind.io.** `docs/solutions/best-practices/leafbind-email-auth-stack-2026-05-16.md` documents the production stack. Send-to-Kindle outbound MUST flow through Resend on the established domain. DMARC progresses `p=none → p=quarantine` on **2026-06-15**; new From identities must verify DKIM alignment before that date.
- **SQLite schema-migration safety.** The `_LATER_COLUMNS` + `BEGIN IMMEDIATE` pattern in `job_store.py:48-83` is the only safe column-add idiom for the concurrent uvicorn workers. Migration tests live in `tests/test_web_job_store_migration_race.py`.
- **XSS lesson from EB-248.** `docs/solutions/security-issues/xss-unescaped-session-id-fastapi-fstring-templates-2026-05-15.md` — all interpolated values in FastAPI HTML responses MUST use `html.escape(value, quote=True)`. New plan endpoints return JSON only (no HTML render helpers added), so this is not a new concern for backend — but flagged in Unit 6 frontend testing scope because React auto-escapes but interpolated email/job_id strings in unsafe contexts (e.g., `href` attribute) still need attention.
- **Cloudflare Free-plan WAF rate-limit rule budget = 1.** From EB-230's cache-purge workaround doc and confirmed in external research. The plan's single combined rule strategy is the only viable Free-plan approach.
- **Verify tool-dependent hypotheses before shipping diagnosis** (`verify-tool-dependent-hypotheses-before-shipping-diagnosis-2026-05-15.md`). For Send-to-Kindle: test a real bounce through Resend before locking the error-state UX.
- **Test the simpler shape first** (`test-baseline-before-investing-in-tooling-2026-05-15.md`). Implementing source-copy without the refcount machinery is the right v1 — falls in line with this learning.
- **ADR-EB-181 data exemption scope.** All test fixtures land via worktree + PR; only `data/batch_reports/**` and `data/debug/**` are exempt. The migration-race tests and Send-to-Kindle MIME fixtures live in `tests/` and must ride the PR.

### External References

- **Amazon Send-to-Kindle (April 2025 change):** Unapproved-sender failures arrive as async reply emails, not SMTP bounces. Wildcard domain approvals removed — exact From address required. Sources: Good e-Reader, Amazon's customer-help page on Send-to-Kindle.
- **Amazon E999 errors:** Post-acceptance Amazon-internal conversion failure, surfaced via user dashboard and async reply email — not via SMTP. AxeeTech reference.
- **Resend Python SDK:** PyPI `resend` package (latest May 2026). Send-with-attachment, restricted API keys (sending-only scoped to domain), Svix-signed webhooks. The SDK supports a native `Idempotency-Key` header (24h window) — **Wave 1 deliberately does NOT use it** (see Key Technical Decisions, "Local 60s SQLite atomic claim is the sole dedup layer"). Sources: `https://resend.com/docs/api-reference/emails/send-email`, `https://resend.com/docs/dashboard/emails/idempotency-keys`, `https://resend.com/docs/dashboard/webhooks/event-types`, `https://resend.com/docs/dashboard/api-keys/introduction`.
- **Resend attachment ceiling:** 40 MB post-base64. Raw bytes inflate ~4/3 under base64 plus ~1.3% line-wrapping + envelope overhead, so the safe raw cap is 25 MiB (yields ~33.3 MiB encoded → ~6 MiB headroom against the 40 MB ceiling). Source: `https://resend.com/docs/dashboard/emails/attachments`.
- **slowapi for FastAPI rate-limiting:** Still maintained in 2026. Custom `key_func` reading `cf-connecting-ip` is the recommended pattern. Source: `https://slowapi.readthedocs.io/`.
- **Cloudflare WAF rate-limiting on Free:** 1 rule total, 10s period max, `cf.colo.id` automatically added as counting characteristic. Source: `https://developers.cloudflare.com/waf/rate-limiting-rules/`.

## Key Technical Decisions

- **Source-copy at dispatch over source-pinning.** The brainstorm R2.4 listed both as viable. External research recommends pinning (refcount on parent) for high fanout. Decision: **source-copy** for v1. Rationale: (a) leafbind's expected fanout is 1–2 children per parent (free→premium upsell or format swap), not 5+; (b) source-copy fully decouples child lifetime from parent — no cleanup race possible; (c) test-the-simpler-shape-first learning favors the lower-coordination option; (d) if telemetry shows high fanout patterns post-launch, switching to pinning is a localized change (add `pin_count`, modify dispatch + cleanup). Disk cost: ~20–100 MB extra per re-convert, well within VM headroom. *(see origin: Key Decisions, "Re-convert uses a stay in place page model with child jobs")*
- **Resend Python SDK over smtplib.** External research is definitive — SDK provides native attachment-MIME assembly, Svix-signed bounce-webhook verification, and restricted-scope API keys; SMTP loses all of these. (The SDK also offers a native `Idempotency-Key` header, but Wave 1 does NOT use it — see the "Local 60s SQLite atomic claim is the sole dedup layer" decision below for why layering Resend's 24h key on top of the local 60s window creates a worst-of-both-worlds lockout.) *(see origin: Deferred to Planning, "Resend integration shape")*
- **Local 60s SQLite idempotency table is the sole dedup layer; Resend `Idempotency-Key` is NOT sent.** R3.4 calls for 60s idempotency on `(job_id, normalized_recipient)`. Initially the plan composed a Resend idempotency key per send for defense-in-depth — but plan review (adversarial P1-7) caught that Resend's 24h window collides with legitimate user retries after the local 60s expires: a user who didn't see arrival, retries after 90s, would get a stale Resend cache for the next 24h while the UI showed "sent." The two layers solve the same problem at different timescales, so layering them creates a worst-of-both-worlds lockout. Decision: **omit the `idempotency_key` parameter on the Resend SDK call**. Local 60s table handles user-click-twice; after 60s, any subsequent retry is a genuine resend that hits Resend fresh. Race between two FastAPI workers within the same 60s window is serialized by SQLite `BEGIN IMMEDIATE` on the idempotency table insert. *(updated per plan-review P1-7)*
- **25 MiB raw attachment cap, calibrated against Resend's 40 MB post-base64 ceiling.** Brainstorm said 36 MB; first plan revision said 30 MB. PR #144 review (F10) re-derived the math: 30 MiB raw × 4/3 = 40 MiB encoded EXACTLY before MIME envelope or line-wrap overhead, so 30 MiB raw is *over* Resend's limit on every send. Final cap: **25 MiB raw** = `25 * 1024 * 1024` bytes → ~33.3 MiB encoded → ~6 MiB headroom against the 40 MB ceiling. The 30 MB earlier figure was wrong arithmetic, not a policy change. *(corrects origin: R3.3; refined per PR #144 review F10)*
- **Cloudflare WAF rule consolidation: single combined rule on Free plan.** Free plan allows only 1 rate-limit rule. Existing `/stripe/webhook` rule (EB-225/EB-236) must be merged with new path matchers. Rule expression uses `or` to cover all three paths; period stays at 10s (Free max); 60s windows live in slowapi inside the app. *(corrects origin: R13's "verify rule budget" gate to a concrete strategy)*
- **slowapi with custom `cf-connecting-ip` key extractor, gated by nginx origin lockdown.** Cloudflare proxies all traffic to api.leafbind.io; `request.client.host` would be the nginx IP. Custom `key_func` reads `CF-Connecting-IP` directly. **Critical pairing**: `CF-Connecting-IP` is trustworthy ONLY if non-Cloudflare origins cannot reach the FastAPI process — Unit 8 adds an nginx IP-range allowlist (Cloudflare's published IPv4/IPv6 ranges) to enforce this, and the slowapi key extractor falls back to `get_remote_address` only when the request reached nginx via an allowlisted proxy. Without origin lockdown, an attacker who discovers the Hetzner VM IP can forge `CF-Connecting-IP` per request and bypass all per-IP rate limiting. *(see origin: R13's trusted-client-IP requirement; expanded during plan review per security-lens P1-1)*
- **Job-ID is the implicit authorization capability for re-convert and Send-to-Kindle (Wave 1).** UUIDv4 job_ids carry ~122 bits of entropy, so knowing a job_id is treated as authorization to act on it. This matches existing `/status/{job_id}` and `/download/{job_id}` semantics. Constraints that MUST hold for this to remain safe: (a) job_ids never appear in referrer headers, analytics events, or third-party logs (R12 telemetry stores SHA-256 hash of recipient but the *job_id itself* is logged — verify it is never sent off-VM in raw form), (b) every sensitive action on a job requires the job's `source_present` or `output_present` to still be true (i.e., post-TTL the capability evaporates with the artifact). Origin lockdown does NOT solve leaked/shared job URLs — a user who shares their result page URL grants re-convert and Send-to-Kindle capability to whoever clicks it. A per-job HMAC capability token model is the natural follow-up if telemetry shows URL-sharing as a real abuse vector. *(deferred per plan-review P1-2; document as a sibling ticket if abuse materializes)*
- **Mail-provider delivery is the authoritative Wave 1 signal; Amazon-side E999 stays out of scope.** Wave 1 ships a Resend webhook handler (Unit 10) so the system observes `email.delivered` / `email.bounced` / `email.failed` / `email.delivery_delayed` — these represent delivery to **Amazon's MX**, not to the user's Kindle library. That's a meaningfully more honest signal than "Resend accepted our API call" and prevents Wave 2's ≥15% kill-criterion gate from being polluted by Resend-2xx-but-nothing-arrived noise. Amazon's post-acceptance E999 (and the April-2025 unapproved-sender async reply path) remain invisible to us — they require inbound-mail parsing which is its own follow-up. R3.5's qualified success copy honestly acknowledges the Amazon-side blind spot. *(updated per plan-review P1-13; webhook handler promoted from deferred to required Wave 1)*
- **Send-to-Kindle is per-job_id, no separate output_id.** Each job (parent or child) produces exactly one output; `(job_id, output_path)` is 1:1 in the current schema. No `outputs[]` shape introduced in Wave 1. If Wave 2 multi-format-on-upload produces multiple outputs per job, that's where the schema change lands. *(see origin: R3.3 per-job-id binding)*
- **`jobs.resend_message_id` is latest-send-attempt-only in Wave 1.** Wave 1 stores a single `resend_message_id` per job — the most recent successful Send-to-Kindle attempt overwrites any prior one. Combined with the "no Resend `Idempotency-Key`" decision (a user who retries after 60s produces a fresh outbound email), this means a webhook for the *first* send arriving after the *second* send overwrites the column will fail to correlate: `find_by_resend_message_id(old_message_id)` returns `None` and Unit 10's handler logs a warning and returns 200 OK without a state transition. Accepted trade-off for v1 because: (a) the expected retry rate is low (most users see the first email arrive within minutes), (b) the lost telemetry on a retried-after-bounce edge case affects dashboards only, not user-visible delivery state, (c) the alternative — a `kindle_send_attempts` table keyed on `(job_id, attempt_n)` with its own delivery_status — adds schema complexity that v1's telemetry signal doesn't justify yet. If post-launch telemetry shows webhook-correlation failures clustering, the migration to a send-attempts table is a localized Unit 4/10 change. Documented here so a future implementer doesn't silently add the table and call it a bug fix.

## Open Questions

### Resolved During Planning

- **Source-copy vs source-pinning** → source-copy (Key Technical Decisions)
- **Resend SDK vs smtplib** → SDK (Key Technical Decisions)
- **Idempotency cache implementation** → SQLite WAL table with 60s window for UX guard; Resend handles send-side dedup via native header (Key Technical Decisions)
- **Cloudflare rule budget on Free** → 1 rule total, single combined rule with `or` over three paths (Key Technical Decisions)
- **Re-convert route shape** → `POST /reconvert/{parent_job_id}` with Form(output_format, token?) — mirrors `convert.py`
- **Status response extension** → add `children[]`, `expires_at`, `source_present`, `output_present` to `GET /status/{job_id}`; same on each child
- **Refund-ledger schema** → mirror `token_store.py:56-86` table-creation pattern; columns: `refund_id (PK)`, `token_hash` (BLOB), `failed_job_id` (TEXT), `refund_reason` (TEXT), `refunded_at` (epoch INTEGER)
- **Telemetry sink** → extend `recovery_events_store._VALID_EVENT_TYPES`; reuse existing `log_event()` fire-and-forget plumbing
- **25 MiB raw cap** → calibrated against Resend's 40 MB post-base64 ceiling (Key Technical Decisions; refined per PR #144 review F10)

### Deferred to Implementation

- **Exact slowapi rate-limit values** (burst size, per-IP vs per-job_id window) — implementer tunes during local load testing and adjusts based on observed traffic patterns
- **Exact recipient-validation library** — Python `email-validator` (PyPI) or stdlib `email.utils.parseaddr` + manual regex. `email-validator` is preferred (RFC-5322-aware, handles unicode normalization) but adds a dependency; implementer picks
- **Exact From-address final string** — likely `kindle@send.leafbind.io` per the existing Resend bounce-MX subdomain, but implementer verifies the Resend domain config before locking
- **Whether to emit `email.complained` Resend webhook events to telemetry** — Wave 1 handles `email.delivered`, `email.bounced`, `email.failed`, `email.delivery_delayed` (per Unit 10 / R3.6). `email.complained` is the spam-complaint event and is the only Resend webhook type Wave 1 ignores; if telemetry shows non-trivial spam complaints post-launch, wire it in a small follow-up
- **Exact UI string for the TTL countdown** ("Session expires in about an hour" vs "less than 10 minutes left") — coarse buckets per brainstorm Key Decisions; final copy is implementer's call within those buckets
- **Whether to add a `pin_count` column for future-proofing toward source-pinning** — deferred; not adding now keeps the migration smaller. If post-launch telemetry shows high fanout, that migration is localized

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

**Extended `GET /status/{job_id}` response shape (Wave 1):**

```
{
  "status": "done" | "queued" | "running" | "failed" | "expired",
  "output_format": "epub",
  "output_size": 1234567,
  "download_url": "/download/{job_id}",
  "expires_at": 1716156000,             // NEW (epoch seconds)
  "source_present": true,               // NEW (gates re-convert)
  "output_present": true,               // NEW (gates Send-to-Kindle)
  "ai_used": { ... },                   // existing AI telemetry block
  "children": [                         // NEW (R2.1)
    {
      "job_id": "j_abc...",
      "format": "mobi",
      "status": "done",
      "expires_at": 1716156000,
      "source_present": true,           // child's own input.<ext> on disk; gates re-converting from this child (rare)
      "output_present": true,           // child's output_path on disk; gates Send-to-Kindle for this child's output
      "kindle_delivery_status": null,   // populated only after the user invokes Send-to-Kindle for this output
      "resend_message_id": null,
      "download_url": "/download/j_abc..."
    }
  ]
}
```

**Send-to-Kindle request flow** (textual sequence — exact module shape is the implementer's call):

1. Frontend posts `recipient` to `POST /send-to-kindle/{job_id}`
2. Backend: parse recipient → normalize → reject non-kindle.com domains (R3.1)
3. Backend: read `job_store` for the job's `output_path` and format → resolve path and assert `is_relative_to(settings.temp_dir)` (P1-4 boundary check) → validate format ∈ `{"epub"}` allowlist → validate raw size ≤ 25 MiB (R3.3)
4. Backend: **atomic claim before Resend.** Under `BEGIN IMMEDIATE`: `INSERT INTO kindle_send_idempotency (job_id, recipient_hash, sent_at, claim_state) VALUES (?, ?, now, 'claimed')`. The table has `PRIMARY KEY (job_id, recipient_hash)`; concurrent insert from another worker raises `IntegrityError` → catch and return `{"status": "already_sent"}` without invoking Resend. Within the 60s window any later attempt also hits the PK conflict (until the opportunistic sweep prunes the row). This eliminates the check-then-act race where two workers could both pass an idempotency check and both call Resend.
5. Backend: Resend SDK call (no `idempotency_key` — see Key Technical Decisions), attachment from `output_path`, From=`settings.send_to_kindle_from`. Wrap in try/except:
   - **Success (Resend 2xx)**: `UPDATE kindle_send_idempotency SET claim_state='sent' WHERE job_id=? AND recipient_hash=?`; capture `message_id` from response; persist on the job row (`resend_message_id`, `kindle_delivery_status = "accepted_by_resend"`); respond `{"status": "sent", "delivery_status": "accepted_by_resend"}`.
   - **Failure (Resend 4xx/5xx, network error, SDK exception)**: `DELETE FROM kindle_send_idempotency WHERE job_id=? AND recipient_hash=? AND claim_state='claimed'` so the user can legitimately retry; raise the sanitized `KindleSendError` (per P1-3 log-hardening); route returns 502 / 422 depending on classification.
6. (Async) Resend webhook fires (Unit 10 handles): `email.delivered` → `kindle_delivery_status = "delivered_to_mail_server"`; `email.bounced` → `bounced`; `email.failed` → `failed`; `email.delivery_delayed` → `delivery_delayed`. Telemetry emits the graded `send_to_kindle_*` events.

**Re-convert request flow** (textual sequence):

1. Frontend posts `output_format` (+ optional `token` for premium) to `POST /reconvert/{parent_job_id}`
2. Backend: read parent job from `job_store`; verify `status === "done"` and `source_present === True`
3. Backend (premium only): `token_store.validate_and_consume(token)` via `billing_executor`; compute `token_hash`; on failure, 422
4. Backend: mint child `job_id`; create child `temp_dir`; copy parent's `input.<ext>` → child's `temp_dir` (source-copy)
5. Backend: `job_store.create_job(job_id=child_id, parent_job_id=parent_id, token_hash=token_hash_or_None, ...)`
6. Backend: `asyncio.create_task(job_queue.dispatch_job(child_id))`; respond `202 {"job_id": child_id, "parent_job_id": parent_id}`
7. Frontend polls `/status/{parent_id}`; the child appears in `children[]` and the action cluster shows its progress
8. On child failure (if `token_hash IS NOT NULL`): `job_queue` invokes `token_store.refund_token(token_hash)` — atomic reverse-consume if token still alive; otherwise writes `refund_ledger` row

## Implementation Units

### Recommended landing order

Units are numbered for stable cross-reference, but they MUST land in this dependency order so the backend contract exists before the UI is built against it:

1. **Unit 1** ✅ MERGED (PR #140) — Schema migrations + datastore helpers (foundation; nothing depends on yet-to-exist columns)
2. **Unit 9a** ✅ MERGED (PR #140) — Telemetry whitelist (mechanically additive: append the new event-type strings to `_VALID_EVENT_TYPES`). Landed in Unit 1's PR — both are foundation changes Units 2–10 depend on. Without 9a landing first, every server-side `log_event()` call in Units 3, 4, 10 would be silently dropped.
3. **Unit 2** ✅ MERGED (PR #140) — `_cleanup_after_download` no-op (small, paired with Unit 1 in the same PR)
4. **Unit 3** ✅ MERGED (PR #141) — Re-convert backend (depended on Unit 1's schema/helpers and Unit 9a's whitelist for `reconvert_*` events)
5. **Unit 4** ⚠️ MERGED MINIMAL + VALIDATION SUITE (PRs #142 + #144) — Send-to-Kindle backend + the validation suite both live on master. **The live route is still gated behind `WEB_SEND_TO_KINDLE_ENABLED=false`** (the default). Disabled deploys boot cleanly without the Resend env vars. Code-side checklist (5 of 9 done): ✅ 25 MiB raw cap, ✅ `@kindle.com` / `@free.kindle.com` allowlist, ✅ display-name + plus-aliasing + angle-wrapper + whitespace rejection, ✅ EPUB-only format allowlist, ✅ output-path boundary check (P1-4) + telemetry. Remaining before flag-flip (4 items, all non-code): signed-event e2e test, manual smoke script, Resend domain/sender/API key provisioning, Cloudflare WAF rule extension. Do not assume `/send-to-kindle` is production-ready just because the route is registered.
6. **Unit 5** — Status response extension + frontend polling (depends on Unit 1 helpers; surfaces the fields the UI will gate on) **— next up**
7. **Unit 10** — Resend webhook handler (depends on Unit 1's `resend_message_id` + `kindle_delivery_status` columns and Unit 9a's whitelist for the four delivery-side events; **MUST land before Unit 6** so `kindle_delivery_status` actually transitions past `accepted_by_resend` — without this the UI promises graded delivery state against a field that never updates)
8. **Unit 6** — Frontend action cluster UI (depends on Units 4, 5, 10 — every promise the result page makes is backed by an existing backend contract before this unit starts)
9. **Unit 9b** — split into two PRs: **server-side emits** ✅ MERGED (PR #147 — `log_event(...)` calls in `routes/reconvert.py`, `routes/send_to_kindle.py`, and `job_queue.dispatch_job`) and **client-side Plausible emits** (still pending — lands with Unit 6 since the emission sites live in the new components). The server-side half was decoupled from Unit 6 to keep the frontend PR focused; the events are independently testable in pytest and the recovery_events table is durable, so the "flicker before dashboards exist" concern below was outweighed by the smaller-PR benefit.
10. **Unit 8** — Rate-limiting + nginx Cloudflare-IP allowlist + Cloudflare WAF deploy task (can land in parallel with Unit 6/9b near the end; doesn't change product behavior, only defensive posture; the slowapi key extractor must be wired before Unit 6 is exposed to real traffic, but the test coverage is independent of the UI)

**Unit 7 was removed** (R11 deferred to a standalone follow-up ticket per plan-review P1-15).

**Original Unit 9 is split into 9a (whitelist + server-side emit-call shape) and 9b (client-side Plausible emissions)** so the whitelist is in place before Units 3/4/10 fire their events. The unit body below describes the combined 9a + 9b scope; implementer lands 9a in the Unit 1 PR and 9b in the Unit 6 PR.

---

- [x] **Unit 1: Schema migrations + datastore helpers (foundation)** — MERGED in PR #140 (commit `fe28ceb`)

**Goal:** Land all SQLite schema changes and helper functions that downstream units depend on, in a single PR with migration-race coverage.

**Requirements:** R2.3, R2.7 (partial — refund mechanics in this unit)

**Dependencies:** None — foundation unit.

**Files:**
- Modify: `web_service/job_store.py` (add `parent_job_id TEXT` and `resend_message_id TEXT` and `kindle_delivery_status TEXT` to `_LATER_COLUMNS`; add index `idx_jobs_parent_job_id`; **NOTE: `jobs.token_hash TEXT` already exists in the base schema (line 35) but is unused — Wave 1 reuses it for refund lookup, storing `compute_token_hash(token).hex()` as a 64-char hex string** rather than adding a new BLOB column; add `list_children(parent_job_id) -> list[dict]`; add `update_kindle_delivery_status(job_id, status)` helper for the webhook to call; extend `create_job(..., parent_job_id=None, token_hash_hex=None)`)
- Modify: `web_service/token_store.py` (add new `_REFUND_LEDGER_SCHEMA_SQL` constant; add `refund_token(token_hash: bytes, failed_job_id: str, reason: str) -> RefundResult` with `BEGIN IMMEDIATE` + atomic reverse-consume + ledger fallback)
- Modify: `web_service/recovery_events_store.py:55-60` (**Unit 9a piggybacks on this PR**: extend `_VALID_EVENT_TYPES` with the 14 new event-type strings enumerated in Unit 9's Approach — `reconvert_*` (4), `send_to_kindle_*` send-side (4), `send_to_kindle_*` delivery-side (4), `expired_action_attempted`, `kindle_send_invariant_violation`. Without this in the foundation PR, Units 3/4/10 would emit silently-dropped events.)
- Test: `tests/test_web_job_store_migration_race.py` (extend to cover new columns)
- Test: `tests/test_web_token_store.py` (add atomic-refund coverage)
- Test: `tests/test_web_recovery_events.py` (assert each of the 14 new event types is accepted by `_VALID_EVENT_TYPES`)

**Approach:**
- New columns added via existing `_LATER_COLUMNS` idiom; no separate migrations directory.
- `parent_job_id`, `resend_message_id`, `kindle_delivery_status` default `NULL`; existing rows untouched.
- **`jobs.token_hash` is NOT a new column** — the existing `jobs.token_hash TEXT` (line 35 of `job_store.py`) is reused. Wave 1 starts writing it for premium child jobs as `compute_token_hash(token).hex()` (64-char hex string). The `refund_token()` operation decodes hex → bytes for the BLOB equality join against `tokens.token_hash`.
- `refund_token()` mirrors `validate_and_consume()` structure: `BEGIN IMMEDIATE`, single `UPDATE tokens SET used=0, used_at=NULL WHERE token_hash=? AND used=1 AND disputed=0 AND expires_at > ?` (parameter is the decoded BLOB form). On `rowcount == 0`, fall back to inserting a `refund_ledger` row.
- `refund_ledger` table schema (column types follow `token_store` conventions): `refund_id TEXT PRIMARY KEY`, `token_hash BLOB NOT NULL` (stored as BLOB — matches `tokens.token_hash` for support-query joins), `failed_job_id TEXT NOT NULL`, `refund_reason TEXT NOT NULL`, `refunded_at INTEGER NOT NULL`. Index on `token_hash` for support queries.
- `list_children(parent_job_id)` returns child rows ordered by `created_at` ASC.

**Execution note:** Migration tests first — the existing `tests/test_web_job_store_migration_race.py` pattern uses two concurrent threads racing `_apply_migrations` on a fresh DB. Extend this before touching the production module code, so the column-add idiom is verified safe under contention.

**Patterns to follow:**
- `web_service/job_store.py:48-83` (`_LATER_COLUMNS`, `_apply_migrations()`)
- `web_service/token_store.py:374-385` (atomic `BEGIN IMMEDIATE` + `UPDATE WHERE ...` race-safe write)
- `web_service/token_store.py:56-86` (table-creation constant + index pattern)
- `tests/test_web_job_store_migration_race.py` (migration-race test pattern)

**Test scenarios:**
- Happy path — Fresh DB starts up, `_apply_migrations()` adds `parent_job_id`, `resend_message_id`, `kindle_delivery_status` columns; `PRAGMA table_info(jobs)` confirms all three present and confirms `token_hash` is the pre-existing TEXT column (not duplicated)
- Happy path — `create_job(parent_job_id="p_123", token_hash_hex="abc123…")` persists both fields; `list_children("p_123")` returns the row with `token_hash` populated as the hex string
- Critical regression — `_apply_migrations()` does NOT try to ADD COLUMN `token_hash` (the existing TEXT column would collide); add an explicit test asserting the migration is idempotent with the pre-existing column present
- Edge case — Calling `_apply_migrations()` twice on the already-migrated DB is a no-op (idempotent)
- Edge case — `list_children("nonexistent_parent")` returns empty list
- Edge case — `create_job(parent_job_id=None)` writes `NULL`; child queries don't match
- Integration — Two threads concurrently run `_apply_migrations()` on a fresh DB; both succeed; final schema matches expected
- Happy path (refund) — `refund_token(hash, "j_failed", "child_job_failed")` on a still-alive consumed token: `tokens.used` flips to 0, `tokens.used_at` becomes NULL, returns `RefundResult(refunded=True)`
- Edge case (refund) — `refund_token(hash, ...)` on an expired token: no token row touched, `refund_ledger` row inserted, returns `RefundResult(refunded=False, ledgered=True)`
- Edge case (refund) — `refund_token(hash, ...)` on a disputed token: no refund applied (matches existing dispute-pin behavior); ledger row reflects the rejection
- Integration — Two threads concurrently call `refund_token()` for the same `token_hash`; exactly one succeeds (`BEGIN IMMEDIATE` serializes)
- Error path — `refund_token(hash, ...)` with a `token_hash` that doesn't exist in `tokens`: ledger row inserted with reason; no crash

**Verification:**
- All migration-race tests pass under `pytest tests/test_web_job_store_migration_race.py`
- `pytest tests/test_web_token_store.py -k refund` shows green

---

- [x] **Unit 2: Cleanup semantics — `_cleanup_after_download` no-op** — MERGED in PR #140 (commit `fe28ceb`)

**Goal:** Stop deleting the output file and marking jobs expired on download. TTL sweep in `_cleanup_job` becomes the sole cleanup mechanism.

**Requirements:** Enables R1 (action cluster after download), R2 (re-convert after download), R4.1 (`output_present` and `source_present` accuracy after download)

**Dependencies:** Unit 1 (uses the same `jobs` schema; no migration changes here)

**Files:**
- Modify: `web_service/routes/download.py:106-112` (remove `os.unlink(output_path)` and `job_store.set_expired(job_id)` from the post-stream cleanup; the function name is preserved but body is no-op or removed entirely)
- Test: `tests/test_web_endpoints.py` (extend with download-then-reuse regression)
- Test: `tests/test_web_sweeps.py` (add the R2.5 race test — see below)

**Approach:**
- The download streaming logic itself stays unchanged — only the post-stream cleanup hook is gutted.
- If the function becomes truly empty, prefer to delete the call site rather than leave a dead helper.
- The TTL sweep at `web_service/job_queue.py:156-163` is already the canonical cleanup path; no change required there in this unit (source-copy decision means parents don't need pin-aware cleanup).

**Execution note:** Add the regression test first — "download EPUB, immediately request `GET /status/{job_id}`, expect `status === "done"` with `output_present === True`". The test should fail today (because `set_expired` was called) and pass after the cleanup removal.

**Patterns to follow:**
- `web_service/routes/download.py:106-112` (the lines being neutralized)
- `web_service/job_queue.py:_cleanup_job:156-163` (the cleanup path that remains)

**Test scenarios:**
- Happy path — User downloads EPUB; immediately requests `GET /status/{job_id}`; response shows `status === "done"`, `output_present === True`, `expires_at` still in the future
- Happy path — User downloads EPUB; then POSTs to `/send-to-kindle/{job_id}` within the retention window; send succeeds (output file still on disk)
- Happy path — User downloads EPUB; then POSTs to `/reconvert/{job_id}` with `output_format=mobi`; child job dispatches (source file still on disk)
- Integration — Sleep until TTL elapses; TTL sweep runs; `temp_dir` and output file deleted; `GET /status/{job_id}` returns 200 with `status: "expired"`, `source_present: false`, `output_present: false` (the sweep calls `set_expired`, **not** `purge_job` — the row stays; the 404 path in `ConversionStatus.tsx:51-67` only fires for unknown/never-existed job_ids, which is what R5 preserves)
- Edge case — Multiple downloads of the same job within the window all succeed (no "already cleaned up" 404)

**Verification:**
- Download → re-convert sequence succeeds in a single integration test run
- TTL sweep test confirms eventual cleanup still works
- No existing test regresses (test_web_endpoints + test_web_sweeps full suites pass)

---

- [x] **Unit 3: Re-convert backend — `POST /reconvert/{parent_job_id}`** — MERGED in PR #141 (commit `93d1207`)

**Goal:** New endpoint that creates child jobs from a parent's already-uploaded source. Handles free re-convert, premium re-convert with token consumption, and atomic refund on child failure.

**Requirements:** R2, R2.1, R2.4 (source-copy implementation), R2.5 (race test), R2.6 (token via TokenField on result page — consumed here), R2.7 (token_hash on child + refund triggered here)

**Dependencies:** Unit 1 (schema + helpers + refund operation), Unit 2 (download cleanup is no-op so source survives)

**Files:**
- Create: `web_service/routes/reconvert.py` (new file mirroring `routes/convert.py` shape)
- Modify: `web_service/main.py:233-240` (register the new router)
- Modify: `web_service/job_queue.py` (extend `dispatch_job` failure path to invoke `token_store.refund_token()` when `child.token_hash IS NOT NULL`)
- Modify: `web_service/job_store.py` (extend `create_job` signature; verify `source_present` helper exists or add it — `Path(temp_dir / f"input.{input_fmt}").exists()`)
- Test: `tests/test_web_reconvert.py` (new test module)
- Test: `tests/test_web_sweeps.py` (R2.5 parent-TTL-during-child-run race)

**Approach:**
- Endpoint validates parent: exists, `status === "done"`, `source_present === True`. Reject early with 410 Gone if source is no longer on disk.
- For premium: `token_store.validate_and_consume(token)` via `billing_executor` (mirror `convert.py:79-93`). On success, capture the `token_hash` for the child row.
- Child dispatch:
  - Mint child `job_id` via `job_store.new_job_id()`
  - Create child `temp_dir` (`f"job_{child_id}"`)
  - Copy parent's `input.<ext>` → child's `temp_dir` (`shutil.copy2(parent_input, child_input)`)
  - `job_store.create_job(job_id=child_id, parent_job_id=parent_id, token_hash=token_hash_or_None, input_fmt=..., output_fmt=..., ...)`
  - `asyncio.create_task(job_queue.dispatch_job(child_id))`
- Failure-refund wiring: in `job_queue.dispatch_job`, when a child reaches `failed` AND `token_hash IS NOT NULL`, call `token_store.refund_token(token_hash, failed_job_id=child_id, reason="child_job_failed")` via `billing_executor`. Telemetry event emitted (`reconvert_refund_applied`).
- CORS: new endpoint inherits the existing `WEB_SERVICE_ALLOWED_ORIGINS` middleware in `main.py:226-232`.

**Execution note:** R2.5 (parent-TTL-elapses-while-child-running) is the load-bearing regression test for the source-copy decision. Write it before the dispatch logic so the test exercises the production behavior end-to-end.

**Patterns to follow:**
- `web_service/routes/convert.py` (Form inputs, validation, billing_executor for token consume, child dispatch pattern)
- `web_service/routes/recover.py` (alternative validation example with read-only token check)
- `web_service/job_queue.py:71-103` (dispatch failure path — extend with refund hook)

**Test scenarios:**
- Happy path (free) — `POST /reconvert/{parent_id}` with `output_format=mobi` and no token, parent done and source present → 202 + child `job_id`; child eventually transitions to `done`; child output file exists
- Happy path (premium) — `POST /reconvert/{parent_id}` with `output_format=kfx` and a valid token → 202 + child `job_id`; token marked `used`; `token_hash` persisted on child row; child eventually transitions to `done`
- Error path — `POST /reconvert/{parent_id}` against a job where `status !== "done"` → 422
- Error path — `POST /reconvert/{parent_id}` against a job where `source_present === False` (parent expired) → 410 Gone
- Error path — Premium re-convert with missing token → 422 `MISSING_TOKEN`
- Error path — Premium re-convert with invalid token format → 422 `INVALID_TOKEN`
- Error path — Premium re-convert with already-consumed token → 422 `TOKEN_CONSUMED`
- Error path — Free re-convert requesting a premium format (KFX) without token → 422
- Integration (refund) — Force child job to fail mid-pipeline (e.g., mock `dispatch_job` to set `failed`); confirm `token_store.refund_token()` is invoked; token's `used` flips back to 0
- Integration (R2.5 — load-bearing) — Dispatch child, force parent TTL to elapse during child run, child completes successfully and produces a downloadable output (because child's `temp_dir` is independent of parent's)
- Integration — Two concurrent reconverts on the same parent: both children dispatch independently (no race on `temp_dir` copy)
- Edge case — Premium re-convert with token whose expiry is mid-conversion: token validates and consumes successfully; child eventually completes; refund path not invoked

**Verification:**
- `pytest tests/test_web_reconvert.py` shows green
- R2.5 integration test passes — child output exists after parent rmtree'd mid-run
- `pytest tests/test_web_sweeps.py` continues to pass (no regression of existing TTL behavior)
- Manual smoke (`pwsh tools/verify_stripe_e2e.ps1`-style script for re-convert flow can land alongside, but it's not blocking — the three-layer test model mirrors `stripe-verification.md`)

---

- [~] **Unit 4: Send-to-Kindle backend — `POST /send-to-kindle/{job_id}`** — MINIMAL ROUTE + VALIDATION SUITE MERGED in PRs #142 + #144 (commits `7567ba2` + #144's squash), **feature-flagged off** behind `WEB_SEND_TO_KINDLE_ENABLED=false`. Only Ops/e2e work remains before the flag can flip.

> **Status as of PR #144:** the route module, `email_client` wrapper, `kindle_send_idempotency` table, the two reviewer-endorsed invariants (atomic claim race-gate + caplog log-leak hardening), AND the full validation suite are on master. Production deploys boot cleanly without `WEB_SEND_TO_KINDLE_FROM` / `WEB_RESEND_API_KEY` because `_require_env` only fires when the flag is enabled.
>
> **Code-side pre-enable checklist — all done:**
> 1. ✅ 25 MiB raw size cap on the EPUB (R3.3 — calibrated against Resend's 40 MB post-base64 ceiling)
> 2. ✅ Strict `@kindle.com` / `@free.kindle.com` domain allowlist (R3.1)
> 3. ✅ Recipient form rejection (display-name + plus-aliasing + angle-wrapper + internal whitespace) (R3.4)
> 4. ✅ EPUB-only format allowlist (R3.3)
> 5. ✅ Output-path filesystem-boundary check + `kindle_send_invariant_violation` telemetry (P1-4 hardening)
>
> **Remaining before the flag can flip (4 items, all non-code):**
> 6. Signed-event e2e test (`tests/test_web_send_to_kindle_signed.py`) — requires a real Resend test API key
> 7. Manual smoke script (`tools/verify_send_to_kindle.ps1`) — pre-deploy + customer-report triage shape per `stripe-verification.md`
> 8. Production Resend domain + sender + API key provisioning (Ops)
> 9. Cloudflare WAF rule extension to include `/send-to-kindle/*` (Ops)
>
> Do NOT flip `WEB_SEND_TO_KINDLE_ENABLED=true` in any environment until items 6–9 above land.

**Goal:** New endpoint that sends a converted EPUB output as an email attachment via Resend. Includes recipient + format + size validation, server-side idempotency, and the approved-sender From-address contract.

**Requirements:** R3, R3.1, R3.3, R3.4

**Dependencies:** Unit 1 (foundation — schema-add discipline + datastore helpers) — Unit 4 adds a NEW separate table (`kindle_send_idempotency`) via the `_SCHEMA_SQL` table-create pattern (see Approach), NOT via `_LATER_COLUMNS`. Coordinate the migration ordering so all schema work lands together. Unit 5 owns `source_present()`/`output_present()` helpers (Unit 4 reads `output_path` directly from `job_store.get_job()` and does its own `Path.exists()`).

**Files:**
- Create: `web_service/routes/send_to_kindle.py` (new route module)
- Create: `web_service/email_client.py` (Resend SDK wrapper — single `send_with_attachment(...)` function)
- Modify: `web_service/main.py:233-240` (register the new router); also add `send_to_kindle_from: str` to `Settings` in `web_service/config.py:85-198` and read from env (`WEB_SEND_TO_KINDLE_FROM`)
- Modify: `web_service/validation.py` (add `validate_kindle_recipient`, `validate_kindle_format`, `validate_kindle_attachment_size`)
- Modify: `web_service/job_store.py` (add 60s idempotency table — `kindle_send_idempotency(job_id TEXT NOT NULL, recipient_hash BLOB NOT NULL, sent_at INTEGER NOT NULL, claim_state TEXT NOT NULL CHECK (claim_state IN ('claimed', 'sent')), PRIMARY KEY (job_id, recipient_hash))` via a new `_KINDLE_IDEMPOTENCY_SCHEMA_SQL` constant executed by `init_db()` — **NOT** via `_LATER_COLUMNS` (which can only ALTER `jobs` to add columns, not CREATE new tables). Pattern mirror: `web_service/recovery_events_store.py:41-50`. Opportunistic `DELETE WHERE sent_at < ?` on insert. **Recipient stored as SHA-256 hash, not plaintext** — equality lookup works identically with the hashed key and aligns with the privacy claim that the Kindle address is never stored in our database. The PRIMARY KEY constraint is the atomic claim mechanism — concurrent workers' INSERTs raise `IntegrityError` on the second attempt, eliminating the check-then-act race.
- Modify: `requirements.txt` (add `resend>=0.x.x`, optional `email-validator>=2.x.x`)
- Test: `tests/test_web_send_to_kindle.py` (new test module, mocked Resend)
- Test: `tests/test_web_send_to_kindle_signed.py` (signed-event e2e flow, gated on a real Resend test API key — mirrors `tests/test_web_payment_e2e.py`)

**Approach:**
- Endpoint reads `recipient` from `Form(...)`; pipeline: parse → normalize (R3.4) → R3.1 domain check → R3.3 format check (read job's `output_fmt`) → R3.3 raw size check (`Path(output_path).stat().st_size`) → P1-4 path boundary check → **atomic SQLite claim** → Resend send → on success update claim_state, on failure delete claim → respond.
- Recipient validation: prefer `email-validator` library for RFC-5322-aware parsing; fall back to stdlib `email.utils.parseaddr` if dependency cost is a concern.
- Domain check: parse the address, lowercase the domain, **strict equality** against `{"kindle.com", "free.kindle.com"}`. No wildcard/suffix matching.
- Normalization (R3.4): `addr.strip().lower()`. Reject if `parseaddr` returns a non-empty display name. Reject if the local-part contains `+`.
- Format allowlist: **Wave 1 narrows the server-side allowlist to exactly `{"epub"}`** — the only format leafbind produces that is Kindle-eligible. Defense-in-depth: even if the frontend incorrectly invokes Send-to-Kindle on a MOBI or KFX row, the server rejects with 422 `FORMAT_NOT_KINDLE_ELIGIBLE`. Adding future eligible formats (e.g., PDF passthrough) requires an explicit allowlist change with the corresponding row-level UI treatment in Unit 6. (Earlier draft listed the full Amazon-accepted set; narrowed during review to avoid false assurance from a 13-format allowlist where 12 entries are currently unreachable.)
- Size check: `raw_bytes ≤ 25 * 1024 * 1024` (25 MiB). Calibrated against Resend's 40 MB post-base64 ceiling — see Key Technical Decisions and PR #144 review F10.
- **Atomic idempotency claim (replaces the earlier check-then-insert pattern that allowed a check-then-act race):** compute `recipient_hash = sha256(normalized_recipient).digest()`. Under a `BEGIN IMMEDIATE` transaction: opportunistic sweep `DELETE FROM kindle_send_idempotency WHERE sent_at < strftime('%s','now') - 60`; then `INSERT INTO kindle_send_idempotency (job_id, recipient_hash, sent_at, claim_state) VALUES (?, ?, strftime('%s','now'), 'claimed')`; `COMMIT`. The PRIMARY KEY constraint (`job_id`, `recipient_hash`) raises `sqlite3.IntegrityError` if a row already exists (either a still-live claim from a concurrent worker, or a recently-`sent` row from this user clicking Send twice). Catch the error and return 200 `{"status": "already_sent"}`. **Only after the claim commits successfully do we invoke Resend.** On Resend failure (4xx/5xx/exception), `DELETE FROM kindle_send_idempotency WHERE job_id=? AND recipient_hash=? AND claim_state='claimed'` so the user can immediately retry. On Resend success, `UPDATE ... SET claim_state='sent'` so a retry within 60s is short-circuited to `already_sent`.
- **Output-path filesystem-boundary validation (P1-4 hardening).** BEFORE opening `output_path` for attachment, the endpoint MUST resolve the path and assert it is inside the expected job temp-dir hierarchy: `Path(output_path).resolve().is_relative_to(settings.temp_dir.resolve())`. Reject with 500 + log a `kindle_send_invariant_violation` event if the check fails. Without this guard, a corrupted or maliciously-modified `output_path` row in SQLite (e.g., via a future SQL injection in another route) could redirect Resend to read `/etc/web_service.env` and exfiltrate API keys via the attachment.
- Resend send: `resend.Emails.send({from: settings.send_to_kindle_from, to: [normalized_recipient], subject: f"Your {output_fmt.upper()} from leafbind", html: <html_body>, attachments: [...]})`. **No `idempotency_key` parameter** — per Key Technical Decisions, the local 60s SQLite table is the sole dedup layer; Resend's 24h native key would collide with legitimate user retries past the 60s window.
- **Log-leak hardening (P1-3).** The `email_client.send_with_attachment(...)` wrapper MUST catch `resend.exceptions.ResendError` (and generic `Exception`) and re-raise a sanitized `KindleSendError` whose `args` and `__str__` contain **no recipient address**. The route handler logs only `{event: "kindle_send_failed", job_id, error_code, error_class}` — never the address, never the raw Resend response body. Add a test (`tests/test_web_send_to_kindle.py::test_no_recipient_in_logs`) that captures `caplog` during a forced failure and asserts no `@kindle.com` substring appears anywhere in captured records. This is the load-bearing guard for the privacy commitment "the address is never stored in our application logs."
- API key: load from env `WEB_RESEND_API_KEY` (sending-access scoped to `leafbind.io`). Document in `.env.example`.
- On Resend 2xx: capture the returned `message_id`; store it on the job row in a new `resend_message_id TEXT` column (added to `_LATER_COLUMNS` in Unit 1). Insert idempotency row. Respond `{"status": "sent", "delivery_status": "accepted_by_resend"}` — the frontend renders this as the immediate confirmation (per R3.5); webhook updates later transition the delivery_status to `delivered_to_mail_server` / `bounced` / `failed` / `delivery_delayed`.
- On Resend 4xx/5xx: log error code, respond `{"status": "send_failed", "code": ...}` — frontend maps to failure-generic state (R3.2).

**Execution note:** The three-layer billing-test model from `web_service/docs/stripe-verification.md` applies — write the mocked unit tests first (covering all validation paths), then the signed-event e2e test (using a Resend test API key), then a manual smoke script in `tools/verify_send_to_kindle.ps1`. The manual script verifies a real send to a real `@kindle.com` test address.

**Patterns to follow:**
- `web_service/routes/convert.py` (route shape, billing_executor for Resend call)
- `web_service/validation.py:46-47` (format-allowlist constants and helpers)
- `tests/test_web_payment.py` (mocked-unit pattern for external API)
- `tests/test_web_payment_e2e.py` + `.github/workflows/web-tests.yml` (signed-event e2e and CI integration)

**Test scenarios:**
- Happy path — Valid EPUB job, valid `@kindle.com` recipient, file ≤ 25 MiB → 200 `{"status": "sent"}`; Resend called once; idempotency row inserted
- Happy path — Same `(job_id, recipient)` POSTed twice within 60s → first returns "sent"; second returns "already_sent" without invoking Resend
- Edge case — Same `(job_id, recipient)` POSTed twice with > 60s between → both calls hit Resend (local idempotency window elapsed). Wave 1 does NOT pass `idempotency_key` to Resend, so the second call WILL produce a fresh outbound email. This is the intended behavior — a user who didn't see the first email arrive can legitimately retry. The trade-off is documented in the resend_message_id semantics decision (latest-send-attempt-only).
- Edge case — Different recipients for same job within 60s → both hit Resend (different idempotency tuples)
- Error path — Non-kindle domain (`evil@example.com`) → 422 `INVALID_RECIPIENT_DOMAIN`
- Error path — Wildcard-suffix attempt (`evil@evil-kindle.com`) → 422 (exact-equality check rejects)
- Error path — Display-name form (`"User" <u@kindle.com>`) → 422 `INVALID_RECIPIENT_FORM`
- Error path — Plus-aliased (`user+tag@kindle.com`) → 422 `INVALID_RECIPIENT_FORM`
- Error path — Job's `output_fmt === "mobi"` → 422 `FORMAT_NOT_KINDLE_ELIGIBLE` (defense-in-depth; frontend gates this row already)
- Error path — Job's `output_fmt === "kfx"` → 422 `FORMAT_NOT_KINDLE_ELIGIBLE`
- Error path — Output file size 35 MB → 422 `OUTPUT_TOO_LARGE_FOR_KINDLE`
- Error path — Job doesn't exist → 404
- Error path — Job's `output_present === False` (output rm'd by TTL sweep) → 410 Gone
- Integration — Resend returns 5xx → 502 from our endpoint; idempotency row not inserted (so user can retry)
- Integration — Resend returns 4xx (invalid recipient on their side) → mapped to 422 from our endpoint with reason

**Verification:**
- `pytest tests/test_web_send_to_kindle.py` shows green (all validation paths)
- `tests/test_web_send_to_kindle_signed.py` passes in CI under `.github/workflows/web-tests.yml` (extend the workflow with a `WEB_RESEND_TEST_API_KEY` secret)
- Manual `pwsh tools/verify_send_to_kindle.ps1` produces a real Resend dashboard entry against an internal test Kindle address

---

- [ ] **Unit 5: Status response extension + frontend polling fix**

**Goal:** Surface `expires_at`, `source_present`, `output_present`, and `children[]` in the status API, and widen the frontend polling stop condition so it doesn't terminate while children are still in-flight.

**Requirements:** R2.1 (`children[]`), R2.2 (polling widening), R4.1 (the four fields)

**Dependencies:** Unit 1 (`list_children` helper); coordinate with Unit 4 (idempotency table doesn't block Unit 5)

**Files:**
- Modify: `web_service/routes/status.py:12-49` (extend response with new fields; call `job_store.list_children(job_id)` and recursively shape child entries; compute `source_present` and `output_present` from `Path.exists()` checks)
- Modify: `web_service/job_store.py` (helper `source_present(job_row) -> bool`, `output_present(job_row) -> bool` — these encapsulate the `Path(temp_dir / f"input.{input_fmt}").exists()` and `Path(output_path).exists()` checks)
- Modify: `web_service/frontend/lib/api.ts` (extend `StatusResponse` interface with new fields; `children: ChildStatus[]`)
- Modify: `web_service/frontend/components/ConversionStatus.tsx:24-29` (widen stop condition to `(status === "done" || status === "failed") && children.every(c => c.status === "done" || c.status === "failed")`)
- Test: `tests/test_web_status.py` (extend to cover new fields and child-array shape)
- Test: `web_service/frontend/tests/conversion-status-children.spec.ts` (Playwright spec — child in-flight extends polling)

**Approach:**
- Children appear in `children[]` only after re-convert is invoked; the array is always present (empty list when no children).
- Each child entry shape (canonical — implementer adheres to this):
  ```
  {
    "job_id": "<child uuid>",
    "format": "mobi" | "kfx" | ...,
    "status": "queued" | "running" | "done" | "failed" | "expired",
    "expires_at": <epoch>,
    "source_present": <bool>,      // child has its own temp_dir (source-copy); true while child is alive
    "output_present": <bool>,      // child's output_path exists on disk
    "kindle_delivery_status": "accepted_by_resend" | "delivered_to_mail_server" | "bounced" | "failed" | "delivery_delayed" | null,
    "resend_message_id": "<resend uuid or null>",
    "download_url": "/download/<child uuid>" | null
  }
  ```
  Both `source_present` and `output_present` are per-child (not parent-derived). Parent's `source_present`/`output_present` describe the parent's own files independently. The frontend gates re-convert on a child row by `child.source_present` (rare — children rarely re-convert themselves) and gates Send-to-Kindle by `child.output_present`.
- Status-response shape per parent status:
  - `done`, `queued`, `running`, `failed`, `expired` — ALL include the new four fields (`expires_at`, `source_present`, `output_present`, `children[]`). For `expired`, `source_present` and `output_present` are typically `false` (cleanup ran); `children[]` is preserved for the lifetime of the row so UI can render history.
  - `download_url` continues to appear only on `status === "done"` for backward compat.
- Frontend stop condition update is a 2-line change; semantic: keep polling while *any* in-flight job exists (parent or any child).
- Polling cadence stays at 5 seconds (no change).

**Patterns to follow:**
- `web_service/routes/status.py:12-49` (current response shape — preserve AI telemetry block at lines 30-44)
- `web_service/frontend/lib/api.ts` (typed StatusResponse and ApiError patterns)
- `web_service/frontend/components/ConversionStatus.tsx:17-49` (polling loop structure)
- `web_service/frontend/tests/format-selector-upsell.spec.ts` (Playwright spec for upsell flow — model the new spec on it)

**Test scenarios:**
- Happy path — `GET /status/{job_id}` for a done job returns `children: []`, `expires_at: <int>`, `source_present: true`, `output_present: true`
- Happy path — After a re-convert, `GET /status/{parent_id}` returns `children: [{job_id, format, status, expires_at, output_present, download_url}]` with the child in `queued` or `running`
- Happy path — When the child reaches `done`, parent's response shows the child's `output_present: true` and `download_url`
- Edge case — Job's `temp_dir` removed by TTL sweep: `source_present === False`, `output_present === False` in response
- Edge case — User downloads output (no longer deletes after Unit 2): `output_present === True` continues to return until TTL
- Integration (frontend) — Playwright: load `/status/{parent_id}` after parent done with a child running; assert polling continues (mock the polling interval); when child reaches done, action cluster updates and polling stops
- Integration (frontend) — Playwright: load `/status/{parent_id}` after both parent and all children done; polling stops within one interval
- Edge case — Child's `parent_job_id` mismatched (data corruption): `list_children` filters correctly; child doesn't appear

**Verification:**
- `pytest tests/test_web_status.py` shows green
- `npx playwright test conversion-status-children.spec.ts` shows green
- `web_service/frontend/lib/api.ts` types compile cleanly (`npm run build` in `web_service/frontend/`)

---

- [ ] **Unit 6: Result page action cluster UI**

**Goal:** Replace the current "Download + Convert another" terminal screen with the per-row action cluster from the brainstorm visual aid. Wire Send-to-Kindle form (with R3.5 approved-sender UX), re-convert buttons (free/premium with TokenField), TTL countdown copy with coarse labels, and localStorage email persistence with "Forget" affordance.

**Requirements:** R1, R3.2, R3.5, R4 (disabled-state copy), plus the localStorage and TTL countdown Key Decisions. (R11 is deferred per plan-review P1-15 — not in Wave 1 scope.)

**Dependencies:** Unit 5 (status response includes `children[]`, `output_present`, `source_present`); Unit 4 (route exists for the form to POST to); **Unit 10 (webhook is wired so the `kindle_delivery_status` field actually transitions through `accepted_by_resend` → `delivered_to_mail_server` / `bounced` / `failed` / `delivery_delayed` — without this, the UI would render graded-delivery copy against a field that never updates past `accepted_by_resend`)**. Unit 9a's whitelist has already landed in Unit 1's PR by this point. Unit 9b (client-side Plausible emissions) lands in this Unit's PR.

**Files:**
- Modify: `web_service/frontend/app/(app)/status/[id]/page.tsx` (compose the new action cluster — preferred shape: extract into `web_service/frontend/components/ActionCluster.tsx` for testability)
- Create: `web_service/frontend/components/ActionCluster.tsx` (the per-row layout component)
- Create: `web_service/frontend/components/SendToKindleForm.tsx` (the form sub-component with localStorage, R3.5 approved-sender hint, success/failure states)
- Create: `web_service/frontend/components/ReconvertButton.tsx` (free/premium row variants, premium uses existing TokenField)
- Create: `web_service/frontend/components/TtlCountdown.tsx` (coarse-label countdown — "about an hour", "less than 10 minutes")
- Modify: `web_service/frontend/lib/api.ts` (add `sendToKindle(jobId, recipient)`, `reconvertFile(parentId, format, token?)`)
- Modify: `web_service/frontend/components/ConversionStatus.tsx` (delegate the done-state render to `ActionCluster` when `status === "done"`)
- Test: `web_service/frontend/tests/action-cluster.spec.ts` (Playwright spec covering all the states from the visual aid)

**Approach:**
- Per-row layout (per visual aid): each format produced by the parent or child jobs gets a row. EPUB row: `[Download] [Send to Kindle ▼]`. MOBI row: `[Convert]` (free, click → POST /reconvert with `output_format=mobi`) once child is dispatched, replaced with `[Download]`. KFX row: `[Convert — paste token]` (TokenField inline) once child is dispatched, replaced with `[Download]`. KFX and MOBI rows never show Send-to-Kindle (per R3.3).
- Send-to-Kindle form (R3.5): idle state shows the From address (`kindle@send.leafbind.io` read from a config-served value or hardcoded for v1 with a planning-time call) with "First time? Add this to your Amazon Approved Personal Document Email List. [How →]" linking to `https://www.amazon.com/sendtokindle`. Email input pre-fills from `localStorage["leafbind_kindle_email"]`. Below the input: "Forget this address" link clears localStorage. Success state shows the approved-sender-qualified copy. Failure-known state (R3.2 + R3.5) puts the approved-sender check first, then the EB-322 link.
- Disabled state (R4): when `source_present === False`, all re-convert buttons grey out with "Session expired — upload again to convert to another format." Send-to-Kindle gates on `output_present` independently.
- TTL countdown: coarse buckets computed from `expires_at` epoch: > 30 min → "about an hour", 10-30 min → "about half an hour", < 10 min → "less than 10 minutes". Hides on any consumed action.
- localStorage shape: `localStorage["leafbind_kindle_email"]` = single string. "Forget" clears the key and re-renders the form blank.
- React renders email and job_id strings via JSX, which auto-escapes. No interpolation into `href` attributes from user-supplied strings (only the From address, which is server-config-controlled). Per the EB-248 XSS learning, audit any new `dangerouslySetInnerHTML` or `href={...}` constructions — there should be none.

**Patterns to follow:**
- `web_service/frontend/components/UploadZone.tsx` ("use client", state mgmt, drop-zone idiom — model rendering of conditional UI states)
- `web_service/frontend/components/TokenField.tsx` (token entry pattern — reuse directly inside `ReconvertButton.tsx` for KFX)
- `web_service/frontend/components/FormatSelector.tsx` (format-gated UI patterns)
- `web_service/frontend/lib/api.ts` (typed fetch wrappers with `ApiError`)
- `web_service/frontend/tests/format-selector-upsell.spec.ts` (Playwright spec patterns — assertions on rendered text, button enablement)

**Test scenarios:**
- Happy path (Playwright) — Done EPUB job: see Download + Send-to-Kindle button on EPUB row; see Convert button on MOBI row and KFX row
- Happy path (Playwright) — Click Send-to-Kindle on EPUB row: form expands with From-address hint visible; enter `you@kindle.com`; click Send; assert "Sent to *you@kindle.com*. Arrives within a few minutes IF kindle@send.leafbind.io..." copy appears
- Happy path (Playwright) — localStorage persistence: send to `you@kindle.com`; reload page; open form; assert input pre-filled with `you@kindle.com`; click "Forget this address"; assert input cleared; reload again; assert still blank
- Happy path (Playwright) — Click "Convert" on MOBI row: button transitions to spinner; child job appears in parent's `children[]` via polling; row eventually shows "[Download MOBI]"
- Happy path (Playwright) — Click "Convert — paste token" on KFX row: TokenField appears; paste valid token; submit; child KFX job dispatches
- Edge case (Playwright) — `source_present === False`: all Convert buttons greyed with "session expired" copy; Send-to-Kindle gates on `output_present` independently (still works if output_present is true)
- Edge case (Playwright) — TTL countdown: with mocked `expires_at` 45 min in the future, see "about an hour"; with 5 min in the future, see "less than 10 minutes"; after a successful Send-to-Kindle, countdown disappears
- Error path (Playwright) — Send-to-Kindle returns 422 INVALID_RECIPIENT_DOMAIN: failure-generic state with inline error + Retry; **no** EB-322 link
- Error path (Playwright) — Send-to-Kindle returns 422 FORMAT_NOT_KINDLE_ELIGIBLE: failure copy points to USB/Calibre sideload (defensive — frontend should already gate MOBI/KFX out, but defense-in-depth)
- Error path (Playwright) — Send-to-Kindle returns failure-known fingerprint (mocked Resend webhook for `email.bounced`): failure copy puts approved-sender check first per R3.5, then EB-322 link
- Error path (Playwright) — Re-convert with invalid token: TokenField shows server error inline
- Edge case (Playwright) — 404 job: existing "we couldn't find that conversion" copy preserved (R5 — no regression)
- Edge case (Playwright) — Duplicate Send-to-Kindle click within 60s: button stays disabled; backend returns `already_sent`; UI shows the same success state (no duplicate alert)
- Integration (Playwright) — Multi-child scenario: re-convert to MOBI, then re-convert to KFX before MOBI completes; both children appear in `children[]`; polling continues; both eventually downloadable

**Verification:**
- `npx playwright test action-cluster.spec.ts` shows green
- `npm run build` (Next.js) shows zero type errors
- Manual smoke against staging Vercel preview: full flow from upload → action cluster → Send-to-Kindle → real arrival on tester's Kindle device

---

- [ ] ~~**Unit 7: FormatSelector visibility fix on upload page (R11)**~~ — **Removed from Wave 1 per plan-review P1-15.** R11 fixes an upload-time problem; Wave 1's kill-criterion gate measures post-conversion re-convert engagement. Shipping R11 in Wave 1 would suppress the signal Wave 2 depends on. File as a standalone follow-up ticket (e.g., EB-324a — *FormatSelector visibility fix*) and ship after the four-week Wave 1 measurement window completes — informed by the actual re-convert engagement data.

---

- [ ] **Unit 8: Rate-limiting (R13) — app-level slowapi + Cloudflare WAF deploy task**

**Goal:** Add app-level throttling on the two new endpoints; coordinate the single combined Cloudflare WAF rule.

**Requirements:** R13

**Dependencies:** Units 3, 4 (the routes being protected must exist)

**Files (in-PR):**
- Modify: `requirements.txt` (add `slowapi>=0.x.x`)
- Modify: `web_service/main.py` (register slowapi Limiter; configure `cf-connecting-ip` key extractor **gated by trusted-proxy check** — only honor the header when `request.client.host` is in the nginx loopback range, otherwise fall back to `get_remote_address` without trusting the header)
- Modify: `web_service/routes/reconvert.py` and `web_service/routes/send_to_kindle.py` (apply slowapi's `@limiter.limit(...)` decorator with the agreed-upon values)
- Modify: `deploy/nginx.conf` (add `allow <cloudflare-ipv4-ranges>; allow <cloudflare-ipv6-ranges>; deny all;` for the main `server` block — Cloudflare publishes the lists at `https://www.cloudflare.com/ips-v4` and `https://www.cloudflare.com/ips-v6`; check them into the config inline rather than referencing the URL at request time)
- Create: `deploy/refresh-cloudflare-ips.sh` (one-shot script: fetch the two Cloudflare IP lists, write them into `nginx.conf` between sentinel comments, validate `nginx -t`, reload — implementer runs this monthly per the runbook; documented but not yet scheduled)
- Modify: `deploy/CLOUDFLARE.md` (document the single combined WAF rule, the cf-connecting-ip dependency, the nginx allowlist + monthly refresh runbook, and the verification procedure for after the WAF deploy task lands)
- Test: `tests/test_web_rate_limit.py` (new module; mocks `cf-connecting-ip` header and verifies slowapi behavior — including the trusted-proxy gating: a request with `request.client.host = "203.0.113.5"` (non-loopback) AND a forged `CF-Connecting-IP` MUST use the actual `request.client.host` as the key, not the forged header)

**Pre-deploy verification (manual, before the code PR ships):**
- From an external IP outside Cloudflare's range, attempt to reach `https://<hetzner-vm-public-ip>/` on ports 80 and 443 — expect connection rejection (nginx denied) or a no-route condition (firewall denied). If the origin responds, the allowlist is not yet in effect and Unit 8 deploy is gated on fixing it.

**Deploy Task (out-of-PR, runs alongside but is not part of the code commit):**
- Cloudflare WAF — merge existing `/stripe/webhook` rule with new path matchers `/reconvert/*` and `/send-to-kindle/*` via Cloudflare API (requires API token with `Zone.WAF` write scope on the leafbind.io zone)

**Approach:**
- slowapi config:
  ```
  Limiter(key_func=lambda req: req.headers.get("cf-connecting-ip") or get_remote_address(req))
  ```
  Mount as middleware in `main.py`; expose `limiter` as a module-level for route decorators to import.
- Rate-limit values (defaults, implementer tunes):
  - `/reconvert/{parent_job_id}`: 10 per minute per IP, 5 per minute per `parent_job_id` (slowapi supports custom keys)
  - `/send-to-kindle/{job_id}`: 10 per minute per IP, 3 per minute per `job_id` (lower because abuse cost is real outbound mail)
- Cloudflare WAF rule (deploy task — runs concurrent with code PR, not blocking):
  - Single rule, period=10s (Free max), threshold=20 requests (coarse burst protector)
  - Expression: `(http.request.uri.path eq "/stripe/webhook") or (starts_with(http.request.uri.path, "/reconvert/")) or (starts_with(http.request.uri.path, "/send-to-kindle/"))`
  - Action: block; mitigation_timeout=10s (Free max)
  - Characteristics: `ip.src` + `cf.colo.id` (Free plan auto-adds)
- Trusted-proxy concern: nginx forwards via `X-Forwarded-For`, Cloudflare adds `CF-Connecting-IP`. Custom key extractor reads `CF-Connecting-IP` directly because all production traffic flows through Cloudflare. For local dev (no Cloudflare), falls back to `get_remote_address`.

**Patterns to follow:**
- `web_service/main.py:226-232` (CORS middleware as the model for adding new middleware)
- `deploy/nginx.conf:18-29` (rate-limit-relevant routing already in place for `/stripe/webhook`)
- `deploy/CLOUDFLARE.md` (existing Cloudflare deployment doc — extend with the new combined rule)

**Test scenarios:**
- Happy path — Single request to `/reconvert/{parent_id}` with `cf-connecting-ip: 1.2.3.4` succeeds; no rate-limit headers (or 200 within limit)
- Edge case — 11 requests in 60s from `cf-connecting-ip: 1.2.3.4` to `/reconvert/{parent_id}` → 11th returns 429
- Edge case — Requests from different `cf-connecting-ip` values share no counter; each IP independently within its 10/min limit
- Edge case — Missing `cf-connecting-ip` header: falls back to `request.client.host` (local dev / tests)
- Edge case — `cf-connecting-ip` with an IPv6 value: counter keyed correctly
- Integration — Send-to-Kindle 11th request from same IP returns 429; idempotency table NOT updated
- Manual (deploy verification) — burst test from a known external IP against staging hits the Cloudflare 10s window before the slowapi 60s window

**Verification:**
- `pytest tests/test_web_rate_limit.py` shows green
- After Cloudflare deploy: `pwsh tools/verify_rate_limit.ps1` (a small helper script — burst N requests, observe 429 from Cloudflare first, then slowapi)
- Existing `/stripe/webhook` rate-limit continues to function (regression check)

---

- [~] **Unit 9: Telemetry (R12)** — split into **9a** ✅ MERGED (whitelist extension; landed in Unit 1's PR #140 so server-side emissions in Units 3/4/10 aren't silently dropped), **9b-server** ✅ MERGED (PR #147 — `log_event(...)` calls in `routes/reconvert.py`, `routes/send_to_kindle.py`, and `job_queue.dispatch_job`; `reconvert_refund_applied` shipped earlier with Unit 3's refund hook), and **9b-client** ⏳ PENDING (client-side Plausible emissions from Unit 6's interaction sites; lands in Unit 6's PR). The unit body below describes the combined scope.

**Server-side emit canonical payload (as shipped in PR #147):** each event's `details` dict carries `output_format` + `tier`. Send-to-Kindle events additionally carry `recipient_hash` = `sha256(normalized_recipient).hexdigest()` (privacy-safe per-recipient correlation key — never the address itself) plus the event-specific field (`code` for rejected_by_validation, `message_id` for accepted_by_resend, `error_code`/`error_class` for send_error). Re-convert events carry `parent_job_id` + `child_job_id`.

**Why the server-side emits were decoupled from Unit 6 (revised):** the original plan paired server emits with Unit 6 to avoid a window where events flicker into recovery_events before dashboards exist. In practice the server emits are independently pytest-testable and the recovery_events table is durable (no premature aging), so PR #147 landed them separately to keep the Unit 6 frontend PR focused on the action cluster. The client-side Plausible emits still land with Unit 6. Exception (unchanged): `reconvert_refund_applied` shipped with Unit 3 because the refund hook itself is in Unit 3.

**Goal:** Emit the four event types the brainstorm specifies — format-selector engagement, send-to-Kindle attempt+outcome, convert-to-another-format attempt+outcome, expired-action-attempt.

**Requirements:** R12

**Dependencies:** Units 3, 4 (event sources); Unit 6 (frontend event emission)

**Files:**
- Modify: `web_service/recovery_events_store.py:55-60` (extend `_VALID_EVENT_TYPES` with the **14 new event types** enumerated in Approach below — 4 re-convert + 4 Send-to-Kindle send-side + 4 Unit 10 webhook delivery-side + 2 result-page UX. Events not in the whitelist are silently dropped per the existing pattern at lines 112-117. **`format_selector_engaged` is NOT included** — R11 is deferred per plan-review P1-15, so the FormatSelector emission ships with R11. **This change is Unit 9a and lands in Unit 1's PR** so server-side emissions in Units 3/4/10 aren't silently dropped when they fire.)
- Modify: `web_service/routes/reconvert.py` (Unit 9b adds: emit `reconvert_attempted` on entry, `reconvert_succeeded` / `reconvert_failed` on completion. Unit 3 already wired `reconvert_refund_applied` in `job_queue.py`'s refund hook — see PR #141.)
- Modify: `web_service/routes/send_to_kindle.py` (emit `send_to_kindle_attempted` on entry; `send_to_kindle_rejected_by_validation` on 4xx validation reject; `send_to_kindle_accepted_by_resend` on Resend 2xx; `send_to_kindle_send_error` on Resend 4xx/5xx/exception)
- Modify: `web_service/frontend/lib/api.ts` (add lightweight `emitEvent(type, props)` POSTing to `/api/event` — the existing Plausible proxy at `web_service/frontend/app/api/event/route.ts`)
- Modify: `web_service/frontend/components/ActionCluster.tsx` (emit `expired_action_attempted` when user clicks a disabled re-convert or Send-to-Kindle button)
- Test: `tests/test_web_recovery_events.py` (extend with the new event types; verify whitelist accepts them)
- Test: `web_service/frontend/tests/telemetry.spec.ts` (Playwright spec mocks `/api/event` and asserts the right POSTs fire on the right interactions)

**Approach:**
- **Whitelist extension lands first** (before Unit 10 wires its webhook emissions; before Units 3, 4 emit their send-side events). Required additions to `_VALID_EVENT_TYPES`:
  - Re-convert: `reconvert_attempted`, `reconvert_succeeded`, `reconvert_failed`, `reconvert_refund_applied`
  - Send-to-Kindle send-side (Unit 4 emits): `send_to_kindle_attempted`, `send_to_kindle_rejected_by_validation`, `send_to_kindle_accepted_by_resend`, `send_to_kindle_send_error`
  - Send-to-Kindle delivery-side (Unit 10 emits): `send_to_kindle_delivered_to_mail_server`, `send_to_kindle_bounced`, `send_to_kindle_delivery_failed`, `send_to_kindle_delivery_delayed`
  - Result-page UX: `expired_action_attempted`, `kindle_send_invariant_violation`

Note the distinction between send-side `send_to_kindle_send_error` (Resend 4xx/5xx at our API call) and delivery-side `send_to_kindle_delivery_failed` (Resend's `email.failed` webhook reporting a post-acceptance failure to deliver to Amazon's MX). The two names are deliberately different so dashboards can distinguish "we couldn't get the request into Resend" from "Resend tried to deliver and the receiving MX refused."
- **Server-side events**: `recovery_events_store.log_event(event_type, details={"job_id": job_id, ...})` — fire-and-forget. The actual function signature is `log_event(event_type, details=None, db_path=None)` (see `web_service/recovery_events_store.py:96-100`); `job_id` lives inside the `details` dict because the `recovery_events` schema has no first-class `job_id` column. Server-side telemetry stays on our VM — raw `job_id` here is acceptable because the capability-token ADR (see Documentation/Operational Notes) scopes the "never appears off-VM" constraint to *third-party* sinks. Payload includes `output_format`, `tier`, and (for send-to-Kindle events) `sha256(normalized_recipient).hexdigest()` — never the address itself.
- **Client-side events (Plausible custom events)**: POST `/api/event` with `{name: <event_type>, props: {...}}`. Plausible is a third-party sink — per the capability-token ADR, **raw `job_id` MUST NOT appear in props**. If cross-session correlation is needed, use `sha256(job_id + settings.telemetry_correlation_salt).hexdigest()[:16]` as `props.job_id_hash`. The salt is a new server-side secret (`WEB_TELEMETRY_CORRELATION_SALT` env var, added to `Settings` in `web_service/config.py`); it never leaves the server. Most events don't need correlation and should omit the field entirely.
- Failed Send-to-Kindle events include the failure code (e.g., `INVALID_RECIPIENT_DOMAIN`, `OUTPUT_TOO_LARGE_FOR_KINDLE`) as a prop, but NEVER the recipient address (raw or hashed) in client-side events.
- "Expired-action-attempt" is a frontend-only event — fires when the user clicks a disabled button. Disabled buttons use `aria-disabled="true"` (not the HTML `disabled` attribute) so click events still capture for telemetry. The keyboard-activation a11y concern (a disabled button is still focusable + activatable via Enter) is handled by attaching the click handler as a no-op when `aria-disabled === "true"` — telemetry fires but no underlying action.

**Patterns to follow:**
- `web_service/recovery_events_store.py:55-60` and `web_service/routes/recovery_events.py` (event-emission pattern, whitelist validation)
- `web_service/frontend/app/api/event/route.ts` (Plausible proxy — already exists)
- `web_service/frontend/app/layout.tsx:84-89` (Plausible Script tag — already wired)

**Test scenarios:**
- Happy path — POST `/send-to-kindle/{job_id}` with valid inputs emits `send_to_kindle_attempted` then `send_to_kindle_accepted_by_resend`
- Happy path — POST `/reconvert/{parent_id}` with KFX + valid token emits `reconvert_attempted`; on child completion emits `reconvert_succeeded` with `output_format=kfx, tier=premium`
- Edge case — Frontend: clicking a disabled Send-to-Kindle button emits `expired_action_attempted` with `action=send_to_kindle`
- Privacy — Telemetry payloads contain SHA-256 hash of recipient, not the address itself (PII boundary)
- Integration — `tests/test_web_recovery_events.py` asserts the new event types are accepted by `_VALID_EVENT_TYPES`

**Verification:**
- `pytest tests/test_web_recovery_events.py` shows green
- `npx playwright test telemetry.spec.ts` shows green
- Plausible dashboard shows the four new custom events appearing in real traffic post-deploy

- [ ] **Unit 10: Resend webhook handler — `POST /webhooks/resend` (delivery telemetry)**

**Goal:** Receive Resend webhook events for Send-to-Kindle messages, verify Svix signatures, update `kindle_delivery_status` on the originating job, and emit graded delivery telemetry. Closes the silent-failure observability gap at the Resend → Amazon-MX layer (Amazon-internal failures past that point remain out of scope).

**Requirements:** R3.6, R3 (the honest-delivery-signal half), R12 (telemetry — extends event set)

**Dependencies:** Unit 1 (`resend_message_id` and `kindle_delivery_status` columns on jobs); Unit 4 (`message_id` captured at send time); Unit 9a whitelist (the four delivery-side event types — `send_to_kindle_delivered_to_mail_server`, `send_to_kindle_bounced`, `send_to_kindle_delivery_failed`, `send_to_kindle_delivery_delayed` — must be in `_VALID_EVENT_TYPES` before this unit emits)

**Files:**
- Create: `web_service/routes/resend_webhook.py` (new route)
- Modify: `web_service/main.py` (register the new router; add `WEB_RESEND_WEBHOOK_SECRET` to `Settings` in `web_service/config.py`)
- Modify: `web_service/job_store.py` (add `find_by_resend_message_id(message_id) -> dict | None` helper; `update_kindle_delivery_status(job_id, status)` already in Unit 1)
- Modify: `requirements.txt` (add `svix>=1.x.x` for signature verification — recommended per Resend docs)
- Modify: `deploy/CLOUDFLARE.md` (add the new path to the combined WAF rule expression; document the webhook URL needs to be registered in the Resend dashboard with the secret stored in `/etc/web_service.env`)
- Test: `tests/test_web_resend_webhook.py` (new module — signed-event fixtures, payload-shape coverage, status-update integration)

**Approach:**
- Endpoint reads raw request body before parsing (Svix verification requires the unparsed bytes). Use `await request.body()` *before* `await request.json()` to avoid the Starlette double-read issue.
- Svix verification: `webhook = Webhook(settings.resend_webhook_secret); payload = webhook.verify(raw_body, dict(request.headers))` — raises on signature failure. Catch and return 401 (not 400 — Svix convention is "401 if signature invalid, 400 if payload malformed").
- Event handling by `payload["type"]`:
  - `email.delivered` → `update_kindle_delivery_status(job_id, "delivered_to_mail_server")`; emit telemetry `send_to_kindle_delivered_to_mail_server`
  - `email.bounced` → `update_kindle_delivery_status(job_id, "bounced")`; emit telemetry `send_to_kindle_bounced` with bounce subtype (Permanent/Transient/Suppressed) in the details dict
  - `email.failed` → `update_kindle_delivery_status(job_id, "failed")`; emit telemetry `send_to_kindle_delivery_failed` with the Resend-reported failure reason in the details dict (but **scrub the recipient address** from the reason if present)
  - `email.delivery_delayed` → `update_kindle_delivery_status(job_id, "delivery_delayed")`; emit telemetry `send_to_kindle_delivery_delayed`
  - Any other event type → 200 OK, no state change, no telemetry (silently ignore — Resend may emit `email.sent`, `email.opened`, `email.clicked`, `email.complained` which we don't act on in Wave 1)
- Correlation: extract `data.email_id` (Resend message ID) from the payload; `find_by_resend_message_id(message_id)` returns the originating job. If no job found (e.g., webhook for a deleted job), 200 OK + log a warning by message_id only (NOT by recipient). Do not crash on missing correlation — Resend may send retries.
- **Privacy / logging discipline (R3.6 + Privacy page commitment)**:
  - Raw webhook payloads MUST NOT be logged. Log only `(event_type, message_id, job_id, status_transition)`.
  - The webhook handler MUST NOT include the recipient address (`data.to[]`) anywhere in logs or telemetry. If a failure-reason field contains the address (Resend sometimes echoes it in `bounce.message`), the address is scrubbed before logging.
  - Idempotency: Resend may retry webhooks. The `update_kindle_delivery_status()` helper MUST be idempotent — repeated identical updates are no-ops; transitions in the wrong direction (e.g., `delivered` → `delivery_delayed` arriving out of order) are logged and ignored.
- WAF: the new path `/webhooks/resend` joins the combined Cloudflare WAF rule from Unit 8 — same path-OR expression now covers `/stripe/webhook`, `/webhooks/resend`, `/reconvert/*`, `/send-to-kindle/*`.

**Execution note:** Write the signature-verification failure test first — if Svix verification can be bypassed, the entire telemetry signal becomes attacker-forgeable.

**Patterns to follow:**
- `web_service/routes/webhook.py` (Stripe webhook — pattern for signature verification + raw-body handling + sync executor dispatch for downstream DB writes — model after this exactly)
- `web_service/recovery_events_store.py:96-100` (`log_event()` fire-and-forget)
- `https://resend.com/docs/dashboard/webhooks/verify-webhooks-requests` (Svix verification reference)
- `https://resend.com/docs/dashboard/webhooks/event-types` (event-payload shapes)

**Test scenarios:**
- Happy path — `email.delivered` for a known message_id: job's `kindle_delivery_status` flips to `delivered_to_mail_server`; telemetry `send_to_kindle_delivered_to_mail_server` event recorded; response 200
- Happy path — `email.bounced` (Permanent): status `bounced`; telemetry includes bounce subtype; response 200
- Happy path — `email.failed`: status `failed`; telemetry includes scrubbed reason
- Happy path — `email.delivery_delayed`: status `delivery_delayed`; later `email.delivered` flips it to delivered (out-of-order arrival handled)
- Edge case — Unknown event type (e.g., `email.opened`): 200 OK, no state change, no telemetry
- Edge case — Webhook for unknown message_id: 200 OK, warning logged by message_id only; no crash
- Edge case — Out-of-order arrival: `delivered` arrives, then `delivery_delayed` arrives: status stays `delivered`, the delay event is logged and ignored
- Edge case — Duplicate webhook (Resend retry): identical event arrives twice; second call is a no-op idempotent update
- Error path — Missing Svix signature headers: 401
- Error path — Invalid Svix signature: 401 (Svix verify raises)
- Error path — Valid signature but malformed payload (missing `type` or `data.email_id`): 400
- Privacy — Test that a webhook payload containing a recipient address in `bounce.message` does NOT cause that address to appear in logs or in the telemetry event's `details` dict

**Verification:**
- `pytest tests/test_web_resend_webhook.py` shows green (all signature + payload paths)
- Log capture during the privacy test contains no `@kindle.com` strings
- Manual smoke (`pwsh tools/verify_resend_webhook.ps1`): send a real Send-to-Kindle via `tools/verify_send_to_kindle.ps1`, verify a corresponding webhook arrives at the staging URL and the job's `kindle_delivery_status` updates

---

## System-Wide Impact

- **Interaction graph:** New routes (`/reconvert`, `/send-to-kindle`) join the existing `/convert`, `/status`, `/download`, `/checkout`, `/webhook`, `/recover` family. All share `billing_executor`, `circuit_breaker`, and the global slowapi limiter. The `_cleanup_after_download` change in Unit 2 removes a callback that today affects `download` semantics — verify no other route calls `set_expired` defensively expecting the old behavior. The job-queue dispatcher (`web_service/job_queue.py:dispatch_job`) gains a refund hook on child-job failure.
- **Error propagation:** New endpoints follow the existing `HTTPException(detail={"error", "code"})` shape so the frontend `ApiError` class handles them uniformly. Resend SDK errors are mapped to our HTTP error codes inside `send_to_kindle.py` — never leaked raw.
- **State lifecycle risks:** Source-copy means each child has independent `temp_dir`; no cross-child cleanup interaction. Parent's source `input.<ext>` is the only shared artifact, and it's read-only — once copied, parent rmtree on TTL doesn't affect children. The 60-second idempotency table is opportunistically swept on insert; if writes stop, rows accumulate harmlessly until the next insert prunes them. The `refund_ledger` table has no TTL — it's a permanent audit trail.
- **API surface parity:** `GET /status/{job_id}` adds four new fields (additive — no breaking change for existing consumers). Frontend's `StatusResponse` type updates correspondingly. Other API clients (e.g., the recovery-page status reader) continue to work because they ignore unknown fields.
- **Integration coverage:** The R2.5 parent-TTL-during-child-run integration test is the load-bearing scenario — exercises the cleanup pattern at its edge. The mocked-Resend tests cover validation logic; the signed-event e2e test verifies the SDK call shape against Resend's actual test API. Frontend Playwright specs cover the user-visible state transitions.
- **Unchanged invariants:** The 1h/24h TTL retention policy is unchanged. The brand promise ("we delete in 1h/24h") is unchanged. The single-use atomic token-consume contract on `tokens.token_hash` is preserved — `refund_token` is a *new* operation that reverse-consumes; the original `validate_and_consume` semantics don't shift. The Stripe webhook signing flow is untouched. CORS configuration is untouched.

## Risks & Dependencies

| Risk | Mitigation |
|---|---|
| `_cleanup_after_download` change orphans output files if TTL sweep is buggy | Unit 2 integration test covers download → TTL elapse → cleanup; existing `test_web_sweeps.py` continues to gate. Production observability: track temp_dir disk usage post-deploy for the first week |
| Source-copy disk usage spikes if real-world fanout exceeds expectations | Telemetry on `reconvert_attempted` per parent gives early signal. If usage spikes, switch to pinning is a localized migration (Unit 1 schema unchanged) |
| Amazon-side E999 / unapproved-sender failures are invisible to our send-side pipeline (arrive as async reply mail, not Resend webhook) | Resend webhook (Unit 10) provides honest mail-provider delivery telemetry; R3.5 UX qualifies success copy with the approved-sender dependency. Inbound-mail bounce parsing is a follow-up ticket if user-reported silent failures materialize |
| Cloudflare WAF rule consolidation deploy task slips after code PR ships | Code PR is deployable without the WAF rule (app-level slowapi is load-bearing). Sequence: ship code → confirm slowapi works → consolidate WAF rule. Do not block code on WAF |
| Migration race on `_LATER_COLUMNS` add | Existing pattern + extended `test_web_job_store_migration_race.py` coverage; `BEGIN IMMEDIATE` serializes concurrent workers |
| Token refund operation introduces a new attack surface (replay attack to keep refunding) | `refund_token` only fires from `job_queue.dispatch_job` failure path (server-internal, not user-callable); idempotent on `token_hash` per atomic update; ledger gives audit trail. No user-facing refund endpoint added in Wave 1 |
| Wave 2 success criterion (≥15% engagement) may not materialize, leaving infrastructure unused | The infrastructure (schema, refund flow, rate-limit, telemetry) is reusable for any future post-conversion feature, not specific to Wave 2's multi-format-on-upload. If Wave 2 telemetry is flat, decisions about further investment are separable |
| Premium re-convert from result page exposes the TokenField to URL-crawler bots that may attempt token brute force | TokenField client-side regex matches the 64-char format; server-side `validate_token_format` rejects anything else with 422 before DB hit. Cloudflare WAF rate-limit rule covers `/reconvert/*`. Brute-force expected-value space is 2^(43*6) — economically infeasible |
| Sender address (`kindle@send.leafbind.io`) isn't on Resend's verified-domain config | Deploy-side blocker: implementer verifies via Resend dashboard before Unit 4 ships. Add to deploy checklist |

## Documentation / Operational Notes

- **`.env.example`** (or equivalent) needs `WEB_RESEND_API_KEY=` and `WEB_SEND_TO_KINDLE_FROM=kindle@send.leafbind.io`. Document scope (sending-access restricted to `leafbind.io`).
- **`deploy/CLOUDFLARE.md`** gets an addendum for the consolidated WAF rule + verification procedure.
- **`web_service/docs/`** — consider a new `send-to-kindle.md` mirroring the structure of `stripe-verification.md` (env vars, troubleshooting, three-layer test model).
- **Privacy page** (`web_service/frontend/app/(marketing)/privacy/page.tsx`) — add a short paragraph about Send-to-Kindle: "When you use Send to Kindle, your Kindle email address is included in the email Resend sends to Amazon. The address is visible in Resend's message log (audit surface), but never stored in our database, application logs, or telemetry. You may clear the locally-remembered address at any time."
- **ADR — `docs/decisions/ADR-EB-324-job-id-capability.md`** (new file, committed in the code PR): document that for the leafbind web service, knowing a `job_id` is treated as the authorization capability for `/status`, `/download`, `/reconvert`, and `/send-to-kindle`. Record the rationale (UUIDv4 entropy ~122 bits; matches existing semantics for `/status` and `/download`), the constraints (raw `job_id` MUST NOT appear in third-party sinks — Plausible client events use `sha256(job_id + correlation_salt).hexdigest()[:16]` if correlation is needed; result page URLs are user-shareable so the capability transfers to anyone with the URL — accepted; per-job HMAC capability tokens are the natural follow-up if URL-sharing abuse materializes), and the explicit non-coverage (origin lockdown does not solve leaked-URL capability transfer — that is a separate problem with a separate follow-up).
- **Operational rollout** — staged: Unit 1 (schema) ships first behind a feature flag is overkill; instead, ship Unit 1 + Unit 2 together (the `_cleanup_after_download` change is functionally invisible until Units 3/4 land). Units 3/4/5 ship together (frontend depends on the routes existing). Units 6/7/8/9 can ship in any order after that.
- **Resend domain provisioning** is a manual prerequisite — implementer creates the `kindle@send.leafbind.io` sender + restricted API key in the Resend dashboard before Unit 4 deploy.
- **Feature manifest is NOT updated for web_service changes.** `feature-manifest.json` tracks PowerShell pipeline surfaces (Verb-Noun cmdlets in `EbookAutomation.psm1`) only — there are no web_service Python entries today and Wave 1 does not introduce a new manifest section. Earlier drafts of the plan called for adding `list_children`, `refund_token`, etc. as manifest entries; that reference has been removed.
- **Worktree-policy** — all `web_service/**` changes land via feature branches per `.claude/worktree-policy.json`. `requirements.txt`, `config/settings.json`, `docs/**` are exempt and can land directly on master.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-05-19-eb-324-post-conversion-action-cluster-requirements.md](../brainstorms/2026-05-19-eb-324-post-conversion-action-cluster-requirements.md)
- **Related solution docs:**
  - `docs/solutions/best-practices/leafbind-email-auth-stack-2026-05-16.md` (Resend stack)
  - `docs/solutions/security-issues/xss-unescaped-session-id-fastapi-fstring-templates-2026-05-15.md` (XSS test discipline)
  - `docs/solutions/workflow-issues/cloudflare-cache-purge-fallback-querystring-2026-05-14.md` (Cloudflare token scope history)
- **Related ADRs:** `docs/decisions/ADR-EB-181-data-exemption-scope.md`
- **Related Jira tickets:** EB-324 (this work), EB-322 (Send-to-Kindle troubleshooting page — R3 link target), EB-315 (async delivery UX — not blocking), EB-321 (premium KFX quality — independent), EB-237 (timeout policy — blocks Wave 2), EB-225/EB-236 (existing Cloudflare WAF rule for `/stripe/webhook`), EB-271 (404 vs 500 distinction in ConversionStatus)
- **External docs:**
  - Amazon Send-to-Kindle: `https://www.amazon.com/sendtokindle`
  - Resend send-email API: `https://resend.com/docs/api-reference/emails/send-email`
  - Resend attachments: `https://resend.com/docs/dashboard/emails/attachments`
  - Resend idempotency: `https://resend.com/docs/dashboard/emails/idempotency-keys`
  - Resend webhooks: `https://resend.com/docs/dashboard/webhooks/event-types`
  - slowapi: `https://slowapi.readthedocs.io/`
  - Cloudflare WAF rate-limit: `https://developers.cloudflare.com/waf/rate-limiting-rules/`
