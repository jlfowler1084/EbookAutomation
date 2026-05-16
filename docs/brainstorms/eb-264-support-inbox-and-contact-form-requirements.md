---
date: 2026-05-15
topic: eb-264-support-inbox-and-contact-form
---

# EB-264 — Support Inbox + On-Site Contact Form for leafbind.io

## Problem Frame

leafbind.io has no public way for users to reach support. The `components/Footer.tsx` exposes Convert / Account / brand links but nothing for help. The product's own `public/llms.txt` (the page AI assistants are most likely to cite when summarizing leafbind) states *"Contact: via the conversion result page"* — but `app/(app)/status/[id]/page.tsx` has no contact UI. The promise has no implementation behind it, which is both a trust signal failure for AI-mediated discovery (AI assistants telling users a contact path that doesn't exist) and a direct user experience failure (people who hit friction during conversion have no escape hatch and abandon).

Two adjacent users are affected and currently un-served:
- **Pre-purchase users** browsing `/pricing`, `/convert/*`, or the pillar guide who have a capability question, a billing question, or general feedback before they commit
- **Post-conversion users** on `/status/[id]` (success or failure) who want help with a specific conversion, want to report a quality issue, or want to flag a corner case

v1 (this ticket) addresses the first audience with a clean marketing-site contact surface. The second audience is explicitly deferred to v2 (a contextual entry point on `/status/[id]` that pre-fills conversion context) and v3 (`/recover` entry point). v1 must be built so v2 reuses the same form backend without rework.

## Requirements

**Inbox Plumbing**

- R1. `support@leafbind.io` exists and forwards to `jlfowler1084@gmail.com` via Cloudflare Email Routing on the existing `leafbind.io` zone.
- R2. **Outbound reply path:** Gmail is configured with a "Send mail as `support@leafbind.io`" alias whose SMTP relay credentials point at the chosen transactional provider (Resend or Postmark). The leafbind.io zone has `support@leafbind.io` verified as a sending identity at the provider; the provider publishes its DKIM selector record at `leafbind.io` and we set a matching SPF record (`v=spf1 include:<provider> -all`). Net effect: every outbound message (both the R11 auto-acknowledgment and any human reply the operator composes in Gmail) leaves authenticated as `support@leafbind.io`, passes SPF + DKIM aligned to `leafbind.io`, and never exposes the operator's personal `@gmail.com` address. Authentication is verified end-to-end with mail-tester.com (or equivalent) score ≥ 9/10 against both the auto-ack path and a manual Gmail-composed reply.
- R3. DMARC starts in monitor mode (`p=none`) with a reporting address so the user can observe authentication results for ~30 days before deciding whether to upgrade to `p=quarantine`. The 30-day review is captured as a separate follow-up task, not in this ticket.

**Contact Page & Form**

- R4. A new page exists at `/contact` (route: `app/(marketing)/contact/page.tsx`) reachable from a new **Support** column in the global marketing footer.
- R5. The contact form captures these fields:
    - Name (optional, free text, maximum 200 characters)
    - Email (required, validated as a syntactically valid email)
    - Topic (required, single-select native `<select>` dropdown: *General* / *Conversion issue* / *Billing* / *Other*)
    - Message (required, minimum 20 characters, maximum 5,000 characters)
    - A hidden honeypot field and a hidden Turnstile token (anti-spam controls, see R9)
