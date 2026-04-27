# Valheim Modding — Networking & RPCs

---

## What IS and IS NOT Synced Server → Client

### ✅ Built-in RPCs (server controls these)

| RPC | Signature | Effect |
|-----|-----------|--------|
| `ShowMessage` | `(int type, string text)` | HUD message on all clients |
| `SetEvent` | `(string name, float time, Vector3 pos)` | Random raid event |
| `SpawnObject` | `(Vector3 pos, Quaternion rot, int prefabHash)` | Spawn entity |
| `RPC_TeleportPlayer` | `(Vector3 pos, Quaternion rot, bool distant)` | Teleport player |
| `SetGlobalKey` / `RemoveGlobalKey` | `(string name)` | Progression flags |
| `SleepStart` / `SleepStop` | none | Force sleep |
| `NetTime` | `(double time)` | Game time |

### ❌ NOT Synced (client-local only)

- **`EnvMan`** — weather/environment. Each client runs its own independently. Use a custom RPC.
- **`AudioMan`** — ambient sound
- **`MusicMan`** — music
- **`Hud`** — HUD elements (use `ShowMessage` RPC instead)
- **`MessageHud`** (direct) — use `ShowMessage` RPC instead
- **`PostProcessing`** — screen effects

---

## Custom RPC (Server → All Clients)

Use when you need to trigger something on clients that has no built-in RPC
(e.g. forcing local weather, playing audio).

### Registration — patch the ZRoutedRpc constructor

Both server and client run the constructor, so both register the handler.
Guard inside the handler to control who acts on it.

```csharp
[HarmonyPatch(typeof(ZRoutedRpc), MethodType.Constructor, new[] { typeof(bool) })]
private static class ZRoutedRpc_Ctor_Patch
{
    static void Postfix()
    {
        ZRoutedRpc.instance.Register<string>("MyMod_MyRPC", RPC_Handler);
    }
}

private static void RPC_Handler(long sender, string payload)
{
    // Guard: only run on the client, not on the server process
    if (Player.m_localPlayer == null) return;
    // do client-side logic here
}
```

### Sending from the Server

```csharp
private static void BroadcastRPC(string payload)
{
    ZRoutedRpc.instance.InvokeRoutedRPC(
        ZRoutedRpc.Everybody,
        "MyMod_MyRPC",
        payload);
}
```

**Naming**: prefix RPC names with your mod name to avoid collisions — e.g. `"RainDance_SetWeather"`.

---

## Client → Server RPC

Unaddressed `InvokeRoutedRPC` calls route to the server automatically:

```csharp
// Client sends — no peer ID needed
ZRoutedRpc.instance.InvokeRoutedRPC("MyMod_PlayerAction");

// Server handler
private static void RPC_PlayerAction(long sender, ZPackage pkg)
{
    if (ZNet.instance == null || !ZNet.instance.IsServer()) return;
    ZNetPeer peer = ZNet.instance.GetPeer(sender);
    // handle the action
}
```

---

## RPC Ordering Guarantee

RPCs sent to the same peer arrive in the order they were sent. This means you can chain:

```csharp
// These arrive and execute in order on the client
ZRoutedRpc.instance.InvokeRoutedRPC(peer.m_uid, "MyMod_RestoreInventory", pkg);
ZRoutedRpc.instance.InvokeRoutedRPC(peer.m_uid, "MyMod_KillPlayer");
ZRoutedRpc.instance.InvokeRoutedRPC(peer.m_uid, "MyMod_EventEnd");
```

Inventory is restored, then the player dies (with suppression still active from the
previous RPC), then the event flag clears.

---

## Upload RPCs (Client → Server)

The server cannot access client inventory directly. Clients must push data up:

```csharp
// Client: serialize and send
var pkg = new ZPackage();
Player.m_localPlayer.GetInventory().Save(pkg);
ZRoutedRpc.instance.InvokeRoutedRPC("MyMod_UploadInventory", pkg);

// Server: receives and stores
private static void RPC_UploadInventory(long sender, ZPackage pkg)
{
    if (!ZNet.instance.IsServer()) return;
    _inventoryByPeer[sender] = pkg.GetArray();
}
```

A fixed wait (e.g. 2.2s) after requesting uploads gives all clients time to respond
before the server proceeds with the data.

---

## Jotunn RPCs (Bidirectional)

Use Jotunn when you need clean bidirectional communication. Requires declaring a
`[BepInDependency]`:

```csharp
[BepInPlugin(PluginGUID, PluginName, PluginVersion)]
[BepInDependency(Jotunn.Main.ModGuid)]
public class MyPlugin : BaseUnityPlugin { }
```

### Registration

```csharp
// In Awake()
clientToServerRPC = NetworkManager.Instance.AddRPC(
    "MyAction",
    RPC_OnMyAction,   // server handler
    RPC_NoOp          // client handler (unused — must NOT be null)
);
serverToClientRPC = NetworkManager.Instance.AddRPC(
    "MyResult",
    RPC_NoOp,         // server handler (unused — must NOT be null)
    RPC_OnMyResult    // client handler
);

// Always use RPC_NoOp, never null — null causes NullReferenceException inside Jotunn
private IEnumerator RPC_NoOp(long sender, ZPackage package) { yield break; }
```

### Server Handler

```csharp
private IEnumerator RPC_OnMyAction(long sender, ZPackage package)
{
    ZNetPeer peer = ZNet.instance.GetPeer(sender);
    // do server-side logic
    serverToClientRPC.SendPackage(ZRoutedRpc.Everybody, new ZPackage());
    yield break;
}
```

### Client Handler

```csharp
private IEnumerator RPC_OnMyResult(long sender, ZPackage package)
{
    if (GUIManager.IsHeadless()) yield break; // skip on dedicated server
    // do client-side logic (audio, UI, etc.)
    yield break;
}
```

### Sending

```csharp
// Client → Server
rpc.SendPackage(ZNet.instance.GetServerPeer().m_uid, new ZPackage());

// Server → All clients
rpc.SendPackage(ZRoutedRpc.Everybody, new ZPackage());
```

### Getting a Peer by Sender ID

```csharp
ZNetPeer peer = ZNet.instance.GetPeer(sender);
```

---

## SpawnObject RPC (Server → All)

```csharp
ZRoutedRpc.instance.InvokeRoutedRPC(
    ZRoutedRpc.Everybody,
    "SpawnObject",
    spawnPos,
    Quaternion.identity,
    prefabName.GetStableHashCode());
```

Fire-and-forget — no handle returned, no way to despawn later. Fine for event monsters;
not suitable for things you need to clean up.

---

## Register ALL RPCs on Both Sides — Guard Inside

Register every RPC regardless of which side handles it. Use guards inside the handler:

```csharp
// server-only handler
if (ZNet.instance == null || !ZNet.instance.IsServer()) return;

// client-only handler
if (Player.m_localPlayer == null) return;
```
