"""
opsmindai/memory/cache_eviction.py

TTL and relevance-based eviction for the RAG knowledge base (SRS FR-17).

Eviction criteria:
  - Entry age > ttl_days (default 90)
  - Relevance score < min_score (default 0.3)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from opsmindai.memory.vector_store import _collection, delete, stats, init_store
from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_TTL_DAYS   = 90
_DEFAULT_MIN_SCORE  = 0.3


def evict_stale(
    ttl_days:  int   = _DEFAULT_TTL_DAYS,
    min_score: float = _DEFAULT_MIN_SCORE,
) -> int:
    """
    Evict KB entries older than ttl_days or with relevance < min_score.

    Args:
        ttl_days:  Maximum age in days before eviction.
        min_score: Minimum relevance score to retain an entry.

    Returns:
        Number of entries evicted.
    """
    backend  = settings.VECTOR_STORE.lower()
    evicted  = 0
    cutoff   = datetime.now(timezone.utc) - timedelta(days=ttl_days)

    if backend == "chromadb":
        evicted = _evict_chromadb(cutoff, min_score)
    elif backend == "qdrant":
        evicted = _evict_qdrant(cutoff, min_score)
    else:
        logger.warning("cache_eviction: unknown backend %s", backend)

    logger.info(
        "cache_eviction: evicted=%d ttl_days=%d min_score=%.2f",
        evicted, ttl_days, min_score,
    )
    return evicted


def _evict_chromadb(cutoff: datetime, min_score: float) -> int:
    """Scan ChromaDB collection and remove stale / low-relevance entries."""
    try:
        col     = _collection()
        results = col.get(include=["metadatas"])
        evicted = 0

        for entry_id, meta in zip(results["ids"], results["metadatas"]):
            meta = meta or {}

            # Age check
            updated_str = meta.get("_updated_at", "")
            if updated_str:
                try:
                    updated_at = datetime.fromisoformat(updated_str)
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                    if updated_at < cutoff:
                        delete(entry_id)
                        evicted += 1
                        continue
                except ValueError:
                    pass

            # Relevance score check
            score_str = meta.get("relevance_score", "")
            if score_str:
                try:
                    if float(score_str) < min_score:
                        delete(entry_id)
                        evicted += 1
                except (ValueError, TypeError):
                    pass

        return evicted
    except Exception as exc:
        logger.error("cache_eviction chromadb error: %s", exc)
        return 0


def _evict_qdrant(cutoff: datetime, min_score: float) -> int:
    """Scan Qdrant collection and remove stale / low-relevance entries."""
    try:
        from qdrant_client.models import Filter, FieldCondition, Range  # type: ignore
        client  = init_store()
        evicted = 0
        offset  = None

        while True:
            response, next_offset = client.scroll(
                collection_name="opsmindai_kb",
                limit=100,
                offset=offset,
                with_payload=True,
            )

            ids_to_delete = []
            for point in response:
                payload    = point.payload or {}
                updated_str = payload.get("_updated_at", "")
                if updated_str:
                    try:
                        updated_at = datetime.fromisoformat(updated_str)
                        if updated_at.tzinfo is None:
                            updated_at = updated_at.replace(tzinfo=timezone.utc)
                        if updated_at < cutoff:
                            ids_to_delete.append(point.id)
                            continue
                    except ValueError:
                        pass

                score = payload.get("relevance_score")
                if score is not None:
                    try:
                        if float(score) < min_score:
                            ids_to_delete.append(point.id)
                    except (ValueError, TypeError):
                        pass

            if ids_to_delete:
                client.delete(
                    collection_name="opsmindai_kb",
                    points_selector=ids_to_delete,
                )
                evicted += len(ids_to_delete)

            if next_offset is None:
                break
            offset = next_offset

        return evicted
    except Exception as exc:
        logger.error("cache_eviction qdrant error: %s", exc)
        return 0


def flush(
    ttl_days:  Optional[int]   = None,
    min_score: Optional[float] = None,
) -> dict:
    """
    Public flush endpoint called by POST /memory/flush.

    Args:
        ttl_days:  Override default TTL (days).
        min_score: Override minimum relevance score.

    Returns:
        Dict with flushed_count and kb_stats after eviction.
    """
    flushed = evict_stale(
        ttl_days  = ttl_days  if ttl_days  is not None else _DEFAULT_TTL_DAYS,
        min_score = min_score if min_score is not None else _DEFAULT_MIN_SCORE,
    )
    return {
        "flushed_count": flushed,
        "kb_stats":      stats(),
    }
