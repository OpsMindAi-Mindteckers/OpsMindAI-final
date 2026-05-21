"""
opsmindai/api/v1/testing.py

REST endpoints for the Testing Agent.

Routes:
    POST   /agents/testing/generate          → Phase 1: generate test stubs
    POST   /agents/testing/suite             → Phase 2: run tests + coverage gate
    POST   /agents/testing/regression        → Phase 3: build regression suite
    GET    /agents/testing/jobs/{job_id}     → Poll job status
    GET    /agents/testing/history           → List user's testing job history
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from opsmindai.api.v1.auth import get_current_user
from opsmindai.db.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/testing", tags=["testing"])


# ── Redis key helpers ─────────────────────────────────────────────────────────

def _job_key(job_id: str) -> str:
    return f"testing:job:{job_id}"

def _user_index_key(user_id: str) -> str:
    return f"testing:user:{user_id}:jobs"


# ── Request / response schemas ────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    repo_url:           str   = Field(..., description="GitHub HTTPS URL of the repository")
    file_path:          Optional[str] = Field(None, description="Relative path to source file. Omit to generate for all files.")
    branch:             str   = Field("master", description="Branch to clone")
    framework:          str   = Field("pytest", description="Test framework: 'pytest' or 'jest'")
    coverage_threshold: float = Field(0.80, ge=0.0, le=1.0, description="Minimum coverage gate (0.0–1.0)")
    pr_number:          Optional[int] = Field(None, description="GitHub PR number — triggers PR comment on gate failure")


class SuiteRequest(BaseModel):
    generation_job_id: str = Field(..., description="Job ID returned from /generate — used to load repo_root")
    pr_number:         Optional[int] = Field(None, description="GitHub PR number for gate failure comment")


class RegressionRequest(BaseModel):
    repo_url:      str  = Field(..., description="GitHub HTTPS URL of the repository")
    branch:        str  = Field("master", description="Branch to clone")
    trigger_event: dict = Field(default_factory=lambda: {"type": "manual"}, description="Event that triggered the regression run")


class JobSubmitResponse(BaseModel):
    job_id:  str
    message: str
    status:  str = "queued"


class CoverageBreakdown(BaseModel):
    coverage_pct:  float
    delta_pct:     float
    lines_covered: int
    lines_total:   int
    gate_passed:   bool
    threshold:     float
    previous_pct:  Optional[float] = None


class GeneratedFileSummary(BaseModel):
    source_file:          str
    output_file:          str
    functions_processed:  int
    tokens_used:          int
    model_used:           str


class JobStatusResponse(BaseModel):
    job_id:       str
    status:       str
    phase:        Optional[str]   = None
    error:        Optional[str]   = None
    created_at:   Optional[str]   = None
    completed_at: Optional[str]   = None
    duration_s:   Optional[float] = None
    # Generation
    generated_files: Optional[list[GeneratedFileSummary]] = None
    warnings:        Optional[list[str]]                  = None
    # Suite
    coverage:    Optional[CoverageBreakdown] = None
    gate_passed: Optional[bool]              = None
    # Regression
    output_file:            Optional[str] = None
    incident_tests_count:   Optional[int] = None
    load_tests_count:       Optional[int] = None
    db_perf_tests_count:    Optional[int] = None
    tokens_used:            Optional[int] = None
    model_used:             Optional[str] = None


class HistoryResponse(BaseModel):
    jobs:  list[JobStatusResponse]
    total: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_redis(request: Request) -> aioredis.Redis:
    pool = getattr(request.app.state, "redis_pool", None)
    if not pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not available",
        )
    return aioredis.Redis(connection_pool=pool)


async def _init_job(redis: aioredis.Redis, job_id: str, phase: str, extra: dict) -> None:
    state = {
        "job_id":     job_id,
        "phase":      phase,
        "status":     "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    await redis.setex(_job_key(job_id), 86_400, json.dumps(state))


async def _read_job(redis: aioredis.Redis, job_id: str) -> dict:
    raw = await redis.get(_job_key(job_id))
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return json.loads(raw)


# ── Phase 1 — Generate ────────────────────────────────────────────────────────

@router.post(
    "/generate",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate test stubs for a repo or file (Phase 1)",
)
async def generate_tests(
    body:    GenerateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Clone the repository, analyse the target source file(s) with the LLM,
    and write test stubs.

    - Omit `file_path` to generate tests for **all** supported files in the repo.
    - Returns a `job_id` immediately. Pass it to `/suite` once complete to run coverage.
    - Supported languages: Python (pytest) and JavaScript/TypeScript (jest).
    """
    redis  = _get_redis(request)
    job_id = f"testgen_{uuid.uuid4().hex[:12]}"

    payload = {
        **body.model_dump(),
        "user_id": str(current_user.id),
    }

    await _init_job(redis, job_id, "generation", {"repo_url": body.repo_url, "user_id": str(current_user.id)})

    try:
         # /home/nabakumr/Music/6thMAy/backend/opsmindai/api/v1/testing_tasks.py
        from opsmindai.api.v1.testing_tasks import task_run_generation
        task_run_generation.apply_async(args=[job_id, payload], task_id=job_id)
    except Exception as exc:
        logger.warning("Celery unavailable — running generation inline: %s", exc)
        from opsmindai.agents.testing.agent import run_generation
        await run_generation(job_id, payload, redis)

    return JobSubmitResponse(
        job_id=job_id,
        message=(
            f"Test generation job submitted. "
            f"Poll /agents/testing/jobs/{job_id} for status, "
            f"then POST /agents/testing/suite with this job_id."
        ),
    )


