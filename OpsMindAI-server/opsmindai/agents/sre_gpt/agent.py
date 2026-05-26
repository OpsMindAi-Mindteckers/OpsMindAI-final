"""
opsmindai/agents/sre_gpt/agent.py

SRE-GPT Agent — main entry point.

Orchestrates the incident response lifecycle:
    1. Ingest alert + dedup
    2. RCA (logs + deployment diff + metrics + RAG + LLM)
    3. Confidence gate:
         >= CONFIDENCE_THRESHOLD → auto-remediate
         <  CONFIDENCE_THRESHOLD → page human
    4. Post-resolution: embed in RAG + dispatch refactor for root-cause file

Three Celery-callable phases:
    run_ingest    — quick: ingest + queue RCA task
    run_rca       — slow:  full RCA pipeline
    run_remediate — slow:  execute playbook + verify + escalate
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from opsmindai.agents.sre_gpt.alert_ingester import (
    get_incident,
    ingest as ingest_alert,
)
from opsmindai.agents.sre_gpt.rca_engine import (
    analyze as run_rca_analysis,
    get_rca,
    is_auto_remediable,
)
from opsmindai.agents.sre_gpt.remediation_executor import execute as run_remediation
from opsmindai.schemas.incidents import (
    AlertPayload,
    IncidentStatus,
    Playbook,
    TimelineEvent,
)

logger = logging.getLogger(__name__)


# ── Redis helpers ─────────────────────────────────────────────────────────────

def _incident_key(incident_id: str) -> str:
    return f"incident:{incident_id}"


def _timeline_key(incident_id: str) -> str:
    return f"incident:{incident_id}:timeline"


def _job_key(job_id: str) -> str:
    return f"sre_job:{job_id}"


async def _append_timeline(redis, incident_id: str, event: str, details: dict | None = None) -> None:
    """Append an event to the incident timeline list (Redis LIST)."""
    timeline_event = TimelineEvent(
        timestamp=datetime.now(timezone.utc),
        event=event,
        details=details or {},
    )
    try:
        await redis.lpush(_timeline_key(incident_id), timeline_event.model_dump_json())
        await redis.expire(_timeline_key(incident_id), 86_400)
    except Exception as exc:
        logger.warning("Could not append timeline event: %s", exc)


async def _update_job(redis, job_id: str, updates: dict) -> None:
    """Merge updates into existing SRE job state in Redis."""
    raw = await redis.get(_job_key(job_id))
    if not raw:
        # Fresh state
        state = {}
    else:
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            state = {}
    state.update(updates)
    await redis.setex(_job_key(job_id), 86_400, json.dumps(state, default=str))


async def _index_for_user(redis, job_id: str, user_id: str) -> None:
    """Add to user's SRE job history."""
    if not user_id or user_id == "anonymous":
        return
    key = f"sre:user:{user_id}:jobs"
    try:
        await redis.lpush(key, job_id)
        await redis.expire(key, 86_400 * 30)
    except Exception as exc:
        logger.warning("Could not index SRE job for user: %s", exc)


# ── Phase 1 — Ingest ──────────────────────────────────────────────────────────

