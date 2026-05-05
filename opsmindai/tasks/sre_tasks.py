"""
opsmindai/tasks/sre_tasks.py

Celery task definitions for the SRE-GPT three-phase incident response.

Workers:
    celery -A opsmindai.tasks.celery_app worker --loglevel=info -Q sre

Each task wraps the corresponding async coroutine in agent.py via
asyncio.run() and bridges the sync Redis client to the async API
expected by agent.py.
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
    """
    Minimal async wrapper around sync redis.Redis.
    Mirrors the methods used by sre_gpt/agent.py.
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


# ── Phase 1: Ingest ──────────────────────────────────────────────────────────

@celery_app.task(
    name="sre.run_ingest",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    queue="sre",
    acks_late=True,
    reject_on_worker_lost=True,
    priority=9,    # FR/SRS priority for alerts
)
def task_run_ingest(self, job_id: str, payload: dict) -> None:
    """Phase 1 — Ingest + dedup + auto-dispatch RCA."""
    from opsmindai.agents.sre_gpt.agent import run_ingest

    logger.info("[sre.run_ingest] job=%s starting", job_id)
    r = _sync_redis()
    redis = _AsyncRedisAdapter(r)
    try:
        asyncio.run(run_ingest(job_id, payload, redis))
        logger.info("[sre.run_ingest] job=%s done", job_id)
    except Exception as exc:
        logger.exception("[sre.run_ingest] job=%s failed", job_id)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            raise
    finally:
        r.close()


# ── Phase 2: RCA ──────────────────────────────────────────────────────────────

@celery_app.task(
    name="sre.run_rca",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
    queue="sre",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=300,    # RCA has heavy LLM call — give it 5 min soft
    time_limit=360,
)
def task_run_rca(self, job_id: str, payload: dict) -> None:
    """Phase 2 — Run RCA pipeline."""
    from opsmindai.agents.sre_gpt.agent import run_rca

    logger.info("[sre.run_rca] job=%s incident=%s starting",
                job_id, payload.get("incident_id"))
    r = _sync_redis()
    redis = _AsyncRedisAdapter(r)
    try:
        asyncio.run(run_rca(job_id, payload, redis))
        logger.info("[sre.run_rca] job=%s done", job_id)
    except Exception as exc:
        logger.exception("[sre.run_rca] job=%s failed", job_id)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            raise
    finally:
        r.close()


# ── Phase 3: Remediate ───────────────────────────────────────────────────────

@celery_app.task(
    name="sre.run_remediate",
    bind=True,
    max_retries=2,           # destructive — limited retries
    default_retry_delay=30,
    queue="sre",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=180,     # playbook + 60s normalisation poll
    time_limit=240,
)
def task_run_remediate(self, job_id: str, payload: dict) -> None:
    """Phase 3 — Execute remediation playbook."""
    from opsmindai.agents.sre_gpt.agent import run_remediate

    logger.info("[sre.run_remediate] job=%s incident=%s playbook=%s starting",
                job_id, payload.get("incident_id"), payload.get("playbook"))
    r = _sync_redis()
    redis = _AsyncRedisAdapter(r)
    try:
        asyncio.run(run_remediate(job_id, payload, redis))
        logger.info("[sre.run_remediate] job=%s done", job_id)
    except Exception as exc:
        logger.exception("[sre.run_remediate] job=%s failed", job_id)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            raise
    finally:
        r.close()