# from fastapi import APIRouter, HTTPException, Depends, status, Query, Path
# from typing import List, Optional, Dict, Any
# from pydantic import BaseModel, Field
# from datetime import datetime
# from uuid import UUID

# router = APIRouter(prefix="/agents", tags=["agents"])


# # ==================== SCHEMAS ====================

# class AgentMetrics(BaseModel):
#     """Operational metrics for a specific agent"""
#     agent_name: str = Field(..., description="Name of the agent")
#     total_runs: int = Field(..., description="Total number of agent runs")
#     success_rate: float = Field(..., ge=0, le=1, description="Success rate as decimal (0-1)")
#     avg_duration_s: float = Field(..., description="Average duration in seconds")
#     avg_tokens_used: int = Field(..., description="Average tokens used per run")
#     revision_rate: float = Field(..., ge=0, le=1, description="Revision rate as decimal")
#     cost_usd_total: float = Field(..., description="Total cost in USD")
#     cost_usd_avg: float = Field(..., description="Average cost per run in USD")
#     last_run_at: Optional[datetime] = Field(None, description="Timestamp of last run")


# class AgentConfig(BaseModel):
#     """Agent configuration parameters"""
#     prompt: Optional[str] = Field(None, description="Agent system prompt")
#     max_tokens: Optional[int] = Field(None, description="Maximum tokens for generation")
#     temperature: Optional[float] = Field(None, ge=0, le=2, description="Temperature parameter")
#     top_p: Optional[float] = Field(None, ge=0, le=1, description="Top-p sampling parameter")
#     retry_count: Optional[int] = Field(None, ge=0, description="Number of retries on failure")
#     timeout_seconds: Optional[int] = Field(None, ge=1, description="Timeout in seconds")
#     enabled: Optional[bool] = Field(None, description="Agent enabled status")


# class UpdateAgentConfigRequest(BaseModel):
#     """Request to update agent configuration"""
#     prompt: Optional[str] = Field(None, description="Agent system prompt")
#     max_tokens: Optional[int] = Field(None, description="Maximum tokens for generation")
#     temperature: Optional[float] = Field(None, ge=0, le=2, description="Temperature parameter")
#     top_p: Optional[float] = Field(None, ge=0, le=1, description="Top-p sampling parameter")
#     retry_count: Optional[int] = Field(None, ge=0, description="Number of retries on failure")
#     timeout_seconds: Optional[int] = Field(None, ge=1, description="Timeout in seconds")
#     enabled: Optional[bool] = Field(None, description="Agent enabled status")


# class AgentStatus(BaseModel):
#     """Status of an individual agent"""
#     agent_name: str = Field(..., description="Name of the agent")
#     status: str = Field(..., description="Current status: active, idle, error, disabled")
#     version: str = Field(..., description="Agent version")
#     enabled: bool = Field(..., description="Whether agent is enabled")
#     last_error: Optional[str] = Field(None, description="Last error message if any")
#     last_run_at: Optional[datetime] = Field(None, description="Last run timestamp")


# class AgentStatusResponse(BaseModel):
#     """Response containing list of all agents and their status"""
#     agents: List[AgentStatus] = Field(..., description="List of registered agents")
#     total: int = Field(..., description="Total number of agents")
#     healthy_count: int = Field(..., description="Number of healthy agents")


# class AgentDetailResponse(BaseModel):
#     """Detailed information about a specific agent"""
#     agent_name: str = Field(..., description="Name of the agent")
#     status: str = Field(..., description="Current status")
#     version: str = Field(..., description="Agent version")
#     enabled: bool = Field(..., description="Whether agent is enabled")
#     config: AgentConfig = Field(..., description="Agent configuration")
#     metrics: Optional[AgentMetrics] = Field(None, description="Agent metrics")
#     description: Optional[str] = Field(None, description="Agent description")
#     created_at: datetime = Field(..., description="Creation timestamp")
#     updated_at: datetime = Field(..., description="Last update timestamp")


# class AgentConfigResponse(BaseModel):
#     """Response after updating agent configuration"""
#     agent_name: str = Field(..., description="Name of the agent")
#     config: AgentConfig = Field(..., description="Updated configuration")
#     updated_at: datetime = Field(..., description="Update timestamp")
#     message: str = Field(..., description="Status message")


# # ==================== ENDPOINTS ====================

