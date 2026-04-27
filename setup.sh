#!/usr/bin/env bash
# setup.sh — one-time setup for mcp-valheim. Idempotent: safe to re-run.
#
# Provisions:
#   - .venv/ (host-side, used by control/)
#   - valheim-mcp-build container image
#   - valheim-mcp-knowledge container image
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

# ── Host venv for control/ ────────────────────────────────────────────────────

if [ ! -d "$VENV" ]; then
    echo "Creating virtualenv at $VENV..."
    python3 -m venv "$VENV"
fi

echo "Installing/upgrading host-side dependencies (control/)..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$SCRIPT_DIR/control/requirements.txt"

# ── Container images ──────────────────────────────────────────────────────────

declare -A SUBDIR=( [valheim-mcp-build]=build [valheim-mcp-knowledge]=knowledge )

for image in valheim-mcp-build valheim-mcp-knowledge; do
    if docker image inspect "$image" >/dev/null 2>&1; then
        echo "Image $image already built — skipping."
    else
        echo "Building image $image..."
        "$SCRIPT_DIR/${SUBDIR[$image]}/build-container.sh"
    fi
done

echo "Done."
