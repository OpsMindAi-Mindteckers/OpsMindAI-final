"""
opsmindai/agents/refactor/smell_detector.py

Detects code smells and correctness issues from a FileAST produced by
ast_analyzer.py. Returns a list of SmellItem sorted by severity.

Smell types detected (20 total):
  Original 8:
    HIGH_COMPLEXITY     cyclomatic complexity > threshold
    LONG_METHOD         function body > threshold lines
    TOO_MANY_PARAMS     function has > threshold parameters
    DEEP_NESTING        function nested depth > threshold
    DEAD_CODE           unused imports
    POOR_NAMING         single-char or non-descriptive identifiers
    GOD_CLASS           class with too many methods
    DUPLICATION         near-identical code blocks across files

  New — correctness:
    SYNTAX_ERROR        invalid Python syntax (CRITICAL)
    UNDEFINED_NAME      name used but not imported/defined (HIGH)
    MISSING_INIT        self.attr used but not set in __init__ (HIGH)
    MUTABLE_DEFAULT_ARG def f(x=[]) — mutable shared default (HIGH)
    UNREACHABLE_CODE    code after return/raise/break/continue (MEDIUM)

  New — error handling:
    BARE_EXCEPT         except: without exception type (HIGH)
    EMPTY_EXCEPT        except ...: pass — silent swallow (HIGH)
    BROAD_EXCEPTION     except Exception without re-raise (MEDIUM)

  New — security / maintainability:
    HARDCODED_SECRET    password/token/key in source code (CRITICAL)
    SHADOWED_BUILTIN    variable shadows len/list/str/etc. (MEDIUM)
    PRINT_STATEMENT     print() instead of logging (LOW)
    MAGIC_NUMBER        unexplained numeric literal (LOW)
"""

from __future__ import annotations

import ast as _pyast
import builtins
import hashlib
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from opsmindai.agents.refactor.ast_analyzer import (
    FileAST, FunctionNode, ClassNode, get_all_functions,
)
from opsmindai.schemas.refactor import SmellItem, SmellSeverity, SmellType

logger = logging.getLogger(__name__)


# ── Thresholds ────────────────────────────────────────────────────────────────

@dataclass
class SmellThresholds:
    max_complexity:     int = 10
    max_method_lines:   int = 50
    max_params:         int = 5
    max_nesting:        int = 4
    max_class_methods:  int = 20
    min_name_length:    int = 3
    duplication_window: int = 6


DEFAULT_THRESHOLDS = SmellThresholds()


# ── Regex patterns ────────────────────────────────────────────────────────────

_COMPLEXITY_KEYWORDS_PY = re.compile(
    r"\b(if|elif|else|for|while|except|with|assert|and|or|not)\b"
)
_COMPLEXITY_KEYWORDS_JS = re.compile(
    r"\b(if|else|for|while|do|switch|case|catch|&&|\|\||\?)\b"
)

