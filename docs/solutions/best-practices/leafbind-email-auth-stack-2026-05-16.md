---
ticket: EB-264
date: 2026-05-16
author: Joe Fowler
tags: [email, dns, cloudflare-email-routing, resend, dkim, spf, dmarc, srs, thunderbird, leafbind]
module: cloudflare/email-routing,external-resend,thunderbird-client
problem_type: integration-architecture
related:
  - EB-264 (parent ticket — support inbox + on-site contact form)
  - EB-45 (Leafbind freemium web service — parent epic)
  - DMARC quarantine upgrade follow-up ticket (created 2026-05-16, due 2026-06-15, links here)
---

# Leafbind email auth stack — Cloudflare Email Routing in + Resend out, DKIM-aligned both ways

Captures the architecture and surprising behavior of the `leafbind.io` email stack so future-you (or another engineer) can debug it without reverse-engineering Cloudflare/Resend internals from headers.

## The four-component picture

```
Inbound:  Sender → leafbind.io MX → Cloudflare Email Routing → forward → jlfowler1084@gmail.com
                                          ↓
                                    (SRS rewrite)
                                    (CF-added DKIM as d=leafbind.io)
                                    (ARC seal of original auth)

Outbound: Thunderbird (Gmail account + leafbind identity)
            → smtp.resend.com:465 (auth: user "resend", password = Resend API key)
            → Resend (signs DKIM as s=resend; d=leafbind.io)
            → Amazon SES outbound IPs
            → Recipient

DNS:      leafbind.io zone in Cloudflare
            MX → route{1,2,3}.mx.cloudflare.net (Email Routing)
            apex SPF: v=spf1 include:_spf.mx.cloudflare.net ~all   (NOT replaced — see divergence)
            apex DMARC: v=DMARC1; p=none; rua=mailto:dmarc-reports@leafbind.io; pct=100
            send.leafbind.io MX → feedback-smtp.us-east-1.amazonses.com  (Resend's bounce subdomain)
            send.leafbind.io SPF: v=spf1 include:amazonses.com ~all
            resend._domainkey.leafbind.io TXT (Resend's DKIM public key)
            cf2024-1._domainkey.leafbind.io TXT (Cloudflare's DKIM public key for forwarded mail)
```

Two DKIM key publishers (Resend and Cloudflare) sign mail with `d=leafbind.io` using different selectors. Both are legitimate authorizations and both are required — Resend signs outbound (`s=resend`), Cloudflare signs forwarded inbound (`s=cf2024-1`).

## Architecture decisions and rationale

### Decision 1: Thunderbird = Gmail account + leafbind identity (not standalone leafbind account)

`support@leafbind.io` lives as a **secondary identity** inside the `jlfowler1084@gmail.com` Thunderbird account, with the leafbind identity bound to a dedicated Resend SMTP outgoing server.

**Why:** Cloudflare Email Routing forwards inbound `support@leafbind.io` mail to `jlfowler1084@gmail.com` — it is NOT a mailbox host. There is no IMAP server at leafbind.io. So a standalone Thunderbird account for `support@leafbind.io` would either need imap.gmail.com under the hood (duplicate view of the same mailbox) or it would simply never connect. The identity pattern lets one IMAP login carry multiple From-personas, with Thunderbird picking the right SMTP per identity at compose time.

**Wrong setup that we cleaned up on 2026-05-16:** Initial setup had `support@leafbind.io` as a separate account with a placeholder SMTP entry (`leafbind.io:587, no security, no auth method`) that Thunderbird's autoconfig wizard generated when it failed to find a real SMTP server at the leafbind.io domain. That config would never have sent mail. The fix: delete the standalone account, delete the bogus SMTP entry, add the leafbind identity under Gmail, point its outbound at the real `smtp.resend.com` entry.

### Decision 2: Two DKIM selectors at `*._domainkey.leafbind.io`

Both `resend._domainkey.leafbind.io` (added during Resend domain verification) and `cf2024-1._domainkey.leafbind.io` (added automatically by Cloudflare Email Routing) are required. Removing either breaks one direction of the stack:

- Remove `resend._domainkey` → outbound from `support@leafbind.io` fails DKIM at the recipient. DMARC may quarantine/reject after the 30-day p=none → p=quarantine upgrade.
- Remove `cf2024-1._domainkey` → forwarded mail from Cloudflare loses one of its three DKIM signatures (the leafbind-aligned one). The original sender's DKIM still passes and ARC chain still validates, but the `leafbind.io` alignment is lost. Risk: receiver-side reputation algorithms (Gmail, especially) may de-prioritize forwarded mail.

Both keys live in Cloudflare DNS — DO NOT prune "unused-looking" DKIM TXT records during DNS housekeeping.

### Decision 3: apex SPF NOT replaced (divergence from EB-264 plan)

**Current apex SPF:** `v=spf1 include:_spf.mx.cloudflare.net ~all`
**Plan called for:** `v=spf1 include:_spf.mx.cloudflare.net include:<resend-spf-token> -all` (replace-in-place during Unit 2)

