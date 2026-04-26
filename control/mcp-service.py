#!/usr/bin/env python3
"""
mcp-service.py — mcp-valheim/control

Runs directly on the host (NOT in a container). Exposes Valheim server and
client lifecycle tools. Reports to the shared mcp-valheim knowledge MCP so
runtime/server logs accumulate alongside build output — closing the
deploy→feedback loop.

Steam process control lives in the sibling mcp-steam service (port 5174).

Register with Claude Code:
    claude mcp add valheim-control --transport http http://localhost:5173/mcp
"""

import os
import subprocess
from pathlib import Path

import psutil
from fastmcp import FastMCP
from mcp_knowledge_base import KnowledgeReporter

# ── Paths ─────────────────────────────────────────────────────────────────────

HOME       = Path.home()
SERVER_DIR = Path(os.environ.get("VALHEIM_SERVER_DIR", str(HOME / ".steam/steam/steamapps/common/Valheim dedicated server")))
CLIENT_DIR = Path(os.environ.get("VALHEIM_CLIENT_DIR", str(HOME / ".steam/steam/steamapps/common/Valheim")))
LOGS_DIR   = Path(os.environ.get("VALHEIM_LOGS_DIR",   str(HOME / "Projects/claude-sandbox/workspace/valheim/logs")))

VALHEIM_SERVER_CONTAINER = "valheim_server"
VALHEIM_SERVER_IMAGE     = "valheim_server"

LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── Knowledge reporter ────────────────────────────────────────────────────────

_reporter = KnowledgeReporter(service="valheim-control")
_report = _reporter.report


# ── MCP server ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="valheim-control",
    instructions=(
        "Tools for controlling the Valheim server container and client process on the host. "
        "Runs directly on the host — use these for anything that requires visibility into "
        "host processes or container management. "
        "Build tools are in the sibling valheim-build MCP (mcp-valheim/build, port 5182). "
        "Steam process control is in the sibling mcp-steam (port 5174)."
    ),
)


# ── Server lifecycle ──────────────────────────────────────────────────────────

@mcp.tool()
def start_server(vanilla: bool = False) -> str:
    """
    Start the Valheim dedicated server in a Docker container with BepInEx loaded.
    Builds the image first if it doesn't exist.

    Args:
        vanilla: If True, skip BepInEx and run the plain server (start_server.sh).
                 Default is False — BepInEx is always loaded unless explicitly bypassed.
    """
    script = "start_server.sh" if vanilla else "run_bepinex.sh"

    inspect = subprocess.run(
        ["docker", "inspect", VALHEIM_SERVER_IMAGE],
        capture_output=True,
    )
    if inspect.returncode != 0:
        build = subprocess.run(
            ["docker", "build", "docker", "-t", VALHEIM_SERVER_IMAGE],
            cwd=str(SERVER_DIR),
            capture_output=True, text=True,
        )
        if build.returncode != 0:
            result = f"IMAGE BUILD FAILED ✗\n\n{build.stderr}"
            _report("start_server", {"vanilla": vanilla}, result, False)
            return result

    log_path = LOGS_DIR / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w") as log:
        subprocess.Popen(
            ["docker", "run", "--rm",
             "--name", VALHEIM_SERVER_CONTAINER,
             "-v", "valheim_server_data:/root/.config/unity3d/IronGate/Valheim",
             "-v", f"{SERVER_DIR}:/irongate",
             "-v", f"{SERVER_DIR}/BepInEx:/opt/valheim-server/BepInEx",
             VALHEIM_SERVER_IMAGE, script],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    mode = "vanilla (no BepInEx)" if vanilla else "BepInEx"
    result = f"Server container starting [{mode}]. Monitor {log_path} for output."
    _report("start_server", {"vanilla": vanilla}, result, True)
    return result


@mcp.tool()
def stop_server() -> str:
    """Stop the Valheim server container gracefully (SIGTERM)."""
    proc = subprocess.run(
        ["docker", "stop", VALHEIM_SERVER_CONTAINER],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        result = f"STOP FAILED ✗\n\n{proc.stderr}"
        _report("stop_server", {}, result, False)
        return result
    result = "Server container stopped."
    _report("stop_server", {}, result, True)
    return result


@mcp.tool()
def kill_server() -> str:
    """Kill the Valheim server container immediately (SIGKILL)."""
    proc = subprocess.run(
        ["docker", "kill", VALHEIM_SERVER_CONTAINER],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        result = f"KILL FAILED ✗\n\n{proc.stderr}"
        _report("kill_server", {}, result, False)
        return result
    result = "Server container killed."
    _report("kill_server", {}, result, True)
    return result


# ── Client lifecycle ──────────────────────────────────────────────────────────

@mcp.tool()
def start_client(extra_args: list[str] = []) -> str:
    """
    Start the Valheim client via BepInEx. Non-blocking — check logs/client.log for startup progress.

    Args:
        extra_args: Additional flags appended to the launch command after all other arguments.
                    Example: ["-skipIntro"] skips the intro cutscene (also prevents Unity
                    freezing when the window loses focus during that sequence).
    """
    log_path = LOGS_DIR / "client.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["./run_bepinex.sh", "valheim.x86_64", "-console"] + extra_args
    with open(log_path, "w") as log:
        subprocess.Popen(
            cmd,
            cwd=str(CLIENT_DIR),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    result = f"Client start initiated. Monitor {log_path} for startup output."
    _report("start_client", {"extra_args": extra_args}, result, True)
    return result


@mcp.tool()
def stop_client() -> str:
    """Stop the Valheim client."""
    targets = [p for p in psutil.process_iter(["cmdline"])
               if "valheim.x86_64" in " ".join(p.info.get("cmdline") or [])]
    if not targets:
        result = "No valheim.x86_64 process found."
        _report("stop_client", {}, result, True)
        return result
    for p in targets:
        p.kill()
    psutil.wait_procs(targets, timeout=5)
    result = "Client stopped."
    _report("stop_client", {}, result, True)
    return result


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting valheim-control MCP on http://0.0.0.0:5173")
    print()
    print("Register with Claude Code:")
    print("  claude mcp add valheim-control --transport http http://localhost:5173/mcp")
    print()
    mcp.run(transport="streamable-http", host="0.0.0.0", port=5173)
