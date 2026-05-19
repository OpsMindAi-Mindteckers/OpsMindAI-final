"""
opsmindai/orchestrator/agent_dispatcher.py

Dispatches AgentTask objects to Celery queues (SRS §10).

Decouples HTTP webhook handlers from Celery internals — callers
build AgentTask via task_router.route_event() then call dispatch().
"""

from __future__ import annotations

import logging
from typing import Optional

from opsmindai.orchestrator.task_router import AgentTask

logger = logging.getLogger(__name__)

# Maps the short task_name used by task_router to the fully-qualified
# Celery task path registered in each tasks/*.py module.
_TASK_MAP: dict[str, str] = {
    "refactor.run_analysis":  "opsmindai.tasks.refactor_tasks.task_run_analysis",
    "refactor.run_suggest":   "opsmindai.tasks.refactor_tasks.task_run_suggest",
    "refactor.run_apply":     "opsmindai.tasks.refactor_tasks.task_run_apply",
    "testing.run_generation": "opsmindai.tasks.testing_tasks.task_run_generation",
    "testing.run_suite":      "opsmindai.tasks.testing_tasks.task_run_suite",
    "testing.run_regression": "opsmindai.tasks.testing_tasks.task_run_regression",
    "sre.run_ingest":         "opsmindai.tasks.sre_tasks.task_run_ingest",
    "sre.run_rca":            "opsmindai.tasks.sre_tasks.task_run_rca",
    "sre.run_remediate":      "opsmindai.tasks.sre_tasks.task_run_remediate",
}


def dispatch(task: AgentTask) -> Optional[str]:
    """
    Send a single AgentTask to the Celery broker.

    Args:
        task: AgentTask produced by task_router.route_event().

    Returns:
        Celery task ID string, or None if dispatch failed.
    """
    from opsmindai.tasks.celery_app import celery_app

    celery_path = _TASK_MAP.get(task.task_name)
    if not celery_path:
        logger.error(
            "agent_dispatcher: no Celery task registered for task_name=%s",
            task.task_name,
        )
        return None

    try:
        result = celery_app.send_task(
            celery_path,
            args=[task.job_id, task.payload],
            task_id=task.job_id,
            queue=task.queue,
            priority=task.priority,
        )
        logger.info(
            "dispatched: task=%s job=%s queue=%s priority=%d celery_id=%s",
            task.task_name, task.job_id, task.queue, task.priority, result.id,
        )
        return result.id
    except Exception as exc:
        logger.exception(
            "dispatch failed: task=%s job=%s: %s",
            task.task_name, task.job_id, exc,
        )
        return None


def dispatch_all(tasks: list[AgentTask]) -> dict[str, Optional[str]]:
    """
    Dispatch a list of AgentTasks and return job_id → celery_task_id mapping.

    Args:
        tasks: List of AgentTask objects from task_router.route_event().

    Returns:
        Dict of {job_id: celery_task_id_or_None}.
    """
    return {t.job_id: dispatch(t) for t in tasks}


def dispatch_from_event(source: str, raw_payload: dict) -> dict[str, Optional[str]]:
    """
    Convenience: normalise a raw webhook payload and dispatch all resulting tasks.

    Args:
        source:      Source identifier ('github', 'prometheus', etc.).
        raw_payload: Raw parsed JSON payload.

    Returns:
        Dict of {job_id: celery_task_id_or_None}.
    """
    from opsmindai.orchestrator.event_handler import normalise
    from opsmindai.orchestrator.task_router import route_event

    event = normalise(source, raw_payload)
    tasks = route_event(event)
    return dispatch_all(tasks)
