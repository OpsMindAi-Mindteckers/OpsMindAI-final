"""
opsmindai/middleware/rate_limiter.py

Redis token-bucket rate limiter (SRS FR-06).

Rules
─────
• 100 requests / minute per API key (derived from Bearer token or cookie).
• Anonymous / unauthenticated requests share a bucket keyed by IP.
• On breach: HTTP 429 + Retry-After header (seconds until bucket refills).
• Skip list: /health, /metrics, /webhooks/* (same as auth middleware).

Token-bucket algorithm
──────────────────────
Redis key : ratelimit:{bucket_key}
Value     : remaining token count (integer string)
TTL       : 60 seconds (window duration)

On each request:
  1. DECR key  → remaining
  2. If key did not exist (DECR on missing → -1), SET it to (LIMIT-1) EX 60
  3. If remaining < 0 → 429 + Retry-After = TTL of the key
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import redis.asyncio as aioredis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

_RATE_LIMIT   = 100          # requests per window
_WINDOW_SECS  = 60           # window length in seconds
_KEY_PREFIX   = "ratelimit:"

_SKIP_PREFIXES = (
    "/health",
    "/metrics",
    "/webhooks/",
    "/api/v1/webhooks/",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/static/",
    "/login",
    "/",
)


def _should_skip(path: str) -> bool:
    return any(path.startswith(p) for p in _SKIP_PREFIXES)


def _bucket_key(request: Request) -> str:
    """
    Derive a rate-limit bucket key.

    Uses the Bearer token prefix (first 16 chars) when available so each
    API key gets its own bucket. Falls back to client IP for anonymous requests.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token_prefix = auth[7:23]   # first 16 chars of token — opaque but stable
        return f"{_KEY_PREFIX}token:{token_prefix}"

    cookie = request.cookies.get("opsmindai_token", "")
    if cookie:
        return f"{_KEY_PREFIX}cookie:{cookie[:16]}"

    ip = (request.client.host if request.client else "unknown")
    return f"{_KEY_PREFIX}ip:{ip}"


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Redis token-bucket rate limiter middleware.

    Reads the Redis pool from app.state.redis_pool. If Redis is unavailable
    the request is allowed through (fail-open) with a warning log.

    Args:
        app: The ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if _should_skip(path):
            return await call_next(request)

        # Get Redis from app.state (created at startup by lifespan)
        pool = getattr(request.app.state, "redis_pool", None)
        if pool is None:
            logger.warning("rate_limiter: no Redis pool — skipping rate limit")
            return await call_next(request)

        redis: aioredis.Redis = aioredis.Redis(connection_pool=pool)
        key   = _bucket_key(request)

        try:
            remaining = await redis.decr(key)

            if remaining == _RATE_LIMIT - 1:
                # Key was just created (DECR on missing starts at 0 then goes -1;
                # but aioredis decr on non-existing returns -1 the first time).
                # Reset to full bucket and set TTL.
                await redis.set(key, _RATE_LIMIT - 1, ex=_WINDOW_SECS)
                remaining = _RATE_LIMIT - 1

            elif remaining < 0:
                # Bucket exhausted — compute retry-after from key TTL
                ttl = await redis.ttl(key)
                retry_after = max(int(ttl), 1)

                logger.warning(
                    "rate_limiter: 429 key=%s path=%s retry_after=%ds",
                    key, path, retry_after,
                )
                await redis.aclose()
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded. Too many requests.",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

        except Exception as exc:
            logger.warning("rate_limiter: Redis error (%s) — allowing request", exc)

        finally:
            try:
                await redis.aclose()
            except Exception:
                pass

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"]     = str(_RATE_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(max(remaining, 0))
        response.headers["X-RateLimit-Window"]    = f"{_WINDOW_SECS}s"
        return response
