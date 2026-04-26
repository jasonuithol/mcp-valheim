#!/usr/bin/env bash
# reset-knowledge.sh — wipe the ChromaDB knowledge base and restart
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KNOWLEDGE_DIR="$SCRIPT_DIR/knowledge"

echo "This will delete all indexed knowledge in $KNOWLEDGE_DIR"
read -rp "Continue? [y/N] " confirm
if [[ "$confirm" != [yY] ]]; then
    echo "Aborted."
    exit 0
fi

# Stop the container
docker rm -f mcp-knowledge 2>/dev/null || true

# Wipe the data
rm -rf "$KNOWLEDGE_DIR"
mkdir -p "$KNOWLEDGE_DIR"

echo "Knowledge base wiped."
echo "Run start-container.sh to restart, then seed.sh to re-seed."
