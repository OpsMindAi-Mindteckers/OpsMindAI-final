"""
tests/integration/test_testing_api.py

Integration tests for the Testing Agent API:
  - POST /api/v1/agents/testing/generate
  - POST /api/v1/agents/testing/suite
  - POST /api/v1/agents/testing/regression
  - GET  /api/v1/agents/testing/jobs/{job_id}
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
    user.id = "user-test-001"
    user.email = "tester@example.com"
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

    # testing.py uses its own _get_redis(request) that bypasses Depends(get_redis)
    monkeypatch.setattr("opsmindai.api.v1.testing._get_redis", lambda req: mock_redis)

    # Prevent actual Celery broker connections from testing.py's direct apply_async calls
    _fake_task = MagicMock()
    _fake_task.apply_async.return_value = MagicMock(id="fake-celery-id")
    monkeypatch.setattr("opsmindai.api.v1.testing_tasks.task_run_generation", _fake_task)
    monkeypatch.setattr("opsmindai.api.v1.testing_tasks.task_run_suite", _fake_task)
    monkeypatch.setattr("opsmindai.api.v1.testing_tasks.task_run_regression", _fake_task)

    yield app

    app.dependency_overrides.clear()


# ── POST /agents/testing/generate ────────────────────────────────────────────

@pytest.mark.asyncio
class TestGenerateEndpoint:

    async def test_returns_job_id_on_valid_request(self, app_client):
        payload = {
            "repo_url": "https://github.com/example/myrepo",
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
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "queued"

    async def test_returns_422_for_missing_repo_url(self, app_client):
        payload = {"branch": "master", "framework": "pytest"}

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.post("/api/v1/agents/testing/generate", json=payload)

        assert resp.status_code == 422

    async def test_job_stored_in_redis(self, app_client, mock_redis):
        payload = {
            "repo_url": "https://github.com/example/repo",
            "branch": "feature-branch",
            "framework": "pytest",
            "coverage_threshold": 0.75,
        }

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.post("/api/v1/agents/testing/generate", json=payload)

        assert resp.status_code in (200, 202)
        job_id = resp.json()["job_id"]

        job_key = f"testing:job:{job_id}"
        stored = await mock_redis.get(job_key)
        assert stored is not None
        job_data = json.loads(stored)
        assert job_data["status"] == "queued"


# ── POST /agents/testing/suite ────────────────────────────────────────────────

@pytest.mark.asyncio
class TestSuiteEndpoint:

    async def test_returns_422_without_generation_job_id(self, app_client):
        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.post("/api/v1/agents/testing/suite", json={})

        assert resp.status_code == 422

    async def test_returns_404_when_parent_job_not_found(self, app_client):
        payload = {"generation_job_id": "nonexistent-job-id-xyz"}

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.post("/api/v1/agents/testing/suite", json=payload)

        assert resp.status_code in (404, 422)

    async def test_queues_suite_when_parent_job_exists(self, app_client, mock_redis):
        gen_job_id = "gen-job-12345"
        gen_job_data = {
            "job_id": gen_job_id,
            "status": "completed",
            "repo_url": "https://github.com/example/repo",
            "repo_path": "/tmp/repo",
            "branch": "master",
        }
        await mock_redis.setex(f"testing:job:{gen_job_id}", 3600, json.dumps(gen_job_data))

        payload = {"generation_job_id": gen_job_id}

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.post("/api/v1/agents/testing/suite", json=payload)

        assert resp.status_code in (200, 202)
        data = resp.json()
        assert "job_id" in data


# ── POST /agents/testing/regression ──────────────────────────────────────────

@pytest.mark.asyncio
class TestRegressionEndpoint:

    async def test_returns_job_id_on_valid_request(self, app_client):
        payload = {
            "repo_url": "https://github.com/example/repo",
            "branch": "master",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.post("/api/v1/agents/testing/regression", json=payload)

        assert resp.status_code in (200, 202)
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "queued"


# ── GET /agents/testing/jobs/{job_id} ─────────────────────────────────────────

@pytest.mark.asyncio
class TestJobStatusEndpoint:

    async def test_returns_job_status_when_found(self, app_client, mock_redis):
        job_id = "test-job-status-001"
        job_data = {
            "job_id": job_id,
            "status": "running",
            "repo_url": "https://github.com/example/repo",
        }
        await mock_redis.setex(f"testing:job:{job_id}", 3600, json.dumps(job_data))

        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.get(f"/api/v1/agents/testing/jobs/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "running"

    async def test_returns_404_for_unknown_job(self, app_client):
        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test",
            headers=_AUTH_HDR,
        ) as client:
            resp = await client.get("/api/v1/agents/testing/jobs/no-such-job-xyz")

        assert resp.status_code == 404
