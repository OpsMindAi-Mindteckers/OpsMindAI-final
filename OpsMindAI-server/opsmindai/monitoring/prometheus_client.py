"""
opsmindai/monitoring/prometheus_client.py

Prometheus metric registry and Prometheus HTTP API query helpers (SRS §11.1).

Metric registry
───────────────
All 8 metrics listed in SRS §11.1 are defined here and exported via
GET /metrics (prometheus_client.exposition.generate_latest).

Query helpers
─────────────
query_instant()  — instant PromQL query (GET /api/v1/query)
query_range()    — range PromQL query (GET /api/v1/query_range)
query_p99_latency() — convenience wrapper for SRE-GPT RCA
query_error_rate()  — convenience wrapper for SRE-GPT RCA
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    REGISTRY,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0)

# ── Metric definitions (SRS §11.1) ────────────────────────────────────────────

agent_runs_total = Counter(
    "opsmind_agent_runs_total",
    "Total agent executions",
    ["agent_name", "status"],
)

agent_duration_seconds = Histogram(
    "opsmind_agent_duration_seconds",
    "Agent execution time in seconds",
    ["agent_name"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

llm_tokens_total = Counter(
    "opsmind_llm_tokens_total",
    "Total LLM tokens processed",
    ["provider", "task_type"],
)

llm_requests_total = Counter(
    "opsmind_llm_requests_total",
    "Total LLM API requests",
    ["provider", "task_type", "routed_to"],
)

incident_mttr_seconds = Histogram(
    "opsmind_incident_mttr_seconds",
    "Mean time to remediation per incident in seconds",
    ["service", "severity"],
    buckets=(30, 60, 120, 300, 600, 1200, 3600),
)

coverage_delta_pct = Gauge(
    "opsmind_coverage_delta_pct",
    "Latest test coverage delta percentage vs previous run",
    ["repo", "branch"],
)

rag_hits_total = Counter(
    "opsmind_rag_hits_total",
    "Total RAG knowledge-base lookups",
    ["cache_hit"],
)

remediation_success_total = Counter(
    "opsmind_remediation_success_total",
    "Total remediation playbook executions",
    ["playbook", "status"],
)


# ── Exposition helpers ────────────────────────────────────────────────────────

def get_metrics_output() -> tuple[bytes, str]:
    """
    Return (metrics_bytes, content_type) for the GET /metrics endpoint.

    Usage in a FastAPI route:
        from fastapi.responses import Response
        body, ctype = get_metrics_output()
        return Response(content=body, media_type=ctype)
    """
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


# ── Prometheus HTTP API query helpers ─────────────────────────────────────────

async def query_instant(promql: str) -> list[dict[str, Any]]:
    """
    Execute an instant PromQL query against the configured Prometheus instance.

    Args:
        promql: PromQL expression string.

    Returns:
        List of result dicts from the 'result' array. Empty list on error.
    """
    url = f"{settings.PROMETHEUS_URL.rstrip('/')}/api/v1/query"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params={"query": promql})
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("result", [])
    except Exception as exc:
        logger.warning("prometheus query_instant failed: %s | query=%s", exc, promql)
        return []


async def query_range(
    promql:  str,
    start:   str,
    end:     str,
    step:    str = "15s",
) -> list[dict[str, Any]]:
    """
    Execute a range PromQL query.

    Args:
        promql: PromQL expression.
        start:  RFC3339 or Unix timestamp for range start.
        end:    RFC3339 or Unix timestamp for range end.
        step:   Query resolution step (e.g. '15s', '1m').

    Returns:
        List of result dicts from the 'result' array. Empty list on error.
    """
    url = f"{settings.PROMETHEUS_URL.rstrip('/')}/api/v1/query_range"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                url,
                params={
                    "query": promql,
                    "start": start,
                    "end":   end,
                    "step":  step,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("result", [])
    except Exception as exc:
        logger.warning("prometheus query_range failed: %s | query=%s", exc, promql)
        return []


async def query_p99_latency(service: str, minutes: int = 15) -> Optional[float]:
    """
    Query P99 request latency for a service over the last N minutes.

    Used by rca_engine to assemble evidence (SRS §9.4 step 58).

    Args:
        service: Service label value (matches Prometheus 'job' label).
        minutes: Look-back window in minutes.

    Returns:
        P99 latency in milliseconds, or None if no data.
    """
    promql = (
        f'histogram_quantile(0.99, '
        f'rate(http_request_duration_seconds_bucket{{job="{service}"}}[{minutes}m]))'
        f' * 1000'
    )
    results = await query_instant(promql)
    if results:
        try:
            return float(results[0]["value"][1])
        except (KeyError, IndexError, ValueError):
            pass
    return None


async def query_error_rate(service: str, minutes: int = 15) -> Optional[float]:
    """
    Query HTTP 5xx error rate for a service over the last N minutes.

    Used by rca_engine to assemble evidence (SRS §9.4 step 58).

    Args:
        service: Service label value.
        minutes: Look-back window in minutes.

    Returns:
        Error rate as a fraction [0, 1], or None if no data.
    """
    promql = (
        f'rate(http_requests_total{{job="{service}",status=~"5.."}}[{minutes}m])'
        f' / rate(http_requests_total{{job="{service}"}}[{minutes}m])'
    )
    results = await query_instant(promql)
    if results:
        try:
            return float(results[0]["value"][1])
        except (KeyError, IndexError, ValueError):
            pass
    return None


async def check_slo(
    service:          str,
    p99_threshold_ms: float,
    error_rate_max:   float,
    minutes:          int = 5,
) -> bool:
    """
    Return True if service P99 latency and error rate are within SLO thresholds.

    Used by remediation_executor post-fix verification (SRS §9.5 step 66).

    Args:
        service:           Service label.
        p99_threshold_ms:  Maximum acceptable P99 latency in ms.
        error_rate_max:    Maximum acceptable error rate fraction.
        minutes:           Evaluation window.

    Returns:
        True if within SLO, False if breaching or data unavailable.
    """
    p99 = await query_p99_latency(service, minutes)
    err = await query_error_rate(service, minutes)

    if p99 is None or err is None:
        logger.warning("check_slo: no data for service=%s — assuming not normalised", service)
        return False

    ok = (p99 < p99_threshold_ms) and (err < error_rate_max)
    logger.info(
        "check_slo: service=%s p99=%.1fms err=%.4f threshold_ms=%.1f err_max=%.4f ok=%s",
        service, p99, err, p99_threshold_ms, error_rate_max, ok,
    )
    return ok


# ── Convenience metric recording helpers ──────────────────────────────────────

def record_agent_run(agent_name: str, status: str, duration_s: float) -> None:
    """Increment agent run counter and record duration histogram."""
    agent_runs_total.labels(agent_name=agent_name, status=status).inc()
    agent_duration_seconds.labels(agent_name=agent_name).observe(duration_s)


def record_llm_request(
    provider:  str,
    task_type: str,
    routed_to: str,
    tokens:    int = 0,
) -> None:
    """Increment LLM request and token counters."""
    llm_requests_total.labels(
        provider=provider, task_type=task_type, routed_to=routed_to
    ).inc()
    if tokens:
        llm_tokens_total.labels(provider=provider, task_type=task_type).inc(tokens)


def record_rag_lookup(cache_hit: bool) -> None:
    """Increment RAG lookup counter."""
    rag_hits_total.labels(cache_hit=str(cache_hit).lower()).inc()


def record_remediation(playbook: str, status: str) -> None:
    """Increment remediation counter."""
    remediation_success_total.labels(playbook=playbook, status=status).inc()


def record_mttr(service: str, severity: str, seconds: float) -> None:
    """Observe incident MTTR."""
    incident_mttr_seconds.labels(service=service, severity=severity).observe(seconds)


def record_coverage_delta(repo: str, branch: str, delta: float) -> None:
    """Set coverage delta gauge."""
    coverage_delta_pct.labels(repo=repo, branch=branch).set(delta)
