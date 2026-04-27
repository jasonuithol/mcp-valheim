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

Launched by [`claude-sandbox-core`](https://github.com/jasonuithol/claude-sandbox-core)
via `bin/start.sh valheim <project>` (the `valheim` domain conf lists
this repo in `MCP_REPOS`). Any MCP client speaking streamable HTTP can
mount these services — the protocol is provider-agnostic.

## Usage

```bash
./setup.sh                       # one-time: host venv (control/) + build images
./start.sh                       # bring up build + control + knowledge
./stop.sh                        # shut everything down
./clean.sh                       # remove venv + containers + images

knowledge/seed.sh                # first-time KB seed
```

To validate setup works from bare state:

```bash
./clean.sh && ./setup.sh && ./start.sh
```

Both containers use host networking (ports above). The knowledge
container needs an NVIDIA GPU + container toolkit for accelerated
embeddings.
