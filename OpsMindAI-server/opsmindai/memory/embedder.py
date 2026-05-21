"""
opsmindai/memory/embedder.py

Sentence-transformers embedding wrapper (SRS FR-11).

Uses all-MiniLM-L6-v2 (384 dims). Model is loaded once at startup
and cached in a module-level variable to avoid repeated disk I/O.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level model cache — loaded once on first call
_model: Optional[object] = None
_MODEL_NAME = "all-MiniLM-L6-v2"


def load_model() -> object:
    """
    Load all-MiniLM-L6-v2 once at startup and cache it.

    Returns:
        SentenceTransformer model instance.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # type: ignore
        logger.info("embedder: loading model %s …", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("embedder: model loaded, dims=384")
    return _model


def embed(text: str) -> list[float]:
    """
    Embed a single text string into a 384-dim vector.

    Args:
        text: Input text to embed.

    Returns:
        List of 384 floats (cosine-comparable).
    """
    model  = load_model()
    vector = model.encode(text, normalize_embeddings=True)  # type: ignore
    return vector.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Batch-embed a list of texts for efficiency.

    Args:
        texts: List of input strings.

    Returns:
        List of 384-dim float vectors, one per input.
    """
    if not texts:
        return []
    model   = load_model()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)  # type: ignore
    return [v.tolist() for v in vectors]
