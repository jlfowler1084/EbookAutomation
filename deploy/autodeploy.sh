#!/usr/bin/env bash
# autodeploy.sh — change-detecting, guarded, deduped pull-deploy wrapper.
#
# Runs as root on the VM (via systemd timer). Delegates the actual deploy to
# deploy/deploy.sh; does NOT reimplement rollback. Alerts to Discord via the
# discord-notify.sh helper (sourced from the same deploy/ directory).
#
# Usage:
#   autodeploy.sh [--force | --emergency-bypass | --heartbeat | --dry-run]
#
# Modes:
#   (no flags)          Normal tick: detect change, run preflights, deploy if ahead.
#   --force             Skip change-detection only; preflights still run.
#                       Use when you want to re-deploy the current master without
#                       waiting for a new commit (e.g. after infra fix).
#   --emergency-bypass  Skip BOTH change-detection AND preflights. Only mode that
#                       skips safety guards. Use only when a preflight guard is
#                       incorrectly blocking a known-safe deploy.
#   --heartbeat         No deploy. Fetch, report N-behind count and liveness to
#                       Discord (green = 0 behind, yellow = behind). Does not
#                       modify any remote-tracking ref beyond the fetch.
#   --dry-run           Use git ls-remote (no remote-ref mutation). Print the
#                       decision/actions that *would* be taken. Never deploys,
#                       never posts to Discord, never restarts anything.
#
# Environment (all have VM defaults; override for testing):
#   APP_DIR             Default: /home/joe/EbookAutomation
#   DEPLOY_SH           Default: $APP_DIR/deploy/deploy.sh
#   LOCK_FILE           Default: /run/ebookweb-deploy.lock
#   STATE_DIR           Default: /var/lib/ebookweb-autodeploy
#   HEALTH_PROBE_URL    Default: https://api.leafbind.io/health
#   DISCORD_DEPLOY_WEBHOOK_URL  (no default — must be set in env file for posts to go through)
#
# State file format (in $STATE_DIR/alert-state):
#   One line: "<alert_class> <epoch_timestamp>"
#   alert_class: "ok" (last known good) or "red" (last posted alert was red)
#   epoch_timestamp: Unix epoch of the last alert post (used for 3h re-nag window)
#   Example: "red 1716500000"
#   Missing or unreadable file → treated as "ok 0" (fail-safe toward visibility).
#
# Exit codes:
#   0   Normal exit (no change, deploy succeeded, heartbeat ok, lock held, dry-run).
#   1   Fatal error that is NOT a deploy failure (e.g. bad flags). Deploy failures
#       are reported to Discord and exit 0 (the timer must not enter a failed state
#       on recoverable deploy errors; systemd will re-run on the next tick).

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve script location and source the Discord helper
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy/discord-notify.sh
source "$SCRIPT_DIR/discord-notify.sh"

# ---------------------------------------------------------------------------
# Configurable paths (override via environment for tests)
# ---------------------------------------------------------------------------
APP_DIR="${APP_DIR:-/home/joe/EbookAutomation}"
DEPLOY_SH="${DEPLOY_SH:-$APP_DIR/deploy/deploy.sh}"
LOCK_FILE="${LOCK_FILE:-/run/ebookweb-deploy.lock}"
STATE_DIR="${STATE_DIR:-/var/lib/ebookweb-autodeploy}"
HEALTH_PROBE_URL="${HEALTH_PROBE_URL:-https://api.leafbind.io/health}"
APP_USER="${APP_USER:-joe}"

# ---------------------------------------------------------------------------
# Git runner — always operate on the checkout as its owner ($APP_USER)
# ---------------------------------------------------------------------------
# This script runs as root under systemd, but $APP_DIR is owned by $APP_USER.
# Running git as root would write root-owned files into $APP_DIR/.git (fetch
# writes FETCH_HEAD/objects/refs; `status` rewrites .git/index), which then
# breaks deploy.sh's `git pull` — deploy.sh deliberately runs git as $APP_USER.
# So we route every repo git call through `sudo -u $APP_USER` to keep .git
# single-owner, matching deploy.sh. (safe.directory is harmless once euid == owner
# but is kept for parity with deploy.sh.)
# Tests have no 'joe' user or sudo: they set AUTODEPLOY_GIT_AS_OWNER=0 to run
# git directly as the current user against a throwaway repo.
if [[ "${AUTODEPLOY_GIT_AS_OWNER:-1}" == "1" ]]; then
    GIT=(sudo -u "$APP_USER" git -c "safe.directory=$APP_DIR")
