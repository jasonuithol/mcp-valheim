# Valheim Modding — Player State & Inventory

---

## Inventory Save / Restore

```csharp
// Save
var pkg = new ZPackage();
player.GetInventory().Save(pkg);
byte[] bytes = pkg.GetArray();

// Restore
player.UnequipAllItems(); // MUST unequip first — loading while equipped leaves ghost state
player.GetInventory().Load(new ZPackage(bytes));
```

`GetInventory()` is the public accessor for the protected `m_inventory` field.
`Save/Load` serialises the full inventory including item counts, quality, and crafting data.

---

## Suppressing Item/Biome Discovery Notifications

When granting items or entering biomes during events (e.g. dream sequences), suppress
the discovery popups so players encounter things fresh in real gameplay:

```csharp
// Player.AddKnownItem() — shows "new item!" unlock popup
[HarmonyPatch(typeof(Player), nameof(Player.AddKnownItem))]
static class Patch_SuppressNewItem
{
    static bool Prefix() => !(IsEventActive || IsEventStarting);
}

// Player.AddKnownBiome() — shows biome discovery message
[HarmonyPatch(typeof(Player), "AddKnownBiome")]
static class Patch_SuppressNewBiome
{
    static bool Prefix() => !(IsEventActive || IsEventStarting);
}
```

---

## Killing a Player via Damage

Do not call `OnDeath()` directly — use the normal damage path so all hooks fire:

```csharp
var hit = new HitData();
hit.m_damage.m_blunt = 99999f;
hit.m_point = player.transform.position;
player.Damage(hit);
// This fires CheckDeath() → OnDeath() → all the right hooks
```

`SetHealth(0f)` alone does not trigger death.

---

## Suppressing Skill Loss and Tombstone Creation

Use Prefix patches returning `false` while the event is active:

```csharp
[HarmonyPatch(typeof(Player), "OnDeath")]
static class Patch_SuppressOnDeath
{
    static bool Prefix() => !(IsEventActive || IsEventStarting);
}
```

---

## Emote Detection (Server-Side)

Via ZDO — see `MODDING_ZDO.md` for the full pattern and ZDOVars reference.

---

## Emote Detection (Client-Side via Harmony)

```csharp
// Fires once when an emote begins
[HarmonyPatch(typeof(Player), nameof(Player.StartEmote))]
static class Patch_StartEmote
{
    static void Postfix(string emote, Player __instance)
    {
        // parameter is 'emote', NOT 'name' — verify with ilspycmd
        if (emote != "rest") return;
    }
}

// Fires EVERY FRAME while emote is active — always debounce
[HarmonyPatch(typeof(Player), "StopEmote")]
static class Patch_StopEmote
{
    private static bool _stopped = false;

    static void Prefix(Player __instance)
    {
        if (Player.LastEmote != "rest" || _stopped) return;
        _stopped = true;
        // handle emote stop
    }

    static void Postfix(Player __instance)
    {
        if (Player.LastEmote != "rest") _stopped = false;
    }
}
```

---

## Audio (Client Only)

Audio must be started client-side. Use an RPC to tell all clients to play.

### Loading OGG at Runtime

Requires `UnityEngine.AudioModule` and `UnityEngine.UnityWebRequestAudioModule` references:

```csharp
private IEnumerator LoadAudio(string path)
{
    if (!File.Exists(path)) yield break;
    using (var req = UnityWebRequestMultimedia.GetAudioClip("file://" + path, AudioType.OGGVORBIS))
    {
        yield return req.SendWebRequest();
        if (req.result == UnityWebRequest.Result.Success)
            _audioClip = DownloadHandlerAudioClip.GetContent(req);
    }
}
```

### Audio Path Relative to DLL

```csharp
string audioPath = Path.Combine(Path.GetDirectoryName(Info.Location), "lullaby.ogg");
```

### Convert MP3 to OGG

```bash
ffmpeg -y -i lullaby.mp3 -c:a libvorbis -q:a 4 lullaby.ogg
```

### Fade In/Out

```csharp
private IEnumerator FadeIn(float duration)
{
    float t = 0f;
    while (t < duration)
    {
        t += Time.deltaTime;
        _audioSource.volume = Mathf.Clamp01(t / duration);
        yield return null;
    }
}
```
