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
WEB_SERVICE_ALLOWED_ORIGINS=https://yourdomain.com
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