else
    GIT=(git -c "safe.directory=$APP_DIR")
fi

# ---------------------------------------------------------------------------
# Dedupe / state helpers
# ---------------------------------------------------------------------------
STATE_FILE="$STATE_DIR/alert-state"

# _read_state — echo "<class> <epoch>" from the state file, or "ok 0" if absent.
_read_state() {
    if [[ -f "$STATE_FILE" ]]; then
        local line
        line="$(cat "$STATE_FILE" 2>/dev/null || echo '')"
        if [[ -n "$line" ]]; then
            echo "$line"
            return
        fi
    fi
    echo "ok 0"
}

# _write_state <class> [epoch]  — write a new state line.
_write_state() {
    local class="$1"
    local epoch="${2:-$(date +%s)}"
    mkdir -p "$STATE_DIR"
    echo "$class $epoch" > "$STATE_FILE"
}

# _should_post_red — returns 0 (true) if we should post a red alert now.
# Posts on healthy→failing transition, then re-nags at most once per 3 hours.
_should_post_red() {
    local state_line class last_epoch now delta
    state_line="$(_read_state)"
    class="${state_line%% *}"
    last_epoch="${state_line##* }"
    now="$(date +%s)"
    delta=$(( now - last_epoch ))
    if [[ "$class" != "red" ]]; then
        # Healthy→failing transition: always post.
        return 0
    fi
    # Already red: re-nag only if ≥ 3 hours have elapsed.
    local three_hours=10800
    if (( delta >= three_hours )); then
        return 0
    fi
    return 1
}

# _notify_red <title> <message> — post red if dedupe allows.
# The re-nag window is measured from the last alert POSTED, not the last
# failure observed. Therefore we re-stamp the timestamp ONLY when we actually
# post; a suppressed tick leaves the existing "red <last_post_epoch>" intact.
# (If we re-stamped on every tick, a failure recurring every 5 min would keep
# sliding the window forward and the ~3h re-nag would never fire.)
_notify_red() {
    local title="$1" message="$2"
    if _should_post_red; then
        discord_notify red "$title" "$message"
        _write_state "red"
    fi
    # When suppressed, _should_post_red returning false guarantees the stored
    # class is already "red"; preserving its epoch keeps the re-nag window honest.
}

# _clear_failing_state [notify_recovery] — if state was red, optionally post a
# recovery line and reset state to ok.
_clear_failing_state() {
    local notify="${1:-yes}"
    local state_line class
    state_line="$(_read_state)"
    class="${state_line%% *}"
    if [[ "$class" == "red" ]]; then
        if [[ "$notify" == "yes" ]]; then
            discord_notify green "[recovered] EbookAutomation" \
                "No new commits (up to date with origin/master) — system is healthy again."
        fi
        _write_state "ok"
    fi
}

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
MODE="normal"
case "${1:-}" in
    --force)             MODE="force"             ;;
    --emergency-bypass)  MODE="emergency-bypass"  ;;
    --heartbeat)         MODE="heartbeat"          ;;
    --dry-run)           MODE="dry-run"            ;;
    "")                  MODE="normal"             ;;
    *)
        echo "[autodeploy] ERROR: unknown flag '$1'" >&2
        echo "Usage: autodeploy.sh [--force|--emergency-bypass|--heartbeat|--dry-run]" >&2
        exit 1
        ;;
esac

