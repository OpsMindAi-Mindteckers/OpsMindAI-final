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
    # ── Original 8 ───────────────────────────────────────────────────────────
    HIGH_COMPLEXITY     = "HIGH_COMPLEXITY"
    LONG_METHOD         = "LONG_METHOD"
    TOO_MANY_PARAMS     = "TOO_MANY_PARAMS"
    DEEP_NESTING        = "DEEP_NESTING"
    DEAD_CODE           = "DEAD_CODE"
    POOR_NAMING         = "POOR_NAMING"
    GOD_CLASS           = "GOD_CLASS"
    DUPLICATION         = "DUPLICATION"
    # ── New: correctness ──────────────────────────────────────────────────────
    SYNTAX_ERROR        = "SYNTAX_ERROR"        # invalid Python syntax
    UNDEFINED_NAME      = "UNDEFINED_NAME"      # name used but not imported/defined
    MISSING_INIT        = "MISSING_INIT"        # self.attr used but not set in __init__
    MUTABLE_DEFAULT_ARG = "MUTABLE_DEFAULT_ARG" # def f(x=[]) — shared mutable default
    UNREACHABLE_CODE    = "UNREACHABLE_CODE"    # code after return/raise/break
    # ── New: error handling ───────────────────────────────────────────────────
    BARE_EXCEPT         = "BARE_EXCEPT"         # except: without type
    EMPTY_EXCEPT        = "EMPTY_EXCEPT"        # except ...: pass
    BROAD_EXCEPTION     = "BROAD_EXCEPTION"     # except Exception without re-raise
    # ── New: security / maintainability ──────────────────────────────────────
    HARDCODED_SECRET    = "HARDCODED_SECRET"    # password/token in source
    SHADOWED_BUILTIN    = "SHADOWED_BUILTIN"    # variable shadows len/list/str etc.
    PRINT_STATEMENT     = "PRINT_STATEMENT"     # print() instead of logging
    MAGIC_NUMBER        = "MAGIC_NUMBER"        # unexplained numeric literal


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
    context:    Optional[str] = Field(None, description="Code snippet showing the issue")

    model_config = {"use_enum_values": True}


class PatchFile(BaseModel):
    file:      str = Field(..., description="Relative file path being patched")
    diff:      str = Field(..., description="Unified diff string")
    additions: int = Field(0,   description="Lines added")
    deletions: int = Field(0,   description="Lines removed")
    summary:   str = Field("",  description="One-line description of the change")