# ── Phase 2 — Suite ──────────────────────────────────────────────────────────

@router.post(
    "/suite",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run generated tests and enforce coverage gate (Phase 2)",
)
async def run_suite(
    body:    SuiteRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Execute the generated test suite against the cloned repository,
    parse coverage results, and enforce the coverage gate.

    The `generation_job_id` must be a completed job from `/generate` —
    it is used to locate the cloned repo directory.

    If a `pr_number` is provided and the gate fails, a comment is posted
    to the GitHub PR.
    """
    redis  = _get_redis(request)
    job_id = f"testsuite_{uuid.uuid4().hex[:12]}"

    # Verify source generation job exists
    await _read_job(redis, body.generation_job_id)

    payload = {
        "job_id":    body.generation_job_id,   # agent reads state from this job
        "pr_number": body.pr_number,
        "user_id":   str(current_user.id),
    }

    await _init_job(redis, job_id, "suite_execution", {"user_id": str(current_user.id)})

    try:
        from opsmindai.api.v1.testing_tasks import task_run_suite
        task_run_suite.apply_async(args=[job_id, payload], task_id=job_id)
    except Exception as exc:
        logger.warning("Celery unavailable — running suite inline: %s", exc)
        from opsmindai.agents.testing.agent import run_suite
        await run_suite(job_id, payload, redis)

    return JobSubmitResponse(
        job_id=job_id,
        message=f"Suite execution job submitted. Poll /agents/testing/jobs/{job_id} for status.",
    )


# ── Phase 3 — Regression ─────────────────────────────────────────────────────

@router.post(
    "/regression",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Build incident-driven regression + load test suite (Phase 3)",
)
async def run_regression(
    body:    RegressionRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Generate a regression test suite covering:

    - **Incident tests** — tests derived from past incidents to prevent recurrence.
    - **Load tests** — load/stress scenarios for affected endpoints.
    - **DB perf tests** — database performance assertions.

    Pass a `trigger_event` dict to provide context (e.g. `{"type": "incident", "incident_id": "inc_abc"}`).
    """
    redis  = _get_redis(request)
    job_id = f"regression_{uuid.uuid4().hex[:12]}"

    payload = {
        **body.model_dump(),
        "user_id": str(current_user.id),
    }

    await _init_job(redis, job_id, "regression", {"repo_url": body.repo_url, "user_id": str(current_user.id)})

    try:
        from opsmindai.api.v1.testing_tasks import task_run_regression
        task_run_regression.apply_async(args=[job_id, payload], task_id=job_id)
    except Exception as exc:
        logger.warning("Celery unavailable — running regression inline: %s", exc)
        from opsmindai.agents.testing.agent import run_regression
        await run_regression(job_id, payload, redis)

    return JobSubmitResponse(
        job_id=job_id,
        message=f"Regression suite job submitted. Poll /agents/testing/jobs/{job_id} for status.",
    )


# ── Job polling ───────────────────────────────────────────────────────────────

@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll testing job status",
)
async def get_testing_job(
    job_id:  str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Poll the status of any testing job (generate / suite / regression)."""
    redis = _get_redis(request)
    state = await _read_job(redis, job_id)

    # Normalise nested coverage dict into CoverageBreakdown if present
    coverage_raw = state.get("coverage")
    coverage = CoverageBreakdown(**coverage_raw) if coverage_raw else None

    generated_raw = state.get("generated_files") or []
    generated = [GeneratedFileSummary(**f) for f in generated_raw if isinstance(f, dict)]

    return JobStatusResponse(
        job_id=state.get("job_id", job_id),
        status=state.get("status", "unknown"),
        phase=state.get("phase"),
        error=state.get("error"),
        created_at=state.get("created_at"),
        completed_at=state.get("completed_at"),
        duration_s=state.get("duration_s"),
        generated_files=generated or None,
        warnings=state.get("warnings"),
        coverage=coverage,
        gate_passed=state.get("gate_passed"),
        output_file=state.get("output_file"),
        incident_tests_count=state.get("incident_tests_count"),
        load_tests_count=state.get("load_tests_count"),
        db_perf_tests_count=state.get("db_perf_tests_count"),
        tokens_used=state.get("tokens_used"),
        model_used=state.get("model_used"),
    )


# ── Job history ───────────────────────────────────────────────────────────────

@router.get(
    "/history",
    response_model=HistoryResponse,
    summary="List user's testing job history",
)
async def testing_history(
    request: Request,
    limit:   int  = 20,
    current_user: User = Depends(get_current_user),
):
    """Return the most recent testing jobs submitted by the current user."""
    redis   = _get_redis(request)
    idx_key = _user_index_key(str(current_user.id))
    job_ids = await redis.lrange(idx_key, 0, limit - 1) or []

    jobs: list[JobStatusResponse] = []
    for jid in job_ids:
        try:
            state = await _read_job(redis, jid)
            coverage_raw = state.get("coverage")
            coverage = CoverageBreakdown(**coverage_raw) if coverage_raw else None
            jobs.append(JobStatusResponse(
                job_id=state.get("job_id", jid),
                status=state.get("status", "unknown"),
                phase=state.get("phase"),
                error=state.get("error"),
                created_at=state.get("created_at"),
                completed_at=state.get("completed_at"),
                duration_s=state.get("duration_s"),
                coverage=coverage,
                gate_passed=state.get("gate_passed"),
            ))
        except HTTPException:
            continue

    return HistoryResponse(jobs=jobs, total=len(jobs))