async def run_ingest(job_id: str, payload: dict, redis) -> None:
    """
    Phase 1 — Normalise the alert, apply 60s dedup window, persist incident.

    Triggered by:
        POST /api/v1/incidents/ingest
        POST /api/v1/webhooks/{prometheus,pagerduty,loki,grafana}

    payload must contain:
        alert_payload: dict (validated AlertPayload)
        user_id:       str (set to 'webhook' for unauthenticated webhook calls)
    """
    start = time.monotonic()
    user_id = payload.get("user_id", "webhook")

    try:
        # Re-validate the payload (safe — Pydantic does not call out)
        alert_dict = payload.get("alert_payload", {})
        alert_payload = AlertPayload(**alert_dict)

        # Ingest + dedup
        normalised, is_duplicate = await ingest_alert(alert_payload, redis)

        await _update_job(redis, job_id, {
            "job_id":      job_id,
            "phase":       "ingest",
            "status":      "completed",
            "incident_id": normalised.incident_id,
            "deduplicated": is_duplicate,
            "user_id":     user_id,
            "created_at":  datetime.now(timezone.utc).isoformat(),
            "duration_s":  round(time.monotonic() - start, 2),
        })
        await _index_for_user(redis, job_id, user_id)
        await _append_timeline(
            redis, normalised.incident_id,
            "alert_ingested",
            {"source": normalised.source.value, "duplicate": is_duplicate},
        )

        if is_duplicate:
            logger.info(
                "Ingest dedup'd: job=%s incident=%s",
                job_id, normalised.incident_id,
            )
            return

        # Auto-dispatch RCA task for new incidents
        # Skip if called from pipeline (pipeline handles RCA itself inline)
        _skip_dispatch = payload.get("_pipeline_mode", False)
        if not _skip_dispatch:
            try:
                from opsmindai.tasks.sre_tasks import task_run_rca
                rca_job_id = f"rca_{normalised.incident_id}"
                task_run_rca.apply_async(
                    args=[rca_job_id, {
                        "incident_id": normalised.incident_id,
                        "user_id":     user_id,
                    }],
                    task_id=rca_job_id,
                    priority=9,
                )
                logger.info(
                    "Auto-dispatched RCA: job=%s incident=%s",
                    rca_job_id, normalised.incident_id,
                )
            except Exception as exc:
                logger.warning("Could not auto-dispatch RCA task: %s", exc)

    except Exception as exc:
        logger.exception("Ingest failed for job %s", job_id)
        await _update_job(redis, job_id, {
            "job_id":     job_id,
            "phase":      "ingest",
            "status":     "failed",
            "error":      str(exc),
            "user_id":    user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "duration_s": round(time.monotonic() - start, 2),
        })
        raise


# ── Phase 2 — RCA ─────────────────────────────────────────────────────────────

async def run_rca(job_id: str, payload: dict, redis) -> None:
    """
    Phase 2 — Run root-cause analysis.

    payload must contain:
        incident_id: str
        user_id:     str
    """
    start = time.monotonic()
    incident_id = payload.get("incident_id")
    user_id     = payload.get("user_id", "system")

    if not incident_id:
        raise ValueError("payload.incident_id is required")

    await _update_job(redis, job_id, {
        "job_id":      job_id,
        "phase":       "rca",
        "status":      "running",
        "incident_id": incident_id,
        "user_id":     user_id,
        "created_at":  datetime.now(timezone.utc).isoformat(),
    })

    try:
        rca = await run_rca_analysis(incident_id, redis)

        await _append_timeline(
            redis, incident_id,
            "rca_completed",
            {
                "confidence":  rca.confidence,
                "root_cause":  rca.root_cause[:200],
                "rag_matched": rca.rag_matched,
            },
        )

        duration = round(time.monotonic() - start, 2)
        await _update_job(redis, job_id, {
            "status":      "completed",
            "confidence":  rca.confidence,
            "root_cause":  rca.root_cause[:500],
            "auto_remediable": is_auto_remediable(rca),
            "completed_at":   datetime.now(timezone.utc).isoformat(),
            "duration_s":     duration,
        })

        logger.info(
            "RCA done: job=%s incident=%s confidence=%.2f duration=%.2fs",
            job_id, incident_id, rca.confidence, duration,
        )

        # FR-47: confidence-based dispatch
        if is_auto_remediable(rca):
            try:
                from opsmindai.tasks.sre_tasks import task_run_remediate
                remediate_job_id = f"rem_{incident_id}"
                task_run_remediate.apply_async(
                    args=[remediate_job_id, {
                        "incident_id": incident_id,
                        "playbook":    Playbook.AUTO.value,
                        "user_id":     user_id,
                    }],
                    task_id=remediate_job_id,
                    priority=9,
                )
                logger.info(
                    "Auto-remediation dispatched: incident=%s confidence=%.2f",
                    incident_id, rca.confidence,
                )
                await _append_timeline(
                    redis, incident_id,
                    "auto_remediation_dispatched",
                    {"confidence": rca.confidence},
                )
            except Exception as exc:
                logger.exception("Could not dispatch remediation: %s", exc)
        else:
            # Page human — handled by remediation_executor's PagerDuty integration
            logger.warning(
                "RCA confidence below threshold (%.2f) — paging human for incident %s",
                rca.confidence, incident_id,
            )
            await _append_timeline(
                redis, incident_id,
                "human_paged",
                {"confidence": rca.confidence, "reason": "below auto-remediation threshold"},
            )
            try:
                from opsmindai.agents.sre_gpt.remediation_executor import _page_pagerduty
                await _page_pagerduty(
                    incident_id,
                    f"Low-confidence RCA ({rca.confidence:.2f}): {rca.root_cause[:200]}",
                )
            except Exception as exc:
                logger.warning("PagerDuty page failed: %s", exc)

    except Exception as exc:
        logger.exception("RCA failed for job %s", job_id)
        await _update_job(redis, job_id, {
            "status":       "failed",
            "error":        str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(time.monotonic() - start, 2),
        })
        await _append_timeline(redis, incident_id, "rca_failed", {"error": str(exc)})
        raise


