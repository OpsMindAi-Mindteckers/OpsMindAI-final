"""
opsmindai/agents/refactor/smell_detector.py

Detects code smells from a FileAST produced by ast_analyzer.py.
Returns a list of SmellItem (schema) with severity scores.

Smell types detected:
  - HIGH_COMPLEXITY   : cyclomatic complexity > threshold
  - LONG_METHOD       : function body > threshold lines
  - TOO_MANY_PARAMS   : function has > threshold parameters
  - DEEP_NESTING      : function nested depth > threshold
  - DEAD_CODE         : unused imports / unreachable blocks (heuristic)
  - POOR_NAMING       : single-char or non-descriptive identifiers
  - GOD_CLASS         : class with too many methods
  - DUPLICATION       : near-identical code blocks across files
"""

from __future__ import annotations

import hashlib
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from opsmindai.agents.refactor.ast_analyzer import (
    FileAST, FunctionNode, ClassNode, get_all_functions
)
from opsmindai.schemas.refactor import SmellItem, SmellSeverity, SmellType

logger = logging.getLogger(__name__)


# ── Thresholds (can be overridden via config/models.yaml) ────────────────────

@dataclass
class SmellThresholds:
    max_complexity:     int   = 5     # cyclomatic complexity — McCabe threshold
    max_method_lines:   int   = 20    # lines per function body
    max_params:         int   = 3     # parameters per function
    max_nesting:        int   = 2     # nesting depth
    max_class_methods:  int   = 10    # methods per class (god class)
    min_name_length:    int   = 3     # minimum identifier length
    duplication_window: int   = 4     # consecutive identical lines = duplicate


DEFAULT_THRESHOLDS = SmellThresholds()


# ── Cyclomatic complexity ─────────────────────────────────────────────────────

# Decision points that increment complexity
_COMPLEXITY_KEYWORDS_PY = re.compile(
    r"\b(if|elif|else|for|while|except|with|assert|and|or|not)\b"
)
_COMPLEXITY_KEYWORDS_JS = re.compile(
    r"\b(if|else|for|while|do|switch|case|catch|&&|\|\||\?)\b"
)


def _cyclomatic_complexity(source: str, language: str) -> int:
    """
    Approximate cyclomatic complexity = 1 + number of decision points.
    Uses regex on raw source rather than full CFG for speed.
    """
    pattern = (
        _COMPLEXITY_KEYWORDS_PY if language == "python"
        else _COMPLEXITY_KEYWORDS_JS
    )
    return 1 + len(pattern.findall(source))


# ── Poor naming heuristics ────────────────────────────────────────────────────

_BANNED_NAMES = {
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "tmp", "temp", "data", "val", "var", "foo", "bar", "baz", "test",
    "func", "helper", "util", "misc",
}


def _is_poor_name(name: str, min_length: int) -> bool:
    if len(name) < min_length:
        return True
    return name.lower() in _BANNED_NAMES


# ── Duplication detection ─────────────────────────────────────────────────────

def _line_hashes(source: str, window: int) -> list[str]:
    """Slide a window over non-blank lines and return content hashes."""
    lines = [l.strip() for l in source.splitlines() if l.strip()]
    hashes = []
    for i in range(len(lines) - window + 1):
        block = "\n".join(lines[i : i + window])
        hashes.append(hashlib.md5(block.encode()).hexdigest())
    return hashes


# ── Severity mapping ──────────────────────────────────────────────────────────

def _complexity_severity(score: int) -> SmellSeverity:
    if score >= 30:  return SmellSeverity.CRITICAL
    if score >= 20:  return SmellSeverity.HIGH
    if score >= 10:  return SmellSeverity.MEDIUM
    return SmellSeverity.LOW


def _score_to_01(raw: int, low: int, high: int) -> float:
    """Normalise raw integer to 0-1 range."""
    return min(1.0, max(0.0, (raw - low) / max(high - low, 1)))


# ── Main detection ────────────────────────────────────────────────────────────

