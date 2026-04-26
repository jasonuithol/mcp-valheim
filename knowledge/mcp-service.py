"""mcp-knowledge: RAG-backed Valheim modding knowledge service.

Built on `mcp-knowledge-base`, which provides the FastMCP + ChromaDB +
/ingest scaffolding. This module adds only the valheim-specific pieces:
the chunker, the tag taxonomy, and the bespoke MCP seeding tools.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp_knowledge_base import KnowledgeService, ServiceConfig

from ingest.chunker import (
    chunk_decompile,
    chunk_docs,
    chunk_mod_source,
    tag_flags,
    upsert_chunks,
)
from ingest.extractors import PATTERN_TAGS, detect_tags, extract_class_name
from ingest.router import ValheimIngestRouter

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/opt/projects")

# ---------------------------------------------------------------------------
# Service assembly
# ---------------------------------------------------------------------------

svc = KnowledgeService(ServiceConfig.from_env(
    name="valheim-knowledge",
    collection_name="valheim_knowledge",
    port=5184,
    header_keys=["class_name", "method_name"],
))

# Generic tools: ask, ask_tagged, list_sources, forget (prefix-match), stats.
svc.register_default_tools()
svc.register_retag_all(PATTERN_TAGS, detect_tags)
svc.set_ingest_router(ValheimIngestRouter(svc.collection))

# Aliases for use inside tool closures
collection = svc.collection
mcp = svc.mcp


# ---- Domain-specific query tools -----------------------------------------


@svc.tool()
def ask_class(class_name: str) -> str:
    """Find all indexed knowledge about a specific Valheim class."""
    results = collection.query(
        query_texts=[class_name],
        n_results=10,
        where={"class_name": class_name},
    )
    return svc.format_query(results)


# ---- Domain-specific seeding tools ---------------------------------------


@svc.tool()
def seed_docs(docs_path: str) -> str:
    """One-time: index the curated MODDING_*.md and VALHEIM_*.md docs."""
    docs_dir = Path(docs_path)
    if not docs_dir.is_dir():
        return f"Directory not found: {docs_path}"

    total_chunks = 0
    files_indexed = []

    for md_file in sorted(docs_dir.glob("*.md")):
        name = md_file.name
        if not (name.startswith("MODDING_") or name.startswith("VALHEIM_")):
            continue

        text = md_file.read_text(encoding="utf-8")
        chunks = chunk_docs(text, name)
        if chunks:
            upsert_chunks(collection, chunks)
            total_chunks += len(chunks)
            files_indexed.append(f"  {name}: {len(chunks)} chunks")

    if not files_indexed:
        return f"No MODDING_*.md or VALHEIM_*.md files found in {docs_path}"

    return (
        f"Indexed {total_chunks} chunks from {len(files_indexed)} files:\n"
        + "\n".join(files_indexed)
    )


@svc.tool()
def seed_mod_source(project: str, source_dir: str, extra_tags: list[str] = None) -> str:
    """Index the source code of a mod or modding library.

    Walks *.cs files under source_dir (skipping bin/ and obj/), one chunk per
    file. Each chunk is tagged `mod-source` plus any tags in `extra_tags`.

    Args:
        project: Project name (used in source metadata, tags, and chunk IDs).
        source_dir: Directory containing the .cs files. Absolute paths
            are used as-is; relative paths resolve under PROJECTS_DIR.
        extra_tags: Tags prepended to each chunk's tag list. Defaults to
            `["successful-example"]` — pass e.g. `["library","jotunn"]` when
            indexing a library rather than a shipped mod.
    """
    if extra_tags is None:
        extra_tags = ["successful-example"]

    src_dir = Path(source_dir)
    if not src_dir.is_absolute():
        src_dir = Path(PROJECTS_DIR) / source_dir
    if not src_dir.is_dir():
        return f"Directory not found: {src_dir}"

    cs_files = [
        p for p in src_dir.rglob("*.cs")
        if "bin" not in p.parts and "obj" not in p.parts
    ]
    if not cs_files:
        return f"No .cs files found under {src_dir}"

    tag_prefix = ",".join(extra_tags) + ("," if extra_tags else "")
    all_chunks = []
    for cs in cs_files:
        text = cs.read_text(encoding="utf-8", errors="replace")
        class_name = extract_class_name(text) or cs.stem
        chunks = chunk_mod_source(text, project, class_name)
        for c in chunks:
            c["id"] = f"mod-source/{project}/{cs.stem}"
            c["metadata"]["tags"] = tag_prefix + c["metadata"]["tags"]
        all_chunks.extend(chunks)

    if all_chunks:
        upsert_chunks(collection, all_chunks)

    return (
        f"Indexed {len(all_chunks)} chunks from {len(cs_files)} .cs files "
        f"in project '{project}'"
    )


@svc.tool()
def seed_decompile(decompiled_source: str) -> str:
    """Index decompiled source. Accepts output from a single class or an entire DLL.

    Splits by class automatically, then chunks each class by method.

    Args:
        decompiled_source: The decompiled source text (from ilspycmd).
    """
    if not decompiled_source.strip():
        return "Empty decompile output"

    chunks = chunk_decompile(decompiled_source)
    if chunks:
        BATCH = 5000
        for i in range(0, len(chunks), BATCH):
            upsert_chunks(collection, chunks[i:i + BATCH])

    # Summarise what was indexed
    classes = {c["metadata"]["class_name"] for c in chunks}
    return f"Indexed {len(chunks)} chunks from {len(classes)} classes: {', '.join(sorted(classes))}"


# ---- One-shot maintenance ------------------------------------------------


@svc.tool()
def backfill_tag_keys() -> str:
    """One-shot: add tag_<name>: True metadata keys to all existing chunks.

    Older chunks may store tags only in the comma-joined `tags` string, which
    can't be filtered via ChromaDB metadata `where` clauses. This walks the
    whole collection and upserts each chunk's metadata with the boolean
    tag_* keys derived from that string.
    """
    existing = collection.get(include=["metadatas", "documents"])
    ids = existing["ids"]
    if not ids:
        return "Collection is empty — nothing to backfill."

    updated = 0
    BATCH = 5000
    for i in range(0, len(ids), BATCH):
        batch_ids = ids[i:i + BATCH]
        batch_metas = existing["metadatas"][i:i + BATCH]
        batch_docs = existing["documents"][i:i + BATCH]

        new_metas = []
        for meta in batch_metas:
            tag_str = meta.get("tags", "")
            tags = [t.strip() for t in tag_str.split(",") if t.strip()]
            meta = {**meta, **tag_flags(tags)}
            new_metas.append(meta)

        collection.upsert(ids=batch_ids, documents=batch_docs, metadatas=new_metas)
        updated += len(batch_ids)

    return f"Backfilled tag_* keys on {updated} chunks."


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    svc.run()
