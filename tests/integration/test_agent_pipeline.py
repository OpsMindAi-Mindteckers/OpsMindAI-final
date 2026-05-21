"""
tests/integration/test_agent_pipeline.py

Integration tests for the agent orchestration pipeline:
  - GitHub webhook → event normalisation → task routing → Celery dispatch
  - Prometheus alert webhook → SRE task dispatch
  - orchestrator.event_handler.normalise() for all sources
  - orchestrator.task_router.route_event() priority assignment
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from opsmindai.orchestrator.event_handler import (
    EventSource,
    EventType,
    NormalisedEvent,
    normalise,
)
from opsmindai.orchestrator.task_router import route_event


# ── Event normalisation ───────────────────────────────────────────────────────

class TestEventNormalisation:

    def test_github_push_normalised_correctly(self):
        payload = {
            "ref": "refs/heads/master",
            "repository": {"clone_url": "https://github.com/org/repo.git"},
            "commits": [{"modified": ["src/api.py", "src/utils.py"], "added": []}],
        }

        event = normalise("github", payload)
        assert event.event_type == EventType.PUSH
        assert event.source == EventSource.GITHUB
        assert event.branch == "master"
        assert "src/api.py" in event.file_paths

    def test_github_pull_request_normalised(self):
        payload = {
            "action": "opened",
            "pull_request": {
                "number": 42,
                "head": {"ref": "feature/auth"},
                "base": {"ref": "master"},
                "body": "Add auth middleware",
            },
            "repository": {"clone_url": "https://github.com/org/repo.git"},
        }

        event = normalise("github", payload)
        assert event.event_type == EventType.PULL_REQUEST
        assert event.pr_number == 42
        assert event.branch == "feature/auth"

    def test_prometheus_alert_normalised(self):
        payload = {
            "alerts": [
                {
                    "labels": {
                        "alertname": "HighErrorRate",
                        "job": "payment-service",
                        "severity": "critical",
                    },
                    "annotations": {"summary": "5xx rate above 5%"},
                    "status": "firing",
                }
            ]
        }

        event = normalise("prometheus", payload)
        assert event.event_type == EventType.ALERT
        assert event.source == EventSource.PROMETHEUS
        assert event.service == "payment-service"
        assert event.severity == "critical"

    def test_pagerduty_alert_normalised(self):
        payload = {
            "messages": [
                {
                    "event": {
                        "data": {
                            "title": "DB down",
                            "severity": "critical",
                            "service": {"summary": "database-service"},
                            "summary": "Database unreachable",
                        }
                    }
                }
            ]
        }

        event = normalise("pagerduty", payload)
        assert event.event_type == EventType.ALERT
        assert event.source == EventSource.PAGERDUTY

    def test_unknown_source_returns_unknown_event_type(self):
        event = normalise("unknown_source", {})
        assert event.event_type == EventType.UNKNOWN

    def test_different_payloads_produce_different_event_ids(self):
        # _event_id is deterministic; different payloads must differ
        payloads = [
            {"alerts": [{"labels": {"alertname": f"Alert{i}", "job": "svc"}, "annotations": {}}]}
            for i in range(3)
        ]
        ids = {normalise("prometheus", p).event_id for p in payloads}
        assert len(ids) == 3


# ── Task routing ──────────────────────────────────────────────────────────────

class TestTaskRouting:

    def _make_event(self, event_type: EventType, **kwargs) -> NormalisedEvent:
        defaults = {
            "event_id": "evt-001",
            "event_type": event_type,
            "source": EventSource.GITHUB,
            "service": "api-service",
            "severity": "medium",
            "repo_url": "https://github.com/org/repo",
            "branch": "master",
            "pr_number": None,
            "file_paths": [],
            "labels": {},
            "raw": {},
            "timestamp": datetime.now(timezone.utc),
        }
        defaults.update(kwargs)
        return NormalisedEvent(**defaults)

    def test_alert_event_routes_to_sre_queue(self):
        event = self._make_event(EventType.ALERT, source=EventSource.PROMETHEUS)
        tasks = route_event(event)
        assert len(tasks) >= 1
        sre_tasks = [t for t in tasks if "sre" in t.queue.lower() or "ingest" in t.task_name]
        assert len(sre_tasks) >= 1

    def test_alert_task_has_highest_priority(self):
        event = self._make_event(EventType.ALERT)
        tasks = route_event(event)
        assert tasks[0].priority >= 7   # alerts are priority 9

    def test_push_event_routes_to_refactor_queue(self):
        event = self._make_event(EventType.PUSH, file_paths=["src/api.py"])
        tasks = route_event(event)
        assert len(tasks) >= 1
        refactor_tasks = [t for t in tasks if "refactor" in t.queue]
        assert len(refactor_tasks) >= 1

    def test_pr_with_test_files_routes_to_testing(self):
        event = self._make_event(
            EventType.PULL_REQUEST,
            pr_number=12,
            file_paths=["src/api.py", "tests/test_api.py"],
        )
        tasks = route_event(event)
        task_names = [t.task_name for t in tasks]
        # Should include a testing task since test files changed
        assert any("test" in name for name in task_names)

    def test_unknown_event_returns_empty_tasks(self):
        event = self._make_event(EventType.UNKNOWN)
        tasks = route_event(event)
        assert tasks == []

    def test_coverage_drop_routes_to_testing(self):
        event = self._make_event(EventType.COVERAGE_DROP)
        tasks = route_event(event)
        testing_tasks = [t for t in tasks if "testing" in t.queue]
        assert len(testing_tasks) >= 1

    def test_task_has_required_fields(self):
        event = self._make_event(EventType.ALERT, source=EventSource.PROMETHEUS)
        tasks = route_event(event)
        for task in tasks:
            assert task.task_name
            assert task.queue
            assert task.priority >= 0
            assert task.job_id


# ── Agent dispatcher ──────────────────────────────────────────────────────────

class TestAgentDispatcher:

    def test_dispatch_returns_celery_task_id(self, mock_celery_send_task):
        from opsmindai.orchestrator.task_router import AgentTask
        from opsmindai.orchestrator.agent_dispatcher import dispatch

        task = AgentTask(
            task_name="sre.run_ingest",
            queue="sre",
            priority=9,
            job_id="job-001",
            payload={"test": True},
            triggered_by="prometheus",
        )

        result = dispatch(task)
        assert result is not None

    def test_dispatch_unknown_task_returns_none(self):
        from opsmindai.orchestrator.task_router import AgentTask
        from opsmindai.orchestrator.agent_dispatcher import dispatch

        task = AgentTask(
            task_name="unknown.task.name.xyz",
            queue="default",
            priority=1,
            job_id="job-002",
            payload={},
            triggered_by="test",
        )

        result = dispatch(task)
        assert result is None
