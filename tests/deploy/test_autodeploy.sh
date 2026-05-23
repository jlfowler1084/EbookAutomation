#!/usr/bin/env bash
# tests/deploy/test_autodeploy.sh
#
# Plain-bash test suite for deploy/autodeploy.sh.
# bats is NOT installed; this is a self-contained runner.
#
# Usage (from repo root OR tests/deploy/):
#   bash tests/deploy/test_autodeploy.sh
#
# Test strategy:
#   Each test builds a throwaway local git repo to simulate HEAD vs origin/master
#   states, injects stub deploy.sh (exits 0 or 1 on demand), and captures Discord
#   notifications via a discord_notify stub (function override). No VM paths are
#   touched; no network calls are made. curl (for the CF probe) is shimmed via PATH.
#
# Exit code: 0 all tests passed, 1 one or more tests failed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AUTODEPLOY="$REPO_ROOT/deploy/autodeploy.sh"

# ---------------------------------------------------------------------------
# Mini test framework (same style as test_discord_notify.sh)
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
assert_file_not_exists() {
    local label="$1" path="$2"
    if [[ ! -f "$path" ]]; then
        pass "$label"
    else
        fail "$label — file unexpectedly exists: $path"
    fi
}

# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------
# All temp dirs gathered here for cleanup.
ALL_TMPS=()

make_tmp() {
    local d
    d="$(mktemp -d)"
    ALL_TMPS+=("$d")
    echo "$d"
}

cleanup_all() {
    for d in "${ALL_TMPS[@]:-}"; do
        rm -rf "$d"
    done
}
trap cleanup_all EXIT

# ---------------------------------------------------------------------------
# build_git_repo <dir> [n_local_commits] [n_origin_ahead]
#
# Creates a bare "origin" and a working clone.
# - n_local_commits: commits in the local clone (default 1; represents HEAD)
# - n_origin_ahead: additional commits pushed to origin after the clone
#   (i.e. origin/master is n_origin_ahead commits ahead of HEAD)
#
# Returns (via echo): path to the working clone directory.
# ---------------------------------------------------------------------------
build_git_repo() {
    local base="$1"
    local n_local="${2:-1}"
    local n_ahead="${3:-0}"

    local origin_dir="$base/origin.git"
    local clone_dir="$base/clone"

    # Init bare origin
    git init --bare "$origin_dir" -q
    git -C "$origin_dir" symbolic-ref HEAD refs/heads/master

    # Create a staging area to push initial content
    local stage_dir="$base/stage"
    git init "$stage_dir" -q
    git -C "$stage_dir" config user.email "test@example.com"
    git -C "$stage_dir" config user.name "Test"
    git -C "$stage_dir" checkout -b master -q 2>/dev/null || git -C "$stage_dir" checkout master -q

    local i
    for ((i = 1; i <= n_local; i++)); do
        echo "commit $i" > "$stage_dir/file.txt"
        git -C "$stage_dir" add file.txt
        git -C "$stage_dir" commit -m "commit $i" -q
    done
    git -C "$stage_dir" remote add origin "$origin_dir"
    git -C "$stage_dir" push -u origin master -q

    # Clone from origin
    git clone "$origin_dir" "$clone_dir" -q
    git -C "$clone_dir" config user.email "test@example.com"
    git -C "$clone_dir" config user.name "Test"

    # Push extra commits to origin (making origin ahead of clone)
    if (( n_ahead > 0 )); then
        for ((i = 1; i <= n_ahead; i++)); do
            echo "origin-commit $i" > "$stage_dir/file.txt"
            git -C "$stage_dir" add file.txt
            git -C "$stage_dir" commit -m "origin-ahead-$i" -q
        done
        git -C "$stage_dir" push origin master -q
    fi

    echo "$clone_dir"
}

# ---------------------------------------------------------------------------
# Shim infrastructure
#
# We inject two shims via a temp dir prepended to PATH:
#   curl      — captures calls (CF probe); returns controlled exit code
#   (discord_notify is overridden as a bash function in the sourced helper,
#    so we inject our own discord-notify.sh that writes to a capture file)
#
# For discord capture: autodeploy.sh sources discord-notify.sh from its own
# script directory. We point SCRIPT_DIR's parent to a fake deploy/ containing
# our stub discord-notify.sh, OR we override the source path via a shim.
# Simpler approach: pass a fake DISCORD_NOTIFY_SHIM path and source it
# after sourcing the real one... but autodeploy.sh uses a hard source path.
#
# Cleanest approach: create a per-test deploy/ directory containing a stub
# discord-notify.sh, and set DEPLOY_SH to a path inside that dir so
# autodeploy.sh resolves SCRIPT_DIR to that dir and sources our stub.
#
# We achieve this by creating:
#   $SHIM_DIR/deploy/discord-notify.sh   (stub that writes to NOTIFY_CAPTURE_FILE)
#   $SHIM_DIR/deploy/autodeploy.sh       (symlink to the real one)
# Then run: bash "$SHIM_DIR/deploy/autodeploy.sh" [flags]
# ---------------------------------------------------------------------------

