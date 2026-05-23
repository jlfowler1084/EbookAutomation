#!/usr/bin/env bash
# tests/deploy/test_install_autodeploy.sh
#
# Plain-bash test suite for deploy/install-autodeploy.sh.
# bats is NOT installed; this is a self-contained runner.
#
# Usage (from repo root OR tests/deploy/):
#   bash tests/deploy/test_install_autodeploy.sh
#
# Test strategy:
#   - All VM paths are redirected to mktemp dirs — no /etc, /var, /run touched.
#   - systemctl shim: a PATH-prepended executable that records calls to a log
#     file and returns 0. Configurable exit code via SYSTEMCTL_EXIT env var.
#   - nginx shim: a PATH-prepended executable that:
#       * Returns 0 for "nginx -t" and "nginx -T" (the latter emits a
#         configurable NGINX_T_OUTPUT env var so tests can control what shows).
#       * Records all calls to a log file.
#   - Unit files are created in a temp source deploy dir so the copy step works.
#
# Exit code: 0 all tests passed, 1 one or more tests failed.

# shellcheck disable=SC2154  # vars assigned via eval "$(make_test_env ...)" — not visible to shellcheck
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALLER="$REPO_ROOT/deploy/install-autodeploy.sh"

# ---------------------------------------------------------------------------
# Mini test framework (same style as test_cf_refresh.sh / test_autodeploy.sh)
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
FAILURES=()

