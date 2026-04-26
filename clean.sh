#!/usr/bin/env bash
# clean.sh — undo setup.sh AND remove built container images. Use to
# validate that setup.sh + the per-subdir build-container.sh scripts work
# from bare state (clean → setup → build → smoke test).
#
# Does NOT touch host-mounted state (knowledge/knowledge/ ChromaDB index)
# — that's data, not setup. Delete it manually if you want a totally
# fresh KB.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [ -d "$VENV" ]; then
    echo "Removing $VENV..."
    rm -rf "$VENV"
fi

for image in valheim-mcp-build valheim-mcp-knowledge; do
    if docker image inspect "$image" >/dev/null 2>&1; then
        echo "Removing image $image..."
        docker rmi -f "$image" >/dev/null
    fi
done

echo "Done."
