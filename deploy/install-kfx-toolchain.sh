#!/usr/bin/env bash
# install-kfx-toolchain.sh — bootstrap/rebuild/manual ONLY. Not for the deploy tick.
# Run as root (handles apt + WineHQ repo); drops to `sudo -u joe` for user-space.
# Idempotent: safe to re-run. Versions/checksums are PINNED below — update only
# after re-validating on the box.
#
# EB-332: installs the PDF -> KFX backend that EB-221's bootstrap missed:
# Wine + a `joe` Wine prefix + Amazon Kindle Previewer 3 (headless via xvfb-run)
# + the Calibre KFX Output plugin. The cheap counterpart for the routine deploy
# tick is verify-kfx-toolchain.sh (installs nothing, alerts on regression).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "must run as root"; exit 1; }

JOE_HOME="/home/joe"
WINE_VERSION="__PIN_DURING_SPIKE__"          # e.g. 9.0~focal-1  (A2)
KP3_URL="__PIN_DURING_SPIKE__"               # Amazon installer URL (A3)
KP3_SHA256="__PIN_DURING_SPIKE__"            # checksum of the downloaded installer
KP3_CACHE="$JOE_HOME/.cache/kfx/KindlePreviewerInstaller.exe"
KFX_PLUGIN_URL="__PIN_DURING_SPIKE__"        # KFX Output plugin zip (jhowell/MobileRead)
KFX_PLUGIN_SHA256="__PIN_DURING_SPIKE__"
KFX_PLUGIN_CACHE="$JOE_HOME/.cache/kfx/KFXOutput.zip"

echo "[1/5] Wine (root, pinned $WINE_VERSION) — A2"      # apt + WineHQ repo
echo "[2/5] Wine prefix for joe — A2"                    # sudo -u joe wineboot
echo "[3/5] Kindle Previewer 3 under Wine (headless) — A3"
echo "[4/5] Calibre KFX Output plugin (verify) — A3"
echo "[5/5] Final end-to-end KFX smoke — A4"
echo "Skeleton only — steps land as the spike confirms them."
