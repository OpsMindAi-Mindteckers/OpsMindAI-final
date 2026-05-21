"""
opsmindai/api/v1/sre.py

REST endpoints for the SRE-GPT incident response agent.

Routes:
    POST   /agents/sre/ingest              → Phase 1: ingest alert + auto-dispatch RCA
    POST   /agents/sre/rca                 → Phase 2: manual RCA trigger
    POST   /agents/sre/remediate           → Phase 3: manual remediation trigger
    GET    /agents/sre/jobs/{job_id}       → Poll any SRE job status
    GET    /agents/sre/incidents/{id}      → Get incident detail + timeline
    GET    /agents/sre/history             → List user's SRE job history
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from opsmindai.api.v1.auth import get_current_user
from opsmindai.db.models import User
from opsmindai.schemas.incidents import (
    AlertPayload,
    AlertSource,
    IncidentSeverity,
    Playbook,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/sre", tags=["sre-gpt"])


# ── Redis key helpers ─────────────────────────────────────────────────────────

def _job_key(job_id: str) -> str:
    return f"sre_job:{job_id}"

def _timeline_key(incident_id: str) -> str:
    return f"incident:{incident_id}:timeline"

def _user_index_key(user_id: str) -> str:
    return f"sre:user:{user_id}:jobs"


# ── Request / response schemas ────────────────────────────────────────────────

class IngestRequest(BaseModel):
    source:      AlertSource
    service:     str = Field(..., min_length=1, description="Affected service name")
    severity:    IncidentSeverity
    alert_name:  str = Field(..., min_length=1, description="Alert rule name")
    labels:      dict[str, Any] = Field(default_factory=dict)
    annotations: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class RCARequest(BaseModel):
    incident_id: str = Field(..., description="Incident ID returned from ingest")


class RemediateRequest(BaseModel):
    incident_id: str    = Field(..., description="Incident ID to remediate")
    playbook:    Playbook = Field(Playbook.AUTO, description="Playbook to execute")


class JobSubmitResponse(BaseModel):
    job_id:      str
    incident_id: Optional[str] = None
    message:     str
    status:      str = "queued"


class JobStatusResponse(BaseModel):
    job_id:      str
    status:      str
    phase:       Optional[str]       = None
    incident_id: Optional[str]       = None
    error:       Optional[str]       = None
    created_at:  Optional[str]       = None
    completed_at: Optional[str]      = None
    duration_s:  Optional[float]     = None
    # RCA-specific
    confidence:      Optional[float] = None
    root_cause:      Optional[str]   = None
    auto_remediable: Optional[bool]  = None
    # Remediation-specific
    remediation_status: Optional[str]     = None
    actions_taken:      Optional[list]    = None
    normalised:         Optional[bool]    = None


class TimelineEventOut(BaseModel):
    timestamp: str
    event:     str
    details:   dict[str, Any] = Field(default_factory=dict)


class IncidentDetailResponse(BaseModel):
    incident_id: str
    timeline:    list[TimelineEventOut]


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


async def _read_job(redis: aioredis.Redis, job_id: str) -> dict:
    raw = await redis.get(_job_key(job_id))
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return json.loads(raw)


# ── Phase 1 — Ingest ──────────────────────────────────────────────────────────

@router.post(
    "/ingest",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest alert and auto-dispatch RCA (Phase 1)",
)
async def ingest_alert(
    body:    IngestRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Normalise an incoming alert, apply 60s dedup window, persist the
    incident, and automatically dispatch Phase 2 (RCA) as a Celery task.

    Returns immediately with a `job_id`. Poll `/agents/sre/jobs/{job_id}`
    for status.
    """
    redis = _get_redis(request)
    job_id = f"ingest_{uuid.uuid4().hex[:12]}"

    payload = {
        "alert_payload": body.model_dump(),
        "user_id": str(current_user.id),
    }

    # Initialise job state
    await redis.setex(
        _job_key(job_id),
        86_400,
        json.dumps({
            "job_id":     job_id,
            "phase":      "ingest",
            "status":     "queued",
            "user_id":    str(current_user.id),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }),
    )

    try:
        from opsmindai.tasks.sre_tasks import task_run_ingest
        task_run_ingest.apply_async(
            args=[job_id, payload],
            task_id=job_id,
            priority=9,
        )
    except Exception as exc:
        logger.warning("Celery unavailable — running ingest inline: %s", exc)
        from opsmindai.agents.sre_gpt.agent import run_ingest
        await run_ingest(job_id, payload, redis)

    return JobSubmitResponse(
        job_id=job_id,
        message=f"Alert ingested. Poll /agents/sre/jobs/{job_id} for status.",
    )


# ── Phase 2 — RCA ─────────────────────────────────────────────────────────────