pass()  { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail()  {
    FAIL=$((FAIL + 1))
    echo "  FAIL: $1"
    FAILURES+=("$1")
}
assert_eq() {
    local label="$1" expected="$2" actual="$3"
    if [[ "$actual" == "$expected" ]]; then
        pass "$label"
    else
        fail "$label — expected '$expected', got '$actual'"
    fi
}
assert_contains() {
    local label="$1" needle="$2" haystack="$3"
    if [[ "$haystack" == *"$needle"* ]]; then
        pass "$label"
    else
        fail "$label — expected to find '$needle' in: $haystack"
    fi
}
assert_not_contains() {
    local label="$1" needle="$2" haystack="$3"
    if [[ "$haystack" != *"$needle"* ]]; then
        pass "$label"
    else
        fail "$label — expected NOT to find '$needle' in: $haystack"
    fi
}
assert_zero() {
    local label="$1" rc="$2"
    if [[ "$rc" -eq 0 ]]; then
        pass "$label"
    else
        fail "$label — expected exit 0, got $rc"
    fi
}
assert_nonzero() {
    local label="$1" rc="$2"
    if [[ "$rc" -ne 0 ]]; then
        pass "$label"
    else
        fail "$label — expected non-zero exit, got 0"
    fi
}
assert_file_exists() {
    local label="$1" path="$2"
    if [[ -f "$path" ]]; then
        pass "$label"
    else
        fail "$label — file does not exist: $path"
    fi
}
# shellcheck disable=SC2317  # invoked indirectly by test cases
assert_file_not_exists() {
    local label="$1" path="$2"
    if [[ ! -f "$path" ]]; then
        pass "$label"
    else
        fail "$label — file unexpectedly exists: $path"
    fi
}
assert_dir_exists() {
    local label="$1" path="$2"
    if [[ -d "$path" ]]; then
        pass "$label"
    else
        fail "$label — directory does not exist: $path"
    fi
}

# ---------------------------------------------------------------------------
# Temp dir pool + cleanup
# ---------------------------------------------------------------------------
ALL_TMPS=()

make_tmp() {
    local d
    d="$(mktemp -d)"
    ALL_TMPS+=("$d")
    echo "$d"
}

# shellcheck disable=SC2317  # invoked indirectly via EXIT trap
cleanup_all() {
    for d in "${ALL_TMPS[@]:-}"; do
        rm -rf "$d"
    done
}
trap cleanup_all EXIT

# ---------------------------------------------------------------------------
# make_test_env <base_dir> <nginx_target_mode> [nginx_t_includes_target]
#
# nginx_target_mode:
#   "valid"          — target file exists WITH both sentinels
#   "missing"        — target file does not exist
#   "no_sentinels"   — target file exists but WITHOUT sentinels
#
# nginx_t_includes_target (default "yes"):
#   "yes"  — nginx -T output includes the NGINX_TARGET path
#   "no"   — nginx -T output does NOT include the NGINX_TARGET path
#
# Creates:
#   $base/deploy/          — source deploy dir with stub unit files + scripts
#   $base/systemd/         — destination SYSTEMD_DIR
#   $base/state/           — STATE_DIR
#   $base/shims/systemctl  — systemctl shim recording calls
#   $base/shims/nginx      — nginx shim controlling -T output
#   $base/systemctl.log    — call log for systemctl shim
#   $base/nginx.log        — call log for nginx shim
#   $base/nginx_target      — the NGINX_TARGET file (mode-dependent)
#
# Prints env exports to eval:
#   app_dir, systemd_dir, state_dir, env_file, nginx_target,
#   shim_dir, systemctl_log, nginx_log
# ---------------------------------------------------------------------------
make_test_env() {
    local base="$1"
    local nginx_mode="${2:-valid}"
    local nginx_t_includes="${3:-yes}"

    # APP_DIR is the git checkout root; the installer constructs DEPLOY_DIR=$APP_DIR/deploy.
    local app_dir="$base/app"
    local deploy_src="$app_dir/deploy"
    local systemd_dir="$base/systemd"
    local state_dir="$base/state"
    local env_file="$base/autodeploy.env"
    local nginx_target="$base/nginx_target"
    local shim_dir="$base/shims"
    local systemctl_log="$base/systemctl.log"
    local nginx_log="$base/nginx.log"

    mkdir -p "$deploy_src" "$systemd_dir" "$state_dir" "$shim_dir"
    : > "$systemctl_log"
    : > "$nginx_log"

    # --- Create stub unit files in the source deploy dir ---
    local units=(
        ebookweb-autodeploy.service
        ebookweb-autodeploy.timer
        ebookweb-heartbeat.service
        ebookweb-heartbeat.timer
        refresh-cloudflare-ips.service
        refresh-cloudflare-ips.timer
    )
    for u in "${units[@]}"; do
        printf '[Unit]\nDescription=stub %s\n' "$u" > "$deploy_src/$u"
    done

    # --- Create stub scripts (executable) ---
    local scripts=(autodeploy.sh deploy.sh cf-refresh-wrapped.sh refresh-cloudflare-ips.sh discord-notify.sh)
    for s in "${scripts[@]}"; do
        printf '#!/usr/bin/env bash\n# stub %s\n' "$s" > "$deploy_src/$s"
        chmod +x "$deploy_src/$s"
    done
    # Remove the execute bit from discord-notify.sh to simulate the "sourced only" script.
    chmod -x "$deploy_src/discord-notify.sh"

    # --- Create (or omit) the nginx target file ---
    case "$nginx_mode" in
        valid)
            {
                echo "# nginx config stub"
                echo "# BEGIN CLOUDFLARE IPS"
                echo "    allow 103.21.244.0/22;"
                echo "# END CLOUDFLARE IPS"
            } > "$nginx_target"
            ;;
        missing)
            # Do not create the file
            ;;
        no_sentinels)
            echo "# nginx config stub — no sentinels here" > "$nginx_target"
            ;;
    esac

    # --- Determine what nginx -T should emit ---
    local nginx_t_content=""
    if [[ "$nginx_t_includes" == "yes" ]]; then
        nginx_t_content="# configuration file $nginx_target:"
    else
        nginx_t_content="# configuration file /etc/nginx/nginx.conf:"
    fi

    # --- systemctl shim ---
    # Records every call.  Always exits 0 (idempotent enable/start/daemon-reload).
    cat > "$shim_dir/systemctl" << SCTL_SHIM
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "${systemctl_log}"
exit "\${SYSTEMCTL_EXIT:-0}"
SCTL_SHIM
    chmod +x "$shim_dir/systemctl"

    # --- nginx shim ---
    # nginx -T  → print the configured output + exit 0
    # nginx -t  → exit 0
    # everything else → exit 0
    cat > "$shim_dir/nginx" << NGINX_SHIM
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "${nginx_log}"
case "\$*" in
    *-T*)
        printf '%s\n' "${nginx_t_content}"
        exit 0
        ;;
    *)
        exit "\${NGINX_EXIT:-0}"
        ;;
