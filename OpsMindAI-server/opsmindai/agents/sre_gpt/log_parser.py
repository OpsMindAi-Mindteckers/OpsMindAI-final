"""
opsmindai/agents/sre_gpt/log_parser.py

Phase P5 — SRS §9.2.

Queries Loki via LogQL for recent error logs from the affected service,
extracts error messages and stack traces, and returns a list of LogLine
objects ready to feed into the RCA engine.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from opsmindai.schemas.incidents import LogLine

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_DEFAULT_LOOKBACK_MIN = 10           # FR-43: last 10 minutes
_LOKI_TIMEOUT_S       = 15
_MAX_LOGS_RETURNED    = 200          # cap response size for prompt safety

# Regex for "looks like an error line"
_ERROR_PATTERNS = re.compile(
    r"\b(error|exception|traceback|panic|fatal|timeout|refused|reset)\b",
    re.IGNORECASE,
)

# Regex for stack-trace continuation lines (whitespace-indented or "at ...")
_STACK_LINE = re.compile(r"^\s+(?:at\s|\w+\s*\(.*\)|File\s+\")")


# ── LogQL helpers ────────────────────────────────────────────────────────────

def _build_query(service: str, severity: str) -> str:
    """
    Build a LogQL query that filters to the service, looks for "error",
    parses logfmt, and filters by level >= severity.

    SRS-specified shape:
        {service="<svc>"} |= "error" | logfmt | level >= "<sev>"
    """
    safe_service = service.replace('"', '\\"')
    safe_sev = severity.replace('"', '\\"')

    # Severity comparison only works if the log already exposes a `level` field.
    # If not, the second clause is a no-op which is fine.
    return (
        f'{{service="{safe_service}"}} '
        f'|= "error" '
        f'| logfmt '
        f'| level=~"{safe_sev}|critical|error|warn"'
    )


def _to_unix_ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


# ── Stack trace extraction ───────────────────────────────────────────────────

def _extract_stack_traces(messages: list[str]) -> list[str]:
    """
    Group consecutive whitespace-indented "stack-like" lines into traces.
    Each trace becomes a single string with newlines preserved.
    """
    traces: list[str] = []
    current: list[str] = []
    in_trace = False

    for line in messages:
        is_stack_continuation = bool(_STACK_LINE.match(line))
        looks_like_error = bool(_ERROR_PATTERNS.search(line))

        if looks_like_error and not is_stack_continuation:
            if current:
                traces.append("\n".join(current))
            current = [line]
            in_trace = True
        elif in_trace and is_stack_continuation:
            current.append(line)
        else:
            if current and len(current) > 1:
                traces.append("\n".join(current))
            current = []
            in_trace = False

    if current and len(current) > 1:
        traces.append("\n".join(current))
    return traces


def _extract_errors(message: str) -> list[str]:
    """Return any error-like phrases from a single log message."""
    if not _ERROR_PATTERNS.search(message):
        return []
    # Split on common delimiters and keep substrings that match
    chunks = re.split(r"[;|\.]\s+", message)
    return [c.strip() for c in chunks if _ERROR_PATTERNS.search(c)]


# ── Public API ────────────────────────────────────────────────────────────────

async def fetch_logs(
    service:  str,
    severity: str,
    minutes:  int = _DEFAULT_LOOKBACK_MIN,
    loki_url: Optional[str] = None,
) -> list[LogLine]:
    """
    Fetch and parse recent error logs for `service` from Loki.

    Args:
        service:  Kubernetes deployment / service label.
        severity: Minimum log level (mapped via LogQL regex match).
        minutes:  Look-back window. Default 10 (per SRS §9.2).
        loki_url: Override LOKI_URL env var.

    Returns:
        List of LogLine, capped at _MAX_LOGS_RETURNED, newest first.
        Returns [] on Loki error rather than raising — RCA can proceed
        without logs if Loki is unreachable.
    """
    base_url = loki_url or os.environ.get("LOKI_URL")
    if not base_url:
        logger.warning("LOKI_URL not set — skipping log fetch for service=%s", service)
        return []

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    params = {
        "query": _build_query(service, severity),
        "start": _to_unix_ns(start),
        "end":   _to_unix_ns(end),
        "limit": _MAX_LOGS_RETURNED,
        "direction": "backward",
    }

    url = f"{base_url.rstrip('/')}/loki/api/v1/query_range"

    try:
        async with httpx.AsyncClient(timeout=_LOKI_TIMEOUT_S) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Loki query failed for service=%s: %s", service, exc)
        return []
    except Exception as exc:
        logger.exception("Unexpected error querying Loki: %s", exc)
        return []

    return _parse_loki_response(data)


def _parse_loki_response(data: dict) -> list[LogLine]:
    """Parse the standard Loki /query_range JSON response into LogLine objects."""
    streams = (data.get("data") or {}).get("result") or []
    log_lines: list[LogLine] = []

    # Collect all messages first so we can group stack traces across the stream
    flat_entries: list[tuple[datetime, str, dict]] = []
    for stream in streams:
        labels = stream.get("stream", {}) or {}
        for ts_ns_str, message in stream.get("values", []):
            try:
                ts = datetime.fromtimestamp(int(ts_ns_str) / 1e9, tz=timezone.utc)
            except (ValueError, TypeError):
                continue
            flat_entries.append((ts, message, labels))

    # Stack traces are grouped over a small sliding window
    flat_entries.sort(key=lambda e: e[0])  # ascending for trace grouping
    messages = [m for _, m, _ in flat_entries]
    stack_traces = _extract_stack_traces(messages)

    # Build LogLine objects (newest first to match `direction=backward`)
    for ts, message, labels in reversed(flat_entries):
        log_lines.append(LogLine(
            timestamp=ts,
            message=message,
            level=str(labels.get("level", "info")).lower(),
            extracted_errors=_extract_errors(message),
            # Attach the full set of traces only to the first line — avoids dup data
            stack_traces=stack_traces if log_lines == [] else [],
        ))

        if len(log_lines) >= _MAX_LOGS_RETURNED:
            break

    logger.info(
        "Fetched %d log line(s) from Loki — %d trace(s) extracted",
        len(log_lines), len(stack_traces),
    )
    return log_lines