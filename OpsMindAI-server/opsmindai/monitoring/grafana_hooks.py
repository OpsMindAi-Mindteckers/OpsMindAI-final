"""
opsmindai/monitoring/grafana_hooks.py

Grafana annotation push client (SRS §11, FR-50).

Used to mark incident detected / RCA done / remediated / resolved
events as Grafana annotations so the dashboard timeline reflects the
full incident lifecycle.

Functions
─────────
post_annotation()    — push a single annotation to Grafana
annotate_detected()  — incident detected
annotate_rca_done()  — RCA analysis complete
annotate_remediated()— remediation applied
annotate_resolved()  — incident resolved
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT     = httpx.Timeout(10.0)
_ANNOTATIONS = "/api/annotations"

# Tag prefixes for Grafana annotation filtering
_TAG_PREFIX = "opsmindai"


async def post_annotation(
    text:      str,
    tags:      list[str],
    time_ms:   Optional[int] = None,
    dashboard_id: Optional[int] = None,
) -> Optional[int]:
    """
    Push a single annotation to Grafana.

    Args:
        text:         Annotation label text.
        tags:         List of tag strings for filtering in Grafana.
        time_ms:      Unix timestamp in milliseconds (default: now).
        dashboard_id: Target dashboard ID (default: all dashboards).

    Returns:
        Grafana annotation ID, or None on failure.
    """
    if not settings.GRAFANA_URL:
        logger.debug("grafana_hooks: GRAFANA_URL not set — skipping annotation")
        return None

    url      = f"{settings.GRAFANA_URL.rstrip('/')}{_ANNOTATIONS}"
    time_ms  = time_ms or _now_ms()

    payload: dict = {
        "text":    text,
        "tags":    [_TAG_PREFIX] + tags,
        "time":    time_ms,
        "isRegion": False,
    }
    if dashboard_id is not None:
        payload["dashboardId"] = dashboard_id

    auth = _get_auth()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, auth=auth) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            annotation_id = resp.json().get("id")
            logger.info(
                "grafana_hooks: annotation id=%s text=%r tags=%s",
                annotation_id, text, tags,
            )
            return annotation_id
    except Exception as exc:
        logger.warning("grafana_hooks: post_annotation failed: %s", exc)
        return None


# ── Incident lifecycle annotation helpers ──────────────────────────────────────

async def annotate_detected(
    incident_id: str,
    service:     str,
    severity:    str,
    alert_name:  str,
) -> Optional[int]:
    """Post 'Incident Detected' annotation at current time."""
    return await post_annotation(
        text = f"[DETECTED] {alert_name} — {service} ({severity})",
        tags = ["incident", "detected", service, severity, incident_id],
    )


async def annotate_rca_done(
    incident_id: str,
    service:     str,
    confidence:  float,
    root_cause:  str,
) -> Optional[int]:
    """Post 'RCA Complete' annotation."""
    short_cause = root_cause[:80] + "…" if len(root_cause) > 80 else root_cause
    return await post_annotation(
        text = f"[RCA] {service} confidence={confidence:.0%} — {short_cause}",
        tags = ["incident", "rca", service, incident_id],
    )


async def annotate_remediated(
    incident_id: str,
    service:     str,
    playbook:    str,
    status:      str,
) -> Optional[int]:
    """Post 'Remediation Applied' annotation."""
    return await post_annotation(
        text = f"[REMEDIATED] {service} playbook={playbook} status={status}",
        tags = ["incident", "remediation", service, playbook, incident_id],
    )


async def annotate_resolved(
    incident_id: str,
    service:     str,
    mttr_s:      float,
) -> Optional[int]:
    """Post 'Incident Resolved' annotation with MTTR."""
    mttr_label = _fmt_duration(mttr_s)
    return await post_annotation(
        text = f"[RESOLVED] {service} MTTR={mttr_label}",
        tags = ["incident", "resolved", service, incident_id],
    )


# ── Internal helpers ───────────────────────────────────────────────────────────

def _now_ms() -> int:
    """Current Unix time in milliseconds."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _fmt_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def _get_auth() -> Optional[httpx.BasicAuth]:
    """
    Return Grafana basic auth credentials if API key or user/pass is configured.

    Grafana API token should be set as: GRAFANA_URL = http://admin:password@localhost:3000
    or inline in the URL. Returns None (no auth) otherwise.
    """
    # If credentials are embedded in the URL, httpx handles them automatically
    return None