# @router.get("", response_model=AgentStatusResponse)
# async def list_agents(
#     status_filter: Optional[str] = Query(None, description="Filter by status: active, idle, error, disabled")
# ):
#     """
#     List all registered agents and their status
    
#     Returns a list of all agents in the system with their current status,
#     health information, and basic metrics.
    
#     **Auth Required:** Bearer token
#     """
#     pass


# @router.get("/{agent_name}", response_model=AgentDetailResponse)
# async def get_agent(
#     agent_name: str = Path(..., description="Name of the agent", min_length=1)
# ):
#     """
#     Get agent configuration and metrics
    
#     Returns detailed information about a specific agent including its configuration,
#     current status, and operational metrics.
    
#     **Auth Required:** Bearer token
    
#     **Path Parameters:**
#     - `agent_name`: The unique identifier of the agent
#     """
#     pass


# @router.get("/{agent_name}/metrics", response_model=AgentMetrics)
# async def get_agent_metrics(
#     agent_name: str = Path(..., description="Name of the agent", min_length=1)
# ):
#     """
#     Get operational metrics for a specific agent
    
#     Returns operational metrics including token usage, average duration, 
#     success rate, and cost analysis. Useful for monitoring agent performance 
#     and cost optimization.
    
#     **Auth Required:** Bearer token
    
#     **Path Parameters:**
#     - `agent_name`: The unique identifier of the agent
    
#     **Response (200):**
#     ```json
#     {
#       "agent_name": "backend",
#       "total_runs": 1482,
#       "success_rate": 0.93,
#       "avg_duration_s": 31.4,
#       "avg_tokens_used": 11200,
#       "revision_rate": 0.12,
#       "cost_usd_total": 284.20,
#       "cost_usd_avg": 0.19,
#       "last_run_at": "2025-01-01T00:00:00Z"
#     }
#     ```
#     """
#     pass


# @router.patch("/{agent_name}/config", response_model=AgentConfigResponse, status_code=status.HTTP_200_OK)
# async def update_agent_config(
#     agent_name: str = Path(..., description="Name of the agent", min_length=1),
#     request: UpdateAgentConfigRequest = None
# ):
#     """
#     Update agent prompt or parameters
    
#     Updates the configuration of a specific agent. Allows modifications to:
#     - System prompt
#     - Token limits
#     - Sampling parameters (temperature, top_p)
#     - Retry behavior
#     - Timeout settings
#     - Enable/disable status
    
#     **Auth Required:** Bearer token with Admin role (Admin only)
    
#     **Path Parameters:**
#     - `agent_name`: The unique identifier of the agent
    
#     **Request Body:**
#     ```json
#     {
#       "prompt": "Updated system prompt...",
#       "max_tokens": 4096,
#       "temperature": 0.7,
#       "top_p": 0.9,
#       "retry_count": 3,
#       "timeout_seconds": 60,
#       "enabled": true
#     }
#     ```
    
#     **Response (200):**
#     ```json
#     {
#       "agent_name": "backend",
#       "config": {
#         "prompt": "Updated system prompt...",
#         "max_tokens": 4096,
#         "temperature": 0.7,
#         "top_p": 0.9,
#         "retry_count": 3,
#         "timeout_seconds": 60,
#         "enabled": true
#       },
#       "updated_at": "2025-01-01T00:00:00Z",
#       "message": "Agent configuration updated successfully"
#     }
#     ```
#     """
#     pass















"""
opsmindai/api/v1/agents.py

Refactor agent REST API.

Endpoints:
  GET    /agents                         → list all known agents + live status
  GET    /agents/{agent_name}            → agent detail + config + metrics
  GET    /agents/{agent_name}/metrics    → metrics only
  PATCH  /agents/{agent_name}/config     → update config (admin only)

  POST   /agents/refactor/analyze        → Phase 1: submit analysis job
  GET    /agents/refactor/jobs/{job_id}  → poll job status / result
  POST   /agents/refactor/suggest        → Phase 2: generate LLM suggestions
  POST   /agents/refactor/apply          → Phase 3: open GitHub PR
  GET    /agents/refactor/history        → list user's past jobs (newest first)

Auth: every endpoint requires get_current_user.
Admin: config PATCH additionally requires is_admin().
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from opsmindai.api.v1.auth import get_current_user
from opsmindai.core.redis import get_redis
from opsmindai.db.models import User
from opsmindai.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

# ── Constants ─────────────────────────────────────────────────────────────────

# All agents the platform currently knows about.
# Extend this list as new agents are added.
_KNOWN_AGENTS: list[str] = ["refactor"]

# Users whose `User.id` is in this set are treated as admins.
# In production, move this to a DB role column or a settings value.
import os
_ADMIN_USER_IDS: set[str] = set(
    filter(None, os.environ.get("ADMIN_USER_IDS", "").split(","))
)

# Redis key TTL for job state (24 hours)
_JOB_TTL = 86_400

# Max jobs returned in history
_HISTORY_LIMIT = 50


# ── Admin guard ───────────────────────────────────────────────────────────────

def is_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency that raises 403 unless the user is an admin."""
    if user.id not in _ADMIN_USER_IDS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# ── Redis helpers ─────────────────────────────────────────────────────────────

