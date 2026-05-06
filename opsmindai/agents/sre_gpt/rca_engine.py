"""
opsmindai/agents/sre_gpt/rca_engine.py

Phase P5 — SRS §9.4.

Performs root-cause analysis for a normalised incident:
  1. Loads alert from Redis
  2. Concurrently fetches logs, deployment diff, Prometheus metrics
  3. Retrieves top-5 RAG matches for similar past incidents
  4. Sends assembled context to the hybrid LLM router
  5. Parses structured RCAResult including confidence
  6. Persists result and triggers remediation OR escalation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import textwrap
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from opsmindai.agents.sre_gpt.alert_ingester import get_incident
from opsmindai.agents.sre_gpt.deployment_differ import get_deployment_diff
from opsmindai.agents.sre_gpt.log_parser import fetch_logs
from opsmindai.schemas.incidents import (
    NormalisedAlert,
    RCAEvidence,
    RCAResult,
)

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_CONFIDENCE_AUTO_REMEDIATE = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.80"))
_PROM_TIMEOUT_S            = 10
_PROM_LOOKBACK_MIN         = 15      # FR-45: last 15 min metrics
_RAG_TOP_K                 = 5

# Redis keys
_RCA_KEY_PREFIX = "incident:"
_RCA_SUFFIX     = ":rca"


def _rca_key(incident_id: str) -> str:
    return f"{_RCA_KEY_PREFIX}{incident_id}{_RCA_SUFFIX}"


# ── Lazy imports (avoid circulars) ────────────────────────────────────────────

def _get_hybrid_router():
    from opsmindai.inference.hybrid_router import HybridRouter
    return HybridRouter()


def _get_rag_pipeline():
    from opsmindai.memory.rag_pipeline import RAGPipeline
    return RAGPipeline()


# ── Prometheus query ─────────────────────────────────────────────────────────

async def _fetch_prometheus_metrics(service: str) -> dict[str, Any]:
    """
    Query Prometheus for P99 latency + error rate over last 15 min.

    Returns:
        {"p99_latency_ms": float|None, "error_rate": float|None,
         "queried_at": iso string, "ok": bool}
    """
    base_url = os.environ.get("PROMETHEUS_URL")
    if not base_url:
        return {"p99_latency_ms": None, "error_rate": None, "ok": False,
                "reason": "PROMETHEUS_URL not set"}

    queries = {
        "p99_latency_ms": (
            f'histogram_quantile(0.99, '
            f'sum(rate(http_request_duration_seconds_bucket{{service="{service}"}}'
            f'[{_PROM_LOOKBACK_MIN}m])) by (le)) * 1000'
        ),
        "error_rate": (
            f'sum(rate(http_requests_total{{service="{service}",status=~"5.."}}'
            f'[{_PROM_LOOKBACK_MIN}m])) '
            f'/ sum(rate(http_requests_total{{service="{service}"}}'
            f'[{_PROM_LOOKBACK_MIN}m]))'
        ),
    }

    results: dict[str, Any] = {"ok": True, "queried_at":
                               datetime.now(timezone.utc).isoformat()}

    try:
        async with httpx.AsyncClient(timeout=_PROM_TIMEOUT_S) as client:
            for name, query in queries.items():
                try:
                    resp = await client.get(
                        f"{base_url.rstrip('/')}/api/v1/query",
                        params={"query": query},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    series = data.get("data", {}).get("result", [])
                    if series:
                        value = series[0].get("value", [None, None])[1]
                        results[name] = float(value) if value else None
                    else:
                        results[name] = None
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    logger.warning("Prometheus query %s failed: %s", name, exc)
                    results[name] = None
    except Exception as exc:
        logger.warning("Prometheus connection failed: %s", exc)
        return {"p99_latency_ms": None, "error_rate": None, "ok": False,
                "reason": str(exc)}

    return results


# ── LLM prompt ────────────────────────────────────────────────────────────────

_RCA_SYSTEM_PROMPT = textwrap.dedent("""
You are an expert Site Reliability Engineer performing root-cause analysis.
You receive: an alert, recent error logs, a deployment diff, current metrics,
and similar past incidents.

OUTPUT RULES:
1. Produce ONLY valid JSON. No markdown fences, no commentary.
2. The JSON object must match this schema EXACTLY:

{
  "root_cause":        "<one-sentence diagnosis>",
  "confidence":        <float between 0.0 and 1.0>,
  "affected_services": ["<service>", ...],
  "remediation_plan":  ["<step1>", "<step2>", ...],
  "rag_matched":       <true|false>,
  "root_cause_file":   "<relative path of suspect source file, or null>"
}

3. confidence calibration:
   - 0.90+ : alert+logs+diff all converge on the same cause
   - 0.70-0.89 : strong signal but at least one piece of evidence missing
   - 0.50-0.69 : plausible but speculative
   - <0.50 : insufficient data

4. remediation_plan is an ordered list of concrete actions. Use playbook
   terms: "rollback", "restart", "scale", "flush_pool", "isolate_node",
   followed by service / namespace as needed.
""").strip()


def _format_log_lines(logs: list) -> str:
    if not logs:
        return "(no logs available)"
    snippets = []
    for line in logs[:30]:
        ts = line.timestamp.isoformat() if line.timestamp else "?"
        snippets.append(f"[{ts}] {line.level}: {line.message[:250]}")
    return "\n".join(snippets)


def _format_diff(diff) -> str:
    if not diff or not diff.changed_fields:
        return "(no recent deployment changes)"
    lines = [f"Service: {diff.service} (ns={diff.namespace})"]
    if diff.last_deploy_time:
        lines.append(f"Last deploy: {diff.last_deploy_time.isoformat()}")
    lines.extend(f"  - {f}" for f in diff.changed_fields)
    return "\n".join(lines)


def _format_metrics(m: dict) -> str:
    if not m or not m.get("ok", False):
        return f"(metrics unavailable: {m.get('reason', 'unknown')})"
    p99 = m.get("p99_latency_ms")
    err = m.get("error_rate")
    return (
        f"P99 latency: {p99:.0f}ms\n"
        f"Error rate:  {err:.2%}"
        if p99 is not None and err is not None
        else f"P99 latency: {p99}\nError rate: {err}"
    )


def _format_rag(rag_results: list) -> str:
    if not rag_results:
        return "(no similar past incidents found)"
    blocks = []
    for i, r in enumerate(rag_results[:_RAG_TOP_K], 1):
        score = r.get("score", 0.0)
        content = (r.get("content") or "")[:400]
        blocks.append(f"[Match {i} | score={score:.2f}]\n{content}")
    return "\n\n".join(blocks)


def _build_rca_user_prompt(
    alert: NormalisedAlert,
    logs:  list,
    diff,
    metrics: dict,
    rag_results: list,
) -> str:
    return textwrap.dedent(f"""
        === INCIDENT ALERT ===
        Service:    {alert.service}
        Severity:   {alert.severity.value}
        Alert:      {alert.alert_name}
        Source:     {alert.source.value}
        Detected:   {alert.detected_at.isoformat()}
        Labels:     {json.dumps(alert.labels, default=str)[:500]}

        === RECENT ERROR LOGS ===
        {_format_log_lines(logs)}

        === DEPLOYMENT DIFF ===
        {_format_diff(diff)}

        === METRICS (last 15 min) ===
        {_format_metrics(metrics)}

        === SIMILAR PAST INCIDENTS (from RAG) ===
        {_format_rag(rag_results)}

        === TASK ===
        Identify the root cause and produce the JSON object exactly per the schema.
    """).strip()


# ── Response parsing ─────────────────────────────────────────────────────────

def _parse_rca_response(
    raw: str,
    fallback_service: str,
) -> RCAResult:
    """
    Parse LLM response into a strict RCAResult.

    Falls back to a low-confidence "unparseable" RCA on bad JSON, so that
    the pipeline always produces something downstream consumers can handle.
    """
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            logger.warning("RCA response not JSON, returning fallback: %s", raw[:200])
            return RCAResult(
                root_cause="Unable to determine — LLM returned malformed response",
                confidence=0.0,
                affected_services=[fallback_service],
                remediation_plan=[],
                rag_matched=False,
            )
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return RCAResult(
                root_cause="Unable to parse LLM response",
                confidence=0.0,
                affected_services=[fallback_service],
                remediation_plan=[],
            )

    # Coerce + sanitise
    confidence = float(data.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))
    affected = data.get("affected_services") or [fallback_service]
    if not isinstance(affected, list):
        affected = [str(affected)]

    plan = data.get("remediation_plan") or []
    if not isinstance(plan, list):
        plan = [str(plan)]

    return RCAResult(
        root_cause=str(data.get("root_cause", "unknown"))[:1000],
        confidence=confidence,
        affected_services=[str(s) for s in affected[:10]],
        remediation_plan=[str(s) for s in plan[:20]],
        rag_matched=bool(data.get("rag_matched", False)),
        root_cause_file=data.get("root_cause_file"),
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def analyze(incident_id: str, redis) -> RCAResult:
    """
    Run full RCA for an incident_id, persist result, and return RCAResult.

    On confidence >= CONFIDENCE_THRESHOLD the caller should auto-remediate.
    On confidence < threshold the caller should page a human.

    This function does NOT itself trigger remediation — that decision lives
    in agent.py / Celery tasks so that side-effects are explicit.
    """
    alert = await get_incident(redis, incident_id)
    if not alert:
        raise ValueError(f"Incident {incident_id} not found in Redis")

    # 1. Concurrent evidence gathering
    logs_task    = fetch_logs(alert.service, alert.severity.value)
    diff_task    = get_deployment_diff(alert.service, alert.namespace or "default")
    metrics_task = _fetch_prometheus_metrics(alert.service)

    # RAG retrieval — non-fatal
    rag_task: asyncio.Task = asyncio.create_task(_safe_rag_lookup(alert))

    logs, diff, metrics = await asyncio.gather(
        logs_task, diff_task, metrics_task,
        return_exceptions=False,
    )
    rag_results = await rag_task

    evidence = RCAEvidence(
        logs=logs,
        metrics=metrics,
        diff=diff,
        rag_results=rag_results,
    )

    # 2. Build prompt
    user_prompt = _build_rca_user_prompt(alert, logs, diff, metrics, rag_results)

    # 3. Call LLM via hybrid router
    try:
        router = _get_hybrid_router()
        response = await router.infer(
            system_prompt=_RCA_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            task_type="rca",
            estimated_tokens=len(user_prompt.split()) + 500,
        )
        raw_text = response.get("text", "") if isinstance(response, dict) else str(response)
    except Exception as exc:
        logger.exception("LLM inference failed for incident %s", incident_id)
        rca = RCAResult(
            root_cause=f"LLM inference failed: {exc}",
            confidence=0.0,
            affected_services=[alert.service],
            evidence=evidence,
            remediation_plan=[],
        )
        await _persist_rca(redis, incident_id, rca)
        return rca

    # 4. Parse response
    rca = _parse_rca_response(raw_text, fallback_service=alert.service)
    rca.evidence = evidence

    # 5. Persist
    await _persist_rca(redis, incident_id, rca)

    logger.info(
        "RCA complete: incident=%s confidence=%.2f cause=%s",
        incident_id, rca.confidence, rca.root_cause[:80],
    )
    return rca


async def _safe_rag_lookup(alert: NormalisedAlert) -> list[dict[str, Any]]:
    """RAG retrieval with full error swallow. Returns [] on any failure."""
    try:
        rag = _get_rag_pipeline()
        query = f"{alert.alert_name} {alert.service} {alert.severity.value}"
        results = await rag.retrieve(
            query=query,
            doc_type="incident",
            top_k=_RAG_TOP_K,
        )
        if isinstance(results, list):
            return results
        return []
    except Exception as exc:
        logger.warning("RAG lookup failed: %s", exc)
        return []


async def _persist_rca(redis, incident_id: str, rca: RCAResult) -> None:
    """Store RCA result in Redis with 24h TTL."""
    try:
        await redis.setex(
            _rca_key(incident_id),
            86_400,
            rca.model_dump_json(),
        )
    except Exception as exc:
        logger.warning("Failed to persist RCA for %s: %s", incident_id, exc)


def is_auto_remediable(rca: RCAResult) -> bool:
    """True when confidence clears the auto-remediation threshold."""
    return rca.confidence >= _CONFIDENCE_AUTO_REMEDIATE


async def get_rca(redis, incident_id: str) -> Optional[RCAResult]:
    raw = await redis.get(_rca_key(incident_id))
    if not raw:
        return None
    return RCAResult.model_validate_json(raw)