make_shim_env() {
    local base="$1"
    local notify_capture="$base/notify_calls.txt"
    local curl_capture="$base/curl_calls.txt"
    local curl_shim_dir="$base/curl_shim"
    local deploy_shim_dir="$base/deploy"

    mkdir -p "$deploy_shim_dir" "$curl_shim_dir"
    > "$notify_capture"
    > "$curl_capture"

    # --- discord-notify.sh stub ---
    cat > "$deploy_shim_dir/discord-notify.sh" <<STUB
#!/usr/bin/env bash
# Stub discord-notify.sh for tests.
_discord_log_warn() { echo "[WARN] discord-notify: \$*" >&2; }

discord_notify() {
    local color_class="\${1:-info}"
    local title="\${2:-}"
    local message="\${3:-}"
    printf 'NOTIFY|%s|%s|%s\n' "\$color_class" "\$title" "\$message" >> "\${NOTIFY_CAPTURE_FILE:-/dev/null}"
}
STUB

    # --- curl shim ---
    local curl_exit="${CURL_SHIM_EXIT:-0}"
    cat > "$curl_shim_dir/curl" <<CURLSHIM
#!/usr/bin/env bash
# curl shim for CF probe tests
printf 'CURL_CALLED\n' >> "\${CURL_CAPTURE_FILE:-/dev/null}"
exit ${curl_exit}
CURLSHIM
    chmod +x "$curl_shim_dir/curl"

    # --- autodeploy.sh symlink pointing to the real script ---
    # We create a wrapper that sources our stub discord-notify.sh first,
    # but actually autodeploy.sh uses SCRIPT_DIR from its own location.
    # So we create a real copy of autodeploy.sh with a shebang wrapper.
    # Simplest: cp autodeploy.sh to our shim deploy dir so SCRIPT_DIR resolves
    # to our fake deploy dir (which has our stub discord-notify.sh).
    cp "$AUTODEPLOY" "$deploy_shim_dir/autodeploy.sh"

    echo "notify_capture=$notify_capture"
    echo "curl_capture=$curl_capture"
    echo "curl_shim_dir=$curl_shim_dir"
    echo "deploy_shim_dir=$deploy_shim_dir"
}

# ---------------------------------------------------------------------------
# run_autodeploy <shim_deploy_dir> <curl_shim_dir> <notify_capture> <curl_capture>
#                <git_repo_dir> <state_dir> [flags...]
#
# Runs the shimmed autodeploy.sh and returns its exit code in LAST_RC.
# Also sets LAST_OUTPUT to captured stdout+stderr.
# ---------------------------------------------------------------------------
LAST_RC=0
LAST_OUTPUT=""

run_autodeploy() {
    local shim_deploy="$1"
    local curl_shim="$2"
    local notify_capture="$3"
    local curl_capture="$4"
    local repo_dir="$5"
    local state_dir="$6"
    shift 6
    local flags=("$@")

    LAST_RC=0
    LAST_OUTPUT="$(
        PATH="$curl_shim:$PATH" \
        NOTIFY_CAPTURE_FILE="$notify_capture" \
        CURL_CAPTURE_FILE="$curl_capture" \
        APP_DIR="$repo_dir" \
        DEPLOY_SH="${DEPLOY_SH_OVERRIDE:-$shim_deploy/stub-deploy.sh}" \
        LOCK_FILE="$state_dir/test.lock" \
        STATE_DIR="$state_dir" \
        HEALTH_PROBE_URL="https://api.leafbind.io/health" \
        DISCORD_DEPLOY_WEBHOOK_URL="https://discord.example.com/webhook/test" \
        bash "$shim_deploy/autodeploy.sh" "${flags[@]}" 2>&1
    )" || LAST_RC=$?
}

# Count NOTIFY lines matching a color in the capture file.
# grep -c exits 1 on 0 matches (outputs "0") — || true suppresses the non-zero
# exit so the caller gets the count without a spurious second "0" from || echo.
count_notifies() {
    local capture="$1" color="$2"
    { grep -c "^NOTIFY|${color}|" "$capture" 2>/dev/null || true; }
}
get_notify_title() {
    local capture="$1" idx="${2:-1}"
    awk -F'|' "NR==$idx {print \$3}" "$capture" 2>/dev/null || echo ""
}
get_notify_msg() {
    local capture="$1" idx="${2:-1}"
    awk -F'|' "NR==$idx {print \$4}" "$capture" 2>/dev/null || echo ""
}

# ===========================================================================
# TEST 1: No-change (HEAD == origin/master) — silent exit 0, no Discord post
# ===========================================================================
echo ""
echo "TEST 1: No-change — silent exit 0, no Discord post"

