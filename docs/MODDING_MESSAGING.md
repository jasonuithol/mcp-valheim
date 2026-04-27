# Valheim Modding — Messaging & UI

---

## ShowMessage — Recommended for All Server Announcements

Sends a floating HUD message to all clients. Safe, no platform ID needed.

```csharp
private static void ShowMessage(MessageHud.MessageType type, string text)
{
    if (string.IsNullOrWhiteSpace(text)) return;
    if (ZRoutedRpc.instance == null) return;

    ZRoutedRpc.instance.InvokeRoutedRPC(
        ZRoutedRpc.Everybody,
        "ShowMessage",
        (int)type,
        text);
}

// Usage
ShowMessage(MessageHud.MessageType.Center, "Big dramatic message");   // centre screen
ShowMessage(MessageHud.MessageType.TopLeft, "Subtle notification");   // top left
```

---

## ChatMessage — Avoid Unless Necessary

Requires a real platform ID. Throws `EndOfStreamException` with a fake one.

```csharp
// (Vector3 pos, int talkerType, string senderName, string platformUserID, string text)
// platformUserID must be a real connected peer's ID — fragile, avoid
```

If you must use `ChatMessage`, get the platform ID like this:

```csharp
//
// WARNING: This is a magic band-aid.
//
private string GetPlatformId(ZNetPeer peer)
{
    var rawId = peer.m_socket.GetHostName();

    if (rawId.StartsWith("Steam_") || rawId.StartsWith("playfab/"))
    {
        return rawId;
    }

    return "Steam_" + rawId;
}

ZRoutedRpc.instance.InvokeRoutedRPC(
    ZRoutedRpc.Everybody,
    "ChatMessage",
    new object[]
    {
        peer.m_refPos,
        (int)Talker.Type.Shout,
        "Server",
        GetPlatformId(peer),
        text
    }
);
```

> The platform ID format varies by connection type (PlayFab relay vs direct Steam).
> Keep this code isolated in one method.

---

## "Day X" Morning Message

`EnvMan.OnMorning` runs at the day transition. To suppress it and deliver it later
(e.g. on respawn):

```csharp
// Suppress in OnMorning patch:
static bool Prefix() { return !SuppressMorning; }

// Deliver on respawn:
[HarmonyPatch(typeof(Player), nameof(Player.OnSpawned))]
static void Postfix(Player __instance)
{
    if (!SuppressMorning) return;
    SuppressMorning = false;
    __instance.Message(MessageHud.MessageType.Center, $"Day {EnvMan.instance.GetDay()}");
}
```

`EnvMan.instance.GetDay()` is cleaner than going through `Localization`.

---

## Suppressing Dream Text and "Good Morning"

These need to be suppressed as soon as `IsEventStarting` is set, not just when
`IsEventActive` is true:

- `$msg_goodmorning` goes through `Player.Message()` — patch that
- Dream text comes from `SleepText.ShowDreamText()` (private) — patch by name

```csharp
[HarmonyPatch(typeof(SleepText), "ShowDreamText")]
static class Patch_SuppressDreamText
{
    static bool Prefix() => !(IsEventActive || IsEventStarting);
}
```

---

## Delivering a Message to a Single Player

Use `InvokeRoutedRPC` with the peer's UID as the target:

```csharp
ZRoutedRpc.instance.InvokeRoutedRPC(
    peer.m_uid,
    "ShowMessage",
    (int)MessageHud.MessageType.Center,
    "Message for you specifically");
```
