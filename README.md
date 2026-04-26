# mcp-valheim

MCP service pair for Valheim mod development (BepInEx / dotnet / Thunderstore). Two containers:

| Subdir | Container | Port | Purpose |
|--------|-----------|------|---------|
| `build/` | `valheim-mcp-build` | 5182 | dotnet build, Thunderstore packaging, BepInEx scaffolding |
| `control/` | host process | 5173 | Valheim server/client lifecycle (host-runner — needs psutil + GUI) |
| `knowledge/` | `valheim-mcp-knowledge` | 5184 | RAG over Valheim/BepInEx/Unity APIs, project source, curated docs |

`build/` and `control/` both fire fire-and-forget POSTs at `knowledge/`'s
`/ingest` endpoint, so build errors AND runtime/server logs accumulate as
retrievable context — closing the loop between deploy and feedback.

## Consumers

Currently launched by [`claude-sandbox`](../claude-sandbox/) via its
`start.sh`. Any MCP client speaking streamable HTTP can mount these
services — the protocol is provider-agnostic.

## Usage

```bash
# Build images (first time, or after Dockerfile changes)
build/build-container.sh
knowledge/build-container.sh

# Start
build/start-container.sh
control/start-mcp-service.sh   # host-runner, no container
knowledge/start-container.sh

# First-time KB seed
knowledge/seed.sh
```

Both containers use host networking (ports above). The knowledge
container needs an NVIDIA GPU + container toolkit for accelerated
embeddings.
