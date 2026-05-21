"""
opsmindai/agents/testing/test_generator.py

LLM-based unit/integration test stub generation.

Pipeline:
    1. Read target source file
    2. Extract function/class definitions via AST
    3. For each function: build a RAG-augmented LLM prompt
    4. Parse generated test stubs from LLM response
    5. Validate stubs compile cleanly (1 retry on syntax error)
    6. Write output to tests/unit/test_{original_filename}.py  (or .test.js)
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
import os
import re
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class FunctionSignature:
    """Extracted metadata for a single function or method."""
    name: str
    args: list[str]
    return_annotation: str
    docstring: str
    body_source: str
    class_name: Optional[str] = None   # set if method inside a class
    is_async: bool = False
    lineno: int = 0


@dataclass
class GeneratedTests:
    """Result of test generation for one source file."""
    source_file: str
    output_file: str
    framework: str
    functions_processed: int
    test_source: str
    tokens_used: int = 0
    model_used: str = ""
    warnings: list[str] = field(default_factory=list)


# ── Lazy imports (avoid circular deps) ───────────────────────────────────────

def _get_hybrid_router():
    from opsmindai.inference.hybrid_router import HybridRouter
    return HybridRouter()


def _get_rag_pipeline():
    from opsmindai.memory.rag_pipeline import RAGPipeline
    return RAGPipeline()


# ── AST extraction ────────────────────────────────────────────────────────────

def _format_annotation(ann) -> str:
    """Format a type annotation as a string."""
    return ast.unparse(ann) if ann else ""


def _extract_function_args(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract argument list from a function node."""
    args = []
    for arg in func_node.args.args:
        ann = _format_annotation(arg.annotation)
        args.append(f"{arg.arg}: {ann}" if ann else arg.arg)
    if func_node.args.vararg:
        args.append(f"*{func_node.args.vararg.arg}")
    if func_node.args.kwarg:
        args.append(f"**{func_node.args.kwarg.arg}")
    return args


def _get_function_body_source(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    lines: list[str],
) -> str:
    """Extract raw source lines for the function body."""
    start = node.lineno - 1
    end = node.end_lineno if hasattr(node, "end_lineno") else start + 20
    return "\n".join(lines[start:end])[:2000]


def _should_skip_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if function should be skipped (private/dunder except __init__)."""
    return node.name.startswith("_") and node.name not in ("__init__",)


def _create_function_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    lines: list[str],
    class_name: Optional[str] = None,
) -> FunctionSignature:
    """Create a FunctionSignature from an AST node."""
    args = _extract_function_args(node)
    docstring = ast.get_docstring(node) or ""
    ret = _format_annotation(node.returns)
    body_source = _get_function_body_source(node, lines)

    return FunctionSignature(
        name=node.name,
        args=args,
        return_annotation=ret,
        docstring=docstring[:500],
        body_source=body_source,
        class_name=class_name,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        lineno=node.lineno,
    )


def _visit_ast_node(
    node,
    sigs: list[FunctionSignature],
    lines: list[str],
    class_name: Optional[str] = None,
) -> None:
    """Recursively visit AST node and collect function signatures."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if _should_skip_function(node):
            return
        sig = _create_function_signature(node, lines, class_name)
        sigs.append(sig)
        # Recurse into nested functions
        for child in ast.iter_child_nodes(node):
            _visit_ast_node(child, sigs, lines, class_name)
    elif isinstance(node, ast.ClassDef):
        for child in ast.iter_child_nodes(node):
            _visit_ast_node(child, sigs, lines, class_name=node.name)
    else:
        for child in ast.iter_child_nodes(node):
            _visit_ast_node(child, sigs, lines, class_name)


