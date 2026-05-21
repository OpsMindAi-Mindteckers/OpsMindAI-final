"""
opsmindai/tasks/refactor_tasks.py

Celery task definitions for the three-phase refactor pipeline.

Workers are started with:
    celery -A opsmindai.tasks.refactor_tasks worker --loglevel=info -Q refactor

Each task is intentionally thin — it resolves Redis, delegates to the
agent, and handles top-level error logging so Celery sees a proper failure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import redis as sync_redis  # sync client — Celery tasks are not async

from opsmindai.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# ── Sync Redis helper (Celery context is sync) ────────────────────────────────

def _sync_redis():
    """Return a synchronous Redis client for use inside Celery tasks."""
    return sync_redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )


class _AsyncRedisAdapter:
    """
    Minimal async-compatible wrapper around the sync redis client.
    Used so that agent.py (written async) works inside a sync Celery task
    via asyncio.run().
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

    async def expire(self, key: str, ttl: int):
        return self._r.expire(key, ttl)


# ── Tasks ─────────────────────────────────────────────────────────────────────

@celery_app.task(
    name="refactor.run_analysis",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    queue="refactor",
    acks_late=True,              # don't ack until task completes
    reject_on_worker_lost=True,
)
def task_run_analysis(self, job_id: str, payload: dict) -> None:
    """
    Phase 1 — Clone repo, run AST + smell detection, persist results to Redis + DB.

    Args:
        job_id:  Unique job identifier (UUID string).
        payload: Dict containing repo_url, branch, file_paths, severity_threshold,
                 user_id.
    """
    from opsmindai.agents.refactor.agent import run_analysis

    logger.info("[task_run_analysis] job=%s starting", job_id)
    r = _sync_redis()
    redis = _AsyncRedisAdapter(r)

    try:
        asyncio.run(run_analysis(job_id, payload, redis))
        logger.info("[task_run_analysis] job=%s completed", job_id)
    except Exception as exc:
        logger.exception("[task_run_analysis] job=%s failed: %s", job_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[task_run_analysis] job=%s max retries exceeded", job_id)
            raise
    finally:
        r.close()


@celery_app.task(
    name="refactor.run_suggest",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    queue="refactor",
    acks_late=True,
    reject_on_worker_lost=True,
)
def task_run_suggest(self, job_id: str, payload: dict) -> None:
    """
    Phase 2 — Generate LLM refactor suggestions for detected smells.

    Args:
        job_id:  Unique job identifier.
        payload: Dict containing repo_url, branch, smells (list of SmellItem dicts).
    """
    from opsmindai.agents.refactor.agent import run_suggest

    logger.info("[task_run_suggest] job=%s starting", job_id)
    r = _sync_redis()
    redis = _AsyncRedisAdapter(r)

    try:
        asyncio.run(run_suggest(job_id, payload, redis))
        logger.info("[task_run_suggest] job=%s completed", job_id)
    except Exception as exc:
        logger.exception("[task_run_suggest] job=%s failed: %s", job_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[task_run_suggest] job=%s max retries exceeded", job_id)
            raise
    finally:
        r.close()


@celery_app.task(
    name="refactor.run_apply",
    bind=True,
    max_retries=1,           # applying patches is destructive — limit retries
    default_retry_delay=30,
    queue="refactor",
    acks_late=True,
    reject_on_worker_lost=True,
)
def task_run_apply(self, job_id: str, payload: dict) -> None:
    """
    Phase 3 — Apply patches and open GitHub PR.

    Args:
        job_id:  Unique job identifier.
        payload: Dict containing repo_url, branch, patches, smells, pr_title,
                 pr_body, draft, notify_slack, source_job_id.
    """
    from opsmindai.agents.refactor.agent import run_apply

    logger.info("[task_run_apply] job=%s starting", job_id)
    r = _sync_redis()
    redis = _AsyncRedisAdapter(r)

    try:
        asyncio.run(run_apply(job_id, payload, redis))
        logger.info("[task_run_apply] job=%s completed", job_id)
    except Exception as exc:
        logger.exception("[task_run_apply] job=%s failed: %s", job_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[task_run_apply] job=%s max retries exceeded", job_id)
            raise
    finally:
        r.close()