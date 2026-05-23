"""
opsmindai/schemas/refactor.py

Pydantic schemas shared across the Code Refactor agent and API layer.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SmellSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


class SmellType(str, Enum):
    HIGH_COMPLEXITY = "HIGH_COMPLEXITY"
    LONG_METHOD     = "LONG_METHOD"
    TOO_MANY_PARAMS = "TOO_MANY_PARAMS"
    DEEP_NESTING    = "DEEP_NESTING"
    DEAD_CODE       = "DEAD_CODE"
    POOR_NAMING     = "POOR_NAMING"
    GOD_CLASS       = "GOD_CLASS"
    DUPLICATION     = "DUPLICATION"


class JobStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class SmellItem(BaseModel):
    file:       str           = Field(..., description="Relative file path")
    line:       int           = Field(..., description="Line number where the smell starts")
    end_line:   Optional[int] = Field(None, description="Line number where the smell ends")
    smell_type: SmellType     = Field(..., description="Category of code smell")
    severity:   SmellSeverity = Field(..., description="Severity level")
    message:    str           = Field(..., description="Human-readable description")
    symbol:     Optional[str] = Field(None, description="Function / class name affected")
    score:      float         = Field(0.0,  description="Numeric severity score")
    context:    Optional[str] = Field(None, description="Short source snippet around the smell")

    model_config = {"use_enum_values": True}


class PatchFile(BaseModel):
    file:      str = Field(..., description="Relative file path being patched")
    diff:      str = Field(..., description="Unified diff string")
    additions: int = Field(0,   description="Lines added")
    deletions: int = Field(0,   description="Lines removed")
    summary:   str = Field("",  description="One-line description of the change")