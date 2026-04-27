#!/usr/bin/env bash
# start.sh — bring up all three mcp-valheim services.
# Idempotent: each inner script revives an existing container or creates a new one.
# Host venv is provisioned by setup.sh on first run (idempotent thereafter).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure host-side venv (for control/) exists. Cheap if already built.
"$SCRIPT_DIR/setup.sh"

echo "Starting valheim-mcp-build..."
"$SCRIPT_DIR/build/start-container.sh"

echo "Starting valheim-control (host process, port 5173)..."
"$SCRIPT_DIR/control/start-mcp-service.sh" >"$SCRIPT_DIR/control.log" 2>&1 &
echo "  background PID $! (logs: $SCRIPT_DIR/control.log)"

echo "Starting valheim-mcp-knowledge..."
"$SCRIPT_DIR/knowledge/start-container.sh"

echo "Done. Services on :5182 (build), :5173 (control), :5184 (knowledge)."
