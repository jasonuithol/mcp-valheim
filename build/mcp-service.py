#!/usr/bin/env python3
"""
mcp-service.py — mcp-build

Runs inside a Docker container. Exposes mod build, deploy, package,
decompile, and SVG conversion tools to Claude Code.

Register with Claude Code (run this inside the claude-sandbox container):
    claude mcp add valheim-build --transport http http://localhost:5182/mcp

Or on the host directly:
    claude mcp add valheim-build --transport http http://localhost:5182/mcp
"""

import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path

import httpx
from fastmcp import FastMCP
from mcp_knowledge_base import KnowledgeReporter

# ── Paths ─────────────────────────────────────────────────────────────────────

import os

HOME        = Path.home()
SERVER_DIR  = Path(os.environ.get("VALHEIM_SERVER_DIR",  str(HOME / ".steam/steam/steamapps/common/Valheim dedicated server")))
CLIENT_DIR  = Path(os.environ.get("VALHEIM_CLIENT_DIR",  str(HOME / ".steam/steam/steamapps/common/Valheim")))
PROJECT_DIR = Path(os.environ.get("VALHEIM_PROJECT_DIR", str(HOME / "Projects")))
LOGS_DIR    = Path(os.environ.get("VALHEIM_LOGS_DIR",    str(HOME / "Projects/claude-sandbox/workspace/valheim/logs")))

LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── Container → host path map ─────────────────────────────────────────────────
#
# Translates paths as seen inside claude-sandbox to paths inside this container.
# Built statically from env vars — no docker socket required.
#
# Claude-sandbox mounts              →  This container's paths
#   CLAUDE_SERVER_MOUNT              →  SERVER_DIR
#   CLAUDE_CLIENT_MOUNT              →  CLIENT_DIR
#   CLAUDE_PROJECT_MOUNT/<project>   →  PROJECT_DIR/<project>
#
# Override the CLAUDE_* vars if claude-sandbox uses non-default workspace paths.

_CLAUDE_SERVER_MOUNT  = os.environ.get("CLAUDE_SERVER_MOUNT",  "/workspace/valheim/server")
_CLAUDE_CLIENT_MOUNT  = os.environ.get("CLAUDE_CLIENT_MOUNT",  "/workspace/valheim/client")
_CLAUDE_PROJECT_MOUNT = os.environ.get("CLAUDE_PROJECT_MOUNT", "/workspace")

_path_map: dict[str, str] = {}


def _build_path_map() -> str:
    """
    Build the claude-sandbox → this container path map from known mount points.
    Call refresh_path_map() if the claude-sandbox workspace layout has changed.
    """
    global _path_map
    _path_map = {
        _CLAUDE_SERVER_MOUNT:  str(SERVER_DIR),
        _CLAUDE_CLIENT_MOUNT:  str(CLIENT_DIR),
        _CLAUDE_PROJECT_MOUNT: str(PROJECT_DIR),
    }
    lines = [f"  {dst} -> {src}" for dst, src in _path_map.items()]
    summary = "Path map (static):\n" + "\n".join(lines)
    print(summary)
    return summary


def _container_to_host(container_path: str) -> str:
    """
    Translate a claude-sandbox path to its equivalent inside this container.
    Raises ValueError if no mapping is found.
    """
    best_dst = ""
    best_src = ""

    for dst, src in _path_map.items():
        if container_path.startswith(dst) and len(dst) > len(best_dst):
            best_dst = dst
            best_src = src

    if not best_dst:
        raise ValueError(
            f"No mapping found for path: {container_path}\n"
            "Check CLAUDE_SERVER_MOUNT, CLAUDE_CLIENT_MOUNT, CLAUDE_PROJECT_MOUNT env vars."
        )

    return best_src + container_path[len(best_dst):]


# ── Knowledge reporter ────────────────────────────────────────────────────────