# ---------------------------------------------------------------------------
# --dry-run: use git ls-remote (no remote-tracking ref mutation), print plan
# ---------------------------------------------------------------------------
if [[ "$MODE" == "dry-run" ]]; then
    echo "[autodeploy][dry-run] Fetching remote HEAD via ls-remote (no ref mutation)..."
    cd "$APP_DIR"
    REMOTE_SHA="$("${GIT[@]}" ls-remote origin refs/heads/master | awk '{print $1}')"
    if [[ -z "$REMOTE_SHA" ]]; then
        echo "[autodeploy][dry-run] WARNING: ls-remote returned empty — cannot determine remote state."
        exit 0
    fi
    LOCAL_SHA="$("${GIT[@]}" rev-parse HEAD 2>/dev/null || echo 'unknown')"
    echo "[autodeploy][dry-run] Local HEAD : $LOCAL_SHA"
    echo "[autodeploy][dry-run] Remote HEAD: $REMOTE_SHA"
    if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
        echo "[autodeploy][dry-run] Decision: NO CHANGE — local is already at origin/master."
        echo "[autodeploy][dry-run] Action  : exit 0 (silent, no Discord post)."
    else
        echo "[autodeploy][dry-run] Decision: CHANGE DETECTED — local is behind (or diverged)."
        echo "[autodeploy][dry-run] Action  : would run preflights, then deploy via $DEPLOY_SH"
        echo "[autodeploy][dry-run] Action  : would post green/red Discord embed on result."
        echo "[autodeploy][dry-run] Action  : would probe $HEALTH_PROBE_URL through CF."
        echo "[autodeploy][dry-run] NOTE    : No deploy, no restart, no Discord post performed."
    fi
    exit 0
fi

# ---------------------------------------------------------------------------
# --heartbeat: explicit fetch + behind-count + liveness report
# ---------------------------------------------------------------------------
if [[ "$MODE" == "heartbeat" ]]; then
    cd "$APP_DIR"
    "${GIT[@]}" fetch --prune origin "+refs/heads/master:refs/remotes/origin/master" 2>&1 \
        || { echo "[autodeploy][heartbeat] ERROR: git fetch failed" >&2; exit 0; }
    LOCAL_SHA="$("${GIT[@]}" rev-parse HEAD)"
    REMOTE_SHA="$("${GIT[@]}" rev-parse refs/remotes/origin/master)"
    if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
        N=0
    else
        N="$("${GIT[@]}" rev-list --count HEAD..refs/remotes/origin/master 2>/dev/null || echo '?')"
    fi
    SHORT_HEAD="$("${GIT[@]}" rev-parse --short HEAD)"
    if [[ "$N" == "0" ]]; then
        discord_notify info "[heartbeat] EbookAutomation" \
            "HEAD=${SHORT_HEAD}, 0 commits behind origin/master — alive."
    else
        discord_notify yellow "[heartbeat] EbookAutomation" \
            "HEAD=${SHORT_HEAD}, ${N} commits behind origin/master — alive but undeployed."
    fi
    exit 0
fi

