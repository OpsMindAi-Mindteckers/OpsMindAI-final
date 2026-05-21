"""
opsmindai/orchestrator/event_handler.py

Normalises all inbound webhook payloads from GitHub, Prometheus,
PagerDuty, Loki, and Grafana into a common NormalisedEvent schema.

Used by task_router.py and the webhook API routes (SRS §10).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Event taxonomy ─────────────────────────────────────────────────────────────

class EventType(str, Enum):
    PUSH          = "push"
    PULL_REQUEST  = "pull_request"
    ALERT         = "alert"
    COVERAGE_DROP = "coverage_drop"
    UNKNOWN       = "unknown"


class EventSource(str, Enum):
    GITHUB     = "github"
    PROMETHEUS = "prometheus"
    PAGERDUTY  = "pagerduty"
    LOKI       = "loki"
    GRAFANA    = "grafana"
    INTERNAL   = "internal"


# ── Normalised event ───────────────────────────────────────────────────────────

class NormalisedEvent(BaseModel):
    """Common event representation consumed by task_router."""
    event_id:   str
    event_type: EventType
    source:     EventSource
    service:    Optional[str]  = None
    severity:   Optional[str]  = None
    repo_url:   Optional[str]  = None
    branch:     Optional[str]  = None
    pr_number:  Optional[int]  = None
    file_paths: list[str]      = Field(default_factory=list)
    labels:     dict[str, Any] = Field(default_factory=dict)
    raw:        dict[str, Any] = Field(default_factory=dict)
    timestamp:  datetime       = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


def _event_id(source: str, payload: dict) -> str:
    """Stable 16-hex event identifier."""
    raw    = f"{source}:{str(sorted(payload.items()))}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"evt_{digest}"


# ── GitHub ─────────────────────────────────────────────────────────────────────

def handle_github(payload: dict) -> NormalisedEvent:
    """
    Normalise a GitHub webhook payload.

    Supports 'push' and 'pull_request' event types.
    Extracts changed source files (.py / .js / .ts) from commit data.
    """
    event_type = EventType.UNKNOWN
    branch:    Optional[str] = None
    repo_url:  Optional[str] = None
    pr_number: Optional[int] = None
    file_paths: list[str]    = []

    if "commits" in payload:
        event_type = EventType.PUSH
        branch     = payload.get("ref", "").replace("refs/heads/", "") or None
        repo_url   = (payload.get("repository") or {}).get("clone_url")
        for commit in payload.get("commits", []):
            file_paths.extend(commit.get("added",    []))
            file_paths.extend(commit.get("modified", []))

    elif "pull_request" in payload:
        event_type = EventType.PULL_REQUEST
        pr         = payload["pull_request"]
        branch     = pr.get("head", {}).get("ref")
        repo_url   = (pr.get("head", {}).get("repo") or {}).get("clone_url")
        pr_number  = pr.get("number")

    src_files = [p for p in file_paths if p.endswith((".py", ".js", ".ts"))]

    logger.info(
        "event_handler github: type=%s repo=%s branch=%s src_files=%d",
        event_type, repo_url, branch, len(src_files),
    )
    return NormalisedEvent(
        event_id   = _event_id("github", payload),
        event_type = event_type,
        source     = EventSource.GITHUB,
        repo_url   = repo_url,
        branch     = branch,
        pr_number  = pr_number,
        file_paths = src_files,
        raw        = payload,
    )


# ── Prometheus (Alertmanager) ──────────────────────────────────────────────────

def handle_prometheus(payload: dict) -> NormalisedEvent:
    """
    Normalise an Alertmanager webhook payload.

    Uses the first alert in the 'alerts[]' array as canonical.
    """
    alerts  = payload.get("alerts", [payload])
    first   = alerts[0] if alerts else {}
    labels  = first.get("labels", {})

    service    = (labels.get("job")
                  or labels.get("service")
                  or labels.get("instance", "unknown"))
    severity   = labels.get("severity", "medium")
    alert_name = labels.get("alertname", "UnknownAlert")

    logger.info(
        "event_handler prometheus: alert=%s service=%s severity=%s",
        alert_name, service, severity,
    )
    return NormalisedEvent(
        event_id   = _event_id("prometheus", payload),
        event_type = EventType.ALERT,
        source     = EventSource.PROMETHEUS,
        service    = service,
        severity   = severity,
        labels     = {**labels, "alert_name": alert_name},
        raw        = payload,
    )


# ── PagerDuty ──────────────────────────────────────────────────────────────────

def handle_pagerduty(payload: dict) -> NormalisedEvent:
    """
    Normalise a PagerDuty webhook v3 payload.

    Extracts from the 'messages[0].incident' structure.
    """
    messages = payload.get("messages", [])
    first    = messages[0] if messages else payload
    incident = first.get("incident", first)

    service    = (incident.get("service", {}).get("name")
                  or incident.get("service_name", "unknown"))
    severity   = incident.get("urgency", "high")
    alert_name = incident.get("title", "PagerDutyAlert")

    logger.info(
        "event_handler pagerduty: alert=%s service=%s",
        alert_name, service,
    )
    return NormalisedEvent(
        event_id   = _event_id("pagerduty", payload),
        event_type = EventType.ALERT,
        source     = EventSource.PAGERDUTY,
        service    = service,
        severity   = severity,
        labels     = {"alert_name": alert_name},
        raw        = payload,
    )


# ── Loki ───────────────────────────────────────────────────────────────────────

def handle_loki(payload: dict) -> NormalisedEvent:
    """Normalise a Loki alert-ruler webhook payload."""
    alerts = payload.get("alerts", [payload])
    first  = alerts[0] if alerts else payload
    labels = first.get("labels", {})

    service    = labels.get("job") or labels.get("service", "unknown")
    severity   = labels.get("severity", "medium")
    alert_name = first.get("annotations", {}).get("summary", "LokiAlert")

    logger.info("event_handler loki: service=%s severity=%s", service, severity)
    return NormalisedEvent(
        event_id   = _event_id("loki", payload),
        event_type = EventType.ALERT,
        source     = EventSource.LOKI,
        service    = service,
        severity   = severity,
        labels     = {**labels, "alert_name": alert_name},
        raw        = payload,
    )


# ── Grafana ────────────────────────────────────────────────────────────────────

def handle_grafana(payload: dict) -> NormalisedEvent:
    """Normalise a Grafana unified alerting webhook payload."""
    alerts = payload.get("alerts", [payload])
    first  = alerts[0] if alerts else payload
    labels = first.get("labels", {})

    service    = labels.get("job") or labels.get("service", "unknown")
    severity   = (labels.get("severity")
                  or payload.get("state", "medium"))
    alert_name = (first.get("annotations", {}).get("summary")
                  or payload.get("title", "GrafanaAlert"))

    logger.info("event_handler grafana: service=%s severity=%s", service, severity)
    return NormalisedEvent(
        event_id   = _event_id("grafana", payload),
        event_type = EventType.ALERT,
        source     = EventSource.GRAFANA,
        service    = service,
        severity   = severity,
        labels     = {**labels, "alert_name": alert_name},
        raw        = payload,
    )


# ── Internal (coverage-drop, manual, etc.) ────────────────────────────────────

def handle_internal(event_type: EventType, payload: dict) -> NormalisedEvent:
    """Wrap internal platform events into a NormalisedEvent."""
    return NormalisedEvent(
        event_id   = _event_id("internal", payload),
        event_type = event_type,
        source     = EventSource.INTERNAL,
        service    = payload.get("service"),
        repo_url   = payload.get("repo_url"),
        branch     = payload.get("branch"),
        file_paths = payload.get("file_paths", []),
        raw        = payload,
    )


# ── Public dispatch map ────────────────────────────────────────────────────────

_HANDLERS = {
    "github":     handle_github,
    "prometheus": handle_prometheus,
    "pagerduty":  handle_pagerduty,
    "loki":       handle_loki,
    "grafana":    handle_grafana,
}


def normalise(source: str, raw_payload: dict) -> NormalisedEvent:
    """
    Normalise a raw webhook payload from any supported source.

    Args:
        source:      Source identifier ('github', 'prometheus', etc.).
        raw_payload: Raw parsed JSON payload dict.

    Returns:
        NormalisedEvent ready for task_router.route_event().
    """
    handler = _HANDLERS.get(source.lower())
    if handler:
        return handler(raw_payload)

    logger.warning(
        "event_handler: unknown source=%s — returning UNKNOWN event", source
    )
    return NormalisedEvent(
        event_id   = _event_id(source, raw_payload),
        event_type = EventType.UNKNOWN,
        source     = EventSource.INTERNAL,
        raw        = raw_payload,
    )
