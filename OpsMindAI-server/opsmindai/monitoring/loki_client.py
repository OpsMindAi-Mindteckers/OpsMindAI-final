"""
opsmindai/monitoring/loki_client.py

Loki LogQL HTTP query client (SRS §9.2, FR-43).

Used by agents/sre_gpt/log_parser.py to fetch error logs and stack
traces from the service's Loki stream.

Functions
─────────
query_range()    — raw LogQL range query → list of stream entries
fetch_errors()   — convenience: filter ERROR-level lines for a service
build_logql()    — build a LogQL expression from service + severity
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx

from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)

# ── Low-level query ────────────────────────────────────────────────────────────

async def query_range(
    logql:  str,
    start:  Optional[datetime] = None,
    end:    Optional[datetime] = None,
    limit:  int = 500,
) -> list[dict[str, Any]]:
    """
    POST a LogQL range query to Loki's /loki/api/v1/query_range endpoint.

    Args:
        logql:  LogQL expression string.
        start:  Query window start (default: now - 10 minutes).
        end:    Query window end (default: now).
        limit:  Maximum log lines to return.

    Returns:
        List of stream entry dicts: {stream: {...labels}, values: [[ts, line], ...]}.
        Empty list on error.
    """
    now   = datetime.now(timezone.utc)
    end   = end   or now
    start = start or (now - timedelta(minutes=10))

    url = f"{settings.LOKI_URL.rstrip('/')}/loki/api/v1/query_range"
    params = {
        "query": logql,
        "start": _to_ns(start),
        "end":   _to_ns(end),
        "limit": limit,
    }

    logger.debug("loki query: %s window=%s→%s", logql, start.isoformat(), end.isoformat())

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("result", [])
    except Exception as exc:
        logger.warning("loki_client query_range failed: %s | logql=%s", exc, logql)
        return []


# ── High-level helpers ─────────────────────────────────────────────────────────

def build_logql(service: str, severity: str = "error") -> str:
    """
    Build a LogQL expression for a service filtered to error-level lines.

    Matches the pattern from SRS §9.2 step 46:
      {service='{service}'} |= 'error' | logfmt | level >= '{severity}'

    Args:
        service:  Service / job name label value.
        severity: Minimum log level string.

    Returns:
        LogQL expression string.
    """
    return (
        f'{{job="{service}"}} '
        f'|= "error" '
        f'| logfmt '
        f'| level >= "{severity}"'
    )


async def fetch_errors(
    service:  str,
    severity: str = "error",
    minutes:  int = 10,
) -> list[dict[str, Any]]:
    """
    Fetch error-level log entries for a service.

    Args:
        service:  Service / job label value.
        severity: Minimum severity to filter for.
        minutes:  Look-back window in minutes.

    Returns:
        Flat list of log line dicts: {timestamp, stream, line}.
    """
    logql = build_logql(service, severity)
    now   = datetime.now(timezone.utc)
    start = now - timedelta(minutes=minutes)

    raw_streams = await query_range(logql, start=start, end=now)
    return _flatten_streams(raw_streams)


async def fetch_stack_traces(
    service: str,
    minutes: int = 10,
) -> list[str]:
    """
    Fetch stack traces from a service's logs by matching exception lines.

    Args:
        service: Service / job label value.
        minutes: Look-back window in minutes.

    Returns:
        List of raw stack trace strings (multi-line, whitespace-preserved).
    """
    logql = f'{{job="{service}"}} |~ "(Traceback|Exception|Error):"'
    now   = datetime.now(timezone.utc)
    start = now - timedelta(minutes=minutes)

    raw_streams = await query_range(logql, start=start, end=now)
    lines       = _flatten_streams(raw_streams)

    traces: list[str] = []
    current_trace: list[str] = []

    for entry in lines:
        line = entry.get("line", "")
        if any(kw in line for kw in ("Traceback", "Exception", "Error:")):
            if current_trace:
                traces.append("\n".join(current_trace))
            current_trace = [line]
        elif current_trace and (line.startswith("  ") or line.startswith("\t")):
            current_trace.append(line)
        else:
            if current_trace:
                traces.append("\n".join(current_trace))
                current_trace = []

    if current_trace:
        traces.append("\n".join(current_trace))

    return traces


# ── Internal helpers ───────────────────────────────────────────────────────────

def _to_ns(dt: datetime) -> int:
    """Convert a datetime to Loki-compatible nanosecond Unix timestamp."""
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return int((dt - epoch).total_seconds() * 1_000_000_000)


def _flatten_streams(streams: list[dict]) -> list[dict[str, Any]]:
    """
    Flatten Loki stream result into a list of log line dicts.

    Each Loki stream has shape:
        {"stream": {label_dict}, "values": [[ns_timestamp, line_str], ...]}

    Returns:
        List of {"timestamp": datetime, "stream": dict, "line": str}.
    """
    entries: list[dict[str, Any]] = []
    for stream in streams:
        labels = stream.get("stream", {})
        for ts_ns, line in stream.get("values", []):
            ts = datetime.fromtimestamp(int(ts_ns) / 1_000_000_000, tz=timezone.utc)
            entries.append({"timestamp": ts, "stream": labels, "line": line})
    return sorted(entries, key=lambda e: e["timestamp"])
