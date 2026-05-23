#!/usr/bin/env bash
# tests/deploy/test_cf_refresh.sh
#
# Plain-bash test suite for deploy/cf-refresh-wrapped.sh.
# bats is NOT installed; this is a self-contained runner.
#
# Usage (from repo root OR tests/deploy/):
#   bash tests/deploy/test_cf_refresh.sh
#
# Test strategy:
#   - REFRESH_SCRIPT seam: set to a per-test stub that exits 0/1/2/3 on demand.
#   - curl shim: PATH-prepended shim controls probe HTTP status for exit-0 tests.
#   - discord_notify capture: a stub discord-notify.sh (in a per-test deploy/ dir
#     that also holds a copy of cf-refresh-wrapped.sh) writes
#     "NOTIFY|<color>|<title>|<message>" to NOTIFY_CAPTURE_FILE.
#   - NGINX_TARGET set to /dev/null (the file must exist; sentinel check is in the
#     underlying script which is stubbed out, so /dev/null is safe for the wrapper).
#
# Exit code: 0 all tests passed, 1 one or more tests failed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WRAPPER="$REPO_ROOT/deploy/cf-refresh-wrapped.sh"

# ---------------------------------------------------------------------------
# Mini test framework (same style as test_discord_notify.sh / test_autodeploy.sh)
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

# ---------------------------------------------------------------------------
# Scaffolding — temp dir pool + cleanup
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
# make_shim_env <base_dir> [probe_http_status]
#
# Creates:
#   $base_dir/deploy/discord-notify.sh   — stub writing NOTIFY|color|title|msg
#   $base_dir/deploy/cf-refresh-wrapped.sh — copy of the real wrapper
#   $base_dir/curl_shim/curl              — returns controlled HTTP status
#   $base_dir/refresh_stub/refresh-cloudflare-ips.sh — caller sets via REFRESH_EXIT
#
# Echoes eval-able assignments:
#   deploy_shim_dir, curl_shim_dir, notify_capture, refresh_stub_dir
# ---------------------------------------------------------------------------
make_shim_env() {
    local base="$1"
    local probe_http="${2:-200}"

    local deploy_shim_dir="$base/deploy"
    local curl_shim_dir="$base/curl_shim"
    local refresh_stub_dir="$base/refresh_stub"
    local notify_capture="$base/notify_calls.txt"

    mkdir -p "$deploy_shim_dir" "$curl_shim_dir" "$refresh_stub_dir"
    : > "$notify_capture"

    # --- stub discord-notify.sh ---
    cat > "$deploy_shim_dir/discord-notify.sh" <<STUB
#!/usr/bin/env bash
_discord_log_warn() { echo "[WARN] discord-notify: \$*" >&2; }
discord_notify() {
    local color_class="\${1:-info}"
    local title="\${2:-}"
    local message="\${3:-}"
    printf 'NOTIFY|%s|%s|%s\n' "\$color_class" "\$title" "\$message" >> "\${NOTIFY_CAPTURE_FILE:-/dev/null}"
}
STUB

    # --- copy the real wrapper into the shim deploy dir so SCRIPT_DIR resolves
    #     to deploy_shim_dir and the wrapper sources our stub discord-notify.sh ---
    cp "$WRAPPER" "$deploy_shim_dir/cf-refresh-wrapped.sh"

    # --- stub refresh-cloudflare-ips.sh — exits REFRESH_EXIT (set per test) ---
    cat > "$refresh_stub_dir/refresh-cloudflare-ips.sh" <<'REFRESHSTUB'
#!/usr/bin/env bash
exit "${REFRESH_EXIT:-0}"
REFRESHSTUB
    chmod +x "$refresh_stub_dir/refresh-cloudflare-ips.sh"

    # --- curl shim: returns controlled HTTP status for the origin probe ---
    local probe_status="$probe_http"
    cat > "$curl_shim_dir/curl" <<CURLSHIM
#!/usr/bin/env bash
# Probe curl shim — returns HTTP status $probe_status
# If the caller passes -w '%{http_code}', we must echo exactly the status.
echo "${probe_status}"
exit 0
CURLSHIM
    chmod +x "$curl_shim_dir/curl"

    echo "deploy_shim_dir=$deploy_shim_dir"
    echo "curl_shim_dir=$curl_shim_dir"
    echo "refresh_stub_dir=$refresh_stub_dir"
    echo "notify_capture=$notify_capture"
}

