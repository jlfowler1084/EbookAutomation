#!/usr/bin/env bash
# deploy.sh — pull latest code, install deps, restart the web service
# Run as the ebookweb user from /opt/ebookautomation
set -euo pipefail

APP_DIR="/opt/ebookautomation"
VENV="$APP_DIR/venv"
SERVICE="ebookweb"

cd "$APP_DIR"

echo "[deploy] Pulling latest code..."
git pull --ff-only

echo "[deploy] Installing Python dependencies..."
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r requirements.txt

echo "[deploy] Restarting service..."
sudo systemctl restart "$SERVICE"
sudo systemctl status "$SERVICE" --no-pager

echo "[deploy] Done. Health check:"
sleep 2
curl -sf http://127.0.0.1:8001/health && echo " OK" || echo " FAILED"