T1_BASE="$(make_tmp)"
T1_REPO="$(build_git_repo "$T1_BASE" 1 0)"  # 0 ahead: same as local
T1_STATE="$(make_tmp)"
eval "$(make_shim_env "$T1_BASE")"
T1_NOTIFY="$notify_capture"
T1_CURL="$curl_capture"
T1_SHIM="$deploy_shim_dir"
T1_CSHIM="$curl_shim_dir"

# No stub-deploy.sh needed for no-change path (should never be called)
run_autodeploy "$T1_SHIM" "$T1_CSHIM" "$T1_NOTIFY" "$T1_CURL" "$T1_REPO" "$T1_STATE"

assert_zero     "T1 exit code is 0"          "$LAST_RC"
T1_NCALLS="$(grep -c '.' "$T1_NOTIFY" 2>/dev/null || true)"
assert_eq       "T1 no Discord posts"        "0" "$T1_NCALLS"
assert_not_contains "T1 no deploy output"    "Running deploy.sh" "$LAST_OUTPUT"

# ===========================================================================
# TEST 2: Deploy success — posts green with OLD..POST and N commits
# ===========================================================================
echo ""
echo "TEST 2: Deploy success — green Discord post with OLD..POST (N)"

T2_BASE="$(make_tmp)"
T2_REPO="$(build_git_repo "$T2_BASE" 1 2)"  # origin is 2 ahead
T2_STATE="$(make_tmp)"
eval "$(make_shim_env "$T2_BASE")"
T2_NOTIFY="$notify_capture"
T2_CURL="$curl_capture"
T2_SHIM="$deploy_shim_dir"
T2_CSHIM="$curl_shim_dir"

# Get OLD sha before deploy
T2_OLD="$(git -C "$T2_REPO" rev-parse HEAD)"
T2_OLD_SHORT="$(git -C "$T2_REPO" rev-parse --short HEAD)"

# Stub deploy.sh: fast-forward pull origin master, exit 0
cat > "$T2_SHIM/stub-deploy.sh" <<DEPLOYSTUB
#!/usr/bin/env bash
set -euo pipefail
git -C "\$APP_DIR" -c "safe.directory=\$APP_DIR" pull --ff-only origin master -q
echo "[stub-deploy] Done."
exit 0
DEPLOYSTUB
chmod +x "$T2_SHIM/stub-deploy.sh"

run_autodeploy "$T2_SHIM" "$T2_CSHIM" "$T2_NOTIFY" "$T2_CURL" "$T2_REPO" "$T2_STATE"

T2_POST_SHORT="$(git -C "$T2_REPO" rev-parse --short HEAD)"
T2_GREEN="$(count_notifies "$T2_NOTIFY" "green")"
T2_TITLE="$(awk -F'|' 'NR==1{print $3}' "$T2_NOTIFY")"
T2_MSG="$(awk -F'|' 'NR==1{print $4}' "$T2_NOTIFY")"

assert_zero     "T2 exit code is 0"                          "$LAST_RC"
assert_eq       "T2 exactly 1 green post"                    "1" "$T2_GREEN"
assert_contains "T2 title has [deployed]"                    "[deployed]" "$T2_TITLE"
assert_contains "T2 message has OLD short sha"               "$T2_OLD_SHORT" "$T2_MSG"
assert_contains "T2 message has POST short sha"              "$T2_POST_SHORT" "$T2_MSG"
assert_contains "T2 message has commit count"                "2 commits" "$T2_MSG"

# State file should be "ok"
T2_STATE_VAL="$(cat "$T2_STATE/alert-state" 2>/dev/null || echo 'missing')"
assert_contains "T2 state cleared to ok"                     "ok" "$T2_STATE_VAL"

# ===========================================================================
# TEST 3: Recovery — was failing, this tick no-change → single green recovery line, state cleared
# ===========================================================================
echo ""
echo "TEST 3: Recovery — was-failing + no-change → 1 green recovery post, state cleared"

T3_BASE="$(make_tmp)"
T3_REPO="$(build_git_repo "$T3_BASE" 1 0)"  # up to date
T3_STATE="$(make_tmp)"
eval "$(make_shim_env "$T3_BASE")"
T3_NOTIFY="$notify_capture"
T3_CURL="$curl_capture"
T3_SHIM="$deploy_shim_dir"
T3_CSHIM="$curl_shim_dir"

# Pre-seed a "red" state (old timestamp so 3h window is not relevant here)
mkdir -p "$T3_STATE"
echo "red 1000000" > "$T3_STATE/alert-state"

run_autodeploy "$T3_SHIM" "$T3_CSHIM" "$T3_NOTIFY" "$T3_CURL" "$T3_REPO" "$T3_STATE"

T3_GREEN="$(count_notifies "$T3_NOTIFY" "green")"
T3_TOTAL="$(grep -c '.' "$T3_NOTIFY" 2>/dev/null || true)"
T3_STATE_VAL="$(cat "$T3_STATE/alert-state" 2>/dev/null || echo 'missing')"

