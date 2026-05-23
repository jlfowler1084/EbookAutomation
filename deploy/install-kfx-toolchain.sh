#!/usr/bin/env bash
# install-kfx-toolchain.sh — bootstrap/rebuild/manual ONLY. Not for the deploy tick.
# Run as root (handles apt + WineHQ repo); drops to `sudo -u joe` for user-space.
# Idempotent: safe to re-run.
#
# EB-332: installs the PDF -> KFX backend that EB-221's bootstrap missed:
# wine-staging + a `joe` Wine prefix + Amazon Kindle Previewer 3 (headless via
# xvfb) + verifies the Calibre KFX Output plugin. The cheap counterpart for the
# routine deploy tick is verify-kfx-toolchain.sh (installs nothing).
#
# Spike-validated 2026-05-23 on claude-dev-01 (Ubuntu 24.04 noble).
#
# *** CRITICAL: wine-STAGING is required — NOT wine-stable. ***
# winehq-stable 11.0.0.0~noble-1 crashes KP3 3.104's renderer with a
# deterministic access violation (0xC0000005 at "Kindle Previewer 3.exe"+0x7F9C)
# on every launch — immune to all env-var/winetricks tuning. winehq-staging
# 11.9~noble-1 runs it and produces a valid KFX. Do not "simplify" to stable.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "must run as root"; exit 1; }

JOE="joe"
JOE_HOME="/home/joe"
WINEPREFIX="$JOE_HOME/.wine"
WINE_PKG_VERSION="11.9~noble-1"   # winehq-STAGING — stable crashes KP3 (see header)
KP3_URL="https://d2bzeorukaqrvt.cloudfront.net/KindlePreviewerInstaller.exe"
KP3_SHA256="9eb06c65bb6fbaaf4b3101e54b57c3f509bc4ff5c8de2fedea8449b0d4703d08"
KP3_CACHE="$JOE_HOME/.cache/kfx/KindlePreviewerInstaller.exe"
KP3_EXE="$WINEPREFIX/drive_c/users/$JOE/AppData/Local/Amazon/Kindle Previewer 3/Kindle Previewer 3.exe"

as_joe() { sudo -u "$JOE" env HOME="$JOE_HOME" WINEPREFIX="$WINEPREFIX" "$@"; }

echo "[1/6] base deps (xvfb, curl, ca-certificates)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends xvfb curl ca-certificates

echo "[2/6] WineHQ repo (noble) + i386 architecture"
dpkg --add-architecture i386
mkdir -pm755 /etc/apt/keyrings
[ -f /etc/apt/keyrings/winehq-archive.key ] || \
  wget -nv -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key
[ -f /etc/apt/sources.list.d/winehq-noble.sources ] || \
  wget -nv -NP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/ubuntu/dists/noble/winehq-noble.sources
apt-get update -qq

echo "[3/6] wine-staging $WINE_PKG_VERSION (NOT stable — see header)"
apt-get install -y --install-recommends "winehq-staging=$WINE_PKG_VERSION"
wine --version

echo "[4/6] wine prefix for $JOE (win64, headless)"
if [ ! -f "$WINEPREFIX/system.reg" ]; then
  as_joe WINEARCH=win64 WINEDLLOVERRIDES="mscoree,mshtml=" xvfb-run -a wineboot --init
else
  echo "  prefix exists — updating"
  as_joe WINEDLLOVERRIDES="mscoree,mshtml=" xvfb-run -a wineboot -u || true
fi
as_joe wineserver -w || true

echo "[5/6] Kindle Previewer 3 (cached, checksum-pinned, silent install)"
sudo -u "$JOE" mkdir -p "$(dirname "$KP3_CACHE")"
if ! echo "$KP3_SHA256  $KP3_CACHE" | sha256sum -c - >/dev/null 2>&1; then
  echo "  downloading KP3 installer (~355 MB)"
  sudo -u "$JOE" curl -fsSL -o "$KP3_CACHE" "$KP3_URL"
  echo "$KP3_SHA256  $KP3_CACHE" | sha256sum -c -
fi
if [ ! -f "$KP3_EXE" ]; then
  as_joe xvfb-run -a wine "$KP3_CACHE" /S
  as_joe wineserver -w || true
fi
[ -f "$KP3_EXE" ] || { echo "ERROR: KP3 not found after install: $KP3_EXE"; exit 1; }

echo "[6/6] verify Calibre KFX Output plugin is registered"
if ! sudo -u "$JOE" calibre-customize --list-plugins | grep -qi 'KFX Output'; then
  echo "ERROR: Calibre 'KFX Output' plugin not registered."
  echo "       Install it: sudo -u $JOE calibre-customize --add-plugin <KFXOutput.zip>"
  exit 1
fi

cat <<NOTE
KFX toolchain install complete.
  wine: $(wine --version)
  KP3 : $KP3_EXE

The conversion subprocess (ebook-convert -> KP3) requires, at runtime:
  HOME=$JOE_HOME  WINEPREFIX=$WINEPREFIX
  QTWEBENGINE_DISABLE_SANDBOX=1
  QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu"
  ... and a virtual X display (xvfb), because KP3 is a GUI app.
These must be provided to ebookweb.service (A4). vcrun2022 was installed during
the spike but is believed unnecessary (KP3 bundles its own VCRUNTIME140/MSVCP140).
NOTE
