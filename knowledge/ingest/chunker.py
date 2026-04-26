"""Chunking logic for Valheim modding knowledge sources.

The cross-domain primitives — `tag_key`, `tag_flags`, `upsert_chunks`,
`now_iso` — live in `mcp_knowledge_base.chunks` and are re-exported here for
the convenience of existing call-sites in `router.py` / `mcp-service.py`.
"""

from __future__ import annotations

import re

from mcp_knowledge_base import (
    now_iso,
    tag_flags,
    tag_key,
    upsert_chunks,
)

from .extractors import detect_tags, extract_methods, split_classes

__all__ = [
    "chunk_decompile",
    "chunk_docs",
    "chunk_build_error",
    "chunk_build_fix",
    "chunk_publish",
    "chunk_mod_source",
    # Re-exports from mcp_knowledge_base for downstream convenience
    "tag_key",
    "tag_flags",
    "upsert_chunks",
]


def chunk_decompile(source: str, dll_name: str = "assembly_valheim") -> list[dict]:
    """Chunk decompiled DLL output by class and method.

    Handles both single-class (ilspycmd -t) and multi-class (full DLL) input.
    Returns list of dicts ready for ChromaDB insertion:
        {id, document, metadata}
    """
    now = now_iso()
    chunks = []

    for cls in split_classes(source):
        class_name = cls["name"]
        class_source = cls["body"]
        methods = extract_methods(class_source)

        if not methods:
            tags = detect_tags(class_source)
            chunks.append({
                "id": f"decompile/{dll_name}/{class_name}",
                "document": class_source,
                "metadata": {
                    "source": f"decompile/{dll_name}/{class_name}",
                    "type": "class",
                    "class_name": class_name,
                    "method_name": "",
                    "tags": ",".join(tags),
                    "indexed_at": now,
                    "project": "",                },
            })
            continue

        seen: dict[str, int] = {}
        for method in methods:
            tags = detect_tags(method["body"])
            name = method["name"]
            seen[name] = seen.get(name, 0) + 1
            suffix = f"_{seen[name]}" if seen[name] > 1 else ""
            method_id = f"decompile/{dll_name}/{class_name}/{name}{suffix}"
            chunks.append({
                "id": method_id,
                "document": method["body"],
                "metadata": {
                    "source": f"decompile/{dll_name}/{class_name}",
                    "type": "method",
                    "class_name": class_name,
                    "method_name": name,
                    "tags": ",".join(tags),
                    "indexed_at": now,
                    "project": "",                },
            })

    # Deduplicate IDs globally (e.g. generic class variants with the same name)
    seen_ids: dict[str, int] = {}
    for chunk in chunks:
        cid = chunk["id"]
        if cid in seen_ids:
            seen_ids[cid] += 1
            chunk["id"] = f"{cid}_{seen_ids[cid]}"
        else:
            seen_ids[cid] = 1

    return chunks


def chunk_docs(text: str, filename: str) -> list[dict]:
    """Chunk a markdown doc by ## headers.

    Returns list of dicts ready for ChromaDB insertion.
    """
    # Split on ## headers, keeping the header with the content
    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    now = now_iso()
    chunks = []

    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue

        # Extract section title
        title_match = re.match(r"^##\s+(.+)", section)
        title = title_match.group(1).strip() if title_match else f"section_{i}"
        safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title)[:80]

        tags = detect_tags(section)
        # Add a tag from the filename (e.g. MODDING_HARMONY.md -> harmony)
        file_tag = filename.replace("MODDING_", "").replace("VALHEIM_", "").replace(".md", "").lower()
        if file_tag and file_tag not in tags:
            tags.insert(0, file_tag)

        chunk_id = f"docs/{filename}/{safe_title}"
        chunks.append({
            "id": chunk_id,
            "document": section,
            "metadata": {
                "source": f"docs/{filename}",
                "type": "section",
                "class_name": "",
                "method_name": "",
                "tags": ",".join(tags),
                "indexed_at": now,
                "project": "",
                **tag_flags(tags),
            },
        })

    return chunks


def chunk_build_error(error_text: str, project: str) -> dict:
    """Create a single chunk for a build error."""
    tags = ["build-error", project.lower()] + detect_tags(error_text)
    return {
        "id": f"build-error/{project}/{now_iso()}",
        "document": error_text,
        "metadata": {
            "source": f"build-error/{project}",
            "type": "error",
            "class_name": "",
            "method_name": "",
            "tags": ",".join(tags),
            "indexed_at": now_iso(),
            "project": project,
            **tag_flags(tags),
        },
    }


def chunk_build_fix(error_text: str, fix_context: str, project: str) -> dict:
    """Create a single chunk for an error->fix pair."""
    combined = f"ERROR:\n{error_text}\n\nFIX (successful build after the above error):\n{fix_context}"
    tags = ["build-fix", project.lower()] + detect_tags(combined)
    return {
        "id": f"build-fix/{project}/{now_iso()}",
        "document": combined,
        "metadata": {
            "source": f"build-fix/{project}",
            "type": "pattern",
            "class_name": "",
            "method_name": "",
            "tags": ",".join(tags),
            "indexed_at": now_iso(),
            "project": project,
            **tag_flags(tags),
        },
    }


def chunk_publish(manifest: str, project: str, mod_name: str) -> dict:
    """Create a chunk for a successful publish event."""
    tags = ["publish", project.lower(), mod_name.lower()]
    return {
        "id": f"publish/{project}/{now_iso()}",
        "document": manifest,
        "metadata": {
            "source": f"publish/{project}",
            "type": "pattern",
            "class_name": "",
            "method_name": "",
            "tags": ",".join(tags),
            "indexed_at": now_iso(),
            "project": project,
        },
    }


def chunk_mod_source(source: str, project: str, class_name: str) -> list[dict]:
    """Chunk mod source code by class (one chunk per file/class)."""
    tags = ["mod-source", project.lower()] + detect_tags(source)
    now = now_iso()
    return [{
        "id": f"mod-source/{project}/{class_name}",
        "document": source,
        "metadata": {
            "source": f"mod-source/{project}",
            "type": "class",
            "class_name": class_name,
            "method_name": "",
            "tags": ",".join(tags),
            "indexed_at": now,
            "project": project,
        },
    }]
