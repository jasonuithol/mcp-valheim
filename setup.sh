#!/usr/bin/env bash
# setup.sh — one-time setup for mcp-valheim. Idempotent: safe to re-run.
#
# Sets up the host-side venv used by control/ (the build/ and knowledge/
# subdirs run in containers built by their own build-container.sh scripts —
# they have no host-side install step).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV" ]; then
    echo "Creating virtualenv at $VENV..."
    python3 -m venv "$VENV"
fi

echo "Installing/upgrading host-side dependencies (control/)..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$SCRIPT_DIR/control/requirements.txt"

echo
echo "Host-side setup done. To build the container subdirs:"
echo "  $SCRIPT_DIR/build/build-container.sh"
echo "  $SCRIPT_DIR/knowledge/build-container.sh"
