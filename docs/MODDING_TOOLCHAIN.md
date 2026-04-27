# Valheim Modding — Toolchain & Environment

---

## Platform & SDK

- **OS**: Linux (KDE Neon / Ubuntu tested)
- **SDK**: .NET 8 — `apt install dotnet-sdk-8.0`
- **Target framework**: `netstandard2.1` — do NOT use `net462` on Linux (requires Mono, fails to resolve refs)
- **Build**: `dotnet build -c Release`

---

## csproj Template

Keep it simple. Direct `<Reference>` includes, no NuGet packages, no custom `OutputPath`
(the MCP service handles deploy).

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>netstandard2.1</TargetFramework>
    <AssemblyName>MyMod</AssemblyName>
    <RootNamespace>MyMod</RootNamespace>
    <LangVersion>8.0</LangVersion>
    <MSBuildWarningsAsMessages>MSB3277</MSBuildWarningsAsMessages>
  </PropertyGroup>
  <PropertyGroup>
    <!-- Use $(HOME) not a hardcoded path — hardcoding leaks PII into public repos -->
    <ValheimDir>$(HOME)/.steam/steam/steamapps/common/Valheim dedicated server</ValheimDir>
    <BepInExDir>$(ValheimDir)/BepInEx</BepInExDir>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="BepInEx">
      <HintPath>$(BepInExDir)/core/BepInEx.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="0Harmony">
      <HintPath>$(BepInExDir)/core/0Harmony.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="assembly_valheim">
      <HintPath>$(ValheimDir)/valheim_server_Data/Managed/assembly_valheim.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="UnityEngine">
      <HintPath>$(ValheimDir)/valheim_server_Data/Managed/UnityEngine.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="UnityEngine.CoreModule">
      <HintPath>$(ValheimDir)/valheim_server_Data/Managed/UnityEngine.CoreModule.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <!-- Add as needed -->
    <Reference Include="UnityEngine.AudioModule">
      <HintPath>$(ValheimDir)/valheim_server_Data/Managed/UnityEngine.AudioModule.dll</HintPath>
      <Private>false</Private>
    </Reference>
  </ItemGroup>
</Project>
```

**Notes:**
- Build against **server** DLLs — avoids the `MSB3277` `System.Net.Http` conflict from client DLLs
- `PluginGUID` determines the config filename — keep it simple (e.g. `"raindance"`) to get `raindance.cfg` not `com.yourname.raindance.cfg`
- Do NOT add `UnityEngine.AnimationModule` unless you actually use `Animator` directly
- `obj/project.assets.json` contains resolved home paths but is gitignored — nothing leaks into the DLL

---

## BepInEx

### Installation (Linux dedicated server)
1. Download `BepInEx_unix_5.x.x.x.zip` from GitHub (NOT v6)
2. Extract into Valheim server root
3. Edit `run_bepinex.sh` — set `executable_name="valheim_server.x86_64"`
4. `chmod +x run_bepinex.sh`
5. Launch via `run_bepinex.sh` — never directly via the binary

### Key Paths
```
BepInEx/plugins/      ← DLL files go here
BepInEx/config/       ← Config files go here
BepInEx/LogOutput.log ← Full plugin log (more detail than console)
```

### Enable Console Logging
In `BepInEx/config/BepInEx.cfg`:
```ini
[Logging.Console]
Enabled = true

[Logging]
LogTimestamps = true
```

---

## ilspycmd

Essential for inspecting Valheim DLLs before writing patches. Never guess parameter names — decompile first.

### Install
```bash
dotnet tool install -g ilspycmd
```

### Key Commands
```bash
# Decompile a specific class
ilspycmd "$HOME/.steam/steam/steamapps/common/Valheim dedicated server/valheim_server_Data/Managed/assembly_valheim.dll" -t ClassName

# Find methods on a type
ilspycmd assembly_valheim.dll -t ZNet | grep "public\|private\|protected"

# Find specific method
ilspycmd assembly_valheim.dll -t Player | grep -i "emote"

# Find RPC registrations
ilspycmd assembly_valheim.dll -t ZRoutedRpc | grep "Register\|Invoke"

# Find ZDOVars constants
ilspycmd assembly_valheim.dll -t ZDOVars | grep -i "emote\|item\|equip"

# Filter with context
ilspycmd assembly_valheim.dll -t EnvMan | grep -A 5 -i "force\|environ"
```

Key classes to decompile are listed in `MODDING_ZDO.md`.

---

## Build & Deploy

The MCP `build`, `deploy_server`, and `deploy_client` tools handle this — see `VALHEIM_MCP.md`.

---

## Steam & Server Prerequisites

- **Steam must be running** before starting the Valheim client — `start_client` will fail silently if it isn't
- **Server IP changes on every restart** — don't hardcode it. After restart:
  ```bash
  grep "IPv4" /workspace/valheim/server/BepInEx/LogOutput.log | tail -1
  ```

---

## Debugging

### Check if plugin loaded
Look for `Chainloader startup complete` then your plugin's load message in `LogOutput.log`.
The Valheim console and BepInEx log are separate — always check `LogOutput.log`.

### Tail both logs simultaneously
```bash
multitail -s 2 \
  "path/to/server/BepInEx/LogOutput.log" \
  "path/to/client/BepInEx/LogOutput.log"
```

### Check if RPC fired
Add log lines at every RPC entry point. If a handler never logs, the RPC was never received.

### Verify DLL is deployed
```bash
ls -la BepInEx/plugins/
# Check timestamp matches your build time
```
