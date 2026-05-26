"""
opsmindai/tasks/testing_tasks.py

Celery task definitions for the three-phase Testing Agent pipeline.

Workers:
    celery -A opsmindai.tasks.testing_tasks worker --loglevel=info -Q testing

Each task is intentionally thin — it bridges the sync Celery context to the
async agent.py coroutines via asyncio.run() and an _AsyncRedisAdapter.
"""

from __future__ import annotations

import asyncio
import logging
import os

import redis as sync_redis

from opsmindai.core.celery_app import celery_app

logger = logging.getLogger(__name__)


def _sync_redis() -> sync_redis.Redis:
    return sync_redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://default:UlZV4uuiRwNdx3uEAJJBTVqJN3e3CG8j@redis-17963.c261.us-east-1-4.ec2.cloud.redislabs.com:17963/0"),
        decode_responses=True,
    )


class _AsyncRedisAdapter:
    """
    Minimal async wrapper around the sync redis.Redis client.
    Mirrors the methods used by agents/testing/agent.py.
    """
    def __init__(self, client: sync_redis.Redis):
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


# ── Phase 1: Generate ─────────────────────────────────────────────────────────

@celery_app.task(
    name="testing.run_generation",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    queue="testing",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,   # LLM generation can be slow for large repos
    time_limit=660,
)
def task_run_generation(self, job_id: str, payload: dict) -> None:
    """Phase 1 — Clone repo, generate LLM test stubs."""
    from opsmindai.agents.testing.agent import run_generation

    logger.info("[testing.run_generation] job=%s repo=%s starting",
                job_id, payload.get("repo_url"))
    r = _sync_redis()
    redis = _AsyncRedisAdapter(r)
    try:
        asyncio.run(run_generation(job_id, payload, redis))
        logger.info("[testing.run_generation] job=%s done", job_id)
    except Exception as exc:
        logger.exception("[testing.run_generation] job=%s failed", job_id)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            raise
    finally:
        r.close()


# ── Phase 2: Suite ────────────────────────────────────────────────────────────

@celery_app.task(
    name="testing.run_suite",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    queue="testing",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=300,   # test execution + coverage parse
    time_limit=360,
)
def task_run_suite(self, job_id: str, payload: dict) -> None:
    """Phase 2 — Execute generated tests and enforce coverage gate."""
    from opsmindai.agents.testing.agent import run_suite

    logger.info("[testing.run_suite] job=%s source_job=%s starting",
                job_id, payload.get("job_id"))
    r = _sync_redis()
    redis = _AsyncRedisAdapter(r)
    try:
        asyncio.run(run_suite(job_id, payload, redis))
        logger.info("[testing.run_suite] job=%s done", job_id)
    except Exception as exc:
        logger.exception("[testing.run_suite] job=%s failed", job_id)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            raise
    finally:
        r.close()


# ── Phase 3: Regression ───────────────────────────────────────────────────────

@celery_app.task(
    name="testing.run_regression",
    bind=True,
    max_retries=2,
    default_retry_delay=20,
    queue="testing",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=480,
    time_limit=540,
)
def task_run_regression(self, job_id: str, payload: dict) -> None:
    """Phase 3 — Build incident-driven regression + load + DB perf test suite."""
    from opsmindai.agents.testing.agent import run_regression

    logger.info("[testing.run_regression] job=%s repo=%s starting",
                job_id, payload.get("repo_url"))
    r = _sync_redis()
    redis = _AsyncRedisAdapter(r)
    try:
        asyncio.run(run_regression(job_id, payload, redis))
        logger.info("[testing.run_regression] job=%s done", job_id)
    except Exception as exc:
        logger.exception("[testing.run_regression] job=%s failed", job_id)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            raise
    finally:
        r.close()