# ---------------------------------------------------------------------------
# run_wrapper <deploy_shim_dir> <curl_shim_dir> <refresh_stub_dir>
#             <notify_capture> <refresh_exit>
#
# Runs the shimmed cf-refresh-wrapped.sh with all seams wired.
# Sets LAST_RC and LAST_OUTPUT.
# ---------------------------------------------------------------------------
# shellcheck disable=SC2034  # LAST_RC and LAST_OUTPUT are read by callers after run_wrapper returns
LAST_RC=0
LAST_OUTPUT=""

run_wrapper() {
    local shim_deploy="$1"
    local curl_shim="$2"
    local refresh_stub="$3"
    local notify_capture="$4"
    local refresh_exit="$5"

    LAST_RC=0
    # shellcheck disable=SC2034  # LAST_OUTPUT is read by callers via the global variable
    LAST_OUTPUT="$(
        PATH="$curl_shim:$PATH" \
        NOTIFY_CAPTURE_FILE="$notify_capture" \
        REFRESH_SCRIPT="$refresh_stub/refresh-cloudflare-ips.sh" \
        NGINX_TARGET="/dev/null" \
        HEALTH_PROBE_URL="https://api.leafbind.io/health" \
        DISCORD_DEPLOY_WEBHOOK_URL="https://discord.example.com/webhook/test" \
        REFRESH_EXIT="$refresh_exit" \
        bash "$shim_deploy/cf-refresh-wrapped.sh" 2>&1
    )" || LAST_RC=$?
}

# Count NOTIFY lines matching a color in the capture file.
count_notifies() {
    local capture="$1" color="$2"
    { grep -c "^NOTIFY|${color}|" "$capture" 2>/dev/null || true; }
}

# Extract field from first NOTIFY line: field 1=color, 2=title, 3=message
notify_field() {
    local capture="$1" field="$2"
    awk -F'|' "NR==1{print \$((${field}+1))}" "$capture"
}

# ===========================================================================
# TEST 1: refresh exit 1 — red, title [cf-refresh-failed], message mentions fetch
# ===========================================================================
echo ""
echo "TEST 1: refresh exit 1 — red Discord post, title [cf-refresh-failed], mentions fetch"

T1_BASE="$(make_tmp)"
eval "$(make_shim_env "$T1_BASE" 200)"
T1_NOTIFY="$notify_capture"
T1_SHIM="$deploy_shim_dir"
T1_CURL="$curl_shim_dir"
T1_REFRESH="$refresh_stub_dir"

run_wrapper "$T1_SHIM" "$T1_CURL" "$T1_REFRESH" "$T1_NOTIFY" "1"

T1_RED="$(count_notifies "$T1_NOTIFY" "red")"
T1_TITLE="$(notify_field "$T1_NOTIFY" 2)"
T1_MSG="$(notify_field "$T1_NOTIFY" 3)"

assert_nonzero  "T1 exit code is non-zero (exit 1)"                "$LAST_RC"
assert_eq       "T1 exactly 1 red post"                            "1" "$T1_RED"
assert_contains "T1 title has [cf-refresh-failed]"                 "[cf-refresh-failed]" "$T1_TITLE"
assert_contains "T1 message mentions fetch"                        "fetch" "$T1_MSG"

# ===========================================================================
# TEST 2: refresh exit 2 — red, title [cf-refresh-failed], message mentions sentinels
# ===========================================================================
echo ""
echo "TEST 2: refresh exit 2 — red Discord post, mentions sentinels/markers"

T2_BASE="$(make_tmp)"
eval "$(make_shim_env "$T2_BASE" 200)"
T2_NOTIFY="$notify_capture"
T2_SHIM="$deploy_shim_dir"
T2_CURL="$curl_shim_dir"
T2_REFRESH="$refresh_stub_dir"

run_wrapper "$T2_SHIM" "$T2_CURL" "$T2_REFRESH" "$T2_NOTIFY" "2"

T2_RED="$(count_notifies "$T2_NOTIFY" "red")"
T2_TITLE="$(notify_field "$T2_NOTIFY" 2)"
T2_MSG="$(notify_field "$T2_NOTIFY" 3)"

assert_nonzero  "T2 exit code is non-zero (exit 2)"                "$LAST_RC"
assert_eq       "T2 exactly 1 red post"                            "1" "$T2_RED"
assert_contains "T2 title has [cf-refresh-failed]"                 "[cf-refresh-failed]" "$T2_TITLE"
assert_contains "T2 message mentions sentinels"                    "entinel" "$T2_MSG"