_reporter = KnowledgeReporter(service="mcp-build")
_report = _reporter.report


# ── Subprocess helpers ────────────────────────────────────────────────────────

def _run(cmd: list[str], cwd: str | None, log_path: Path) -> tuple[bool, str]:
    """
    Run a command synchronously, tee stdout+stderr to a log file.
    Returns (success, full_log_content).
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w") as log:
        log.write(f"--- Started: {datetime.now()} ---\n")
        log.flush()

        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
        )

        status = "succeeded" if proc.returncode == 0 else "failed"
        log.write(f"--- {status.capitalize()}: {datetime.now()} ---\n")

    return proc.returncode == 0, log_path.read_text()


async def _run_async(cmd: list[str], cwd: str | None, log_path: Path) -> tuple[bool, str]:
    """Async wrapper around _run so long builds don't block the MCP event loop."""
    return await asyncio.to_thread(_run, cmd, cwd, log_path)


# ── MCP server ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="valheim-build",
    instructions=(
        "Tools for building, deploying, and packaging Valheim mods. "
        "All tools (build, deploy, package, decompile, convert) return "
        "the full log output so you can diagnose failures without reading a file. "
        "Server and client control tools are in the sibling valheim-control MCP (mcp-valheim/control, port 5173)."
    ),
)


# ── Build, deploy, package (blocking — return full log) ───────────────────────

@mcp.tool()
async def build(project: str) -> str:
    """
    Build a mod project with 'dotnet build -c Release'.

    Args:
        project: Project folder name under ~/Projects (no path separators, e.g. 'ValheimRainDance').

    Returns the full build log. Always check the result before running deploy or package.
    """
    cwd = str(PROJECT_DIR / project)
    success, log = await _run_async(
        ["dotnet", "build", "-c", "Release"],
        cwd=cwd,
        log_path=LOGS_DIR / "build.log",
    )
    header = "BUILD SUCCEEDED ✓" if success else "BUILD FAILED ✗"
    result = f"{header}\n\n{log}"
    _report("build", {"project": project}, result, success)
    return result


@mcp.tool()
async def deploy_server(project: str) -> str:
    """
    Deploy a mod to the Valheim dedicated server.
    Copies built DLLs to BepInEx/plugins/ and .cfg files to BepInEx/config/.

    Args:
        project: Project folder name under ~/Projects (no path separators).
    """
    result = await asyncio.to_thread(_deploy, project, SERVER_DIR, LOGS_DIR / "deploy-server.log")
    _report("deploy_server", {"project": project}, result, result.startswith("DEPLOY SUCCEEDED"))
    return result


@mcp.tool()
async def deploy_client(project: str) -> str:
    """
    Deploy a mod to the Valheim client.
    Copies built DLLs to BepInEx/plugins/ and .cfg files to BepInEx/config/.

    Args:
        project: Project folder name under ~/Projects (no path separators).
    """
    result = await asyncio.to_thread(_deploy, project, CLIENT_DIR, LOGS_DIR / "deploy-client.log")
    _report("deploy_client", {"project": project}, result, result.startswith("DEPLOY SUCCEEDED"))
    return result


def _deploy(project: str, target: Path, log_path: Path) -> str:
    import shutil
    lines = [f"--- Started: {datetime.now()} ---"]
    try:
        project_dir = PROJECT_DIR / project
        dll_src  = project_dir / "bin/Release/netstandard2.1"
        cfg_srcs = list(project_dir.glob("*.cfg"))

        plugins_dst = target / "BepInEx/plugins"
        config_dst  = target / "BepInEx/config"

        dlls = list(dll_src.glob("*.dll"))
        if not dlls:
            raise FileNotFoundError(f"No DLLs found in {dll_src}")

        for dll in dlls:
            shutil.copy2(dll, plugins_dst / dll.name)
            lines.append(f"Copied {dll.name} -> {plugins_dst}")

        for cfg in cfg_srcs:
            shutil.copy2(cfg, config_dst / cfg.name)
            lines.append(f"Copied {cfg.name} -> {config_dst}")

        lines.append(f"--- Succeeded: {datetime.now()} ---")
        result = "\n".join(lines)
        log_path.write_text(result)
        return f"DEPLOY SUCCEEDED ✓\n\n{result}"

    except Exception as e:
        lines.append(f"ERROR: {e}")
        lines.append(f"--- Failed: {datetime.now()} ---")
        result = "\n".join(lines)
        log_path.write_text(result)
        return f"DEPLOY FAILED ✗\n\n{result}"


