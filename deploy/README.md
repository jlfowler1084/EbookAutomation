# First-Deployment Walkthrough

This guide covers initial deployment of the EbookAutomation web service on the Hetzner VM.
Run these steps once; subsequent updates use `deploy.sh`.

## Prerequisites

- Ubuntu 22.04 LTS
- Python 3.10+, git, nginx, certbot installed
- Calibre installed at `/usr/bin/ebook-convert` (or set `CALIBRE_PATH` in `.env`)
- Tailscale up (for desktop→VM rsync of pattern DB)

---

## 1. Create the service user

```bash
sudo useradd -r -s /usr/sbin/nologin -d /opt/ebookautomation ebookweb
sudo mkdir -p /opt/ebookautomation
sudo chown ebookweb:ebookweb /opt/ebookautomation
```

## 2. Clone the repo

```bash
sudo -u ebookweb git clone https://github.com/jlfowler1084/EbookAutomation.git /opt/ebookautomation
```

## 3. Create the Python venv and install deps

```bash
cd /opt/ebookautomation
sudo -u ebookweb python3 -m venv venv
sudo -u ebookweb venv/bin/pip install --upgrade pip
sudo -u ebookweb venv/bin/pip install -r requirements.txt
```

## 4. Write the .env file

```bash
sudo -u ebookweb nano /opt/ebookautomation/.env
```

Minimum required variables:

```
# CORS origin list. Comma-separated, no spaces. Production values for leafbind:
WEB_SERVICE_ALLOWED_ORIGINS=https://leafbind.io,https://www.leafbind.io
# Vercel preview origins are not supported here — Starlette's CORSMiddleware
# does strict-equality on origins, not regex. Add NEXT_PUBLIC_API_URL override
# at the Vercel preview-env level instead of trying to allow-list previews.
# Optional overrides (defaults come from config/settings.json):
# CALIBRE_PATH=/usr/bin/ebook-convert
# WEB_SERVICE_DB_PATH=/opt/ebookautomation/data/jobs.db
# WEB_SERVICE_OUTPUT_DIR=/opt/ebookautomation/data/output
# WEB_SERVICE_MAX_CONCURRENT_JOBS=3
```

## Stripe Configuration

Phase 2 billing requires seven additional environment variables. Add these to
`/opt/ebookautomation/.env` manually (the credential-write hook blocks Claude
from writing them).

**Required variables (all fail-closed — service will not start if any are absent):**

```
# Stripe API keys — get these from the Stripe Dashboard > Developers > API keys
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...

# Stripe webhook signing secret — generated when you register the endpoint in
# the Stripe Dashboard (Developers > Webhooks > Add endpoint).
# For local dev/testing, use: stripe listen --forward-to localhost:8001/stripe/webhook
STRIPE_WEBHOOK_SECRET=whsec_...

# Stripe Price IDs — created once via deploy/stripe_bootstrap.py or the
# Stripe Dashboard (Products > create Product + Price for each pack).
STRIPE_PRICE_STARTER=price_...   # $2.99 / 3 credits
STRIPE_PRICE_STANDARD=price_...  # $7.99 / 10 credits
STRIPE_PRICE_POWER=price_...     # $14.99 / 25 credits

# HMAC secret for token generation and validation.
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
# IMPORTANT: Never rotate this value without also rotating all active tokens.
# key_version column in the token table enables future rotation — see docs.
TOKEN_HMAC_SECRET=<64-hex-char random string>
```

**Optional Stripe variables (sensible defaults — set only to override):**

```
# Stripe API version pin (EB-227). Defaults to 2026-04-22.dahlia. Must match
# the version configured on the Stripe webhook endpoint in Workbench. Bumping
# this requires updating BOTH this env var AND the webhook endpoint config in
# Stripe Workbench, or signed payloads can carry a different shape than the
# SDK expects.
STRIPE_API_VERSION=2026-04-22.dahlia
```

**Environment mismatch check:** At startup the service compares the prefixes of
`STRIPE_PUBLISHABLE_KEY` and `STRIPE_SECRET_KEY`. If one is `pk_test_` and the
other is `sk_live_` (or vice versa), a WARN is logged. The service continues
running — this is a configuration advisory, not a fatal error. Verify both keys
are from the same Stripe mode (test or live) before going to production.

