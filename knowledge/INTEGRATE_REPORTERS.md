# Integrate Knowledge Reporting into mcp-build and mcp-control

Both services already use the canonical `KnowledgeReporter` from the
shared `mcp-knowledge-base` package. This doc describes the integration
shape so that any new sibling service (or a new tool added to an
existing one) follows the same pattern.

---

## What you're doing

Every `@mcp.tool()` function fires a fire-and-forget HTTP POST to
`mcp-knowledge`'s `/ingest` endpoint with the tool name, args, result,
and success flag. If the knowledge service is down, nothing breaks — the
POST silently fails.

---

## Step 1: Construct the reporter

Add this near the top of the service's main file, after imports:

```python
from mcp_knowledge_base import KnowledgeReporter

reporter = KnowledgeReporter(service="mcp-build")  # or "mcp-control", etc.
```

`KnowledgeReporter` reads its target URL from `$KNOWLEDGE_URL` (set in
each service's `start-container.sh` to `http://localhost:5184/ingest`
for the valheim stack, `:5174` for pygame, `:5176` for dos-re). Default
timeout is 5 seconds; pass `timeout=` to override.

---

## Step 2: Add `reporter.report(...)` to every tool function

One call at the end of each `@mcp.tool()`, just before the `return`.
Don't change the return value. Don't await it. Don't wrap existing
logic in try/except for reporting purposes — `KnowledgeReporter` never
raises.

### Pattern

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

### What to pass

| Argument | Value |
|----------|-------|
| `tool` | The function name as a string: `"build"`, `"decompile_dll"`, `"publish"`, etc. |
| `args` | A dict of the meaningful arguments. Don't include large blobs — just the identifiers (project name, class name, dll name, etc.) |
| `result` | The return value string (the same thing being returned to the caller) |
| `success` | `True` if the operation succeeded, `False` if it failed. Most tools already track this. If a tool doesn't have a clear success/failure, pass `True`. |

---

## Step 3: Verify the package is pinned

`mcp-knowledge-base` should be in `requirements.txt` for each
reporter-side service, pinned to the same tag the server side uses
(currently `v0.2.1`):

```
mcp-knowledge-base @ git+https://github.com/.../mcp-knowledge-base.git@v0.2.1
```

The reporter itself only depends on `httpx`; the heavier server-side
dependencies (chromadb, fastmcp, …) are gated behind the `[server]`
extra and aren't pulled in for reporter consumers.

---

## Step 4: Rebuild and restart

```bash
cd ~/Projects/mcp-valheim/build
./build-container.sh
./start-container.sh
```

`mcp-control` runs on the host venv — `pip install -r requirements.txt`
plus a process restart is sufficient.

---

## Every tool needs a report call

Don't skip any. The knowledge service decides what's interesting; the
reporters send everything. See `mcp-knowledge/ingest/router.py` for the
current routing logic, and `mcp-knowledge/CLAUDE.md` for the design
rationale.

---

## Checklist

- [ ] `KnowledgeReporter` instance constructed in the service main file
- [ ] Every `@mcp.tool()` calls `reporter.report(...)` before its `return`
- [ ] `mcp-knowledge-base` pinned in `requirements.txt`
- [ ] `KNOWLEDGE_URL` env var set in `start-container.sh`
- [ ] Container rebuilt / host service restarted
- [ ] Smoke test: `curl -X POST $KNOWLEDGE_URL -H 'Content-Type: application/json' -d '{"tool":"test","args":{},"result":"hello","success":true,"timestamp":"2026-04-26T00:00:00Z","service":"test"}'` returns `{"action":"skipped_unknown","chunks":0}`