- R6. Form helper text guides users with conversion-specific issues: *"For issues with a specific PDF, please include the conversion ID from your result page in your message. Direct file attachments are coming in a future update."* This sets expectations for the v2 result-page flow.
- R7. The form blocks submission until required fields validate, with inline error messages that name the specific failure (e.g., *"Please enter a valid email address"*, *"Message must be at least 20 characters"*). Validation triggers on field blur per-field, plus a full-form pass on the first submit attempt so tab-skipped fields are caught. The submit button is labeled **"Send message"** at rest, **"Sending…"** while in flight (button disabled), and stays **"Send message"** (just inactive) when required fields are incomplete — no alarming label changes. Pattern matches the existing `RecoverClient` *Recover → Recovering…* convention.
- R8. On successful submission the form shows an inline success state on the same page (no full redirect, no toast-only confirmation), echoing the submitted message text back to the user so they have visual confirmation it sent. The success container uses `tabIndex=-1`, `role="status"`, and `aria-live="polite"`; on submit success, focus moves to the container so keyboard and screen-reader users receive an immediate confirmation. The echoed message text is the value already held in React state — never reflected from the Worker response (to avoid an XSS vector); messages longer than 300 characters are truncated in the echo with a "show full" affordance. On failure the form shows an inline error specific to the failure mode, preserving the user's already-typed content. Four named failure cases with distinct copy:
    - Network timeout / unreachable Worker: *"Something went wrong. Your message is still here — try again."*
    - Rate-limit 429: *"You've sent several messages recently. Please wait a few minutes before trying again."*
    - Turnstile token expired (long compose session): *"Verification timed out — refresh the page. Your message text will be preserved."*
    - Turnstile widget failed to load (blocked by client filter / network): *"Verification couldn't load. Please email support@leafbind.io directly."*
    
    Additionally, the form auto-saves its current draft (name / email / topic / message) to `sessionStorage` on every submit attempt and on page-visibility-change; on page reload, the draft is restored so a failed submit followed by F5 does not lose typed content.

**Anti-Spam & Submission Path**

- R9. The form is protected by (a) Cloudflare Turnstile in managed mode, validated server-side before the submission is accepted, and (b) a hidden honeypot field. If the honeypot is filled, the submission is silently dropped server-side AND the response renders the **exact same success UI** as a legitimate submission — including the echoed message text from R8. Bots gain no oracle (they already have their own input); real users get unambiguous confirmation. The Turnstile secret key is stored exclusively via `wrangler secret put TURNSTILE_SECRET_KEY` (Cloudflare Workers encrypted secret); the site key is the only Turnstile value embedded client-side.
- R10. Form submissions POST to a Cloudflare Worker endpoint at a custom route on `leafbind.io` (e.g., `/api/contact`) that:
    - Returns `Content-Type: application/json` and sets `Access-Control-Allow-Origin: https://leafbind.io` on every response. The response body is a structured status only (e.g., `{ok: true}`) — it never reflects user-supplied content back to the client.
    - Validates the Turnstile token server-side via Cloudflare's siteverify endpoint. If siteverify is unreachable, fails closed and returns 502.
    - Enforces dual rate-limiting in Cloudflare KV: (a) **per-IP** at 5 submissions/hour, keyed on `CF-Connecting-IP` with IPv6 bucketed to the /64 prefix; (b) **per-submitted-email-address** at 3 submissions per 24 hours, keyed on `sha256(normalized_email)`. Either limit gates the submission. On 429, returns a structured error with a hint to retry after the bucket rolls.
    - Caps input length server-side before any provider call: Message ≤ 5,000 chars, Name ≤ 200 chars. Over-cap requests return 413.
    - Sanitizes user-supplied fields before embedding in the outbound email: strips HTML, entity-encodes any remaining markup, validates the email field is a single RFC 5321 address with no CRLF, and uses the transactional provider's SDK (not raw SMTP string construction) so headers cannot be injected. The forwarded email is **plain-text only** — never HTML.
    - Forwards the sanitized message to `support@leafbind.io` via the chosen transactional email provider (Resend or Postmark — choice deferred to planning).
    - Handles failure modes: transactional provider 5xx → one retry with jitter, then 502 to client; auto-reply send failure (R11) is logged Worker-side but does not block the success response to the user (the user-facing UI is gated on the support-bound email, not the courtesy auto-reply).
    - All secrets (transactional provider API key, Turnstile secret, any KV-write tokens) are stored exclusively via `wrangler secret put` (Cloudflare Workers encrypted secrets) — never as plaintext environment variables and never committed to source.

    The Worker is chosen over a Next.js server action because Turnstile validation and the SMTP send both happen at the Cloudflare edge with no Vercel execution-time cost.

**Auto-Acknowledgment**

- R11. Within ~1 minute of a successful submission, the user receives a plain-text auto-reply at the email they submitted: *"Thanks — we've received your message and will reply within 1 business day. — leafbind support."* The auto-reply is sent from `support@leafbind.io` and passes SPF/DKIM checks. It does not include any tracking pixels. The Worker enforces a per-recipient auto-ack throttle of 1 message per recipient email address per 24 hours (separate KV namespace from the submission rate-limit) to prevent the form being used as an email-relay amplifier against attacker-supplied addresses.

