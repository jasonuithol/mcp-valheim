#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The embedding model is baked into the image (see Dockerfile) — no
# host-side download.
docker build -t valheim-mcp-knowledge "$SCRIPT_DIR"
