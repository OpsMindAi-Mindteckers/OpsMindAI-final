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
from datetime import datetime, timedelta, timezone
import secrets
import hashlib

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from opsmindai.core.config import settings
from opsmindai.db.models import User, APIKey
from opsmindai.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

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
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    username: Optional[str] = None



class LoginIn(BaseModel):
    # BOTH optional — empty body {} is valid for "am I already logged in?" check
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    username: Optional[str] = None


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
    username: Optional[str] = None

class ApiKeyIn(BaseModel):
    name: str


class ApiKeyOut(BaseModel):
    key_id: str
    api_key: str                           # shown ONCE — full plaintext key
    name: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    message: str = "Save this key now — you won't see it again."

# ---------- Clerk Backend API helpers ----------
async def _clerk_create_user(email: str, password: str, username: str) -> dict:
    payload = {
        "email_address": [email],
        "password": password,
        "username": username,
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
async def _clerk_find_user_by_username(username: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{CLERK_API}/users",
            headers=_headers(),
            params=[("username", username)],
        )
    if r.status_code >= 400:
        print(f"[Clerk find user by username error] {r.status_code}: {r.text}")
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

# ---------- API Key helpers ----------
def _generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns (raw_key, prefix, hashed_key):
      - raw_key    → full plaintext, shown to user ONCE (never stored)
      - prefix     → first 8 chars of raw_key, stored for display ("opsm_liv")
      - hashed_key → SHA-256 hash, stored for verification
    """
    random_part = secrets.token_urlsafe(32)
    raw_key = f"opsm_live_{random_part}"
    prefix = raw_key[:8]
    hashed_key = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, prefix, hashed_key


'''def _hash_api_key(raw_key: str) -> str:
    """Hash a raw API key for comparison with stored hash."""
    return hashlib.sha256(raw_key.encode()).hexdigest()'''

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
    db: AsyncSession = Depends(get_db),
) -> User:
    # Try Bearer first, fall back to cookie
    token = request.cookies.get(COOKIE_NAME)  # default to cookie for logging
    if token:
        print("[auth] using cookie token")
    if not token:
        # Fallback: check Authorization header (for API clients like curl/Postman)
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            print("[auth] using Bearer token from header")


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

    # ── DEVELOPMENT MODE: Skip Clerk verification for test tokens ──
    is_test_token = user_id_from_token.startswith("test_") or (sid and sid.startswith("test_"))
    
    if is_test_token:
        print(f"[auth] 🧪 TEST TOKEN DETECTED — skipping Clerk verification")
        user_id = user_id_from_token
    elif sid:
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

    # Load local user row — auto-provision for OAuth/test users
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()

    if not user:
        print(f"[auth] auto-provisioning user {user_id}")
        
        # For test users, skip Clerk lookup
        if is_test_token:
            email = f"{user_id}@test.local"
            full_name = "Test User"
        else:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"{CLERK_API}/users/{user_id}", headers=_headers())
            if r.status_code != 200:
                raise HTTPException(401, "User not found on Clerk")
            cu = r.json()
            emails = cu.get("email_addresses") or []
            email = emails[0].get("email_address", "") if emails else ""
            full_name = cu.get("first_name", "") + " " + cu.get("last_name", "")
        
        user = User(id=user_id, email=email, full_name=full_name.strip() or None)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"[auth] auto-provisioned user {user_id} ({email})")

    if user is None:
        raise HTTPException(500, "Failed to load or create user")

    user.__dict__["_sid"] = sid
    return user



# ---------- Test/Dev Endpoints ----------
@router.get("/test-token", tags=["auth"])
async def get_test_token(db: AsyncSession = Depends(get_db)):
    """
    🧪 DEVELOPMENT ONLY: Generate a test JWT token without authentication.
    This endpoint is used for testing the API without Clerk setup.
    Returns a valid token that can be used as Bearer token for other endpoints.
    """
    test_user_id = "test_user_dev"
    test_session_id = "test_session_dev"
    
    # Create a valid JWT token (without Clerk verification)
    payload = {
        "sub": test_user_id,
        "sid": test_session_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.API_SECRET_KEY or "dev-secret", algorithm="HS256")
    
    # Auto-provision test user in database
    res = await db.execute(select(User).where(User.id == test_user_id))
    user = res.scalar_one_or_none()
    if not user:
        user = User(
            id=test_user_id,
            email="test@example.com",
            full_name="Test User",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"[test-token] auto-provisioned test user {test_user_id}")
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600,
        "test_user": test_user_id,
        "message": "🧪 Test token generated. Use as: Authorization: Bearer {access_token}",
    }


# ---------- Endpoints ----------
@router.post("/register", status_code=201, response_model=RegisterOut)
@limiter.limit("10/hour")
async def register(
    request: Request,
    body: RegisterIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    clerk_user = await _clerk_create_user(body.email, body.password, body.username)
    user = User(id=clerk_user["id"], email=body.email)
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
    db: AsyncSession = Depends(get_db),
):
    """
    Smart login:
    - Already authenticated (Bearer/cookie) → returns "already logged in" + fresh token.
    - Otherwise → requires email + password.
    Always sets the shared auth cookie on success so all UIs share the session.
    """
    # Step 1: detect existing auth
    existing_token = request.cookies.get(COOKIE_NAME)
    if existing_token:
        print("[login] checking cookie token...")
    else:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            existing_token = auth_header[7:]
            print("[login] checking Bearer token from header...")

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
                user_username = ""
                async with httpx.AsyncClient(timeout=10) as c:
                    ur2 = await c.get(f"{CLERK_API}/users/{user_id}", headers=_headers())
                if ur2.status_code == 200:
                    user_username = ur2.json().get("username") or ""

                identifier = user_email or user_username
                return LoginOut(
                    access_token=fresh_token,
                    refresh_token=active_sid,
                    expires_in=3600,
                    already_logged_in=True,
                    message=f" You are already logged in as {user_email}",
                    user_email=user_email,
                    username=user_username,
                )
            else:
                print("[login] token present but no active session — falling through to password")
        except Exception as e:
            print(f"[login] existing token check failed: {e} — falling through to password")

    # Step 2: no valid auth — require email + password
    # Step 2: no valid auth — require (email OR username) + password
    if not body.password:
        raise HTTPException(400, "Not logged in. Provide (email or username) + password, or sign in via /login page first.")

    if not body.email and not body.username:
        raise HTTPException(400, "Provide either email or username along with password.")

    try:
        # Find user by email OR username
        clerk_user = None
        if body.email:
            clerk_user = await _clerk_find_user_by_email(body.email)
            print(f"[login] found by email: {clerk_user.get('id') if clerk_user else None}")
        elif body.username:
            clerk_user = await _clerk_find_user_by_username(body.username)
            print(f"[login] found by username: {clerk_user.get('id') if clerk_user else None}")

        if not clerk_user:
            raise HTTPException(401, "Invalid credentials")

        ok = await _clerk_verify_password(clerk_user["id"], body.password)
        print(f"[login] password ok: {ok}")
        if not ok:
            raise HTTPException(401, "Invalid credentials")

        session = await _clerk_create_session(clerk_user["id"])
        token = await _clerk_session_token(session["id"])

        # Get email and username from Clerk
        user_email = (clerk_user.get("email_addresses") or [{}])[0].get("email_address", "")
        user_username = clerk_user.get("username") or ""

        _set_auth_cookie(response, token)

        identifier = user_email or user_username
        return LoginOut(
            access_token=token,
            refresh_token=session["id"],
            expires_in=3600,
            already_logged_in=False,
            message=f"✅ Logged in as {identifier}",
            user_email=user_email,
            username=user_username,
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
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(400, "Bearer token required")
    token = auth_header[7:]

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
    print(f"[set-cookie] cookie set for {user_email} (replaces any previous)")

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
# ---------- /api-key POST ----------
@router.post("/api-key", status_code=201, response_model=ApiKeyOut)
@limiter.limit("5/day")
async def create_api_key(
    request: Request,
    body: ApiKeyIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a long-lived API key for programmatic access.
    The full key is returned ONCE — only its hash is stored.
    Use the key in future requests as:  Authorization: Bearer opsm_live_xxx
    """
    if not body.name or len(body.name.strip()) == 0:
        raise HTTPException(400, "name is required")

    # Generate key components
    raw_key, prefix, hashed_key = _generate_api_key()

    # Default expiry: 1 year from now
    expires = datetime.now(timezone.utc) + timedelta(days=365)

    # Save only hash + prefix to DB (never the raw key)
    api_key = APIKey(
        user_id=user.id,
        name=body.name.strip(),
        prefix=prefix,
        hashed_key=hashed_key,
        expires_at=expires,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    print(f"[api-key]  created key {api_key.key_id} for user {user.id}")
    return ApiKeyOut(
        key_id=api_key.key_id,
        api_key=raw_key,                        # full key shown ONCE
        name=api_key.name,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


# ---------- /api-key DELETE ----------
@router.delete("/api-key/{key_id}", status_code=204)
@limiter.limit("20/hour")
async def delete_api_key(
    request: Request,
    key_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently revoke and delete an API key.
    Users can only delete their own keys.
    """
    res = await db.execute(select(APIKey).where(APIKey.key_id == key_id))
    api_key = res.scalar_one_or_none()

    if not api_key:
        raise HTTPException(404, "API key not found")

    if api_key.user_id != user.id:
        raise HTTPException(403, "Not your API key")

    await db.delete(api_key)
    await db.commit()

    print(f"[api-key] deleted key {key_id} for user {user.id}")
    return