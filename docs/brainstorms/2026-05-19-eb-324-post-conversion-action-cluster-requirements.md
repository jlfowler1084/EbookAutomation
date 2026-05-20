---
date: 2026-05-19
topic: eb-324-post-conversion-action-cluster
---

# EB-324 — Post-Conversion Result Page Action Cluster

## Problem Frame

A user uploads a PDF to leafbind.io and waits for conversion. The status page (`web_service/frontend/app/(app)/status/[id]/page.tsx`) shows "Status: Done!" with **two** affordances: "Download converted file" and "← Convert another file". Three problems flow from that terminal screen:

1. **The output format was chosen silently.** A `FormatSelector` exists in `web_service/frontend/components/UploadZone.tsx:110` and renders below the drop zone with EPUB as default, but it is visually de-emphasized — users who focus on the drop zone get auto-EPUB without realizing they had a choice.
2. **No action besides "download" is reachable.** The Kindle email delivery pipeline exists in the PowerShell module but has **zero** frontend representation today (grep across `web_service/`: send-to-kindle is referenced only in marketing/guide pages, never as a callable feature). Premium upsell to KFX requires leaving the page and starting over.
3. **No path to convert the same file to another format.** Even though the source PDF stays on disk for 1 h (free) or 24 h (premium) per `web_service/config.py:97-98`, the result page does not expose any way to re-use it. The user has to re-upload.

The combined effect: uploading feels transactional ("convert one file, leave") rather than productive ("convert this thing, do something useful with it, optionally pay to upgrade the output"). The freemium upsell is also weaker than it could be because the moment the user has tasted the free output is exactly the moment they would best understand the value of the premium tier.

## Requirements

This work ships in two waves. **Wave 1 = EB-324** (the core fix). **Wave 2 = sibling ticket** (e.g. EB-324b), opened only if Wave 1 telemetry meets the kill-criterion threshold recorded in Key Decisions. Single-ticket anchoring was rejected during document review because it couples Wave 2 cancellation to bureaucratic friction.

### Wave 1 — Result page action cluster

**Action cluster on `Status: Done`**

- **R1.** When a job reaches `done` and source files are still within their retention window, the result page MUST present at least these actions in addition to "Convert another file":
  - Download the converted file (current behavior, preserved).
  - **Send to Kindle** — collect a Kindle email address inline and submit to a server-side handoff route that uses the existing email delivery mechanism.
  - **Convert this file to another format** — at least one other free format (EPUB↔MOBI) and at least one premium upsell (KFX → consumes 1 credit).
- **R2.** Each "convert to another format" action MUST re-use the already-uploaded source (no re-upload). The action is gated by both retention-window expiry and (for premium formats) credit availability.
- **R2.1.** Re-convert MUST use the stay-in-place page model recorded in Key Decisions. A re-convert action creates a *child job* linked to the parent in `job_store`; the result page stays at `/status/{parent_job_id}` and `GET /status/{parent_job_id}` returns a `children: [{job_id, format, status, download_url}]` array. The action cluster updates progressively as each child reaches `done`.

**Child-job mechanics (datastore, polling, TTL):**

- **R2.2.** The frontend status-poller (`web_service/frontend/components/ConversionStatus.tsx:24`) MUST continue polling `/status/{parent_job_id}` after the parent reaches `done` **while any child is in `queued` or `running`**. Current stop condition (`status === "done" || status === "failed"`) is incorrect for the action-cluster page and MUST be widened to `parent terminal AND no child in_flight`. Polling cadence stays at 5 seconds (current value).
- **R2.3.** `job_store.jobs` MUST gain a nullable `parent_job_id` column (TEXT, foreign key to `jobs.job_id`), indexed for child lookup. `create_job` accepts an optional `parent_job_id`. A new helper `list_children(parent_job_id)` returns child rows ordered by creation time. Migration is forward-only; existing rows have `parent_job_id = NULL`.
- **R2.4.** Source-data lifetime under parent/child relationships MUST eliminate the race where parent TTL cleanup runs while a child is mid-conversion. Two viable strategies; planning picks one:
  - **(a) source-copy at dispatch** — child's `temp_dir` gets its own copy of `input.<ext>` at re-convert dispatch; child is then independent of parent TTL. Simpler coordination, ~20–100 MB extra disk per re-convert.
  - **(b) source-pinning** — parent `temp_dir` stays alive while any child is in-flight; `_cleanup_job` MUST check `list_children(parent_job_id)` for non-terminal children and defer rmtree if any exist. More efficient on disk, requires careful coordination on the cleanup boundary.

  Whichever is chosen, the requirement is: **no child job loses its source mid-conversion due to parent cleanup.** Recommended default is (a) source-copy because the disk cost is small for the expected re-convert volume and it sidesteps cleanup ordering bugs entirely.
