"""
opsmindai/agents/refactor/ast_analyzer.py

Parses source files into AST trees using tree-sitter.
Returns structured node data consumed by smell_detector.py.

Supported languages: Python, JavaScript, TypeScript
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── tree-sitter language mapping ─────────────────────────────────────────────
# Install: pip install tree-sitter tree-sitter-python tree-sitter-javascript
try:
    import tree_sitter_python as tspython
    import tree_sitter_javascript as tsjavascript
    from tree_sitter import Language, Parser
    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False
    logger.warning("tree-sitter not installed. AST analysis unavailable.")
    Parser = None  # type: ignore

_LANG_MAP: dict[str, str] = {
    ".py":  "python",
    ".js":  "javascript",
    ".ts":  "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
}

_PARSERS: dict[str, "Parser | None"] = {}   # cached per-language parsers


def _get_parser(lang: str) -> Optional["Parser"]:
    """Build (or return cached) tree-sitter Parser for a language.
    
    Args:
        lang: Language code (e.g., 'python', 'javascript', 'typescript').
    
    Returns:
        Parser instance or None if language is unsupported or tree-sitter unavailable.
    """
    if not _TS_AVAILABLE:
        return None
    if lang in _PARSERS:
        return _PARSERS[lang]

    try:
        if lang == "python":
            language = Language(tspython.language())
        elif lang in ("javascript", "typescript"):
            language = Language(tsjavascript.language())
        else:
            return None

        parser = Parser(language)
        _PARSERS[lang] = parser
        return parser
    except Exception as exc:
        logger.error("Failed to build parser for %s: %s", lang, exc)
        return None


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class FunctionNode:
    """Represents a single function / method extracted from the AST.
    
    Attributes:
        name: Function name.
        file: File path where function is defined.
        start_line: Starting line number (1-indexed).
        end_line: Ending line number (1-indexed).
        parameters: List of parameter names.
        body_lines: Number of lines in function body.
        nesting_depth: Depth of nesting (0 for top-level functions).
        complexity: Cyclomatic complexity (populated by smell_detector).
        raw_source: Raw source code of the function.
    """
    name:         str
    file:         str
    start_line:   int
    end_line:     int
    parameters:   list[str]       = field(default_factory=list)
    body_lines:   int             = 0
    nesting_depth: int            = 0
    # Populated by smell_detector
    complexity:   int             = 0
    raw_source:   str             = ""


@dataclass
class ClassNode:
    """Represents a class extracted from the AST.
    
    Attributes:
        name: Class name.
        file: File path where class is defined.
        start_line: Starting line number (1-indexed).
        end_line: Ending line number (1-indexed).
        methods: List of methods defined in the class.
        body_lines: Number of lines in class body.
    """
    name:         str
    file:         str
    start_line:   int
    end_line:     int
    methods:      list[FunctionNode] = field(default_factory=list)
    body_lines:   int                = 0


@dataclass
class FileAST:
    """Full AST analysis result for one source file.
    
    Attributes:
        file_path: Relative path to the source file.
        language: Programming language (e.g., 'python', 'javascript').
        source: Raw source code content.
        functions: Top-level functions found in the file.
        classes: Classes found in the file.
        total_lines: Total number of lines in the file.
        parse_error: Error message if parsing failed; None if successful.
    """
    file_path:    str
    language:     str
    source:       str
    functions:    list[FunctionNode] = field(default_factory=list)
    classes:      list[ClassNode]    = field(default_factory=list)
    total_lines:  int                = 0
    parse_error:  Optional[str]      = None


# ── Core analysis ─────────────────────────────────────────────────────────────

def analyze_file(file_path: str, source_code: str) -> FileAST:
    """
    Parse a source file and extract functions, classes, and structural metadata.

    Args:
        file_path:   Relative path of the file (used to detect language).
        source_code: Raw UTF-8 source content.

    Returns:
        FileAST with extracted structural info.
    """
    ext      = Path(file_path).suffix.lower()
    language = _LANG_MAP.get(ext)
    result   = FileAST(
        file_path=file_path,
        language=language or "unknown",
        source=source_code,
        total_lines=source_code.count("\n") + 1,
    )

    if not language:
        result.parse_error = f"Unsupported extension: {ext}"
        return result

    parser = _get_parser(language)
    if parser is None:
        # Fallback: regex-based extraction when tree-sitter unavailable
        result = _fallback_parse(result, source_code, language)
        return result

    try:
        tree  = parser.parse(bytes(source_code, "utf-8"))
        root  = tree.root_node

        if root.has_error:
            result.parse_error = "tree-sitter reported parse errors"

        if language == "python":
            _extract_python(result, root, source_code, file_path)
        elif language in ("javascript", "typescript"):
            _extract_js(result, root, source_code, file_path)

    except Exception as exc:
        logger.exception("AST parse failed for %s", file_path)
        result.parse_error = str(exc)

    return result


# ── Python extraction ─────────────────────────────────────────────────────────

def _extract_python(ast_result: FileAST, root, source: str, file_path: str) -> None:
    """Walk tree-sitter Python AST and populate functions + classes."""
    lines = source.splitlines()

    def _get_params(params_node) -> list[str]:
        return [c.text.decode() for c in params_node.children
                if c.type not in ("(", ")", ",", "default_parameter")]

    def _get_source(start_line: int, end_line: int) -> str:
        return "\n".join(lines[start_line - 1 : end_line])

    def _walk(node, depth: int = 0, parent_class: Optional[ClassNode] = None):
        if node.type == "class_definition":
            name_node  = node.child_by_field_name("name")
            class_name = name_node.text.decode() if name_node else "<anonymous>"
            cls = ClassNode(
                name=class_name,
                file=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                body_lines=node.end_point[0] - node.start_point[0],
            )
            ast_result.classes.append(cls)
            for child in node.children:
                _walk(child, depth + 1, parent_class=cls)
            return

        if node.type in ("function_definition", "async_function_definition"):
            name_node   = node.child_by_field_name("name")
            params_node = node.child_by_field_name("parameters")
            func_name   = name_node.text.decode() if name_node else "<anonymous>"
            params      = _get_params(params_node) if params_node else []
            start_line  = node.start_point[0] + 1
            end_line    = node.end_point[0] + 1
            fn = FunctionNode(
                name=func_name,
                file=file_path,
                start_line=start_line,
                end_line=end_line,
                parameters=params,
                body_lines=end_line - start_line,
                nesting_depth=depth,
                raw_source=_get_source(start_line, end_line),
            )
            if parent_class:
                parent_class.methods.append(fn)
            else:
                ast_result.functions.append(fn)
            # Recurse into nested functions
            for child in node.children:
                _walk(child, depth + 1, parent_class)
            return

        for child in node.children:
            _walk(child, depth, parent_class)

    _walk(root)


# ── JavaScript / TypeScript extraction ────────────────────────────────────────

def _extract_js(ast_result: FileAST, root, source: str, file_path: str) -> None:
    """Walk tree-sitter JS/TS AST and populate functions + classes."""
    lines = source.splitlines()

    def _get_source(start_line: int, end_line: int) -> str:
        return "\n".join(lines[start_line - 1 : end_line])

    def _walk(node, depth: int = 0, parent_class: Optional[ClassNode] = None):
        if node.type == "class_declaration":
            name_node  = node.child_by_field_name("name")
            class_name = name_node.text.decode() if name_node else "<anonymous>"
            cls = ClassNode(
                name=class_name,
                file=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                body_lines=node.end_point[0] - node.start_point[0],
            )
            ast_result.classes.append(cls)
            for child in node.children:
                _walk(child, depth + 1, parent_class=cls)
            return

        if node.type in (
            "function_declaration", "function_expression",
            "arrow_function", "method_definition",
        ):
            name_node = node.child_by_field_name("name")
            func_name = name_node.text.decode() if name_node else "<anonymous>"
            params_node = node.child_by_field_name("parameters")
            params = (
                [c.text.decode() for c in params_node.children
                 if c.type not in ("(", ")", ",")]
                if params_node else []
            )
            start_line = node.start_point[0] + 1
            end_line   = node.end_point[0] + 1
            fn = FunctionNode(
                name=func_name,
                file=file_path,
                start_line=start_line,
                end_line=end_line,
                parameters=params,
                body_lines=end_line - start_line,
                nesting_depth=depth,
                raw_source=_get_source(start_line, end_line),
            )
            if parent_class:
                parent_class.methods.append(fn)
            else:
                ast_result.functions.append(fn)
            for child in node.children:
                _walk(child, depth + 1, parent_class)
            return

        for child in node.children:
            _walk(child, depth, parent_class)

    _walk(root)


# ── Regex fallback (no tree-sitter) ──────────────────────────────────────────

def _fallback_parse(result: FileAST, source: str, language: str) -> FileAST:
    """
    Minimal regex-based extractor used when tree-sitter is unavailable.
    Less accurate but sufficient for basic smell detection.
    """
    import re
    lines = source.splitlines()

    if language == "python":
        pattern = re.compile(r"^(\s*)def\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE)
        for m in pattern.finditer(source):
            indent = len(m.group(1)) // 4
            start  = source[:m.start()].count("\n") + 1
            # Estimate end line by looking for next def at same indent
            fn = FunctionNode(
                name=m.group(2),
                file=result.file_path,
                start_line=start,
                end_line=min(start + 50, result.total_lines),  # conservative estimate
                parameters=[p.strip() for p in m.group(3).split(",") if p.strip()],
                nesting_depth=indent,
                raw_source="\n".join(lines[start - 1 : start + 49]),
            )
            result.functions.append(fn)

    result.parse_error = "Used regex fallback — tree-sitter unavailable"
    return result


# ── Public helpers ────────────────────────────────────────────────────────────

def get_all_functions(ast_result: FileAST) -> list[FunctionNode]:
    """Return all functions including class methods."""
    funcs = list(ast_result.functions)
    for cls in ast_result.classes:
        funcs.extend(cls.methods)
    return funcs