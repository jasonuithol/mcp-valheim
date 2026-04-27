# Valheim Modding — Server Admin Commands

---

## Dedicated Server Console Access

### F5 Console — Does NOT work on dedicated servers

Even if a player's Steam ID is listed in `adminlist.txt`, the `devcommands` command (and all cheat/admin commands) are **disabled by the engine** on dedicated servers. This is a Valheim engine-level restriction, not a configuration issue.

- `devcommands` only works in local singleplayer worlds
- Being on `adminlist.txt` grants in-game moderation powers (kick, ban) but NOT cheat commands

### Options for Admin/Dev Commands on Dedicated Servers

**Option 1 — "Server Devcommands" mod (recommended)**

The mod by JereKuusela (available on Thunderstore/Nexusmods) re-enables `devcommands` for players listed in `adminlist.txt` on dedicated servers. Widely used and maintained.

- Thunderstore: search "Server Devcommands"
- After installing on server + client, admins can use F5 console commands normally

**Option 2 — Server process stdin**

The Valheim dedicated server process accepts console commands on stdin. If you can attach to the server process you can type commands directly:

```bash
docker attach <container_name>
```

This requires `docker` to be available in the environment. The valheim-control MCP does not currently expose a "send console command" tool.

**Option 3 — Custom BepInEx command mod**

Write a server-side BepInEx plugin that listens for commands via a socket, file watcher, or HTTP endpoint, and executes them via `ZRoutedRpc` or direct game API calls. Useful if you need automated/scripted server control.

---

## adminlist.txt

Located at `/workspace/valheim/server/adminlist.txt` (or the server's working directory). Format is one Steam ID per line, prefixed with `Steam_`:

```
Steam_76561197992112559
```

Grants in-game moderation (kick/ban) but NOT devcommands without the Server Devcommands mod.
