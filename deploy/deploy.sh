#!/usr/bin/env bash
# deploy.sh — pull latest code, install deps, restart the web service, verify health.
#
# Run as root on the VM (e.g. over Tailscale: ssh root@<vm>). git/pip run as the
# 'joe' owner; systemctl runs as root. On a failed post-restart health check, the
# code is rolled back to the pre-deploy commit and the service restarted.
set -euo pipefail

APP_DIR="/home/joe/EbookAutomation"
APP_USER="joe"
VENV="$APP_DIR/.venv"
SERVICE="ebookweb"
HEALTH_URL="http://127.0.0.1:8001/health"
GIT=(git -c "safe.directory=$APP_DIR")
HEALTH_POLL_INTERVAL=3   # seconds between probes
HEALTH_POLL_MAX=15        # max probes (~45s total)

# Poll $HEALTH_URL every $HEALTH_POLL_INTERVAL seconds up to $HEALTH_POLL_MAX times.
# Returns 0 on first successful probe, 1 if all probes time out.
wait_for_health() {
    local i
    for ((i = 1; i <= HEALTH_POLL_MAX; i++)); do
        if curl -sf "$HEALTH_URL" >/dev/null; then
            return 0
        fi
        echo "[deploy] Health probe $i/$HEALTH_POLL_MAX failed — retrying in ${HEALTH_POLL_INTERVAL}s..."
        sleep "$HEALTH_POLL_INTERVAL"
    done
    return 1
}

cd "$APP_DIR"

ROLLBACK="$(sudo -u "$APP_USER" "${GIT[@]}" rev-parse HEAD)"
echo "[deploy] Rollback point: $(sudo -u "$APP_USER" "${GIT[@]}" rev-parse --short HEAD)"

echo "[deploy] Pulling latest code (ff-only)..."
sudo -u "$APP_USER" "${GIT[@]}" pull --ff-only origin master

echo "[deploy] Installing Python dependencies..."
sudo -u "$APP_USER" "$VENV/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$VENV/bin/pip" install -q -r requirements.txt

echo "[deploy] Restarting service (DB migrations auto-apply on startup)..."
systemctl restart "$SERVICE"

if wait_for_health; then
    echo "[deploy] Done. Health OK at $(sudo -u "$APP_USER" "${GIT[@]}" rev-parse --short HEAD)"
else
    echo "[deploy] Health check FAILED — rolling back to $ROLLBACK" >&2
    sudo -u "$APP_USER" "${GIT[@]}" reset --hard "$ROLLBACK"
    sudo -u "$APP_USER" "$VENV/bin/pip" install -q -r requirements.txt
    systemctl restart "$SERVICE"
    if wait_for_health; then
        echo "[deploy] Rolled back; health OK."
    else
        echo "[deploy] Rolled back but health STILL failing — investigate." >&2
    fi
    exit 1
fi