def _job_key(job_id: str) -> str:
    return f"refactor:job:{job_id}"


def _user_jobs_key(user_id: str) -> str:
    return f"refactor:user:{user_id}:jobs"


def _agent_config_key(agent_name: str) -> str:
    return f"agent:config:{agent_name}"


def _agent_metrics_key(agent_name: str) -> str:
    return f"agent:metrics:{agent_name}"


async def _get_job(redis: aioredis.Redis, job_id: str) -> dict:
    """Fetch job state from Redis. Raises 404 if missing."""
    raw = await redis.get(_job_key(job_id))
    if not raw:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return json.loads(raw)


async def _set_job(redis: aioredis.Redis, job_id: str, state: dict) -> None:
    await redis.setex(_job_key(job_id), _JOB_TTL, json.dumps(state, default=str))


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AgentConfig(BaseModel):
    prompt: Optional[str] = Field(None, description="Agent system prompt override")
    max_tokens: Optional[int] = Field(None, ge=1, le=32_000)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    retry_count: Optional[int] = Field(None, ge=0, le=10)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=3600)
    enabled: Optional[bool] = None


class AgentMetrics(BaseModel):
    agent_name: str
    total_runs: int
    success_rate: float = Field(ge=0, le=1)
    avg_duration_s: float
    avg_tokens_used: int
    revision_rate: float = Field(ge=0, le=1)
    cost_usd_total: float
    cost_usd_avg: float
    last_run_at: Optional[datetime] = None


class AgentStatus(BaseModel):
    agent_name: str
    status: str  # active | idle | error | disabled
    version: str
    enabled: bool
    last_error: Optional[str] = None
    last_run_at: Optional[datetime] = None


class AgentStatusResponse(BaseModel):
    agents: list[AgentStatus]
    total: int
    healthy_count: int


class AgentDetailResponse(BaseModel):
    agent_name: str
    status: str
    version: str
    enabled: bool
    config: AgentConfig
    metrics: Optional[AgentMetrics] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AgentConfigResponse(BaseModel):
    agent_name: str
    config: AgentConfig
    updated_at: datetime
    message: str


# ── Refactor job schemas ──────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., description="HTTPS GitHub repo URL")
    branch: str = Field("main", description="Branch to analyse")
    file_paths: list[str] = Field(
        default_factory=list,
        description="Specific files to analyse. Leave empty to scan whole repo.",
    )
    severity_threshold: str = Field(
        "medium",
        pattern="^(low|medium|high|critical)$",
        description="Minimum severity to report",
    )


class SuggestRequest(BaseModel):
    repo_url: str = Field(..., description="HTTPS GitHub repo URL")
    branch: str = Field("main")
    source_job_id: str = Field(
        ..., description="job_id from a completed /analyze job"
    )


class ApplyRequest(BaseModel):
    repo_url: str = Field(..., description="HTTPS GitHub repo URL")
    branch: str = Field("main")
    source_job_id: str = Field(
        ..., description="job_id from a completed /suggest job"
    )
    pr_title: Optional[str] = Field(None, description="Custom PR title")
    pr_body: Optional[str] = Field(None, description="Custom PR body (Markdown)")
    draft: bool = Field(True, description="Open PR as draft")
    notify_slack: bool = Field(True, description="Send Slack notification on PR open")


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending | running | completed | failed
    phase: str   # analyze | suggest | apply
    created_at: datetime
    completed_at: Optional[datetime] = None
    duration_s: Optional[float] = None
    error: Optional[str] = None
    # Phase-specific result fields (present when status=completed)
    result: Optional[dict[str, Any]] = None


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str = "pending"
    message: str