@mcp.tool()
async def package(project: str) -> str:
    """
    Package a mod for Thunderstore.
    Reads version from ThunderstoreAssets/manifest.json and produces
    release/tarbaby-<modname>-<version>.zip in the project directory.

    Always build successfully before packaging.

    Args:
        project: Project folder name under ~/Projects (no path separators).
    """
    result = await asyncio.to_thread(_package, project, LOGS_DIR / "package.log")
    _report("package", {"project": project}, result, result.startswith("PACKAGE SUCCEEDED"))
    return result


def _package(project: str, log_path: Path) -> str:
    import shutil, zipfile
    lines = [f"--- Started: {datetime.now()} ---"]
    try:
        project_dir = PROJECT_DIR / project
        assets_dir  = project_dir / "ThunderstoreAssets"

        manifest_path = assets_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        version  = manifest["version_number"]
        modname  = project_dir.name
        zip_name = f"tarbaby-{modname}-{version}.zip"

        staging = project_dir / "staging"
        release = project_dir / "release"
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(release, ignore_errors=True)
        (staging / "plugins").mkdir(parents=True)
        (staging / "config").mkdir(parents=True)
        release.mkdir()

        for name in ("icon.png", "README.md", "manifest.json"):
            shutil.copy2(assets_dir / name, staging / name)
            lines.append(f"Staged {name}")

        changelog = assets_dir / "CHANGELOG.md"
        if changelog.exists():
            shutil.copy2(changelog, staging / "CHANGELOG.md")
            lines.append("Staged CHANGELOG.md")

        dll_src = project_dir / "bin/Release/netstandard2.1"
        for dll in dll_src.glob("*.dll"):
            shutil.copy2(dll, staging / "plugins" / dll.name)
            lines.append(f"Staged plugins/{dll.name}")

        for cfg in project_dir.glob("*.cfg"):
            shutil.copy2(cfg, staging / "config" / cfg.name)
            lines.append(f"Staged config/{cfg.name}")

        zip_path = release / zip_name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in staging.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(staging))

        lines.append(f"Created {zip_path}")
        lines.append(f"--- Succeeded: {datetime.now()} ---")
        result = "\n".join(lines)
        log_path.write_text(result)
        return f"PACKAGE SUCCEEDED ✓\n\n{result}"

    except Exception as e:
        lines.append(f"ERROR: {e}")
        lines.append(f"--- Failed: {datetime.now()} ---")
        result = "\n".join(lines)
        log_path.write_text(result)
        return f"PACKAGE FAILED ✗\n\n{result}"


# ── Thunderstore publish ──────────────────────────────────────────────────────

@mcp.tool()
async def publish(project: str, community: str = "valheim", categories: list[str] = []) -> str:
    """
    Publish the packaged mod to Thunderstore.
    Uploads the ZIP from release/ (created by package()).
    Reads the auth token from the THUNDERSTORE_TOKEN environment variable.

    Args:
        project:    Project folder name under ~/Projects (no path separators).
        community:  Thunderstore community slug (default: 'valheim').
        categories: List of community category slugs to apply (e.g. ['client-side', 'server-side']).
                    'ai-generated' is always included automatically.
                    Use https://thunderstore.io/api/experimental/community/{community}/category/ to look up valid slugs.

    Always run build() and package() successfully before publishing.
    """
    result = await asyncio.to_thread(_publish, project, community, categories, LOGS_DIR / "publish.log")
    _report("publish", {"project": project, "community": community, "categories": categories}, result, result.startswith("PUBLISH SUCCEEDED"))
    return result


