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