**NTP synchronization:** The service checks NTP sync at startup and logs an ERROR
if not synchronized. Stripe webhook signature validation uses wall-clock time;
clock drift exceeding 300 seconds causes Stripe to reject webhooks. Ensure NTP is
active on the VM:

```bash
# Check current sync status
timedatectl show --property=NTPSynchronized --value

# Enable NTP sync if not active
sudo timedatectl set-ntp true
sudo systemctl restart systemd-timesyncd
```

The `/health` endpoint reports `"ntp_synced": true/false` at runtime.

### Stripe webhook endpoint registration (Workbench)

Stripe replaced the legacy Developers Dashboard with **Workbench** (GA Aug 2024).
The instructions below use current Workbench navigation; if your account is still
on the legacy Developers UI, the equivalent path is in parentheses.

After the env vars are in /etc/web_service.env and the service has restarted:

1. Open **Workbench → Webhooks tab → Add destination** (legacy: Developers → Webhooks → Add endpoint)
2. Endpoint URL: `https://leafbind.io/stripe/webhook`
3. **API version:** set to `2026-04-22.dahlia` to match the SDK pin in `STRIPE_API_VERSION`. Mismatched versions produce payload shapes the handler may not parse correctly.
4. Events to send (EB-227: subscribe to ALL FOUR):
   - `checkout.session.completed` (sync card payments: mints tokens after capture)
   - `checkout.session.async_payment_succeeded` (ACH/SEPA: mints tokens once funds settle — without this, async-method customers never get tokens)
   - `checkout.session.async_payment_failed` (ACH/SEPA: logged so support can investigate)
   - `charge.dispute.created` (revokes tokens on chargeback)
5. Click "Add destination"
6. On the resulting endpoint page, click "Reveal" next to "Signing secret"
7. Copy the `whsec_...` value and paste it into `/etc/web_service.env` as `STRIPE_WEBHOOK_SECRET`
8. `sudo systemctl restart ebookweb.service`
9. From Workbench → Webhooks → endpoint detail → **Send test event** → `checkout.session.completed`. Verify the response is 200 OK in the **Event deliveries** tab.

**Test mode vs live mode**: register a SEPARATE webhook endpoint per mode. Stripe issues different `whsec_*` per endpoint. For local development, use `stripe listen --forward-to http://localhost:8001/stripe/webhook` and capture the `whsec_test_*` it prints into `.env.local`.

**Why subscribe to async events even if you're card-only today**: Stripe Link
auto-surfaces alternative payment methods (ACH on US accounts) to returning
customers without merchant config. The async events arrive only if the customer
actually uses an async method; the handler short-circuits cleanly on
`payment_status="unpaid"` (EB-227), so subscribing costs nothing and is
forward-compatible.

### Cloudflare rate-limit rule

Defense-in-depth against scanner traffic on the webhook endpoint:

1. Cloudflare Dashboard → leafbind.io zone → Security → WAF → Rate limiting rules
2. Create rule:
   - Name: `Stripe webhook abuse limit`
   - Field: URI Path equals `/stripe/webhook`
   - Action: Block
   - Period: 1 minute
   - Requests: 30 per IP
   - Mitigation timeout: 10 minutes
3. Deploy the rule

This is defense-in-depth only — Stripe signature validation (already in the webhook handler) is the primary defense. The rate-limit reduces noise from internet scanners hitting the well-known `/stripe/webhook` path.

**Do NOT IP-allowlist Stripe**: Stripe's webhook IPs change without notice (per docs.stripe.com/ips). The signature check provides cryptographic verification independent of source IP.

### nginx hardening

The repository's `deploy/nginx.conf` already includes:
- `client_max_body_size 256k` on the `/stripe/webhook` location block (CVE-2026-40481 DoS mitigation, with headroom for future Stripe event subscriptions)
- `proxy_read_timeout 30s` on the webhook endpoint (long timeouts mask app-layer bugs)

To apply config changes on the VM:

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/leafbind
sudo nginx -t && sudo systemctl reload nginx
```

### Pre-launch checklist (test mode)

Before flipping to live mode, verify all of the following:

- [ ] Stripe account created; test mode API keys obtained (`sk_test_*`, `pk_test_*`)
- [ ] `deploy/stripe_bootstrap.py` run against test mode; 3 `STRIPE_PRICE_*` IDs captured
- [ ] `TOKEN_HMAC_SECRET` generated via `openssl rand -hex 32`
- [ ] All 7 new env vars in `/etc/web_service.env`:
      `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `TOKEN_HMAC_SECRET`, `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_STANDARD`, `STRIPE_PRICE_POWER`