class JobHistoryResponse(BaseModel):
    jobs: list[JobStatusResponse]
    total: int


# ── Agent config / status helpers ────────────────────────────────────────────

_AGENT_DESCRIPTIONS: dict[str, str] = {
    "refactor": (
        "Analyses source repositories for code smells using tree-sitter AST parsing, "
        "generates LLM-powered refactor patches, and opens GitHub pull requests."
    ),
}

_AGENT_VERSIONS: dict[str, str] = {
    "refactor": "1.0.0",
}

_DEFAULT_CONFIGS: dict[str, AgentConfig] = {
    "refactor": AgentConfig(
        max_tokens=4096,
        temperature=0.2,
        top_p=0.9,
        retry_count=2,
        timeout_seconds=300,
        enabled=True,
    ),
}


async def _load_agent_config(
    redis: aioredis.Redis, agent_name: str
) -> AgentConfig:
    """Load agent config from Redis, falling back to defaults."""
    raw = await redis.get(_agent_config_key(agent_name))
    if raw:
        return AgentConfig(**json.loads(raw))
    return _DEFAULT_CONFIGS.get(agent_name, AgentConfig(enabled=True))


async def _load_agent_metrics(
    redis: aioredis.Redis, agent_name: str
) -> Optional[AgentMetrics]:
    """Load agent metrics from Redis. Returns None if no runs recorded yet."""
    raw = await redis.get(_agent_metrics_key(agent_name))
    if not raw:
        return None
    data = json.loads(raw)
    return AgentMetrics(agent_name=agent_name, **data)


async def _build_agent_status(
    redis: aioredis.Redis, agent_name: str
) -> AgentStatus:
    """Derive live status from config + most recent job state."""
    config = await _load_agent_config(redis, agent_name)
    if not config.enabled:
        return AgentStatus(
            agent_name=agent_name,
            status="disabled",
            version=_AGENT_VERSIONS.get(agent_name, "unknown"),
            enabled=False,
        )

    metrics = await _load_agent_metrics(redis, agent_name)
    last_run_at = metrics.last_run_at if metrics else None

    return AgentStatus(
        agent_name=agent_name,
        status="active" if metrics else "idle",
        version=_AGENT_VERSIONS.get(agent_name, "unknown"),
        enabled=True,
        last_run_at=last_run_at,
    )


# ── Agent management endpoints ────────────────────────────────────────────────

