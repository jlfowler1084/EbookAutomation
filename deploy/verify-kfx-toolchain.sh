#!/usr/bin/env bash
# verify-kfx-toolchain.sh — cheap KFX readiness probe for the routine deploy tick.
# Installs nothing. Exit 0 = ready, 1 = a prerequisite is missing (alert).
#
# EB-332: the heavy installer (install-kfx-toolchain.sh) runs only at
# bootstrap/rebuild/manual. The routine ~5-minute autodeploy tick runs THIS
# probe instead — it asserts the KFX toolchain is still present and alerts on
# regression, without apt, downloads, or snapshots.
set -euo pipefail

JOE_HOME="/home/joe"
fail=0
note() { echo "[kfx-verify] $*"; }

command -v wine >/dev/null 2>&1 || { note "MISSING: wine not on PATH"; fail=1; }
[ -f "$JOE_HOME/.wine/system.reg" ] || { note "MISSING: wine prefix $JOE_HOME/.wine"; fail=1; }

# KFX Output plugin registered in calibre (run as joe).
if ! sudo -u joe calibre-customize --list-plugins 2>/dev/null | grep -qi 'KFX Output'; then
  note "MISSING: Calibre 'KFX Output' plugin not registered"; fail=1
fi

# Kindle Previewer present (path frozen by the installer; placeholder until A3).
KP_EXE="${KINDLE_PREVIEWER:-$JOE_HOME/.wine/drive_c/Kindle Previewer 3/Kindle Previewer 3.exe}"
[ -f "$KP_EXE" ] || { note "MISSING: Kindle Previewer at $KP_EXE"; fail=1; }

if [ "$fail" -ne 0 ]; then note "KFX toolchain NOT ready"; exit 1; fi
note "KFX toolchain ready"
