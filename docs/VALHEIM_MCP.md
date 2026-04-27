# Valheim Development Environment

This document describes how to control the Valheim server and client from inside
the Claude Code container using the MCP tool servers.

## Architecture

Three MCP services run on the host. `mcp-build` runs in a container (heavy
build tools). `mcp-control` runs as a host process (needs access to host
processes and container management). `mcp-knowledge` runs in a container
(RAG knowledge base). Both mcp-build and mcp-control report every tool
execution to mcp-knowledge via fire-and-forget HTTP POST.

```
Podman (on host)
│
├── claude-sandbox          Claude Code
│       │
│       ├──── HTTP (port 5182) ────────────────────────────────────┐
│       │                                                           ▼
│       │                                             mcp-build    (port 5182, container)
│       │                                                  │
│       │                                                  ├── dotnet build     (mod builds)
│       │                                                  ├── ilspycmd         (decompile DLLs)
│       │                                                  ├── rsvg-convert     (SVG→PNG)
│       │                                                  └── POST /ingest ──────────┐
│       │                                                                               │
│       ├──── HTTP (port 5173) ────────────────────────────────────┐                    │
│       │                                                           ▼                    │
│       │                                             mcp-control  (port 5173, host)     │
│       │                                                  │                              │
│       │                                                  ├── docker (server container)  │
│       │                                                  ├── psutil (Steam/client)      │
│       │                                                  └── POST /ingest ──────────┐  │
│       │                                                                               │  │
│       └──── HTTP (port 5184) ────────────────────────────────────┐                    │  │
│                                                                   ▼                    │  │
│                                                     mcp-knowledge (port 5184, container)◄─┘
│                                                          │
│                                                          ├── ChromaDB    (vector store)
│                                                          ├── /ingest     (auto-learns from tool use)
│                                                          └── MCP tools   (ask, ask_class, stats, etc.)
│
├── valheim_server          Valheim dedicated server (managed by mcp-control)
│
└── [host]
        └── Valheim client  (Steam/native — started/stopped by mcp-control)
```

## Setup

### Prerequisites

Ensure the Podman socket is running:

```bash
systemctl --user enable --now podman.socket
```

### 1. Build the mcp-build image (once)

```bash
~/Projects/claude-sandbox/mcp-build/build-container.sh
```

This installs Python, dotnet SDK, ilspycmd, and rsvg-convert into the image.
Takes a few minutes on first build.

### 2. Start mcp-build

```bash
~/Projects/claude-sandbox/mcp-build/start-container.sh
```

Starts the container and listens on port 5182.

### 3. Start mcp-control (on the host)

```bash
~/Projects/claude-sandbox/mcp-control/start-mcp-service.sh
```

Runs directly on the host (no container). Listens on port 5173.
Handles server/client lifecycle and Steam status.

### 4. Register both with Claude Code (once, inside the claude-sandbox container)

```bash
~/Projects/claude-sandbox/claude/register-services.sh
```

Verify the connection with `/mcp` inside any Claude Code session.

### 5. Refresh the path map if the claude-sandbox container is restarted

The path map (used by `decompile_dll` and `convert_svg` to translate container
paths to host paths) is built when mcp-build starts. If claude-sandbox is
restarted, call `refresh_path_map()` to rebuild it without restarting mcp-build.

---

## MCP Tools

### Build and Deploy (`valheim-build`, port 5182)

These tools are **blocking** — they run to completion and return the full log.

| Tool | Argument | Description |
|------|----------|-------------|
| `build(project)` | Project folder name | `dotnet build -c Release` |
| `deploy_server(project)` | Project folder name | Copy DLLs and configs to server BepInEx dirs |
| `deploy_client(project)` | Project folder name | Copy DLLs and configs to client BepInEx dirs |
| `package(project)` | Project folder name | Bundle mod into Thunderstore zip |
| `publish(project, community)` | Project folder name, community slug (default: `"valheim"`) | Upload packaged zip to Thunderstore |

`project` is a folder name under `~/Projects` with no path separators,
e.g. `"ValheimRainDance"`. Always build and verify success before deploying
or packaging. Always build and package before publishing.

### Thunderstore Publishing

`publish` requires a `THUNDERSTORE_TOKEN` environment variable. Place your
service account token (format `tss_XXXX`) in `mcp-build/.env`:

```
THUNDERSTORE_TOKEN=tss_your_token_here
```

This file is gitignored. The token is loaded automatically by
`start-container.sh` and passed into the container.

### Decompiling Assemblies (`valheim-build`)

```
decompile_dll(container_path)
```

Decompiles a DLL with `ilspycmd` and returns the source. Pass the path as
seen from inside the claude-sandbox container:

```
/workspace/valheim/server/valheim_server_Data/Managed/assembly_valheim.dll
```

Output is also written to `logs/ilspy.log`. Output can be large for complex
assemblies — filter or grep as needed.

### Converting SVG to PNG (`valheim-build`)

```
convert_svg(container_path)
```

Converts an SVG to a 256×256 PNG using `rsvg-convert`. Pass the path as
seen from inside the claude-sandbox container:

```
/workspace/ValheimRainDance/ThunderstoreAssets/icon.svg
```

Output PNG is written next to the source SVG with a `.png` extension, suitable
for Thunderstore mod icons.

### Utility (`valheim-build`)

```
refresh_path_map()
```

Rebuilds the path map from environment variables. Only needed if mount paths
have changed since mcp-build started (rare — the map is static by default).

### Server Control (`valheim-control`, port 5173)

The dedicated server runs as a Docker container (`valheim_server`).

| Tool | Description |
|------|-------------|
| `start_server(vanilla)` | Start the server container. Builds the image if needed. `vanilla=False` (default) loads BepInEx; `vanilla=True` runs plain `start_server.sh` |
| `stop_server()` | Stop the server container gracefully (`docker stop`) |
| `kill_server()` | Kill the server container immediately (`docker kill`) |

#### Server config files (adminlist, bannedlist, etc.)

The server container uses a **named podman volume** (`valheim_server_data`)
mounted at `/root/.config/unity3d/IronGate/Valheim`. This is where the server
reads `adminlist.txt`, `bannedlist.txt`, and `permittedlist.txt` at runtime.

On the host, this volume lives at:
```
~/.local/share/containers/storage/volumes/valheim_server_data/_data/
```