@router.get("", response_model=AgentStatusResponse, summary="List all agents")
async def list_agents(
    status_filter: Optional[str] = Query(
        None,
        pattern="^(active|idle|error|disabled)$",
        description="Filter by status",
    ),
    _user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Return live status for every registered agent.

    Reads config + metrics from Redis to determine current status.
    No DB query required — all agent state is cached in Redis.
    """
    statuses: list[AgentStatus] = []
    for name in _KNOWN_AGENTS:
        s = await _build_agent_status(redis, name)
        if status_filter is None or s.status == status_filter:
            statuses.append(s)

    healthy = sum(1 for s in statuses if s.status in ("active", "idle"))
    return AgentStatusResponse(
        agents=statuses,
        total=len(statuses),
        healthy_count=healthy,
    )


@router.get(
    "/{agent_name}",
    response_model=AgentDetailResponse,
    summary="Get agent detail",
)
async def get_agent(
    agent_name: str = Path(..., min_length=1),
    _user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Return full detail for a specific agent: config, metrics, status."""
    if agent_name not in _KNOWN_AGENTS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    config = await _load_agent_config(redis, agent_name)
    metrics = await _load_agent_metrics(redis, agent_name)
    agent_status = await _build_agent_status(redis, agent_name)

    now = datetime.now(timezone.utc)
    return AgentDetailResponse(
        agent_name=agent_name,
        status=agent_status.status,
        version=_AGENT_VERSIONS.get(agent_name, "unknown"),
        enabled=config.enabled if config.enabled is not None else True,
        config=config,
        metrics=metrics,
        description=_AGENT_DESCRIPTIONS.get(agent_name),
        # These would come from a DB row in a full implementation.
        # Using sentinel values until an AgentConfig DB table is added.
        created_at=now,
        updated_at=now,
    )


@router.get(
    "/{agent_name}/metrics",
    response_model=AgentMetrics,
    summary="Get agent metrics",
)
async def get_agent_metrics(
    agent_name: str = Path(..., min_length=1),
    _user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Return operational metrics for a specific agent."""
    if agent_name not in _KNOWN_AGENTS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    metrics = await _load_agent_metrics(redis, agent_name)
    if not metrics:
        # Return zero-state metrics — agent exists but has never run
        return AgentMetrics(
            agent_name=agent_name,
            total_runs=0,
            success_rate=0.0,
            avg_duration_s=0.0,
            avg_tokens_used=0,
            revision_rate=0.0,
            cost_usd_total=0.0,
            cost_usd_avg=0.0,
            last_run_at=None,
        )
    return metrics


@router.patch(
    "/{agent_name}/config",
    response_model=AgentConfigResponse,
    summary="Update agent config (admin only)",
)
async def update_agent_config(
    agent_name: str = Path(..., min_length=1),
    request_body: AgentConfig = None,
    admin: User = Depends(is_admin),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Merge new config values into the stored agent config.

    Only fields explicitly provided are updated (partial update semantics).
    Requires admin privileges — enforced via `is_admin` dependency.
    """
    if agent_name not in _KNOWN_AGENTS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    if request_body is None:
        raise HTTPException(status_code=422, detail="Request body is required")

    # Load existing, merge non-None fields from request
    existing = await _load_agent_config(redis, agent_name)
    existing_dict = existing.model_dump()
    update_dict = request_body.model_dump(exclude_none=True)
    merged = {**existing_dict, **update_dict}

    updated_config = AgentConfig(**merged)
    await redis.setex(
        _agent_config_key(agent_name),
        _JOB_TTL * 30,  # config persists for 30 days
        json.dumps(merged),
    )

    logger.info(
        "Agent config updated by admin %s: agent=%s fields=%s",
        admin.id, agent_name, list(update_dict.keys()),
    )

    return AgentConfigResponse(
        agent_name=agent_name,
        config=updated_config,
        updated_at=datetime.now(timezone.utc),
        message=f"Agent '{agent_name}' configuration updated successfully",
    )


# ── Refactor pipeline endpoints ───────────────────────────────────────────────

@router.post(
    "/refactor/analyze",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit repository analysis job (Phase 1)",
)
async def submit_analysis(
    body: AnalyzeRequest,
    user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Submit a Phase 1 analysis job.

    Clones the repository, runs tree-sitter AST parsing, and detects
    code smells above the requested severity threshold.

    Returns immediately with a `job_id`. Poll `/refactor/jobs/{job_id}`
    to check progress.
    """
    # Guard: check agent is enabled
    config = await _load_agent_config(redis, "refactor")
    if config.enabled is False:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Refactor agent is currently disabled",
        )

    job_id = str(uuid.uuid4())
    payload = {
        **body.model_dump(),
        "user_id": user.id,
        "phase": "analyze",
    }

    # Persist initial job state to Redis before dispatching
    await _set_job(redis, job_id, {
        "job_id":     job_id,
        "status":     "pending",
        "phase":      "analyze",
        "user_id":    user.id,
        "repo_url":   body.repo_url,
        "branch":     body.branch,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Index job under user for history endpoint
    await redis.lpush(_user_jobs_key(user.id), job_id)
    await redis.expire(_user_jobs_key(user.id), _JOB_TTL * 30)

    # Dispatch to Celery worker
    try:
        from opsmindai.tasks.refactor_tasks import task_run_analysis
        task_run_analysis.apply_async(
            args=[job_id, payload],
            task_id=job_id,      # use job_id as Celery task ID for easy lookup
        )
        logger.info("Analysis job dispatched: job=%s user=%s repo=%s",
                    job_id, user.id, body.repo_url)
    except Exception as exc:
        # Celery unavailable — update job to failed and raise
        await _set_job(redis, job_id, {
            "job_id": job_id, "status": "failed",
            "phase": "analyze", "user_id": user.id,
            "error": f"Failed to dispatch job: {exc}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.exception("Failed to dispatch analysis job %s", job_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not dispatch job: {exc}",
        )

    return JobSubmitResponse(
        job_id=job_id,
        status="pending",
        message=f"Analysis job submitted. Poll /agents/refactor/jobs/{job_id} for status.",
    )


@router.post(
    "/refactor/suggest",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate LLM refactor suggestions (Phase 2)",
)
async def submit_suggest(
    body: SuggestRequest,
    user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Submit a Phase 2 suggestion job.

    Reads detected smells from the source analysis job, sends them to the
    LLM refactor engine, and generates unified diff patches.

    Requires a `source_job_id` pointing to a **completed** Phase 1 job
    owned by the same user.
    """
    # Verify source job exists and belongs to this user
    source_state = await _get_job(redis, body.source_job_id)

    if source_state.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Job does not belong to you")

    if source_state.get("phase") != "analyze":
        raise HTTPException(
            status_code=400,
            detail="source_job_id must point to an 'analyze' phase job",
        )

    if source_state.get("status") != "completed":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Source job is '{source_state.get('status')}' — "
                "wait for it to complete before requesting suggestions"
            ),
        )

    smells = source_state.get("smells", [])
    if not smells:
        raise HTTPException(
            status_code=400,
            detail="Source analysis job found no smells — nothing to suggest",
        )

    job_id = str(uuid.uuid4())
    payload = {
        "repo_url":      body.repo_url,
        "branch":        body.branch,
        "smells":        smells,
        "source_job_id": body.source_job_id,
        "user_id":       user.id,
        "phase":         "suggest",
    }

    await _set_job(redis, job_id, {
        "job_id":        job_id,
        "status":        "pending",
        "phase":         "suggest",
        "user_id":       user.id,
        "source_job_id": body.source_job_id,
        "repo_url":      body.repo_url,
        "branch":        body.branch,
        "created_at":    datetime.now(timezone.utc).isoformat(),
    })

    await redis.lpush(_user_jobs_key(user.id), job_id)
    await redis.expire(_user_jobs_key(user.id), _JOB_TTL * 30)

    try:
        from opsmindai.tasks.refactor_tasks import task_run_suggest
        task_run_suggest.apply_async(args=[job_id, payload], task_id=job_id)
        logger.info("Suggest job dispatched: job=%s source=%s user=%s",
                    job_id, body.source_job_id, user.id)
    except Exception as exc:
        await _set_job(redis, job_id, {
            "job_id": job_id, "status": "failed", "phase": "suggest",
            "user_id": user.id, "error": f"Failed to dispatch job: {exc}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not dispatch job: {exc}",
        )

    return JobSubmitResponse(
        job_id=job_id,
        status="pending",
        message=f"Suggestion job submitted. Poll /agents/refactor/jobs/{job_id} for status.",
    )


@router.post(
    "/refactor/apply",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Apply patches and open GitHub PR (Phase 3)",
)
async def submit_apply(
    body: ApplyRequest,
    user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Submit a Phase 3 apply job.

    Reads patches from the source suggestion job, applies them to a new
    branch, commits, pushes, and opens a (draft) GitHub PR.

    Requires a `source_job_id` pointing to a **completed** Phase 2 job.
    """
    source_state = await _get_job(redis, body.source_job_id)

    if source_state.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Job does not belong to you")

    if source_state.get("phase") != "suggest":
        raise HTTPException(
            status_code=400,
            detail="source_job_id must point to a 'suggest' phase job",
        )

    if source_state.get("status") != "completed":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Source job is '{source_state.get('status')}' — "
                "wait for suggestions to complete before applying"
            ),
        )

    patches = source_state.get("patches", [])
    if not patches:
        raise HTTPException(
            status_code=400,
            detail="Source suggest job produced no patches — nothing to apply",
        )

    # Pull smells from the original analyze job for PR body generation
    analyze_job_id = source_state.get("source_job_id")
    smells: list = []
    if analyze_job_id:
        try:
            analyze_state = await _get_job(redis, analyze_job_id)
            smells = analyze_state.get("smells", [])
        except HTTPException:
            logger.warning("Could not load analyze job %s for smells", analyze_job_id)

    job_id = str(uuid.uuid4())
    payload = {
        "repo_url":      body.repo_url,
        "branch":        body.branch,
        "patches":       patches,
        "smells":        smells,
        "source_job_id": body.source_job_id,
        "pr_title":      body.pr_title,
        "pr_body":       body.pr_body,
        "draft":         body.draft,
        "notify_slack":  body.notify_slack,
        "user_id":       user.id,
        "phase":         "apply",
    }

    await _set_job(redis, job_id, {
        "job_id":        job_id,
        "status":        "pending",
        "phase":         "apply",
        "user_id":       user.id,
        "source_job_id": body.source_job_id,
        "repo_url":      body.repo_url,
        "branch":        body.branch,
        "created_at":    datetime.now(timezone.utc).isoformat(),
    })

    await redis.lpush(_user_jobs_key(user.id), job_id)
    await redis.expire(_user_jobs_key(user.id), _JOB_TTL * 30)

    try:
        from opsmindai.tasks.refactor_tasks import task_run_apply
        task_run_apply.apply_async(args=[job_id, payload], task_id=job_id)
        logger.info("Apply job dispatched: job=%s source=%s user=%s",
                    job_id, body.source_job_id, user.id)
    except Exception as exc:
        await _set_job(redis, job_id, {
            "job_id": job_id, "status": "failed", "phase": "apply",
            "user_id": user.id, "error": f"Failed to dispatch job: {exc}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not dispatch job: {exc}",
        )

    return JobSubmitResponse(
        job_id=job_id,
        status="pending",
        message=f"Apply job submitted. Poll /agents/refactor/jobs/{job_id} for status.",
    )


@router.get(
    "/refactor/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll job status and result",
)
async def get_job_status(
    job_id: str = Path(..., min_length=1),
    user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Poll a refactor job for its current status.

    Returns the full job state once complete, including smells, patches,
    or PR URL depending on the phase.

    Users can only access their own jobs.
    """
    state = await _get_job(redis, job_id)

    if state.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Job does not belong to you")

    # Build result payload from completed phase-specific fields
    result: Optional[dict] = None
    if state.get("status") == "completed":
        phase = state.get("phase")
        if phase == "analyze":
            result = {
                "smells":         state.get("smells", []),
                "total_smells":   state.get("total_smells", 0),
                "severity_score": state.get("severity_score", 0.0),
                "critical_count": state.get("critical_count", 0),
                "high_count":     state.get("high_count", 0),
                "file_paths":     state.get("file_paths", []),
            }
        elif phase == "suggest":
            result = {
                "patches":     state.get("patches", []),
                "tokens_used": state.get("tokens_used", 0),
                "model_used":  state.get("model_used", "unknown"),
            }
        elif phase == "apply":
            result = {
                "pr_url":       state.get("pr_url"),
                "pr_number":    state.get("pr_number"),
                "pr_title":     state.get("pr_title"),
                "branch":       state.get("branch"),
                "files_changed":state.get("files_changed", 0),
            }

    return JobStatusResponse(
        job_id=job_id,
        status=state.get("status", "unknown"),
        phase=state.get("phase", "unknown"),
        created_at=datetime.fromisoformat(state["created_at"]),
        completed_at=(
            datetime.fromisoformat(state["completed_at"])
            if state.get("completed_at") else None
        ),
        duration_s=state.get("duration_s"),
        error=state.get("error"),
        result=result,
    )


@router.get(
    "/refactor/history",
    response_model=JobHistoryResponse,
    summary="List user's refactor job history",
)
async def get_job_history(
    limit: int = Query(20, ge=1, le=_HISTORY_LIMIT, description="Max jobs to return"),
    user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Return the most recent refactor jobs submitted by the current user.

    Jobs are returned newest-first. Only jobs still alive in Redis
    (within the 30-day TTL) are returned.
    """
    raw_ids = await redis.lrange(_user_jobs_key(user.id), 0, limit - 1)
    if not raw_ids:
        return JobHistoryResponse(jobs=[], total=0)

    jobs: list[JobStatusResponse] = []
    for job_id in raw_ids:
        raw = await redis.get(_job_key(job_id))
        if not raw:
            continue  # TTL expired
        state = json.loads(raw)

        # Skip jobs not belonging to this user (safety check)
        if state.get("user_id") != user.id:
            continue

        jobs.append(JobStatusResponse(
            job_id=job_id,
            status=state.get("status", "unknown"),
            phase=state.get("phase", "unknown"),
            created_at=datetime.fromisoformat(state["created_at"]),
            completed_at=(
                datetime.fromisoformat(state["completed_at"])
                if state.get("completed_at") else None
            ),
            duration_s=state.get("duration_s"),
            error=state.get("error"),
            result=None,  # history view omits full result for brevity
        ))

    return JobHistoryResponse(jobs=jobs, total=len(jobs))