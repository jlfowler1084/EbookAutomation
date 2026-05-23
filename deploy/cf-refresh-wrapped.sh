#!/usr/bin/env bash
# cf-refresh-wrapped.sh — EB-331 Unit 6
#
# Monthly Cloudflare-IP allowlist refresh wrapper.
# Calls refresh-cloudflare-ips.sh (EB-324, frozen), maps its exit code to a
# Discord notification, and performs a through-CF origin probe on success.
#
# Usage:
#   sudo /home/joe/EbookAutomation/deploy/cf-refresh-wrapped.sh
#
# Typically invoked by the refresh-cloudflare-ips.timer systemd timer (monthly).
# May also be run manually to force an immediate refresh.
#
# Environment overrides (for testing / alternate configs):
#   REFRESH_SCRIPT     Path to refresh-cloudflare-ips.sh
#                      Default: $SCRIPT_DIR/refresh-cloudflare-ips.sh
#   NGINX_TARGET       nginx config file passed to the underlying refresh script
#                      (the EXPLICIT live enabled-sites path, not sites-available)
#                      Default: /etc/nginx/sites-enabled/leafbind
#   HEALTH_PROBE_URL   Origin health endpoint to verify after a successful reload
#                      Default: https://api.leafbind.io/health
#
# Exit codes mirrored from refresh-cloudflare-ips.sh:
#   0  Allowlist refreshed, nginx -t passed, reload issued, origin probe OK
#   1  Cloudflare IP fetch failed (network/timeout)
#   2  Sentinel markers not found in the target nginx file
#   3  nginx -t failed after rewrite (reload NOT issued — inspect config)
#  10  Origin probe failed after a successful reload (IP drift / 403 possible)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Source Discord helper (best-effort; never blocks the refresh itself)
# ---------------------------------------------------------------------------
# shellcheck source=deploy/discord-notify.sh
source "$SCRIPT_DIR/discord-notify.sh"

# ---------------------------------------------------------------------------
# Env-overridable seams (for testing)
# ---------------------------------------------------------------------------
REFRESH_SCRIPT="${REFRESH_SCRIPT:-$SCRIPT_DIR/refresh-cloudflare-ips.sh}"
NGINX_TARGET="${NGINX_TARGET:-/etc/nginx/sites-enabled/leafbind}"
HEALTH_PROBE_URL="${HEALTH_PROBE_URL:-https://api.leafbind.io/health}"

# ---------------------------------------------------------------------------
# Run the underlying refresh script
# ---------------------------------------------------------------------------
echo "[cf-refresh-wrapped] Running: $REFRESH_SCRIPT $NGINX_TARGET"

REFRESH_RC=0
"$REFRESH_SCRIPT" "$NGINX_TARGET" || REFRESH_RC=$?

# ---------------------------------------------------------------------------
# Map exit codes → Discord notifications
# ---------------------------------------------------------------------------
case "$REFRESH_RC" in
    0)
        # Refresh and reload succeeded — run a through-CF origin probe.
        echo "[cf-refresh-wrapped] Reload succeeded; probing origin via $HEALTH_PROBE_URL"
        PROBE_URL="${HEALTH_PROBE_URL}?cb=$(date +%s)"

        PROBE_HTTP=0
        PROBE_HTTP="$(curl -s -o /dev/null -w '%{http_code}' \
            --max-time 15 \
            "$PROBE_URL")" || PROBE_HTTP=0

        if [[ "$PROBE_HTTP" =~ ^2 ]]; then
            echo "[cf-refresh-wrapped] Origin probe returned HTTP $PROBE_HTTP — OK"
            discord_notify green "[cf-refresh] EbookAutomation" \
                "Cloudflare allowlist refreshed, reloaded, origin probe OK (HTTP $PROBE_HTTP)."
            exit 0
        else
            echo "[cf-refresh-wrapped] Origin probe returned HTTP $PROBE_HTTP — WARN" >&2
            discord_notify red "[cf-refresh-failed] EbookAutomation" \
                "Cloudflare allowlist reloaded but origin probe failed (HTTP $PROBE_HTTP) — possible IP drift / 403. Verify nginx allowlist and Cloudflare routing."
            exit 10
        fi
        ;;

    1)
        echo "[cf-refresh-wrapped] ERROR: Cloudflare IP fetch failed (exit 1)" >&2
        discord_notify red "[cf-refresh-failed] EbookAutomation" \
            "Cloudflare IP fetch failed. Check network connectivity to cloudflare.com endpoints. nginx config unchanged."
        exit 1
        ;;

    2)
        echo "[cf-refresh-wrapped] ERROR: Sentinel markers not found in target file (exit 2)" >&2
        discord_notify red "[cf-refresh-failed] EbookAutomation" \
            "Sentinel markers not found in target file ($NGINX_TARGET); left untouched. Verify the BEGIN/END CLOUDFLARE IPS markers are present in the live nginx config."
        exit 2
        ;;

    3)
        echo "[cf-refresh-wrapped] ERROR: nginx -t failed after rewrite (exit 3)" >&2
        discord_notify red "[cf-refresh-failed] EbookAutomation" \
            "nginx -t failed after allowlist rewrite; NOT reloaded — inspect config at $NGINX_TARGET. Run 'nginx -t' manually to see the error."
        exit 3
        ;;

    *)
        echo "[cf-refresh-wrapped] ERROR: Unexpected exit code $REFRESH_RC from refresh script" >&2
        discord_notify red "[cf-refresh-failed] EbookAutomation" \
            "Unexpected exit code $REFRESH_RC from refresh-cloudflare-ips.sh — investigate."
        exit "$REFRESH_RC"
        ;;
esac
