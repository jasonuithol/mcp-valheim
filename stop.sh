#!/usr/bin/env bash
# stop.sh — shut down all three mcp-valheim services.
#
# Default: SIGTERM (docker stop / fuser -TERM).
# --kill:  SIGKILL (docker kill / fuser -KILL). Containers are left in
#          place for revival; full removal is in ./clean.sh.
set -euo pipefail

FORCE=false
[ "${1:-}" = "--kill" ] && FORCE=true

stop_container() {
    local name="$1"
    echo "Stopping $name..."
    if $FORCE; then
        docker kill "$name" 2>/dev/null && echo "  killed" || echo "  not running"
    else
        docker stop "$name" 2>/dev/null && echo "  stopped" || echo "  not running"
    fi
}

stop_host_port() {
    local label="$1"
    local port="$2"
    echo "Stopping $label (port $port)..."
    if $FORCE; then
        fuser -k -KILL "$port/tcp" 2>/dev/null && echo "  killed" || echo "  not running"
    else
        fuser -k -TERM "$port/tcp" 2>/dev/null && echo "  stopped" || echo "  not running"
    fi
}

stop_container valheim-mcp-build
stop_host_port valheim-control 5173
stop_container valheim-mcp-knowledge

echo "Done."