esac
NGINX_SHIM
    chmod +x "$shim_dir/nginx"

    # Print eval-able assignments (no spaces around = per POSIX convention).
    # app_dir is the git checkout root ($APP_DIR in the installer);
    # the installer itself appends /deploy to get the unit/script source dir.
    echo "app_dir=$app_dir"
    echo "systemd_dir=$systemd_dir"
    echo "state_dir=$state_dir"
    echo "env_file=$env_file"
    echo "nginx_target=$nginx_target"
    echo "shim_dir=$shim_dir"
    echo "systemctl_log=$systemctl_log"
    echo "nginx_log=$nginx_log"
}

# ---------------------------------------------------------------------------
# run_installer <shim_dir> <app_dir> <systemd_dir> <state_dir>
#               <env_file> <nginx_target>
#
# Runs install-autodeploy.sh with all seams wired.
# Sets LAST_RC and LAST_OUTPUT.
# ---------------------------------------------------------------------------
LAST_RC=0
LAST_OUTPUT=""

run_installer() {
    local shim_path="$1"
    local a_dir="$2"
    local s_dir="$3"
    local st_dir="$4"
    local e_file="$5"
    local n_target="$6"

    LAST_RC=0
    LAST_OUTPUT="$(
        PATH="$shim_path:$PATH" \
        APP_DIR="$a_dir" \
        SYSTEMD_DIR="$s_dir" \
        STATE_DIR="$st_dir" \
        ENV_FILE="$e_file" \
        NGINX_TARGET="$n_target" \
        NGINX_BIN="$shim_path/nginx" \
        SYSTEMCTL="$shim_path/systemctl" \
        bash "$INSTALLER" 2>&1
    )" || LAST_RC=$?
}

# shellcheck disable=SC2317  # invoked indirectly by test cases
# Count lines in the systemctl log matching a pattern.
count_systemctl_calls() {
    local log="$1" pattern="$2"
    { grep -c "$pattern" "$log" 2>/dev/null || true; }
}

# Check whether the systemctl log contains a line matching the pattern.
systemctl_called_with() {
    local log="$1" pattern="$2"
    grep -qF "$pattern" "$log" 2>/dev/null
}

# ===========================================================================
# TEST 1: Happy path — all conditions met, timers enabled+started, env stub created
# ===========================================================================
echo ""
echo "TEST 1: Happy path — valid CF target, timers enabled+started, env stub created 0600"

T1_BASE="$(make_tmp)"
eval "$(make_test_env "$T1_BASE" "valid" "yes")"
T1_APP="$app_dir"
T1_SYS="$systemd_dir"
T1_STATE="$state_dir"
T1_ENV="$env_file"
T1_NGINX="$nginx_target"
T1_SHIM="$shim_dir"
T1_SCTL_LOG="$systemctl_log"

run_installer "$T1_SHIM" "$T1_APP" "$T1_SYS" "$T1_STATE" "$T1_ENV" "$T1_NGINX"

# Exit 0
assert_zero     "T1 installer exits 0" "$LAST_RC"

# Unit files copied to SYSTEMD_DIR
assert_file_exists "T1 ebookweb-autodeploy.service copied"      "$T1_SYS/ebookweb-autodeploy.service"
assert_file_exists "T1 ebookweb-autodeploy.timer copied"        "$T1_SYS/ebookweb-autodeploy.timer"
assert_file_exists "T1 ebookweb-heartbeat.service copied"       "$T1_SYS/ebookweb-heartbeat.service"
assert_file_exists "T1 ebookweb-heartbeat.timer copied"         "$T1_SYS/ebookweb-heartbeat.timer"
assert_file_exists "T1 refresh-cloudflare-ips.service copied"   "$T1_SYS/refresh-cloudflare-ips.service"
assert_file_exists "T1 refresh-cloudflare-ips.timer copied"     "$T1_SYS/refresh-cloudflare-ips.timer"

# State dir created
assert_dir_exists  "T1 state dir created" "$T1_STATE"

# Env stub created
assert_file_exists "T1 env file created" "$T1_ENV"

# Env stub is 0600
T1_ENV_PERMS="$(stat -c '%a' "$T1_ENV" 2>/dev/null || stat -f '%Lp' "$T1_ENV" 2>/dev/null || echo 'unknown')"
assert_eq          "T1 env file is 0600" "600" "$T1_ENV_PERMS"

# Env stub has placeholder line
T1_ENV_CONTENT="$(cat "$T1_ENV")"
assert_contains    "T1 env file has DISCORD_DEPLOY_WEBHOOK_URL placeholder" \
                   "DISCORD_DEPLOY_WEBHOOK_URL=" "$T1_ENV_CONTENT"

