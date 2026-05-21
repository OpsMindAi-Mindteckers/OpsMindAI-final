"""
opsmindai/agents/testing/regression_suite.py

Generates synthetic regression, load-boundary, and DB performance tests
derived from recent incidents stored in the RAG knowledge base.

Pipeline:
    1. Retrieve top-10 recent incidents from RAG KB (filter_type='incident')
    2. For each incident: LLM generates a regression test that reproduces
       the failure condition described in the incident
    3. Generate load-boundary tests: 10x rate per API endpoint, assert no 5xx
    4. Generate DB query performance tests: assert all queries < 100ms
    5. Write output to tests/e2e/test_regression_{timestamp}.py
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class RegressionSuite:
    """Assembled regression test suite artifact."""
    output_file: str
    test_source: str
    incident_tests_count: int
    load_tests_count: int
    db_perf_tests_count: int
    tokens_used: int = 0
    model_used: str = ""
    warnings: list[str] = field(default_factory=list)


# ── Lazy imports ──────────────────────────────────────────────────────────────

def _get_hybrid_router():
    from opsmindai.inference.hybrid_router import HybridRouter
    return HybridRouter()


def _get_rag_pipeline():
    from opsmindai.memory.rag_pipeline import RAGPipeline
    return RAGPipeline()


# ── System prompts ────────────────────────────────────────────────────────────

_INCIDENT_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert Python QA engineer writing regression tests for production incidents.

    Given an incident description, generate a pytest test that:
    1. Reproduces the exact failure condition that caused the incident.
    2. Asserts the system now handles the condition correctly (fix regression).
    3. Uses pytest fixtures and mocks where external services are involved.
    4. Is named `test_regression_{incident_id}` and includes a docstring citing the incident.

    Output ONLY a Python code block between ```python and ```. No prose.
""")

_LOAD_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert Python performance/load test engineer.

    Given an API endpoint path and HTTP method, generate a pytest test that:
    1. Sends 10x the normal rate to the endpoint in rapid succession (use threading or asyncio).
    2. Asserts that NO response has a 5xx status code.
    3. Asserts that median response time is < 2000ms.
    4. Uses `httpx` or `requests` for HTTP calls, with a base URL from an env var or fixture.

    Output ONLY a Python code block between ```python and ```. No prose.
""")

_DB_PERF_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert Python database performance test engineer.

    Given a database query or ORM method name, generate a pytest test that:
    1. Executes the query / ORM call against a test database.
    2. Asserts execution time is < 100ms (use `time.perf_counter` or `timeit`).
    3. Asserts the result is not None and has at least one row (non-empty).
    4. Uses a `db_session` fixture for the DB connection.

    Output ONLY a Python code block between ```python and ```. No prose.
""")


# ── LLM response parsing ──────────────────────────────────────────────────────

