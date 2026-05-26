"""
opsmindai/tasks/testing_tasks.py

Celery task definitions for the three-phase Testing Agent pipeline.

Workers:
    celery -A opsmindai.tasks.celery_app worker --loglevel=info -Q testing -n test@%h

Each task wraps the corresponding async agent coroutine via _run_async()
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
        os.environ.get("REDIS_URL", "redis://default:UlZV4uuiRwNdx3uEAJJBTVqJN3e3CG8j@redis-17963.c261.us-east-1-4.ec2.cloud.redislabs.com:17963/0"),
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


def _run_async(coro):
    """
    Run an async coroutine from a sync Celery worker, then drain all pending
    tasks and async generators before closing the loop.

    Replaces bare _run_async() to prevent 'Event loop is closed' errors from
    httpx/anyio connection-pool cleanup that fires after the loop tears down.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            # Cancel and await any tasks httpx/anyio left behind
            pending = asyncio.all_tasks(loop)
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            # Shut down async generators and the default thread executor
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


# ── Phase 1: Generate test stubs ──────────────────────────────────────────────


@celery_app.task(
    name="testing.run_generation",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    queue="testing",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=240,
    time_limit=260,
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
        _run_async(run_generation(job_id, payload, redis))
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
    soft_time_limit=240,
    time_limit=260,
)
def task_run_suite(self, job_id: str, payload: dict) -> None:
    """
    Phase 2 — Execute generated tests, parse coverage, enforce gate.

    Runs fully synchronously — no asyncio event loop, no httpx, no aclose()
    issues. Redis is accessed via the sync client directly.

    Args:
        job_id:  Unique job identifier.
        payload: Dict with job_id (from generation phase), pr_number, user_id.
    """
    import json, shutil, time, os
    from datetime import datetime, timezone
    from opsmindai.agents.testing.coverage_analyzer import run_and_analyze

    logger.info("[testing.run_suite] job=%s starting", job_id)
    r = _sync_redis()
    start = time.monotonic()

    def _redis_get(key):
        return r.get(key)

    def _redis_set(key, value):
        r.set(key, value)

    def _job_key(jid):
        return f"testing:job:{jid}"

    def _update(jid, data):
        raw = r.get(_job_key(jid))
        state = json.loads(raw) if raw else {}
        state.update(data)
        r.set(_job_key(jid), json.dumps(state))

    repo_root = None
    try:
        gen_job_id = payload.get("job_id") or job_id
        raw = r.get(_job_key(gen_job_id))
        if not raw:
            raise ValueError(
                f"Generation job {gen_job_id!r} not found in Redis. "
                "Please re-run Phase 1."
            )

        state     = json.loads(raw)
        repo_root = state.get("repo_root")
        repo_url  = state.get("repo_url", payload.get("repo_url", ""))
        branch    = state.get("branch", payload.get("branch", "main"))
        framework = state.get("framework", payload.get("framework", "pytest"))
        threshold = float(state.get("threshold", payload.get("coverage_threshold", 0.80)))
        pr_number = payload.get("pr_number")

        _update(job_id, {"status": "running", "phase": "suite_execution"})

        # Re-clone if temp dir is gone
        if not repo_root or not os.path.isdir(repo_root):
            logger.warning(
                "repo_root %r gone — re-cloning %s@%s",
                repo_root, repo_url, branch,
            )
            if not repo_url:
                raise ValueError("repo_root missing and repo_url not stored. Re-run Phase 1.")
            token = os.environ.get("GITHUB_TOKEN", "")
            try:
                from opsmindai.core.config import settings
                token = getattr(settings, "GITHUB_TOKEN", None) or token
            except Exception:
                pass
            from opsmindai.agents.testing.agent import _clone_repo
            repo_root = _clone_repo(repo_url, branch, token or "")
            _update(gen_job_id, {"repo_root": repo_root})

        # Copy generated test files into clone
        generated_files = state.get("generated_files", [])
        persistent_dir  = state.get("persistent_dir", "")
        if generated_files:
            tests_dest = os.path.join(repo_root, "tests", "unit")
            os.makedirs(tests_dest, exist_ok=True)
            copied = 0
            for gf in generated_files:
                fname = os.path.basename(gf.get("output_file", ""))
                if not fname:
                    continue
                src_path = None
                if persistent_dir and os.path.exists(os.path.join(persistent_dir, fname)):
                    src_path = os.path.join(persistent_dir, fname)
                elif gf.get("output_file") and os.path.exists(gf["output_file"]):
                    src_path = gf["output_file"]
                if src_path:
                    dest = os.path.join(tests_dest, fname)
                    if os.path.abspath(src_path) != os.path.abspath(dest):
                        shutil.copy2(src_path, dest)
                    copied += 1
                    logger.info("Copied generated test %s → %s", src_path, dest)
            logger.info("Copied %d generated test file(s) into %s", copied, tests_dest)

        # Run tests synchronously via _run_async helper
        coverage = _run_async(run_and_analyze(
            job_id=job_id,
            repo_path=repo_root,
            repo_url=repo_url,
            branch=branch,
            framework=framework,
            threshold=threshold,
            pr_number=pr_number,
            redis=_AsyncRedisAdapter(r),
        ))

        duration = time.monotonic() - start
        logger.info(
            "Suite complete job=%s coverage=%.1f%% delta=%.1f%% gate=%s duration=%.2fs",
            job_id, coverage.coverage_pct, coverage.delta_pct,
            coverage.gate_passed, duration,
        )

        _update(job_id, {
            "status": "completed",
            "coverage": {
                "coverage_pct":   coverage.coverage_pct,
                "delta_pct":      coverage.delta_pct,
                "lines_covered":  coverage.lines_covered,
                "lines_total":    coverage.lines_total,
                "file_breakdown": coverage.file_breakdown,
                "gate_passed":    coverage.gate_passed,
                "threshold":      coverage.threshold,
                "previous_pct":   coverage.previous_pct,
            },
            "gate_passed":  coverage.gate_passed,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(duration, 2),
        })

        logger.info("[testing.run_suite] job=%s completed", job_id)

    except Exception as exc:
        logger.exception("[testing.run_suite] job=%s failed", job_id)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[testing.run_suite] job=%s max retries exceeded", job_id)
            raise
    finally:
        if repo_root and os.path.isdir(repo_root):
            shutil.rmtree(repo_root, ignore_errors=True)
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
    soft_time_limit=240,
    time_limit=260,
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
        _run_async(run_regression(job_id, payload, redis))
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