@router.post(
    "/rca",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger RCA for an incident (Phase 2)",
)
async def trigger_rca(
    body:    RCARequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Manually kick off root-cause analysis for an existing incident.
    Normally RCA is auto-dispatched after ingest, but this endpoint lets
    you retrigger it (e.g. after new evidence arrives).
    """
    redis = _get_redis(request)
    job_id = f"rca_{uuid.uuid4().hex[:12]}"

    payload = {
        "incident_id": body.incident_id,
        "user_id":     str(current_user.id),
    }

    await redis.setex(
        _job_key(job_id),
        86_400,
        json.dumps({
            "job_id":      job_id,
            "phase":       "rca",
            "status":      "queued",
            "incident_id": body.incident_id,
            "user_id":     str(current_user.id),
            "created_at":  datetime.now(timezone.utc).isoformat(),
        }),
    )

    try:
        from opsmindai.tasks.sre_tasks import task_run_rca
        task_run_rca.apply_async(args=[job_id, payload], task_id=job_id)
    except Exception as exc:
        logger.warning("Celery unavailable — running RCA inline: %s", exc)
        from opsmindai.agents.sre_gpt.agent import run_rca
        await run_rca(job_id, payload, redis)

    return JobSubmitResponse(
        job_id=job_id,
        incident_id=body.incident_id,
        message=f"RCA job submitted. Poll /agents/sre/jobs/{job_id} for status.",
    )


# ── Phase 3 — Remediate ──────────────────────────────────────────────────────

@router.post(
    "/remediate",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger remediation playbook (Phase 3)",
)
async def trigger_remediate(
    body:    RemediateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Execute a remediation playbook against an incident.

    - Use `playbook: "auto"` to let the agent pick the best playbook.
    - Other options: `rollback`, `restart`, `scale`, `flush_pool`, `isolate_node`.
    """
    redis = _get_redis(request)
    job_id = f"rem_{uuid.uuid4().hex[:12]}"

    payload = {
        "incident_id": body.incident_id,
        "playbook":    body.playbook.value,
        "user_id":     str(current_user.id),
    }

    await redis.setex(
        _job_key(job_id),
        86_400,
        json.dumps({
            "job_id":      job_id,
            "phase":       "remediate",
            "status":      "queued",
            "incident_id": body.incident_id,
            "playbook":    body.playbook.value,
            "user_id":     str(current_user.id),
            "created_at":  datetime.now(timezone.utc).isoformat(),
        }),
    )

    try:
        from opsmindai.tasks.sre_tasks import task_run_remediate
        task_run_remediate.apply_async(args=[job_id, payload], task_id=job_id, priority=9)
    except Exception as exc:
        logger.warning("Celery unavailable — running remediation inline: %s", exc)
        from opsmindai.agents.sre_gpt.agent import run_remediate
        await run_remediate(job_id, payload, redis)

    return JobSubmitResponse(
        job_id=job_id,
        incident_id=body.incident_id,
        message=f"Remediation job submitted. Poll /agents/sre/jobs/{job_id} for status.",
    )


# ── Job polling ───────────────────────────────────────────────────────────────

@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll SRE job status",
)
async def get_sre_job(
    job_id:  str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Poll the status of any SRE job (ingest / rca / remediate)."""
    redis  = _get_redis(request)
    state  = await _read_job(redis, job_id)
    return JobStatusResponse(**{k: state.get(k) for k in JobStatusResponse.model_fields})


# ── Incident detail + timeline ────────────────────────────────────────────────

@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentDetailResponse,
    summary="Get incident timeline",
)
async def get_incident_detail(
    incident_id: str,
    request:     Request,
    current_user: User = Depends(get_current_user),
):
    """Return the full timeline of events for an incident."""
    redis = _get_redis(request)
    raw_events = await redis.lrange(_timeline_key(incident_id), 0, -1)
    if raw_events is None:
        raw_events = []

    timeline = []
    for raw in raw_events:
        try:
            ev = json.loads(raw)
            timeline.append(TimelineEventOut(
                timestamp=ev.get("timestamp", ""),
                event=ev.get("event", ""),
                details=ev.get("details", {}),
            ))
        except Exception:
            continue

    # Timeline is stored newest-first (lpush), reverse for chronological order
    timeline.reverse()
    return IncidentDetailResponse(incident_id=incident_id, timeline=timeline)


# ── Job history ───────────────────────────────────────────────────────────────

@router.get(
    "/history",
    response_model=HistoryResponse,
    summary="List user's SRE job history",
)
async def sre_history(
    request: Request,
    limit:   int  = 20,
    current_user: User = Depends(get_current_user),
):
    """Return the most recent SRE jobs submitted by the current user."""
    redis   = _get_redis(request)
    idx_key = _user_index_key(str(current_user.id))
    job_ids = await redis.lrange(idx_key, 0, limit - 1) or []

    jobs: list[JobStatusResponse] = []
    for jid in job_ids:
        try:
            state = await _read_job(redis, jid)
            jobs.append(JobStatusResponse(**{k: state.get(k) for k in JobStatusResponse.model_fields}))
        except HTTPException:
            continue

    return HistoryResponse(jobs=jobs, total=len(jobs))