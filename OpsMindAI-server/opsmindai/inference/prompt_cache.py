"""
opsmindai/inference/prompt_cache.py

Redis-backed prefix caching for LLM prompts (SRS FR-16).

Reduces redundant token processing on repeated prompts by caching
prompt→response pairs under a SHA-256 fingerprint key with configurable TTL.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 3600      # 1 hour
_KEY_PREFIX  = "prompt_cache:"


def _cache_key(prompt: str, system: Optional[str], task_type: str) -> str:
    """Compute a stable Redis key from the prompt fingerprint."""
    raw    = f"{task_type}:{system or ''}:{prompt}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return f"{_KEY_PREFIX}{digest}"


async def get_cached(
    redis: aioredis.Redis,
    prompt: str,
    system: Optional[str],
    task_type: str,
) -> Optional[str]:
    """
    Return a cached LLM response, or None on miss.

    Args:
        redis:     Async Redis client.
        prompt:    Full user prompt.
        system:    System instruction (or None).
        task_type: Task category string.

    Returns:
        Cached response text, or None.
    """
    key = _cache_key(prompt, system, task_type)
    try:
        value = await redis.get(key)
        if value:
            logger.debug("prompt_cache HIT key=%s", key)
            return value
    except Exception as exc:
        logger.warning("prompt_cache get error: %s", exc)
    return None


async def set_cached(
    redis: aioredis.Redis,
    prompt: str,
    system: Optional[str],
    task_type: str,
    response: str,
    ttl: int = _DEFAULT_TTL,
) -> None:
    """
    Store a prompt→response pair in Redis.

    Args:
        redis:     Async Redis client.
        prompt:    Full user prompt.
        system:    System instruction (or None).
        task_type: Task category string.
        response:  LLM-generated text to cache.
        ttl:       Expiry in seconds (default 3600).
    """
    key = _cache_key(prompt, system, task_type)
    try:
        await redis.setex(key, ttl, response)
        logger.debug("prompt_cache SET key=%s ttl=%ds", key, ttl)
    except Exception as exc:
        logger.warning("prompt_cache set error: %s", exc)


async def call_llm_cached(
    prompt: str,
    task_type: str = "default",
    system_prompt: Optional[str] = None,
    redis: Optional[aioredis.Redis] = None,
    ttl: int = _DEFAULT_TTL,
) -> str:
    """
    Call hybrid_router.call_llm with Redis prefix caching.

    Cache hit  → returns immediately without LLM call.
    Cache miss → calls LLM, stores result, returns text.

    Args:
        prompt:        User prompt.
        task_type:     Task category for routing.
        system_prompt: Optional system instruction.
        redis:         Async Redis client (caching disabled if None).
        ttl:           Cache TTL in seconds.

    Returns:
        Generated (or cached) text string.
    """
    from opsmindai.inference.hybrid_router import call_llm

    if redis is not None:
        hit = await get_cached(redis, prompt, system_prompt, task_type)
        if hit is not None:
            return hit

    response = await call_llm(prompt, task_type, system_prompt)

    if redis is not None:
        await set_cached(redis, prompt, system_prompt, task_type, response, ttl)

    return response