def _extract_python_block(text: str) -> str:
    m = re.search(r"```python\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\w*\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def _validate_python(code: str) -> Optional[str]:
    try:
        compile(code, "<generated_regression>", "exec")
        return None
    except SyntaxError as exc:
        return str(exc)


# ── API endpoint discovery ────────────────────────────────────────────────────

def _discover_api_endpoints(repo_root: str) -> list[tuple[str, str]]:
    """
    Scan FastAPI router files to extract (method, path) tuples for load tests.

    Args:
        repo_root: Root of the repository on disk.

    Returns:
        List of (http_method, path) tuples, e.g. [('POST', '/api/v1/testing/generate')].
    """
    endpoints: list[tuple[str, str]] = []
    pattern = re.compile(
        r'@\w+\.(get|post|put|patch|delete|head)\(\s*["\']([^"\']+)["\']',
        re.IGNORECASE,
    )

    for root, dirs, files in os.walk(repo_root):
        # Skip non-source dirs
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules", "venv", ".venv")]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                for m in pattern.finditer(content):
                    method = m.group(1).upper()
                    path   = m.group(2)
                    if "{" not in path:   # skip parameterised paths for load tests
                        endpoints.append((method, path))
            except Exception:
                pass

    # Deduplicate
    seen: set[tuple[str, str]] = set()
    unique = [(m, p) for m, p in endpoints if (m, p) not in seen and not seen.add((m, p))]  # type: ignore[func-returns-value]
    logger.info("Discovered %d API endpoints for load tests", len(unique))
    return unique[:20]   # cap to avoid an enormous test file


# ── DB query discovery ────────────────────────────────────────────────────────

def _discover_db_queries(repo_root: str) -> list[str]:
    """
    Heuristically find ORM query method names that should be performance-tested.

    Args:
        repo_root: Root of the repository on disk.

    Returns:
        List of ORM method name strings.
    """
    queries: list[str] = []
    pattern = re.compile(
        r"(?:session|db|conn|query)\.(filter|filter_by|get|all|first|execute|query)\(",
        re.IGNORECASE,
    )
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules", "venv", ".venv", "tests")]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                for m in pattern.finditer(content):
                    label = f"{Path(fpath).stem}.{m.group(1)}"
                    queries.append(label)
            except Exception:
                pass

    # Deduplicate
    seen: set[str] = set()
    return [q for q in queries if q not in seen and not seen.add(q)][:10]  # type: ignore[func-returns-value]


# ── File header ───────────────────────────────────────────────────────────────

def _build_header(timestamp: str) -> str:
    return textwrap.dedent(f"""\
        \"\"\"
        Auto-generated regression + load + DB performance tests
        Generated by OpsMind AI Testing Agent at {timestamp}

        DO NOT EDIT — re-run the Testing Agent to regenerate.
        \"\"\"
        import time
        import threading
        import pytest
        import httpx
        from unittest.mock import patch, MagicMock

        BASE_URL = __import__("os").environ.get("OPSMIND_TEST_BASE_URL", "http://localhost:8000")

    """)


# ── Main entry point ──────────────────────────────────────────────────────────

async def generate_regression_tests(
    repo_url:     str,
    trigger_event: dict[str, Any],
    repo_root:    str = ".",
    output_dir:   Optional[str] = None,
) -> RegressionSuite:
    """
    Build the full regression test suite: incident replay + load + DB perf.

    Args:
        repo_url:      GitHub repo URL (for metadata and RAG queries).
        trigger_event: Event dict that triggered the regression run
                       (e.g. deploy, refactor PR open). Logged for traceability.
        repo_root:     Local filesystem root of the repo.
        output_dir:    Override output directory; defaults to tests/e2e/.

    Returns:
        RegressionSuite with the generated test file path and metadata.

    Raises:
        RuntimeError: If zero test blocks were produced (all LLM calls failed).
    """
    router = _get_hybrid_router()
    rag    = _get_rag_pipeline()

    timestamp    = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    total_tokens = 0
    model_used   = ""
    warnings: list[str] = []

    test_blocks: list[str] = []
    incident_count = load_count = db_count = 0

    # ── 1. Incident regression tests ──────────────────────────────────────
    test_blocks.append("# ════════════════════════════════════════════════════\n"
                        "#  SECTION 1 — Incident Regression Tests\n"
                        "# ════════════════════════════════════════════════════\n")

    incidents = await rag.retrieve(
        query="production incident failure error",
        top_k=10,
        filter_type="incident",
    )
    logger.info("Retrieved %d incident(s) from RAG KB", len(incidents))

    for inc in incidents:
        inc_id = (
            inc.metadata.get("incident_id")
            or inc.metadata.get("job_id")
            or f"inc_{hash(inc.content) % 100000:05d}"
        )
        safe_id = re.sub(r"\W+", "_", inc_id)

        prompt = textwrap.dedent(f"""\
            INCIDENT ID: {inc_id}
            SERVICE: {inc.metadata.get('service', 'unknown')}
            SEVERITY: {inc.metadata.get('severity', 'unknown')}
            DESCRIPTION:
            {inc.content[:1500]}

            Generate a regression test that proves this failure is now handled correctly.
        """)

        response, tokens, model = await router.call_llm(
            prompt=prompt,
            task_type="test_generation",
            system_prompt=_INCIDENT_SYSTEM_PROMPT,
        )
        total_tokens += tokens
        model_used    = model

        code = _extract_python_block(response)
        err  = _validate_python(code)

        if err:
            # Single retry with stricter instruction
            retry_prompt = prompt + f"\n\nFix this syntax error: {err}\nOutput ONLY valid Python."
            response2, tokens2, _ = await router.call_llm(
                prompt=retry_prompt,
                task_type="test_generation",
                system_prompt=_INCIDENT_SYSTEM_PROMPT,
            )
            total_tokens += tokens2
            code2 = _extract_python_block(response2)
            if _validate_python(code2):
                warnings.append(f"Skipped regression test for incident {inc_id} — syntax error after retry")
                logger.warning("Skipping incident regression test %s — syntax error persists", inc_id)
                continue
            code = code2

        test_blocks.append(f"\n# Regression: {inc_id}\n{code}\n")
        incident_count += 1

    # ── 2. Load boundary tests ─────────────────────────────────────────────
    test_blocks.append("\n# ════════════════════════════════════════════════════\n"
                         "#  SECTION 2 — Load Boundary Tests (10x rate)\n"
                         "# ════════════════════════════════════════════════════\n")

    endpoints = _discover_api_endpoints(repo_root)
    if not endpoints:
        # Fallback: test the known OpsMind routes from the SRS
        endpoints = [
            ("POST", "/api/v1/testing/generate"),
            ("POST", "/api/v1/refactor/analyze"),
            ("POST", "/api/v1/incidents/ingest"),
            ("GET",  "/health"),
        ]
        logger.info("No endpoints discovered via scan; using SRS defaults")

    for method, path in endpoints:
        safe_name = re.sub(r"\W+", "_", path).strip("_")
        prompt = textwrap.dedent(f"""\
            API Endpoint: {method} {path}
            Normal rate assumption: 10 requests/second

            Generate a load boundary test that sends 100 requests
            (10x normal rate) and asserts no 5xx responses.
        """)

        response, tokens, model = await router.call_llm(
            prompt=prompt,
            task_type="test_generation",
            system_prompt=_LOAD_SYSTEM_PROMPT,
        )
        total_tokens += tokens
        model_used    = model

        code = _extract_python_block(response)
        if _validate_python(code):
            warnings.append(f"Skipped load test for {method} {path} — syntax error")
            continue

        test_blocks.append(f"\n# Load test: {method} {path}\n{code}\n")
        load_count += 1

    # ── 3. DB query performance tests ─────────────────────────────────────
    test_blocks.append("\n# ════════════════════════════════════════════════════\n"
                         "#  SECTION 3 — DB Query Performance Tests (< 100ms)\n"
                         "# ════════════════════════════════════════════════════\n")

    db_queries = _discover_db_queries(repo_root)
    if not db_queries:
        db_queries = ["session.query_all", "session.filter_by_user", "session.get_by_id"]
        logger.info("No DB queries discovered; using generic placeholders")

    for query_label in db_queries:
        prompt = textwrap.dedent(f"""\
            Database operation: {query_label}
            Generate a performance test asserting execution time < 100ms.
        """)

        response, tokens, model = await router.call_llm(
            prompt=prompt,
            task_type="test_generation",
            system_prompt=_DB_PERF_SYSTEM_PROMPT,
        )
        total_tokens += tokens
        model_used    = model

        code = _extract_python_block(response)
        if _validate_python(code):
            warnings.append(f"Skipped DB perf test for {query_label} — syntax error")
            continue

        test_blocks.append(f"\n# DB perf: {query_label}\n{code}\n")
        db_count += 1

    # ── 4. Assemble and write ─────────────────────────────────────────────
    if incident_count + load_count + db_count == 0:
        raise RuntimeError(
            "All regression test generation attempts failed. "
            "Check LLM availability and RAG knowledge base."
        )

    out_dir  = output_dir or os.path.join(repo_root, "tests", "e2e")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"test_regression_{timestamp}.py")

    header       = _build_header(timestamp)
    final_source = header + "\n".join(test_blocks)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final_source)

    logger.info(
        "Regression suite written to %s "
        "(incidents=%d load=%d db=%d tokens=%d)",
        out_path, incident_count, load_count, db_count, total_tokens,
    )

    # ── 5. Embed suite metadata in RAG ────────────────────────────────────
    try:
        summary = (
            f"Regression suite {timestamp} repo={repo_url} "
            f"incidents={incident_count} load={load_count} db_perf={db_count}"
        )
        await rag.embed(
            content=summary,
            doc_type="test_result",
            metadata={
                "type":            "regression_suite",
                "repo_url":        repo_url,
                "timestamp":       timestamp,
                "incident_count":  incident_count,
                "load_count":      load_count,
                "db_count":        db_count,
                "trigger_event":   trigger_event.get("type", "unknown"),
            },
        )
    except Exception as exc:
        logger.warning("RAG embed failed (non-fatal): %s", exc)

    return RegressionSuite(
        output_file=out_path,
        test_source=final_source,
        incident_tests_count=incident_count,
        load_tests_count=load_count,
        db_perf_tests_count=db_count,
        tokens_used=total_tokens,
        model_used=model_used,
        warnings=warnings,
    )