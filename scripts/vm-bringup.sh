#!/usr/bin/env bash
# vm-bringup.sh — Idempotent EbookAutomation VM setup for claude-dev-01
#
# Usage:
#   ssh root@claude-dev-01 'bash -s' < scripts/vm-bringup.sh
#
# After running: populate ~/EbookAutomation/.env with real API keys (mode 0600).
# See .env.template in the repo for required keys.
#
# Tested on Ubuntu 24.04 (Hetzner Cloud, 2026-05-14, EB-210).

set -euo pipefail

REPO_URL="https://github.com/jlfowler1084/EbookAutomation.git"
REPO_DIR="$HOME/EbookAutomation"
VENV_DIR="$REPO_DIR/.venv"
DATA_DIR="$HOME/ebook-data"

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
echo "=== [1/5] Installing system packages ==="

apt-get update -q

# Core pipeline dependencies
apt-get install -y -q \
    python3.12 \
    python3.12-venv \
    python3-pip \
    calibre \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    ocrmypdf \
    ghostscript \
    git \
    git-lfs

# PowerShell 7 via Microsoft apt repo (idempotent — skipped if already enrolled)
if ! command -v pwsh &>/dev/null; then
    echo "  Installing PowerShell 7..."
    apt-get install -y -q wget apt-transport-https software-properties-common
    wget -q "https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb"
    dpkg -i packages-microsoft-prod.deb
    rm packages-microsoft-prod.deb
    apt-get update -q
    apt-get install -y -q powershell
else
    echo "  pwsh already installed: $(pwsh --version)"
fi

# Verify critical tools
echo "  ebook-convert: $(ebook-convert --version 2>&1 | head -1)"
echo "  tesseract: $(tesseract --version 2>&1 | head -1)"
echo "  ocrmypdf: $(ocrmypdf --version 2>&1)"
echo "  pwsh: $(pwsh --version)"

# ---------------------------------------------------------------------------
# 2. Repo clone / update
# ---------------------------------------------------------------------------
echo "=== [2/5] Repo setup ==="

if [ -d "$REPO_DIR/.git" ]; then
    echo "  Repo exists — pulling latest..."
    git -C "$REPO_DIR" pull --ff-only
else
    echo "  Cloning repo..."
    git clone "$REPO_URL" "$REPO_DIR"
fi

# ---------------------------------------------------------------------------
# 3. Python venv + dependencies
# ---------------------------------------------------------------------------
echo "=== [3/5] Python venv and dependencies ==="

if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "  Creating venv..."
    python3.12 -m venv "$VENV_DIR"
fi

echo "  Installing requirements..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$REPO_DIR/requirements.txt"

# ---------------------------------------------------------------------------
# 4. Working directories
# ---------------------------------------------------------------------------
echo "=== [4/5] Working directories ==="

mkdir -p "$DATA_DIR"/{inbox,processing,archive,output}
echo "  Created: $DATA_DIR/{inbox,processing,archive,output}"

# ---------------------------------------------------------------------------
# 5. .env check
# ---------------------------------------------------------------------------
echo "=== [5/5] Environment file check ==="

ENV_FILE="$REPO_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo "  .env present"
    # Ensure mode 0600 (credential protection)
    chmod 600 "$ENV_FILE"
else
    echo "  WARNING: $ENV_FILE not found."
    echo "  Copy .env.template to .env and populate API keys before running the pipeline:"
    echo "    cp $REPO_DIR/.env.template $REPO_DIR/.env"
    echo "    chmod 600 $REPO_DIR/.env"
    echo "    \$EDITOR $REPO_DIR/.env"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== VM bring-up complete ==="
echo "  Repo:         $REPO_DIR"
echo "  Venv:         $VENV_DIR"
echo "  Data dirs:    $DATA_DIR/{inbox,processing,archive,output}"
echo "  Logs:         $REPO_DIR/logs/"
echo ""
echo "Next: populate .env, then run the P4 functional gate:"
echo "  source $VENV_DIR/bin/activate"
echo "  python $REPO_DIR/tools/pdf_to_balabolka.py --input <pdf> --output-dir $DATA_DIR/output"
