"""
opsmindai/api/v1/incidents.py

SRE-GPT incident response REST API — implements SRS §9.6.

Endpoints:
  POST   /incidents/ingest                → ingest alert (HMAC-protected webhook)
  POST   /incidents/analyze               → manually trigger RCA on queued incident
  POST   /incidents/remediate             → execute remediation playbook
  POST   /incidents/correlate             → correlate incidents by shared root cause
  GET    /incidents/history               → list incidents with filters
  GET    /incidents/{incident_id}         → full detail (alert + RCA + timeline)
  GET    /incidents/{incident_id}/timeline → timeline only
  PATCH  /incidents/{id}/status           → update status manually

Auth model:
  - /ingest      → HMAC signature (webhook source)
  - everything else → JWT via get_current_user
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis
from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)
from pydantic import BaseModel, Field

from opsmindai.api.v1.auth import get_current_user
from opsmindai.core.redis import get_redis
from opsmindai.db.models import User
from opsmindai.schemas.incidents import (
    AlertPayload,
    AlertSource,
    IncidentDetail,
    IncidentIngestResponse,
    IncidentSeverity,
    IncidentStatus,
    NormalisedAlert,
    Playbook,
    RCAResult,
    RemediateRequest,
    RemediateResponse,
    TimelineEvent,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/incidents", tags=["incidents"])


# ── Constants ─────────────────────────────────────────────────────────────────

_INCIDENT_TTL = 86_400
_HISTORY_LIMIT = 100


# ── Redis key helpers ─────────────────────────────────────────────────────────

def _incident_key(incident_id: str) -> str:
    return f"incident:{incident_id}"


def _rca_key(incident_id: str) -> str:
    return f"incident:{incident_id}:rca"


def _status_key(incident_id: str) -> str:
    return f"incident:{incident_id}:status"


def _timeline_key(incident_id: str) -> str:
    return f"incident:{incident_id}:timeline"


def _history_key() -> str:
    return "incident:history"


# ── HMAC verification (for /ingest webhook) ──────────────────────────────────

def _verify_hmac(
    raw_body: bytes,
    signature: Optional[str],
    secret: str,
) -> bool:
    """
    Verify an HMAC-SHA256 signature header against the request body.

    Accepts headers in either of these formats:
        sha256=<hex>
        <hex>
    """
    if not signature or not secret:
        return False

    sig = signature.strip()
    if sig.startswith("sha256="):
        sig = sig[len("sha256="):]

    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


async def verify_webhook_signature(
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature-256"),
    x_hub_signature: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
) -> bytes:
    """
    Dependency that verifies HMAC signature for incident webhooks.
    Returns the raw body so handlers don't have to read it twice.
    """
    secret = os.environ.get("INCIDENT_WEBHOOK_SECRET", "")
    if not secret:
        # If no secret configured, refuse webhook entirely in production.
        # Allow only when DEBUG=1 explicitly set.
        if os.environ.get("DEBUG") != "1":
            raise HTTPException(
                status_code=503,
                detail="Webhook signature verification is not configured",
            )
        return await request.body()

    raw = await request.body()
    candidate = x_signature or x_hub_signature
    if not _verify_hmac(raw, candidate, secret):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )
    return raw


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _load_incident(redis: aioredis.Redis, incident_id: str) -> NormalisedAlert:
    raw = await redis.get(_incident_key(incident_id))
    if not raw:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return NormalisedAlert.model_validate_json(raw)


async def _load_rca(redis: aioredis.Redis, incident_id: str) -> Optional[RCAResult]:
    raw = await redis.get(_rca_key(incident_id))
    if not raw:
        return None
    return RCAResult.model_validate_json(raw)


async def _load_status(redis: aioredis.Redis, incident_id: str) -> tuple[IncidentStatus, Optional[datetime]]:
    raw = await redis.get(_status_key(incident_id))
    if not raw:
        return IncidentStatus.OPEN, None
    try:
        data = json.loads(raw)
        status_val = IncidentStatus(data.get("status", "open"))
        resolved = data.get("resolved_at")
        resolved_dt = datetime.fromisoformat(resolved) if resolved else None
        return status_val, resolved_dt
    except (json.JSONDecodeError, ValueError):
        return IncidentStatus.OPEN, None


async def _load_timeline(redis: aioredis.Redis, incident_id: str) -> list[TimelineEvent]:
    raws = await redis.lrange(_timeline_key(incident_id), 0, -1)
    events: list[TimelineEvent] = []
    for raw in raws or []:
        try:
            events.append(TimelineEvent.model_validate_json(raw))
        except Exception:
            continue
    # newest -> oldest as stored, return oldest -> newest
    events.reverse()
    return events


async def _index_incident(redis: aioredis.Redis, incident_id: str) -> None:
    """Add to the global incident history list (newest first)."""
    try:
        await redis.lpush(_history_key(), incident_id)
        await redis.expire(_history_key(), _INCIDENT_TTL * 30)
    except Exception as exc:
        logger.warning("Could not index incident: %s", exc)


# ── Local response schemas ────────────────────────────────────────────────────

class IncidentSummary(BaseModel):
    incident_id:  str
    service:      str
    severity:     IncidentSeverity
    status:       IncidentStatus
    alert_name:   str
    detected_at:  datetime
    resolved_at:  Optional[datetime] = None


class IncidentHistoryResponse(BaseModel):
    incidents: list[IncidentSummary]
    total:     int


class CorrelateRequest(BaseModel):
    incident_ids: list[str] = Field(..., min_length=2, max_length=20)


class CorrelateResponse(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)
    shared_cause: Optional[str] = None
    matched_pairs: list[tuple[str, str]] = Field(default_factory=list)


class StatusUpdateRequest(BaseModel):
    status: IncidentStatus
    notes:  Optional[str] = None


# ── 1. POST /ingest (HMAC) ───────────────────────────────────────────────────

@router.post(
    "/ingest",
    response_model=IncidentIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest alert from monitoring system (HMAC-protected)",
)
async def ingest_alert(
    request: Request,
    raw_body: bytes = Depends(verify_webhook_signature),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Webhook endpoint for Prometheus / PagerDuty / Loki / Grafana alerts.

    Workflow:
      1. Verify HMAC (via dependency)
      2. Parse body as AlertPayload
      3. Dispatch task_run_ingest to Celery
      4. Return 202 with incident_id

    The actual normalisation + dedup happens in the Celery worker so this
    endpoint returns within ~50ms (FR + SRS §10.2: <500ms).
    """
    try:
        body = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        alert_payload = AlertPayload(**body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid alert payload: {exc}")

    # Synchronously ingest so we can return the real incident_id immediately.
    # Heavy work (RCA) is async via Celery dispatch inside run_ingest.
    from opsmindai.agents.sre_gpt.alert_ingester import ingest as ingest_fn
    try:
        normalised, is_duplicate = await ingest_fn(alert_payload, redis)
    except Exception as exc:
        logger.exception("Alert ingest failed")
        raise HTTPException(status_code=500, detail=f"Ingest failed: {exc}")

    # Index for history listing
    if not is_duplicate:
        await _index_incident(redis, normalised.incident_id)

    # Dispatch RCA task (only for new incidents)
    if not is_duplicate:
        try:
            from opsmindai.tasks.sre_tasks import task_run_rca
            rca_job_id = f"rca_{normalised.incident_id}"
            task_run_rca.apply_async(
                args=[rca_job_id, {
                    "incident_id": normalised.incident_id,
                    "user_id":     "webhook",
                }],
                task_id=rca_job_id,
                priority=9,
            )
        except Exception as exc:
            logger.warning("Could not dispatch RCA task: %s", exc)

    return IncidentIngestResponse(
        incident_id=normalised.incident_id,
        status=(IncidentStatus.DUPLICATE_SUPPRESSED if is_duplicate else IncidentStatus.QUEUED),
        deduplicated=is_duplicate,
    )


# ── 2. POST /analyze (JWT) ───────────────────────────────────────────────────

class AnalyzeRequestBody(BaseModel):
    incident_id: str = Field(..., min_length=1)


@router.post(
    "/analyze",
    response_model=RCAResult,
    summary="Manually trigger RCA on a queued incident",
)
async def analyze_incident(
    body: AnalyzeRequestBody,
    user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Run RCA synchronously on a previously-ingested incident and return the result.

    This is a debug / manual-override endpoint. The normal flow ingests
    via webhook and runs RCA automatically.
    """
    # Verify incident exists
    await _load_incident(redis, body.incident_id)

    from opsmindai.agents.sre_gpt.rca_engine import analyze
    try:
        rca = await analyze(body.incident_id, redis)
    except Exception as exc:
        logger.exception("RCA failed for incident %s", body.incident_id)
        raise HTTPException(status_code=500, detail=f"RCA failed: {exc}")

    logger.info(
        "Manual RCA: user=%s incident=%s confidence=%.2f",
        user.id, body.incident_id, rca.confidence,
    )
    return rca


# ── 3. POST /remediate (JWT) ─────────────────────────────────────────────────

@router.post(
    "/remediate",
    response_model=RemediateResponse,
    summary="Execute remediation playbook against an incident",
)
async def remediate_incident(
    body: RemediateRequest,
    user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Run a remediation playbook against an incident.

    Synchronous: blocks until the playbook completes and metrics are
    verified (up to ~90s total). For long-running operations, use the
    Celery task directly.
    """
    await _load_incident(redis, body.incident_id)

    from opsmindai.agents.sre_gpt.remediation_executor import execute
    try:
        result = await execute(body.incident_id, redis, playbook=body.playbook)
    except Exception as exc:
        logger.exception("Remediation failed")
        raise HTTPException(status_code=500, detail=f"Remediation failed: {exc}")

    logger.info(
        "Manual remediation: user=%s incident=%s playbook=%s status=%s",
        user.id, body.incident_id, body.playbook.value, result.status.value,
    )
    return result


# ── 4. POST /correlate (JWT) ─────────────────────────────────────────────────

@router.post(
    "/correlate",
    response_model=CorrelateResponse,
    summary="Correlate incidents by shared root cause",
)
async def correlate_incidents(
    body: CorrelateRequest,
    _user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Compute a similarity score between incidents based on root_cause text
    and shared affected_services. Used to detect cascade failures.
    """
    rcas: list[tuple[str, RCAResult]] = []
    for inc_id in body.incident_ids:
        rca = await _load_rca(redis, inc_id)
        if rca:
            rcas.append((inc_id, rca))

    if len(rcas) < 2:
        return CorrelateResponse(
            score=0.0,
            shared_cause=None,
            matched_pairs=[],
        )

    # Simple Jaccard over (lowercase tokens of root_cause + affected_services)
    def tokens(rca: RCAResult) -> set[str]:
        text = (rca.root_cause or "").lower()
        words = {w for w in text.split() if len(w) > 3}
        words.update(s.lower() for s in rca.affected_services)
        return words

    pairs: list[tuple[str, str]] = []
    overlap_scores: list[float] = []
    base_id, base_rca = rcas[0]
    base_tokens = tokens(base_rca)

    for other_id, other_rca in rcas[1:]:
        other_tokens = tokens(other_rca)
        if not base_tokens or not other_tokens:
            continue
        union = base_tokens | other_tokens
        intersection = base_tokens & other_tokens
        jaccard = len(intersection) / len(union) if union else 0.0
        overlap_scores.append(jaccard)
        if jaccard >= 0.4:
            pairs.append((base_id, other_id))

    score = max(overlap_scores) if overlap_scores else 0.0
    shared_cause = base_rca.root_cause if score >= 0.4 else None

    return CorrelateResponse(
        score=round(score, 3),
        shared_cause=shared_cause,
        matched_pairs=pairs,
    )


# ── 5. GET /history (JWT) ────────────────────────────────────────────────────

@router.get(
    "/history",
    response_model=IncidentHistoryResponse,
    summary="List incidents",
)
async def list_incidents(
    service:   Optional[str] = Query(None),
    severity:  Optional[IncidentSeverity] = Query(None),
    status_q:  Optional[IncidentStatus] = Query(None, alias="status"),
    date_from: Optional[datetime] = Query(None),
    limit:     int = Query(20, ge=1, le=_HISTORY_LIMIT),
    _user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    List incidents in reverse-chronological order with optional filters.

    Filters apply in-memory after loading so should be combined with `limit`
    to avoid scanning the entire 30-day history.
    """
    raw_ids = await redis.lrange(_history_key(), 0, _HISTORY_LIMIT - 1)
    summaries: list[IncidentSummary] = []

    for inc_id in raw_ids or []:
        try:
            alert = await _load_incident(redis, inc_id)
        except HTTPException:
            continue   # incident TTL expired, skip
        st, resolved_at = await _load_status(redis, inc_id)

        if service and alert.service != service:
            continue
        if severity and alert.severity != severity:
            continue
        if status_q and st != status_q:
            continue
        if date_from and alert.detected_at < date_from:
            continue

        summaries.append(IncidentSummary(
            incident_id=alert.incident_id,
            service=alert.service,
            severity=alert.severity,
            status=st,
            alert_name=alert.alert_name,
            detected_at=alert.detected_at,
            resolved_at=resolved_at,
        ))

        if len(summaries) >= limit:
            break

    return IncidentHistoryResponse(incidents=summaries, total=len(summaries))


# ── 6. GET /{incident_id} (JWT) ──────────────────────────────────────────────

@router.get(
    "/{incident_id}",
    response_model=IncidentDetail,
    summary="Get full incident detail",
)
async def get_incident_detail(
    incident_id: str = Path(..., min_length=1),
    _user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Return alert + RCA + timeline + status for an incident."""
    alert = await _load_incident(redis, incident_id)
    rca = await _load_rca(redis, incident_id)
    st, resolved_at = await _load_status(redis, incident_id)
    timeline = await _load_timeline(redis, incident_id)

    return IncidentDetail(
        incident_id=alert.incident_id,
        service=alert.service,
        severity=alert.severity,
        status=st,
        detected_at=alert.detected_at,
        resolved_at=resolved_at,
        rca=rca,
        timeline=timeline,
        alert=alert,
    )


# ── 7. GET /{id}/timeline (JWT) ──────────────────────────────────────────────

@router.get(
    "/{incident_id}/timeline",
    response_model=list[TimelineEvent],
    summary="Get incident timeline",
)
async def get_incident_timeline(
    incident_id: str = Path(..., min_length=1),
    _user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Return timestamped event log for an incident."""
    await _load_incident(redis, incident_id)   # 404 if not found
    return await _load_timeline(redis, incident_id)


# ── 8. PATCH /{id}/status (JWT) ──────────────────────────────────────────────

@router.patch(
    "/{incident_id}/status",
    response_model=IncidentDetail,
    summary="Manually update incident status",
)
async def update_incident_status(
    incident_id: str = Path(..., min_length=1),
    body: StatusUpdateRequest = Body(...),
    user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Manually update incident status (e.g. mark as false_positive).

    Appends a timeline event recording who made the change.
    """
    alert = await _load_incident(redis, incident_id)

    # Persist new status
    payload: dict[str, Any] = {
        "status":     body.status.value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user.id,
    }
    if body.status == IncidentStatus.RESOLVED:
        payload["resolved_at"] = datetime.now(timezone.utc).isoformat()

    await redis.setex(_status_key(incident_id), _INCIDENT_TTL, json.dumps(payload))

    # Timeline event
    event = TimelineEvent(
        timestamp=datetime.now(timezone.utc),
        event="status_updated_manually",
        details={
            "new_status": body.status.value,
            "updated_by": user.id,
            "notes":      body.notes,
        },
    )
    await redis.lpush(_timeline_key(incident_id), event.model_dump_json())
    await redis.expire(_timeline_key(incident_id), _INCIDENT_TTL)

    logger.info("Status updated: incident=%s by=%s status=%s",
                incident_id, user.id, body.status.value)

    # Return refreshed detail
    rca = await _load_rca(redis, incident_id)
    timeline = await _load_timeline(redis, incident_id)
    st, resolved_at = await _load_status(redis, incident_id)
    return IncidentDetail(
        incident_id=alert.incident_id,
        service=alert.service,
        severity=alert.severity,
        status=st,
        detected_at=alert.detected_at,
        resolved_at=resolved_at,
        rca=rca,
        timeline=timeline,
        alert=alert,
    )