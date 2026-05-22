"""
opsmindai/middleware/auth.py

Bearer-token / API-key presence middleware (SRS §5.3, FR-05).

What it does
────────────
• Runs before every request.
• Skip list: /health, /metrics, /webhooks/*, /docs, /openapi.json, /login,
  /static/*, /auth/* (auth routes handle their own logic).
• For all other routes: require a Bearer token in the Authorization header
  OR the opsmindai_token cookie.
• If absent → 401 immediately (saves expensive DB/Clerk round-trip).
• If present → decode JWT to extract user_id and attach to request.state
  so downstream handlers can read it cheaply without re-decoding.

Full cryptographic verification happens inside get_current_user (Clerk API call).
This layer is purely a fast early-exit for unauthenticated requests.
"""

from __future__ import annotations

import logging
from typing import Optional

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

_COOKIE_NAME = "opsmindai_token"

# Exact path prefixes that bypass auth middleware
_SKIP_PREFIXES = (
    "/health",
    "/metrics",
    "/webhooks/",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/login",
    "/static/",
    "/api/v1/auth/",     # login, register, set-cookie, clear-cookie
    "/api/v1/webhooks/", # webhook routes use HMAC, not Bearer
)


def _should_skip(path: str) -> bool:
    if path == "/":
        return True
    return any(path.startswith(prefix) for prefix in _SKIP_PREFIXES)


def _extract_token(request: Request) -> Optional[str]:
    """Pull Bearer token from Authorization header or opsmindai_token cookie."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get(_COOKIE_NAME)


def _decode_token(token: str) -> Optional[dict]:
    """
    Decode JWT without signature verification to extract claims.
    Signature is verified downstream by Clerk API.
    """
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Credentials": "true",
}
class AuthMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that enforces token presence on all protected routes.

    Attaches to request.state:
      - request.state.user_id  (str | None)
      - request.state.token    (str | None)

    Args:
        app: The ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path

        if _should_skip(path):
            request.state.user_id = None
            request.state.token   = None
            return await call_next(request)

        token = _extract_token(request)

        if not token:
            logger.warning(
                "auth middleware: missing token path=%s ip=%s",
                path, request.client.host if request.client else "unknown",
                
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Bearer token or auth cookie"},
                headers=_CORS_HEADERS,
            )

        claims = _decode_token(token)
        if claims is None:
            logger.warning("auth middleware: malformed token path=%s", path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Malformed token"},
                headers=_CORS_HEADERS,
            )

        # Attach cheap claims to state — full verification by get_current_user
        request.state.user_id = claims.get("sub")
        request.state.token   = token

        logger.debug(
            "auth middleware: ok user_id=%s path=%s",
            request.state.user_id, path,
        )
        return await call_next(request)
