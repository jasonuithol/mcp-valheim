# Valheim Modding — Creature AI & Sleep

Patterns for working with `MonsterAI`, `BaseAI`, and the game's sleep system.

---

## Controlling Creature Movement

### Making a tamed animal walk to a target

Use `MonsterAI.SetFollowTarget(GameObject)`. The animal will path to the target at its
current `Character.m_walkSpeed`.

```csharp
ai.SetFollowTarget(destinationObject);
```

### Making a tamed animal move faster

Follow mode uses `Character.m_walkSpeed` — not `m_runSpeed`. To make the animal run,
temporarily boost `m_walkSpeed`:

```csharp
float originalWalkSpeed = hen.m_walkSpeed;
hen.m_walkSpeed = hen.m_runSpeed * 2f;   // double run speed feels right for "hurrying"
ai.SetFollowTarget(destinationObject);

// On arrival — restore
hen.m_walkSpeed = originalWalkSpeed;
```

Store `originalWalkSpeed` as a field (not a local) so cleanup code (`WakeUp`, `OnDestroy`,
coroutine cancellation) can restore it even if the coroutine is stopped mid-walk.

**Do NOT use `SetAlerted(true)` for speed.** It briefly triggers flee behaviour — the
animal sprints in a random direction before the follow target takes over.
`SetAlerted` is protected on `MonsterAI`; call it via `Traverse` if genuinely needed.

### Preventing wandering after arrival

Clearing the follow target (`SetFollowTarget(null)`) immediately resumes idle wandering.
To hold an animal in place after it arrives, keep the follow target pointing at the
destination object — the AI sees it is already close enough and stays put.

```csharp
// Arrived — keep pointing at bed to prevent wandering
ai.SetFollowTarget(bedGameObject);  // NOT null

// When you actually want it to roam again:
ai.SetFollowTarget(null);
```

---

## Walk-to-Destination Coroutine Pattern

A full pattern for sending a creature to a target, waiting for arrival, then settling it:

```csharp
private Coroutine m_tuckCoroutine;
private float m_originalWalkSpeed;

public void StartWalking(Character hen, MonsterAI ai)
{
    m_originalWalkSpeed = hen.m_walkSpeed;
    hen.m_walkSpeed = hen.m_runSpeed * 2f;
    m_tuckCoroutine = StartCoroutine(WalkToTarget(hen, ai));
}

private IEnumerator WalkToTarget(Character hen, MonsterAI ai)
{
    ai.SetFollowTarget(gameObject);

    float timeout = 20f;
    float elapsed = 0f;
    float arrivalThreshold = 1.5f;

    while (elapsed < timeout)
    {
        if (hen == null || ai == null) yield break;
        if (Vector3.Distance(hen.transform.position, transform.position) <= arrivalThreshold)
            break;
        elapsed += Time.deltaTime;
        yield return null;
    }

    if (hen == null || ai == null) yield break;

    // Restore speed and settle in — keep follow target to prevent wandering
    hen.m_walkSpeed = m_originalWalkSpeed;
    ai.SetFollowTarget(gameObject);

    hen.transform.position = transform.position;
    // ... apply sleeping ZDO, animator bool, etc.

    m_tuckCoroutine = null;
}

public void Cancel(Character hen, MonsterAI ai)
{
    if (m_tuckCoroutine != null)
    {
        StopCoroutine(m_tuckCoroutine);
        m_tuckCoroutine = null;
        if (hen != null) hen.m_walkSpeed = m_originalWalkSpeed;
    }
    if (ai != null) ai.SetFollowTarget(null);
}
```

---

## Sleep System

### How sleep works (server-side)

`Game.UpdateSleeping()` runs every 2 seconds on the server. When all players are in
bed (`EverybodyIsTryingToSleep()` returns true), it calls:

1. `EnvMan.instance.SkipToMorning()` — skips time to morning
2. Sets `m_sleeping = true`
3. Sends `SleepStart` RPC to all clients

When `EnvMan` finishes the time skip (`!IsTimeSkipping()`), `UpdateSleeping` sends
`SleepStop` and sets `m_sleeping = false`.

### Detecting sleep start

**Best hook: `EnvMan.SkipToMorning`** (public method, patches cleanly):

```csharp
[HarmonyPatch(typeof(EnvMan), nameof(EnvMan.SkipToMorning))]
public static class SleepStartPatch
{
    static void Prefix()
    {
        if (!ZNet.instance.IsServer()) return;
        // All players are sleeping — do server-side work here
    }
}
```

Alternative: patch the private `Game.SleepStop` (by string) to detect morning arrival.

### Detecting when a local player gets into bed

Patch `Player.AttachStart` — it fires with `isBed = true` when the player enters a bed:

```csharp
[HarmonyPatch(typeof(Player), nameof(Player.AttachStart))]
public static class PlayerBedPatch
{
    static void Postfix(Player __instance, bool isBed)
    {
        if (!isBed || __instance != Player.m_localPlayer) return;
        // Local player just got into bed
    }
}
```

### Delaying sleep until creatures arrive

Patch the private `Game.EverybodyIsTryingToSleep` as a Postfix to hold back morning
while creatures are still walking. Use a static counter + timeout:

```csharp
public static int s_pendingArrivals = 0;
public static float s_blockStartTime = 0f;
private const float SleepBlockTimeout = 20f;

[HarmonyPatch(typeof(Game), "EverybodyIsTryingToSleep")]
public static class DelaySleepPatch
{
    static void Postfix(ref bool __result)
    {
        if (!__result) return;                    // already false — don't interfere
        if (s_pendingArrivals <= 0) return;       // all creatures settled

        float elapsed = Time.time - s_blockStartTime;
        if (elapsed < SleepBlockTimeout)
        {
            __result = false;                     // hold back morning
        }
        else
        {
            s_pendingArrivals = 0;                // timeout — let sleep proceed
        }
    }
}
```

Increment `s_pendingArrivals` when each creature starts walking; decrement when it
arrives (or is cancelled). Set `s_blockStartTime = Time.time` on the first increment
each sleep cycle.

`Game.UpdateSleeping` checks `EverybodyIsTryingToSleep` every ~2 seconds, so the delay
has up to a 2-second granularity — morning fires within 2 seconds of the last creature
settling.

---

## Sleeping ZDO State

To put a creature into a sleep pose:

```csharp
var nview = hen.GetComponent<ZNetView>();
if (nview != null && nview.IsValid())
{
    var animator = hen.GetComponentInChildren<Animator>();
    if (animator != null)
        animator.SetBool("sleeping", true);

    nview.GetZDO().Set(ZDOVars.s_sleeping, true);
}
```

Reverse on wake-up. The animator bool drives the visual; the ZDO value persists it
across save/load and replicates to other clients.