The plan's spec was a belt-and-suspenders measure. Why the current state is fine:

- Resend's outbound MAIL FROM is `<bounce-id>@send.leafbind.io` (a subdomain, not the apex). The `send.leafbind.io` record has its own SPF (`v=spf1 include:amazonses.com ~all`), authorizing AWS SES IPs.
- DMARC alignment uses relaxed mode by default — the org domain (`leafbind.io`) matches on both From and MAIL FROM. ✓
- Apex SPF only matters for mail with MAIL FROM `<anything>@leafbind.io` exactly. Resend never does this.

**When to revisit:** if Resend's outbound architecture changes (e.g., bare `leafbind.io` MAIL FROM) OR if we add a second sending provider that uses the apex, replace-in-place per the original plan.

**Why `~all` not `-all`:** soft-fail is more forgiving during DMARC monitor mode. Tighten to `-all` when DMARC moves from `p=none` to `p=quarantine` (target: 2026-06-15).

## Cloudflare Email Routing is an active re-authenticator, not a dumb forwarder

This is the single most counterintuitive piece of the stack. When mail forwards through Cloudflare, three things happen:

### 1. SRS (Sender Rewriting Scheme) rewrite

The Return-Path becomes `SRS0=<hash>=<short>=<originaldomain>=<localpart>@leafbind.io`. Example from a 2026-05-16 inbound test (hotmail → support@leafbind.io → Gmail):

```
Return-Path: <SRS0=r6Ch=nd=hotmail.com=joefowler13@leafbind.io>
```

**Why this matters:** the next-hop SPF check (at Gmail) would fail if Return-Path still said `joefowler13@hotmail.com` — Cloudflare's forwarding IPs aren't in hotmail's SPF. By rewriting Return-Path to a leafbind.io address, Cloudflare ensures `leafbind.io`'s own SPF authorizes its forwarding IPs (`include:_spf.mx.cloudflare.net`).

### 2. Cloudflare adds its own DKIM signature with `d=leafbind.io`

The forwarded message at Gmail has THREE DKIM signatures (from the same 2026-05-16 inbound test):

```
dkim=pass header.i=@hotmail.com           header.s=selector1   header.b=NujUsRz2  (original)
dkim=pass header.i=@leafbind.io           header.s=cf2024-1    header.b=gjfx1HUB  (CF-added, leafbind-aligned)
dkim=pass header.i=@cloudflare-email.net  header.s=cf2024-1    header.b=Va7dcAx0  (CF service)
```

The middle one is the most important — it gives the forwarded message a DKIM signature aligned with the org domain of the visible From header, which improves trust scoring at the recipient.

### 3. ARC chain preserves original auth

Cloudflare adds `ARC-Seal:`, `ARC-Message-Signature:`, `ARC-Authentication-Results:` headers. Gmail records `arc=pass (i=2 spf=pass spfdomain=hotmail.com dkim=pass dkdomain=hotmail.com dmarc=pass fromdomain=hotmail.com)` — Gmail trusts Cloudflare's ARC seal, which carries forward the original hotmail.com auth even though the wire-level auth on the second hop is leafbind-based.

This is why forwarded `support@leafbind.io` mail doesn't get spam-foldered at Gmail even when the original sender's SPF wouldn't have validated against Cloudflare's IPs.

## Verified outbound auth (2026-05-16)

Outbound from `support@leafbind.io` via Thunderbird → Resend → joefowler13@hotmail.com. Headers from the received `.msg` at hotmail:

```
Authentication-Results:
  spf=pass    (sender IP 54.240.9.68)  smtp.mailfrom=send.leafbind.io
  dkim=pass   (signature verified)     header.d=leafbind.io
  dkim=pass   (signature verified)     header.d=amazonses.com
  dmarc=pass  action=none               header.from=leafbind.io
  compauth=pass reason=100

Return-Path: <01000...@send.leafbind.io>
DKIM-Signature: v=1; a=rsa-sha256; s=resend; d=leafbind.io; ...
Received: from a9-68.smtp-out.amazonses.com (54.240.9.68)
```

Things to notice:
- The `Authentication-Results` has TWO `dkim=pass` lines. One for `d=leafbind.io` (Resend signing as leafbind, load-bearing for DMARC alignment), one for `d=amazonses.com` (AWS SES signing as itself — Resend rides on SES under the hood). Both are passing; only the leafbind one matters for DMARC.
- `Return-Path: @send.leafbind.io` — bounces never expose `jlfowler1084@gmail.com`.
- `compauth=pass reason=100` — Microsoft's composite score is 100/100.

## Verified inbound auth (2026-05-16)

Inbound joefowler13@hotmail.com → support@leafbind.io → jlfowler1084@gmail.com. Headers as seen at Gmail:

