# Valheim Modding — ZDO & Player State

ZDOs (Zone Data Objects) are Valheim's networked state objects for every entity.
Players sync their state here and the server can read it.

---

## Getting a Player's ZDO

```csharp
foreach (var peer in ZNet.instance.GetPeers())
{
    if (peer.m_uid == 0) continue; // always skip ghost peers

    ZDO zdo = ZDOMan.instance.GetZDO(peer.m_characterID);
    if (zdo == null) continue;

    // read state from zdo...
}
```

---

## Emote Detection

```csharp
// s_emote is stored as a plain STRING — not a hash
string emoteName = zdo.GetString(ZDOVars.s_emote); // "dance", "wave", "sit", "" when idle
bool isDancing = emoteName == "dance";
```

---

## Equipment Detection

```csharp
// Equipment is stored as INT (name.GetStableHashCode()) — NOT a string
int rightItemHash = zdo.GetInt(ZDOVars.s_rightItem);
if (rightItemHash != 0)
{
    GameObject prefab = ZNetScene.instance?.GetPrefab(rightItemHash);
    ItemDrop itemDrop = prefab?.GetComponent<ItemDrop>();
    Skills.SkillType skill = itemDrop?.m_itemData.m_shared.m_skillType ?? Skills.SkillType.None;
    bool isAxe = skill == Skills.SkillType.Axes;
}
```

---

## ZDOVars Quick Reference

```csharp
ZDOVars.s_emote          // string — current emote name, "" when idle
ZDOVars.s_emoteID        // int — counter, increments each emote start/stop
ZDOVars.s_emoteOneshot   // bool
ZDOVars.s_rightItem      // int hash — right hand item prefab name hash
ZDOVars.s_leftItem       // int hash
ZDOVars.s_helmetItem     // int hash
ZDOVars.s_chestItem      // int hash
ZDOVars.s_legItem        // int hash
ZDOVars.s_shoulderItem   // int hash
```

---

## ⚠️ ZSyncAnimation Salt Warning

Animator parameters synced via `ZSyncAnimation` use a salt:
`438569 + Animator.StringToHash(paramName)`.

**However**, emotes do NOT go through `ZSyncAnimation` — they write directly to ZDO
via `ZDOVars`. Do not apply the salt to emote keys.

---

## Finding ZDO Key Constants

Use `ilspycmd` to discover ZDOVars constants rather than guessing:

```bash
ilspycmd assembly_valheim.dll -t ZDOVars | grep -i "emote\|item\|equip"
```

---

## Key Classes

| Class | Purpose |
|-------|---------|
| `ZDOVars` | All ZDO key constants (as `int` hashes of strings) |
| `ZDOMan` | ZDO manager — `GetZDO(ZDOID)` |
| `ZNetPeer` | Peer fields: `m_uid`, `m_playerName`, `m_characterID`, `m_refPos`, `m_socket` |
| `ZSyncAnimation` | Animator parameter sync (uses `438569 + hash` salt) |
| `VisEquipment` | Equipment visual sync (stores as int hash, not string) |