# daemon-reload called
assert_zero        "T1 daemon-reload was called" \
                   "$(systemctl_called_with "$T1_SCTL_LOG" "daemon-reload"; echo $?)"

# Timers enabled + started (not services)
assert_zero        "T1 ebookweb-autodeploy.timer enabled" \
                   "$(systemctl_called_with "$T1_SCTL_LOG" "enable ebookweb-autodeploy.timer"; echo $?)"
assert_zero        "T1 ebookweb-autodeploy.timer started" \
                   "$(systemctl_called_with "$T1_SCTL_LOG" "start ebookweb-autodeploy.timer"; echo $?)"
assert_zero        "T1 ebookweb-heartbeat.timer enabled" \
                   "$(systemctl_called_with "$T1_SCTL_LOG" "enable ebookweb-heartbeat.timer"; echo $?)"
assert_zero        "T1 ebookweb-heartbeat.timer started" \
                   "$(systemctl_called_with "$T1_SCTL_LOG" "start ebookweb-heartbeat.timer"; echo $?)"
assert_zero        "T1 refresh-cloudflare-ips.timer enabled" \
                   "$(systemctl_called_with "$T1_SCTL_LOG" "enable refresh-cloudflare-ips.timer"; echo $?)"
assert_zero        "T1 refresh-cloudflare-ips.timer started" \
                   "$(systemctl_called_with "$T1_SCTL_LOG" "start refresh-cloudflare-ips.timer"; echo $?)"

# .service units must NOT be enabled directly
T1_SCTL_CONTENT="$(cat "$T1_SCTL_LOG")"
assert_not_contains "T1 .service units NOT enabled directly" \
                   "enable ebookweb-autodeploy.service" "$T1_SCTL_CONTENT"
assert_not_contains "T1 heartbeat .service NOT enabled directly" \
                   "enable ebookweb-heartbeat.service" "$T1_SCTL_CONTENT"
assert_not_contains "T1 cf-refresh .service NOT enabled directly" \
                   "enable refresh-cloudflare-ips.service" "$T1_SCTL_CONTENT"

# ===========================================================================
# TEST 2: Idempotent re-run — existing env file is NOT overwritten
# ===========================================================================
echo ""
echo "TEST 2: Idempotent re-run — pre-existing env file with real secret is preserved"

T2_BASE="$(make_tmp)"
eval "$(make_test_env "$T2_BASE" "valid" "yes")"
T2_APP="$app_dir"
T2_SYS="$systemd_dir"
T2_STATE="$state_dir"
T2_ENV="$env_file"
T2_NGINX="$nginx_target"
T2_SHIM="$shim_dir"
T2_SCTL_LOG="$systemctl_log"

# Pre-create env file with a sentinel secret value
SENTINEL_VALUE="DISCORD_DEPLOY_WEBHOOK_URL=https://discord.example.com/api/webhooks/REAL_SECRET"
printf '%s\n' "$SENTINEL_VALUE" > "$T2_ENV"
chmod 0600 "$T2_ENV"

run_installer "$T2_SHIM" "$T2_APP" "$T2_SYS" "$T2_STATE" "$T2_ENV" "$T2_NGINX"

assert_zero        "T2 installer exits 0 on re-run" "$LAST_RC"

# Secret line must be intact
T2_ENV_AFTER="$(cat "$T2_ENV")"
assert_contains    "T2 real secret line survives re-run" \
                   "https://discord.example.com/api/webhooks/REAL_SECRET" "$T2_ENV_AFTER"
assert_eq          "T2 env file content exactly unchanged" \
                   "$SENTINEL_VALUE" "${T2_ENV_AFTER%$'\n'}"

# timers still enabled (idempotent re-enable is fine)
assert_zero        "T2 daemon-reload called on re-run" \
                   "$(systemctl_called_with "$T2_SCTL_LOG" "daemon-reload"; echo $?)"
assert_zero        "T2 timers enabled on re-run" \
                   "$(systemctl_called_with "$T2_SCTL_LOG" "enable ebookweb-autodeploy.timer"; echo $?)"

# ===========================================================================
# TEST 3: CF gate — NGINX_TARGET file missing → non-zero exit, no timers enabled
# ===========================================================================
echo ""
echo "TEST 3: CF gate — NGINX_TARGET missing → fail loud, non-zero, no timers enabled"