def _publish(project: str, community: str, categories: list[str], log_path: Path) -> str:
    import httpx

    lines = [f"--- Started: {datetime.now()} ---"]

    try:
        token = os.environ.get("THUNDERSTORE_TOKEN", "")
        if not token:
            raise ValueError(
                "THUNDERSTORE_TOKEN environment variable is not set. "
                "Generate a service account token at thunderstore.io and pass it "
                "via -e THUNDERSTORE_TOKEN when starting the container."
            )

        release_dir = PROJECT_DIR / project / "release"
        zips = sorted(release_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not zips:
            raise FileNotFoundError(
                f"No ZIP found in {release_dir}. Run package() first."
            )
        zip_path = zips[0]
        lines.append(f"Uploading {zip_path.name} to community '{community}'...")

        # Read team name from manifest
        manifest_path = PROJECT_DIR / project / "ThunderstoreAssets" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        author_name = manifest.get("author", manifest.get("namespace", ""))
        if not author_name:
            raise ValueError(
                "manifest.json must contain an 'author' or 'namespace' field "
                "matching your Thunderstore team name."
            )

        url = f"https://thunderstore.io/api/experimental/submission/upload/"
        headers = {"Authorization": f"Bearer {token}"}
        all_categories = list({"ai-generated"} | set(categories))
        lines.append(f"Categories: {all_categories}")
        metadata = json.dumps({
            "author_name": author_name,
            "communities": [community],
            "has_nsfw_content": False,
            "community_categories": {community: all_categories},
        })

        with open(zip_path, "rb") as f:
            response = httpx.post(
                url,
                headers=headers,
                files={"file": (zip_path.name, f, "application/zip")},
                data={"metadata": metadata},
                timeout=120,
            )

        lines.append(f"HTTP {response.status_code}")
        try:
            body = json.dumps(response.json(), indent=2)
        except Exception:
            body = response.text
        lines.append(body)

        if response.status_code in (200, 201):
            lines.append(f"--- Succeeded: {datetime.now()} ---")
            result = "\n".join(lines)
            log_path.write_text(result)
            return f"PUBLISH SUCCEEDED ✓\n\n{result}"
        else:
            lines.append(f"--- Failed: {datetime.now()} ---")
            result = "\n".join(lines)
            log_path.write_text(result)
            return f"PUBLISH FAILED ✗\n\n{result}"

    except Exception as e:
        lines.append(f"ERROR: {e}")
        lines.append(f"--- Failed: {datetime.now()} ---")
        result = "\n".join(lines)
        log_path.write_text(result)
        return f"PUBLISH FAILED ✗\n\n{result}"


# ── Thunderstore download + deploy ────────────────────────────────────────────

@mcp.tool()
async def download(package: str, client: bool = False, server: bool = False) -> str:
    """
    Download a Thunderstore package and deploy its contents to the Valheim
    client and/or server install directories.

    The zip is fetched once (cached under /tmp/thunderstore-cache/) and
    deployed to whichever of client/server flags are true. Pass at least one.

    Args:
        package: manifest.json-style dependency string 'namespace-name-version'
                 (e.g. 'denikson-BepInExPack_Valheim-5.4.2202').
        client:  Deploy to the Valheim client install (CLIENT_DIR).
        server:  Deploy to the Valheim dedicated server install (SERVER_DIR).

    Deploy rules:
      - BepInEx pack (top-level dir starts with 'BepInExPack'): merge that dir's
        inner contents into game root.
      - Regular mod: treat the zip as a fragment of the BepInEx tree, so e.g.
        'plugins/MyMod.dll' lands in '<game_root>/BepInEx/plugins/MyMod.dll'.
      - Skip metadata at archive root: manifest.json, README.md, CHANGELOG.md,
        icon.png, LICENSE*/LICENCE*, dotfiles.
    """
    result = await asyncio.to_thread(
        _download, package, client, server, LOGS_DIR / "download.log"
    )
    _report(
        "download",
        {"package": package, "client": client, "server": server},
        result,
        result.startswith("DOWNLOAD SUCCEEDED"),
    )
    return result


def _download(package: str, client: bool, server: bool, log_path: Path) -> str:
    import re
    import shutil
    import zipfile

    lines = [f"--- Started: {datetime.now()} ---"]
    try:
        if not (client or server):
            raise ValueError("At least one of client= or server= must be True.")

        # 'namespace-name-version' — namespace has no dashes; name may contain
        # dashes; version is digits-and-dots (handles SemVer plus 4-component
        # versions like '5.4.2202.10').
        m = re.match(r"^([^-/]+)-([^/]+)-(\d+(?:\.\d+)+)$", package)
        if not m:
            raise ValueError(
                f"Package '{package}' is not in 'namespace-name-version' form."
            )
        namespace, name, version = m.group(1), m.group(2), m.group(3)
        if ".." in (namespace, name):
            raise ValueError("Package components must not contain '..'.")
        lines.append(f"Parsed: namespace={namespace} name={name} version={version}")

        cache_dir = Path("/tmp/thunderstore-cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        zip_path = cache_dir / f"{namespace}-{name}-{version}.zip"

        if not zip_path.exists():
            url = f"https://thunderstore.io/package/download/{namespace}/{name}/{version}/"
            lines.append(f"Fetching {url}")
            with httpx.Client(follow_redirects=True, timeout=120) as cli:
                resp = cli.get(url)
                resp.raise_for_status()
                zip_path.write_bytes(resp.content)
            lines.append(f"Downloaded {zip_path} ({zip_path.stat().st_size} bytes)")
        else:
            lines.append(f"Using cached {zip_path}")

        # Extract to a per-package working dir
        extract_dir = cache_dir / f"{namespace}__{name}__{version}"
        shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

        targets: list[tuple[str, Path]] = []
        if client:
            targets.append(("client", CLIENT_DIR))
        if server:
            targets.append(("server", SERVER_DIR))

        for label, target in targets:
            lines.append(f"--- Deploying to {label}: {target} ---")
            count = _deploy_extracted(extract_dir, target, lines)
            lines.append(f"Deployed {count} file(s) to {target}")

        lines.append(f"--- Succeeded: {datetime.now()} ---")
        result = "\n".join(lines)
        log_path.write_text(result)
        return f"DOWNLOAD SUCCEEDED ✓\n\n{result}"

    except Exception as e:
        lines.append(f"ERROR: {e}")
        lines.append(f"--- Failed: {datetime.now()} ---")
        result = "\n".join(lines)
        log_path.write_text(result)
        return f"DOWNLOAD FAILED ✗\n\n{result}"


_METADATA_NAMES = {"manifest.json", "README.md", "CHANGELOG.md", "icon.png"}


def _is_metadata(name: str) -> bool:
    if name in _METADATA_NAMES:
        return True
    upper = name.upper()
    if upper.startswith("LICENSE") or upper.startswith("LICENCE"):
        return True
    if name.startswith("."):
        return True
    return False


def _deploy_extracted(extracted: Path, game_root: Path, lines: list[str]) -> int:
    """
    Copy deployable contents of an extracted Thunderstore package into game_root.
    Returns the file count.
    """
    import shutil

    # BepInEx pack: a top-level dir like 'BepInExPack_Valheim' wraps the
    # framework — its inner contents merge into game root.
    bep_pack_dir: Path | None = None
    for child in extracted.iterdir():
        if child.is_dir() and child.name.startswith("BepInExPack"):
            bep_pack_dir = child
            break

    if bep_pack_dir is not None:
        lines.append(f"  Detected BepInEx pack: {bep_pack_dir.name}")
        src_root = bep_pack_dir
        dst_root = game_root
    else:
        src_root = extracted
        dst_root = game_root / "BepInEx"

    count = 0
    for src in src_root.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(src_root)
        # Strip top-level metadata files (don't touch nested ones — those may
        # be part of the actual mod, e.g. plugins/MyMod/README.md).
        if len(rel.parts) == 1 and _is_metadata(rel.parts[0]):
            continue
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        lines.append(f"  Copied {rel} -> {dst}")
        count += 1
    return count


# ── Path-translated tools (blocking) ─────────────────────────────────────────

@mcp.tool()
async def decompile_dll(container_path: str, type_name: str | None = None) -> str:
    """
    Decompile a DLL with ilspycmd and return the source output.
    Output is also written to logs/ilspy.log.

    Args:
        container_path: Path to the DLL as seen from inside the container,
                        e.g. '/workspace/valheim/server/valheim_server_Data/Managed/assembly_valheim.dll'
        type_name:      Optional type name to decompile a single class,
                        e.g. 'Player' or 'ZRoutedRpc'. Omit to decompile the entire DLL.
    """
    try:
        host_path = _container_to_host(container_path)
    except ValueError as e:
        result = f"PATH TRANSLATION FAILED\n\n{e}"
        _report("decompile_dll", {"container_path": container_path, "type_name": type_name}, result, False)
        return result

    cmd = ["ilspycmd"]
    if type_name:
        cmd += ["-t", type_name]
    cmd.append(host_path)

    success, log = await _run_async(
        cmd,
        cwd=None,
        log_path=LOGS_DIR / "ilspy.log",
    )
    header = "DECOMPILE SUCCEEDED ✓" if success else "DECOMPILE FAILED ✗"
    result = f"{header}\n\n{log}"
    _report("decompile_dll", {"container_path": container_path, "type_name": type_name}, result, success)
    return result


@mcp.tool()
async def convert_svg(container_path: str) -> str:
    """
    Convert an SVG to a 256x256 PNG using rsvg-convert.
    Output PNG is written next to the source SVG with a .png extension.

    Args:
        container_path: Path to the .svg as seen from inside the container,
                        e.g. '/workspace/ValheimRainDance/ThunderstoreAssets/icon.svg'
    """
    try:
        host_svg = _container_to_host(container_path)
    except ValueError as e:
        result = f"PATH TRANSLATION FAILED\n\n{e}"
        _report("convert_svg", {"container_path": container_path}, result, False)
        return result

    host_png = str(Path(host_svg).with_suffix(".png"))

    success, log = await _run_async(
        ["rsvg-convert", "-w", "256", "-h", "256", host_svg, "-o", host_png],
        cwd=None,
        log_path=LOGS_DIR / "svg-to-png.log",
    )
    header = "CONVERT SUCCEEDED ✓" if success else "CONVERT FAILED ✗"
    result = f"{header}\n\n{log}"
    _report("convert_svg", {"container_path": container_path}, result, success)
    return result


# ── Utility ───────────────────────────────────────────────────────────────────

@mcp.tool()
def refresh_path_map() -> str:
    """
    Rebuild the claude-sandbox → mcp-build path map from environment variables.
    Only needed if mount paths have changed since startup.
    """
    result = _build_path_map()
    _report("refresh_path_map", {}, result, True)
    return result


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Building initial path map...")
    _build_path_map()
    print("Starting valheim-build MCP on http://0.0.0.0:5182")
    print()
    print("Register with Claude Code:")
    print("  claude mcp add valheim-build --transport http http://localhost:5182/mcp")
    print()
    mcp.run(transport="streamable-http", host="0.0.0.0", port=5182)
