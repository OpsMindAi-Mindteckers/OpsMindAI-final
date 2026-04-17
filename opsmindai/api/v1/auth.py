"""
opsmindai/api/v1/auth.py

- /register  -> creates user via Clerk Backend API + local DB row + sets cookie
- /login     -> smart login: detects existing auth (cookie/Bearer) OR password login + sets cookie
- /logout    -> revokes ALL active sessions (global logout) + clears cookie
- /set-cookie -> sets the shared auth cookie after Clerk frontend sign-in
- /clear-cookie -> clears the auth cookie
- get_current_user -> checks Bearer token OR cookie, verifies via Clerk
"""
from typing import Optional
import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from opsmindai.core.config import settings
from opsmindai.db.models import User
from opsmindai.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)
bearer_scheme = HTTPBearer(auto_error=False)

CLERK_API = "https://api.clerk.com/v1"
COOKIE_NAME = "opsmindai_token"


def _headers():
    return {
        "Authorization": f"Bearer {settings.CLERK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def _set_auth_cookie(response: Response, token: str) -> None:
    """Single source of truth for cookie settings — used everywhere."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=False,    # JS can read it (so /login page can detect/clear it)
        samesite="lax",    # works for same-origin Swagger + page
        max_age=3600,      # 1 hour
        path="/",          # available to every route
    )


# ---------- Pydantic schemas ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class LoginIn(BaseModel):
    # BOTH optional — empty body {} is valid for "am I already logged in?" check
    email: Optional[EmailStr] = None
    password: Optional[str] = None


class TokenOut(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = 3600


class RegisterOut(TokenOut):
    user_id: str


class LoginOut(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = 3600
    already_logged_in: bool = False
    message: str
    user_email: Optional[str] = None


# ---------- Clerk Backend API helpers ----------
async def _clerk_create_user(email: str, password: str, full_name: str) -> dict:
    first, _, last = full_name.partition(" ")
    payload = {
        "email_address": [email],
        "password": password,
        "first_name": first or full_name,
        "last_name": last,
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{CLERK_API}/users", headers=_headers(), json=payload)
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.json())
    return r.json()


async def _clerk_find_user_by_email(email: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{CLERK_API}/users",
            headers=_headers(),
            params=[("email_address", email)],
        )
    if r.status_code >= 400:
        print(f"[Clerk find user error] {r.status_code}: {r.text}")
        return None
    data = r.json()
    return data[0] if data else None


async def _clerk_verify_password(user_id: str, password: str) -> bool:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{CLERK_API}/users/{user_id}/verify_password",
            headers=_headers(),
            json={"password": password},
        )
    return r.status_code == 200


async def _clerk_create_session(user_id: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{CLERK_API}/sessions",
            headers=_headers(),
            json={"user_id": user_id},
        )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.json())
    return r.json()


async def _clerk_session_token(session_id: str) -> str:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{CLERK_API}/sessions/{session_id}/tokens",
            headers=_headers(),
        )
    r.raise_for_status()
    return r.json()["jwt"]


async def _clerk_get_user_email(user_id: str) -> str:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{CLERK_API}/users/{user_id}", headers=_headers())
    if r.status_code != 200:
        return ""
    emails = r.json().get("email_addresses") or []
    return emails[0].get("email_address", "") if emails else ""


async def _clerk_revoke_all_user_sessions(user_id: str) -> int:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{CLERK_API}/sessions",
            headers=_headers(),
            params={"user_id": user_id, "status": "active"},
        )
        if r.status_code >= 400:
            print(f"[logout] list sessions failed: {r.status_code} {r.text}")
            return 0

        sessions = r.json()
        count = 0
        for session in sessions:
            sid = session["id"]
            rev = await c.post(
                f"{CLERK_API}/sessions/{sid}/revoke",
                headers=_headers(),
            )
            if rev.status_code < 400:
                count += 1
                print(f"[logout] revoked session {sid}")
            else:
                print(f"[logout] failed to revoke {sid}: {rev.text}")
        return count


# ---------- Dependency: verify token via Clerk session lookup ----------
async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    # Try Bearer first, fall back to cookie
    token = None
    if creds:
        token = creds.credentials
        print("[auth] using Bearer token")
    elif request.cookies.get(COOKIE_NAME):
        token = request.cookies.get(COOKIE_NAME)
        print("[auth] using cookie token")

    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token or auth cookie")

    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        print(f"[auth] decoded: sub={payload.get('sub')} sid={payload.get('sid')}")
    except Exception as e:
        print(f"[auth] decode failed: {e}")
        raise HTTPException(401, f"Malformed token: {e}")

    sid = payload.get("sid")
    user_id_from_token = payload.get("sub")

    if not user_id_from_token:
        raise HTTPException(401, "Token has no user ID (sub)")

    user_id: Optional[str] = None

    if sid:
        async with httpx.AsyncClient(timeout=10) as c:
            sr = await c.get(f"{CLERK_API}/sessions/{sid}", headers=_headers())
        if sr.status_code >= 400:
            raise HTTPException(401, "Session not found")
        session_data = sr.json()
        if session_data.get("status") != "active":
            raise HTTPException(401, f"Session {session_data.get('status')}")
        user_id = session_data["user_id"]
        print(f"[auth] verified session {sid} for user {user_id}")
    else:
        print(f"[auth] no sid in token, looking up sessions for {user_id_from_token}")
        async with httpx.AsyncClient(timeout=10) as c:
            sr = await c.get(
                f"{CLERK_API}/sessions",
                headers=_headers(),
                params={"user_id": user_id_from_token, "status": "active"},
            )
        if sr.status_code >= 400:
            raise HTTPException(401, "Could not verify user sessions")
        sessions = sr.json()
        if not sessions:
            raise HTTPException(401, "No active session for user")
        sid = sessions[0]["id"]
        user_id = user_id_from_token
        print(f"[auth] picked active session {sid} for user {user_id}")

    if not user_id:
        raise HTTPException(401, "Could not determine user_id")

    # Load local user row — auto-provision for OAuth users
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()

    if not user:
        print(f"[auth] auto-provisioning user {user_id}")
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{CLERK_API}/users/{user_id}", headers=_headers())
        if r.status_code != 200:
            raise HTTPException(401, "User not found on Clerk")
        cu = r.json()
        emails = cu.get("email_addresses") or []
        email = emails[0].get("email_address", "") if emails else ""
        first = cu.get("first_name") or ""
        last = cu.get("last_name") or ""
        full_name = f"{first} {last}".strip() or email or "Unknown"
        user = User(id=user_id, email=email, full_name=full_name)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"[auth] auto-provisioned user {user_id} ({email})")

    if user is None:
        raise HTTPException(500, "Failed to load or create user")

    user.__dict__["_sid"] = sid
    return user


# ---------- Endpoints ----------
@router.post("/register", status_code=201, response_model=RegisterOut)
@limiter.limit("10/hour")
async def register(
    request: Request,
    body: RegisterIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    clerk_user = await _clerk_create_user(body.email, body.password, body.full_name)
    user = User(id=clerk_user["id"], email=body.email, full_name=body.full_name)
    db.add(user)
    await db.commit()

    session = await _clerk_create_session(clerk_user["id"])
    token = await _clerk_session_token(session["id"])

    _set_auth_cookie(response, token)

    return RegisterOut(
        user_id=user.id,
        access_token=token,
        refresh_token=session["id"],
        expires_in=3600,
    )


@router.post("/login", response_model=LoginOut)
@limiter.limit("20/hour")
async def login(
    request: Request,
    response: Response,
    body: LoginIn,
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    Smart login:
    - Already authenticated (Bearer/cookie) → returns "already logged in" + fresh token.
    - Otherwise → requires email + password.
    Always sets the shared auth cookie on success so all UIs share the session.
    """
    # Step 1: detect existing auth
    existing_token = None
    if creds:
        existing_token = creds.credentials
        print("[login] checking Bearer token...")
    elif request.cookies.get(COOKIE_NAME):
        existing_token = request.cookies.get(COOKIE_NAME)
        print("[login] checking cookie token...")

    if existing_token:
        try:
            payload = jwt.decode(existing_token, options={"verify_signature": False})
            sid = payload.get("sid")
            user_id = payload.get("sub")
            print(f"[login] existing token: sub={user_id} sid={sid}")

            active_sid = None
            if sid:
                async with httpx.AsyncClient(timeout=10) as c:
                    sr = await c.get(f"{CLERK_API}/sessions/{sid}", headers=_headers())
                if sr.status_code < 400 and sr.json().get("status") == "active":
                    active_sid = sid

            if not active_sid and user_id:
                async with httpx.AsyncClient(timeout=10) as c:
                    sr = await c.get(
                        f"{CLERK_API}/sessions",
                        headers=_headers(),
                        params={"user_id": user_id, "status": "active"},
                    )
                if sr.status_code < 400:
                    sessions = sr.json()
                    if sessions:
                        active_sid = sessions[0]["id"]

            if active_sid:
                fresh_token = await _clerk_session_token(active_sid)
                user_email = await _clerk_get_user_email(user_id)

                _set_auth_cookie(response, fresh_token)

                print(f"[login] already authenticated as {user_email}")
                return LoginOut(
                    access_token=fresh_token,
                    refresh_token=active_sid,
                    expires_in=3600,
                    already_logged_in=True,
                    message=f" You are already logged in as {user_email}",
                    user_email=user_email,
                )
            else:
                print("[login] token present but no active session — falling through to password")
        except Exception as e:
            print(f"[login] existing token check failed: {e} — falling through to password")

    # Step 2: no valid auth — require email + password
    if not body.email or not body.password:
        raise HTTPException(
            400,
            "Not logged in. Provide email + password, or sign in via /login page first.",
        )

    try:
        clerk_user = await _clerk_find_user_by_email(body.email)
        print(f"[login] found user: {clerk_user.get('id') if clerk_user else None}")
        if not clerk_user:
            raise HTTPException(401, "Invalid credentials")

        ok = await _clerk_verify_password(clerk_user["id"], body.password)
        print(f"[login] password ok: {ok}")
        if not ok:
            raise HTTPException(401, "Invalid credentials")

        session = await _clerk_create_session(clerk_user["id"])
        token = await _clerk_session_token(session["id"])

        _set_auth_cookie(response, token)

        return LoginOut(
            access_token=token,
            refresh_token=session["id"],
            expires_in=3600,
            already_logged_in=False,
            message=f"Logged in as {body.email}",
            user_email=body.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Login error: {e}")


@router.post("/set-cookie", status_code=200)
async def set_cookie_after_clerk_signin(
    request: Request,
    response: Response,
):
    """
    Called by the /login page after Clerk frontend sign-in.
    Does NOT use get_current_user (which might read the old cookie).
    Instead, reads the Bearer token directly from the Authorization header.
    """
    # Always clear old cookie first — prevents stale session conflicts
    response.delete_cookie(key=COOKIE_NAME, path="/")

    # Read the Bearer token from the Authorization header
    creds = await bearer_scheme(request)
    if not creds:
        raise HTTPException(400, "Bearer token required")

    token = creds.credentials

    # Quick validation: decode to get user_id, verify with Clerk
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub")
        sid = payload.get("sid")
        print(f"[set-cookie] decoded: sub={user_id} sid={sid}")
    except Exception as e:
        raise HTTPException(400, f"Invalid token: {e}")

    if not user_id:
        raise HTTPException(400, "Token has no user ID")

    # Verify the user exists on Clerk
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{CLERK_API}/users/{user_id}", headers=_headers())
    if r.status_code != 200:
        raise HTTPException(401, "User not found on Clerk")

    user_email = ""
    emails = r.json().get("email_addresses") or []
    if emails:
        user_email = emails[0].get("email_address", "")

    # Set the NEW cookie
    _set_auth_cookie(response, token)
    print(f"[set-cookie] ✅ cookie set for {user_email} (replaces any previous)")

    return {"status": "cookie set", "user_email": user_email}

@router.post("/clear-cookie", status_code=200)
async def clear_auth_cookie(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    print("[clear-cookie] cookie cleared")
    return {"status": "cookie cleared"}


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    """
    Global logout — revokes ALL active sessions for the user across
    every device/browser/UI. Also clears the shared cookie.
    """
    revoked = await _clerk_revoke_all_user_sessions(user.id)
    print(f"[logout] user={user.id} revoked {revoked} sessions")
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return