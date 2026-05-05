"""
opsmindai/agents/sre_gpt/alert_ingester.py

Phase P5 — SRS §9.1.

Ingests raw alert payloads from Prometheus, PagerDuty, Loki, or Grafana,
normalises them into a canonical NormalisedAlert, and applies a 60-second
fingerprint-based deduplication window via Redis.

Supports both async (FastAPI) and sync (Celery) Redis adapters.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from opsmindai.schemas.incidents import (
    AlertPayload,
    AlertSource,
    IncidentSeverity,
    IncidentStatus,
    NormalisedAlert,
)

logger = logging.getLogger(__name__)

# ── Redis keys / TTLs ─────────────────────────────────────────────────────────

_DEDUP_TTL_SEC      = 60          # FR-42: 60s dedup window
_INCIDENT_TTL_SEC   = 86_400      # 24h
_DEDUP_KEY_PREFIX   = "incident:dedup:"
_INCIDENT_KEY_PREFIX = "incident:"


def _dedup_key(fingerprint: str) -> str:
    return f"{_DEDUP_KEY_PREFIX}{fingerprint}"


def _incident_key(incident_id: str) -> str:
    return f"{_INCIDENT_KEY_PREFIX}{incident_id}"


# ── Source-specific extractors ────────────────────────────────────────────────

def _extract_prometheus(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Alertmanager v4 payload shape:
        {"alerts": [{"labels": {...}, "annotations": {...}, "status": ...}], ...}
    We take the first alert in the batch — caller can iterate for multi-alerts.
    """
    alerts = raw.get("alerts", [])
    if not alerts:
        return {}
    a = alerts[0]
    labels = a.get("labels", {}) or {}
    annotations = a.get("annotations", {}) or {}
    return {
        "alert_name":  labels.get("alertname", "unknown"),
        "service":     labels.get("service") or labels.get("job") or "unknown",
        "severity":    (labels.get("severity") or "medium").lower(),
        "labels":      labels,
        "annotations": annotations,
        "namespace":   labels.get("namespace"),
    }


def _extract_pagerduty(raw: dict[str, Any]) -> dict[str, Any]:
    """
    PagerDuty webhook v3:
        {"messages": [{"event": {"data": {...}}}]}  OR  {"event": {"data": {...}}}
    """
    event = raw.get("event") or (raw.get("messages", [{}])[0].get("event", {}))
    data = event.get("data", {}) or {}
    custom = data.get("custom_details", {}) or {}
    return {
        "alert_name":  data.get("title") or data.get("summary", "unknown"),
        "service":     (data.get("service", {}) or {}).get("summary")
                       or custom.get("service", "unknown"),
        "severity":    (data.get("severity") or "medium").lower(),
        "labels":      custom,
        "annotations": {"description": data.get("summary", "")},
        "namespace":   custom.get("namespace"),
    }


