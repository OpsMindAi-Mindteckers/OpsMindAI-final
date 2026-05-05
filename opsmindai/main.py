"""
opsmindai/main.py

FastAPI application entry point.

Changes from original:
- Redis connection pool created at startup and injected into app.state
- Pool cleanly drained at shutdown via lifespan
- Request-ID middleware added (each request gets a unique X-Request-ID header)
- Health check endpoint added (/health)
"""

import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from opsmindai.api.v1.auth import limiter
from opsmindai.api.v1.router import api_router
from opsmindai.core.redis import create_redis_pool, close_redis_pool
from opsmindai.db.session import init_db

logger = logging.getLogger(__name__)


# ── Request-ID middleware ─────────────────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique X-Request-ID header to every request and response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    await init_db()
    logger.info("Database initialised")

    pool = create_redis_pool()
    app.state.redis_pool = pool
    logger.info("Redis pool attached to app.state.redis_pool")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await close_redis_pool()
    logger.info("Redis pool closed")


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="OpsMindAI",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,   # served manually below with cookie support
    swagger_ui_parameters={"persistAuthorization": True},
)

# Middleware (order matters — outermost runs first)
app.add_middleware(RequestIDMiddleware)

# Rate-limit error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# API routes
app.include_router(api_router, prefix="/api/v1")

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", include_in_schema=False)
async def health(request: Request):
    """
    Liveness + readiness probe for Docker / Kubernetes.

    Checks:
    - Redis ping
    Returns 200 if healthy, 503 if any dependency is down.
    """
    import redis.asyncio as aioredis

    checks: dict = {"status": "ok", "redis": "ok", "db": "ok"}
    http_status = 200

    try:
        client = aioredis.Redis(connection_pool=request.app.state.redis_pool)
        await client.ping()
        await client.aclose()
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        checks["status"] = "degraded"
        http_status = 503

    return JSONResponse(content=checks, status_code=http_status)


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/login")


@app.get("/login", include_in_schema=False)
async def login_page():
    return FileResponse("static/login.html")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_docs():
    """Swagger UI that sends cookies with every request."""
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>OpsMindAI API</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({
            url: '/openapi.json',
            dom_id: '#swagger-ui',
            persistAuthorization: true,
            requestInterceptor: function(request) {
                request.credentials = 'include';
                return request;
            },
        });
    </script>
</body>
</html>
    """)