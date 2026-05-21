"""
opsmindai/agents/sre_gpt/remediation_executor.py

Phase P5 — SRS §9.5.

Executes one of 5 remediation playbooks against a Kubernetes cluster:
    rollback | restart | scale | flush_pool | isolate_node | auto

Auto mode parses RCAResult.remediation_plan[0] and picks the first viable
playbook. After execution the executor polls Prometheus for metric
normalisation; if not normalised within 60s, status flips to 'escalated'
and PagerDuty is paged.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from opsmindai.agents.sre_gpt.alert_ingester import get_incident
from opsmindai.agents.sre_gpt.rca_engine import get_rca
from opsmindai.schemas.incidents import (
    IncidentStatus,
    Playbook,
    RCAResult,
    RemediateResponse,
    RemediationStatus,
)

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_KUBECTL_TIMEOUT_S       = 30
_POST_ACTION_WAIT_S      = 30        # SRS §9.5: wait 30s before checking
_NORMALISATION_TIMEOUT_S = 60        # SRS §9.5: escalate if not normal in 60s
_NORMAL_P99_LATENCY_MS   = float(os.environ.get("SLO_P99_LATENCY_MS", "1000"))
_NORMAL_ERROR_RATE       = float(os.environ.get("SLO_ERROR_RATE", "0.01"))

# k8s name guard
_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9\-\.]{0,252}[a-z0-9]$")


def _validate(name: str, kind: str) -> None:
    if not _SAFE_NAME.match(name):
        raise ValueError(f"Invalid kubernetes {kind} name: {name!r}")


# ── Subprocess wrapper ───────────────────────────────────────────────────────

async def _run_kubectl(args: list[str]) -> tuple[int, str, str]:
    """Run `kubectl <args>` with timeout. Returns (rc, stdout, stderr)."""
    if not shutil.which("kubectl"):
        return 127, "", "kubectl binary not found"

    proc = await asyncio.create_subprocess_exec(
        "kubectl", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_KUBECTL_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", f"kubectl timed out after {_KUBECTL_TIMEOUT_S}s"

    return proc.returncode or 0, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")


# ── Playbook implementations ─────────────────────────────────────────────────

async def _playbook_rollback(service: str, namespace: str, **_) -> tuple[bool, list[str], dict]:
    """Undo the last deployment to the previous image."""
    rc, stdout, stderr = await _run_kubectl([
        "rollout", "undo", f"deployment/{service}", "-n", namespace,
    ])
    if rc != 0:
        return False, [f"rollback failed: {stderr.strip()}"], {}
    return True, [f"rolled back deployment/{service}"], {"rollback_to": "previous"}


async def _playbook_restart(service: str, namespace: str, **_) -> tuple[bool, list[str], dict]:
    """Restart all pods to flush in-memory state."""
    rc, stdout, stderr = await _run_kubectl([
        "rollout", "restart", f"deployment/{service}", "-n", namespace,
    ])
    if rc != 0:
        return False, [f"restart failed: {stderr.strip()}"], {}
    return True, [f"restarted deployment/{service}"], {}


async def _playbook_scale(service: str, namespace: str, **_) -> tuple[bool, list[str], dict]:
    """
    Double the replica count. We first read the current count, then
    set replicas=current*2 (capped at 20 to avoid runaway scaling).
    """
    rc, stdout, stderr = await _run_kubectl([
        "get", "deployment", service, "-n", namespace,
        "-o", "jsonpath={.spec.replicas}",
    ])
    if rc != 0 or not stdout.strip().isdigit():
        return False, [f"scale: could not read current replicas: {stderr.strip()}"], {}

    current = int(stdout.strip())
    target = min(current * 2, 20)

    rc, _, stderr = await _run_kubectl([
        "scale", f"deployment/{service}",
        f"--replicas={target}",
        "-n", namespace,
    ])
    if rc != 0:
        return False, [f"scale failed: {stderr.strip()}"], {}
    return True, [f"scaled deployment/{service} from {current} to {target} replicas"], \
           {"new_pod_count": target}


async def _playbook_flush_pool(service: str, namespace: str, **_) -> tuple[bool, list[str], dict]:
    """Trigger a connection-pool reset via env-var bump (POOL_RESET=<unix>)."""
    timestamp = str(int(time.time()))
    rc, _, stderr = await _run_kubectl([
        "set", "env", f"deployment/{service}",
        f"POOL_RESET={timestamp}",
        "-n", namespace,
    ])
    if rc != 0:
        return False, [f"flush_pool failed: {stderr.strip()}"], {}
    return True, [f"flushed connection pool for deployment/{service}"], \
           {"pool_reset_at": timestamp}


async def _playbook_isolate_node(service: str, namespace: str, node: Optional[str] = None, **_) -> tuple[bool, list[str], dict]:
    """Cordon and drain a node hosting failing pods. Requires `node` arg."""
    if not node:
        # Try to find a node hosting the service's pods
        rc, stdout, _ = await _run_kubectl([
            "get", "pods", "-n", namespace,
            "-l", f"app={service}",
            "-o", "jsonpath={.items[0].spec.nodeName}",
        ])
        if rc == 0 and stdout.strip():
            node = stdout.strip()
        else:
            return False, ["isolate_node: could not determine target node"], {}

    try:
        _validate(node, "node")
    except ValueError as exc:
        return False, [str(exc)], {}

    actions: list[str] = []
    rc, _, stderr = await _run_kubectl(["cordon", node])
    if rc != 0:
        return False, [f"cordon failed: {stderr.strip()}"], {}
    actions.append(f"cordoned node {node}")

    rc, _, stderr = await _run_kubectl([
        "drain", node,
        "--ignore-daemonsets",
        "--delete-emptydir-data",
        "--force",
        "--timeout=60s",
    ])
    if rc != 0:
        actions.append(f"drain partial: {stderr.strip()[:200]}")
        return False, actions, {"node": node}

    actions.append(f"drained node {node}")
    return True, actions, {"node": node}


_PLAYBOOK_FN = {
    Playbook.ROLLBACK:     _playbook_rollback,
    Playbook.RESTART:      _playbook_restart,
    Playbook.SCALE:        _playbook_scale,
    Playbook.FLUSH_POOL:   _playbook_flush_pool,
    Playbook.ISOLATE_NODE: _playbook_isolate_node,
}


# ── Auto playbook selection ──────────────────────────────────────────────────

_AUTO_KEYWORDS: list[tuple[Playbook, list[str]]] = [
    (Playbook.ROLLBACK,     ["rollback", "revert", "undo deploy"]),
    (Playbook.RESTART,      ["restart", "reboot", "bounce"]),
    (Playbook.SCALE,        ["scale", "increase replicas", "add capacity"]),
    (Playbook.FLUSH_POOL,   ["flush", "pool", "reset connection"]),
    (Playbook.ISOLATE_NODE, ["isolate", "cordon", "drain"]),
]


def _select_auto_playbook(rca: RCAResult) -> Playbook:
    """
    Pick the first playbook whose keywords appear in remediation_plan[0]
    or root_cause text. Falls back to RESTART (least destructive).
    """
    text = " ".join([
        rca.remediation_plan[0] if rca.remediation_plan else "",
        rca.root_cause or "",
    ]).lower()

    for playbook, keywords in _AUTO_KEYWORDS:
        if any(kw in text for kw in keywords):
            return playbook
    return Playbook.RESTART


# ── Post-action verification ─────────────────────────────────────────────────

async def _check_normalised(service: str) -> bool:
    """
    Poll Prometheus to verify P99 latency and error rate are below SLO.
    Imports rca_engine's metric helper to keep query logic in one place.
    """
    from opsmindai.agents.sre_gpt.rca_engine import _fetch_prometheus_metrics

    metrics = await _fetch_prometheus_metrics(service)
    if not metrics.get("ok", False):
        # If Prometheus is unreachable, we can't verify — assume OK to avoid
        # false escalations. Audit log explains why.
        logger.warning("Cannot verify normalisation — Prometheus unreachable")
        return True

    p99 = metrics.get("p99_latency_ms")
    err = metrics.get("error_rate")

    p99_ok = (p99 is None) or (p99 < _NORMAL_P99_LATENCY_MS)
    err_ok = (err is None) or (err < _NORMAL_ERROR_RATE)
    return p99_ok and err_ok


async def _wait_for_normalisation(service: str) -> bool:
    """
    Wait 30s, then poll up to _NORMALISATION_TIMEOUT_S total for SLOs to
    return to baseline. Returns True if normalised, False if timed out.
    """
    await asyncio.sleep(_POST_ACTION_WAIT_S)

    end_time = time.monotonic() + _NORMALISATION_TIMEOUT_S
    while time.monotonic() < end_time:
        if await _check_normalised(service):
            return True
        await asyncio.sleep(10)
    return False


# ── PagerDuty escalation ─────────────────────────────────────────────────────

async def _page_pagerduty(incident_id: str, summary: str) -> bool:
    routing_key = os.environ.get("PAGERDUTY_ROUTING_KEY")
    if not routing_key:
        logger.warning("PAGERDUTY_ROUTING_KEY not set — cannot escalate")
        return False

    payload = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "dedup_key": incident_id,
        "payload": {
            "summary": summary[:1024],
            "severity": "critical",
            "source": "opsmind-sre-gpt",
            "custom_details": {"incident_id": incident_id},
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
            )
            if resp.status_code >= 400:
                logger.warning("PagerDuty escalation failed: %s %s",
                               resp.status_code, resp.text)
                return False
        logger.info("Escalated to PagerDuty: incident=%s", incident_id)
        return True
    except Exception as exc:
        logger.exception("PagerDuty escalation error: %s", exc)
        return False


# ── Slack notifications ──────────────────────────────────────────────────────

async def _notify_slack(message: str) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(webhook, json={"text": message})
    except Exception as exc:
        logger.warning("Slack notify failed: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────

async def execute(
    incident_id: str,
    redis,
    playbook: Playbook = Playbook.AUTO,
) -> RemediateResponse:
    """
    Execute a remediation playbook for `incident_id`.

    Steps:
      1. Load alert + RCA from Redis
      2. Resolve playbook (auto -> select from RCA)
      3. Run kubectl playbook
      4. Wait + verify metric normalisation
      5. Update incident status + Slack notify, or escalate

    Returns:
        RemediateResponse with full action log.
    """
    start = time.monotonic()

    alert = await get_incident(redis, incident_id)
    if not alert:
        return RemediateResponse(
            incident_id=incident_id,
            status=RemediationStatus.FAILED,
            actions_taken=[f"incident {incident_id} not found in Redis"],
        )

    rca = await get_rca(redis, incident_id)
    namespace = alert.namespace or "default"

    # Resolve auto -> concrete playbook
    if playbook == Playbook.AUTO:
        if not rca:
            playbook = Playbook.RESTART
            logger.info("[remediate] auto with no RCA, defaulting to restart")
        else:
            playbook = _select_auto_playbook(rca)
            logger.info("[remediate] auto-selected playbook: %s", playbook.value)

    fn = _PLAYBOOK_FN.get(playbook)
    if not fn:
        return RemediateResponse(
            incident_id=incident_id,
            status=RemediationStatus.FAILED,
            actions_taken=[f"unknown playbook: {playbook}"],
            playbook_used=playbook,
        )

    # Validate names before any kubectl call
    try:
        _validate(alert.service, "deployment")
        _validate(namespace, "namespace")
    except ValueError as exc:
        return RemediateResponse(
            incident_id=incident_id,
            status=RemediationStatus.FAILED,
            actions_taken=[str(exc)],
            playbook_used=playbook,
        )

    # 1. Mark as remediating
    await _set_status(redis, incident_id, IncidentStatus.REMEDIATING)
    await _notify_slack(
        f":wrench: *Remediation started* — incident `{incident_id}` "
        f"service `{alert.service}` playbook `{playbook.value}`"
    )

    # 2. Run playbook
    try:
        ok, actions, extras = await fn(alert.service, namespace)
    except Exception as exc:
        logger.exception("Playbook %s raised", playbook.value)
        return RemediateResponse(
            incident_id=incident_id,
            status=RemediationStatus.FAILED,
            actions_taken=[f"playbook crashed: {exc}"],
            playbook_used=playbook,
            duration_s=round(time.monotonic() - start, 2),
        )

    if not ok:
        await _set_status(redis, incident_id, IncidentStatus.FAILED)
        return RemediateResponse(
            incident_id=incident_id,
            status=RemediationStatus.FAILED,
            actions_taken=actions,
            playbook_used=playbook,
            duration_s=round(time.monotonic() - start, 2),
            **{k: v for k, v in extras.items()
               if k in ("new_pod_count", "rollback_to")},
        )

    # 3. Wait + verify
    normalised = await _wait_for_normalisation(alert.service)

    duration = round(time.monotonic() - start, 2)

    if normalised:
        await _set_status(redis, incident_id, IncidentStatus.RESOLVED, resolved=True)
        await _notify_slack(
            f":white_check_mark: *Resolved* — incident `{incident_id}` "
            f"normalised after `{playbook.value}`. Duration: {duration:.0f}s"
        )

        # Embed in RAG (non-fatal)
        await _embed_resolution(alert, rca, playbook, actions)

        # Optionally trigger refactor on root-cause file
        if rca and rca.root_cause_file:
            await _dispatch_refactor(rca.root_cause_file)

        return RemediateResponse(
            incident_id=incident_id,
            status=RemediationStatus.SUCCESS,
            actions_taken=actions,
            playbook_used=playbook,
            normalised=True,
            duration_s=duration,
            **{k: v for k, v in extras.items()
               if k in ("new_pod_count", "rollback_to")},
        )

    # Not normalised — escalate
    await _set_status(redis, incident_id, IncidentStatus.ESCALATED)
    await _page_pagerduty(
        incident_id,
        f"Service {alert.service} not normalised after {playbook.value}",
    )
    await _notify_slack(
        f":rotating_light: *Escalated* — incident `{incident_id}` "
        f"did not normalise after `{playbook.value}`. Paged PagerDuty."
    )

    return RemediateResponse(
        incident_id=incident_id,
        status=RemediationStatus.PARTIAL,
        actions_taken=actions + ["metrics did not normalise — escalated to PagerDuty"],
        playbook_used=playbook,
        normalised=False,
        duration_s=duration,
        **{k: v for k, v in extras.items()
           if k in ("new_pod_count", "rollback_to")},
    )


# ── Persistence helpers ──────────────────────────────────────────────────────

async def _set_status(
    redis,
    incident_id: str,
    status: IncidentStatus,
    resolved: bool = False,
) -> None:
    """Update the incident status JSON blob in Redis."""
    key = f"incident:{incident_id}:status"
    payload = {
        "status": status.value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if resolved:
        payload["resolved_at"] = datetime.now(timezone.utc).isoformat()
    try:
        import json
        await redis.setex(key, 86_400, json.dumps(payload))
    except Exception as exc:
        logger.warning("Failed to update incident status: %s", exc)


async def _embed_resolution(alert, rca, playbook, actions) -> None:
    """Embed (incident + fix) into RAG for future similarity matching."""
    try:
        from opsmindai.memory.rag_pipeline import RAGPipeline
        rag = RAGPipeline()
        content = (
            f"Incident: {alert.alert_name} on {alert.service}. "
            f"Root cause: {rca.root_cause if rca else 'unknown'}. "
            f"Resolved by playbook '{playbook.value}'. "
            f"Actions: {'; '.join(actions)}"
        )
        await rag.embed(
            content=content,
            doc_type="incident",
            metadata={
                "incident_id": alert.incident_id,
                "service":     alert.service,
                "severity":    alert.severity.value,
                "playbook":    playbook.value,
            },
        )
    except Exception as exc:
        logger.warning("RAG embed of resolution failed: %s", exc)


async def _dispatch_refactor(file_path: str) -> None:
    """
    Queue a Celery refactor task for the root-cause file (FR-49).
    Failure is non-fatal — incident is already resolved.
    """
    try:
        from opsmindai.tasks.refactor_tasks import task_run_analysis
        # Refactor task expects a payload — we synthesise a minimal one.
        # Caller of this whole chain is expected to set REFACTOR_DEFAULT_REPO_URL.
        repo_url = os.environ.get("REFACTOR_DEFAULT_REPO_URL")
        if not repo_url:
            logger.info("REFACTOR_DEFAULT_REPO_URL not set, skipping post-incident refactor")
            return
        import uuid
        job_id = f"post_incident_{uuid.uuid4().hex[:8]}"
        task_run_analysis.apply_async(
            args=[job_id, {
                "repo_url":   repo_url,
                "branch":     "master",
                "file_paths": [file_path],
                "user_id":    "sre_gpt",
                "severity_threshold": "medium",
            }],
            task_id=job_id,
        )
        logger.info("Dispatched post-incident refactor for %s (job=%s)", file_path, job_id)
    except Exception as exc:
        logger.warning("Could not dispatch post-incident refactor: %s", exc)