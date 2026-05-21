"""
opsmindai/agents/base.py

BaseAgent — abstract base class shared by all three OpsMind agents.

Provides:
  - Shared lifecycle hooks: on_start, on_complete, on_error
  - Structured JSON logging (every lifecycle event)
  - RAG context injection helper
  - Redis job-state helpers
  - Abstract run() method that subclasses must implement
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all OpsMind AI agents.

    Subclasses (RefactorAgent, TestingAgent, SREGPTAgent) must implement
    the ``run`` method.  All other lifecycle methods have default
    implementations that can be overridden.

    Args:
        agent_name: Human-readable name logged with every event.
        redis:      Async Redis client injected at construction time.
    """

    def __init__(self, agent_name: str, redis: Any) -> None:
        self.agent_name = agent_name
        self.redis      = redis
        self._job_id: Optional[str] = None
        self._start_time: float = 0.0

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    async def run(self, job_id: str, payload: dict) -> dict:
        """
        Execute the agent's main pipeline.

        Args:
            job_id:  Unique job identifier (pre-created by the API layer).
            payload: Request payload dict (validated Pydantic model dumped to dict).

        Returns:
            Result dict that will be merged into the Redis job state.

        Raises:
            Any exception — BaseAgent.execute() will catch, call on_error,
            and re-raise.
        """
        ...

    # ── Lifecycle hooks ───────────────────────────────────────────────────────

    async def on_start(self, job_id: str, payload: dict) -> None:
        """
        Called immediately before ``run``.  Updates job status to 'running'
        and emits a structured log line.

        Override to add custom pre-run setup (e.g. metric counters).

        Args:
            job_id:  Unique job identifier.
            payload: Request payload dict.
        """
        self._job_id    = job_id
        self._start_time = time.monotonic()

        await self._update_job(job_id, {
            "status":     "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        })

        logger.info(
            json.dumps({
                "event":      "agent_start",
                "agent":      self.agent_name,
                "job_id":     job_id,
                "repo_url":   payload.get("repo_url", ""),
                "timestamp":  datetime.now(timezone.utc).isoformat(),
            })
        )

    async def on_complete(self, job_id: str, result: dict) -> None:
        """
        Called after ``run`` returns successfully.  Updates job status to
        'completed' and emits a structured log line.

        Override to add post-run actions (e.g. Slack notification, metric flush).

        Args:
            job_id:  Unique job identifier.
            result:  Return value from ``run``.
        """
        duration = time.monotonic() - self._start_time

        await self._update_job(job_id, {
            "status":       "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(duration, 2),
            **result,
        })

        logger.info(
            json.dumps({
                "event":      "agent_complete",
                "agent":      self.agent_name,
                "job_id":     job_id,
                "duration_s": round(duration, 2),
                "timestamp":  datetime.now(timezone.utc).isoformat(),
            })
        )

    async def on_error(self, job_id: str, exc: Exception) -> None:
        """
        Called when ``run`` raises an exception.  Updates job status to
        'failed' and emits a structured error log line.

        Override to add custom error handling (e.g. PagerDuty escalation).

        Args:
            job_id: Unique job identifier.
            exc:    The exception that was raised.
        """
        duration = time.monotonic() - self._start_time

        await self._update_job(job_id, {
            "status":       "failed",
            "error":        str(exc),
            "error_type":   type(exc).__name__,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(duration, 2),
        })

        logger.error(
            json.dumps({
                "event":      "agent_error",
                "agent":      self.agent_name,
                "job_id":     job_id,
                "error":      str(exc),
                "error_type": type(exc).__name__,
                "duration_s": round(duration, 2),
                "timestamp":  datetime.now(timezone.utc).isoformat(),
            })
        )

    # ── Orchestration ─────────────────────────────────────────────────────────

    async def execute(self, job_id: str, payload: dict) -> dict:
        """
        Top-level orchestration method called by Celery tasks.

        Calls: on_start → run → on_complete (or on_error on exception).

        Args:
            job_id:  Unique job identifier.
            payload: Request payload dict.

        Returns:
            Result dict from ``run``.

        Raises:
            Re-raises any exception from ``run`` after calling on_error.
        """
        await self.on_start(job_id, payload)
        try:
            result = await self.run(job_id, payload)
            await self.on_complete(job_id, result)
            return result
        except Exception as exc:
            await self.on_error(job_id, exc)
            raise

    # ── RAG injection helper ──────────────────────────────────────────────────

    async def inject_rag_context(
        self,
        query: str,
        top_k: int = 5,
        filter_type: Optional[str] = None,
    ) -> list[str]:
        """
        Retrieve relevant context from the RAG knowledge base and return
        as a list of content strings ready to prepend to an LLM prompt.

        Args:
            query:       Natural-language query to embed and search.
            top_k:       Maximum number of results to return.
            filter_type: Optional type filter ('incident', 'pattern', 'test_result').

        Returns:
            List of content strings (empty list on failure).
        """
        try:
            from opsmindai.memory.rag_pipeline import RAGPipeline
            rag = RAGPipeline()
            results = await rag.retrieve(
                query=query,
                top_k=top_k,
                filter_type=filter_type,
            )
            return [r.content for r in results]
        except Exception as exc:
            logger.warning(
                "RAG context retrieval failed (non-fatal) agent=%s: %s",
                self.agent_name, exc,
            )
            return []

    # ── Redis helpers ─────────────────────────────────────────────────────────

    def _redis_key(self, job_id: str) -> str:
        """Compute the Redis key for a job.

        Override in subclasses to use agent-specific namespacing.

        Args:
            job_id: Unique job identifier.

        Returns:
            Redis key string.
        """
        return f"{self.agent_name}:job:{job_id}"

    async def _update_job(self, job_id: str, updates: dict) -> None:
        """
        Merge `updates` into the existing job state document in Redis.

        Creates the key if it does not exist (gracefully handles first write).

        Args:
            job_id:  Unique job identifier.
            updates: Dictionary of fields to merge.
        """
        key = self._redis_key(job_id)
        try:
            raw = await self.redis.get(key)
            state: dict = json.loads(raw) if raw else {}
            state.update(updates)
            await self.redis.setex(key, 86400, json.dumps(state, default=str))
        except Exception as exc:
            logger.warning(
                "Redis update failed for job %s: %s (updates will be lost)",
                job_id, exc,
            )

    async def _load_job(self, job_id: str) -> Optional[dict]:
        """
        Load the full job state document from Redis.

        Args:
            job_id: Unique job identifier.

        Returns:
            Parsed job state dict, or None if not found.
        """
        key = self._redis_key(job_id)
        try:
            raw = await self.redis.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("Redis load failed for job %s: %s", job_id, exc)
            return None

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def new_job_id() -> str:
        """
        Generate a new unique job ID.

        Returns:
            UUID4 hex string prefixed with 'job_'.
        """
        return f"job_{uuid.uuid4().hex[:12]}"