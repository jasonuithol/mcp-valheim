# mcp-knowledge — Valheim Modding Knowledge Service

A RAG-backed MCP service that stores and retrieves modding knowledge learned
from decompiling game assemblies, building mods, debugging failures, and
shipping to Thunderstore. Runs as a container alongside `build/` and
`control/` (sibling subdirs in this repo) inside `claude-sandbox-core`'s
`valheim` domain.

---

## Goal

Replace the static docs in `mcp-valheim/docs/MODDING_*.md` with a
living knowledge base that grows automatically as mods are built. The docs
remain the curated reference — the RAG layer adds the deep, hard-won detail
that doesn't fit neatly into documentation.

---

## Architecture

```
mcp-valheim (this repo)
│
├── build/      (port 5182, container)  — build, deploy, package, publish, download
├── control/    (port 5173, host)       — server/client lifecycle
└── knowledge/  (port 5184, container)  — THIS SERVICE: RAG knowledge base
```

### Design Principle: Passive Ingest, Active Query

Knowledge accumulates **automatically** — not because anyone remembers to
record it, but because every tool execution in mcp-build and mcp-control
reports what happened to mcp-knowledge.

The RAG service owns **all ingest logic**. The other services are dumb
reporters — they fire a payload and move on. mcp-knowledge decides what's
worth keeping.

```
mcp-build / mcp-control tool executes
    ↓
returns result to caller (unchanged — no latency added)
    ↓
fires async POST to mcp-knowledge /ingest
    {tool, args, result, success}
    ↓ (fire-and-forget, silent on failure)
mcp-knowledge receives payload and decides:
    → build failure?     index the error
    → decompile output?  chunk by method, index each
    → publish succeeded? index the mod's manifest + source
    → routine deploy?    skip, not interesting
```

### Decoupling Rules

- mcp-build and mcp-control **never block** on mcp-knowledge. The POST is
  async and fire-and-forget. If mcp-knowledge is down, nothing breaks.
- mcp-build and mcp-control **never decide** what's worth indexing. They send
  everything; mcp-knowledge filters.
- Ingest logic (chunking, tagging, deduplication) lives **only** in
  mcp-knowledge. The other services send raw payloads.
- Claude can still call mcp-knowledge MCP tools directly for manual ingest
  or queries — the automatic pipeline doesn't replace that.

### Ingest Payload Format

Every tool execution in mcp-build and mcp-control sends:

```json
{
    "tool": "build",
    "args": {"project": "NightTerrors"},
    "result": "BUILD FAILED ✗\n\nerror CS1002: ; expected...",
    "success": false,
    "timestamp": "2026-04-12T07:45:00Z",
    "service": "mcp-build"
}
```

Sent as `POST http://localhost:5184/ingest` (plain HTTP, not MCP). This is a
lightweight sidecar endpoint, not an MCP tool — it doesn't need session
management or JSON-RPC framing.

### Reporter Integration (mcp-build / mcp-control)

