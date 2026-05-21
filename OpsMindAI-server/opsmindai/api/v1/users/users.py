"""
opsmindai/api/v1/users/router.py

GROUP 2 — USER ACCOUNT  (/api/v1/users)
────────────────────────────────────────────────────────────────────────────
 #7   GET    /me                  — get own profile
 #8   PATCH  /me                  — update name / email
 #9   POST   /me/change-password  — change password via Clerk Backend API
 #10  DELETE /me                  — soft-delete (is_active=False) + cancel jobs
 #11  GET    /me/api-keys         — list API keys (values masked)
 #12  GET    /me/usage            — usage summary (jobs, tokens, projects, cost)
────────────────────────────────────────────────────────────────────────────

Auth   : every endpoint uses get_current_user from opsmindai.api.v1.auth
         (Bearer JWT or cookie — Clerk session verified)
Async  : all DB calls use AsyncSession (aiosqlite)
"""

from datetime import datetime, timezone
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import extract, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opsmindai.api.v1.auth import get_current_user, _headers, CLERK_API
from opsmindai.core.config import settings
from opsmindai.db.models import APIKey, Job, Project, User
from opsmindai.db.session import get_db
from .schemas import (
    APIKeyOut,
    ChangePasswordRequest,
    DeleteAccountRequest,
    MessageOut,
    UsageOut,
    MonthUsage,
    UserOut,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["User Account"])
limiter = Limiter(key_func=get_remote_address)


# ─────────────────────────────────────────────────────────────────────────────
# Clerk helper — change password via Backend API
# ─────────────────────────────────────────────────────────────────────────────

