#!/usr/bin/env bash
# Installs the Python dependencies needed by the `matt` CLI / matter_cli.py
# on a standalone Linux host (e.g. Rocky Linux 9 / RHEL 9).
#
# Usage:
#   ./install.sh
#
# This uses python3 -m pip so it works whether or not pip is on PATH,
# and installs for the current user only (no sudo/root required).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[FAIL] python3 not found. Install it first (e.g. sudo dnf install -y python3 python3-pip)."
    exit 1
fi

echo "Installing Python dependencies from requirements.txt ..."
python3 -m pip install --user -r "${SCRIPT_DIR}/requirements.txt"

echo "[OK] Dependencies installed."
echo ""
echo "Next steps (see README.md section 5 to install 'matt' onto your PATH):"
echo "  chmod +x ${SCRIPT_DIR}/matt ${SCRIPT_DIR}/matter_cli.py"
echo "  sudo cp ${SCRIPT_DIR}/matt ${SCRIPT_DIR}/matter_cli.py /usr/local/bin/"