Reporters use `KnowledgeReporter` from the shared `mcp-knowledge-base`
package. The endpoint URL comes from `$KNOWLEDGE_URL` (set in each
service's `start-container.sh` to `http://localhost:5184/ingest`).

```python
from mcp_knowledge_base import KnowledgeReporter

reporter = KnowledgeReporter(service="mcp-build")  # or "mcp-control"
```

Called at the end of every tool function:

```python
@mcp.tool()
async def build(project: str) -> str:
    cwd = str(PROJECT_DIR / project)
    success, log = await _run_async(...)
    header = "BUILD SUCCEEDED ✓" if success else "BUILD FAILED ✗"
    result = f"{header}\n\n{log}"
    reporter.report("build", {"project": project}, result, success)
    return result
```

The reporter is fire-and-forget and never raises — see
`mcp_knowledge_base.reporter` for the canonical implementation (5 s
timeout, tz-aware UTC timestamps).

### Container layout

```
mcp-valheim/knowledge/
├── CLAUDE.md              ← this file
├── Dockerfile
├── build-container.sh
├── start-container.sh
├── mcp-service.py         ← FastMCP server (query tools) + /ingest HTTP endpoint
├── ingest/
│   ├── router.py          ← decides what to do with each payload by tool name
│   ├── chunker.py         ← splits decompiled source, logs, code into chunks
│   └── extractors.py      ← source-specific extraction (errors, methods, patterns)
├── knowledge/             ← ChromaDB persistent storage (mounted volume, gitignored)
└── requirements.txt       ← fastmcp, chromadb, httpx
```

---

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| MCP framework | FastMCP | Same as mcp-build — consistent stack |
| Vector DB | ChromaDB (PersistentClient) | File-based, no server, Python-native, good enough for this scale |
| Embeddings | ChromaDB's default (all-MiniLM-L6-v2) | Runs locally in the container, no API key needed, fast |
| Chunking | Custom per source type | Modding knowledge has natural boundaries (class, method, pattern) |
| Transport | HTTP, streamable (MCP) + plain HTTP (/ingest) | MCP for Claude queries, plain HTTP for service-to-service ingest |

ChromaDB's built-in embedding model runs on CPU and is fine for this corpus
size (thousands of chunks, not millions). If embedding quality becomes an
issue, swap to the Anthropic Voyage embeddings or `nomic-embed-text` later.

---

## MCP Tools (Query — Called by Claude)

| Tool | Args | Description |
|------|------|-------------|
| `ask(question)` | `question: str` | Semantic search — returns the top 5 most relevant chunks with source metadata |
| `ask_class(class_name)` | `class_name: str` | Find all indexed knowledge about a specific Valheim class |
| `ask_tagged(question, tags)` | `question: str, tags: list[str]` | Filtered search — restrict results by tags like `"rpc"`, `"zdo"`, `"weather"` |

## MCP Tools (Maintenance — Called by Claude)

| Tool | Args | Description |
|------|------|-------------|
| `list_sources()` | none | List all indexed sources with chunk counts |
| `forget(source)` | `source: str` | Remove all chunks from a source |
| `stats()` | none | Collection size, source breakdown, tag distribution |
| `seed_docs(docs_path)` | `docs_path: str` | One-time: index the curated MODDING_*.md docs |
| `seed_decompile(class_name)` | `class_name: str` | One-time: decompile a class via mcp-build and index it |

## Ingest Router (Automatic — Driven by Tool Payloads)

The `/ingest` endpoint receives every tool execution and routes by tool name:

| Tool payload | Action | Tags |
|-------------|--------|------|
| `build` (failure) | Index error message, extract CS error codes | `build-error`, project name |
| `build` (success after prior failure) | Index error→fix pair from consecutive payloads | `build-fix`, project name |
| `build` (success, no prior failure) | Skip — routine success isn't interesting | — |
| `decompile_dll` | Chunk output by method, index each method | `decompile`, class name, auto-detected patterns |
| `deploy_server` / `deploy_client` | Skip — routine, no knowledge value | — |
| `package` | Skip — routine | — |
| `publish` (success) | Index manifest metadata + flag for source code ingest | `publish`, project name, mod name |
| `publish` (failure) | Index the error (auth, validation, etc.) | `publish-error`, project name |
| `start_server` / `stop_server` | Skip | — |
| `start_client` / `stop_client` | Skip | — |

The router maintains a small in-memory buffer of recent payloads to detect
sequences (e.g. build failure → build success = error/fix pair).

---

## Knowledge Sources

### 1. Decompiled assemblies (highest value)

Chunked by class and method from `assembly_valheim.dll` and related DLLs.
Each chunk includes:

- Full decompiled method source
- Class name and method name as metadata
- Auto-generated tags based on content (e.g. method uses `ZRoutedRpc` → tag `"rpc"`)

Ingested automatically when `decompile_dll` is called, or manually via
`seed_decompile("Player")`.

### 2. Curated docs (seed data)

The curated docs in `mcp-valheim/docs/` are the seed corpus:

- `MODDING_TOOLCHAIN.md` — build environment, csproj template, BepInEx setup
- `MODDING_PLUGIN_BASICS.md` — plugin boilerplate, server/client detection
- `MODDING_HARMONY.md` — patching patterns, parameter matching
- `MODDING_NETWORKING.md` — RPCs, ZRoutedRpc, Jotunn RPCs
- `MODDING_ZDO.md` — ZDO state, equipment/emote detection, ZDOVars reference
- `MODDING_WORLD.md` — weather, teleportation, world gen, raids
- `MODDING_PLAYER.md` — inventory, emotes, audio, death handling
- `MODDING_CONFIG.md` — BepInEx config, custom config, FileSystemWatcher
- `MODDING_PACKAGING.md` — Thunderstore package structure, build/publish pipeline
- `MODDING_GOTCHAS.md` — consolidated pitfall table
- `MODDING_MESSAGING.md` — ShowMessage, ChatMessage, UI
- `VALHEIM_MCP.md` — MCP tool reference and architecture

Indexed via `seed_docs()` — chunked by `## ` header sections, tagged by
filename and detected topics.

### 3. Build failures and fixes

Captured automatically via the ingest pipeline. When a `build` payload
arrives with `success: false`, the error is stashed. If the next `build`
for the same project succeeds, the error→fix pair is indexed together.

### 4. Mod source code (known-good patterns)

After a successful `publish` payload, mcp-knowledge can fetch the mod's
source from the mounted projects volume, chunk by class, and index as
working examples. Tagged with the mod name and detected patterns.

### 5. Decompile output

Every `decompile_dll` call automatically feeds its output into
mcp-knowledge. The chunker splits by method/class boundaries and indexes
each chunk with class name, method name, and auto-detected tags.

---

## Chunking Strategy

Different sources need different chunking:

| Source | Chunk boundary | Typical chunk size |
|--------|---------------|-------------------|
| Decompiled DLL | One chunk per method | 20-200 lines |
| Docs | One chunk per `## ` section | 10-100 lines |
| Build errors | One chunk per error + fix pair | 5-30 lines |
| Mod source | One chunk per class | 50-500 lines |

Keep chunks small enough to be precise but large enough to be self-contained.
Each chunk must make sense on its own without needing the chunks around it.

---

## Metadata Schema

Every chunk stored in ChromaDB carries:

```python
{
    "source": "decompile/assembly_valheim/Player",  # where it came from
    "type": "method",                                 # method | section | error | pattern
    "class_name": "Player",                           # if applicable
    "method_name": "StartEmote",                      # if applicable
    "tags": "emote,player,animation",                 # comma-separated, for display
    "indexed_at": "2026-04-12T07:45:00Z",            # when it was added
    "project": "",                                    # if from a specific mod project
    # Plus one boolean key per tag, used for `where`-clause filtering in
    # ask_tagged (ChromaDB metadata has no $contains operator):
    "tag_emote": True,
    "tag_player": True,
    "tag_animation": True,
}
```

---

## Container Setup

### Dockerfile

Based on `python:3.12-slim-bookworm` (same as mcp-build). Installs:
- `fastmcp` — MCP server
- `chromadb` — vector DB + built-in embeddings
- `httpx` — for calling mcp-build (decompile during seeding)

### Volumes

```
-v "$HOME/Projects/mcp-valheim/knowledge/knowledge:/opt/knowledge"
-v "$HOME/Projects:/opt/projects:ro"
```

- `/opt/knowledge` — ChromaDB persistent storage, survives rebuilds
- `/opt/projects` — read-only access to mod source code for post-publish indexing

### Network

`--network host` — same as mcp-build. Listens on port 5184.
- MCP endpoint: `http://localhost:5184/mcp` (Claude queries)
- Ingest endpoint: `http://localhost:5184/ingest` (service-to-service)

### Registration

```bash
claude mcp add valheim-knowledge --transport http http://localhost:5184/mcp
```

---

## Seed Workflow

First-time setup after the service is running:

1. Index the curated docs:
   ```
   seed_docs("/opt/projects/mcp-valheim/docs")
   ```

2. Decompile and index the key classes:
   ```
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

After seeding, the knowledge base grows automatically from normal tool usage.

---

## Non-Goals

- Not a replacement for the curated docs — those stay as the authoritative,
  human-reviewed reference
- Not a general-purpose knowledge base — scoped to Valheim modding only
- Not a hosted service — runs locally alongside the other MCP services
- No fine-tuning or model training — pure retrieval, the LLM does the reasoning

---

## Known Concerns & Ideas

### 1. Payload buffer doesn't survive restarts

The in-memory buffer that tracks recent payloads (for detecting build
failure→success pairs) is lost when the container restarts. If the container
bounces between a failed build and its fix, that error→fix pair is gone.

**Idea:** Persist the buffer to `/opt/knowledge/buffer.json` on every write.
It's a small file (last ~20 payloads) and the volume already survives
rebuilds. Load it on startup.

### 2. No deduplication on re-index

If someone decompiles `Player` twice, do we get duplicate chunks? The
metadata schema has `source` and `indexed_at` but nothing prevents the same
content from being indexed again.

**Idea:** Use deterministic ChromaDB IDs derived from `source + chunk index`
(e.g. `decompile/assembly_valheim/Player/StartEmote`). Upserting with the
same ID replaces instead of duplicating. Alternatively, call
`forget(source)` before re-indexing — simpler, but briefly leaves a gap
where queries against that source return nothing.

### 3. Ingest endpoint is unauthenticated

`/ingest` is plain HTTP with no auth. Fine for `--network host` on a local
machine, but if the container is ever exposed beyond localhost, anything can
push data into the knowledge base.

**Idea:** Accept this for now — document that the endpoint must only be
reachable from localhost. If the network model ever changes, add a shared
secret via environment variable and check it in a header
(`X-Ingest-Token`).

### 4. Seed workflow requires mcp-build

`seed_decompile` calls mcp-build to do the actual decompilation. If you're
standing up mcp-knowledge for the first time, mcp-build must already be
running. The seed workflow section doesn't mention this.

**Idea:** Add a prerequisite note to the seed workflow section. Optionally,
have `seed_decompile` check mcp-build health first and return a clear error
instead of a connection failure.

### 5. Large payloads may be silently dropped

`KnowledgeReporter` uses a 5-second timeout. Big decompile outputs —
which are the highest-value payloads — are the most likely to exceed
that limit and get silently dropped.

**Idea:** Pass a longer `timeout=` when constructing the reporter for
services that emit large payloads, or have the `/ingest` endpoint accept
the payload immediately, return 202, and do the chunking/indexing in a
background task.

### 6. ~~ChromaDB `$contains` is case-sensitive~~ — misdiagnosed, now fixed

**Original note claimed** the issue was case sensitivity on `$contains`. That
was wrong. The real problem: ChromaDB's metadata `where` clause has **no
`$contains` operator at all** — it's only valid in a `where_document` clause
against chunk bodies. The old `ask_tagged` implementation passed
`{"tags": {"$contains": t}}` as a metadata filter, which silently returned
zero matches regardless of case.

**Fix (2026-04-20):** tags are now stored as individual boolean metadata
keys (`tag_rpc: True`, `tag_successful_example: True`, ...) in addition to
the comma-joined `tags` string kept for display. `ask_tagged` filters via
`{"tag_<name>": True}` (or `$and` of those for multi-tag queries). Tag names
are normalised via `tag_key()` in `ingest/chunker.py` — lowercase,
non-alphanumeric → underscore (so `status-effect` → `tag_status_effect`).

Existing chunks were retrofitted via the `backfill_tag_keys()` MCP tool,
which can be re-run idempotently if needed.
