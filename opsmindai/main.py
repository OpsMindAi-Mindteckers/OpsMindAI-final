from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

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