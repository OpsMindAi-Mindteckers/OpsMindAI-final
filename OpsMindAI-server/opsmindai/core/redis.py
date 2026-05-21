"""
opsmindai/core/redis.py

Redis client factory + FastAPI dependency.

Usage in endpoints:
    redis = Depends(get_redis)

Injected into app.state.redis during lifespan (main.py).
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Request

from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

# ── Pool (created once at startup) ───────────────────────────────────────────

_pool: aioredis.ConnectionPool | None = None


def create_redis_pool() -> aioredis.ConnectionPool:
    """Create the module-level connection pool.  Called once from lifespan."""
    global _pool
    _pool = aioredis.ConnectionPool.from_url(
        settings.REDIS_URL,          # e.g. redis://localhost:6379/0
        max_connections=20,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )
    logger.info("Redis pool created → %s", settings.REDIS_URL)
    return _pool


async def close_redis_pool() -> None:
    """Drain the pool at shutdown."""
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None
        logger.info("Redis pool closed")


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_redis(request: Request) -> AsyncGenerator[aioredis.Redis, None]:
    """
    Yield a Redis client bound to the app-level pool.
    Use as:  redis: aioredis.Redis = Depends(get_redis)
    """
    client: aioredis.Redis = aioredis.Redis(connection_pool=request.app.state.redis_pool)
    try:
        yield client
    finally:
        await client.aclose()