async def _clerk_change_password(
    user_id: str,
    current_password: str,
    new_password: str,
) -> None:
    """
    1. Verify current password.
    2. Push new password via PATCH /users/{id}.
    Raises HTTP 400 / 401 on failure.
    """
    async with httpx.AsyncClient(timeout=15) as c:
        # Step 1 — verify current password
        verify = await c.post(
            f"{CLERK_API}/users/{user_id}/verify_password",
            headers=_headers(),
            json={"password": current_password},
        )
    if verify.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if current_password == new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from the current password",
        )

    async with httpx.AsyncClient(timeout=15) as c:
        # Step 2 — update to new password
        patch = await c.patch(
            f"{CLERK_API}/users/{user_id}",
            headers=_headers(),
            json={"password": new_password, "skip_password_checks": False},
        )
    if patch.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=patch.json().get("errors", "Failed to update password"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# #7  GET /api/v1/users/me
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=UserOut,
    summary="#7 — Get current user profile",
)
@limiter.limit("120/minute")
async def get_my_profile(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Returns the authenticated user's full profile.

    - **Auth**: Bearer JWT or cookie
    - **Rate**: 120 / min
    """
    return UserOut.from_orm_user(current_user)


# ─────────────────────────────────────────────────────────────────────────────
# #8  PATCH /api/v1/users/me
# ─────────────────────────────────────────────────────────────────────────────
@router.patch(
    "/me",
    response_model=UserOut,
    summary="#8 — Update profile details",
)
@limiter.limit("20/hour")
async def update_my_profile(
    request: Request,
    body: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update `full_name` and / or `email`. Also syncs the change to Clerk.

    - **Auth**: Bearer JWT or cookie
    - **Rate**: 20 / hr
    """
    # ── email uniqueness check ────────────────────────────────────────────────
    if body.email and body.email != current_user.email:
        result = await db.execute(
            select(User).where(User.email == body.email, User.id != current_user.id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use by another account",
            )

    # ── build Clerk PATCH payload ─────────────────────────────────────────────
    clerk_payload: dict = {}
    if body.full_name is not None:
        first, _, last = body.full_name.partition(" ")
        clerk_payload["first_name"] = first or body.full_name
        clerk_payload["last_name"]  = last
        current_user.full_name = body.full_name

    if body.email:
        # Clerk requires adding a new email_address object, so we sync display
        # name only and update local DB; for full email-change flow the user
        # should go through Clerk's email-verification UI.
        current_user.email = body.email

    # ── sync to Clerk (best-effort) ───────────────────────────────────────────
    if clerk_payload:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.patch(
                f"{CLERK_API}/users/{current_user.id}",
                headers=_headers(),
                json=clerk_payload,
            )
        if r.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Clerk sync failed: {r.text}",
            )

    await db.commit()
    await db.refresh(current_user)
    return UserOut.from_orm_user(current_user)


# ─────────────────────────────────────────────────────────────────────────────
# #9  POST /api/v1/users/me/change-password
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/me/change-password",
    response_model=MessageOut,
    summary="#9 — Change account password",
)
@limiter.limit("5/hour")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Changes password through Clerk's Backend API.
 
    - **Auth**: Bearer JWT or cookie
    - **Rate**: 5 / hr
    - Requires the current password for verification.
    """
    await _clerk_change_password(
        user_id          = current_user.id,
        current_password = body.current_password,
        new_password     = body.new_password,
    )
 
    # Security: revoke ALL active sessions so the old password
    # can never be used to resume an existing Clerk session.
    from opsmindai.api.v1.auth import _clerk_revoke_all_user_sessions
    revoked = await _clerk_revoke_all_user_sessions(current_user.id)
    print(f"[change-password] revoked {revoked} session(s) for user {current_user.id}")
 
    return MessageOut(message="Password updated. Please log in again with your new password.")
 
# ─────────────────────────────────────────────────────────────────────────────
# #10  DELETE /api/v1/users/me
# ─────────────────────────────────────────────────────────────────────────────
@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="#10 — Soft-delete account",
)
@limiter.limit("1/day")
async def delete_my_account(
    request: Request,
    body: DeleteAccountRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-deletes the account (`is_active = False`) and bulk-cancels all
    pending / running jobs. Also clears the auth cookie.

    - **Auth**: Bearer JWT or cookie
    - **Rate**: 1 / day
    - Body must include `{ "confirm": true }`
    """
    # Cancel active jobs
    await db.execute(
        update(Job)
        .where(Job.user_id == current_user.id, Job.status.in_(["pending", "running"]))
        .values(status="cancelled")
    )

    # Soft-delete the user
    current_user.is_active = False
    await db.commit()

    # Clear auth cookie (matches COOKIE_NAME in auth.py)
    response.delete_cookie(key="opsmindai_token", path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────────────────
# #11  GET /api/v1/users/me/api-keys
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/me/api-keys",
    response_model=List[APIKeyOut],
    summary="#11 — List API keys (masked)",
)
@limiter.limit("60/minute")
async def list_my_api_keys(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all API keys for the authenticated user.
    The raw key value is **never** returned — only `prefix` (first 8 chars).

    - **Auth**: Bearer JWT or cookie
    - **Rate**: 60 / min
    """
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == current_user.id)
        .order_by(APIKey.created_at.desc())
    )
    return result.scalars().all()


# ─────────────────────────────────────────────────────────────────────────────
# #12  GET /api/v1/users/me/usage
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/me/usage",
    response_model=UsageOut,
    summary="#12 — Usage summary",
)
@limiter.limit("60/minute")
async def get_my_usage(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns aggregated usage stats — all-time and for the current calendar month.

    - **Auth**: Bearer JWT or cookie
    - **Rate**: 60 / min
    """
    uid = current_user.id
    now = datetime.now(timezone.utc)

    # ── Total projects ────────────────────────────────────────────────────────
    proj_count = (
        await db.execute(
            select(func.count(Project.project_id)).where(Project.user_id == uid)
        )
    ).scalar_one()

    # ── All-time job aggregates ───────────────────────────────────────────────
    all_time = (
        await db.execute(
            select(
                func.count(Job.job_id).label("jobs"),
                func.coalesce(func.sum(Job.tokens_used), 0).label("tokens"),
                func.coalesce(func.sum(Job.cost_usd),    0.0).label("cost"),
            ).where(Job.user_id == uid)
        )
    ).one()

    # ── This-month job aggregates ─────────────────────────────────────────────
    this_month = (
        await db.execute(
            select(
                func.count(Job.job_id).label("jobs"),
                func.coalesce(func.sum(Job.tokens_used), 0).label("tokens"),
                func.coalesce(func.sum(Job.cost_usd),    0.0).label("cost"),
            ).where(
                Job.user_id == uid,
                extract("year",  Job.created_at) == now.year,
                extract("month", Job.created_at) == now.month,
            )
        )
    ).one()

    return UsageOut(
        total_projects     = proj_count,
        total_jobs         = all_time.jobs,
        total_tokens_used  = all_time.tokens,
        estimated_cost_usd = round(float(all_time.cost), 6),
        this_month=MonthUsage(
            total_jobs         = this_month.jobs,
            total_tokens_used  = this_month.tokens,
            estimated_cost_usd = round(float(this_month.cost), 6),
        ),
    )