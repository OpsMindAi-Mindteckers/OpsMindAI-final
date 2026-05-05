"""
opsmindai/api/v1/router.py

Mounts all sub-routers under /api/v1 (prefix set in main.py).
"""

import logging

from fastapi import APIRouter

from opsmindai.api.v1.agents import router as agents_router
from opsmindai.api.v1.auth import router as auth_router
from opsmindai.api.v1.projects import router as projects_router
from opsmindai.api.v1.users import router as users_router
from opsmindai.api.v1.incidents import router as incidents_router
logger = logging.getLogger(__name__)

api_router = APIRouter()

api_router.include_router(auth_router)      # /auth/...
api_router.include_router(users_router)     # /users/...
api_router.include_router(agents_router)    # /agents/...
api_router.include_router(projects_router)  # /projects/...
api_router.include_router(incidents_router)   # /incidents/...