_SECRET_PATTERN = re.compile(
    r'(?:password|passwd|secret|api_key|apikey|token|auth_token|private_key'
    r'|access_key|aws_secret|client_secret|db_pass|database_url)\s*=\s*["\'][^"\']{4,}["\']',
    re.IGNORECASE,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_BANNED_NAMES = {
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "tmp", "temp", "data", "val", "var", "foo", "bar", "baz", "test",
    "func", "helper", "util", "misc",
}

_PYTHON_BUILTINS = {
    'list', 'dict', 'set', 'tuple', 'str', 'int', 'float', 'bool',
    'bytes', 'bytearray', 'type', 'object', 'id', 'len', 'range', 'map',
    'filter', 'zip', 'enumerate', 'sorted', 'reversed', 'sum', 'min', 'max',
    'print', 'input', 'open', 'hash', 'hex', 'oct', 'bin', 'abs', 'round',
    'pow', 'repr', 'iter', 'next', 'all', 'any', 'callable', 'isinstance',
    'issubclass', 'getattr', 'setattr', 'hasattr', 'delattr', 'vars', 'dir',
    'format', 'chr', 'ord', 'eval', 'exec', 'compile', 'globals', 'locals',
}

_MAGIC_EXEMPT: set = {
    0, 1, -1, 2, 3, 4, 5, 8, 10, 16, 24, 32, 64, 100, 128,
    200, 201, 202, 204, 256, 301, 302, 400, 401, 403, 404, 409,
    422, 429, 500, 502, 503, 1000, 1024, 3600, 86400,
}

_TERMINATORS = (_pyast.Return, _pyast.Raise, _pyast.Break, _pyast.Continue)

_IMPLICIT_GLOBALS = {
    '__name__', '__file__', '__doc__', '__package__', '__spec__',
    '__loader__', '__builtins__', '__annotations__', '__all__',
    '__version__', '__author__', 'TYPE_CHECKING', 'annotations',
    'Self', 'override', 'NotRequired', 'Required', 'TypeAlias',
    'self', 'cls',  # conventional method receiver names
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cyclomatic_complexity(source: str, language: str) -> int:
    pattern = (
        _COMPLEXITY_KEYWORDS_PY if language == "python"
        else _COMPLEXITY_KEYWORDS_JS
    )
    return 1 + len(pattern.findall(source))


def _is_poor_name(name: str, min_length: int) -> bool:
    if len(name) < min_length:
        return True
    return name.lower() in _BANNED_NAMES


def _line_hashes(source: str, window: int) -> list[str]:
    lines = [ln.strip() for ln in source.splitlines() if ln.strip()]
    hashes = []
    for i in range(len(lines) - window + 1):
        block = "\n".join(lines[i: i + window])
        hashes.append(hashlib.md5(block.encode()).hexdigest())
    return hashes


def _complexity_severity(score: int) -> SmellSeverity:
    if score >= 30:  return SmellSeverity.CRITICAL
    if score >= 20:  return SmellSeverity.HIGH
    if score >= 10:  return SmellSeverity.MEDIUM
    return SmellSeverity.LOW


def _score_to_01(raw: int, low: int, high: int) -> float:
    return min(1.0, max(0.0, (raw - low) / max(high - low, 1)))


def _add(
    smells: list[SmellItem],
    min_severity: int,
    severity_order: dict,
    *,
    file: str,
    line: int,
    smell_type: SmellType,
    severity: SmellSeverity,
    message: str,
    score: float = 0.5,
    end_line: Optional[int] = None,
    context: Optional[str] = None,
) -> None:
    if severity_order[severity] >= min_severity:
        smells.append(SmellItem(
            file=file, line=line, end_line=end_line,
            smell_type=smell_type, severity=severity,
            message=message, score=score, context=context,
        ))


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def detect_smells(
    ast_results: list[FileAST],
    thresholds: SmellThresholds = DEFAULT_THRESHOLDS,
    severity_threshold: SmellSeverity = SmellSeverity.LOW,
) -> list[SmellItem]:
    """
    Run all smell detectors across a list of FileAST objects.

    Returns a flat list of SmellItem sorted by severity (critical first).
    """
    smells: list[SmellItem] = []
    all_hashes: dict[str, list[str]] = {}

    severity_order = {
        SmellSeverity.CRITICAL: 4,
        SmellSeverity.HIGH:     3,
        SmellSeverity.MEDIUM:   2,
        SmellSeverity.LOW:      1,
    }
    min_severity = severity_order[severity_threshold]

    for ast_result in ast_results:
        lang = ast_result.language

        # ── Python: deep analysis via built-in ast module ─────────────────────
        if lang == "python":
            _detect_python_ast_issues(ast_result, smells, min_severity, severity_order)

        # ── Hardcoded secrets (all languages, regex) ──────────────────────────
        _detect_hardcoded_secrets(ast_result, smells, min_severity, severity_order)

        # Skip structural checks if the file couldn't be parsed at all
        if ast_result.parse_error and not ast_result.functions and not ast_result.classes:
            logger.warning("Skipping structural analysis for %s — parse error: %s",
                           ast_result.file_path, ast_result.parse_error)
            continue

        all_functions = get_all_functions(ast_result)

        # ── Per-function checks ───────────────────────────────────────────────
        for fn in all_functions:
            cc = _cyclomatic_complexity(fn.raw_source, lang)
            fn.complexity = cc

            if cc > thresholds.max_complexity:
                sev = _complexity_severity(cc)
                _add(smells, min_severity, severity_order,
                     file=fn.file, line=fn.start_line, end_line=fn.end_line,
                     smell_type=SmellType.HIGH_COMPLEXITY, severity=sev,
                     message=(f"Function '{fn.name}' has cyclomatic complexity "
                              f"{cc} (threshold: {thresholds.max_complexity})"),
                     score=_score_to_01(cc, thresholds.max_complexity, 50),
                     context=fn.raw_source[:300] if fn.raw_source else None)

            if fn.body_lines > thresholds.max_method_lines:
                sev = (SmellSeverity.HIGH if fn.body_lines > thresholds.max_method_lines * 2
                       else SmellSeverity.MEDIUM)
                _add(smells, min_severity, severity_order,
                     file=fn.file, line=fn.start_line, end_line=fn.end_line,
                     smell_type=SmellType.LONG_METHOD, severity=sev,
                     message=(f"Function '{fn.name}' is {fn.body_lines} lines "
                              f"(threshold: {thresholds.max_method_lines})"),
                     score=_score_to_01(fn.body_lines,
                                        thresholds.max_method_lines,
                                        thresholds.max_method_lines * 4))

            param_count = len(fn.parameters)
            if param_count > thresholds.max_params:
                sev = (SmellSeverity.HIGH if param_count > thresholds.max_params * 2
                       else SmellSeverity.MEDIUM)
                _add(smells, min_severity, severity_order,
                     file=fn.file, line=fn.start_line,
                     smell_type=SmellType.TOO_MANY_PARAMS, severity=sev,
                     message=(f"Function '{fn.name}' has {param_count} parameters "
                              f"(threshold: {thresholds.max_params})"),
                     score=_score_to_01(param_count,
                                        thresholds.max_params, thresholds.max_params * 3),
                     context=f"def {fn.name}({', '.join(fn.parameters)})")

            if fn.nesting_depth > thresholds.max_nesting:
                _add(smells, min_severity, severity_order,
                     file=fn.file, line=fn.start_line,
                     smell_type=SmellType.DEEP_NESTING, severity=SmellSeverity.MEDIUM,
                     message=(f"Function '{fn.name}' has nesting depth "
                              f"{fn.nesting_depth} (threshold: {thresholds.max_nesting})"),
                     score=_score_to_01(fn.nesting_depth,
                                        thresholds.max_nesting, thresholds.max_nesting * 2))

            if _is_poor_name(fn.name, thresholds.min_name_length):
                _add(smells, min_severity, severity_order,
                     file=fn.file, line=fn.start_line,
                     smell_type=SmellType.POOR_NAMING, severity=SmellSeverity.LOW,
                     message=f"Function name '{fn.name}' is too short or non-descriptive",
                     score=0.3)

        # ── Per-class checks ──────────────────────────────────────────────────
        for cls in ast_result.classes:
            if len(cls.methods) > thresholds.max_class_methods:
                _add(smells, min_severity, severity_order,
                     file=cls.file, line=cls.start_line, end_line=cls.end_line,
                     smell_type=SmellType.GOD_CLASS, severity=SmellSeverity.HIGH,
                     message=(f"Class '{cls.name}' has {len(cls.methods)} methods "
                              f"(threshold: {thresholds.max_class_methods})"),
                     score=_score_to_01(len(cls.methods),
                                        thresholds.max_class_methods,
                                        thresholds.max_class_methods * 3))

        # ── Dead code (unused imports) ─────────────────────────────────────────
        if lang == "python":
            _detect_dead_imports(ast_result, smells, min_severity, severity_order)

        # ── Duplication fingerprinting ─────────────────────────────────────────
        if thresholds.duplication_window > 0:
            all_hashes[ast_result.file_path] = _line_hashes(
                ast_result.source, thresholds.duplication_window
            )

    _detect_duplication(all_hashes, smells, min_severity, severity_order)

    severity_rank = {
        SmellSeverity.CRITICAL: 0,
        SmellSeverity.HIGH:     1,
        SmellSeverity.MEDIUM:   2,
        SmellSeverity.LOW:      3,
    }
    smells.sort(key=lambda s: (severity_rank[s.severity], s.file, s.line))
    return smells


# ─────────────────────────────────────────────────────────────────────────────
# Python deep analysis (built-in ast module)
# ─────────────────────────────────────────────────────────────────────────────

def _detect_python_ast_issues(
    ast_result: FileAST,
    smells: list[SmellItem],
    min_severity: int,
    severity_order: dict,
) -> None:
    source = ast_result.source
    file_path = ast_result.file_path

    try:
        tree = _pyast.parse(source, filename=file_path)
    except SyntaxError as exc:
        _add(smells, min_severity, severity_order,
             file=file_path, line=exc.lineno or 1,
             smell_type=SmellType.SYNTAX_ERROR, severity=SmellSeverity.CRITICAL,
             message=f"Syntax error: {exc.msg}",
             score=1.0,
             context=exc.text.strip() if exc.text else None)
        return

    _pyast.fix_missing_locations(tree)
    lines = source.splitlines()

    _check_except_handlers(tree, file_path, lines, smells, min_severity, severity_order)
    _check_mutable_defaults(tree, file_path, smells, min_severity, severity_order)
    _check_unreachable_code(tree, file_path, smells, min_severity, severity_order)
    _check_shadowed_builtins(tree, file_path, smells, min_severity, severity_order)
    _check_print_statements(tree, file_path, lines, smells, min_severity, severity_order)
    _check_magic_numbers(tree, file_path, lines, smells, min_severity, severity_order)
    _check_missing_init_attrs(tree, file_path, smells, min_severity, severity_order)
    _check_undefined_names(tree, file_path, smells, min_severity, severity_order)


def _check_except_handlers(tree, file_path, lines, smells, min_severity, severity_order):
    """BARE_EXCEPT, EMPTY_EXCEPT, BROAD_EXCEPTION."""
    for node in _pyast.walk(tree):
        if not isinstance(node, _pyast.ExceptHandler):
            continue

        line = node.lineno
        line_text = lines[line - 1].strip() if line <= len(lines) else ""

        body_stmts = node.body
        body_is_trivial = all(
            isinstance(s, _pyast.Pass) or
            (isinstance(s, _pyast.Expr) and
             isinstance(s.value, _pyast.Constant) and s.value.value is ...)
            for s in body_stmts
        )

        # 1. Bare except: (no type → catches EVERYTHING including KeyboardInterrupt)
        if node.type is None:
            _add(smells, min_severity, severity_order,
                 file=file_path, line=line,
                 smell_type=SmellType.BARE_EXCEPT, severity=SmellSeverity.HIGH,
                 message=("Bare 'except:' catches ALL exceptions including "
                          "KeyboardInterrupt and SystemExit. Specify exception type(s)."),
                 score=0.75, context=line_text)

        # 2. Empty / trivial except body (silently swallows exception)
        if body_is_trivial:
            exc_name = (
                _pyast.unparse(node.type) if node.type else "Exception"
            )
            _add(smells, min_severity, severity_order,
                 file=file_path, line=line,
                 smell_type=SmellType.EMPTY_EXCEPT, severity=SmellSeverity.HIGH,
                 message=(f"Empty except block silently swallows '{exc_name}'. "
                          "Add error handling or at least a log statement."),
                 score=0.8, context=line_text)

        # 3. Broad exception caught without re-raising
        if (node.type and
                isinstance(node.type, _pyast.Name) and
                node.type.id in ('Exception', 'BaseException') and
                not body_is_trivial):
            has_reraise = any(
                isinstance(s, _pyast.Raise) and s.exc is None
                for s in _pyast.walk(_pyast.Module(body=node.body, type_ignores=[]))
            )
            if not has_reraise:
                _add(smells, min_severity, severity_order,
                     file=file_path, line=line,
                     smell_type=SmellType.BROAD_EXCEPTION, severity=SmellSeverity.MEDIUM,
                     message=(f"Catching broad '{node.type.id}' hides unexpected errors. "
                              "Catch specific exception types instead."),
                     score=0.5, context=line_text)


def _check_mutable_defaults(tree, file_path, smells, min_severity, severity_order):
    """MUTABLE_DEFAULT_ARG: def foo(x=[], y={})."""
    for node in _pyast.walk(tree):
        if not isinstance(node, (_pyast.FunctionDef, _pyast.AsyncFunctionDef)):
            continue
        all_defaults = node.args.defaults + [
            d for d in node.args.kw_defaults if d is not None
        ]
        for default in all_defaults:
            if isinstance(default, (_pyast.List, _pyast.Dict, _pyast.Set)):
                type_name = {
                    _pyast.List: "list",
                    _pyast.Dict: "dict",
                    _pyast.Set:  "set",
                }[type(default)]
                _add(smells, min_severity, severity_order,
                     file=file_path, line=node.lineno,
                     smell_type=SmellType.MUTABLE_DEFAULT_ARG, severity=SmellSeverity.HIGH,
                     message=(f"Function '{node.name}' has a mutable {type_name} as default "
                              "argument. Mutable defaults are shared across all calls — "
                              f"use None and initialize inside: if param is None: param = {type_name}()"),
                     score=0.75,
                     context=f"def {node.name}(..., param={type_name}(), ...)")


def _check_unreachable_code(tree, file_path, smells, min_severity, severity_order):
    """UNREACHABLE_CODE: statements after return/raise/break/continue."""
    for node in _pyast.walk(tree):
        body: Optional[list] = None

        if isinstance(node, (_pyast.FunctionDef, _pyast.AsyncFunctionDef,
                              _pyast.If, _pyast.For, _pyast.While,
                              _pyast.With, _pyast.AsyncWith)):
            body = node.body
        elif isinstance(node, _pyast.Try):
            body = node.body

        if not body or len(body) < 2:
            continue

        for i, stmt in enumerate(body[:-1]):
            if isinstance(stmt, _TERMINATORS):
                next_stmt = body[i + 1]
                terminator = type(stmt).__name__.lower()
                _add(smells, min_severity, severity_order,
                     file=file_path, line=next_stmt.lineno,
                     smell_type=SmellType.UNREACHABLE_CODE, severity=SmellSeverity.MEDIUM,
                     message=f"Unreachable code after '{terminator}' statement.",
                     score=0.6)
                break  # one report per block


def _check_shadowed_builtins(tree, file_path, smells, min_severity, severity_order):
    """SHADOWED_BUILTIN: variable or parameter that shadows a Python builtin."""
    for node in _pyast.walk(tree):
        # Variable assignments
        targets: list = []
        if isinstance(node, _pyast.Assign):
            targets = node.targets
        elif isinstance(node, (_pyast.AugAssign, _pyast.AnnAssign)):
            targets = [node.target]

        for target in targets:
            for name_node in _pyast.walk(target):
                if (isinstance(name_node, _pyast.Name) and
                        isinstance(name_node.ctx, _pyast.Store) and
                        name_node.id in _PYTHON_BUILTINS):
                    _add(smells, min_severity, severity_order,
                         file=file_path, line=node.lineno,
                         smell_type=SmellType.SHADOWED_BUILTIN, severity=SmellSeverity.MEDIUM,
                         message=(f"Variable '{name_node.id}' shadows the built-in "
                                  f"'{name_node.id}'. Use a more specific name."),
                         score=0.4, context=f"{name_node.id} = ...")

        # Function/method parameter names
        if isinstance(node, (_pyast.FunctionDef, _pyast.AsyncFunctionDef)):
            all_args = (node.args.args + node.args.posonlyargs +
                        node.args.kwonlyargs)
            if node.args.vararg:
                all_args.append(node.args.vararg)
            if node.args.kwarg:
                all_args.append(node.args.kwarg)
            for arg in all_args:
                if arg.arg in _PYTHON_BUILTINS:
                    _add(smells, min_severity, severity_order,
                         file=file_path, line=node.lineno,
                         smell_type=SmellType.SHADOWED_BUILTIN, severity=SmellSeverity.MEDIUM,
                         message=(f"Parameter '{arg.arg}' in '{node.name}' shadows "
                                  f"the built-in '{arg.arg}'."),
                         score=0.4,
                         context=f"def {node.name}(..., {arg.arg}, ...)")


def _check_print_statements(tree, file_path, lines, smells, min_severity, severity_order):
    """PRINT_STATEMENT: print() calls instead of logging."""
    for node in _pyast.walk(tree):
        if (isinstance(node, _pyast.Call) and
                isinstance(node.func, _pyast.Name) and
                node.func.id == 'print'):
            line_text = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
            _add(smells, min_severity, severity_order,
                 file=file_path, line=node.lineno,
                 smell_type=SmellType.PRINT_STATEMENT, severity=SmellSeverity.LOW,
                 message="Use 'logging' instead of print() in production code.",
                 score=0.2, context=line_text)


def _check_magic_numbers(tree, file_path, lines, smells, min_severity, severity_order):
    """MAGIC_NUMBER: unexplained numeric literals in expressions."""
    for node in _pyast.walk(tree):
        if not isinstance(node, _pyast.Constant):
            continue
        if not isinstance(node.value, (int, float)):
            continue
        if node.value in _MAGIC_EXEMPT:
            continue
        if isinstance(node.value, float) and node.value in {0.0, 1.0, 0.5}:
            continue

        line_text = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""

        # Skip if used in an import, class def, or decorator (rare but possible)
        # Skip pure constant assignments at module level (MAX_SIZE = 512)
        # We use a heuristic: if line is just "NAME = NUMBER", skip it
        if re.match(r'^[A-Z_][A-Z_0-9]*\s*=\s*[\d.]+', line_text):
            continue

        _add(smells, min_severity, severity_order,
             file=file_path, line=node.lineno,
             smell_type=SmellType.MAGIC_NUMBER, severity=SmellSeverity.LOW,
             message=(f"Magic number '{node.value}' — consider extracting to a "
                      "named constant for readability."),
             score=0.2, context=line_text)


def _check_missing_init_attrs(tree, file_path, smells, min_severity, severity_order):
    """MISSING_INIT: self.attr used in methods but never assigned in __init__."""
    for cls_node in _pyast.walk(tree):
        if not isinstance(cls_node, _pyast.ClassDef):
            continue

        # Collect all method names in this class (to exclude method calls)
        method_names: set[str] = {
            item.name for item in cls_node.body
            if isinstance(item, (_pyast.FunctionDef, _pyast.AsyncFunctionDef))
        }

        # Check if __init__ exists
        init_nodes = [
            item for item in cls_node.body
            if isinstance(item, _pyast.FunctionDef) and item.name == '__init__'
        ]
        if not init_nodes:
            continue

        # Collect attrs assigned in __init__ via self.X = ...
        init_attrs: set[str] = set()
        for stmt in _pyast.walk(init_nodes[0]):
            if isinstance(stmt, _pyast.Assign):
                for target in stmt.targets:
                    if (isinstance(target, _pyast.Attribute) and
                            isinstance(target.value, _pyast.Name) and
                            target.value.id == 'self'):
                        init_attrs.add(target.attr)
            elif (isinstance(stmt, _pyast.AnnAssign) and
                  isinstance(stmt.target, _pyast.Attribute) and
                  isinstance(stmt.target.value, _pyast.Name) and
                  stmt.target.value.id == 'self'):
                init_attrs.add(stmt.target.attr)

        # Check other methods for self.X loads not in init_attrs
        reported: set[str] = set()
        for item in cls_node.body:
            if (not isinstance(item, (_pyast.FunctionDef, _pyast.AsyncFunctionDef)) or
                    item.name == '__init__'):
                continue
            for node in _pyast.walk(item):
                if (isinstance(node, _pyast.Attribute) and
                        isinstance(node.value, _pyast.Name) and
                        node.value.id == 'self' and
                        isinstance(node.ctx, _pyast.Load) and
                        node.attr not in init_attrs and
                        node.attr not in method_names and
                        node.attr not in reported and
                        not node.attr.startswith('__')):
                    reported.add(node.attr)
                    _add(smells, min_severity, severity_order,
                         file=file_path, line=node.lineno,
                         smell_type=SmellType.MISSING_INIT, severity=SmellSeverity.HIGH,
                         message=(f"'{cls_node.name}.{node.attr}' is accessed in "
                                  f"'{item.name}' but never assigned in '__init__'. "
                                  "This will raise AttributeError at runtime."),
                         score=0.85,
                         context=f"self.{node.attr}  # not set in __init__")


def _check_undefined_names(tree, file_path, smells, min_severity, severity_order):
    """UNDEFINED_NAME: attribute access on names not imported or defined."""
    # Collect all names defined at module scope
    defined: set[str] = set(dir(builtins)) | _IMPLICIT_GLOBALS

    for stmt in tree.body:
        if isinstance(stmt, _pyast.Import):
            for alias in stmt.names:
                defined.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(stmt, _pyast.ImportFrom):
            for alias in stmt.names:
                if alias.name != '*':
                    defined.add(alias.asname or alias.name)
        elif isinstance(stmt, (_pyast.FunctionDef, _pyast.AsyncFunctionDef)):
            defined.add(stmt.name)
        elif isinstance(stmt, _pyast.ClassDef):
            defined.add(stmt.name)
        elif isinstance(stmt, _pyast.Assign):
            for target in _pyast.walk(stmt):
                if isinstance(target, _pyast.Name) and isinstance(target.ctx, _pyast.Store):
                    defined.add(target.id)
        elif isinstance(stmt, _pyast.AnnAssign):
            if isinstance(stmt.target, _pyast.Name):
                defined.add(stmt.target.id)

    # Find Attribute accesses on undefined module-like names
    reported: set[str] = set()
    for node in _pyast.walk(tree):
        if not isinstance(node, _pyast.Attribute):
            continue
        if not isinstance(node.value, _pyast.Name):
            continue
        name = node.value.id
        if (name not in defined and
                name not in reported and
                not name.startswith('_') and
                name[0].islower()):  # module names are conventionally lowercase
            reported.add(name)
            _add(smells, min_severity, severity_order,
                 file=file_path, line=node.value.lineno,
                 smell_type=SmellType.UNDEFINED_NAME, severity=SmellSeverity.HIGH,
                 message=(f"'{name}' is used but not imported or defined. "
                          f"Did you forget 'import {name}'?"),
                 score=0.85,
                 context=f"{name}.{node.attr}")


# ─────────────────────────────────────────────────────────────────────────────
# Regex-based detectors (all languages)
# ─────────────────────────────────────────────────────────────────────────────

def _detect_hardcoded_secrets(
    ast_result: FileAST,
    smells: list[SmellItem],
    min_severity: int,
    severity_order: dict,
) -> None:
    """HARDCODED_SECRET: detect credentials assigned as string literals."""
    for m in _SECRET_PATTERN.finditer(ast_result.source):
        line = ast_result.source[:m.start()].count("\n") + 1
        matched = m.group(0)
        # Redact the value in the message
        key_part = matched.split("=")[0].strip()
        _add(smells, min_severity, severity_order,
             file=ast_result.file_path, line=line,
             smell_type=SmellType.HARDCODED_SECRET, severity=SmellSeverity.CRITICAL,
             message=(f"Hardcoded secret detected: '{key_part}'. "
                      "Use environment variables or a secrets manager instead."),
             score=1.0,
             context=f"{key_part} = '***REDACTED***'")


def _detect_dead_imports(
    ast_result: FileAST,
    smells: list[SmellItem],
    min_severity: int,
    severity_order: dict,
) -> None:
    """DEAD_CODE: import statements whose identifier never appears again."""
    import_pattern = re.compile(
        r"^(?:import\s+(\w+)|from\s+\S+\s+import\s+(\w+))", re.MULTILINE
    )
    for m in import_pattern.finditer(ast_result.source):
        name = m.group(1) or m.group(2)
        line = ast_result.source[:m.start()].count("\n") + 1
        remaining = ast_result.source[m.end():]
        if name and remaining.count(name) == 0:
            _add(smells, min_severity, severity_order,
                 file=ast_result.file_path, line=line,
                 smell_type=SmellType.DEAD_CODE, severity=SmellSeverity.LOW,
                 message=f"Unused import: '{name}'",
                 score=0.25,
                 context=m.group(0))


def _detect_duplication(
    all_hashes: dict[str, list[str]],
    smells: list[SmellItem],
    min_severity: int,
    severity_order: dict,
) -> None:
    """DUPLICATION: files sharing identical rolling-window line hashes."""
    seen: dict[str, str] = {}
    for file_path, hashes in all_hashes.items():
        for h in set(hashes):
            if h in seen and seen[h] != file_path:
                _add(smells, min_severity, severity_order,
                     file=file_path, line=1,
                     smell_type=SmellType.DUPLICATION, severity=SmellSeverity.MEDIUM,
                     message=(f"Duplicated code block detected between "
                              f"'{file_path}' and '{seen[h]}'"),
                     score=0.6)
                break
            else:
                seen.setdefault(h, file_path)


# ─────────────────────────────────────────────────────────────────────────────
# Summary helpers
# ─────────────────────────────────────────────────────────────────────────────

def severity_score(smells: list[SmellItem]) -> float:
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
    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for s in smells:
        key = s.severity.value if hasattr(s.severity, 'value') else str(s.severity).lower().split('.')[-1]
        if key in counts:
            counts[key] += 1
    return counts