T3_BASE="$(make_tmp)"
eval "$(make_test_env "$T3_BASE" "missing" "yes")"
T3_APP="$app_dir"
T3_SYS="$systemd_dir"
T3_STATE="$state_dir"
T3_ENV="$env_file"
T3_NGINX="$nginx_target"   # this path does not exist (mode=missing)
T3_SHIM="$shim_dir"
T3_SCTL_LOG="$systemctl_log"

run_installer "$T3_SHIM" "$T3_APP" "$T3_SYS" "$T3_STATE" "$T3_ENV" "$T3_NGINX"

assert_nonzero     "T3 installer exits non-zero (CF gate)" "$LAST_RC"
assert_contains    "T3 output mentions validation FAILED" \
                   "validation FAILED" "$LAST_OUTPUT"

# No timer must be enabled
T3_SCTL_CONTENT="$(cat "$T3_SCTL_LOG")"
assert_not_contains "T3 no timer enabled when CF gate fails (autodeploy)" \
                   "enable ebookweb-autodeploy.timer" "$T3_SCTL_CONTENT"
assert_not_contains "T3 no timer enabled when CF gate fails (heartbeat)" \
                   "enable ebookweb-heartbeat.timer" "$T3_SCTL_CONTENT"
assert_not_contains "T3 CF timer NOT enabled when CF gate fails" \
                   "enable refresh-cloudflare-ips.timer" "$T3_SCTL_CONTENT"

# ===========================================================================
# TEST 4: CF gate — file present but NO sentinels → non-zero exit
# ===========================================================================
echo ""
echo "TEST 4: CF gate — target file present but sentinels missing → fail loud, non-zero"

T4_BASE="$(make_tmp)"
eval "$(make_test_env "$T4_BASE" "no_sentinels" "yes")"
T4_APP="$app_dir"
T4_SYS="$systemd_dir"
T4_STATE="$state_dir"
T4_ENV="$env_file"
T4_NGINX="$nginx_target"
T4_SHIM="$shim_dir"
T4_SCTL_LOG="$systemctl_log"

run_installer "$T4_SHIM" "$T4_APP" "$T4_SYS" "$T4_STATE" "$T4_ENV" "$T4_NGINX"

assert_nonzero     "T4 installer exits non-zero (no sentinels)" "$LAST_RC"
assert_contains    "T4 output mentions validation FAILED" \
                   "validation FAILED" "$LAST_OUTPUT"

T4_SCTL_CONTENT="$(cat "$T4_SCTL_LOG")"
assert_not_contains "T4 CF timer NOT enabled (no sentinels)" \
                   "enable refresh-cloudflare-ips.timer" "$T4_SCTL_CONTENT"
assert_not_contains "T4 autodeploy timer NOT enabled (no sentinels)" \
                   "enable ebookweb-autodeploy.timer" "$T4_SCTL_CONTENT"

# ===========================================================================
# TEST 5: CF gate — sentinels present but NOT in nginx -T output → non-zero exit
# ===========================================================================
echo ""
echo "TEST 5: CF gate — sentinels OK but file not in nginx -T output → fail loud, non-zero"

T5_BASE="$(make_tmp)"
eval "$(make_test_env "$T5_BASE" "valid" "no")"
T5_APP="$app_dir"
T5_SYS="$systemd_dir"
T5_STATE="$state_dir"
T5_ENV="$env_file"
T5_NGINX="$nginx_target"
T5_SHIM="$shim_dir"
T5_SCTL_LOG="$systemctl_log"

run_installer "$T5_SHIM" "$T5_APP" "$T5_SYS" "$T5_STATE" "$T5_ENV" "$T5_NGINX"

assert_nonzero     "T5 installer exits non-zero (not in nginx -T)" "$LAST_RC"
assert_contains    "T5 output mentions validation FAILED" \
                   "validation FAILED" "$LAST_OUTPUT"

T5_SCTL_CONTENT="$(cat "$T5_SCTL_LOG")"
assert_not_contains "T5 CF timer NOT enabled (not in nginx -T)" \
                   "enable refresh-cloudflare-ips.timer" "$T5_SCTL_CONTENT"
assert_not_contains "T5 autodeploy timer NOT enabled (not in nginx -T)" \
                   "enable ebookweb-autodeploy.timer" "$T5_SCTL_CONTENT"

