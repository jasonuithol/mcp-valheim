"""Source-specific extraction: errors, methods, patterns."""

from __future__ import annotations

import re

# Patterns that indicate interesting Valheim systems in decompiled code
PATTERN_TAGS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ZRoutedRpc|RoutedRpc", re.IGNORECASE), "rpc"),
    (re.compile(r"ZDO|m_zdo|GetZDO", re.IGNORECASE), "zdo"),
    (re.compile(r"ZNetPeer|ZNet\b", re.IGNORECASE), "networking"),
    (re.compile(r"ItemDrop|Inventory|m_inventory", re.IGNORECASE), "inventory"),
    (re.compile(r"SEMan|StatusEffect|SE_", re.IGNORECASE), "status-effect"),
    (re.compile(r"Harmony|HarmonyPatch|Prefix|Postfix|Transpiler", re.IGNORECASE), "harmony"),
    (re.compile(r"EnvMan|Weather|GetCurrentEnvironment", re.IGNORECASE), "weather"),
    (re.compile(r"Emote|StartEmote|StopEmote", re.IGNORECASE), "emote"),
    (re.compile(r"Anim|ZSyncAnimation|SetTrigger", re.IGNORECASE), "animation"),
    (re.compile(r"Teleport|TeleportTo|TeleportWorld", re.IGNORECASE), "teleport"),
    # \bPin\b — bare word only, to avoid matching Plugin, Mapping, Opinion, Sniping, etc.
    (re.compile(r"Minimap|\bPin\b|PinData|AddPin|RemovePin|GetClosestPin|MapData", re.IGNORECASE), "minimap"),
    (re.compile(r"Piece|WearNTear|PlacePiece", re.IGNORECASE), "building"),
    (re.compile(r"Raid|RandEventSystem|RandEvent", re.IGNORECASE), "raid"),
    (re.compile(r"VisEquipment|AttachItem|SetModel", re.IGNORECASE), "visual-equip"),
    (re.compile(r"BepInEx|BaseUnityPlugin|ConfigEntry", re.IGNORECASE), "bepinex"),
]


def detect_tags(text: str) -> list[str]:
    """Scan text for known Valheim patterns and return matching tags."""
    tags = []
    for pattern, tag in PATTERN_TAGS:
        if pattern.search(text):
            tags.append(tag)
    return tags


# --- CS error extraction ---

_CS_ERROR_RE = re.compile(r"(error\s+CS\d+.*?)(?:\n|$)", re.IGNORECASE)


def extract_cs_errors(build_log: str) -> list[str]:
    """Extract C# compiler error lines from a build log."""
    return _CS_ERROR_RE.findall(build_log)


# --- Method extraction from decompiled source ---

_METHOD_BOUNDARY_RE = re.compile(
    r"^(?:\t| {4})(?:public|private|protected|internal|static|\s)+"
    r"(?:override\s+|virtual\s+|abstract\s+|sealed\s+|async\s+)*"
    r"\S+\s+(\w+)\s*\(",
    re.MULTILINE,
)


def extract_methods(decompiled_source: str) -> list[dict]:
    """Split decompiled source into method chunks.

    Returns a list of dicts with keys: name, body, start_line.
    """
    matches = list(_METHOD_BOUNDARY_RE.finditer(decompiled_source))
    if not matches:
        return []

    lines = decompiled_source.split("\n")
    methods = []

    for i, match in enumerate(matches):
        name = match.group(1)
        start_line = decompiled_source[: match.start()].count("\n")

        # End is start of next method, or end of source
        if i + 1 < len(matches):
            end_line = decompiled_source[: matches[i + 1].start()].count("\n")
        else:
            end_line = len(lines)

        body = "\n".join(lines[start_line:end_line]).rstrip()
        if body:
            methods.append({"name": name, "body": body, "start_line": start_line})

    return methods


def extract_class_name(decompiled_source: str) -> str | None:
    """Extract the primary class name from decompiled source."""
    m = re.search(
        r"(?:public|internal)\s+(?:sealed\s+|abstract\s+|static\s+)*class\s+(\w+)",
        decompiled_source,
    )
    return m.group(1) if m else None


# --- Class splitting for multi-class decompiled output ---

_CLASS_DECL_RE = re.compile(
    r"^(?:public|internal)\s+(?:sealed\s+|abstract\s+|static\s+)*class\s+(\w+)",
    re.MULTILINE,
)


def split_classes(decompiled_source: str) -> list[dict]:
    """Split decompiled DLL output into per-class blocks.

    Returns a list of dicts with keys: name, body.
    If only one class (or none) is found, returns the whole source as a single entry.
    """
    matches = list(_CLASS_DECL_RE.finditer(decompiled_source))

    if len(matches) <= 1:
        name = matches[0].group(1) if matches else "Unknown"
        return [{"name": name, "body": decompiled_source}]

    classes = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(decompiled_source)
        classes.append({"name": match.group(1), "body": decompiled_source[start:end].rstrip()})

    return classes
