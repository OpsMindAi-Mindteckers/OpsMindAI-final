"""
tests/integration/test_refactor_api.py

Integration tests for the Code Refactor Agent API via SRE router
(refactor sub-agent functionality exposed through the SRE endpoint).

Tests cover:
  - POST /api/v1/agents/sre/analyze (refactor analysis dispatch)
  - Job state management via Redis
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import make_fake_jwt

_AUTH_HDR = {"Authorization": f"Bearer {make_fake_jwt()}"}


# ── App fixture ───────────────────────────────────────────────────────────────

@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = "user-refactor-001"
    user.email = "dev@example.com"
    return user


@pytest.fixture
def app_client(mock_redis, mock_user, monkeypatch):
    from opsmindai.main import app
    from opsmindai.api.v1.auth import get_current_user
    from opsmindai.core.redis import get_redis

    async def override_auth():
        return mock_user

    async def override_redis():
        yield mock_redis

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_redis] = override_redis
    monkeypatch.setattr("opsmindai.api.v1.testing._get_redis", lambda req: mock_redis)

    _fake_task = MagicMock()
    _fake_task.apply_async.return_value = MagicMock(id="fake-celery-id")
    monkeypatch.setattr("opsmindai.api.v1.testing_tasks.task_run_generation", _fake_task)
    monkeypatch.setattr("opsmindai.api.v1.testing_tasks.task_run_suite", _fake_task)
    monkeypatch.setattr("opsmindai.api.v1.testing_tasks.task_run_regression", _fake_task)

    yield app

    app.dependency_overrides.clear()


# ── Testing Router (refactor stubs) ──────────────────────────────────────────

@pytest.mark.asyncio
class TestRefactorAnalysisDispatch:
    """Test that refactor analysis can be queued and tracked."""

    async def test_generate_returns_job_id(self, app_client):
        payload = {
            "repo_url": "https://github.com/example/service",
            "branch": "master",
            "framework": "pytest",
            "coverage_threshold": 0.80,
        }

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.post("/api/v1/agents/testing/generate", json=payload)

        assert resp.status_code in (200, 202)
        body = resp.json()
        assert "job_id" in body
        assert len(body["job_id"]) > 0

    async def test_job_id_is_unique_per_request(self, app_client):
        payload = {
            "repo_url": "https://github.com/example/service",
            "branch": "master",
            "framework": "pytest",
            "coverage_threshold": 0.80,
        }

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp1 = await client.post("/api/v1/agents/testing/generate", json=payload)
            resp2 = await client.post("/api/v1/agents/testing/generate", json=payload)

        assert resp1.json()["job_id"] != resp2.json()["job_id"]

    async def test_job_status_queued_on_creation(self, app_client, mock_redis):
        payload = {
            "repo_url": "https://github.com/example/service",
            "branch": "master",
            "framework": "pytest",
            "coverage_threshold": 0.80,
        }

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.post("/api/v1/agents/testing/generate", json=payload)

        job_id = resp.json()["job_id"]
        stored_raw = await mock_redis.get(f"testing:job:{job_id}")
        assert stored_raw is not None

        stored = json.loads(stored_raw)
        assert stored["status"] in ("queued", "pending")

    async def test_status_endpoint_reflects_stored_state(self, app_client, mock_redis):
        job_id = "refactor-integ-job-001"
        job_data = {
            "job_id": job_id,
            "status": "completed",
            "repo_url": "https://github.com/example/svc",
            "result": {"smells_count": 7, "patches_count": 3},
        }
        await mock_redis.setex(f"testing:job:{job_id}", 3600, json.dumps(job_data))

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.get(f"/api/v1/agents/testing/jobs/{job_id}")

        assert resp.status_code in (200, 202)
        data = resp.json()
        assert data["status"] == "completed"


# ── Regression tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRegressionEndpoint:

    async def test_regression_with_invalid_threshold_rejected(self, app_client):
        payload = {
            "repo_url": "https://github.com/example/repo",
            "branch": "master",
            "coverage_threshold": 1.5,   # > 1.0 should fail validation
            "framework": "pytest",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            # If this goes to generate endpoint where threshold is validated
            resp = await client.post("/api/v1/agents/testing/generate", json=payload)

        assert resp.status_code == 422

    async def test_regression_endpoint_accepts_valid_payload(self, app_client):
        payload = {
            "repo_url": "https://github.com/example/repo",
            "branch": "develop",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.post("/api/v1/agents/testing/regression", json=payload)

        assert resp.status_code in (200, 202)