- **R2.5.** Test suite MUST include an integration test that exercises the parent-TTL-elapses-while-child-running race: dispatch a child re-convert, force parent TTL to elapse mid-conversion, assert the child completes successfully and produces a downloadable output. This is the load-bearing test for R2.4; either strategy must pass it.

**Premium re-convert credit binding:**

- **R2.6.** For premium re-convert (e.g., "Convert to KFX — 1 credit"), the result page MUST collect a token via the existing `<TokenField>` component (`web_service/frontend/components/TokenField.tsx`) — same UX as upload. The token is supplied at the moment the user initiates the re-convert; it is **not** carried over from the parent job. (Free re-converts — EPUB → MOBI — collect no token.)
- **R2.7.** Premium child jobs MUST persist a hash of the consumed token on the child job row in `job_store`, so the refund operation (per the atomic-refund Key Decision) can locate the originating token without storing the plaintext. The hash MUST be **the existing `compute_token_hash(token)` digest** defined at `web_service/crypto.py:127` (HMAC-SHA256) — this is the same digest the `tokens` table is keyed on (`web_service/token_store.py:360`), so refund lookup is a single join. Do NOT introduce a different hash function. Storage representation MUST match what `token_store` already uses for `token_hash` (BLOB column today; planning verifies whether `jobs` table stores the same BLOB form or hex). The new refund operation in `token_store` MUST:
  - Re-enable (atomic reverse-consume) the original token if it is still within its purchase-expiry window, AND
  - Fall back to writing a `refund_ledger` row + surfacing "Contact support to recover this credit" in the failure copy if the token has expired by the time refund fires.
  - Refund is triggered automatically when a premium child job transitions to `failed`. The user does not have to ask for it. Telemetry event under R12 records the refund occurred.
