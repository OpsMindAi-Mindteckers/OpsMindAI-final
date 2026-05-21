"""
opsmindai/tasks/testing_tasks.py

Celery task definitions for the three-phase Testing Agent pipeline.

Workers:
    celery -A opsmindai.tasks.celery_app worker --loglevel=info -Q testing -n test@%h

Each task wraps the corresponding async agent coroutine via asyncio.run()
and bridges the sync Redis client to the async API expected by agent.py.
"""

from __future__ import annotations

import asyncio
import logging
import os

import redis as sync_redis

from opsmindai.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _sync_redis() -> sync_redis.Redis:
    return sync_redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )


class _AsyncRedisAdapter:
    """Thin async wrapper around sync redis.Redis for use in agent coroutines."""

    def __init__(self, client: sync_redis.Redis) -> None:
        self._r = client

    async def get(self, key: str):
        return self._r.get(key)

    async def set(self, key: str, value: str):
        return self._r.set(key, value)

    async def setex(self, key: str, ttl: int, value: str):
        return self._r.setex(key, ttl, value)

    async def lpush(self, key: str, *values):
        return self._r.lpush(key, *values)

    async def lrange(self, key: str, start: int, stop: int):
        return self._r.lrange(key, start, stop)

    async def expire(self, key: str, ttl: int):
        return self._r.expire(key, ttl)

    async def delete(self, *keys):
        return self._r.delete(*keys)


# ── Phase 1: Generate test stubs ──────────────────────────────────────────────

@celery_app.task(
    name="testing.run_generation",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    queue="testing",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=660,
)
def task_run_generation(self, job_id: str, payload: dict) -> None:
    """
    Phase 1 — Clone repo, extract function signatures, generate test stubs via LLM.

    Args:
        job_id:  Unique job identifier.
        payload: Dict with repo_url, file_path, branch, framework,
                 coverage_threshold, user_id.
    """
    from opsmindai.agents.testing.agent import run_generation

    logger.info("[testing.run_generation] job=%s starting", job_id)
    r     = _sync_redis()
    redis = _AsyncRedisAdapter(r)
    try:
        asyncio.run(run_generation(job_id, payload, redis))
        logger.info("[testing.run_generation] job=%s completed", job_id)
    except Exception as exc:
        logger.exception("[testing.run_generation] job=%s failed", job_id)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[testing.run_generation] job=%s max retries exceeded", job_id)
            raise
    finally:
        r.close()


# ── Phase 2: Run test suite + coverage gate ───────────────────────────────────

@celery_app.task(
    name="testing.run_suite",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    queue="testing",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=480,
    time_limit=540,
)
def task_run_suite(self, job_id: str, payload: dict) -> None:
    """
    Phase 2 — Execute generated tests, parse coverage, enforce gate.

    Args:
        job_id:  Unique job identifier.
        payload: Dict with job_id (from generation phase), pr_number, user_id.
    """
    from opsmindai.agents.testing.agent import run_suite

    logger.info("[testing.run_suite] job=%s starting", job_id)
    r     = _sync_redis()
    redis = _AsyncRedisAdapter(r)
    try:
        asyncio.run(run_suite(job_id, payload, redis))
        logger.info("[testing.run_suite] job=%s completed", job_id)
    except Exception as exc:
        logger.exception("[testing.run_suite] job=%s failed", job_id)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[testing.run_suite] job=%s max retries exceeded", job_id)
            raise
    finally:
        r.close()


# ── Phase 3: Regression suite ─────────────────────────────────────────────────

@celery_app.task(
    name="testing.run_regression",
    bind=True,
    max_retries=2,
    default_retry_delay=20,
    queue="testing",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=660,
)
def task_run_regression(self, job_id: str, payload: dict) -> None:
    """
    Phase 3 — Generate incident-driven regression + load tests from RAG KB.

    Args:
        job_id:  Unique job identifier.
        payload: Dict with repo_url, branch, trigger_event, user_id.
    """
    from opsmindai.agents.testing.agent import run_regression

    logger.info("[testing.run_regression] job=%s starting", job_id)
    r     = _sync_redis()
    redis = _AsyncRedisAdapter(r)
    try:
        asyncio.run(run_regression(job_id, payload, redis))
        logger.info("[testing.run_regression] job=%s completed", job_id)
    except Exception as exc:
        logger.exception("[testing.run_regression] job=%s failed", job_id)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[testing.run_regression] job=%s max retries exceeded", job_id)
            raise
    finally:
        r.close()
