#!/usr/bin/env bash
# seed.sh — seed the mcp-knowledge database with docs and decompiled assembly
# Run from the host. Requires valheim-mcp-knowledge (port 5184) and mcp-build (port 5182).
set -euo pipefail

BASE="http://localhost:5184/mcp"
BUILD_BASE="http://localhost:5182/mcp"
DLL_PATH="/workspace/valheim/server/valheim_server_Data/Managed/assembly_valheim.dll"

# ---------------------------------------------------------------------------
# MCP session helpers
# ---------------------------------------------------------------------------

get_session() {
    local url="$1"
    curl -si -X POST "$url" \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"seed","version":"0"}}}' \
        2>/dev/null | grep -i 'mcp-session-id' | tr -d '\r' | awk '{print $2}'
}

call_tool() {
    local url="$1"
    local session="$2"
    local id="$3"
    local name="$4"
    local args="$5"
    local max_time="${6:-120}"
    RESPONSE=$(echo "{\"jsonrpc\":\"2.0\",\"id\":$id,\"method\":\"tools/call\",\"params\":{\"name\":\"$name\",\"arguments\":$args}}" \
        | curl -s -X POST "$url" \
            -H 'Content-Type: application/json' \
            -H 'Accept: application/json, text/event-stream' \
            -H "mcp-session-id: $session" \
            --data-binary @- \
            --max-time "$max_time")
    echo "$RESPONSE" | grep '^data:' | tail -1 | sed 's/^data: //' | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for c in d.get('result',{}).get('content',[]):
        if c.get('type')=='text': print(c['text'])
except: print('(parse error)')
" 2>/dev/null || echo "(no response)"
}

# ---------------------------------------------------------------------------
# Get sessions
# ---------------------------------------------------------------------------

echo "Connecting to mcp-knowledge..."
K_SESSION=$(get_session "$BASE")
if [ -z "$K_SESSION" ]; then
    echo "ERROR: Could not get MCP session from mcp-knowledge ($BASE)"
    exit 1
fi
echo "  Session: $K_SESSION"

echo "Connecting to mcp-build..."
B_SESSION=$(get_session "$BUILD_BASE")
if [ -z "$B_SESSION" ]; then
    echo "ERROR: Could not get MCP session from mcp-build ($BUILD_BASE)"
    exit 1
fi
echo "  Session: $B_SESSION"

# ---------------------------------------------------------------------------
# Seed docs
# ---------------------------------------------------------------------------

echo ""
echo "=== Seeding docs ==="
call_tool "$BASE" "$K_SESSION" 2 "seed_docs" '{"docs_path":"/opt/projects/mcp-valheim/docs"}'

# ---------------------------------------------------------------------------
# Decompile full DLL and seed
# ---------------------------------------------------------------------------

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo ""
echo "=== Decompiling assembly_valheim.dll (this may take a while) ==="
call_tool "$BUILD_BASE" "$B_SESSION" 3 "decompile_dll" "{\"container_path\":\"$DLL_PATH\"}" 600 \
    > "$TMPDIR/decompiled.txt"

# Strip the header line
sed -i '1{/^DECOMPILE/d;}' "$TMPDIR/decompiled.txt"

LINES=$(wc -l < "$TMPDIR/decompiled.txt")
if [ "$LINES" -lt 10 ]; then
    echo "ERROR: Decompile returned only $LINES lines"
    cat "$TMPDIR/decompiled.txt"
    exit 1
fi
echo "  Got $LINES lines of decompiled source"

echo ""
echo "=== Seeding decompiled source ==="
# Payload is too large for command-line args — build JSON in Python and pipe to curl
python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    source = f.read()
payload = {
    'jsonrpc': '2.0', 'id': 4,
    'method': 'tools/call',
    'params': {'name': 'seed_decompile', 'arguments': {'decompiled_source': source}}
}
sys.stdout.buffer.write(json.dumps(payload).encode())
" "$TMPDIR/decompiled.txt" \
    | curl -s -X POST "$BASE" \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -H "mcp-session-id: $K_SESSION" \
        --data-binary @- \
        --max-time 300 \
    | grep '^data:' | tail -1 | sed 's/^data: //' \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for c in d.get('result',{}).get('content',[]):
        if c.get('type')=='text': print(c['text'])
except: print('(parse error)')
" 2>/dev/null || echo "(no response)"

# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

echo ""
echo "=== Stats ==="
call_tool "$BASE" "$K_SESSION" 5 "stats" '{}'

echo ""
echo "Done."