def _extract_loki(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Loki Alertmanager payload (similar to Prometheus, with `alerts` array).
    """
    return _extract_prometheus(raw)


def _extract_grafana(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Grafana unified alerting webhook:
        {"alerts": [{"labels": {...}, "annotations": {...}}], "commonLabels": {...}}
    """
    alerts = raw.get("alerts", [])
    if not alerts:
        common_labels = raw.get("commonLabels", {}) or {}
        return {
            "alert_name":  raw.get("title", "unknown"),
            "service":     common_labels.get("service", "unknown"),
            "severity":    (common_labels.get("severity") or "medium").lower(),
            "labels":      common_labels,
            "annotations": raw.get("commonAnnotations", {}),
            "namespace":   common_labels.get("namespace"),
        }
    a = alerts[0]
    labels = a.get("labels", {}) or {}
    return {
        "alert_name":  labels.get("alertname") or a.get("ruleName", "unknown"),
        "service":     labels.get("service") or labels.get("job", "unknown"),
        "severity":    (labels.get("severity") or "medium").lower(),
        "labels":      labels,
        "annotations": a.get("annotations", {}) or {},
        "namespace":   labels.get("namespace"),
    }


_EXTRACTORS = {
    AlertSource.PROMETHEUS: _extract_prometheus,
    AlertSource.PAGERDUTY:  _extract_pagerduty,
    AlertSource.LOKI:       _extract_loki,
    AlertSource.GRAFANA:    _extract_grafana,
}


# ── Source autodetection (optional) ──────────────────────────────────────────

def detect_source(raw: dict[str, Any]) -> AlertSource:
    """Detect source from payload shape. Falls back to PROMETHEUS."""
    if "messages" in raw or (raw.get("event") or {}).get("event_type"):
        return AlertSource.PAGERDUTY
    if "ruleName" in raw or "commonLabels" in raw:
        return AlertSource.GRAFANA
    if "alerts" in raw:
        # Both Prometheus and Loki use the same shape; default to Prometheus
        return AlertSource.PROMETHEUS
    return AlertSource.PROMETHEUS


# ── Fingerprint ───────────────────────────────────────────────────────────────

def compute_fingerprint(service: str, alert_name: str, labels: dict) -> str:
    """SHA-256 fingerprint over (service, alert_name, sorted labels)."""
    canonical = json.dumps(
        {"service": service, "alert": alert_name, "labels": labels},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


# ── Severity sanitisation ────────────────────────────────────────────────────

_SEVERITY_ALIASES = {
    "p1": "critical", "p2": "high", "p3": "medium", "p4": "low",
    "warning": "medium", "warn": "medium", "info": "low",
    "error": "high", "fatal": "critical",
}


def _normalise_severity(raw: str) -> IncidentSeverity:
    s = (raw or "medium").lower().strip()
    s = _SEVERITY_ALIASES.get(s, s)
    try:
        return IncidentSeverity(s)
    except ValueError:
        return IncidentSeverity.MEDIUM


# ── Public API ────────────────────────────────────────────────────────────────

async def ingest(
    payload: AlertPayload,
    redis,
) -> tuple[NormalisedAlert, bool]:
    """
    Normalise an alert and apply the 60-second dedup window.

    Args:
        payload: AlertPayload (validated by FastAPI).
        redis:   Async Redis client.

    Returns:
        (NormalisedAlert, is_duplicate).
        If duplicate: caller should NOT enqueue an RCA task.
    """
    raw = payload.raw_payload or {}
    source = payload.source

    # 1. Run source-specific extractor on the raw payload
    extractor = _EXTRACTORS.get(source, _extract_prometheus)
    extracted = extractor(raw) if raw else {}

    # 2. Fall back to top-level payload fields if extractor returned nothing
    service     = extracted.get("service")    or payload.service
    alert_name  = extracted.get("alert_name") or payload.alert_name
    labels      = extracted.get("labels")     or payload.labels
    annotations = extracted.get("annotations") or payload.annotations
    namespace   = extracted.get("namespace")
    severity    = _normalise_severity(extracted.get("severity") or payload.severity.value)

    # 3. Fingerprint + dedup
    fingerprint = compute_fingerprint(service, alert_name, labels)
    dedup_key   = _dedup_key(fingerprint)

    existing = await redis.get(dedup_key)
    if existing:
        # Pull the existing incident_id so the caller can correlate
        existing_incident_id = existing if isinstance(existing, str) else existing.decode()
        logger.info(
            "Duplicate alert suppressed: fingerprint=%s existing_incident=%s",
            fingerprint, existing_incident_id,
        )
        # Build a NormalisedAlert that points to the existing incident
        return (
            NormalisedAlert(
                incident_id=existing_incident_id,
                fingerprint=fingerprint,
                source=source,
                service=service,
                severity=severity,
                alert_name=alert_name,
                labels=labels,
                annotations=annotations,
                detected_at=datetime.now(timezone.utc),
                namespace=namespace,
                raw_payload=raw,
            ),
            True,    # is_duplicate
        )

    # 4. New incident
    incident_id = f"inc_{uuid.uuid4().hex[:12]}"
    alert = NormalisedAlert(
        incident_id=incident_id,
        fingerprint=fingerprint,
        source=source,
        service=service,
        severity=severity,
        alert_name=alert_name,
        labels=labels,
        annotations=annotations,
        detected_at=datetime.now(timezone.utc),
        namespace=namespace,
        raw_payload=raw,
    )

    # 5. Persist: dedup marker + incident state
    await redis.setex(dedup_key, _DEDUP_TTL_SEC, incident_id)
    await redis.setex(
        _incident_key(incident_id),
        _INCIDENT_TTL_SEC,
        alert.model_dump_json(),
    )

    logger.info(
        "Alert ingested: incident=%s service=%s severity=%s fingerprint=%s",
        incident_id, service, severity.value, fingerprint[:12],
    )
    return alert, False


async def get_incident(redis, incident_id: str) -> Optional[NormalisedAlert]:
    """Load a previously-ingested NormalisedAlert from Redis. None if expired."""
    raw = await redis.get(_incident_key(incident_id))
    if not raw:
        return None
    return NormalisedAlert.model_validate_json(raw)