Edit that copy directly — it is NOT the same as `~/.config/unity3d/IronGate/Valheim/`
(which is the client's copy and is not mapped into the container).

Use the `Steam_` prefix format for player IDs (e.g. `Steam_44445555666677788`).

### Client Control and Steam (`valheim-control`)

| Tool | Description |
|------|-------------|
| `steam_status()` | Check whether Steam is running on the host |
| `start_steam()` | Launch Steam on the host. Non-blocking |
| `start_client(extra_args)` | Start the client via `run_bepinex.sh`. Non-blocking. `extra_args` (list, default `[]`) are appended after all other flags — e.g. `["-skipIntro"]` |
| `stop_client()` | Stop the client process |

### Knowledge Base (`valheim-knowledge`, port 5184)

RAG-backed knowledge service. Grows automatically from tool use — every tool
execution in mcp-build and mcp-control reports to mcp-knowledge via
fire-and-forget POST. See `INGEST_MCP.md` for full
usage docs.

| Tool | Description |
|------|-------------|
| `ask(question)` | Semantic search across all knowledge (top 5 results) |
| `ask_class(class_name)` | Find all indexed knowledge about a specific Valheim class |
| `ask_tagged(question, tags)` | Semantic search filtered by tags (lowercase only) |
| `stats()` | Collection size, source breakdown, tag distribution |
| `list_sources()` | All indexed sources with chunk counts |
| `forget(source)` | Delete all chunks from a source |
| `seed_docs(docs_path)` | One-time: index the curated MODDING_*.md docs |
| `seed_decompile(class_name)` | One-time: decompile a class via mcp-build and index it |

#### First-time seeding

After starting mcp-knowledge for the first time, seed with the curated docs
and key Valheim classes:

```
seed_docs("/opt/projects/claude-sandbox/claude/docs")
seed_decompile("Player")
seed_decompile("ZRoutedRpc")
seed_decompile("ZDOVars")
seed_decompile("EnvMan")
seed_decompile("ZNetPeer")
seed_decompile("Bed")
seed_decompile("RandEventSystem")
seed_decompile("VisEquipment")
seed_decompile("ZSyncAnimation")
```

Run `stats()` afterwards to confirm. After seeding, knowledge grows
automatically from normal tool usage.

---

## Logs

All tool logs are written to `~/Projects/claude-sandbox/workspace/valheim/logs/` on the host
(mounted into the mcp-build container at `/opt/workspace/valheim/logs/`),
and are also returned directly in the tool response.

| File | Written by |
|------|------------|
| `logs/build.log` | `build` |
| `logs/deploy-server.log` | `deploy_server` |
| `logs/deploy-client.log` | `deploy_client` |
| `logs/package.log` | `package` |
| `logs/publish.log` | `publish` |
| `logs/ilspy.log` | `decompile_dll` |
| `logs/svg-to-png.log` | `convert_svg` |
| `logs/server.log` | `start_server` (server container stdout) |
| `logs/client.log` | `start_client` (client process stdout) |

Each log is overwritten on each run and includes timestamps at start and end.

---

## BepInEx

BepInEx is installed on both server and client. Plugin and config directories
are writable from inside the claude-sandbox container:

| Location | Path (in claude-sandbox) |
|----------|--------------------------|
| Server plugins | `/workspace/valheim/server/BepInEx/plugins/` |
| Client plugins | `/workspace/valheim/client/BepInEx/plugins/` |
| Server config | `/workspace/valheim/server/BepInEx/config/` |
| Client config | `/workspace/valheim/client/BepInEx/config/` |

BepInEx logs are at:

- Server: `/workspace/valheim/server/BepInEx/LogOutput.log`
- Client: `/workspace/valheim/client/BepInEx/LogOutput.log`

> **Warning:** The server log only stays live if the BepInEx volume mount is in place.
> `start_server` in mcp-control mounts `{SERVER_DIR}/BepInEx` → `/opt/valheim-server/BepInEx`
> inside the container. Without this mount the container writes to its own internal path and
> the file at `/workspace/valheim/server/BepInEx/LogOutput.log` goes stale after the first run.

---

## Testing the MCP Servers

To test from the host without Claude Code, use the helper scripts:

```bash
# Get a session ID
~/Projects/claude-sandbox/get-mcp-session-id.sh

# List tools (requires httpx — available in .venv)
source ~/Projects/claude-sandbox/.venv/bin/activate
python3 - <<'EOF'
import httpx, json
base = 'http://localhost:5182/mcp'  # or 5173 for mcp-control, 5184 for mcp-knowledge
h = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
r = httpx.post(base, headers=h, json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'test','version':'0'}}})
h['mcp-session-id'] = r.headers['mcp-session-id']
r2 = httpx.post(base, headers=h, json={'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})
tools = json.loads(r2.text.split('data: ')[1])['result']['tools']
for t in tools: print(t['name'])
EOF
```

---

## Files

| File | Purpose |
|------|---------|
| `mcp-build/mcp-service.py` | Build MCP implementation (container, port 5182) |
| `mcp-build/Dockerfile` | Build MCP container image definition |
| `mcp-build/build-container.sh` | Build the container image |
| `mcp-build/start-container.sh` | Start the container |
| `mcp-control/mcp-service.py` | Control MCP implementation (host process, port 5173) |
| `mcp-control/start-mcp-service.sh` | Start the control MCP server on the host |
| `mcp-knowledge/` | Knowledge RAG service (container, port 5184) — see `mcp-knowledge/CLAUDE.md` |

---

## Notes

- Build and deploy tools block until complete — do not call multiple
  build/deploy tools simultaneously.
- Server and client start tools are non-blocking — check logs to confirm
  successful startup.
- The package zip is written to `release/<teamname>-<modname>-<version>.zip`
  inside the project directory. If `ThunderstoreAssets/CHANGELOG.md` exists
  it is included in the zip.
- Path environment variables can override default mount points:
  `VALHEIM_SERVER_DIR`, `VALHEIM_CLIENT_DIR`, `VALHEIM_PROJECT_DIR`, `VALHEIM_LOGS_DIR`.
- All tool executions in mcp-build and mcp-control are reported to
  mcp-knowledge (`localhost:5184/ingest`) via fire-and-forget HTTP POST.
  If mcp-knowledge is not running, the reports are silently dropped.
