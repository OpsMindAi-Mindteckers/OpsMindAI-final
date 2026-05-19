"""
opsmindai/memory/vector_store.py

Vector store abstraction — ChromaDB (dev) or Qdrant (prod) (SRS FR-10).

Switchable via VECTOR_STORE env var without code change.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

_chroma_client: Any  = None
_qdrant_client: Any  = None


# ── Store initialisation ───────────────────────────────────────────────────────

def init_store() -> Any:
    """
    Read VECTOR_STORE env var and return the appropriate client.

    Returns ChromaDB client for 'chromadb', Qdrant client for 'qdrant'.
    Called once at startup; repeated calls return the cached client.
    """
    global _chroma_client, _qdrant_client
    backend = settings.VECTOR_STORE.lower()

    if backend == "chromadb":
        if _chroma_client is None:
            import chromadb  # type: ignore
            _chroma_client = chromadb.PersistentClient(path=settings.CHROMADB_PATH)
            logger.info("vector_store: ChromaDB initialised at %s", settings.CHROMADB_PATH)
        return _chroma_client

    if backend == "qdrant":
        if _qdrant_client is None:
            from qdrant_client import QdrantClient  # type: ignore
            _qdrant_client = QdrantClient(url=settings.QDRANT_URL)
            logger.info("vector_store: Qdrant initialised at %s", settings.QDRANT_URL)
        return _qdrant_client

    raise RuntimeError(f"Unknown VECTOR_STORE: {backend!r}. Expected 'chromadb' or 'qdrant'.")


def _collection():
    """Return the ChromaDB collection (creates it if missing)."""
    client = init_store()
    return client.get_or_create_collection(
        name="opsmindai_kb",
        metadata={"hnsw:space": "cosine"},
    )


# ── CRUD operations ────────────────────────────────────────────────────────────

def upsert(
    entry_id: str,
    vector:   list[float],
    content:  str,
    metadata: dict[str, Any],
) -> None:
    """
    Insert or update an entry in the vector store.

    Args:
        entry_id: Stable unique identifier for this document.
        vector:   384-dim embedding vector.
        content:  Raw text content.
        metadata: Arbitrary key-value metadata (must be JSON-serialisable strings/ints/floats).
    """
    backend = settings.VECTOR_STORE.lower()

    if backend == "chromadb":
        col = _collection()
        safe_meta = {k: str(v) for k, v in metadata.items()}
        safe_meta["_content"] = content
        safe_meta["_updated_at"] = datetime.now(timezone.utc).isoformat()
        col.upsert(
            ids=[entry_id],
            embeddings=[vector],
            documents=[content],
            metadatas=[safe_meta],
        )
        logger.debug("vector_store upsert: id=%s", entry_id)

    elif backend == "qdrant":
        from qdrant_client.models import PointStruct  # type: ignore
        client = init_store()
        client.upsert(
            collection_name="opsmindai_kb",
            points=[PointStruct(
                id=abs(hash(entry_id)) % (2**63),
                vector=vector,
                payload={**metadata, "_content": content, "_entry_id": entry_id},
            )],
        )
        logger.debug("vector_store qdrant upsert: id=%s", entry_id)


def search(
    query_vector: list[float],
    top_k: int = 5,
    filter_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Return top_k nearest neighbours with score + content.

    Args:
        query_vector: 384-dim query embedding.
        top_k:        Maximum results to return.
        filter_type:  Optional 'type' metadata filter ('incident', 'pattern', 'test_result').

    Returns:
        List of dicts: {entry_id, score, content, type, metadata}.
    """
    backend = settings.VECTOR_STORE.lower()

    if backend == "chromadb":
        col     = _collection()
        where   = {"type": filter_type} if filter_type else None
        results = col.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[dict[str, Any]] = []
        for idx in range(len(results["ids"][0])):
            meta = results["metadatas"][0][idx] or {}
            hits.append({
                "entry_id": results["ids"][0][idx],
                "score":    1.0 - results["distances"][0][idx],
                "content":  results["documents"][0][idx],
                "type":     meta.get("type", "unknown"),
                "metadata": meta,
            })
        return sorted(hits, key=lambda h: h["score"], reverse=True)

    elif backend == "qdrant":
        from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore
        client      = init_store()
        qdrant_filter = None
        if filter_type:
            qdrant_filter = Filter(
                must=[FieldCondition(key="type", match=MatchValue(value=filter_type))]
            )
        results = client.search(
            collection_name="opsmindai_kb",
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )
        return [
            {
                "entry_id": r.payload.get("_entry_id", str(r.id)),
                "score":    r.score,
                "content":  r.payload.get("_content", ""),
                "type":     r.payload.get("type", "unknown"),
                "metadata": r.payload,
            }
            for r in results
        ]

    return []


def delete(entry_id: str) -> None:
    """
    Remove an entry by ID.

    Args:
        entry_id: The stable ID used during upsert.
    """
    backend = settings.VECTOR_STORE.lower()
    if backend == "chromadb":
        _collection().delete(ids=[entry_id])
    elif backend == "qdrant":
        client = init_store()
        client.delete(
            collection_name="opsmindai_kb",
            points_selector=[abs(hash(entry_id)) % (2**63)],
        )
    logger.debug("vector_store delete: id=%s", entry_id)


def stats() -> dict[str, Any]:
    """
    Return KB statistics.

    Returns:
        Dict with total_entries, by_type, last_updated, index_health.
    """
    try:
        backend = settings.VECTOR_STORE.lower()
        if backend == "chromadb":
            col   = _collection()
            count = col.count()
            return {
                "total_entries": count,
                "by_type":       {},
                "last_updated":  datetime.now(timezone.utc).isoformat(),
                "index_health":  "healthy",
                "backend":       "chromadb",
            }
        elif backend == "qdrant":
            client = init_store()
            info   = client.get_collection("opsmindai_kb")
            return {
                "total_entries": info.points_count,
                "by_type":       {},
                "last_updated":  datetime.now(timezone.utc).isoformat(),
                "index_health":  "healthy",
                "backend":       "qdrant",
            }
    except Exception as exc:
        logger.warning("vector_store stats error: %s", exc)
        return {
            "total_entries": 0,
            "by_type":       {},
            "last_updated":  datetime.now(timezone.utc).isoformat(),
            "index_health":  "degraded",
        }
    return {}
