"""
opsmindai/api/v1/users/schemas.py
Pydantic v2 request / response models for /api/v1/users endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, field_validator


# ─── #7 / #8  User profile ────────────────────────────────────────────────────

class UserOut(BaseModel):
    user_id:    str
    email:      EmailStr
    full_name:  Optional[str]
    role:       str
    is_active:  bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_user(cls, user) -> "UserOut":
        return cls(
            user_id    = user.id,
            email      = user.email,
            full_name  = user.full_name,
            role       = user.role,
            is_active  = user.is_active,
            created_at = user.created_at,
        )


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email:     Optional[EmailStr] = None

    @field_validator("full_name")
    @classmethod
    def name_not_blank(cls, v):
        if v is not None and not v.strip():
            raise ValueError("full_name cannot be blank")
        return v.strip() if v else v


# ─── #9  Change password ───────────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str

    @field_validator("new_password")
    @classmethod
    def strong_enough(cls, v):
        if len(v) < 8:
            raise ValueError("new_password must be at least 8 characters")
        return v


# ─── #10  Delete account ──────────────────────────────────────────────────────

class DeleteAccountRequest(BaseModel):
    confirm: bool

    @field_validator("confirm")
    @classmethod
    def must_confirm(cls, v):
        if not v:
            raise ValueError("confirm must be true to delete the account")
        return v


# ─── #11  API keys ────────────────────────────────────────────────────────────

class APIKeyOut(BaseModel):
    key_id:     str
    name:       str
    prefix:     str
    created_at: datetime
    expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── #12  Usage summary ───────────────────────────────────────────────────────

class MonthUsage(BaseModel):
    total_jobs:         int
    total_tokens_used:  int
    estimated_cost_usd: float


class UsageOut(BaseModel):
    total_projects:     int
    total_jobs:         int
    total_tokens_used:  int
    estimated_cost_usd: float
    this_month:         MonthUsage


# ─── Generic ──────────────────────────────────────────────────────────────────

class MessageOut(BaseModel):
    message: str