# ---------------------------------------------------------------------------
# Acquire exclusive lock (flock -n: non-blocking)
# ---------------------------------------------------------------------------
# We exec a sub-process that holds the lock for the entire body. The inner
# body is defined as a function and called with flock wrapping it.
_deploy_body() {
    # -----------------------------------------------------------------------
    # cd to app dir
    # -----------------------------------------------------------------------
    cd "$APP_DIR"

    # -----------------------------------------------------------------------
    # git fetch
    # -----------------------------------------------------------------------
    FETCH_OUT="$("${GIT[@]}" fetch --prune origin "+refs/heads/master:refs/remotes/origin/master" 2>&1)" || {
        _notify_red "[fetch-failed] EbookAutomation" \
            "git fetch failed — cannot check for updates. Last fetch output:\n${FETCH_OUT}"
        echo "[autodeploy] ERROR: git fetch failed" >&2
        return 0  # exit 0: timer must not enter failed state
    }

    # -----------------------------------------------------------------------
    # Change detection (skipped in force/emergency-bypass modes)
    # -----------------------------------------------------------------------
    LOCAL_SHA="$("${GIT[@]}" rev-parse HEAD)"
    REMOTE_SHA="$("${GIT[@]}" rev-parse refs/remotes/origin/master)"

    if [[ "$MODE" == "normal" ]]; then
        if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
            # No change — clear any prior failing state (posts recovery line if was red)
            _clear_failing_state "yes"
            echo "[autodeploy] Up to date with origin/master — nothing to deploy."
            return 0
        fi
    fi

    # -----------------------------------------------------------------------
    # Preflights (skipped only in emergency-bypass)
    # -----------------------------------------------------------------------
    if [[ "$MODE" != "emergency-bypass" ]]; then
        # PF1: branch must be master
        CURRENT_BRANCH="$("${GIT[@]}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'HEAD')"
        if [[ "$CURRENT_BRANCH" != "master" ]]; then
            _notify_red "[preflight-failed] EbookAutomation" \
                "Preflight FAILED: branch is '${CURRENT_BRANCH}', expected 'master'. Deploy aborted."
            echo "[autodeploy] PREFLIGHT FAIL: not on master branch" >&2
            return 0
        fi

        # PF2: working tree must be clean (tracked changes only)
        DIRTY="$("${GIT[@]}" status --porcelain 2>/dev/null | grep -v '^??' || true)"
        if [[ -n "$DIRTY" ]]; then
            _notify_red "[preflight-failed] EbookAutomation" \
                "Preflight FAILED: dirty tree (tracked changes present). Deploy aborted.\n\`\`\`\n${DIRTY}\n\`\`\`"
            echo "[autodeploy] PREFLIGHT FAIL: dirty tree" >&2
            return 0
        fi

        # PF3: HEAD must be an ancestor of origin/master (no diverge / no local-ahead)
        if ! "${GIT[@]}" merge-base --is-ancestor HEAD refs/remotes/origin/master 2>/dev/null; then
            _notify_red "[preflight-failed] EbookAutomation" \
                "Preflight FAILED: HEAD is not an ancestor of origin/master (diverged or ahead). Deploy aborted."
            echo "[autodeploy] PREFLIGHT FAIL: HEAD not ancestor of origin/master" >&2
            return 0
        fi
    fi

    # -----------------------------------------------------------------------
    # Deploy
    # -----------------------------------------------------------------------
    OLD="$("${GIT[@]}" rev-parse HEAD)"
    OLD_SHORT="$("${GIT[@]}" rev-parse --short HEAD)"
    echo "[autodeploy] Running deploy.sh (OLD=${OLD_SHORT})..."

    # Capture deploy.sh output (both stdout and stderr) while still streaming it
    DEPLOY_OUTPUT_FILE="$(mktemp)"
    DEPLOY_RC=0
    # We need to capture output AND stream it. Use tee.
    { "$DEPLOY_SH" 2>&1 | tee "$DEPLOY_OUTPUT_FILE"; } || DEPLOY_RC="${PIPESTATUS[0]}"

    if [[ "$DEPLOY_RC" -eq 0 ]]; then
        # --- Success path ---
        POST="$("${GIT[@]}" rev-parse HEAD)"
        POST_SHORT="$("${GIT[@]}" rev-parse --short HEAD)"
        N="$("${GIT[@]}" rev-list --count "${OLD}..${POST}" 2>/dev/null || echo '?')"

        # Through-CF probe (annotation only — never triggers rollback)
        PROBE_URL="${HEALTH_PROBE_URL}?cb=$(date +%s)"
        PROBE_RC=0
        curl -sf --max-time 15 "$PROBE_URL" >/dev/null 2>&1 || PROBE_RC=$?

        if [[ "$PROBE_RC" -eq 0 ]]; then
            discord_notify green "[deployed] EbookAutomation" \
                "Deployed ${OLD_SHORT}..${POST_SHORT} (${N} commits) — health OK (origin probe passed)."
        else
            discord_notify yellow "[deployed] EbookAutomation" \
                "Deployed ${OLD_SHORT}..${POST_SHORT} (${N} commits) — local health OK, but origin probe failed (CF/nginx issue?). No rollback."
        fi

        # Clear any prior failing state (no recovery notify — success line serves that role)
        _write_state "ok"

    else
        # --- Failure path ---
        # Extract last ~15 lines of deploy output
        LAST_LINES="$(tail -n 15 "$DEPLOY_OUTPUT_FILE" || true)"
        _notify_red "[deploy-failed] EbookAutomation" \
            "deploy.sh exited ${DEPLOY_RC}. Last output:\n\`\`\`\n${LAST_LINES}\n\`\`\`"
        echo "[autodeploy] ERROR: deploy.sh failed with exit ${DEPLOY_RC}" >&2
    fi

    rm -f "$DEPLOY_OUTPUT_FILE"
    return 0
}

# Run _deploy_body under an exclusive flock.
# flock -n: if the lock is already held, exit 0 immediately (no double-deploy).
# If flock is unavailable (e.g. non-Linux test environment), fall through without
# locking — production deploys on Linux always have flock available.
if command -v flock >/dev/null 2>&1; then
    (
        flock -n 9 || {
            echo "[autodeploy] Lock held by another instance — skipping this tick."
            exit 0
        }
        _deploy_body
    ) 9>"$LOCK_FILE"
else
    _deploy_body
fi
