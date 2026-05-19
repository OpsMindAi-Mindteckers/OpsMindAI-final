"""
opsmindai/middleware/logging.py

Structured JSON request/response logging middleware (SRS FR-04).

Every request emits one JSON log line containing:
  request_id   — UUID (from X-Request-ID header or generated)
  method       — HTTP method
  path         — URL path
  status_code  — Response status code
  duration_ms  — Wall-clock duration in milliseconds
  user_id      — From request.state.user_id (set by AuthMiddleware)
  ip           — Client IP address
  user_agent   — User-Agent header

The X-Request-ID header is echoed back in the response so callers can
correlate logs with a specific request.

Usage
─────
Register in main.py AFTER AuthMiddleware so user_id is already in state:

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(AuthMiddleware)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

logger = logging.getLogger("opsmindai.access")

_REQUEST_ID_HEADER = "X-Request-ID"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Structured JSON access-log middleware.

    Injects X-Request-ID into every request and response.
    Logs one JSON line per request at INFO level via the 'opsmindai.access' logger.

    Args:
        app: The ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Resolve or generate a request ID
        request_id: str = (
            request.headers.get(_REQUEST_ID_HEADER)
            or getattr(request.state, "request_id", None)
            or str(uuid.uuid4())
        )
        request.state.request_id = request_id

        start_ts = time.monotonic()

        try:
            response = await call_next(request)
        except Exception as exc:
            _emit(
                request_id  = request_id,
                method      = request.method,
                path        = request.url.path,
                status_code = 500,
                duration_ms = _ms(start_ts),
                user_id     = getattr(request.state, "user_id", None),
                ip          = _ip(request),
                user_agent  = request.headers.get("user-agent", ""),
                error       = str(exc),
            )
            raise

        duration_ms = _ms(start_ts)

        _emit(
            request_id  = request_id,
            method      = request.method,
            path        = request.url.path,
            status_code = response.status_code,
            duration_ms = duration_ms,
            user_id     = getattr(request.state, "user_id", None),
            ip          = _ip(request),
            user_agent  = request.headers.get("user-agent", ""),
        )

        response.headers[_REQUEST_ID_HEADER] = request_id
        return response


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ms(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 2)


def _ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _emit(
    request_id:  str,
    method:      str,
    path:        str,
    status_code: int,
    duration_ms: float,
    user_id:     Optional[str],
    ip:          str,
    user_agent:  str,
    error:       Optional[str] = None,
) -> None:
    record = {
        "event":       "http_request",
        "request_id":  request_id,
        "method":      method,
        "path":        path,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "user_id":     user_id,
        "ip":          ip,
        "user_agent":  user_agent,
    }
    if error:
        record["error"] = error

    if status_code >= 500:
        logger.error(json.dumps(record))
    elif status_code >= 400:
        logger.warning(json.dumps(record))
    else:
        logger.info(json.dumps(record))
