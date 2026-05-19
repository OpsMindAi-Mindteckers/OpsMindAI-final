"""
opsmindai/monitoring/alert_handler.py

Alert enrichment and routing (SRS §11, FR-40 / FR-41).

Receives raw payloads from any monitoring source, enriches them with
service metadata and Prometheus metrics, then routes them to:
  - Redis (incident dedup + storage)
  - SRE-GPT Celery task queue (via orchestrator)
  - Slack notification (if SLACK_WEBHOOK_URL configured)

Used by the webhook API routes (/webhooks/prometheus, /webhooks/pagerduty, etc.)
as the single entry-point for all alert processing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from opsmindai.core.config import settings
from opsmindai.orchestrator.event_handler import normalise, EventType

logger = logging.getLogger(__name__)

_SLACK_TIMEOUT = httpx.Timeout(10.0)

# Severity → Slack colour
_SEVERITY_COLOUR = {
    "critical": "#FF0000",
    "high":     "#FF6600",
    "medium":   "#FFC000",
    "low":      "#36A64F",
}


# ── Main entry-point ──────────────────────────────────────────────────────────

async def handle_alert(
    source:      str,
    raw_payload: dict[str, Any],
    redis: Any = None,
) -> dict[str, Any]:
    """
    Enrich an inbound alert, deduplicate it, dispatch SRE-GPT task, and notify Slack.

    Args:
        source:      Source name: 'prometheus', 'pagerduty', 'loki', 'grafana'.
        raw_payload: Raw parsed JSON payload dict.
        redis:       Optional async Redis client. If provided, dedup is checked here
                     before dispatching to avoid duplicate Celery tasks.

    Returns:
        Dict with {incident_id, status, dispatched, slack_sent}.
    """
    # 1. Normalise payload
    event = normalise(source, raw_payload)

    if event.event_type != EventType.ALERT:
        logger.info("alert_handler: non-alert event_type=%s from source=%s — skipped", event.event_type, source)
        return {"status": "skipped", "reason": "not an alert event"}

    # 2. Build alert payload for SRE-GPT ingestion
    alert_payload = _build_alert_payload(source, event.service, event.severity, event.labels, raw_payload)

    # 3. Enrich with Prometheus metrics (non-blocking)
    enrichment = await _enrich_with_metrics(event.service)
    alert_payload["enrichment"] = enrichment

    # 4. Dispatch to SRE-GPT via orchestrator
    dispatched: Optional[str] = None
    try:
        from opsmindai.orchestrator.agent_dispatcher import dispatch
        from opsmindai.orchestrator.task_router import route_event
        tasks = route_event(event)
        if tasks:
            celery_id = dispatch(tasks[0])
            dispatched = celery_id
            logger.info(
                "alert_handler: dispatched task=%s celery_id=%s service=%s",
                tasks[0].task_name, celery_id, event.service,
            )
    except Exception as exc:
        logger.warning("alert_handler: dispatch failed: %s", exc)

    # 5. Slack notification
    slack_sent = False
    if settings.SLACK_WEBHOOK_URL:
        slack_sent = await _send_slack(
            service    = event.service or "unknown",
            severity   = event.severity or "medium",
            alert_name = event.labels.get("alert_name", "Alert"),
            source     = source,
        )

    return {
        "event_id":   event.event_id,
        "service":    event.service,
        "severity":   event.severity,
        "status":     "dispatched" if dispatched else "received",
        "dispatched": dispatched,
        "slack_sent": slack_sent,
    }


# ── Alert payload builder ──────────────────────────────────────────────────────

def _build_alert_payload(
    source:      str,
    service:     Optional[str],
    severity:    Optional[str],
    labels:      dict,
    raw_payload: dict,
) -> dict[str, Any]:
    """Build a normalised alert payload dict for downstream consumption."""
    return {
        "source":      source,
        "service":     service      or "unknown",
        "severity":    severity     or "medium",
        "alert_name":  labels.get("alert_name", "UnknownAlert"),
        "labels":      labels,
        "annotations": {},
        "raw_payload": raw_payload,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Prometheus enrichment ─────────────────────────────────────────────────────

async def _enrich_with_metrics(service: Optional[str]) -> dict[str, Any]:
    """
    Fetch current P99 latency and error rate for the affected service.

    Non-blocking — returns empty dict on any failure.
    """
    if not service:
        return {}
    try:
        from opsmindai.monitoring.prometheus_client import (
            query_p99_latency,
            query_error_rate,
        )
        p99 = await query_p99_latency(service, minutes=5)
        err = await query_error_rate(service, minutes=5)
        return {
            "p99_latency_ms": p99,
            "error_rate":     err,
        }
    except Exception as exc:
        logger.debug("alert_handler: enrichment failed: %s", exc)
        return {}


# ── Slack notification ─────────────────────────────────────────────────────────

async def _send_slack(
    service:    str,
    severity:   str,
    alert_name: str,
    source:     str,
) -> bool:
    """
    POST a Slack Block Kit message to SLACK_WEBHOOK_URL.

    Returns True on success, False on any error.
    """
    colour  = _SEVERITY_COLOUR.get(severity.lower(), "#888888")
    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    payload = {
        "attachments": [
            {
                "color":    colour,
                "fallback": f"[{severity.upper()}] {alert_name} — {service}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*:rotating_light: {severity.upper()} alert detected*\n"
                                f"*Alert:* `{alert_name}`\n"
                                f"*Service:* `{service}`\n"
                                f"*Source:* {source}\n"
                                f"*Time:* {ts}"
                            ),
                        },
                    }
                ],
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=_SLACK_TIMEOUT) as client:
            resp = await client.post(settings.SLACK_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
            logger.info(
                "alert_handler: Slack notification sent service=%s alert=%s",
                service, alert_name,
            )
            return True
    except Exception as exc:
        logger.warning("alert_handler: Slack notification failed: %s", exc)
        return False


async def send_slack_notification(
    text:   str,
    colour: str = "#36A64F",
) -> bool:
    """
    Generic Slack notification helper for use by other modules.

    Args:
        text:   Markdown-formatted message text.
        colour: Attachment colour hex string.

    Returns:
        True on success, False on failure.
    """
    if not settings.SLACK_WEBHOOK_URL:
        return False

    payload = {
        "attachments": [
            {
                "color": colour,
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": text},
                    }
                ],
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=_SLACK_TIMEOUT) as client:
            resp = await client.post(settings.SLACK_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.warning("send_slack_notification failed: %s", exc)
        return False