```
Cloudflare receiving leg (mx.cloudflare.net):
  dkim=pass    header.d=hotmail.com
  spf=pass     smtp.mailfrom=joefowler13@hotmail.com
  dmarc=pass   header.from=hotmail.com policy.dmarc=none

Cloudflare forwarding to Gmail leg (mx.google.com):
  dkim=pass    header.i=@hotmail.com
  dkim=pass    header.i=@leafbind.io           s=cf2024-1
  dkim=pass    header.i=@cloudflare-email.net  s=cf2024-1
  spf=pass     smtp.mailfrom=SRS0=...@leafbind.io   (via SRS rewrite)
  dmarc=pass   via arc=pass (i=2)

X-Forwarded-To: jlfowler1084@gmail.com
X-Forwarded-For: support@leafbind.io jlfowler1084@gmail.com
```

The `X-Forwarded-For` line is the canonical proof the forwarding chain matches the design: `support@leafbind.io → jlfowler1084@gmail.com`.

## DMARC progression plan

Current: `p=none; pct=100; rua=mailto:dmarc-reports@leafbind.io`. Aggregate reports flow to `dmarc-reports@leafbind.io`, which Cloudflare Email Routing forwards to `jlfowler1084@gmail.com`.

Target upgrade: `p=quarantine` after 30 days of monitor data. Gate: review last 7 days of aggregate reports; if no legitimate-source failures (SPF/DKIM both passing for all leafbind-originated mail in the report), proceed to quarantine. Otherwise, identify the failing source and fix before upgrading.

Follow-up Jira ticket: filed 2026-05-16, due 2026-06-15.

After quarantine soak (additional 30 days), consider `p=reject` for full enforcement — but only if a second sending source isn't planned.

## Debugging checklist when mail breaks

If outbound from `support@leafbind.io` stops being delivered or lands in spam:

1. **Send to verifier.port25.com or mail-tester.com.** Confirm `dkim=pass header.d=leafbind.io` is in the report.
2. **`dig TXT resend._domainkey.leafbind.io`** — confirm the Resend DKIM key is still published.
3. **Resend dashboard → Domains → leafbind.io** — confirm DKIM/SPF still show ✓.
4. **Check Return-Path header on a sent message** — should be `<...>@send.leafbind.io`, not `@gmail.com`. If it's `@gmail.com`, Thunderbird is routing through smtp.gmail.com instead of smtp.resend.com. Re-check the identity's bound Outgoing Server.

If inbound to `support@leafbind.io` stops arriving in Gmail:

1. **Cloudflare Dashboard → Email Routing → Routing Rules** — confirm the `support@leafbind.io` rule is `enabled: true` with destination `jlfowler1084@gmail.com`.
2. **Cloudflare Dashboard → Email Routing → Destination addresses** — confirm `jlfowler1084@gmail.com` is `verified`.
3. **`dig MX leafbind.io`** — confirm the three `route{1,2,3}.mx.cloudflare.net` records still resolve.
4. **`dig TXT cf2024-1._domainkey.leafbind.io`** — confirm CF's DKIM key for forwarding is still published.
5. **Send a test from an external account and check `X-Forwarded-For` in headers** — proves the forward path is live.

## Operator action items (not in code)

These live outside the repo but are required state for the stack to function:

- Cloudflare Email Routing enabled with two routing rules (`support@leafbind.io`, `dmarc-reports@leafbind.io`).
- Resend account with `leafbind.io` verified.
- Resend REST API key (`re_...`) provisioned to the contact-worker via `wrangler secret put RESEND_API_KEY`.
- Resend SMTP credentials configured in Thunderbird (Outgoing Server: `smtp.resend.com:465`, user `resend`, password = the API key).
- Thunderbird Gmail account using a Google App Password (Gmail 2FA blocks plain password auth from desktop clients).
- Thunderbird identity `Joseph Fowler <support@leafbind.io>` under the Gmail account, bound to the Resend SMTP server.
- Cloudflare Turnstile widget for `leafbind.io` (set up at Cloudflare Dashboard → Turnstile → Add Site). Site key goes in the frontend; secret key goes to the Worker via `wrangler secret put TURNSTILE_SECRET_KEY`.

## Surprises worth remembering

- **Three DKIM signatures on every forwarded message is normal, not a bug.** Don't try to "clean up" duplicates.
- **AWS SES adds its own `d=amazonses.com` signature to Resend-sent mail.** This is dual-sign defense in depth from Resend's underlying infrastructure. Harmless. Don't try to disable it.
- **SRS-rewritten Return-Path doesn't break DMARC alignment.** DMARC uses relaxed alignment on the org domain. `leafbind.io` matches `leafbind.io`. ✓
- **Cloudflare's DKIM key under `cf2024-1` selector is rotated periodically by Cloudflare** (the `2024-1` part is the key generation tag). If a future selector appears (e.g., `cf2025-1`), Cloudflare handles the rotation; do not delete the old key until Cloudflare's UI says it's safe.
- **`compauth=pass reason=100` from Microsoft is the highest score.** Lower reason codes (e.g., reason=001) on the same `pass` verdict mean Microsoft trusted with caveats; treat as a yellow flag worth investigating in aggregate.

## Related memory

- `leafbind-email-forwarding-behavior` — Claude project memory capturing the CF re-authentication pattern for future debugging context.
