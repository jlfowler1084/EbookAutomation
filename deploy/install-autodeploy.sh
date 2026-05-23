#!/usr/bin/env bash
# install-autodeploy.sh — EB-331 Unit 7
#
# Idempotent installer for the EbookAutomation VM auto-deploy stack.
# Copies the six systemd unit files, creates the state dir + env stub (only if
# absent), validates the Cloudflare nginx target, reloads systemd, and enables +
# starts the three timers.
#
# Run as root on the VM:
#   sudo /home/joe/EbookAutomation/deploy/install-autodeploy.sh
#
# A re-run is safe: already-enabled timers are no-ops, and a real
# /etc/ebookweb-autodeploy.env is NEVER overwritten.
#
# Environment overrides (all have VM defaults; override for testing):
#   APP_DIR       Git checkout root   Default: /home/joe/EbookAutomation
#   SYSTEMD_DIR   systemd unit dir    Default: /etc/systemd/system
#   STATE_DIR     Dedupe state dir    Default: /var/lib/ebookweb-autodeploy
#   ENV_FILE      EnvironmentFile     Default: /etc/ebookweb-autodeploy.env
#   NGINX_TARGET  CF sentinel file    Default: /etc/nginx/sites-enabled/leafbind
#
# The systemctl and nginx binaries are resolved via PATH so tests can shim them.
#
# Exit codes:
#   0  All steps completed successfully; timers enabled and started.
#   1  CF target validation failed (file missing, sentinels absent, or not in
#      nginx -T output). No timers were enabled. Fix the nginx config and re-run.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configurable paths (override via environment for tests)
# ---------------------------------------------------------------------------
APP_DIR="${APP_DIR:-/home/joe/EbookAutomation}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
STATE_DIR="${STATE_DIR:-/var/lib/ebookweb-autodeploy}"
ENV_FILE="${ENV_FILE:-/etc/ebookweb-autodeploy.env}"
NGINX_TARGET="${NGINX_TARGET:-/etc/nginx/sites-enabled/leafbind}"

# The six unit files that must be installed.
UNITS=(
    ebookweb-autodeploy.service
    ebookweb-autodeploy.timer
    ebookweb-heartbeat.service
    ebookweb-heartbeat.timer
    refresh-cloudflare-ips.service
    refresh-cloudflare-ips.timer
)

# The four directly-executed scripts (committed +x; chmod belt-and-suspenders).
# Do NOT include discord-notify.sh — it is sourced, not executed directly.
EXEC_SCRIPTS=(
    autodeploy.sh
    deploy.sh
    cf-refresh-wrapped.sh
    refresh-cloudflare-ips.sh
)

# The three timers to enable + start (services are timer-triggered oneshots;
# do NOT enable them directly).
TIMERS=(
    ebookweb-autodeploy.timer
    ebookweb-heartbeat.timer
    refresh-cloudflare-ips.timer
)

DEPLOY_DIR="$APP_DIR/deploy"

echo "[install-autodeploy] =============================================="
echo "[install-autodeploy] EbookAutomation auto-deploy installer (EB-331)"
echo "[install-autodeploy] =============================================="
echo "[install-autodeploy] APP_DIR     = $APP_DIR"
echo "[install-autodeploy] SYSTEMD_DIR = $SYSTEMD_DIR"
echo "[install-autodeploy] STATE_DIR   = $STATE_DIR"
echo "[install-autodeploy] ENV_FILE    = $ENV_FILE"
echo "[install-autodeploy] NGINX_TARGET= $NGINX_TARGET"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Copy the six unit files to SYSTEMD_DIR
# ---------------------------------------------------------------------------
echo "[install-autodeploy] Step 1: Installing systemd unit files..."
for unit in "${UNITS[@]}"; do
    src="$DEPLOY_DIR/$unit"
    dst="$SYSTEMD_DIR/$unit"
    if [[ ! -f "$src" ]]; then
        echo "[install-autodeploy] ERROR: unit file not found: $src" >&2
        exit 1
    fi
    cp "$src" "$dst"
    echo "[install-autodeploy]   copied $unit -> $SYSTEMD_DIR/"
done

# ---------------------------------------------------------------------------
# Step 2: chmod +x the four directly-executed scripts (belt-and-suspenders)
# ---------------------------------------------------------------------------
echo ""
echo "[install-autodeploy] Step 2: Ensuring execute bit on deploy scripts..."
for script in "${EXEC_SCRIPTS[@]}"; do
    path="$DEPLOY_DIR/$script"
    if [[ -f "$path" ]]; then
        chmod +x "$path"
        echo "[install-autodeploy]   chmod +x $path"
    else
        echo "[install-autodeploy]   WARNING: script not found (skipping): $path" >&2
    fi
done

# ---------------------------------------------------------------------------
# Step 3: State dir + env stub (only if absent; never overwrite a real secret)
# ---------------------------------------------------------------------------
echo ""
echo "[install-autodeploy] Step 3: Creating state dir and env stub (if absent)..."

mkdir -p "$STATE_DIR"
echo "[install-autodeploy]   state dir: $STATE_DIR"

if [[ -f "$ENV_FILE" ]]; then
    echo "[install-autodeploy]   $ENV_FILE already exists — leaving untouched (never overwrite a real secret)."