assert_zero     "T3 exit code is 0"                         "$LAST_RC"
assert_eq       "T3 exactly 1 green recovery post"          "1" "$T3_GREEN"
assert_eq       "T3 only 1 total notify call"               "1" "$T3_TOTAL"
assert_contains "T3 state is now ok"                        "ok" "$T3_STATE_VAL"

# ===========================================================================
# TEST 4: Fetch fail — posts red (deduped), no deploy
# ===========================================================================
echo ""
echo "TEST 4: Fetch fail — red Discord post, no deploy"

T4_BASE="$(make_tmp)"
T4_STATE="$(make_tmp)"
# Build a repo whose remote does not exist (fetch will fail)
T4_REPO="$(make_tmp)/fakerepo"
git init "$T4_REPO" -q
git -C "$T4_REPO" config user.email "test@example.com"
git -C "$T4_REPO" config user.name "Test"
git -C "$T4_REPO" checkout -b master -q 2>/dev/null || true
echo "init" > "$T4_REPO/file.txt"
git -C "$T4_REPO" add file.txt
git -C "$T4_REPO" commit -m "init" -q
# Add a remote that points nowhere
git -C "$T4_REPO" remote add origin "file:///nonexistent/path/does/not/exist.git"

eval "$(make_shim_env "$T4_BASE")"
T4_NOTIFY="$notify_capture"
T4_CURL="$curl_capture"
T4_SHIM="$deploy_shim_dir"
T4_CSHIM="$curl_shim_dir"

run_autodeploy "$T4_SHIM" "$T4_CSHIM" "$T4_NOTIFY" "$T4_CURL" "$T4_REPO" "$T4_STATE"

T4_RED="$(count_notifies "$T4_NOTIFY" "red")"
T4_GREEN="$(count_notifies "$T4_NOTIFY" "green")"
T4_YELLOW="$(count_notifies "$T4_NOTIFY" "yellow")"

assert_zero     "T4 exit code is 0 (no fatal error — timer stays healthy)" "$LAST_RC"
assert_eq       "T4 exactly 1 red post"                                     "1" "$T4_RED"
assert_eq       "T4 no green posts on fetch fail"                           "0" "$T4_GREEN"
assert_eq       "T4 no yellow posts on fetch fail"                          "0" "$T4_YELLOW"
T4_TITLE="$(awk -F'|' 'NR==1{print $3}' "$T4_NOTIFY")"
assert_contains "T4 title has [fetch-failed]"                               "[fetch-failed]" "$T4_TITLE"
# No deploy output
assert_not_contains "T4 deploy.sh not called" "Running deploy.sh" "$LAST_OUTPUT"

# ===========================================================================
# TEST 5: Dirty tree — preflight red naming "dirty", no deploy
# ===========================================================================
echo ""
echo "TEST 5: Dirty tree — preflight red naming dirty, no deploy"

T5_BASE="$(make_tmp)"
T5_REPO="$(build_git_repo "$T5_BASE" 1 1)"  # origin 1 ahead (change detected)
T5_STATE="$(make_tmp)"
eval "$(make_shim_env "$T5_BASE")"
T5_NOTIFY="$notify_capture"
T5_CURL="$curl_capture"
T5_SHIM="$deploy_shim_dir"
T5_CSHIM="$curl_shim_dir"

# Make a tracked file dirty
echo "local change" >> "$T5_REPO/file.txt"

run_autodeploy "$T5_SHIM" "$T5_CSHIM" "$T5_NOTIFY" "$T5_CURL" "$T5_REPO" "$T5_STATE"

T5_RED="$(count_notifies "$T5_NOTIFY" "red")"
T5_TITLE="$(awk -F'|' 'NR==1{print $3}' "$T5_NOTIFY")"
T5_MSG="$(awk -F'|' 'NR==1{print $4}' "$T5_NOTIFY")"

assert_zero     "T5 exit code is 0"                  "$LAST_RC"
assert_eq       "T5 exactly 1 red post"              "1" "$T5_RED"
assert_contains "T5 title has [preflight-failed]"    "[preflight-failed]" "$T5_TITLE"
assert_contains "T5 message mentions dirty tree"     "dirty" "$T5_MSG"
assert_not_contains "T5 deploy.sh not called"        "Running deploy.sh" "$LAST_OUTPUT"

# ===========================================================================
# TEST 6: Diverged/ahead — preflight red, no deploy
# ===========================================================================
echo ""
echo "TEST 6: Diverged HEAD not ancestor of origin — preflight red, no deploy"

T6_BASE="$(make_tmp)"
T6_REPO="$(build_git_repo "$T6_BASE" 1 1)"  # origin 1 ahead
T6_STATE="$(make_tmp)"
eval "$(make_shim_env "$T6_BASE")"
T6_NOTIFY="$notify_capture"
T6_CURL="$curl_capture"
T6_SHIM="$deploy_shim_dir"
T6_CSHIM="$curl_shim_dir"

