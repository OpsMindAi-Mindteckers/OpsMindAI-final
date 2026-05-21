"""
tests/conftest.py

Shared pytest fixtures for unit, integration, and e2e test suites.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from opsmindai.schemas.incidents import (
    AlertPayload,
    AlertSource,
    IncidentSeverity,
    NormalisedAlert,
)
from opsmindai.schemas.refactor import SmellItem, SmellSeverity, SmellType


# ── Redis mock ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    """Async Redis mock with an in-memory store."""
    store: dict[str, Any] = {}

    redis = AsyncMock()

    async def _get(key):
        return store.get(key)

    async def _setex(key, ttl, value):
        store[key] = value

    async def _set(key, value):
        store[key] = value

    async def _delete(key):
        store.pop(key, None)

    async def _exists(key):
        return int(key in store)

    async def _ping():
        return True

    redis.get.side_effect = _get
    redis.setex.side_effect = _setex
    redis.set.side_effect = _set
    redis.delete.side_effect = _delete
    redis.exists.side_effect = _exists
    redis.ping.side_effect = _ping
    redis._store = store   # allow tests to inspect raw store

    return redis


# ── Celery mock ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_celery_send_task(monkeypatch):
    """Prevent Celery from actually queuing tasks in every test."""
    fake_result = MagicMock()
    fake_result.id = "test-celery-id-0000"

    mock_app = MagicMock()
    mock_app.send_task.return_value = fake_result

    # Patch the Celery app that agent_dispatcher lazily imports
    monkeypatch.setattr(
        "opsmindai.tasks.celery_app.celery_app",
        mock_app,
        raising=False,
    )
    return mock_app


# ── Sample data fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_alert_payload() -> AlertPayload:
    return AlertPayload(
        source=AlertSource.PROMETHEUS,
        service="payment-service",
        alert_name="HighErrorRate",
        severity=IncidentSeverity.CRITICAL,
        labels={"alertname": "HighErrorRate", "job": "payment-service", "severity": "critical"},
        annotations={"summary": "Error rate above threshold"},
        raw_payload={
            "alerts": [
                {
                    "labels": {
                        "alertname": "HighErrorRate",
                        "job": "payment-service",
                        "severity": "critical",
                    },
                    "annotations": {"summary": "Error rate above threshold"},
                    "status": "firing",
                }
            ]
        },
    )


@pytest.fixture
def sample_normalised_alert() -> NormalisedAlert:
    return NormalisedAlert(
        incident_id="inc_abc123def456",
        fingerprint="a" * 64,
        source=AlertSource.PROMETHEUS,
        service="payment-service",
        severity=IncidentSeverity.CRITICAL,
        alert_name="HighErrorRate",
        labels={"alertname": "HighErrorRate", "severity": "critical"},
        annotations={},
        detected_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_smell_item() -> SmellItem:
    return SmellItem(
        file="src/processor.py",
        line=42,
        smell_type=SmellType.HIGH_COMPLEXITY,
        severity=SmellSeverity.HIGH,
        message="Function 'process_data' has cyclomatic complexity 15 (threshold: 10)",
        score=0.75,
    )


@pytest.fixture
def sample_smell_list() -> list[SmellItem]:
    return [
        SmellItem(
            file="src/a.py",
            line=10,
            smell_type=SmellType.HIGH_COMPLEXITY,
            severity=SmellSeverity.CRITICAL,
            message="Cyclomatic complexity 35",
            score=1.0,
        ),
        SmellItem(
            file="src/a.py",
            line=50,
            smell_type=SmellType.LONG_METHOD,
            severity=SmellSeverity.HIGH,
            message="Function is 110 lines",
            score=0.7,
        ),
        SmellItem(
            file="src/b.py",
            line=1,
            smell_type=SmellType.POOR_NAMING,
            severity=SmellSeverity.LOW,
            message="Identifier 'x' too short",
            score=0.3,
        ),
    ]


# ── FastAPI test client ───────────────────────────────────────────────────────

@pytest.fixture
def app_with_mocked_state():
    """Return app with redis pool and limiter mocked on state."""
    from opsmindai.main import app

    mock_pool = MagicMock()
    app.state.redis_pool = mock_pool
    return app


def make_fake_jwt(user_id: str = "test-user-001") -> str:
    """Create a minimal unsigned JWT that the AuthMiddleware can decode."""
    header  = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": user_id, "exp": 9999999999}).encode()
    ).decode().rstrip("=")
    return f"{header}.{payload}.fakesig"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Fake Bearer JWT header that passes the AuthMiddleware decode check."""
    return {"Authorization": f"Bearer {make_fake_jwt()}"}