- **R3.** "Send to Kindle" MUST surface success/failure inline. On failure with a known fingerprint (Amazon e999, auth failure), the failure copy MUST link to the existing troubleshooting guide page (EB-322 deliverable; ticket already filed).
- **R3.1.** The Send-to-Kindle endpoint MUST validate the recipient email server-side before invoking the email-send path. Validation steps in order: (1) parse the address using a real RFC-5322-aware parser (e.g., Python `email.utils.parseaddr` + `email_validator` library), (2) apply R3.4 normalization (lowercase, strip whitespace, reject display-name and plus-aliasing forms), (3) require the **normalized domain part** to be **exactly** one of `kindle.com` or `free.kindle.com` — no wildcard / suffix matching, since loose suffix matches accept hostile inputs like `evil-kindle.com`. Non-matching recipients MUST be rejected with a 422 and user-visible copy explaining the constraint. This prevents the endpoint from being used as an open mail relay.
- **R3.2.** The frontend Send-to-Kindle form MUST implement the state contract recorded in Key Decisions: idle / sending / success-collapsed / failure-known (with EB-322 link) / failure-generic (no EB-322 link) / duplicate-send-guard. "Success" is defined as Resend returning a 2xx ack — *not* confirmation of Kindle-side delivery. The success copy MUST honestly surface the approved-sender dependency per R3.5 — exact wording lives in R3.5 (delivery depends on the From address being on the user's Amazon Approved Personal Document Email List, with a verification link). Do NOT use the unqualified "it usually arrives within a few minutes" — that copy is now obsolete and creates the silent-failure mode R3.5 was added to prevent.
- **R3.3.** The Send-to-Kindle endpoint MUST validate the output before invoking the email-send path:
  - **Format allowlist**: output format MUST be in Amazon's current Send-to-Kindle **email-accepted** list. The canonical local reference is the troubleshooting guide at `web_service/frontend/app/(marketing)/guides/send-to-kindle-not-working/page.tsx:260-269` (PDF, DOC/DOCX, RTF, TXT, HTML/HTM, EPUB DRM-free, JPG/JPEG/PNG/GIF/BMP). **MOBI is explicitly NOT accepted via email** (Amazon dropped it in 2022 — verified in `how-to-send-pdf-to-kindle/page.tsx:81` and the updated MOBI section). **KFX is NOT accepted via email** — it's a sideload format. **For leafbind in Wave 1, only one of our outputs is email-eligible: EPUB.** MOBI and KFX rows on the result page MUST NOT render a Send-to-Kindle button; their copy nudges USB-or-Calibre sideload. The full format-allowlist check is therefore "future-proof" rather than load-bearing for Wave 1, but MUST be implemented as a server-side allowlist regardless so that any future output format addition (e.g., PDF passthrough) goes through the validation path.
  - **Size cap**: post-MIME-encoded attachment size MUST be ≤ 36 MB. Resend's published maximum is 40 MB inclusive of MIME framing and base64 expansion; the 36 MB cap leaves a safety margin for headers/boundary overhead. Reject oversized outputs with a 422 and copy that suggests side-load via USB or splitting. (Reference: https://resend.com/docs/dashboard/emails/attachments)
  - **Per-job-id binding**: Send-to-Kindle is a **per-output** action — but since each job (parent or child) produces exactly one output file in the current and proposed schema, the endpoint takes a single `job_id` (parent or child) and the server reads the one stored output path for that job. No separate `output_id` is introduced; "output identifier" === "job_id" for Wave 1. (If Wave 2's multi-format-on-upload later produces multiple outputs per job, a real `outputs[]` shape gets introduced then — explicitly out of scope for Wave 1.)
- **R3.4.** The Send-to-Kindle endpoint MUST enforce server-side abuse prevention beyond R13's rate-limit layer:
  - **Idempotency**: the server MUST track `(job_id, normalized_recipient)` tuples for at least 60 seconds. A duplicate submission within that window returns 200 with body `{"status": "already_sent"}` and does NOT trigger a second outbound email. Beyond 60 seconds the user may legitimately re-send (e.g., they noticed the first didn't arrive) — that case is allowed.
  - **Output binding**: the endpoint MUST send only the stored output file at the job's `output_path` (read from `job_store` metadata for the given `job_id`) — it MUST NOT accept a user-supplied content body, attachment path, or alternate output. (Aligns with the "job_id === output identifier" model in R3.3.)
  - **Recipient normalization**: server-side normalization MUST lowercase the entire address, strip leading/trailing whitespace, and reject the display-name form `"Name" <addr@kindle.com>` with a 422. Plus-aliasing (`user+tag@kindle.com`) is rejected because Amazon's Kindle address scheme doesn't use it. Normalization happens BEFORE the R3.1 allowlist check.
- **R3.5.** The Send-to-Kindle UI MUST surface the **approved-sender requirement** before the user submits. Without this, Resend can return 2xx and Amazon can still drop the email because the From address is not in the user's personal-document approved-sender list — silent failure, indistinguishable from success in the UI.
  - **Form state**: the idle email form MUST display the chosen From address (e.g., `kindle@send.leafbind.io` — final value is a planning-time call recorded in the Dependencies/Assumptions section) with copy like: *"Sending from `kindle@send.leafbind.io`. **First time?** Add this address to your **Amazon Personal Document Settings → Approved Personal Document Email List** or Amazon will reject the email. [How →](https://www.amazon.com/sendtokindle)"*
  - **Success state**: the success copy MUST acknowledge the approved-sender gate. Replace the current "it usually arrives within a few minutes" with: *"Sent to `you@kindle.com`. Arrives within a few minutes — **if** `kindle@send.leafbind.io` is on your approved-sender list. [Verify →](https://www.amazon.com/sendtokindle)"*
  - **Failure state**: when Resend reports an Amazon-side auth-failure fingerprint (per R3.2's "failure-known" branch), the copy MUST include the approved-sender check as the first troubleshooting step before linking to EB-322 for the broader troubleshooting page.
  - **Single source of truth**: the From address SHOULD be exposed via the same backend config that drives R3.4's output-binding so the UI string can't drift from the actual sender. A `GET /config/send-to-kindle` (or equivalent) returning `{from_address: "kindle@send.leafbind.io"}` is appropriate — planning decides whether to inline this in the status response or fetch separately.

**Retention-expired state**

- **R4.** When the TTL has elapsed and source files are no longer on disk, "Send to Kindle" and "Convert to another format" buttons MUST display as disabled with copy that explains the expiry (e.g., "This session expired — upload your file again to convert to another format"). "Convert another file" MUST remain available.
- **R4.1.** `GET /status/{job_id}` MUST surface the fields the frontend needs to drive disabled state and (optionally) a countdown — at minimum: `expires_at` (epoch seconds), `source_present` (boolean: is `temp_dir/input.<ext>` still on disk?), and `output_present` (boolean: is the job's `output_path` still on disk?). The two on-disk hints are independent because re-convert needs the **source** while Send-to-Kindle needs the **output** — and either can be missing while the other survives (e.g., source-copy strategy from R2.4 detaches a child's lifetime from its parent's source). The frontend MUST gate re-convert on `source_present` and gate Send-to-Kindle on `output_present`; do NOT use `source_present` to disable the Send-to-Kindle button. Same fields appear on each child in the `children[]` array.
- **R5.** A user landing on a result page where the job_id no longer exists at all (404 path already handled in `ConversionStatus.tsx:51-67`) MUST continue to see the existing "we couldn't find that conversion" copy — the new actions are additive, not a replacement for that flow.

**Failure-state actions**

- **R6. (removed 2026-05-19)** Originally proposed a failure-state "try a different output format" action. Removed entirely per the document-review-time decision recorded in Key Decisions — failure-mode UX needs its own thinking once we have telemetry on what actually fails and why. Numbering preserved for stable cross-references; the requirement does not ship.

### Wave 2 — Multi-format-on-upload

- **R7.** The upload form MUST allow the user to select more than one output format before submitting. Default selection is a single format (EPUB) so users who do not engage with the picker see no change.
- **R8.** When the user selects multiple free formats (EPUB + MOBI) the server MUST produce both in a single job. The result page presents both downloads inline.
- **R9.** When the user selects a premium format alongside a free one (EPUB + KFX), the credit consumption MUST happen at upload time (same as the current single-format premium flow). Mixed selections that exceed available credits MUST fail validation before upload completes, with a clear upsell path.
- **R10.** Free tier multi-select MUST be capped at two formats to bound abuse of free compute. Premium has no such cap beyond credit balance.

### Cross-wave UX standards

- **R11.** Format selector visibility on the upload page MUST be improved as part of Wave 1 (it is the cheapest fix in the cluster — repositioning and restyling the existing component). The fix is in-scope even though the picker itself already exists. This addresses the original "silent format pick" complaint without restructuring the upload page.
- **R12.** Telemetry MUST capture, at minimum, four event types: format-selector engagement on upload, send-to-Kindle attempt + outcome, convert-to-another-format attempt + outcome, and expired-action-attempt (user clicked a disabled button or revisited an expired result page). Used for prioritization of Wave 2 and future polish.
- **R13.** Both new server-side endpoints (`POST /reconvert/*` and `POST /send-to-kindle/*`) MUST be covered by rate-limit enforcement. The Cloudflare WAF rule budget on the Free plan is tight — EB-225/EB-236 already consumed the rule slot for `/stripe/webhook`. The plan MUST therefore:
  - Verify the current Cloudflare Free-plan WAF rule budget for the leafbind.io zone before deployment, **and**
  - Either: (a) add a single combined WAF rule whose URI matches all three sensitive paths (`/stripe/webhook`, `/reconvert/*`, `/send-to-kindle/*`) with characteristics on `ip.src`, OR (b) move to Cloudflare Pro if multiple distinct rules with per-path tuning are required, OR (c) accept that WAF coverage is best-effort and rely on the app-level throttle below.
  - Implement **app-level throttling in the FastAPI service** as a complementary layer (per-IP and per-job_id counters with a small in-memory or SQLite-backed leaky-bucket). This is the load-bearing defense; the WAF rule is defense-in-depth. Without app-level throttling, `send-to-kindle` is an SMTP-relay abuse path and `reconvert` is a free-compute DoS path.
  - **Trusted client-IP extraction**: per-IP throttling MUST NOT use `request.client.host` naively — behind nginx and Cloudflare that value is the proxy IP, not the user. The app MUST resolve the real client IP from `CF-Connecting-IP` (Cloudflare's authoritative header) or `X-Forwarded-For` (nginx-set), and MUST only trust those headers if the request originates from a known proxy range (Cloudflare's published IP ranges + the local nginx). This pattern is already required elsewhere in the code; planning should align with existing usage in `web_service/routes/checkout.py:97` and the trust-proxies pattern in `deploy/nginx.conf:35`. Without this, per-IP throttle counters collapse onto one or two proxy IPs and the limit becomes effectively zero.
  - Reference: Cloudflare WAF rate-limiting rules documentation at https://developers.cloudflare.com/waf/rate-limiting-rules/ for current rule shape and free-plan constraints.

## Success Criteria

- A user who uploads a PDF and receives an EPUB can, **without leaving the result page**, send it to their Kindle email and confirm the handoff succeeded (Resend accepted the message — Amazon-side delivery is outside our observability surface, per R3.2).
- A user who uploads a PDF, receives an EPUB, and then realizes they wanted KFX can purchase a credit and produce a KFX from the same source within the retention window — no re-upload required.
- Telemetry over a four-week window post-launch shows non-trivial use of at least one new action (send-to-Kindle or re-convert). If both stay near zero, the action cluster is not solving a real problem and Wave 2 should be reassessed rather than auto-shipped.
- Free-tier compute usage does **not** materially increase from Wave 1 alone (no eager multi-format work; everything is user-initiated).

## Scope Boundaries

- **Out of scope, this brainstorm:** Redesigning the upload page beyond format-picker visibility (R11). Repricing the credit cost of KFX or other premium formats. Changing the free-tier file-size cap.
- **Out of scope, deferred to other tickets:**
  - In-progress UX (progress bar, time estimate, email-me-when-done) — that is **EB-315**, intentionally not blocking EB-324.
  - 30-day premium retention as a product positioning move — the "challenger" approach from the brainstorm. Worth a sibling ticket only if Wave 1 telemetry shows users hitting the TTL wall.
  - Send-to-Kindle troubleshooting page — that is **EB-322**, already filed. R3 links *to* it, doesn't duplicate it.
  - Premium EPUB→KFX quality regression — **EB-321**, independent.

## Key Decisions

- **Two-wave delivery, sibling-ticket model.** *(Superseded by the "Wave 2 ships as a sibling ticket" decision below — kept here as the historical entry point for the wave structure.)* Wave 1 is EB-324; Wave 2 lives in its own ticket opened only if Wave 1 telemetry hits the kill-criterion threshold.
- **Retention model is *not* changing in this brainstorm.** The existing 1 h (free) / 24 h (premium) source-retention behavior in `web_service/config.py` and `_cleanup_job` is already sufficient to power "convert to another format" — verified by reading `web_service/routes/convert.py:104-108` (source written to `temp_dir/input.<ext>`) and `web_service/job_queue.py:156-163` (rmtree on TTL expiry). The brand promise ("we delete in 1 h / 24 h") is preserved.
- **Send-to-Kindle is additive, not a replacement for download.** Some users want the file locally to side-load via USB or Calibre. Removing the download path would regress a real use case.
- **`_cleanup_after_download` is changed to a no-op for the action cluster: download neither deletes the output file nor calls `set_expired`. The TTL sweep in `web_service/job_queue.py:_cleanup_job` is now the single point of cleanup at retention expiry. (resolved 2026-05-19)** This is the only sustainable resolution to the download-then-cleanup conflict flagged in document review; "first action wins" UX (greying out Send-to-Kindle after download) was rejected as punitive. Implementer note: existing `download.py:106-112` behavior is now scoped to the *expired-cleanup* path only, not the *post-download* path.
- **Re-convert uses a "stay in place" page model with child jobs. (resolved 2026-05-19)** Clicking "Convert to MOBI" or "Convert to KFX" creates a child job linked to the parent in the job store; the result page stays at `/status/{original_job_id}` and the action cluster updates as each child completes (spinner → Download button per format). `GET /status/{job_id}` is extended to return a `children` array with each child's `job_id`, format, and status. Redirecting per re-convert was rejected because it fragments the "this upload" mental model. Single in-flight re-convert at a time is acceptable for v1; concurrent re-converts can be added later if telemetry shows the need.
- **Send-to-Kindle state contract on the result page. (resolved 2026-05-19, success copy updated by R3.5)** Idle: email input + Send button, with the chosen From address and approved-sender hint per R3.5. Sending: button disabled with copy "Sending…". Success (Resend returns a 2xx ack with a message ID — equivalent across the SDK and SMTP paths): form collapses to inline confirmation along the lines of "Sent to *you@kindle.com*. Arrives within a few minutes **if** `kindle@send.leafbind.io` is on your approved-sender list. [Verify →] **Send again →**" — exact wording governed by R3.5. Clicking "Send again" restores the form pre-filled. Failure with known Kindle fingerprint (e999, auth) — if available via Resend bounce webhook: inline error copy that surfaces the approved-sender check FIRST per R3.5, then the link to EB-322 troubleshooting. Failure with generic transport fingerprint (Resend 5xx, network error, timeout): inline error copy + Retry button, address pre-filled, **no** EB-322 link (EB-322 is about Kindle-side configuration, not server-side transient failures). Duplicate-send guard: Send button stays disabled between submit and response.
- **Send-to-Kindle is a free-tier feature, with KFX as the upsell. (resolved 2026-05-19)** Per the brainstorm's own framing — the moment the user has tasted the free output is the moment they best understand the premium tier — Send-to-Kindle is the wow-moment that drives word-of-mouth; the KFX re-convert is the credit-purchase pitch sitting right next to it. Abuse surface is mitigated by R3.1 (recipient-domain allowlist) + R13 (rate-limit), not by gating the feature itself.
- **Kindle email persists in `localStorage` with a 'Forget this address' affordance. (resolved 2026-05-19)** Matches the consumer Send-to-Kindle norm (Calibre, kindle.amazon.com itself) so repeat users don't retype. The "Forget" affordance preserves the no-accounts voice. The address is never persisted server-side beyond the active request — it appears in Resend's message log (audit surface), but not in our database, not in our application logs, and not in telemetry payloads.
- **TTL countdown is shown on the result page with coarse labels, not a live ticker. (resolved 2026-05-19)** Display "Session expires in about an hour" / "less than 10 minutes left" rather than a live counter. Hides on the result page after the user has taken any action that "consumes" the session intent (a Download or a successful Send-to-Kindle); stays visible until then. Disappears entirely after TTL elapses — replaced by the expired-state copy from R4.
- **R6 (failure-state "try a different format") is deferred entirely. (resolved 2026-05-19)** Adversarial review correctly flagged that most pipeline failures in this codebase are source-specific (extraction, OCR, structure analysis) — offering a "try MOBI" button on a failed PDF would predictably fail again, and would be especially harmful if a premium credit gets consumed on the retry. Failure-state UX deserves its own brainstorm + ticket once we have failure-mode telemetry to inform what "next action" is actually useful. R6 is removed from EB-324 entirely (not deferred to Wave 2).
- **Wave 2 kill-criterion threshold: ≥15% of `done`-state result-page visits trigger at least one new action (Send-to-Kindle attempt OR re-convert attempt), sustained across weeks 3 and 4 of a four-week post-launch window. (resolved 2026-05-19)** If either week 3 or week 4 falls below 15% engagement, Wave 2 is not auto-shipped — the action cluster is reassessed (cancel, redesign, or extend the measurement window with a stated reason). This converts the "non-trivial use" success criterion from unfalsifiable to operational.
- **Wave 2 ships as a sibling ticket, not under EB-324. (resolved 2026-05-19)** EB-324 closes when Wave 1 (R1–R5 + R11 + R12 + R13 + R3.1/R3.2 + R4.1) ships and the four-week telemetry window completes. If the kill-criterion threshold is met, a new ticket (EB-324b or successor) is opened against R7–R10. This prevents the original ticket from staying open indefinitely awaiting a Wave 2 that telemetry may invalidate, and respects the doc's own kill-criterion language.
- **Credit-refund policy: re-convert and multi-format partial-failures refund atomically. (resolved 2026-05-19)** When a re-convert (R2) or a Wave 2 multi-format job (R9) results in any premium output that fails to produce, the corresponding credits are refunded back to the user's token bag. This overrides the current single-format `convert` "no refund on failure" policy (`web_service/routes/convert.py:33`) for the re-convert and multi-format paths specifically, because the user did not re-upload — the source has already been validated and accepted, so a failure on our side is *our* failure, not a user-error. Implementation requires a `token_store` refund operation (currently consume is single-use atomic; refund is the inverse). Original single-format `convert` no-refund policy stays as-is.
- **Wave 1 ships R1–R5 + R11 + R12 + R13 plus sub-requirements R2.1–R2.7, R3.1–R3.5, R4.1. Wave 2 ships R7–R10.** R6 is removed (see prior decision); not in any wave. Each wave is independently demoable and shippable.

## Dependencies / Assumptions

- **Verified:** Source files remain on disk in `temp_dir/input.<ext>` for `job_ttl_free` (1 h) or `job_ttl_premium` (24 h) before `_cleanup_job` removes the directory (`web_service/job_queue.py:156-163`).
- **Verified:** A FormatSelector already exists at `web_service/frontend/components/FormatSelector.tsx` covering EPUB/MOBI/KFX with premium gating — R11 builds on it, doesn't replace it.
- **Verified:** Send-to-Kindle has no frontend implementation today — confirmed by grepping `web_service/` for `kindle_email|send.to.kindle|sendToKindle`, which returned only marketing/guide content. Wave 1 introduces the first frontend handle.
- **Decided** (resolved during document review, 2026-05-19): Send-to-Kindle goes through **Resend** — already authenticated and DKIM-aligned for `leafbind.io` per `docs/solutions/best-practices/leafbind-email-auth-stack-2026-05-16.md`, and already in production for support/contact mail. The `EbookAutomation.psm1` `Send-MailMessage` path is a Windows-only PowerShell helper and cannot run on the Linux Hetzner VM, so it is explicitly NOT in scope. Choice of Resend Python SDK vs `smtplib` pointed at `smtp.resend.com` is a planning-time implementation call; the SMTP credential lives in an environment variable on the VM, scoped to a Resend restricted API key. The From-address must be on Amazon's pre-approved senders list a user adds to their Kindle Personal Document Email approval list — chosen address is a planning-time call (likely `kindle@send.leafbind.io`).
- **Assumed:** EB-237 (large-PDF timeout policy) lands or stays static. Wave 2 multi-format conversion compounds compute time; if the timeout window is still 120 s after Wave 2 design begins, the multi-format checkbox needs additional product framing.

## Visual aid

```
   ┌─────────────────────────────────────────────────────────────┐
   │  CURRENT STATE — result page (status/[id])                  │
   │                                                             │
   │  Status: Done!                                              │
   │  [ Download converted file ]                                │
   │                                                             │
   │  ← Convert another file                                     │
   └─────────────────────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────────────────────┐
   │  WAVE 1 — result page (status/[parent_job_id])              │
   │                                                             │
   │  Status: Done!                                              │
   │                                                             │
   │  ─── Your formats ──────────────────────────────────────    │
   │   EPUB    [ Download ]  [ Send to Kindle ]                  │
   │   MOBI    [ Convert ]  (free)        ← no Kindle email      │
   │                                        button: Amazon       │
   │                                        dropped MOBI in 2022 │
   │   KFX     [ Convert — paste token ]  (1 credit)             │
   │           sideload via USB/Calibre   ← no Kindle email      │
   │                                        button: KFX is not   │
   │                                        accepted via email   │
   │                                                             │
   │  After clicking "Send to Kindle" on the EPUB row:           │
   │     Sending from: kindle@send.leafbind.io                   │
   │     First time? Add this address to Amazon Personal         │
   │     Document Settings → Approved Personal Document          │
   │     Email List, or Amazon will reject. [How →]              │
   │                                                             │
   │     Email:  [ you@kindle.com         ]  [ Send ]            │
   │                                                             │
   │   ✓ Sent to you@kindle.com — arrives within a few           │
   │     minutes IF kindle@send.leafbind.io is on your           │
   │     approved-sender list.  [Verify →]   Send again →        │
   │                                                             │
   │   Session expires in about an hour                          │
   │                                                             │
   │  ← Convert another file                                     │
   └─────────────────────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────────────────────┐
   │  WAVE 2 — upload form (homepage)                            │
   │                                                             │
   │  [ Drop your PDF here ]                                     │
   │                                                             │
   │  Output formats:                                            │
   │   ☑ EPUB    ☐ MOBI    ☐ KFX (premium)                       │
   │                                                             │
   │   Free tier: pick up to 2.  Premium: as many as credits.    │
   └─────────────────────────────────────────────────────────────┘
```

## Outstanding Questions

### Resolve Before Planning

*(Empty — all original user-decision items and all three promoted items were resolved during document review on 2026-05-19. See Key Decisions for the recorded resolutions.)*

### Deferred to Planning

- **[Affects R2.1, R2.3][Technical]** Re-convert route shape — a new `POST /reconvert/{parent_job_id}` route vs reusing `POST /convert` with a `source_job_id` parameter. The product model (stay-in-place + child-jobs) is fixed; this is route-shape + validation-reuse only.
- **[Affects R2.4][Technical]** Source-copy at dispatch vs source-pinning with deferred cleanup. R2.4 records both options; planning picks one and writes the integration test (R2.5) against the chosen strategy. Recommended default = source-copy.
- **[Affects R2.7][Technical]** Refund-ledger schema and the `token_store` reverse-consume operation. Open sub-questions: storage of `refund_ledger` (new table vs reuse `failed_mints` pattern), whether refunds emit a Stripe-side note, and whether re-enable resets the original purchase-expiry window or honors it.
- **[Affects R3][Technical]** Resend integration shape: official `resend` Python SDK vs Python `smtplib`/`aiosmtplib` pointed at `smtp.resend.com`. SDK simplifies attachment-MIME assembly, bounce-webhook hookup, and From-domain alignment checks; SMTP minimizes new dependencies. The Resend dashboard's message log will be the audit surface for delivery — note that the recipient address is therefore visible in Resend even with no app-level persistence, which is a privacy-page consequence to call out in copy.
- **[Affects R3.4][Technical]** Idempotency-cache implementation for Send-to-Kindle — in-memory dict with TTL eviction (fastest, lost on restart) vs SQLite table (durable across restarts, slightly slower). 60-second window is small enough that in-memory loss on restart is acceptable; recommended default = in-memory with a tuple → epoch dict.
- **[Affects R13][Technical]** Cloudflare Free-plan WAF rule budget verification before deployment. Confirm current rule count on the leafbind.io zone; decide combined-rule vs Pro-upgrade vs accept-as-defense-in-depth-only. App-level throttle is the load-bearing layer regardless.
- **[Affects R10][Needs research]** Compute cost of Wave 2 multi-format (e.g., EPUB+MOBI in one job) on the Hetzner VM under realistic file-size distribution. Should ride into the EB-237 timeout-policy ticket's measurement work rather than be done independently.
- **[Affects R12][Technical]** Telemetry sink for the four event types — Plausible (current analytics provider) supports custom events but not high-volume per-job event streams; might need a lightweight server-side log or a separate event bus depending on the metric we ultimately care about.

## Alternatives Considered

- **Approach 1 — Lazy re-convert only (no Wave 2).** Smallest scope. Rejected as the primary path because it leaves the original "silent format pick" complaint (R11) unaddressed and offers no upgrade path for users who already know they want both formats.
- **Approach 2 — Multi-format-on-upload only (no Wave 1 action cluster).** Eliminates the "convert to another" decision tree at the source, but doubles compute per upload and ignores Send-to-Kindle, which is the highest-leverage user request in the original ticket text.
- **Retention-as-product challenger (30-day premium retention).** Worth filing as a sibling ticket only if Wave 1 telemetry shows users hitting the 24 h TTL wall on the re-convert action. Carries a meaningful brand-promise rewrite and storage-cost model — too big to fold into EB-324.

## Next Steps

→ `/ce:plan` for structured implementation planning. All user-decisions have been resolved; remaining open items in *Deferred to Planning* are technical/research questions appropriate for the planning step to address.