else
    # Create the stub env file with a placeholder. Never echo/print its contents.
    printf 'DISCORD_DEPLOY_WEBHOOK_URL=\n' > "$ENV_FILE"
    chmod 0600 "$ENV_FILE"
    echo "[install-autodeploy]   created $ENV_FILE (0600, placeholder — paste real webhook URL before use)."
fi

# ---------------------------------------------------------------------------
# Step 4: CF target validation — FAIL LOUDLY before enabling the CF timer
#
# Checks:
#   (a) $NGINX_TARGET exists
#   (b) file contains both sentinel comments
#   (c) the file is included in `nginx -T` output
#
# On any failure: print a clear >&2 message and exit 1 WITHOUT enabling
# any timers.  The autodeploy/heartbeat timers could still be enabled
# independently, but we abort the whole install so the operator is forced
# to fix the nginx config before any timer goes live — a partial half-enabled
# state is harder to reason about than a clean re-run after the fix.
# ---------------------------------------------------------------------------
echo ""
echo "[install-autodeploy] Step 4: Validating Cloudflare nginx target..."

CF_GATE_FAIL=0
CF_FAIL_REASON=""

# (a) file must exist
if [[ ! -f "$NGINX_TARGET" ]]; then
    CF_GATE_FAIL=1
    CF_FAIL_REASON="NGINX_TARGET file does not exist: $NGINX_TARGET"
fi

# (b) file must contain both sentinels
if [[ "$CF_GATE_FAIL" -eq 0 ]]; then
    if ! grep -qF "# BEGIN CLOUDFLARE IPS" "$NGINX_TARGET"; then
        CF_GATE_FAIL=1
        CF_FAIL_REASON="Sentinel '# BEGIN CLOUDFLARE IPS' not found in $NGINX_TARGET"
    elif ! grep -qF "# END CLOUDFLARE IPS" "$NGINX_TARGET"; then
        CF_GATE_FAIL=1
        CF_FAIL_REASON="Sentinel '# END CLOUDFLARE IPS' not found in $NGINX_TARGET"
    fi
fi

# (c) file must appear in `nginx -T` output
if [[ "$CF_GATE_FAIL" -eq 0 ]]; then
    NGINX_BIN="${NGINX_BIN:-$(command -v nginx 2>/dev/null || echo 'nginx')}"
    NGINX_T_OUTPUT=""
    if ! NGINX_T_OUTPUT="$("$NGINX_BIN" -T 2>&1)"; then
        CF_GATE_FAIL=1
        CF_FAIL_REASON="'nginx -T' failed — nginx may not be installed or config is invalid"
    elif ! echo "$NGINX_T_OUTPUT" | grep -qF "$NGINX_TARGET"; then
        CF_GATE_FAIL=1
        CF_FAIL_REASON="$NGINX_TARGET is not included in 'nginx -T' output — the file may not be active"
    fi
fi

if [[ "$CF_GATE_FAIL" -ne 0 ]]; then
    echo "" >&2
    echo "[install-autodeploy] ERROR: Cloudflare nginx target validation FAILED" >&2
    echo "[install-autodeploy] Reason: $CF_FAIL_REASON" >&2
    echo "" >&2
    echo "[install-autodeploy] Fix the nginx configuration at $NGINX_TARGET" >&2
    echo "[install-autodeploy] and ensure it contains both:" >&2
    echo "[install-autodeploy]   # BEGIN CLOUDFLARE IPS" >&2
    echo "[install-autodeploy]   # END CLOUDFLARE IPS" >&2
    echo "[install-autodeploy] and is included in 'nginx -T' output." >&2
    echo "" >&2
    echo "[install-autodeploy] No timers have been enabled. Re-run after fixing nginx." >&2
    exit 1
fi

echo "[install-autodeploy]   $NGINX_TARGET exists: OK"
echo "[install-autodeploy]   Sentinels present: OK"
echo "[install-autodeploy]   Included in nginx -T: OK"

# ---------------------------------------------------------------------------
# Step 5: daemon-reload, then enable + start the three timers only
# ---------------------------------------------------------------------------
echo ""
echo "[install-autodeploy] Step 5: Reloading systemd and enabling timers..."

SYSTEMCTL="${SYSTEMCTL:-$(command -v systemctl 2>/dev/null || echo 'systemctl')}"

"$SYSTEMCTL" daemon-reload
echo "[install-autodeploy]   daemon-reload: done"

for timer in "${TIMERS[@]}"; do
    "$SYSTEMCTL" enable "$timer"
    "$SYSTEMCTL" start  "$timer"
    echo "[install-autodeploy]   enabled + started: $timer"
done

# ---------------------------------------------------------------------------
# Step 6: Print the timer listing filtered to our new timers
# ---------------------------------------------------------------------------
echo ""
echo "[install-autodeploy] Step 6: Active timer status:"
echo ""
"$SYSTEMCTL" list-timers ebookweb-autodeploy.timer ebookweb-heartbeat.timer refresh-cloudflare-ips.timer --no-pager 2>&1 || true

echo ""
echo "[install-autodeploy] =============================================="
echo "[install-autodeploy] Install complete."
echo "[install-autodeploy] NEXT STEP: paste the real DISCORD_DEPLOY_WEBHOOK_URL"
echo "[install-autodeploy] into $ENV_FILE"
echo "[install-autodeploy] =============================================="
