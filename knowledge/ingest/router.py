"""Ingest router: decides what to do with each tool execution payload."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from mcp_knowledge_base import IngestRouter

from .chunker import (
    chunk_build_error,
    chunk_build_fix,
    chunk_decompile,
    chunk_publish,
    upsert_chunks,
)
from .extractors import extract_cs_errors

if TYPE_CHECKING:
    import chromadb

logger = logging.getLogger("mcp-knowledge.router")

# Persist the payload buffer to survive container restarts
BUFFER_PATH = Path("/opt/knowledge/buffer.json")
MAX_BUFFER_SIZE = 20

# Tools we skip entirely — routine, no knowledge value
SKIP_TOOLS = {
    "deploy_server",
    "deploy_client",
    "package",
    "start_server",
    "stop_server",
    "start_client",
    "stop_client",
}


class ValheimIngestRouter(IngestRouter):
    """Routes incoming tool payloads to the appropriate chunking/indexing logic."""

    def __init__(self, collection: "chromadb.Collection"):
        self.collection = collection
        self._recent: list[dict] = self._load_buffer()

    def _load_buffer(self) -> list[dict]:
        """Load recent payload buffer from disk."""
        try:
            if BUFFER_PATH.exists():
                data = json.loads(BUFFER_PATH.read_text())
                if isinstance(data, list):
                    return data[-MAX_BUFFER_SIZE:]
        except Exception:
            logger.warning("Failed to load payload buffer, starting fresh")
        return []

    def _save_buffer(self):
        """Persist recent payload buffer to disk."""
        try:
            BUFFER_PATH.parent.mkdir(parents=True, exist_ok=True)
            BUFFER_PATH.write_text(json.dumps(self._recent[-MAX_BUFFER_SIZE:]))
        except Exception:
            logger.warning("Failed to persist payload buffer")

    def _push_recent(self, payload: dict):
        self._recent.append(payload)
        if len(self._recent) > MAX_BUFFER_SIZE:
            self._recent = self._recent[-MAX_BUFFER_SIZE:]
        self._save_buffer()

    def _last_failure_for_project(self, project: str) -> dict | None:
        """Find the most recent build failure for a given project."""
        for p in reversed(self._recent):
            if p.get("tool") == "build" and p.get("args", {}).get("project") == project:
                if not p.get("success"):
                    return p
                # Hit a success before finding a failure — no pending failure
                return None
        return None

    def _index_chunks(self, chunks: list[dict]):
        """Upsert chunks into ChromaDB."""
        if not chunks:
            return
        upsert_chunks(self.collection, chunks)
        logger.info("Indexed %d chunks", len(chunks))

    def route(self, payload: dict) -> dict:
        """Route a payload and return a status summary.

        Returns: {"action": str, "chunks": int}
        """
        tool = payload.get("tool", "")
        success = payload.get("success", True)
        result = payload.get("result", "")
        args = payload.get("args", {})

        # Skip routine tools
        if tool in SKIP_TOOLS:
            return {"action": "skipped", "chunks": 0}

        # --- Build payloads ---
        if tool == "build":
            project = args.get("project", "unknown")

            # Check for prior failure BEFORE pushing current payload,
            # otherwise the success finds itself and bails early
            prior_failure = self._last_failure_for_project(project) if success else None

            self._push_recent(payload)

            if not success:
                # Index the build error
                errors = extract_cs_errors(result)
                error_text = "\n".join(errors) if errors else result
                chunk = chunk_build_error(error_text, project)
                self._index_chunks([chunk])
                return {"action": "indexed_build_error", "chunks": 1}

            # Success — use the prior failure we found above
            if prior_failure:
                error_text = prior_failure.get("result", "")
                errors = extract_cs_errors(error_text)
                if errors:
                    error_text = "\n".join(errors)
                chunk = chunk_build_fix(error_text, result, project)
                self._index_chunks([chunk])
                return {"action": "indexed_build_fix", "chunks": 1}

            # Routine success, skip
            return {"action": "skipped_routine_success", "chunks": 0}

        # --- Decompile payloads ---
        if tool == "decompile_dll":
            chunks = chunk_decompile(result)
            self._index_chunks(chunks)
            return {"action": "indexed_decompile", "chunks": len(chunks)}

        # --- Publish payloads ---
        if tool == "publish":
            project = args.get("project", "unknown")
            self._push_recent(payload)

            if not success:
                chunk = chunk_build_error(result, project)
                chunk["metadata"]["tags"] = chunk["metadata"]["tags"].replace(
                    "build-error", "publish-error"
                )
                chunk["metadata"]["source"] = f"publish-error/{project}"
                chunk["id"] = f"publish-error/{project}/{chunk['metadata']['indexed_at']}"
                self._index_chunks([chunk])
                return {"action": "indexed_publish_error", "chunks": 1}

            mod_name = args.get("mod_name", project)
            chunk = chunk_publish(result, project, mod_name)
            self._index_chunks([chunk])
            return {"action": "indexed_publish", "chunks": 1}

        # Unknown tool — skip
        logger.debug("Unhandled tool: %s", tool)
        return {"action": "skipped_unknown", "chunks": 0}
