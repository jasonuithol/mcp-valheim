#!/usr/bin/env bash
# build-container.sh — build the valheim MCP server container image
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Building valheim-mcp-build image..."
docker build -f "$SCRIPT_DIR/Dockerfile" -t valheim-mcp-build "$SCRIPT_DIR"
echo "Done. Run with: $SCRIPT_DIR/start-container.sh"