**Information Architecture, Footer, SEO**

- R12. The marketing footer (`components/Footer.tsx`) gains a fourth column titled **Support**, containing `/contact` and `/recover` links. The existing "Recover tokens" link is moved out of the Account column into Support (it is a support flow, not an account flow — leafbind has no user accounts as of 2026-05).
- R13. `/contact` is added to `app/sitemap.ts` at priority 0.5, `changeFrequency: yearly`. It is added to `app/robots.ts` as crawl-allowed by default (no special directive needed — falls under the existing `allow: "/"` rule).
- R14. `/contact` emits `ContactPage` JSON-LD structured data (via the existing `JsonLd` component) validated clean in the Google Rich Results Test.

**Privacy Posture**

- R15. The contact flow sets no cookies (other than what Cloudflare Turnstile inherently requires for bot detection). No IP capture beyond what Cloudflare logs natively at the edge and the transient rate-limit state in Cloudflare KV (which stores `CF-Connecting-IP` and `sha256(normalized_email)` for the per-IP and per-recipient throttles described in R10/R11, expiring at the bucket TTL). A privacy line directly under the form reads: *"We only use your email to reply to you. We do not share or sell your information."*

**AI-Mediated Discovery**

- R16. `web_service/frontend/public/llms.txt` is updated to replace the existing line *"Contact: via the conversion result page (no public contact form on the marketing site as of 2026-05)"* with *"Contact: https://leafbind.io/contact"*. Required to make the success criterion about AI-mediated discovery true.

## Success Criteria

- A user landing on any marketing page can reach a working contact form in one click via the footer.
- A submitted message from a real user (test with own personal account) arrives in `jlfowler1084@gmail.com` within 2 minutes, displays correctly, and a reply from Gmail back to the user's email lands in their inbox (not spam).
- A spam submission attempt (no Turnstile token, or honeypot filled) is rejected with no email delivered to `support@leafbind.io` and no error surfaced to the would-be spammer.
- The `llms.txt` line about contact is updated to point to `/contact` so AI-mediated discovery describes a path that actually exists.
- mail-tester.com (or equivalent) score ≥ 9/10 for outbound `support@leafbind.io` mail.
- Google Rich Results Test reports zero errors and zero warnings for `/contact`.
- **Visibility outcome:** Within 30 days of launch, at least **5 inbound messages from non-test users** arrive at `support@leafbind.io`. Zero real inbound is the signal that the form is invisible (not that demand is absent) — re-evaluate footer placement and `/contact` page copy before deferring further.
- **v2 prioritization trigger:** Within 30 days, at least **1 inbound message mentions a conversion ID** (signaling a post-conversion user found their way through the marketing footer). If zero post-conversion-context inbound, that is the explicit trigger to prioritize v2 (contextual entry on `/status/[id]`) within the following 60 days.

## Scope Boundaries

v1 explicitly does **not** include:

- File attachments of any kind (image or PDF). Helper text sets expectations; v2 result-page flow will solve the "attach a failing PDF" case using conversion context.
- A contextual support entry point on `/status/[id]` (deferred to v2).
- A contextual support entry point on `/recover` (deferred to v3).
- Any ticketing system, threading, tagging, or status tracking. Replies happen out of the user's Gmail inbox as plain email.
- Auto-categorization, AI triage, or canned responses.
- A bounded retrieval support chatbot. That is captured as a separate future ticket, conditional on email volume justifying it.
- Multi-language support. Form copy is English-only.
- Analytics event tracking on the form (captured separately under EB-265 Phase 2).

**Volume trigger for ticketing:** If sustained inbound exceeds ~20 messages/week, revisit ticketing / threading / tagging and consider migrating to a help desk product (e.g., HelpScout, Front, Plain). Until then, the operator's Gmail inbox is the queue.

## Key Decisions