# ===========================================================================
# TEST 3: refresh exit 3 — red, mentions nginx -t / not reloaded
# ===========================================================================
echo ""
echo "TEST 3: refresh exit 3 — red Discord post, mentions nginx -t and not reloaded"

T3_BASE="$(make_tmp)"
eval "$(make_shim_env "$T3_BASE" 200)"
T3_NOTIFY="$notify_capture"
T3_SHIM="$deploy_shim_dir"
T3_CURL="$curl_shim_dir"
T3_REFRESH="$refresh_stub_dir"

run_wrapper "$T3_SHIM" "$T3_CURL" "$T3_REFRESH" "$T3_NOTIFY" "3"

T3_RED="$(count_notifies "$T3_NOTIFY" "red")"
T3_TITLE="$(notify_field "$T3_NOTIFY" 2)"
T3_MSG="$(notify_field "$T3_NOTIFY" 3)"

assert_nonzero  "T3 exit code is non-zero (exit 3)"                "$LAST_RC"
assert_eq       "T3 exactly 1 red post"                            "1" "$T3_RED"
assert_contains "T3 title has [cf-refresh-failed]"                 "[cf-refresh-failed]" "$T3_TITLE"
assert_contains "T3 message mentions nginx -t"                     "nginx" "$T3_MSG"
assert_contains "T3 message mentions NOT reloaded"                 "NOT reloaded" "$T3_MSG"

# ===========================================================================
# TEST 4: refresh exit 0 + probe 200 — 1 green, title [cf-refresh], origin OK
# ===========================================================================
echo ""
echo "TEST 4: refresh exit 0 + probe 200 — 1 green, title [cf-refresh], origin OK"

T4_BASE="$(make_tmp)"
eval "$(make_shim_env "$T4_BASE" 200)"
T4_NOTIFY="$notify_capture"
T4_SHIM="$deploy_shim_dir"
T4_CURL="$curl_shim_dir"
T4_REFRESH="$refresh_stub_dir"

run_wrapper "$T4_SHIM" "$T4_CURL" "$T4_REFRESH" "$T4_NOTIFY" "0"

T4_GREEN="$(count_notifies "$T4_NOTIFY" "green")"
T4_RED="$(count_notifies "$T4_NOTIFY" "red")"
T4_TITLE="$(notify_field "$T4_NOTIFY" 2)"
T4_MSG="$(notify_field "$T4_NOTIFY" 3)"

assert_zero     "T4 exit code is 0"                                "$LAST_RC"
assert_eq       "T4 exactly 1 green post"                          "1" "$T4_GREEN"
assert_eq       "T4 no red posts"                                  "0" "$T4_RED"
assert_contains "T4 title has [cf-refresh]"                        "[cf-refresh]" "$T4_TITLE"
assert_contains "T4 message mentions probe OK"                     "probe OK" "$T4_MSG"

# ===========================================================================
# TEST 5: refresh exit 0 + probe fails (non-2xx) — 1 red, mentions origin/drift
# ===========================================================================
echo ""
echo "TEST 5: refresh exit 0 + probe fails — 1 red, mentions origin probe / drift"

T5_BASE="$(make_tmp)"
eval "$(make_shim_env "$T5_BASE" 403)"
T5_NOTIFY="$notify_capture"
T5_SHIM="$deploy_shim_dir"
T5_CURL="$curl_shim_dir"
T5_REFRESH="$refresh_stub_dir"

run_wrapper "$T5_SHIM" "$T5_CURL" "$T5_REFRESH" "$T5_NOTIFY" "0"

T5_RED="$(count_notifies "$T5_NOTIFY" "red")"
T5_GREEN="$(count_notifies "$T5_NOTIFY" "green")"
T5_TITLE="$(notify_field "$T5_NOTIFY" 2)"
T5_MSG="$(notify_field "$T5_NOTIFY" 3)"

assert_nonzero  "T5 exit code is non-zero (probe failure)"         "$LAST_RC"
assert_eq       "T5 exactly 1 red post"                            "1" "$T5_RED"
assert_eq       "T5 no green posts"                                "0" "$T5_GREEN"
assert_contains "T5 title has [cf-refresh-failed]"                 "[cf-refresh-failed]" "$T5_TITLE"
assert_contains "T5 message mentions origin probe"                 "probe" "$T5_MSG"
assert_contains "T5 message mentions drift"                        "drift" "$T5_MSG"

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
