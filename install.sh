#!/usr/bin/env bash
# PG3 install script.
#
# PG3 runs this after cloning/updating the node server to install its
# Python dependencies. It may be invoked with the venv's python path as
# $1, or with no arguments at all (in which case we fall back to
# whatever "python3"/"pip3" is active, which PG3 sets up as the node
# server's own virtual environment before running this script).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_BIN="$1"
if [ -z "$PYTHON_BIN" ] || ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    else
        PYTHON_BIN="python"
    fi
fi

echo "Installing PMatter dependencies with: ${PYTHON_BIN}"
"${PYTHON_BIN}" -m pip install -r "${SCRIPT_DIR}/requirements.txt"
