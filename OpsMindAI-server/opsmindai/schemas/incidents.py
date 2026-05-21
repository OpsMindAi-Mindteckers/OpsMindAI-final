"""
opsmindai/schemas/incidents.py

Pydantic schemas for the SRE-GPT incident response pipeline.
Matches SRS §4.3 exactly.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class AlertSource(str, Enum):
    PROMETHEUS = "prometheus"
    PAGERDUTY  = "pagerduty"
    LOKI       = "loki"
    GRAFANA    = "grafana"


class IncidentSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


class IncidentStatus(str, Enum):
    QUEUED              = "queued"
    DUPLICATE_SUPPRESSED = "duplicate_suppressed"
    OPEN                = "open"
    ANALYZING           = "analyzing"
    REMEDIATING         = "remediating"
    RESOLVED            = "resolved"
    FALSE_POSITIVE      = "false_positive"
    ESCALATED           = "escalated"
    FAILED              = "failed"


class Playbook(str, Enum):
    ROLLBACK     = "rollback"
    RESTART      = "restart"
    SCALE        = "scale"
    FLUSH_POOL   = "flush_pool"
    ISOLATE_NODE = "isolate_node"
    AUTO         = "auto"


class RemediationStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED  = "failed"


# ── Inbound alert payload ─────────────────────────────────────────────────────

class AlertPayload(BaseModel):
    """Generic alert payload — matches §4.3 AlertPayload."""
    source:       AlertSource
    service:      str = Field(..., min_length=1)
    severity:     IncidentSeverity
    alert_name:   str = Field(..., min_length=1)
    labels:       dict[str, Any] = Field(default_factory=dict)
    annotations:  dict[str, Any] = Field(default_factory=dict)
    raw_payload:  dict[str, Any] = Field(default_factory=dict)


class NormalisedAlert(BaseModel):
    """Internal canonical alert form after ingestion."""
    incident_id:  str
    fingerprint:  str
    source:       AlertSource
    service:      str
    severity:     IncidentSeverity
    alert_name:   str
    labels:       dict[str, Any] = Field(default_factory=dict)
    annotations:  dict[str, Any] = Field(default_factory=dict)
    detected_at:  datetime
    namespace:    Optional[str] = None
    raw_payload:  dict[str, Any] = Field(default_factory=dict)


class IncidentIngestResponse(BaseModel):
    incident_id:   str
    status:        IncidentStatus
    deduplicated:  bool = False


# ── Logs / deployment / RCA ───────────────────────────────────────────────────

class LogLine(BaseModel):
    timestamp:         datetime
    message:           str
    level:             str = "info"
    extracted_errors:  list[str] = Field(default_factory=list)
    stack_traces:      list[str] = Field(default_factory=list)


class DeploymentDiff(BaseModel):
    service:           str
    namespace:         str = "default"
    current_image:     Optional[str] = None
    previous_image:    Optional[str] = None
    changed_fields:    list[str]      = Field(default_factory=list)
    last_deploy_time:  Optional[datetime] = None
    revisions_inspected: int = 0


class RCAEvidence(BaseModel):
    logs:        list[LogLine] = Field(default_factory=list)
    metrics:     dict[str, Any] = Field(default_factory=dict)
    diff:        Optional[DeploymentDiff] = None
    rag_results: list[dict[str, Any]] = Field(default_factory=list)


class RCAResult(BaseModel):
    """RCA output — matches §4.3 RCAResult + FR-46."""
    root_cause:        str
    confidence:        float = Field(..., ge=0.0, le=1.0)
    affected_services: list[str] = Field(default_factory=list)
    evidence:          RCAEvidence = Field(default_factory=RCAEvidence)
    remediation_plan:  list[str] = Field(default_factory=list)
    rag_matched:       bool = False
    root_cause_file:   Optional[str] = None  # used to dispatch refactor


# ── Remediation ───────────────────────────────────────────────────────────────

class RemediateRequest(BaseModel):
    incident_id:  str
    playbook:     Playbook = Playbook.AUTO


class RemediateResponse(BaseModel):
    incident_id:    str
    actions_taken:  list[str] = Field(default_factory=list)
    status:         RemediationStatus
    new_pod_count:  Optional[int] = None
    rollback_to:    Optional[str] = None
    playbook_used:  Optional[Playbook] = None
    normalised:     bool = False     # whether post-fix metrics returned to baseline
    duration_s:     Optional[float] = None


# ── Detail / timeline ─────────────────────────────────────────────────────────

class TimelineEvent(BaseModel):
    timestamp:  datetime
    event:      str
    details:    dict[str, Any] = Field(default_factory=dict)


class IncidentDetail(BaseModel):
    incident_id:   str
    service:       str
    severity:      IncidentSeverity
    status:        IncidentStatus
    detected_at:   datetime
    resolved_at:   Optional[datetime] = None
    rca:           Optional[RCAResult] = None
    timeline:      list[TimelineEvent] = Field(default_factory=list)
    alert:         Optional[NormalisedAlert] = None
    remediation:   Optional[RemediateResponse] = None