# ===========================================================================
# TEST 6: Timer vs service discipline — only *.timer enabled, never *.service
# (dedicated assertion; duplicate of T1 specific sub-tests but isolated for clarity)
# ===========================================================================
echo ""
echo "TEST 6: systemctl call discipline — *.timer enabled, *.service never enabled"

T6_BASE="$(make_tmp)"
eval "$(make_test_env "$T6_BASE" "valid" "yes")"
T6_APP="$app_dir"
T6_SYS="$systemd_dir"
T6_STATE="$state_dir"
T6_ENV="$env_file"
T6_NGINX="$nginx_target"
T6_SHIM="$shim_dir"
T6_SCTL_LOG="$systemctl_log"

run_installer "$T6_SHIM" "$T6_APP" "$T6_SYS" "$T6_STATE" "$T6_ENV" "$T6_NGINX"

assert_zero "T6 exits 0" "$LAST_RC"

T6_SCTL="$(cat "$T6_SCTL_LOG")"

# All three timers must be enabled
assert_contains    "T6 autodeploy timer enabled"  "enable ebookweb-autodeploy.timer"     "$T6_SCTL"
assert_contains    "T6 heartbeat timer enabled"   "enable ebookweb-heartbeat.timer"      "$T6_SCTL"
assert_contains    "T6 cf-refresh timer enabled"  "enable refresh-cloudflare-ips.timer"  "$T6_SCTL"

# No .service must be passed to 'enable'
assert_not_contains "T6 autodeploy.service NOT enabled"    "enable ebookweb-autodeploy.service"    "$T6_SCTL"
assert_not_contains "T6 heartbeat.service NOT enabled"     "enable ebookweb-heartbeat.service"     "$T6_SCTL"
assert_not_contains "T6 cf-refresh.service NOT enabled"    "enable refresh-cloudflare-ips.service" "$T6_SCTL"

# ===========================================================================
# TEST 7: chmod +x applied to directly-executed scripts, not discord-notify.sh
# ===========================================================================
echo ""
echo "TEST 7: chmod +x applied to exec scripts; discord-notify.sh remains as-is"

T7_BASE="$(make_tmp)"
eval "$(make_test_env "$T7_BASE" "valid" "yes")"
T7_APP="$app_dir"
T7_SYS="$systemd_dir"
T7_STATE="$state_dir"
T7_ENV="$env_file"
T7_NGINX="$nginx_target"
T7_SHIM="$shim_dir"

# Strip execute bit from exec scripts (they live in $T7_APP/deploy/).
chmod -x "$T7_APP/deploy/autodeploy.sh"
chmod -x "$T7_APP/deploy/deploy.sh"
chmod -x "$T7_APP/deploy/cf-refresh-wrapped.sh"
chmod -x "$T7_APP/deploy/refresh-cloudflare-ips.sh"

run_installer "$T7_SHIM" "$T7_APP" "$T7_SYS" "$T7_STATE" "$T7_ENV" "$T7_NGINX"

assert_zero "T7 exits 0" "$LAST_RC"

# Verify execute bit was restored on exec scripts
T7_AX="$([ -x "$T7_APP/deploy/autodeploy.sh" ] && echo yes || echo no)"
T7_DX="$([ -x "$T7_APP/deploy/deploy.sh" ] && echo yes || echo no)"
T7_CX="$([ -x "$T7_APP/deploy/cf-refresh-wrapped.sh" ] && echo yes || echo no)"
T7_RX="$([ -x "$T7_APP/deploy/refresh-cloudflare-ips.sh" ] && echo yes || echo no)"

assert_eq "T7 autodeploy.sh is +x after install"             "yes" "$T7_AX"
assert_eq "T7 deploy.sh is +x after install"                 "yes" "$T7_DX"
assert_eq "T7 cf-refresh-wrapped.sh is +x after install"     "yes" "$T7_CX"
assert_eq "T7 refresh-cloudflare-ips.sh is +x after install" "yes" "$T7_RX"

# ===========================================================================
# Summary
# ===========================================================================
echo ""
echo "========================================"
echo "Results: $PASS passed, $FAIL failed"
echo "========================================"

if [[ "${#FAILURES[@]}" -gt 0 ]]; then
    echo ""
    echo "Failed tests:"
    for f in "${FAILURES[@]}"; do
        echo "  - $f"
    done
    exit 1
fi

exit 0
