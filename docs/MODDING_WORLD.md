# Valheim Modding — World, Weather & Teleportation

---

## Weather / EnvMan

`EnvMan` is **client-local**. `SetForceEnvironment()` on the server affects only the
server process — no players are there. Use a custom RPC to call it on each client.

### Forcing Weather on All Clients

```csharp
// Server: send RPC
ZRoutedRpc.instance.InvokeRoutedRPC(
    ZRoutedRpc.Everybody,
    "MyMod_SetWeather",
    "ThunderStorm");

// Client handler
private static void RPC_SetWeather(long sender, string envName)
{
    if (Player.m_localPlayer == null) return;
    EnvMan.instance.SetForceEnvironment(envName);
}
```

### Environment Names

Valid names from `m_environments` (loaded from assets):

```
"Rain"           — light rain
"ThunderStorm"   — storm with lightning
"LightRain"      — drizzle
"DeepForest_Mist"
"Ashrain"
""               — clear override, return to natural weather
```

### ✅ Use SetForceEnvironment(), Not Direct Field Assignment

```csharp
EnvMan.instance.SetForceEnvironment("Rain");   // ✅ triggers immediate refresh
EnvMan.instance.m_forceEnv = "Rain";           // ❌ does NOT refresh
```

`SetForceEnvironment("")` clears the override cleanly without throwing.

---

## Teleportation

### RPC_TeleportPlayer

```csharp
ZRoutedRpc.instance.InvokeRoutedRPC(
    peer.m_uid,
    "RPC_TeleportPlayer",
    destination,       // Vector3
    Quaternion.identity,
    true);             // distantTeleport = true → black loading screen while zone loads
```

Distant teleport produces a black screen while the destination zone loads — this is
expected engine behaviour, not a bug. Players can hear audio and see inventory changes
during this window.

---

## World Generation

```csharp
// Find a random land position — retry up to 100 times (usually finds one immediately)
Vector3 FindLandPosition()
{
    for (int i = 0; i < 100; i++)
    {
        float x = UnityEngine.Random.Range(-10000f, 10000f);
        float z = UnityEngine.Random.Range(-10000f, 10000f);

        float height = WorldGenerator.instance.GetHeight(x, z);
        if (height < ZoneSystem.instance.m_waterLevel) continue; // skip ocean

        Heightmap.Biome biome = WorldGenerator.instance.GetBiome(x, z);
        if (biome == Heightmap.Biome.Ocean) continue; // belt-and-suspenders

        return new Vector3(x, height, z);
    }
    return Vector3.zero; // fallback
}
```

The world is 20,000 × 20,000 (`[-10000, 10000]`). Ocean is detected by comparing
height against `ZoneSystem.instance.m_waterLevel`, not by biome enum — check height first.

---

## Random Event / Raid System

Use the `SetEvent` RPC — see `MODDING_NETWORKING.md` for the signature.
Key class: `RandEventSystem` — decompile to find event names and `IsEventActive`.

---

## Spawning Monsters

See `SpawnObject` RPC in `MODDING_NETWORKING.md`. Fire-and-forget — no despawn handle.
The nearest client claims ZDO ownership, making server-side cleanup unreliable.