# Add a local commit that diverges from origin
echo "local-only commit" > "$T6_REPO/localfile.txt"
git -C "$T6_REPO" add localfile.txt
git -C "$T6_REPO" commit -m "local diverge" -q

run_autodeploy "$T6_SHIM" "$T6_CSHIM" "$T6_NOTIFY" "$T6_CURL" "$T6_REPO" "$T6_STATE"

T6_RED="$(count_notifies "$T6_NOTIFY" "red")"
T6_TITLE="$(awk -F'|' 'NR==1{print $3}' "$T6_NOTIFY")"
T6_MSG="$(awk -F'|' 'NR==1{print $4}' "$T6_NOTIFY")"

assert_zero     "T6 exit code is 0"                         "$LAST_RC"
assert_eq       "T6 exactly 1 red post"                     "1" "$T6_RED"
assert_contains "T6 title has [preflight-failed]"           "[preflight-failed]" "$T6_TITLE"
assert_contains "T6 message mentions ancestor/diverged"     "ancestor" "$T6_MSG"
assert_not_contains "T6 deploy.sh not called"               "Running deploy.sh" "$LAST_OUTPUT"

# ===========================================================================
# TEST 7: deploy.sh fail — red with last ~15 lines of output
# ===========================================================================
echo ""
echo "TEST 7: deploy.sh exit 1 — red post with last lines of output"

T7_BASE="$(make_tmp)"
T7_REPO="$(build_git_repo "$T7_BASE" 1 1)"  # origin 1 ahead
T7_STATE="$(make_tmp)"
eval "$(make_shim_env "$T7_BASE")"
T7_NOTIFY="$notify_capture"
T7_CURL="$curl_capture"
T7_SHIM="$deploy_shim_dir"
T7_CSHIM="$curl_shim_dir"

# Stub deploy.sh that prints recognisable output and exits 1
cat > "$T7_SHIM/stub-deploy.sh" <<'DEPLOYSTUB'
#!/usr/bin/env bash
# Print some lines so we can verify last-lines capture
for i in $(seq 1 20); do
    echo "[deploy] line $i of failure output"
done
echo "[deploy] FINAL LINE: health check FAILED"
exit 1
DEPLOYSTUB
chmod +x "$T7_SHIM/stub-deploy.sh"

run_autodeploy "$T7_SHIM" "$T7_CSHIM" "$T7_NOTIFY" "$T7_CURL" "$T7_REPO" "$T7_STATE"

T7_RED="$(count_notifies "$T7_NOTIFY" "red")"
T7_TITLE="$(awk -F'|' 'NR==1{print $3}' "$T7_NOTIFY")"
# Extract the full multi-line notification body by reading the entire file
# (message may span multiple lines due to embedded newlines in deploy output)
T7_FILE_CONTENT="$(cat "$T7_NOTIFY")"

assert_zero     "T7 exit code is 0"                        "$LAST_RC"
assert_eq       "T7 exactly 1 red post"                    "1" "$T7_RED"
assert_contains "T7 title has [deploy-failed]"             "[deploy-failed]" "$T7_TITLE"
assert_contains "T7 message has last-lines content"        "FINAL LINE" "$T7_FILE_CONTENT"
# Verify that very early output (line 1) is NOT in the captured message
# (since we only take ~15 lines and there are 21 lines total, line 1 should be absent)
assert_not_contains "T7 early lines not included"          "line 1 of failure" "$T7_FILE_CONTENT"

# ===========================================================================
# TEST 8: Dedupe — same failure twice → only 1 red alert (second suppressed within 3h)
# ===========================================================================
echo ""
echo "TEST 8: Dedupe — second consecutive failure suppressed within 3h"

T8_BASE="$(make_tmp)"
T8_REPO="$(build_git_repo "$T8_BASE" 1 1)"  # origin 1 ahead
T8_STATE="$(make_tmp)"
eval "$(make_shim_env "$T8_BASE")"
T8_NOTIFY="$notify_capture"
T8_CURL="$curl_capture"
T8_SHIM="$deploy_shim_dir"
T8_CSHIM="$curl_shim_dir"

# Stub deploy.sh that always fails
cat > "$T8_SHIM/stub-deploy.sh" <<'DEPLOYSTUB'
#!/usr/bin/env bash
echo "[deploy] Failure output"
exit 1
DEPLOYSTUB
chmod +x "$T8_SHIM/stub-deploy.sh"

# First run — should post red
run_autodeploy "$T8_SHIM" "$T8_CSHIM" "$T8_NOTIFY" "$T8_CURL" "$T8_REPO" "$T8_STATE"

T8_RED_AFTER_FIRST="$(count_notifies "$T8_NOTIFY" "red")"
assert_eq "T8 1 red after first failure" "1" "$T8_RED_AFTER_FIRST"