# ── Phase 3 — Remediate ──────────────────────────────────────────────────────

async def run_remediate(job_id: str, payload: dict, redis) -> None:
    """
    Phase 3 — Execute remediation playbook and verify normalisation.

    payload must contain:
        incident_id: str
        playbook:    str  ('auto' | 'rollback' | 'restart' | ...)
        user_id:     str
    """
    start = time.monotonic()
    incident_id = payload.get("incident_id")
    playbook_str = payload.get("playbook", Playbook.AUTO.value)
    user_id = payload.get("user_id", "system")

    if not incident_id:
        raise ValueError("payload.incident_id is required")

    try:
        playbook = Playbook(playbook_str)
    except ValueError:
        raise ValueError(f"Invalid playbook: {playbook_str}")

    await _update_job(redis, job_id, {
        "job_id":      job_id,
        "phase":       "remediate",
        "status":      "running",
        "incident_id": incident_id,
        "playbook":    playbook.value,
        "user_id":     user_id,
        "created_at":  datetime.now(timezone.utc).isoformat(),
    })

    await _append_timeline(
        redis, incident_id,
        "remediation_started",
        {"playbook": playbook.value, "user_id": user_id},
    )

    try:
        result = await run_remediation(incident_id, redis, playbook=playbook)

        duration = round(time.monotonic() - start, 2)
        await _update_job(redis, job_id, {
            "status":         "completed",
            "remediation_status": result.status.value,
            "actions_taken":  result.actions_taken,
            "normalised":     result.normalised,
            "playbook_used":  result.playbook_used.value if result.playbook_used else None,
            "completed_at":   datetime.now(timezone.utc).isoformat(),
            "duration_s":     duration,
        })

        await _append_timeline(
            redis, incident_id,
            "remediation_completed",
            {
                "status":     result.status.value,
                "normalised": result.normalised,
                "playbook":   result.playbook_used.value if result.playbook_used else None,
            },
        )

        logger.info(
            "Remediation done: job=%s incident=%s status=%s normalised=%s duration=%.2fs",
            job_id, incident_id, result.status.value, result.normalised, duration,
        )

    except Exception as exc:
        logger.exception("Remediation failed for job %s", job_id)
        await _update_job(redis, job_id, {
            "status":       "failed",
            "error":        str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(time.monotonic() - start, 2),
        })
        await _append_timeline(redis, incident_id, "remediation_failed", {"error": str(exc)})
        raise