def _extract_functions_python(source: str) -> list[FunctionSignature]:
    """
    Walk the Python AST and collect all top-level and class-method
    function definitions with their signatures, docstrings, and bodies.

    Args:
        source: Raw Python source code string.

    Returns:
        List of FunctionSignature objects, one per def/async def.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        logger.warning("AST parse failed: %s", exc)
        return []

    lines = source.splitlines()
    sigs: list[FunctionSignature] = []
    _visit_ast_node(tree, sigs, lines)
    return sigs


def _extract_js_function_name_and_args(match) -> tuple[str, list[str]]:
    """Extract name and args from a regex match."""
    name = match.group(1)
    args_raw = match.group(2)
    args = [
        a.strip().split(":")[0].strip()
        for a in args_raw.split(",")
        if a.strip()
    ]
    return name, args


def _build_js_signature(match, source: str) -> FunctionSignature:
    """Build a FunctionSignature from a regex match."""
    name, args = _extract_js_function_name_and_args(match)
    lineno = source[: match.start()].count("\n") + 1

    return FunctionSignature(
        name=name,
        args=args,
        return_annotation="",
        docstring="",
        body_source="",
        lineno=lineno,
    )


def _deduplicate_js_signatures(sigs: list[FunctionSignature]) -> list[FunctionSignature]:
    """Remove duplicate signatures by name and line number."""
    seen: set[tuple[str, int]] = set()
    unique = []
    for sig in sigs:
        key = (sig.name, sig.lineno)
        if key not in seen:
            seen.add(key)
            unique.append(sig)
    return unique


def _extract_functions_js(source: str) -> list[FunctionSignature]:
    """
    Lightweight regex-based extractor for JS/TS function declarations.
    Not AST-precise but sufficient for test stub generation.

    Args:
        source: Raw JS/TS source code string.

    Returns:
        List of FunctionSignature objects.
    """
    sigs: list[FunctionSignature] = []
    # Match: export function foo(args) / async function foo(args) / const foo = (args) =>
    patterns = [
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
        r"(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*(?::\s*\w+\s*)?=>",
    ]

    for pat in patterns:
        for m in re.finditer(pat, source):
            sig = _build_js_signature(m, source)
            sigs.append(sig)

    return _deduplicate_js_signatures(sigs)


# ── Prompt building ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT_PYTEST = textwrap.dedent("""\
    You are an expert Python test engineer generating pytest test suites.

    RULES:
    1. Each function MUST have exactly 3 tests:
       - `test_{name}_happy_path`   — valid inputs, assert correct return value / side effect
       - `test_{name}_edge_case`    — boundary / unusual but valid input
       - `test_{name}_null_empty`   — None, empty string, empty list, zero, or missing arg
    2. Use `pytest.raises` for expected exceptions.
    3. Use `unittest.mock.patch` or `pytest-mock` for external dependencies.
    4. Import the function under test at the top of the generated code block.
    5. Output ONLY a Python code block between ```python and ```. No prose.
""")

_SYSTEM_PROMPT_JEST = textwrap.dedent("""\
    You are an expert JavaScript/TypeScript test engineer generating Jest test suites.

    RULES:
    1. Each function MUST have exactly 3 tests:
       - `it('should handle happy path...')`   — valid inputs, expect correct value
       - `it('should handle edge case...')`    — boundary / unusual but valid input
       - `it('should handle null/empty...')`   — null, undefined, empty string, 0
    2. Use `jest.mock()` for module dependencies.
    3. Output ONLY a TypeScript code block between ```typescript and ```. No prose.
