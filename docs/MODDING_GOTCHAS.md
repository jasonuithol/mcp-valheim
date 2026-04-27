# Valheim Modding — Gotchas

Consolidated list of non-obvious traps.

---

## Gotchas Table

| Gotcha | Cause | Fix |
|--------|-------|-----|
| `MSB3277` warning | Client DLL has newer `System.Net.Http` | Build against **server** DLLs; suppress with `<MSBuildWarningsAsMessages>MSB3277</MSBuildWarningsAsMessages>` |
| `CS0108` BroadcastMessage | `Component.BroadcastMessage` exists on all MonoBehaviours | Rename your method — use `SendServerBroadcast`, `ShowMessage`, etc. |
| Emote patch parameter wrong | Parameter is `emote`, not `name` | Always decompile first — never guess parameter names |
| `StopEmote` fires every frame | Called every frame during emote, not once on exit | Debounce with a bool flag or DateTime check |
| `FileSystemWatcher` fires twice | Editor writes content then metadata separately | 1-second debounce on any config reload handler |
| Null RPC handler crash | Jotunn NullReferenceException when `null` handler receives RPC | Always use `RPC_NoOp` instead of `null` |
| `ChatMessage` validation fails | Wrong platform ID format (Steam_ prefix missing) | Use `GetPlatformId()` helper with prefix logic; prefer `ShowMessage` |
| Ghost peers | `peer.m_uid == 0` is a ghost peer with no real player | Always `if (peer.m_uid == 0) continue` |
| Equipment ZDO is a hash, not string | `zdo.GetString(ZDOVars.s_rightItem)` always returns `""` | Use `zdo.GetInt(ZDOVars.s_rightItem)` |
| Emote ZDO is a string | Exception to the above — emote is stored as `string` | Use `zdo.GetString(ZDOVars.s_emote)` |
| `ZSyncAnimation` salt | Animator params on ZDO use `438569 + StringToHash(name)` as key | Emotes do NOT use this salt — they go via `ZDOVars` directly |
| `SetForceEnvironment` vs `m_forceEnv` | Direct field assignment doesn't trigger a refresh | Always use `SetForceEnvironment()` |
| `EnvMan` is client-local | Server `SetForceEnvironment` affects no players | Send a custom RPC; clients call it on their own `EnvMan.instance` |
| `mkdir -p` in deploy scripts | `BepInEx/plugins/` may not exist on first deploy | Always `mkdir -p` before `cp` |
| BepInEx config not hot-reloaded | BepInEx `.cfg` changes require a server restart | Use a custom `.cfg` with `FileSystemWatcher` if live reload is needed |
| `~` in bash strings | Tilde doesn't expand inside double-quoted strings | Use `$HOME` instead of `~` in scripts |
| `net462` fails on Linux | Requires Mono, fails to resolve refs correctly | Use `netstandard2.1` |
| Server IP changes on restart | No static IP for the local dedicated server | After restart: `grep "IPv4" BepInEx/LogOutput.log \| tail -1` |
| Steam must be running for client launch | `start_client` fails silently if Steam isn't up | Check Steam status first; use `start_steam` if needed |
| Spawned creature ZDO ownership | Server spawns it but nearest client claims ZDO ownership | Server-side `ZDOMan.DestroyZDO()` unreliable for client-owned ZDOs |
| `ZRoutedRpc` has no `Awake` | It's a plain class, not a MonoBehaviour | Patch the constructor: `[HarmonyPatch(typeof(ZRoutedRpc), MethodType.Constructor, new[] { typeof(bool) })]` |
| Private method — can't use `nameof()` | Compiler can't reference inaccessible members | Pass the name as a string literal; decompile first to confirm it |
| Audio only plays locally | Audio started on one client doesn't broadcast | Use an RPC to tell all clients to play |
| Inventory ghost state on load | Loading inventory bytes while items are equipped | Call `UnequipAllItems()` before loading inventory |
| `SetHealth(0f)` doesn't kill | Bypasses `CheckDeath()` | Use `player.Damage(hit)` with massive damage instead |
| `Object.Instantiate` triggers `Awake` immediately | If the source prefab is active, all components on the clone call `Awake` during `Instantiate` — before you can call `SetActive(false)`. `ZNetView.Awake` registers the clone as a live network object with no valid ZDO, corrupting ZNet state (world spinning, items floating, crafting duplication). | Deactivate the source before cloning, then restore it: `bool wasActive = src.activeSelf; src.SetActive(false); var clone = Object.Instantiate(src); src.SetActive(wasActive);` |
| Custom prefab template must be active for `ZNetScene.CreateObject` | `ZNetScene.CreateObject` uses a static handshake (`ZNetView.m_useInitZDO = true` / `m_initZDO = zdo`) that requires the prefab to be active so `ZNetView.Awake` fires during `Instantiate`. An inactive template produces inactive clones whose `Awake` is deferred — the ZDO is never claimed, causing `"ZDO N not used when creating object piece_X"` spam → infinite retry loop → world-load hang. | After all setup, call `template.SetActive(true)`. `ZNetView.Awake` fires and creates a spurious ZDO for the template itself — clean it up: `templateView.ResetZDO()`, remove from `m_instances` via Traverse, call `ZDOMan.instance.DestroyZDO(spuriousZdo)`. |
| SDK glob auto-includes subdirectory `obj/` files | An SDK-style `.csproj` includes all `**/*.cs` recursively. It excludes its own `$(IntermediateOutputPath)` but NOT subdirectory `obj/` folders. If you drop a reference mod (or any project) as a subfolder, its `obj/Release/.../AssemblyInfo.cs` gets compiled alongside yours, causing `CS0579: Duplicate assembly attribute` errors. | Add `<Compile Remove="SubfolderName\**\*.cs" />` in an `<ItemGroup>` to exclude the reference project from compilation. |
| `SetAlerted(true)` on a tamed animal causes flee scatter | Setting a tamed animal's alert state before `SetFollowTarget` briefly triggers flee behaviour — the animal sprints in a random direction before the follow target takes over. | Don't use `SetAlerted` to boost movement speed. Temporarily set `character.m_walkSpeed = character.m_runSpeed * 2f` instead — follow mode uses `m_walkSpeed`, so this makes the animal run to its target without any flee side-effects. Restore the original value on arrival. |
| Tamed animal wanders after `SetFollowTarget(null)` | Clearing the follow target resumes the AI's normal idle wander immediately. | After the animal arrives at its destination, keep `SetFollowTarget(destinationGameObject)` pointing at the destination object. The AI sees it's already close enough and stays put. Call `SetFollowTarget(null)` only when you actually want it to roam again (e.g. on wake-up). |