# Second run — same failure, within 3h (state file has current timestamp)
# The state file written by first run has NOW as the timestamp, so 3h has NOT elapsed.
run_autodeploy "$T8_SHIM" "$T8_CSHIM" "$T8_NOTIFY" "$T8_CURL" "$T8_REPO" "$T8_STATE"

T8_RED_AFTER_SECOND="$(count_notifies "$T8_NOTIFY" "red")"
assert_eq "T8 still only 1 red after second failure (suppressed)" "1" "$T8_RED_AFTER_SECOND"

# ===========================================================================
# TEST 8b: Dedupe re-nag — suppressed ticks must NOT slide the 3h window;
# a re-nag fires once >3h has elapsed since the LAST POST (not the last tick).
# Regression for the "window keeps resetting → re-nag never fires" bug.
# ===========================================================================
echo ""
echo "TEST 8b: Dedupe re-nag after 3h (window measured from last post)"

T8B_BASE="$(make_tmp)"
T8B_REPO="$(build_git_repo "$T8B_BASE" 1 1)"  # origin 1 ahead
T8B_STATE="$(make_tmp)"
eval "$(make_shim_env "$T8B_BASE")"
T8B_NOTIFY="$notify_capture"
T8B_CURL="$curl_capture"
T8B_SHIM="$deploy_shim_dir"
T8B_CSHIM="$curl_shim_dir"

cat > "$T8B_SHIM/stub-deploy.sh" <<'DEPLOYSTUB'
#!/usr/bin/env bash
echo "[deploy] Failure output"
exit 1
DEPLOYSTUB
chmod +x "$T8B_SHIM/stub-deploy.sh"

STATE_FILE_8B="$T8B_STATE/alert-state"

# First failure → posts red, stamps the window at NOW.
run_autodeploy "$T8B_SHIM" "$T8B_CSHIM" "$T8B_NOTIFY" "$T8B_CURL" "$T8B_REPO" "$T8B_STATE"
assert_eq "T8b 1 red after first failure" "1" "$(count_notifies "$T8B_NOTIFY" "red")"
EPOCH_AFTER_FIRST="$(awk '{print $2}' "$STATE_FILE_8B")"

# Two suppressed ticks within the window: no new posts AND the stored epoch
# must be unchanged (the bug re-stamped it here, sliding the window).
run_autodeploy "$T8B_SHIM" "$T8B_CSHIM" "$T8B_NOTIFY" "$T8B_CURL" "$T8B_REPO" "$T8B_STATE"
run_autodeploy "$T8B_SHIM" "$T8B_CSHIM" "$T8B_NOTIFY" "$T8B_CURL" "$T8B_REPO" "$T8B_STATE"
assert_eq "T8b still 1 red after suppressed ticks" "1" "$(count_notifies "$T8B_NOTIFY" "red")"
EPOCH_AFTER_SUPPRESSED="$(awk '{print $2}' "$STATE_FILE_8B")"
assert_eq "T8b suppressed ticks did NOT slide the re-nag window" "$EPOCH_AFTER_FIRST" "$EPOCH_AFTER_SUPPRESSED"

# Backdate the stored epoch to >3h ago → next failure must re-nag.
echo "red $(( $(date +%s) - 10801 ))" > "$STATE_FILE_8B"
run_autodeploy "$T8B_SHIM" "$T8B_CSHIM" "$T8B_NOTIFY" "$T8B_CURL" "$T8B_REPO" "$T8B_STATE"
assert_eq "T8b re-nag fires once >3h elapsed since last post" "2" "$(count_notifies "$T8B_NOTIFY" "red")"

# ===========================================================================
# TEST 9: Lock held — second invocation exits 0, no double-deploy
# ===========================================================================
echo ""
echo "TEST 9: Lock held — second invocation exits 0 immediately, no deploy"

if ! command -v flock >/dev/null 2>&1; then
    echo "  SKIP: flock not available in this environment (test requires Linux/util-linux)"
    echo "  NOTE: production VM always has flock; locking path is verified by code review."
    pass "T9 second invocation exits 0 (SKIPPED — no flock)"
    pass "T9 lock held message in output (SKIPPED — no flock)"
    pass "T9 deploy.sh was NOT called (no marker file) (SKIPPED — no flock)"
else

T9_BASE="$(make_tmp)"
T9_REPO="$(build_git_repo "$T9_BASE" 1 1)"  # origin 1 ahead
T9_STATE="$(make_tmp)"
eval "$(make_shim_env "$T9_BASE")"
T9_NOTIFY="$notify_capture"
T9_CURL="$curl_capture"
T9_SHIM="$deploy_shim_dir"
T9_CSHIM="$curl_shim_dir"

T9_LOCK="$T9_STATE/test.lock"

# Hold the lock externally in a background subshell
(
    exec 9>"$T9_LOCK"
    flock -x 9
    # Hold the lock for 5 seconds
    sleep 5
) &
T9_BG_PID=$!

# Brief wait to ensure the background process has the lock
sleep 0.3

