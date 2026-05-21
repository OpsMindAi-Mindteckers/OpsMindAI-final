"""
opsmindai/orchestrator/task_router.py

Routes NormalisedEvents to the correct Celery agent tasks with priorities.

Priority rules (SRS §10.1):
  alert=9, coverage_drop=7, pull_request=5, push=3

Event → agent mapping:
  push / pull_request  → refactor agent (+ test agent when PR has test files)
  alert                → SRE-GPT agent
  coverage_drop        → test generation agent
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from opsmindai.orchestrator.event_handler import EventType, NormalisedEvent

logger = logging.getLogger(__name__)

_TEST_FILE_PATTERNS = (
    "test_", "_test.py",
    ".test.js", ".test.ts",
    ".spec.js", ".spec.ts",
)


@dataclass
class AgentTask:
    """Represents a single Celery task ready for dispatch."""
    task_name:    str
    queue:        str
    priority:     int
    job_id:       str
    payload:      dict
    triggered_by: Optional[str] = None


def _new_job(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _has_test_files(file_paths: list[str]) -> bool:
    return any(
        any(pat in fp for pat in _TEST_FILE_PATTERNS)
        for fp in file_paths
    )


def route_event(event: NormalisedEvent) -> list[AgentTask]:
    """
    Classify a NormalisedEvent and return AgentTasks to dispatch.

    Args:
        event: Normalised inbound event from event_handler.normalise().

    Returns:
        List of AgentTask objects (may be empty for UNKNOWN events).
    """
    tasks: list[AgentTask] = []

    if event.event_type in (EventType.PUSH, EventType.PULL_REQUEST):
        tasks.extend(_route_code_event(event))

    elif event.event_type == EventType.ALERT:
        tasks.append(_route_alert_event(event))

    elif event.event_type == EventType.COVERAGE_DROP:
        tasks.append(_route_coverage_drop(event))

    else:
        logger.info(
            "task_router: no handler for event_type=%s event_id=%s",
            event.event_type, event.event_id,
        )

    for t in tasks:
        logger.info(
            "task_router: task=%s queue=%s priority=%d job=%s triggered_by=%s",
            t.task_name, t.queue, t.priority, t.job_id, t.triggered_by,
        )

    return tasks


# ── Private routers ────────────────────────────────────────────────────────────

def _route_code_event(event: NormalisedEvent) -> list[AgentTask]:
    """Push/PR → refactor analysis; add test suite task when PR contains test files."""
    priority = 5 if event.event_type == EventType.PULL_REQUEST else 3
    job_id   = _new_job("refactor")

    tasks: list[AgentTask] = [
        AgentTask(
            task_name    = "refactor.run_analysis",
            queue        = "refactor",
            priority     = priority,
            job_id       = job_id,
            triggered_by = event.event_id,
            payload      = {
                "repo_url":   event.repo_url  or "",
                "branch":     event.branch    or "main",
                "file_paths": event.file_paths,
                "pr_number":  event.pr_number,
                "user_id":    "webhook",
            },
        )
    ]

    if (event.event_type == EventType.PULL_REQUEST
            and _has_test_files(event.file_paths)):
        tasks.append(AgentTask(
            task_name    = "testing.run_suite",
            queue        = "testing",
            priority     = priority,
            job_id       = _new_job("testsuite"),
            triggered_by = event.event_id,
            payload      = {
                "job_id":    job_id,
                "pr_number": event.pr_number,
                "user_id":   "webhook",
            },
        ))

    return tasks


def _route_alert_event(event: NormalisedEvent) -> AgentTask:
    """Alert → SRE-GPT ingest at highest priority (9)."""
    return AgentTask(
        task_name    = "sre.run_ingest",
        queue        = "sre",
        priority     = 9,
        job_id       = _new_job("sre_ingest"),
        triggered_by = event.event_id,
        payload      = {
            "source":      event.source.value,
            "service":     event.service  or "unknown",
            "severity":    event.severity or "medium",
            "alert_name":  event.labels.get("alert_name", "UnknownAlert"),
            "labels":      event.labels,
            "annotations": {},
            "raw_payload": event.raw,
            "user_id":     "webhook",
        },
    )


def _route_coverage_drop(event: NormalisedEvent) -> AgentTask:
    """Coverage drop → test generation for affected module (priority 7)."""
    return AgentTask(
        task_name    = "testing.run_generation",
        queue        = "testing",
        priority     = 7,
        job_id       = _new_job("testgen"),
        triggered_by = event.event_id,
        payload      = {
            "repo_url":           event.repo_url or "",
            "branch":             event.branch   or "main",
            "file_path":          event.file_paths[0] if event.file_paths else None,
            "framework":          "pytest",
            "coverage_threshold": 0.80,
            "user_id":            "webhook",
        },
    )
