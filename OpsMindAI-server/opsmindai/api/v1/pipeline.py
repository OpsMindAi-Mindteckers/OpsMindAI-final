"""
opsmindai/api/v1/pipeline.py

REST + SSE endpoints for the end-to-end autonomous pipeline.

Routes:
    POST  /agents/pipeline/run           → Submit pipeline job
    GET   /agents/pipeline/jobs/{id}     → Poll pipeline state
    GET   /agents/pipeline/stream/{id}   → SSE stream of events
    GET   /agents/pipeline/history       → List user's pipeline runs
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from opsmindai.api.v1.auth import get_current_user
from opsmindai.db.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/pipeline", tags=["pipeline"])

TTL = 86_400  # 24 h


# ── Redis key helpers ─────────────────────────────────────────────────────────

def _pipeline_key(pipeline_id: str) -> str:
    return f"pipeline:{pipeline_id}"

def _events_key(pipeline_id: str) -> str:
    return f"pipeline:{pipeline_id}:events"

def _user_index_key(user_id: str) -> str:
    return f"pipeline:user:{user_id}:jobs"


# ── Schemas ───────────────────────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    input_type: str          = Field("log", description="'url' or 'log'")
    server_url: Optional[str] = Field(None, description="Cloud/Vercel/Render URL")
    raw_log:    Optional[str] = Field(None, description="Pasted log text")
    repo_url:   Optional[str] = Field(None, description="GitHub repo to refactor (optional)")
    branch:     str           = Field("main", description="Git branch")
    service:    Optional[str] = Field(None, description="Service label override")

    @field_validator("input_type")
    @classmethod
    def _validate_input_type(cls, v: str) -> str:
        if v not in ("url", "log"):
            raise ValueError("input_type must be 'url' or 'log'")
        return v

    @field_validator("server_url", "raw_log", mode="before")
    @classmethod
    def _passthrough(cls, v: Any) -> Any:
        return v


class PipelineRunResponse(BaseModel):
    pipeline_id: str
    message:     str
    status:      str = "queued"
    stream_url:  str


class PipelineStateResponse(BaseModel):
    pipeline_id:   str
    status:        str
    current_stage: Optional[str]  = None
    stages:        dict           = Field(default_factory=dict)
    service:       Optional[str]  = None
    error:         Optional[str]  = None
    started_at:    Optional[str]  = None
    completed_at:  Optional[str]  = None
    failed_at:     Optional[str]  = None


class PipelineHistoryResponse(BaseModel):
    pipelines: list[PipelineStateResponse]
    total:     int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_redis(request: Request) -> aioredis.Redis:
    pool = getattr(request.app.state, "redis_pool", None)
    if not pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not available",
        )
    return aioredis.Redis(connection_pool=pool)


async def _read_pipeline(redis: aioredis.Redis, pipeline_id: str) -> dict:
    raw = await redis.get(_pipeline_key(pipeline_id))
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline '{pipeline_id}' not found",
        )
    return json.loads(raw)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ── Submit ────────────────────────────────────────────────────────────────────

@router.post(
    "/run",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an end-to-end autonomous pipeline run",
)
async def run_pipeline(
    body:         PipelineRunRequest,
    request:      Request,
    current_user: User = Depends(get_current_user),
):
    """
    Accepts a cloud server URL or raw log text, then kicks off the full
    autonomous pipeline:

        SRE Monitor → Testing → Code Refactor → Testing (verify) → SRE Remediate

    Returns immediately with a pipeline_id.
    Stream live events at GET /agents/pipeline/stream/{pipeline_id}.
    """
    if not body.server_url and not body.raw_log:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either server_url or raw_log",
        )

    redis       = _get_redis(request)
    pipeline_id = f"pipe_{uuid.uuid4().hex[:12]}"

    initial_state: dict = {
        "pipeline_id":   pipeline_id,
        "status":        "queued",
        "current_stage": None,
        "stages": {
            "sre_monitor":     "pending",
            "testing_initial": "pending",
            "code_refactor":   "pending",
            "testing_verify":  "pending",
            "sre_remediate":   "pending",
        },
        "service":    body.service or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_id":    str(current_user.id),
    }
    await redis.setex(_pipeline_key(pipeline_id), TTL, json.dumps(initial_state))
    await redis.lpush(_user_index_key(str(current_user.id)), pipeline_id)
    await redis.expire(_user_index_key(str(current_user.id)), TTL)

    task_payload = {
        "input_type": body.input_type,
        "server_url": body.server_url or "",
        "raw_log":    body.raw_log    or "",
        "repo_url":   body.repo_url   or "",
        "branch":     body.branch,
        "service":    body.service    or "",
        "user_id":    str(current_user.id),
    }

    try:
        from opsmindai.tasks.pipeline_tasks import task_run_pipeline
        task_run_pipeline.apply_async(
            args=[pipeline_id, task_payload],
            task_id=pipeline_id,
            queue="pipeline",
        )
        logger.info("[pipeline] %s queued via Celery", pipeline_id)
    except Exception as exc:
        logger.warning("Celery unavailable — pipeline will not run: %s", exc)
        initial_state["status"] = "broker_unavailable"
        initial_state["error"]  = str(exc)
        await redis.setex(_pipeline_key(pipeline_id), TTL, json.dumps(initial_state))

    stream_url = f"/api/v1/agents/pipeline/stream/{pipeline_id}"
    return PipelineRunResponse(
        pipeline_id=pipeline_id,
        message=f"Pipeline queued. Stream events at {stream_url}",
        stream_url=stream_url,
    )


# ── Poll ──────────────────────────────────────────────────────────────────────

@router.get(
    "/jobs/{pipeline_id}",
    response_model=PipelineStateResponse,
    summary="Poll pipeline state",
)
async def get_pipeline_state(
    pipeline_id:  str,
    request:      Request,
    current_user: User = Depends(get_current_user),
):
    redis = _get_redis(request)
    state = await _read_pipeline(redis, pipeline_id)
    return PipelineStateResponse(
        **{k: state.get(k) for k in PipelineStateResponse.model_fields}
    )


# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get(
    "/stream/{pipeline_id}",
    summary="SSE stream of pipeline events",
    include_in_schema=True,
)
async def stream_pipeline_events(
    pipeline_id: str,
    request:     Request,
):
    """
    Server-Sent Events stream. Connect with:

        const es = new EventSource('/api/v1/agents/pipeline/stream/<id>');
        es.onmessage = e => console.log(JSON.parse(e.data));

    Each message is a JSON object:
        { timestamp, stage, status, message, details }
    Special messages:
        { type: "state", data: <PipelineState> }   — initial full state
        { type: "done",  status: "completed"|"failed" }  — terminal
        { type: "error", message: "..." }           — stream error
    """
    redis = _get_redis(request)

    async def _event_generator() -> AsyncGenerator[str, None]:
        sent_count = 0

        # Send initial state immediately
        try:
            raw = await redis.get(_pipeline_key(pipeline_id))
            if raw:
                yield _sse({"type": "state", "data": json.loads(raw)})
        except Exception:
            pass

        while True:
            if await request.is_disconnected():
                break

            try:
                # Events are LPUSH'd (newest first) — reverse to chronological
                all_raw = await redis.lrange(_events_key(pipeline_id), 0, -1)
                all_events = list(reversed(all_raw or []))

                for raw_ev in all_events[sent_count:]:
                    try:
                        yield _sse(json.loads(raw_ev))
                        sent_count += 1
                    except Exception:
                        continue

                # Check terminal state
                raw_state = await redis.get(_pipeline_key(pipeline_id))
                if raw_state:
                    state = json.loads(raw_state)
                    if state.get("status") in ("completed", "failed"):
                        yield _sse({"type": "done", "status": state["status"]})
                        break

            except Exception as exc:
                yield _sse({"type": "error", "message": str(exc)})
                break

            await asyncio.sleep(1.0)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── History ───────────────────────────────────────────────────────────────────

@router.get(
    "/history",
    response_model=PipelineHistoryResponse,
    summary="List user's pipeline runs",
)
async def pipeline_history(
    request:      Request,
    limit:        int  = 20,
    current_user: User = Depends(get_current_user),
):
    redis   = _get_redis(request)
    idx_key = _user_index_key(str(current_user.id))
    ids     = await redis.lrange(idx_key, 0, limit - 1) or []

    pipelines: list[PipelineStateResponse] = []
    for pid in ids:
        try:
            state = await _read_pipeline(redis, pid)
            pipelines.append(PipelineStateResponse(
                **{k: state.get(k) for k in PipelineStateResponse.model_fields}
            ))
        except HTTPException:
            continue

    return PipelineHistoryResponse(pipelines=pipelines, total=len(pipelines))