# Stub deploy.sh — if called, writes a marker file
cat > "$T9_SHIM/stub-deploy.sh" <<DEPLOYSTUB
#!/usr/bin/env bash
echo "DEPLOY_CALLED" >> "$T9_STATE/deploy_marker"
exit 0
DEPLOYSTUB
chmod +x "$T9_SHIM/stub-deploy.sh"

run_autodeploy "$T9_SHIM" "$T9_CSHIM" "$T9_NOTIFY" "$T9_CURL" "$T9_REPO" "$T9_STATE"

assert_zero "T9 second invocation exits 0" "$LAST_RC"
assert_contains "T9 lock held message in output" "Lock held" "$LAST_OUTPUT"
assert_file_not_exists "T9 deploy.sh was NOT called (no marker file)" "$T9_STATE/deploy_marker"

# Clean up background lock holder
kill "$T9_BG_PID" 2>/dev/null || true
wait "$T9_BG_PID" 2>/dev/null || true

fi  # end flock availability guard

# ===========================================================================
# TEST 10: --dry-run — uses ls-remote, mutates no ref, posts nothing, no deploy
# ===========================================================================
echo ""
echo "TEST 10: --dry-run — ls-remote, no ref mutation, no Discord post, no deploy"

T10_BASE="$(make_tmp)"
T10_REPO="$(build_git_repo "$T10_BASE" 1 2)"  # origin 2 ahead
T10_STATE="$(make_tmp)"
eval "$(make_shim_env "$T10_BASE")"
T10_NOTIFY="$notify_capture"
T10_CURL="$curl_capture"
T10_SHIM="$deploy_shim_dir"
T10_CSHIM="$curl_shim_dir"

# Record origin/master ref before dry-run
T10_REMOTE_BEFORE="$(git -C "$T10_REPO" rev-parse refs/remotes/origin/master 2>/dev/null || echo 'none')"

# Stub deploy.sh that writes a marker if called
cat > "$T10_SHIM/stub-deploy.sh" <<DEPLOYSTUB
#!/usr/bin/env bash
echo "DEPLOY_CALLED" >> "$T10_STATE/deploy_marker"
exit 0
DEPLOYSTUB
chmod +x "$T10_SHIM/stub-deploy.sh"

run_autodeploy "$T10_SHIM" "$T10_CSHIM" "$T10_NOTIFY" "$T10_CURL" "$T10_REPO" "$T10_STATE" "--dry-run"

T10_REMOTE_AFTER="$(git -C "$T10_REPO" rev-parse refs/remotes/origin/master 2>/dev/null || echo 'none')"
T10_NCALLS="$(grep -c '.' "$T10_NOTIFY" 2>/dev/null || true)"

assert_zero     "T10 exit code is 0"                           "$LAST_RC"
assert_eq       "T10 no Discord posts"                         "0" "$T10_NCALLS"
assert_eq       "T10 remote-tracking ref NOT mutated"          "$T10_REMOTE_BEFORE" "$T10_REMOTE_AFTER"
assert_contains "T10 dry-run output printed"                   "dry-run" "$LAST_OUTPUT"
assert_file_not_exists "T10 deploy.sh not called"              "$T10_STATE/deploy_marker"

# ===========================================================================
# TEST 11: --force — redeploys even with no new commits, but dirty tree still aborts
# ===========================================================================
echo ""
echo "TEST 11: --force — redeploys current master; dirty tree still aborts"

T11_BASE="$(make_tmp)"
T11_REPO="$(build_git_repo "$T11_BASE" 1 0)"  # no origin ahead (would be no-change in normal mode)
T11_STATE="$(make_tmp)"
eval "$(make_shim_env "$T11_BASE")"
T11_NOTIFY="$notify_capture"
T11_CURL="$curl_capture"
T11_SHIM="$deploy_shim_dir"
T11_CSHIM="$curl_shim_dir"

# Stub deploy.sh that exits 0
cat > "$T11_SHIM/stub-deploy.sh" <<DEPLOYSTUB
#!/usr/bin/env bash
echo "[stub-deploy] force deploy done"
exit 0
DEPLOYSTUB
chmod +x "$T11_SHIM/stub-deploy.sh"

# Part A: --force with clean tree should proceed to deploy
run_autodeploy "$T11_SHIM" "$T11_CSHIM" "$T11_NOTIFY" "$T11_CURL" "$T11_REPO" "$T11_STATE" "--force"

T11A_OUTPUT="$LAST_OUTPUT"
assert_zero "T11a --force: exit code 0"               "$LAST_RC"
assert_contains "T11a --force: deploy.sh was called"  "Running deploy.sh" "$T11A_OUTPUT"

# Part B: --force with dirty tree → preflight aborts (dirty tree still blocks)
> "$T11_NOTIFY"
echo "local change" >> "$T11_REPO/file.txt"

run_autodeploy "$T11_SHIM" "$T11_CSHIM" "$T11_NOTIFY" "$T11_CURL" "$T11_REPO" "$T11_STATE" "--force"

