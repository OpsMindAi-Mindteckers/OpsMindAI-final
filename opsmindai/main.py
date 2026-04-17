from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from opsmindai.api.v1.router import api_router
from opsmindai.api.v1.auth import limiter
from opsmindai.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="OpsMindAI",
    lifespan=lifespan,
    docs_url=None,  # disable default /docs — we'll serve our own
    swagger_ui_parameters={"persistAuthorization": True},
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(api_router, prefix="/api/v1")

# Serve the Clerk login page
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return RedirectResponse(url="/login")


@app.get("/login")
async def login_page():
    return FileResponse("static/login.html")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_docs():
    """
    Custom Swagger UI that sends cookies with every request.
    This is the key fix — default Swagger doesn't send cookies.
    """
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>OpsMindAI - Swagger</title>
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
                // Force browser to send cookies with every request
                request.credentials = 'include';
                return request;
            },
        });
    </script>
</body>
</html>
    """)