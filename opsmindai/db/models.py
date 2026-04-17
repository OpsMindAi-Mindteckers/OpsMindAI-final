"""
opsmindai/db/models.py

Tables
──────
  User     — core identity row (Clerk user_id as PK)
  APIKey   — masked API keys belonging to a user
  Project  — top-level grouping owned by a user
  Job      — individual work units (tracks tokens + cost)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id:        Mapped[str] = mapped_column(String, primary_key=True)   # Clerk user_id
    email:     Mapped[str] = mapped_column(String, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String, nullable=True)
    role:      Mapped[str] = mapped_column(String, default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    api_keys = relationship("APIKey",  back_populates="user", cascade="all, delete-orphan")
    jobs     = relationship("Job",     back_populates="user", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")


# ─────────────────────────────────────────────────────────────────────────────
class APIKey(Base):
    __tablename__ = "api_keys"

    key_id:     Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id:    Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    name:       Mapped[str] = mapped_column(String, nullable=False)
    prefix:     Mapped[str] = mapped_column(String, nullable=False)          # first 8 chars
    hashed_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="api_keys")


# ─────────────────────────────────────────────────────────────────────────────
class Project(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id:    Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    name:       Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    user = relationship("User", back_populates="projects")
    jobs = relationship("Job",  back_populates="project")


# ─────────────────────────────────────────────────────────────────────────────
class Job(Base):
    __tablename__ = "jobs"

    job_id:      Mapped[str]   = mapped_column(String, primary_key=True, default=_uuid)
    user_id:     Mapped[str]   = mapped_column(String, ForeignKey("users.id"),        nullable=False)
    project_id:  Mapped[str | None] = mapped_column(String, ForeignKey("projects.project_id"), nullable=True)
    status:      Mapped[str]   = mapped_column(String, default="pending")  # pending|running|done|cancelled
    tokens_used: Mapped[int]   = mapped_column(Integer, default=0)
    cost_usd:    Mapped[float] = mapped_column(Float,   default=0.0)
    created_at:  Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    user    = relationship("User",    back_populates="jobs")
    project = relationship("Project", back_populates="jobs")