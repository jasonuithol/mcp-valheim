# Valheim Modding — Plugin Basics

---

## GUID Convention

```
com.authorname.modname
```
Or keep it short — `PluginGUID` determines the config filename:
- `"raindance"` → `raindance.cfg`
- `"com.yourname.raindance"` → `com.yourname.raindance.cfg`

---

## Minimal Plugin Boilerplate

```csharp
[BepInPlugin(PluginGUID, PluginName, PluginVersion)]
public class MyPlugin : BaseUnityPlugin
{
    public const string PluginGUID    = "myplugin";
    public const string PluginName    = "MyPlugin";
    public const string PluginVersion = "1.0.0";

    internal static ManualLogSource Log;
    internal static MyPlugin Instance;
    private Harmony _harmony;

    private void Awake()
    {
        Log      = Logger;
        Instance = this;
        _harmony = new Harmony(PluginGUID);
        _harmony.PatchAll();
        Log.LogInfo($"{PluginName} v{PluginVersion} loaded.");
    }

    private void OnDestroy() => _harmony?.UnpatchSelf();
}
```

---

## Server vs Client Detection

The dedicated server runs the same assembly as the client. Both call `Awake()` and can
register RPC handlers. Branch with:

```csharp
ZNet.instance.IsServer()    // true on dedicated server AND host
GUIManager.IsHeadless()     // true ONLY on dedicated server (requires Jotunn)
```

Guard server-only logic in `Update()`:
```csharp
if (ZNet.instance == null || !ZNet.instance.IsServer()) return;
```

---

## Peer Iteration (Server-Side)

```csharp
foreach (var peer in ZNet.instance.GetPeers())
{
    if (peer.m_uid == 0) continue; // always skip ghost peers

    ZDO zdo = ZDOMan.instance.GetZDO(peer.m_characterID);
    if (zdo == null) continue;

    // peer.m_playerName              — display name
    // peer.m_uid                     — unique peer ID (long)
    // peer.m_refPos                  — player's world position
    // peer.m_socket.GetHostName()    — platform ID e.g. "playfab/XXX" or "76561XXXXXX"
    // peer.m_characterID             — ZDO reference for reading player state
}
```

### Cleanup pattern for Dictionary keyed by peer UID
```csharp
var connected = new HashSet<long>(ZNet.instance.GetPeers().Select(p => p.m_uid));
foreach (var uid in myDict.Keys.Where(uid => !connected.Contains(uid)).ToList())
    myDict.Remove(uid);
```

---

## Jotunn Dependency

When using Jotunn RPCs, add `[BepInDependency(Jotunn.Main.ModGuid)]` — see `MODDING_NETWORKING.md`.
