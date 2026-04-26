# mcp-valheim

MCP service pair for Valheim mod development (BepInEx / dotnet / Thunderstore). Two containers:

| Subdir | Container | Port | Purpose |
|--------|-----------|------|---------|
| `service/` | `valheim-mcp-build` | 5182 | dotnet build, Thunderstore packaging, BepInEx scaffolding |
| `knowledge/` | `valheim-mcp-knowledge` | 5184 | RAG over Valheim/BepInEx/Unity APIs, project source, curated docs |

The two halves are paired: `service/` fires fire-and-forget POSTs at
`knowledge/`'s `/ingest` endpoint, so build errors and other signals
accumulate as retrievable context.

## Consumers

Currently launched by [`claude-sandbox`](../claude-sandbox/) via its
`start.sh`. Any MCP client speaking streamable HTTP can mount these
services — the protocol is provider-agnostic.

## Usage

```bash
# Build images (first time, or after Dockerfile changes)
service/build-container.sh
knowledge/build-container.sh

# Start
service/start-container.sh
knowledge/start-container.sh

# First-time KB seed
knowledge/seed.sh
```

Both containers use host networking (ports above). The knowledge
container needs an NVIDIA GPU + container toolkit for accelerated
embeddings.
