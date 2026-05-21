#!/usr/bin/env bash
#
# refresh-cloudflare-ips.sh — EB-324 Unit 8
#
# Fetches Cloudflare's current published IP ranges and rewrites the
# allowlist block in deploy/nginx.conf between the sentinel comments:
#
#     # BEGIN CLOUDFLARE IPS (managed by deploy/refresh-cloudflare-ips.sh — do not edit by hand)
#     ...allow lines...
#     # END CLOUDFLARE IPS
#
# Then validates with `nginx -t` and reloads. Run monthly per the runbook
# in deploy/CLOUDFLARE.md. Cloudflare changes its ranges rarely, but a
# stale allowlist that drops a newly-added Cloudflare range would 403
# legitimate traffic from that edge.
#
# Usage:
#   sudo deploy/refresh-cloudflare-ips.sh [path-to-nginx.conf]
#
# Defaults to /etc/nginx/sites-available/leafbind (the deployed copy). Pass
# an explicit path to dry-run against the repo copy.
#
# Exit codes:
#   0  success (file rewritten, nginx -t passed, reload issued)
#   1  fetch failure (Cloudflare IP endpoints unreachable)
#   2  sentinel markers not found in target file
#   3  nginx -t validation failed (file left rewritten for inspection;
#      reload NOT issued)

set -euo pipefail

NGINX_CONF="${1:-/etc/nginx/sites-available/leafbind}"
V4_URL="https://www.cloudflare.com/ips-v4"
V6_URL="https://www.cloudflare.com/ips-v6"
BEGIN_MARKER="# BEGIN CLOUDFLARE IPS"
END_MARKER="# END CLOUDFLARE IPS"

if [[ ! -f "$NGINX_CONF" ]]; then
    echo "ERROR: nginx config not found: $NGINX_CONF" >&2
    exit 2
fi

if ! grep -qF "$BEGIN_MARKER" "$NGINX_CONF" || ! grep -qF "$END_MARKER" "$NGINX_CONF"; then
    echo "ERROR: sentinel markers not found in $NGINX_CONF" >&2
    echo "       Expected '$BEGIN_MARKER' ... '$END_MARKER'" >&2
    exit 2
fi

echo "Fetching Cloudflare IP ranges..."
v4="$(curl -fsS "$V4_URL" || true)"
v6="$(curl -fsS "$V6_URL" || true)"
if [[ -z "$v4" || -z "$v6" ]]; then
    echo "ERROR: failed to fetch Cloudflare IP lists (v4 or v6 empty)" >&2
    exit 1
fi

# Build the replacement allow-block.
block_file="$(mktemp)"
trap 'rm -f "$block_file"' EXIT
{
    echo "    $BEGIN_MARKER (managed by deploy/refresh-cloudflare-ips.sh — do not edit by hand)"
    while IFS= read -r cidr; do
        [[ -n "$cidr" ]] && echo "    allow $cidr;"
    done <<< "$v4"
    while IFS= read -r cidr; do
        [[ -n "$cidr" ]] && echo "    allow $cidr;"
    done <<< "$v6"
    echo "    $END_MARKER"
} > "$block_file"

# Replace everything between the markers (inclusive) with the new block.
tmp_conf="$(mktemp)"
trap 'rm -f "$block_file" "$tmp_conf"' EXIT
awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" -v blockfile="$block_file" '
    $0 ~ begin { print_block=1; while ((getline line < blockfile) > 0) print line; close(blockfile); skip=1; next }
    $0 ~ end   { skip=0; next }
    skip != 1  { print }
' "$NGINX_CONF" > "$tmp_conf"

cp "$tmp_conf" "$NGINX_CONF"
echo "Rewrote Cloudflare allowlist in $NGINX_CONF"

echo "Validating nginx config..."
if ! nginx -t; then
    echo "ERROR: nginx -t failed. Config rewritten but NOT reloaded — inspect $NGINX_CONF" >&2
    exit 3
fi

echo "Reloading nginx..."
nginx -s reload
echo "Done. Cloudflare allowlist refreshed and nginx reloaded."