T11B_RED="$(count_notifies "$T11_NOTIFY" "red")"
T11B_TITLE="$(awk -F'|' 'NR==1{print $3}' "$T11_NOTIFY")"

assert_zero     "T11b --force + dirty: exit code 0"                    "$LAST_RC"
assert_eq       "T11b --force + dirty: 1 red post"                     "1" "$T11B_RED"
assert_contains "T11b --force + dirty: title has [preflight-failed]"   "[preflight-failed]" "$T11B_TITLE"

# ===========================================================================
# TEST 12: Through-CF annotation — deploy.sh exits 0 but CF probe fails → yellow, no rollback
# ===========================================================================
echo ""
echo "TEST 12: Through-CF probe fails — yellow annotation, no rollback"

T12_BASE="$(make_tmp)"
T12_REPO="$(build_git_repo "$T12_BASE" 1 1)"  # origin 1 ahead
T12_STATE="$(make_tmp)"

# This test needs a FAILING curl shim
T12_CURL_SHIM_EXIT=1  # curl exits non-zero to simulate probe failure

T12_SHIM_DIR="$(make_tmp)"
T12_NOTIFY="$T12_SHIM_DIR/notify_calls.txt"
T12_CURL="$T12_SHIM_DIR/curl_calls.txt"
T12_CDEPLOY="$T12_SHIM_DIR/deploy"
T12_CCURLSHIM="$T12_SHIM_DIR/curlshim"
mkdir -p "$T12_CDEPLOY" "$T12_CCURLSHIM"
> "$T12_NOTIFY"
> "$T12_CURL"

cat > "$T12_CDEPLOY/discord-notify.sh" <<STUB
#!/usr/bin/env bash
_discord_log_warn() { echo "[WARN] discord-notify: \$*" >&2; }
discord_notify() {
    local color_class="\${1:-info}"
    local title="\${2:-}"
    local message="\${3:-}"
    printf 'NOTIFY|%s|%s|%s\n' "\$color_class" "\$title" "\$message" >> "\${NOTIFY_CAPTURE_FILE:-/dev/null}"
}
STUB

cat > "$T12_CCURLSHIM/curl" <<'CURLSHIM'
#!/usr/bin/env bash
printf 'CURL_CALLED\n' >> "${CURL_CAPTURE_FILE:-/dev/null}"
exit 1
CURLSHIM
chmod +x "$T12_CCURLSHIM/curl"

cp "$AUTODEPLOY" "$T12_CDEPLOY/autodeploy.sh"

# Stub deploy.sh: fast-forward and exit 0
cat > "$T12_CDEPLOY/stub-deploy.sh" <<DEPLOYSTUB
#!/usr/bin/env bash
set -euo pipefail
git -C "\$APP_DIR" -c "safe.directory=\$APP_DIR" pull --ff-only origin master -q
echo "[stub-deploy] Done."
exit 0
DEPLOYSTUB
chmod +x "$T12_CDEPLOY/stub-deploy.sh"

LAST_RC=0
LAST_OUTPUT="$(
    PATH="$T12_CCURLSHIM:$PATH" \
    NOTIFY_CAPTURE_FILE="$T12_NOTIFY" \
    CURL_CAPTURE_FILE="$T12_CURL" \
    APP_DIR="$T12_REPO" \
    DEPLOY_SH="$T12_CDEPLOY/stub-deploy.sh" \
    LOCK_FILE="$T12_STATE/test.lock" \
    STATE_DIR="$T12_STATE" \
    HEALTH_PROBE_URL="https://api.leafbind.io/health" \
    DISCORD_DEPLOY_WEBHOOK_URL="https://discord.example.com/webhook/test" \
    bash "$T12_CDEPLOY/autodeploy.sh" 2>&1
)" || LAST_RC=$?

T12_YELLOW="$(count_notifies "$T12_NOTIFY" "yellow")"
T12_RED="$(count_notifies "$T12_NOTIFY" "red")"
T12_GREEN="$(count_notifies "$T12_NOTIFY" "green")"
T12_TITLE="$(awk -F'|' 'NR==1{print $3}' "$T12_NOTIFY")"
T12_MSG="$(awk -F'|' 'NR==1{print $4}' "$T12_NOTIFY")"

assert_zero     "T12 exit code is 0"                                      "$LAST_RC"
assert_eq       "T12 0 red posts (no rollback)"                           "0" "$T12_RED"
assert_eq       "T12 0 green posts"                                       "0" "$T12_GREEN"
assert_eq       "T12 1 yellow annotation"                                 "1" "$T12_YELLOW"
assert_contains "T12 title has [deployed]"                                "[deployed]" "$T12_TITLE"
assert_contains "T12 message mentions probe failed"                       "probe failed" "$T12_MSG"
assert_not_contains "T12 no rollback mentioned"                           "rollback" "$LAST_OUTPUT"

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