- **Marketing footer + `/contact` only for v1 (not multi-entry-point).** Rationale: simplest scope that closes the visible gap, defers context-rich entry points to v2 where they can be designed properly around conversion ID and file re-upload. The user explicitly elected to revisit v2/v3 later. Captured in Future Scope above.
- **No file attachments in v1.** Rationale: Cloudflare Email Routing has a silent ~25 MB per-message ceiling that can blackhole large attachments; storage backend (R2 + signed URLs) adds non-trivial scope; most pre-purchase support emails do not need attachments. v2 result-page flow will solve the attachment case via conversion ID, which is a strictly better UX (no re-upload needed).
- **Cloudflare Worker over Next.js server action for the submit handler.** Rationale: Turnstile validation runs at the same Cloudflare edge that issued the token (lower latency, no internal network hop); Cloudflare Workers free tier covers expected volume with margin; preserves Vercel execution-time budget for genuine app work; the form backend has zero coupling to the Next.js render tree.
- **Auto-acknowledgment email is sent.** Rationale: a silent inbox after a submission is the most common reason users re-send. The cost (one extra outbound email per submission) is trivial; the trust benefit is substantial. Auto-reply is deliberately plain-text and short to avoid looking like phishing.
- **DMARC starts at `p=none` (monitor mode), not `p=quarantine`.** Rationale: a misconfigured DMARC at `p=quarantine` or `p=reject` can break outbound Gmail forwards silently. Monitor mode catches misconfigurations cheaply; the upgrade decision is informed by 30 days of real reporting data, not a guess.
- **Inline success state, not redirect.** Rationale: a redirect to `/contact/success` would be a separate indexable page with no SEO or product value, and the back-button UX from a success page is awkward (users hit Back and re-see the form, which feels like the submission was lost).
- **"Recover tokens" moves to Support column.** Rationale: leafbind has no user accounts. The Recover flow is a support pathway that happens to use a token, not an account-management surface. Putting it next to `/contact` makes the IA honest and improves discoverability for users who lost their download link.

## Dependencies / Assumptions

- The `leafbind.io` zone in Cloudflare (zone id `20967fb38b4e1feb6dfc01e4407d7225`) is reachable via the existing Cloudflare MCP integration. *Verified during this brainstorm via Cloudflare API.*
- Cloudflare Email Routing is provisionable on the zone (free Cloudflare feature, no additional billing). *Verified 2026-05-15 via Cloudflare API: `routing_status.enabled = false`, `status = "unconfigured"` — feature is available but not yet enabled. Enabling it is part of R1 scope, not a prerequisite.*
- The `support@leafbind.io` address does not currently exist. *Verified — no MX records direct to it in DNS scan during this brainstorm.*
- Vercel deploys from the `master` branch (productionBranch fix per EB-257). *Verified via prior session memory.*
- A transactional email provider (Resend, Postmark, or Cloudflare's own Email Workers SMTP) is available. **Choice deferred to planning.**

## Outstanding Questions

### Resolve Before Planning

*All P1 product-level blockers surfaced by the 7-persona document-review (2026-05-15) have been resolved in the body above. See "Deferred to Planning" for items that remain open but are technical/research questions for the planner, not product decisions blocking planning.*

### Deferred to Planning

- [Affects R10][Technical] Choice of transactional email provider: Resend (most modern, free tier 3K/mo, simplest DX), Postmark (highest deliverability reputation, $15/mo above free), or Cloudflare's own Email Workers SMTP (no extra vendor, but newer and less battle-tested). Pick during planning based on Worker integration complexity and free-tier headroom.
- [Affects R9][Technical] Rate-limit storage backend in the Worker: Cloudflare KV (eventually consistent, free tier ample) vs. Durable Objects (strongly consistent, more accurate, slightly higher cost). Likely KV is sufficient for expected volume; confirm during planning.
- [Affects R8][Needs research] Whether to write the success-state echo as an aria-live region for screen readers vs. relying on focus management. Accessibility detail best decided when implementing the component, not in requirements.
- [Affects R2, R3][Needs research] Exact SPF / DKIM / DMARC TXT record syntax for a Cloudflare Email Routing + Gmail-as-reply-sender setup. Cloudflare publishes guidance; planning should fetch and validate against current docs.
- [Affects R12][Technical] Whether moving "Recover tokens" out of the Account column requires removing the Account column entirely (only Pricing and Quality would remain — those fit Convert or a new "Product" column).

## Next Steps

-> `/ce:plan` for structured implementation planning.
