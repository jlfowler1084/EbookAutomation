#!/usr/bin/env bash
# tests/deploy/test_discord_notify.sh
#
# Plain-bash test suite for deploy/discord-notify.sh.
# bats is NOT installed; this is a self-contained runner.
#
# Usage (from repo root OR tests/deploy/):
#   bash tests/deploy/test_discord_notify.sh
#
# curl shim strategy:
#   discord_notify calls `curl` inside a command-substitution subshell
#   (http_status="$(curl ...)"), so shell-variable assignments inside the
#   shim don't propagate back to the outer shell. Instead, the shim writes
#   the captured arguments to a temp file that the parent process reads after
#   discord_notify returns. This is a clean, portable capture pattern that
#   avoids modifying production code for testability.
#
# Exit code: 0 all tests passed, 1 one or more tests failed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export REPO_ROOT

# ---------------------------------------------------------------------------
# Mini test framework
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
FAILURES=()

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() {
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
        fail "$label — expected return 0, got $rc"
    fi
}
assert_valid_json() {
    local label="$1" json="$2"
    if echo "$json" | jq . >/dev/null 2>&1; then
        pass "$label"
    else
        fail "$label — invalid JSON: $json"
    fi
}

# ---------------------------------------------------------------------------
# run_test <label> <script_body>
#
# Runs the script body in a fresh bash -c subshell with REPO_ROOT exported.
# Sets T_RC to the exit code. The script body can write to $T_CAPTURE_FILE
# (a temp file the caller creates) for out-of-band result extraction.
# ---------------------------------------------------------------------------
T_CAPTURE_FILE="$(mktemp)"
cleanup() { rm -f "$T_CAPTURE_FILE"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Shared curl-shim body: writes captured payload+url to T_CAPTURE_FILE,
# then echoes the desired HTTP status (read from T_SHIM_STATUS env var,
# default "204") and exits with T_SHIM_EXIT (default 0).
# ---------------------------------------------------------------------------
# We inject a curl shim script as a real file on PATH so that it is found
# by discord_notify's `curl ...` call regardless of subshell depth.

T_SHIM_DIR="$(mktemp -d)"
cleanup() { rm -f "$T_CAPTURE_FILE"; rm -rf "$T_SHIM_DIR"; }
trap cleanup EXIT

cat > "$T_SHIM_DIR/curl" <<'CURLSHIM'
#!/usr/bin/env bash
# Test shim for curl. Writes the -d payload and URL to $T_CAPTURE_FILE,
# returns T_SHIM_STATUS (default 204) and exits T_SHIM_EXIT (default 0).
PAYLOAD=""
URL=""
prev=""
for arg in "$@"; do
    if [[ "$prev" == "-d" ]]; then
        PAYLOAD="$arg"
    fi
    case "$arg" in
        http://*|https://*) URL="$arg" ;;
    esac
    prev="$arg"
done

if [[ -n "${T_CAPTURE_FILE:-}" ]]; then
    printf '%s\n---URL---\n%s\n' "$PAYLOAD" "$URL" >> "$T_CAPTURE_FILE"
fi

echo "${T_SHIM_STATUS:-204}"
exit "${T_SHIM_EXIT:-0}"
CURLSHIM
chmod +x "$T_SHIM_DIR/curl"
export T_SHIM_DIR

# ---------------------------------------------------------------------------
# TEST 1: Happy path — green embed, color int 3066993, one curl call
# ---------------------------------------------------------------------------
echo ""
echo "TEST 1: Happy path (green, payload captured via shim)"

> "$T_CAPTURE_FILE"
export T_CAPTURE_FILE
T1_RC=0
bash -c '
    export PATH="$T_SHIM_DIR:$PATH"
    export T_CAPTURE_FILE T_SHIM_STATUS=204 T_SHIM_EXIT=0
    source "$REPO_ROOT/deploy/discord-notify.sh"
    export DISCORD_DEPLOY_WEBHOOK_URL="https://discord.example.com/webhook/test"
    discord_notify green "Deploy succeeded" "Deployed abc..def (3 commits)"
' || T1_RC=$?

T1_PAYLOAD="$(sed '/^---URL---/,$d' "$T_CAPTURE_FILE")"
T1_URL="$(sed -n '/^---URL---/{n;p}' "$T_CAPTURE_FILE")"
# count how many times the shim was called (each call appends a ---URL--- block)
T1_CALLS="$(grep -c '^---URL---$' "$T_CAPTURE_FILE" 2>/dev/null; true)"

assert_zero     "T1 function returns 0"          "$T1_RC"
assert_eq       "T1 curl called once"            "1"                                        "$T1_CALLS"
assert_eq       "T1 URL is the webhook"          "https://discord.example.com/webhook/test" "$T1_URL"
assert_valid_json "T1 payload is valid JSON"     "$T1_PAYLOAD"
assert_contains "T1 title present"               '"title"'                                  "$T1_PAYLOAD"
assert_contains "T1 description present"         '"description"'                            "$T1_PAYLOAD"
assert_contains "T1 footer present"              '"footer"'                                 "$T1_PAYLOAD"
# Use jq to extract the actual color value (jq output is pretty-printed; compact grep is unreliable)
T1_COLOR="$(echo "$T1_PAYLOAD" | jq -r '.embeds[0].color' 2>/dev/null || echo '')"
assert_eq "T1 color int is 3066993" "3066993" "$T1_COLOR"
# Use jq to extract footer text and match ISO-8601 UTC pattern
T1_FOOTER_TEXT="$(echo "$T1_PAYLOAD" | jq -r '.embeds[0].footer.text' 2>/dev/null || echo '')"
if echo "$T1_FOOTER_TEXT" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'; then
    pass "T1 footer is ISO-8601 UTC"
else
    fail "T1 footer is ISO-8601 UTC — got: $T1_FOOTER_TEXT"
fi

# ---------------------------------------------------------------------------
# TEST 2: Unset DISCORD_DEPLOY_WEBHOOK_URL → return 0, warning, no curl call
# ---------------------------------------------------------------------------
echo ""
echo "TEST 2: Unset DISCORD_DEPLOY_WEBHOOK_URL — must return 0, warning, no curl call"

> "$T_CAPTURE_FILE"
T2_RC=0
T2_STDERR="$(bash -c '
    export PATH="$T_SHIM_DIR:$PATH"
    export T_CAPTURE_FILE T_SHIM_STATUS=204 T_SHIM_EXIT=0
    source "$REPO_ROOT/deploy/discord-notify.sh"
    unset DISCORD_DEPLOY_WEBHOOK_URL
    discord_notify green "test" "body"
' 2>&1)" || T2_RC=$?

T2_CALLS="$(grep -c '^---URL---$' "$T_CAPTURE_FILE" 2>/dev/null; true)"
assert_zero "T2 function returns 0 when URL unset" "$T2_RC"
assert_eq   "T2 curl NOT called"                   "0" "$T2_CALLS"
if echo "$T2_STDERR" | grep -qi "unset\|skipping\|warning"; then
    pass "T2 warning logged to stderr"
else
    fail "T2 warning logged — no warning keyword found in: $T2_STDERR"
fi

# ---------------------------------------------------------------------------
# TEST 3: HTTP 500 response → return 0, log warning
# ---------------------------------------------------------------------------
echo ""
echo "TEST 3: POST failure (HTTP 500) — must return 0, log warning"

> "$T_CAPTURE_FILE"
T3_RC=0
T3_STDERR="$(bash -c '
    export PATH="$T_SHIM_DIR:$PATH"
    export T_CAPTURE_FILE T_SHIM_STATUS=500 T_SHIM_EXIT=0
    source "$REPO_ROOT/deploy/discord-notify.sh"
    export DISCORD_DEPLOY_WEBHOOK_URL="https://discord.example.com/webhook/test"
    discord_notify red "Deploy failed" "Something broke"
    echo "RETURNED:0"
' 2>&1)" || T3_RC=$?

assert_zero "T3 function returns 0 on HTTP 500" "$T3_RC"
if echo "$T3_STDERR" | grep -q "RETURNED:0"; then
    pass "T3 execution reached end of function"
else
    fail "T3 execution reached end of function — output: $T3_STDERR"
fi
if echo "$T3_STDERR" | grep -qi "500\|warning\|http"; then
    pass "T3 warning about bad HTTP status logged"
else
    fail "T3 warning about bad HTTP status logged — output: $T3_STDERR"
fi

# ---------------------------------------------------------------------------
# TEST 3b: curl network error (shim exits non-zero) → return 0
# ---------------------------------------------------------------------------
echo ""
echo "TEST 3b: POST failure (curl network error / exit 7) — must return 0"

> "$T_CAPTURE_FILE"
T3B_RC=0
T3B_STDERR="$(bash -c '
    export PATH="$T_SHIM_DIR:$PATH"
    export T_CAPTURE_FILE T_SHIM_STATUS=000 T_SHIM_EXIT=7
    source "$REPO_ROOT/deploy/discord-notify.sh"
    export DISCORD_DEPLOY_WEBHOOK_URL="https://discord.example.com/webhook/test"
    discord_notify red "Deploy failed" "network error"
    echo "RETURNED:0"
' 2>&1)" || T3B_RC=$?

assert_zero "T3b function returns 0 on curl network error" "$T3B_RC"
if echo "$T3B_STDERR" | grep -q "RETURNED:0"; then
    pass "T3b execution reached end of function after curl failure"
else
    fail "T3b execution reached end of function — output: $T3B_STDERR"
fi

# ---------------------------------------------------------------------------
# TEST 4: JSON escaping — message with quotes and newline → valid JSON
# ---------------------------------------------------------------------------
echo ""
echo "TEST 4: JSON escaping — message with double-quotes and literal newline"

> "$T_CAPTURE_FILE"
T4_RC=0
bash -c '
    export PATH="$T_SHIM_DIR:$PATH"
    export T_CAPTURE_FILE T_SHIM_STATUS=204 T_SHIM_EXIT=0
    source "$REPO_ROOT/deploy/discord-notify.sh"
    export DISCORD_DEPLOY_WEBHOOK_URL="https://discord.example.com/webhook/test"
    TRICKY_MSG="Deploy \"succeeded\" with note:
second line here"
    discord_notify red "Title with \"quotes\"" "$TRICKY_MSG"
' || T4_RC=$?

T4_PAYLOAD="$(sed '/^---URL---/,$d' "$T_CAPTURE_FILE")"
assert_zero       "T4 function returns 0"                                "$T4_RC"
assert_valid_json "T4 payload with quotes+newline is valid JSON"         "$T4_PAYLOAD"
assert_contains   "T4 description field present" '"description"'        "$T4_PAYLOAD"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
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