def detect_smells(
    ast_results: list[FileAST],
    thresholds: SmellThresholds = DEFAULT_THRESHOLDS,
    severity_threshold: SmellSeverity = SmellSeverity.MEDIUM,
) -> list[SmellItem]:
    """
    Run all smell detectors across a list of FileAST objects.

    Args:
        ast_results:        Parsed ASTs from ast_analyzer.py.
        thresholds:         Configurable detection thresholds.
        severity_threshold: Minimum severity to include in output.

    Returns:
        Flat list of SmellItem sorted by severity descending.
    """
    smells: list[SmellItem] = []
    all_hashes: dict[str, list[str]] = {}   # file → line hashes (for dup detection)

    severity_order = {
        SmellSeverity.CRITICAL: 4,
        SmellSeverity.HIGH:     3,
        SmellSeverity.MEDIUM:   2,
        SmellSeverity.LOW:      1,
    }
    min_severity = severity_order[severity_threshold]

    for ast_result in ast_results:
        if ast_result.parse_error and not ast_result.functions and not ast_result.classes:
            logger.warning(
                "Parse error for %s (%s) — adding structural smell so LLM reviews it",
                ast_result.file_path, ast_result.parse_error,
            )
            # Instead of silently skipping, inject a HIGH smell so this file
            # is included in the suggest phase's file_contents and reviewed by
            # the LLM.  Typical cause: commented-out class/function declarations.
            if severity_order[SmellSeverity.HIGH] >= min_severity:
                smells.append(SmellItem(
                    file=ast_result.file_path,
                    line=1,
                    smell_type=SmellType.DEAD_CODE,
                    severity=SmellSeverity.HIGH,
                    message=(
                        f"File has structural issues that prevented full AST parsing "
                        f"({ast_result.parse_error}). Possible causes: commented-out "
                        f"class/function declarations, orphaned method bodies, or "
                        f"syntax errors. Review the entire file for structural bugs."
                    ),
                    score=0.85,
                ))
            continue

        lang = ast_result.language
        all_functions = get_all_functions(ast_result)

        # ── Per-function checks ──────────────────────────────────
        for fn in all_functions:
            # 1. Cyclomatic complexity
            cc = _cyclomatic_complexity(fn.raw_source, lang)
            fn.complexity = cc
            if cc > thresholds.max_complexity:
                sev = _complexity_severity(cc)
                if severity_order[sev] >= min_severity:
                    smells.append(SmellItem(
                        file=fn.file,
                        line=fn.start_line,
                        end_line=fn.end_line,
                        smell_type=SmellType.HIGH_COMPLEXITY,
                        severity=sev,
                        message=(
                            f"Function '{fn.name}' has cyclomatic complexity "
                            f"{cc} (threshold: {thresholds.max_complexity})"
                        ),
                        score=_score_to_01(cc, thresholds.max_complexity, 50),
                        context=fn.raw_source[:300] if fn.raw_source else None,
                    ))

            # 2. Long method
            if fn.body_lines > thresholds.max_method_lines:
                sev = (SmellSeverity.HIGH if fn.body_lines > thresholds.max_method_lines * 2
                       else SmellSeverity.MEDIUM)
                if severity_order[sev] >= min_severity:
                    smells.append(SmellItem(
                        file=fn.file,
                        line=fn.start_line,
                        end_line=fn.end_line,
                        smell_type=SmellType.LONG_METHOD,
                        severity=sev,
                        message=(
                            f"Function '{fn.name}' is {fn.body_lines} lines "
                            f"(threshold: {thresholds.max_method_lines})"
                        ),
                        score=_score_to_01(fn.body_lines,
                                           thresholds.max_method_lines,
                                           thresholds.max_method_lines * 4),
                        context=None,
                    ))

            # 3. Too many parameters
            param_count = len(fn.parameters)
            if param_count > thresholds.max_params:
                sev = (SmellSeverity.HIGH if param_count > thresholds.max_params * 2
                       else SmellSeverity.MEDIUM)
                if severity_order[sev] >= min_severity:
                    smells.append(SmellItem(
                        file=fn.file,
                        line=fn.start_line,
                        smell_type=SmellType.TOO_MANY_PARAMS,
                        severity=sev,
                        message=(
                            f"Function '{fn.name}' has {param_count} parameters "
                            f"(threshold: {thresholds.max_params})"
                        ),
                        score=_score_to_01(param_count,
                                           thresholds.max_params,
                                           thresholds.max_params * 3),
                        context=f"def {fn.name}({', '.join(fn.parameters)})",
                    ))

            # 4. Deep nesting
            if fn.nesting_depth > thresholds.max_nesting:
                sev = SmellSeverity.MEDIUM
                if severity_order[sev] >= min_severity:
                    smells.append(SmellItem(
                        file=fn.file,
                        line=fn.start_line,
                        smell_type=SmellType.DEEP_NESTING,
                        severity=sev,
                        message=(
                            f"Function '{fn.name}' has nesting depth "
                            f"{fn.nesting_depth} (threshold: {thresholds.max_nesting})"
                        ),
                        score=_score_to_01(fn.nesting_depth,
                                           thresholds.max_nesting,
                                           thresholds.max_nesting * 2),
                        context=None,
                    ))

            # 5. Poor naming
            if _is_poor_name(fn.name, thresholds.min_name_length):
                sev = SmellSeverity.LOW
                if severity_order[sev] >= min_severity:
                    smells.append(SmellItem(
                        file=fn.file,
                        line=fn.start_line,
                        smell_type=SmellType.POOR_NAMING,
                        severity=sev,
                        message=f"Function name '{fn.name}' is too short or non-descriptive",
                        score=0.3,
                        context=None,
                    ))

        # ── Per-class checks ─────────────────────────────────────
        for cls in ast_result.classes:
            if len(cls.methods) > thresholds.max_class_methods:
                sev = SmellSeverity.HIGH
                if severity_order[sev] >= min_severity:
                    smells.append(SmellItem(
                        file=cls.file,
                        line=cls.start_line,
                        end_line=cls.end_line,
                        smell_type=SmellType.GOD_CLASS,
                        severity=sev,
                        message=(
                            f"Class '{cls.name}' has {len(cls.methods)} methods "
                            f"(threshold: {thresholds.max_class_methods})"
                        ),
                        score=_score_to_01(len(cls.methods),
                                           thresholds.max_class_methods,
                                           thresholds.max_class_methods * 3),
                        context=None,
                    ))

        # ── Dead code (heuristic: unused imports in Python) ──────
        if lang == "python":
            _detect_dead_imports(ast_result, smells, min_severity, severity_order)

        # ── Duplication fingerprinting ───────────────────────────
        if thresholds.duplication_window > 0:
            all_hashes[ast_result.file_path] = _line_hashes(
                ast_result.source, thresholds.duplication_window
            )

    # ── Cross-file duplication ───────────────────────────────────
    _detect_duplication(all_hashes, smells, min_severity, severity_order)

    # Sort: critical first
    severity_rank = {
        SmellSeverity.CRITICAL: 0,
        SmellSeverity.HIGH:     1,
        SmellSeverity.MEDIUM:   2,
        SmellSeverity.LOW:      3,
    }
    smells.sort(key=lambda s: (severity_rank[s.severity], s.file, s.line))
    return smells


