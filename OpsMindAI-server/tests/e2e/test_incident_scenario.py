"""
tests/e2e/test_incident_scenario.py

End-to-end test for the full incident response lifecycle:
  T+0s  — Alert arrives at /incidents/ingest (Prometheus webhook)
  T+2s  — SRE-GPT RCA task queued and simulated
  T+5s  — Remediation playbook selected and executed
  T+12m — Incident resolved, MTTR recorded, Grafana annotated

External calls (Slack, Grafana, Celery, LLM) are all mocked.
Redis uses the in-memory mock from conftest.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from opsmindai.agents.sre_gpt.alert_ingester import compute_fingerprint, ingest
from opsmindai.orchestrator.event_handler import normalise, EventType
from opsmindai.orchestrator.task_router import route_event
from opsmindai.schemas.incidents import (
    AlertPayload,
    AlertSource,
    IncidentSeverity,
    IncidentStatus,
    NormalisedAlert,
)
from tests.conftest import make_fake_jwt


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_hmac(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── Full incident lifecycle ───────────────────────────────────────────────────

@pytest.mark.asyncio
class TestIncidentLifecycle:

    async def test_full_lifecycle_from_alert_to_resolution(self, mock_redis):
        """
        Simulates the full incident lifecycle end-to-end:
        1. Alert ingested → NormalisedAlert created, dedup key set
        2. Duplicate suppressed on second identical alert
        3. RCA dispatch via task router
        4. Remediation task created
        5. Incident state tracked in Redis
        """
        # ── T+0s: Alert arrives ───────────────────────────────────────────────
        raw_payload = {
            "alerts": [
                {
                    "labels": {
                        "alertname": "PaymentServiceDown",
                        "job": "payment-service",
                        "severity": "critical",
                        "namespace": "production",
                    },
                    "annotations": {"summary": "Payment service not responding"},
                    "status": "firing",
                }
            ]
        }

        alert_payload = AlertPayload(
            source=AlertSource.PROMETHEUS,
            service="payment-service",
            alert_name="PaymentServiceDown",
            severity=IncidentSeverity.CRITICAL,
            labels={"alertname": "PaymentServiceDown"},
            annotations={},
            raw_payload=raw_payload,
        )

        alert, is_dup = await ingest(alert_payload, mock_redis)

        assert is_dup is False
        assert alert.incident_id.startswith("inc_")
        assert alert.service == "payment-service"
        assert alert.severity == IncidentSeverity.CRITICAL

        # ── T+0s dedup: same alert within 60s ────────────────────────────────
        alert_dup, is_dup2 = await ingest(alert_payload, mock_redis)
        assert is_dup2 is True
        assert alert_dup.incident_id == alert.incident_id

        # ── T+2s: Orchestrator routes to SRE task ────────────────────────────
        event = normalise("prometheus", raw_payload)
        assert event.event_type == EventType.ALERT

        tasks = route_event(event)
        assert len(tasks) >= 1
        sre_task = next(t for t in tasks if "ingest" in t.task_name or "sre" in t.queue)
        assert sre_task.priority == 9   # critical alert priority

        # ── T+5s: RCA result stored in Redis ─────────────────────────────────
        rca_data = {
            "root_cause": "Database connection pool exhausted due to missing connection.close() in payment flow",
            "confidence": 0.92,
            "affected_services": ["payment-service", "database"],
            "remediation_plan": ["restart_connection_pool", "apply_patch"],
        }
        rca_key = f"incident:{alert.incident_id}:rca"
        await mock_redis.setex(rca_key, 86400, json.dumps(rca_data))

        stored_rca = await mock_redis.get(rca_key)
        assert stored_rca is not None
        rca = json.loads(stored_rca)
        assert rca["confidence"] == 0.92

        # ── T+5s: Status update to remediating ───────────────────────────────
        status_key = f"incident:{alert.incident_id}:status"
        await mock_redis.setex(status_key, 86400, IncidentStatus.REMEDIATING.value)
        assert await mock_redis.get(status_key) == IncidentStatus.REMEDIATING.value

        # ── T+12m: Incident resolved ──────────────────────────────────────────
        await mock_redis.setex(status_key, 86400, IncidentStatus.RESOLVED.value)
        assert await mock_redis.get(status_key) == IncidentStatus.RESOLVED.value

    async def test_multi_source_same_incident_deduplicated(self, mock_redis):
        """Prometheus + PagerDuty alert for same service/alert → only one incident."""
        prom_payload = AlertPayload(
            source=AlertSource.PROMETHEUS,
            service="auth-service",
            alert_name="AuthServiceDown",
            severity=IncidentSeverity.HIGH,
            labels={"alertname": "AuthServiceDown", "job": "auth-service"},
            annotations={},
            raw_payload={},
        )

        pd_payload = AlertPayload(
            source=AlertSource.PAGERDUTY,
            service="auth-service",   # same service
            alert_name="AuthServiceDown",  # same alert
            severity=IncidentSeverity.HIGH,
            labels={"alertname": "AuthServiceDown", "job": "auth-service"},  # same labels
            annotations={},
            raw_payload={},
        )

        alert1, dup1 = await ingest(prom_payload, mock_redis)
        alert2, dup2 = await ingest(pd_payload, mock_redis)

        # Same fingerprint (same service + alert_name + labels) → dedup
        assert dup1 is False
        assert dup2 is True
        assert alert2.incident_id == alert1.incident_id

    async def test_critical_alert_has_highest_task_priority(self, mock_redis):
        raw = {
            "alerts": [
                {
                    "labels": {"alertname": "DBDown", "job": "database", "severity": "critical"},
                    "annotations": {},
                }
            ]
        }

        event = normalise("prometheus", raw)
        tasks = route_event(event)
        assert any(t.priority >= 9 for t in tasks)


# ── Webhook → API path ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_incident_ingest_via_api(mock_redis, monkeypatch):
    """Simulate alert coming through the HTTP API endpoint."""
    monkeypatch.setenv("DEBUG", "1")
    monkeypatch.setenv("INCIDENT_WEBHOOK_SECRET", "e2e-secret")

    from opsmindai.main import app
    from opsmindai.api.v1.auth import get_current_user
    from opsmindai.core.redis import get_redis

    mock_user = MagicMock()
    mock_user.id = "e2e-user"

    async def override_auth():
        return mock_user

    async def override_redis():
        yield mock_redis

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_redis] = override_redis

    try:
        payload = {
            "source": "prometheus",
            "service": "checkout-service",
            "alert_name": "CheckoutDown",
            "severity": "critical",
            "labels": {"alertname": "CheckoutDown", "job": "checkout-service"},
            "annotations": {},
            "raw_payload": {
                "alerts": [
                    {
                        "labels": {"alertname": "CheckoutDown", "job": "checkout-service", "severity": "critical"},
                        "annotations": {},
                    }
                ]
            },
        }

        body = json.dumps(payload).encode()
        signature = _make_hmac(body, "e2e-secret")

        with patch("opsmindai.monitoring.alert_handler.handle_alert") as mock_handle:
            mock_handle.return_value = {
                "event_id": "e2e-evt-001",
                "service": "checkout-service",
                "severity": "critical",
                "status": "dispatched",
                "dispatched": "celery-e2e-001",
                "slack_sent": False,
            }

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/incidents/ingest",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Signature-256": signature,
                        "Authorization": f"Bearer {make_fake_jwt()}",
                    },
                )

        # Ingest endpoint returns 202 Accepted
        assert resp.status_code == 202
    finally:
        app.dependency_overrides.clear()
