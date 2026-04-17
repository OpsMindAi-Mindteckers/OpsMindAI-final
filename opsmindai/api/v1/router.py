"""
opsmindai/api/v1/router.py
Mounts all sub-routers under /api/v1 (prefix set in main.py).
"""

from fastapi import APIRouter

from opsmindai.api.v1.auth import router as auth_router
from opsmindai.api.v1.users import router as users_router

api_router = APIRouter()

api_router.include_router(auth_router)   # /auth/...
api_router.include_router(users_router)  # /users/...