"""
opsmindai/memory/rag_pipeline.py

RAG pipeline — retrieve context and store results (SRS §6.3).

Functions:
  retrieve_context  — embed query, search vector store, return top-k results
  build_rag_prompt  — prepend retrieved context block to a base prompt
  store_result      — embed content and upsert into the KB
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Single RAG search hit."""
    entry_id: str
    score:    float
    content:  str
    type:     str
    metadata: dict[str, Any] = field(default_factory=dict)


async def retrieve_context(
    query:       str,
    top_k:       int            = 5,
    filter_type: Optional[str]  = None,
) -> list[SearchResult]:
    """
    Embed query, search the vector store, and return top-k results (SRS FR-12).

    Args:
        query:       Natural-language search query.
        top_k:       Maximum number of results to return.
        filter_type: Optional metadata filter ('incident', 'pattern', 'test_result').

    Returns:
        List of SearchResult objects sorted by descending similarity score.
    """
    from opsmindai.memory.embedder import embed
    from opsmindai.memory.vector_store import search

    try:
        vector = embed(query)
        hits   = search(vector, top_k=top_k, filter_type=filter_type)
        return [
            SearchResult(
                entry_id = h["entry_id"],
                score    = h["score"],
                content  = h["content"],
                type     = h["type"],
                metadata = h["metadata"],
            )
            for h in hits
        ]
    except Exception as exc:
        logger.warning("retrieve_context failed (non-fatal): %s", exc)
        return []


def build_rag_prompt(base_prompt: str, context: list[SearchResult]) -> str:
    """
    Prepend a 'Relevant past context:' block to a base prompt (SRS §6.3).

    Args:
        base_prompt: The original agent prompt.
        context:     List of SearchResult objects from retrieve_context().

    Returns:
        Augmented prompt string with context prepended.
    """
    if not context:
        return base_prompt

    snippets = "\n\n".join(
        f"[{i+1}] (score={r.score:.3f}, type={r.type})\n{r.content}"
        for i, r in enumerate(context)
    )
    return (
        f"Relevant past context:\n"
        f"{'─' * 60}\n"
        f"{snippets}\n"
        f"{'─' * 60}\n\n"
        f"{base_prompt}"
    )


async def store_result(
    content:  str,
    type:     str,
    metadata: dict[str, Any],
) -> str:
    """
    Embed content and upsert into the RAG knowledge base (SRS §6.3).

    Args:
        content:  Text content to index.
        type:     Entry type ('incident', 'pattern', 'test_result').
        metadata: Arbitrary metadata dict.

    Returns:
        entry_id of the stored document.
    """
    from opsmindai.memory.embedder import embed
    from opsmindai.memory.vector_store import upsert

    entry_id = f"{type}_{uuid.uuid4().hex[:16]}"
    vector   = embed(content)

    upsert(
        entry_id = entry_id,
        vector   = vector,
        content  = content,
        metadata = {"type": type, **metadata},
    )

    logger.info("rag_pipeline store_result: type=%s entry_id=%s", type, entry_id)
    return entry_id


# ── Legacy async-class shim (kept for backward-compat with existing callers) ──

class RAGPipeline:
    """Thin wrapper around module-level functions for callers using the class API."""

    async def retrieve(
        self,
        query:       str,
        top_k:       int           = 5,
        filter_type: Optional[str] = None,
        threshold:   float         = 0.0,
    ) -> list[SearchResult]:
        results = await retrieve_context(query, top_k, filter_type)
        return [r for r in results if r.score >= threshold]

    async def add_results(self, content: str, metadata: dict) -> None:
        doc_type = metadata.get("type", "pattern")
        await store_result(content, doc_type, metadata)