""")


def _build_prompt(sig: FunctionSignature, framework: str, rag_snippets: list[str]) -> str:
    """
    Build the per-function LLM prompt combining signature, body, and RAG context.

    Args:
        sig: Extracted function signature metadata.
        framework: 'pytest' or 'jest'.
        rag_snippets: Relevant past test results from RAG KB.

    Returns:
        Formatted prompt string.
    """
    class_prefix = f"{sig.class_name}." if sig.class_name else ""
    full_name    = f"{class_prefix}{sig.name}"
    args_str     = ", ".join(sig.args)
    ret_str      = f" -> {sig.return_annotation}" if sig.return_annotation else ""

    context_block = ""
    if rag_snippets:
        joined = "\n---\n".join(rag_snippets[:3])
        context_block = f"\n\nRELEVANT PAST TEST PATTERNS:\n{joined}\n"

    return textwrap.dedent(f"""\
        Generate {framework} tests for the following function.

        FUNCTION SIGNATURE:
        {"async " if sig.is_async else ""}def {full_name}({args_str}){ret_str}

        DOCSTRING:
        {sig.docstring or "(none)"}

        BODY (first 2000 chars):
        {sig.body_source or "(not available)"}
        {context_block}
        Generate the 3 required test cases now.
    """)


# ── LLM response parsing ──────────────────────────────────────────────────────

def _extract_code_block(text: str, language: str) -> str:
    """
    Extract code between ```language ... ``` fences.

    Args:
        text: Raw LLM response.
        language: Expected fence language ('python' or 'typescript').

    Returns:
        Extracted code string, or the full text if no fence found.
    """
    pattern = rf"```{language}\s*(.*?)```"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fallback: any code fence
    m = re.search(r"```\w*\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def _validate_python(code: str) -> Optional[str]:
    """
    Attempt to compile generated Python code.

    Args:
        code: Generated Python source.

    Returns:
        Error string if invalid, None if valid.
    """
    try:
        compile(code, "<generated>", "exec")
        return None
    except SyntaxError as exc:
        return str(exc)


def _validate_js(code: str, tmp_dir: str) -> Optional[str]:
    """
    Attempt to parse generated JS/TS by running `node --check` on it.

    Args:
        code: Generated JS/TS source.
        tmp_dir: Temp directory to write the file.

    Returns:
        Error string if invalid, None if valid (or node unavailable).
    """
    tmp = os.path.join(tmp_dir, "_gen_check.js")
    try:
        with open(tmp, "w") as f:
            f.write(code)
        result = subprocess.run(
            ["node", "--check", tmp],
            capture_output=True, text=True, timeout=10
        )
        return result.stderr.strip() if result.returncode != 0 else None
    except Exception:
        return None   # non-fatal; node may not be installed


# ── Header generation ─────────────────────────────────────────────────────────

def _build_pytest_header(source_file: str) -> str:
    module = Path(source_file).stem
    return textwrap.dedent(f"""\
        \"\"\"
        Auto-generated tests for {source_file}
        Generated by OpsMind AI Testing Agent
        \"\"\"
        import pytest
        from unittest.mock import patch, MagicMock
        # TODO: update import path to match project structure
        # from opsmindai.{module} import *

    """)


def _build_jest_header(source_file: str) -> str:
    return textwrap.dedent(f"""\
        /**
         * Auto-generated tests for {source_file}
         * Generated by OpsMind AI Testing Agent
         */
        // TODO: update import path to match project structure
        // import {{ ... }} from '../{Path(source_file).stem}';

    """)


# ── Output path resolution ────────────────────────────────────────────────────

def _output_path(source_file: str, framework: str, repo_root: str = ".") -> str:
    """
    Compute test output path following pytest/Jest conventions.

    Args:
        source_file: Relative path to source file (e.g. 'src/utils.py').
        framework: 'pytest' or 'jest'.
        repo_root: Root of the repository on disk.

    Returns:
        Absolute path for the generated test file.
    """
    stem = Path(source_file).stem
    if framework == "pytest":
        out = os.path.join(repo_root, "tests", "unit", f"test_{stem}.py")
    else:
        out = os.path.join(repo_root, "tests", "unit", f"{stem}.test.ts")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    return out


# ── Main entry point ─────────────────────────────────────────────────────────

def _extract_signatures_from_source(
    file_path: str,
    source_code: str,
) -> list[FunctionSignature]:
    """Extract function signatures based on file extension."""
    ext = Path(file_path).suffix.lower()
    if ext in (".py",):
        return _extract_functions_python(source_code)
    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        return _extract_functions_js(source_code)
    else:
        raise ValueError(f"Unsupported file extension for test generation: {ext}")


def _get_test_generation_config(framework: str) -> tuple[str, str, str]:
    """Get system prompt, code language, and header for test framework."""
    if framework == "pytest":
        return _SYSTEM_PROMPT_PYTEST, "python", _build_pytest_header
    else:
        return _SYSTEM_PROMPT_JEST, "typescript", _build_jest_header


async def _validate_and_retry_test_generation(
    code: str,
    framework: str,
    sig: FunctionSignature,
    prompt: str,
    system_prompt: str,
    router,
    tmp_dir: str,
) -> tuple[Optional[str], int, list[str]]:
    """Validate generated code and retry once if needed."""
    warnings = []
    additional_tokens = 0

    # Initial validation
    if framework == "pytest":
        err = _validate_python(code)
    else:
        err = _validate_js(code, tmp_dir)

    if not err:
        return code, additional_tokens, warnings

    # Retry with error message
    logger.warning(
        "Generated test for %s has syntax error (%s) — retrying",
        sig.name,
        err,
    )
    retry_prompt = (
        prompt
        + f"\n\nPREVIOUS ATTEMPT HAD SYNTAX ERROR:\n{err}\n"
        + "Output ONLY a valid code block with no prose."
    )
    response2, tokens2, _ = await router.call_llm(
        prompt=retry_prompt,
        task_type="test_generation",
        system_prompt=system_prompt,
    )
    additional_tokens = tokens2
    code_lang = "python" if framework == "pytest" else "typescript"
    code2 = _extract_code_block(response2, code_lang)

    # Validate retry
    if framework == "pytest":
        err2 = _validate_python(code2)
    else:
        err2 = _validate_js(code2, tmp_dir)

    if err2:
        warnings.append(
            f"Could not generate valid tests for {sig.name} after retry: {err2}"
        )
        logger.error("Retry also failed for %s: %s", sig.name, err2)
        return None, additional_tokens, warnings

    return code2, additional_tokens, warnings


async def _generate_tests_for_functions(
    sigs: list[FunctionSignature],
    file_path: str,
    framework: str,
    system_prompt: str,
    code_lang: str,
    router,
    rag,
    tmp_dir: str,
) -> tuple[list[str], int, str, list[str]]:
    """Generate test blocks for all extracted functions."""
    test_blocks: list[str] = []
    total_tokens = 0
    model_used = ""
    warnings: list[str] = []

    module_name = Path(file_path).stem

    for sig in sigs:
        # Fetch RAG context
        rag_results = await rag.retrieve(
            query=f"{sig.name} {module_name}",
            top_k=3,
            filter_type="test_result",
        )
        rag_snippets = [r.content for r in rag_results]
        prompt = _build_prompt(sig, framework, rag_snippets)

        # Generate tests
        response, tokens, model = await router.call_llm(
            prompt=prompt,
            task_type="test_generation",
            system_prompt=system_prompt,
        )
        total_tokens += tokens
        model_used = model
        code = _extract_code_block(response, code_lang)

        # Validate and retry if needed
        code, retry_tokens, retry_warnings = await _validate_and_retry_test_generation(
            code, framework, sig, prompt, system_prompt, router, tmp_dir
        )
        total_tokens += retry_tokens
        warnings.extend(retry_warnings)

        if code is None:
            continue

        test_blocks.append(
            f"\n# ── Tests for {sig.name} {'(async)' if sig.is_async else ''} ──\n"
        )
        test_blocks.append(code)

    return test_blocks, total_tokens, model_used, warnings


async def generate_tests(
    repo_url: str,
    file_path: str,
    source_code: str,
    framework: str = "pytest",
    threshold: float = 0.80,
    repo_root: str = ".",
) -> GeneratedTests:
    """
    Generate LLM-based test stubs for all public functions in a source file.

    Steps:
        1. Extract function signatures from source AST.
        2. For each function: fetch RAG context + call LLM.
        3. Validate generated code; retry once on syntax error.
        4. Assemble and write final test file.

    Args:
        repo_url:    GitHub repo URL (used for RAG KB lookups).
        file_path:   Relative path of the source file within the repo.
        source_code: Raw source code content of the file.
        framework:   'pytest' or 'jest'.
        threshold:   Coverage threshold (stored in result metadata).
        repo_root:   Local filesystem root of the repo checkout.

    Returns:
        GeneratedTests dataclass with output file path and assembled source.

    Raises:
        ValueError: If no public functions are found in the source file.
    """
    # Extract signatures
    sigs = _extract_signatures_from_source(file_path, source_code)
    if not sigs:
        raise ValueError(f"No public functions found in {file_path}")

    logger.info("Extracted %d function(s) from %s", len(sigs), file_path)

    # Get framework configuration
    system_prompt, code_lang, header_builder = _get_test_generation_config(framework)
    header = header_builder(file_path)

    # Initialize LLM and RAG
    router = _get_hybrid_router()
    rag = _get_rag_pipeline()

    # Setup temp directory and test blocks
    tmp_dir = tempfile.mkdtemp(prefix="opsmind_tests_")
    test_blocks: list[str] = [header]

    # Generate tests for all functions
    func_blocks, total_tokens, model_used, warnings = await _generate_tests_for_functions(
        sigs, file_path, framework, system_prompt, code_lang, router, rag, tmp_dir
    )

    if not func_blocks:
        raise RuntimeError(
            f"All test generation attempts failed for {file_path}. "
            "Check LLM availability and source file syntax."
        )

    test_blocks.extend(func_blocks)

    # Write output file
    final_source = "\n".join(test_blocks)
    out_path = _output_path(file_path, framework, repo_root)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final_source)

    logger.info(
        "Wrote %d test block(s) to %s (tokens=%d model=%s)",
        len(func_blocks),
        out_path,
        total_tokens,
        model_used,
    )

    return GeneratedTests(
        source_file=file_path,
        output_file=out_path,
        framework=framework,
        functions_processed=len(sigs),
        test_source=final_source,
        tokens_used=total_tokens,
        model_used=model_used,
        warnings=warnings,
    )