- [ ] Test-mode webhook endpoint registered in Stripe Workbench (API version `2026-04-22.dahlia`) with four event subscriptions: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `charge.dispute.created`
- [ ] Cloudflare rate-limit rule deployed on `/stripe/webhook`
- [ ] `timedatectl status` shows `System clock synchronized: yes` (NTP startup check depends on this)
- [ ] nginx config reloaded (`sudo nginx -t && sudo systemctl reload nginx`)
- [ ] `sudo systemctl restart ebookweb.service`
- [ ] `curl https://leafbind.io/health` returns `{"status":"ok","ntp_synced":true}`
- [ ] Manual test-mode purchase end-to-end succeeds (visit `/pricing` → buy Starter → Stripe Checkout → success page shows 3 tokens → use one in `/convert`)
- [ ] `stripe trigger charge.dispute.created` (after a real test purchase) correctly marks the matching tokens `disputed=1` in `web_service.db`

### Live-mode switch

When test-mode is fully validated:

1. Swap `STRIPE_SECRET_KEY` and `STRIPE_PUBLISHABLE_KEY` from `sk_test_*`/`pk_test_*` to `sk_live_*`/`pk_live_*` in `/etc/web_service.env`
2. Register a NEW webhook endpoint in Stripe Dashboard LIVE mode (test-mode and live-mode webhook secrets are different)
3. Copy the new live-mode `whsec_*` into `STRIPE_WEBHOOK_SECRET`
4. `sudo systemctl restart ebookweb.service`
5. Real purchase test with your own card (refund via Stripe Dashboard afterward)

### Secret rotation runbook (TOKEN_HMAC_SECRET)

The `key_version` column on the `tokens` table supports future rotation. Phase 2 ships with `key_version=1`. To rotate:

1. Pause new purchases for 30 days (drain in-flight token window)
2. After 30 days, all `key_version=1` tokens are either consumed or expired
3. Generate new secret: `openssl rand -hex 32`
4. Bump `key_version=2` constant in `web_service/crypto.py:derive_fernet_key(..., key_version=2)`
5. Update `TOKEN_HMAC_SECRET` env var
6. `sudo systemctl restart ebookweb.service`
7. New tokens mint with `key_version=2` and the new secret

In-flight rotation (rotating without draining the window) is NOT supported in Phase 2. Add `MultiFernet` support in a future ticket if needed.

## 5. Create the data directory

```bash
sudo -u ebookweb mkdir -p /opt/ebookautomation/data/output
```

## 6. Install the systemd unit

```bash
sudo cp deploy/web_service.service /etc/systemd/system/ebookweb.service
sudo systemctl daemon-reload
sudo systemctl enable ebookweb
sudo systemctl start ebookweb
sudo systemctl status ebookweb
```

Verify the health endpoint:

```bash
curl http://127.0.0.1:8001/health
# Expected: {"status":"ok"}
```

## 7. Configure nginx

Replace `api.yourdomain.com` in `deploy/nginx.conf` with your actual domain, then:

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ebookweb
sudo ln -s /etc/nginx/sites-available/ebookweb /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 8. Obtain a TLS certificate

```bash
sudo certbot --nginx -d api.yourdomain.com
```

Follow the prompts. Certbot will auto-update the nginx config with SSL paths.

## 9. Allow deploy.sh to restart the service without a password

Add to `/etc/sudoers.d/ebookweb`:

```
ebookweb ALL=(ALL) NOPASSWD: /bin/systemctl restart ebookweb, /bin/systemctl status ebookweb
```

## 10. Subsequent deploys

```bash
sudo -u ebookweb bash /opt/ebookautomation/deploy/deploy.sh
```

---

## Verifying a Live Conversion

```bash
curl -X POST http://127.0.0.1:8001/convert \
  -F "file=@/path/to/test.pdf" \
  -F "output_format=epub" \
  -F "tier=free"
# Returns: {"job_id":"<uuid>"}

curl http://127.0.0.1:8001/status/<uuid>
# Poll until: {"status":"done","download_url":"/download/<uuid>", ...}

curl -O http://127.0.0.1:8001/download/<uuid>
```
