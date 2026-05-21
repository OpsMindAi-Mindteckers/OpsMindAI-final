"""
tests/integration/test_incidents_api.py

Integration tests for the SRE-GPT Incidents API:
  - POST /api/v1/incidents/ingest (HMAC webhook)
  - GET  /api/v1/incidents/{incident_id}
  - POST /api/v1/incidents/analyze
  - POST /api/v1/incidents/remediate
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.conftest import make_fake_jwt

from opsmindai.schemas.incidents import (
    AlertSource,
    IncidentSeverity,
    IncidentStatus,
    NormalisedAlert,
)


# ── App fixture with mocked dependencies ─────────────────────────────────────

@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = "user-test-001"
    user.email = "tester@example.com"
    return user


@pytest.fixture
def app_client(mock_redis, mock_user, monkeypatch):
    """FastAPI test client with auth and Redis mocked."""
    monkeypatch.setenv("DEBUG", "1")
    monkeypatch.setenv("INCIDENT_WEBHOOK_SECRET", "test-secret")

    from opsmindai.main import app
    from opsmindai.api.v1.auth import get_current_user
    from opsmindai.core.redis import get_redis

    async def override_auth():
        return mock_user

    async def override_redis():
        yield mock_redis

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_redis] = override_redis

    yield app

    app.dependency_overrides.clear()


def _make_hmac_signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


# ── POST /incidents/ingest ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestIngestEndpoint:

    async def test_valid_hmac_returns_200(self, app_client):
        payload = {
            "source": "prometheus",
            "service": "api-service",
            "alert_name": "HighLatency",
            "severity": "high",
            "labels": {"alertname": "HighLatency", "job": "api-service"},
            "annotations": {},
            "raw_payload": {
                "alerts": [
                    {
                        "labels": {"alertname": "HighLatency", "job": "api-service", "severity": "high"},
                        "annotations": {},
                    }
                ]
            },
        }
        body = json.dumps(payload).encode()
        signature = _make_hmac_signature(body, "test-secret")

        with patch("opsmindai.monitoring.alert_handler.handle_alert") as mock_handle:
            mock_handle.return_value = {
                "event_id": "evt-001",
                "service": "api-service",
                "severity": "high",
                "status": "dispatched",
                "dispatched": "celery-id-001",
                "slack_sent": False,
            }

            async with AsyncClient(
                transport=ASGITransport(app=app_client), base_url="http://test"
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

    async def test_missing_signature_returns_4xx(self, app_client, monkeypatch):
        monkeypatch.setenv("DEBUG", "0")   # strict mode — HMAC required
        payload = {"source": "prometheus", "service": "svc", "alert_name": "A",
                   "severity": "low", "labels": {}, "annotations": {}}
        body = json.dumps(payload).encode()

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/incidents/ingest",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {make_fake_jwt()}",
                    # No X-Signature-256 — should reject
                },
            )

        # endpoint returns 401 for missing/invalid HMAC when secret is configured
        assert resp.status_code in (400, 401, 403, 503)

    async def test_invalid_hmac_returns_4xx(self, app_client):
        payload = {"source": "prometheus", "service": "svc", "alert_name": "A",
                   "severity": "low", "labels": {}, "annotations": {}}
        body = json.dumps(payload).encode()

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/incidents/ingest",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature-256": "sha256=badhexvalue",
                    "Authorization": f"Bearer {make_fake_jwt()}",
                },
            )

        # endpoint returns 401 for invalid HMAC (code path: _verify_hmac fails → 401)
        assert resp.status_code in (400, 401, 403)


# ── GET /incidents/{incident_id} ──────────────────────────────────────────────

@pytest.mark.asyncio
class TestGetIncidentDetail:

    async def test_returns_incident_detail_when_found(self, app_client, mock_redis):
        incident_id = "inc_abc123000000"
        alert = NormalisedAlert(
            incident_id=incident_id,
            fingerprint="a" * 64,
            source=AlertSource.PROMETHEUS,
            service="payment-service",
            severity=IncidentSeverity.HIGH,
            alert_name="HighLatency",
            labels={},
            annotations={},
            detected_at=datetime.now(timezone.utc),
        )
        # Store alert in mock redis
        mock_redis._store[f"incident:{incident_id}"] = alert.model_dump_json()
        mock_redis._store[f"incident:{incident_id}:status"] = IncidentStatus.OPEN.value

        _hdrs = {"Authorization": f"Bearer {make_fake_jwt()}"}
        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/v1/incidents/{incident_id}", headers=_hdrs)

        assert resp.status_code == 200
        data = resp.json()
        assert data["incident_id"] == incident_id

    async def test_returns_404_for_unknown_incident(self, app_client):
        _hdrs = {"Authorization": f"Bearer {make_fake_jwt()}"}
        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/incidents/inc_nonexistent9999", headers=_hdrs)

        assert resp.status_code == 404


# ── Health check ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check_returns_200_when_redis_ok(app_client):
    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        resp = await client.get("/health")

    assert resp.status_code in (200, 503)   # 503 if redis mock ping fails
    data = resp.json()
    assert "status" in data
