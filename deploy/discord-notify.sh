#!/usr/bin/env bash
# discord-notify.sh — best-effort Discord embed helper for the EB-331 auto-deploy system.
#
# Source this file in autodeploy.sh or cf-refresh-wrapped.sh; do NOT execute it directly.
# Provides a single function: discord_notify <color_class> <title> <message>
#
# Usage (after sourcing):
#   discord_notify green "Deploy succeeded" "Deployed abc123..def456 (3 commits) — health OK"
#   discord_notify red   "Deploy failed"    "Last 15 lines:\n  ..."
#   discord_notify yellow "Warning"         "Preflight: dirty tree"
#   discord_notify info  "Heartbeat"        "HEAD=abc123, 0 behind, alive"
#
# Color classes and their Discord color integers:
#   red    → 15158332
#   green  → 3066993
#   yellow → 16776960
#   info   → 9807270
#
# Environment:
#   DISCORD_DEPLOY_WEBHOOK_URL  — full Discord webhook URL; if unset/empty the
#                                 function logs a warning and returns 0.
#
# Best-effort contract:
#   This function NEVER exits non-zero and NEVER propagates failure to the
#   caller. If the webhook URL is absent, or the POST fails (non-2xx / curl
#   error / jq missing), it logs a warning to journald (via `logger`) or
#   stderr, then returns 0. A deploy must never be blocked by Discord being down.
#
# JSON safety:
#   Payload is built with `jq -n --arg` so any characters in <title> or
#   <message> (quotes, backslashes, control chars) are encoded correctly.
#   If jq is unavailable, falls back to Python's json.dumps (also safe).
#   String interpolation is never used for payload fields.
#
# Exit codes:
#   (none — function only; always returns 0)

# ---------------------------------------------------------------------------
# _discord_log_warn — write a warning to journald if logger is available,
# otherwise to stderr. Used internally; not exported.
# ---------------------------------------------------------------------------
_discord_log_warn() {
    local msg="discord-notify: $*"
    if command -v logger >/dev/null 2>&1; then
        logger -t discord-notify -p user.warning "$msg"
    else
        echo "[WARN] $msg" >&2
    fi
}

# ---------------------------------------------------------------------------
# discord_notify <color_class> <title> <message>
#
# <color_class>  one of: red | green | yellow | info
# <title>        short string shown as embed title (no "[…] EbookAutomation"
#                wrapper applied here — caller supplies the full title text)
# <message>      body text; may contain quotes and literal \n sequences
# ---------------------------------------------------------------------------
discord_notify() {
    local color_class="${1:-info}"
    local title="${2:-EbookAutomation}"
    local message="${3:-}"

    # -- resolve color int ------------------------------------------------
    local color_int
    case "$color_class" in
        red)    color_int=15158332 ;;
        green)  color_int=3066993  ;;
        yellow) color_int=16776960 ;;
        info)   color_int=9807270  ;;
        *)
            _discord_log_warn "unknown color class '$color_class'; defaulting to info"
            color_int=9807270
            ;;
    esac

    # -- guard: webhook URL must be set and non-empty ---------------------
    if [[ -z "${DISCORD_DEPLOY_WEBHOOK_URL:-}" ]]; then
        _discord_log_warn "DISCORD_DEPLOY_WEBHOOK_URL is unset or empty — skipping Discord post (title: $title)"
        return 0
    fi

    # -- build ISO-8601 UTC footer timestamp ------------------------------
    local footer_ts
    footer_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    # -- build JSON payload -----------------------------------------------
    # Prefer jq (installed on the VM); fall back to Python's json.dumps.
    local payload
    if command -v jq >/dev/null 2>&1; then
        # jq -n --arg correctly handles any content in title/message/footer
        if ! payload="$(jq -n \
            --argjson color_int "$color_int" \
            --arg     title      "$title" \
            --arg     message    "$message" \
            --arg     footer_ts  "$footer_ts" \
            '{"embeds":[{"color":$color_int,"title":$title,"description":$message,"footer":{"text":$footer_ts}}]}')"; then
            _discord_log_warn "jq failed to build payload — skipping Discord post (title: $title)"
            return 0
        fi
    elif command -v python3 >/dev/null 2>&1; then
        if ! payload="$(python3 -c "
import json, sys
color_int  = $color_int
title      = sys.argv[1]
message    = sys.argv[2]
footer_ts  = sys.argv[3]
print(json.dumps({'embeds':[{'color':color_int,'title':title,'description':message,'footer':{'text':footer_ts}}]}))
" "$title" "$message" "$footer_ts")"; then
            _discord_log_warn "python3 JSON build failed — skipping Discord post (title: $title)"
            return 0
        fi
    else
        _discord_log_warn "neither jq nor python3 available — skipping Discord post (title: $title)"
        return 0
    fi

    # -- POST to Discord --------------------------------------------------
    # Guard with an explicit if so a non-2xx or curl error is caught and
    # does NOT propagate under set -e in the caller.
    local http_status
    if ! http_status="$(curl -s -o /dev/null -w '%{http_code}' \
            -H 'Content-Type: application/json' \
            -d "$payload" \
            --max-time 10 \
            "$DISCORD_DEPLOY_WEBHOOK_URL")"; then
        _discord_log_warn "curl failed (network error) posting to Discord (title: $title)"
        return 0
    fi

    # Discord returns 204 No Content on success; treat 2xx broadly as OK
    case "$http_status" in
        2??)
            # Success — no output; caller's logging describes the event
            ;;
        *)
            _discord_log_warn "Discord POST returned HTTP $http_status for title '$title'"
            ;;
    esac

    return 0
}