def _detect_dead_imports(
    ast_result: FileAST,
    smells: list[SmellItem],
    min_severity: int,
    severity_order: dict,
) -> None:
    """Heuristic: flag import statements whose identifier never appears again.
    
    Uses a simple regex-based approach to find unused imports by checking
    if the imported name appears anywhere after the import statement.
    
    Args:
        ast_result: FileAST object containing source code and parse results.
        smells: List to append detected dead code smells to.
        min_severity: Minimum severity level to include (for filtering).
        severity_order: Dictionary mapping SmellSeverity to numeric values.
    """
    import_pattern = re.compile(
        r"^(?:import\s+(\w+)|from\s+\S+\s+import\s+(\w+))", re.MULTILINE
    )
    for i, m in enumerate(import_pattern.finditer(ast_result.source)):
        name = m.group(1) or m.group(2)
        line = ast_result.source[:m.start()].count("\n") + 1
        # Count occurrences after the import line
        remaining = ast_result.source[m.end():]
        if name and remaining.count(name) == 0:
            sev = SmellSeverity.LOW
            if severity_order[sev] >= min_severity:
                smells.append(SmellItem(
                    file=ast_result.file_path,
                    line=line,
                    smell_type=SmellType.DEAD_CODE,
                    severity=sev,
                    message=f"Unused import: '{name}'",
                    score=0.25,
                    context=m.group(0),
                ))


def _detect_duplication(
    all_hashes: dict[str, list[str]],
    smells: list[SmellItem],
    min_severity: int,
    severity_order: dict,
) -> None:
    """Find files sharing identical rolling-window line hashes.
    
    Detects duplicated code blocks across multiple files by comparing
    MD5 hashes of sliding windows of source lines.
    
    Args:
        all_hashes: Dictionary mapping file paths to lists of line hashes.
        smells: List to append detected duplication smells to.
        min_severity: Minimum severity level to include (for filtering).
        severity_order: Dictionary mapping SmellSeverity to numeric values.
    """
    seen: dict[str, str] = {}   # hash → first file that had it
    for file_path, hashes in all_hashes.items():
        for h in set(hashes):
            if h in seen and seen[h] != file_path:
                sev = SmellSeverity.MEDIUM
                if severity_order[sev] >= min_severity:
                    smells.append(SmellItem(
                        file=file_path,
                        line=1,
                        smell_type=SmellType.DUPLICATION,
                        severity=sev,
                        message=(
                            f"Duplicated code block detected between "
                            f"'{file_path}' and '{seen[h]}'"
                        ),
                        score=0.6,
                        context=None,
                    ))
                break   # one dup report per file pair is enough
            else:
                seen.setdefault(h, file_path)


# ── Summary helpers ───────────────────────────────────────────────────────────

def severity_score(smells: list[SmellItem]) -> float:
    """Compute an overall 0-1 severity score from a smell list.
    
    Args:
        smells: List of SmellItem objects.
    
    Returns:
        Overall severity score between 0.0 (no issues) and 1.0 (critical issues).
    """
    if not smells:
        return 0.0
    weights = {
        SmellSeverity.CRITICAL: 1.0,
        SmellSeverity.HIGH:     0.7,
        SmellSeverity.MEDIUM:   0.4,
        SmellSeverity.LOW:      0.1,
    }
    total = sum(weights[s.severity] * s.score for s in smells)
    return min(1.0, total / max(len(smells), 1))


def count_by_severity(smells: list[SmellItem]) -> dict[str, int]:
    """Count smells grouped by severity level.
    
    Args:
        smells: List of SmellItem objects to count.
        
    Returns:
        Dictionary with keys 'critical', 'high', 'medium', 'low' and their counts.
    """
    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for s in smells:
        severity_key = s.severity.value if hasattr(s.severity, 'value') else str(s.severity).lower().split('.')[-1]
        if severity_key in counts:
            counts[severity_key] += 1
    return counts