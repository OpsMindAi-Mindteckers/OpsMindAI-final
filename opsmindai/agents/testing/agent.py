"""
opsmindai/agents/testing/agent.py

Testing Agent — main entry point and job lifecycle manager.

Orchestrates the full testing pipeline:
    1. Clone repository and resolve target files
    2. test_generator   → generate LLM-based test stubs
    3. coverage_analyzer→ run tests, parse coverage, enforce gate
    4. regression_suite → build incident-driven regression tests (on trigger)
    5. Embed results in RAG KB
    6. Update job state in Redis throughout
    7. Post GitHub PR comment on gate failure

This module is called by tasks/testing_task.py Celery workers.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Optional

from opsmindai.agents.testing.test_generator   import generate_tests, GeneratedTests
from opsmindai.agents.testing.coverage_analyzer import run_and_analyze, CoverageResult
from opsmindai.agents.testing.regression_suite  import generate_regression_tests, RegressionSuite

logger = logging.getLogger(__name__)

# Redis key patterns (mirror refactor agent convention)
_JOB_KEY        = "testing:job:{job_id}"
_USER_INDEX_KEY = "testing:user:{user_id}:jobs"

# Supported source extensions for test generation
_SUPPORTED_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx"}


# ── Redis helpers ─────────────────────────────────────────────────────────────

def _job_key(job_id: str) -> str:
    return _JOB_KEY.format(job_id=job_id)


async def _update_job(redis, job_id: str, updates: dict) -> None:
    """Merge `updates` into the existing job state stored in Redis.

    Args:
        redis:   Async Redis client.
        job_id:  Unique job identifier.
        updates: Fields to merge into job state.
    """
    raw = await redis.get(_job_key(job_id))
    if not raw:
        logger.warning("Job %s not found in Redis — creating new state", job_id)
        state: dict = {}
    else:
        state = json.loads(raw)
    state.update(updates)
    await redis.setex(_job_key(job_id), 86400, json.dumps(state, default=str))


async def _index_job_for_user(redis, job_id: str, user_id: str) -> None:
    """Append job_id to the user's testing job history index in Redis."""
    idx_key = _USER_INDEX_KEY.format(user_id=user_id)
    await redis.lpush(idx_key, job_id)
    await redis.expire(idx_key, 86400 * 30)


# ── Source file cloning ───────────────────────────────────────────────────────

def _clone_repo(repo_url: str, branch: str, token: str) -> str:
    """
    Shallow-clone the repository to a temporary directory.

    Args:
        repo_url: HTTPS GitHub URL.
        branch:   Branch to clone.
        token:    GitHub PAT for authentication.

    Returns:
        Absolute path to the cloned directory.

    Raises:
        subprocess.CalledProcessError: If git clone fails.
    """
    work_dir  = tempfile.mkdtemp(prefix="opsmind_testing_")
    auth_url  = repo_url.replace("https://", f"https://{token}@")
    subprocess.run(
        ["git", "clone", "--depth=1", "--branch", branch, auth_url, work_dir],
        check=True,
        capture_output=True,
    )
    logger.info("Cloned %s@%s to %s", repo_url, branch, work_dir)
    return work_dir


def _read_file(repo_root: str, file_path: str) -> str:
    """
    Read a single source file from the cloned repo.

    Args:
        repo_root: Root of the cloned repo.
        file_path: Relative path within the repo.

    Returns:
        File contents as a UTF-8 string.
    """
    abs_path = os.path.join(repo_root, file_path)
    with open(abs_path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _collect_source_files(repo_root: str) -> list[str]:
    """
    Walk repo and return all supported source file paths (relative).

    Args:
        repo_root: Root of the cloned repo.

    Returns:
        List of relative file paths.
    """
    skip_dirs = {"__pycache__", ".git", "node_modules", "venv", ".venv", "tests", ".github"}
    result = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for fname in files:
            if any(fname.endswith(ext) for ext in _SUPPORTED_EXTS):
                rel = os.path.relpath(os.path.join(root, fname), repo_root)
                result.append(rel)
    return result


# ── Main agent entry points ───────────────────────────────────────────────────

async def run_generation(job_id: str, payload: dict, redis) -> None:
    """
    PHASE 1 — Generate test stubs for the target file(s).
    Called by Celery task: run_test_generation.

    Payload keys:
        repo_url    (str)   GitHub HTTPS URL
        file_path   (str)   Relative path; if omitted, generates for all files
        branch      (str)   Branch name (default: 'main')
        framework   (str)   'pytest' or 'jest' (default: 'pytest')
        coverage_threshold (float) 0.0–1.0 (default: 0.80)
        user_id     (str)   For Redis job index
        pr_number   (int)   Optional — GitHub PR number for PR comment
    """
    start = time.monotonic()
    await _update_job(redis, job_id, {"status": "running", "phase": "generation"})
    await _index_job_for_user(redis, job_id, payload.get("user_id", "anonymous"))

    repo_root: Optional[str] = None
    try:
        token      = os.environ.get("GITHUB_TOKEN", "")
        repo_url   = payload["repo_url"]
        branch     = payload.get("branch", "main")
        framework  = payload.get("framework", "pytest")
        threshold  = float(payload.get("coverage_threshold", 0.80))
        file_path  = payload.get("file_path")   # may be None → generate for all

        # Clone repo
        repo_root = _clone_repo(repo_url, branch, token)

        # Resolve files to process
        if file_path:
            targets = [file_path]
        else:
            targets = _collect_source_files(repo_root)
            logger.info("Full repo scan: %d file(s) found", len(targets))

        generated: list[dict] = []
        all_warnings: list[str] = []

        for fp in targets:
            try:
                source = _read_file(repo_root, fp)
            except FileNotFoundError:
                logger.warning("Source file not found in repo: %s", fp)
                continue

            try:
                result: GeneratedTests = await generate_tests(
                    repo_url=repo_url,
                    file_path=fp,
                    source_code=source,
                    framework=framework,
                    threshold=threshold,
                    repo_root=repo_root,
                )
                generated.append({
                    "source_file":         result.source_file,
                    "output_file":         result.output_file,
                    "functions_processed": result.functions_processed,
                    "tokens_used":         result.tokens_used,
                    "model_used":          result.model_used,
                })
                all_warnings.extend(result.warnings)
            except Exception as exc:
                logger.warning("Test generation failed for %s: %s", fp, exc)
                all_warnings.append(f"{fp}: {exc}")

        if not generated:
            raise RuntimeError(
                "No tests were generated. "
                "Check that source files contain public functions and LLM is reachable."
            )

        duration = time.monotonic() - start
        logger.info(
            "Generation complete job=%s files=%d duration=%.2fs",
            job_id, len(generated), duration,
        )

        await _update_job(redis, job_id, {
            "status":         "generation_complete",
            "generated_files": generated,
            "warnings":        all_warnings,
            "repo_root":       repo_root,   # kept for run_suite step
            "repo_url":        repo_url,
            "branch":          branch,
            "framework":       framework,
            "threshold":       threshold,
            "duration_s":      round(duration, 2),
            "completed_at":    datetime.now(timezone.utc).isoformat(),
        })

    except Exception as exc:
        logger.exception("Generation failed for job %s", job_id)
        await _update_job(redis, job_id, {
            "status":       "failed",
            "error":        str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(time.monotonic() - start, 2),
        })
        if repo_root:
            shutil.rmtree(repo_root, ignore_errors=True)
        raise


async def run_suite(job_id: str, payload: dict, redis) -> None:
    """
    PHASE 2 — Execute generated tests and enforce coverage gate.
    Called by Celery task: run_test_suite.

    Payload keys:
        job_id     (str)  Source generation job ID (to load repo_root from Redis)
        pr_number  (int)  Optional — GitHub PR number for gate failure comment
    """
    start = time.monotonic()
    await _update_job(redis, job_id, {"status": "running", "phase": "suite_execution"})

    repo_root: Optional[str] = None
    try:
        # Load state from source generation job
        raw = await redis.get(_job_key(job_id))
        if not raw:
            raise ValueError(f"Job {job_id} not found in Redis")

        state      = json.loads(raw)
        repo_root  = state.get("repo_root")
        repo_url   = state.get("repo_url", payload.get("repo_url", ""))
        branch     = state.get("branch", payload.get("branch", "main"))
        framework  = state.get("framework", payload.get("framework", "pytest"))
        threshold  = float(state.get("threshold", payload.get("coverage_threshold", 0.80)))
        pr_number  = payload.get("pr_number")

        if not repo_root or not os.path.isdir(repo_root):
            raise ValueError(
                f"repo_root {repo_root!r} is missing. "
                "Ensure run_generation completed successfully and repo was not cleaned up."
            )

        coverage: CoverageResult = await run_and_analyze(
            job_id=job_id,
            repo_path=repo_root,
            repo_url=repo_url,
            branch=branch,
            framework=framework,
            threshold=threshold,
            pr_number=pr_number,
            redis=redis,
        )

        duration = time.monotonic() - start
        logger.info(
            "Suite complete job=%s coverage=%.1f%% delta=%.1f%% gate=%s duration=%.2fs",
            job_id,
            coverage.coverage_pct,
            coverage.delta_pct,
            coverage.gate_passed,
            duration,
        )

        await _update_job(redis, job_id, {
            "status":      "completed",
            "coverage": {
                "coverage_pct":   coverage.coverage_pct,
                "delta_pct":      coverage.delta_pct,
                "lines_covered":  coverage.lines_covered,
                "lines_total":    coverage.lines_total,
                "file_breakdown": coverage.file_breakdown,
                "gate_passed":    coverage.gate_passed,
                "threshold":      coverage.threshold,
                "previous_pct":   coverage.previous_pct,
            },
            "gate_passed":  coverage.gate_passed,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(duration, 2),
        })

    except Exception as exc:
        logger.exception("Suite execution failed for job %s", job_id)
        await _update_job(redis, job_id, {
            "status":       "failed",
            "error":        str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(time.monotonic() - start, 2),
        })
        raise

    finally:
        # Cleanup temp clone
        if repo_root and os.path.isdir(repo_root):
            shutil.rmtree(repo_root, ignore_errors=True)
            logger.debug("Cleaned up temp repo %s", repo_root)


async def run_regression(job_id: str, payload: dict, redis) -> None:
    """
    PHASE 3 — Build and run the regression + load + DB perf test suite.
    Called by Celery task: run_regression_suite.

    Payload keys:
        repo_url       (str)  GitHub HTTPS URL
        branch         (str)  Branch name (default: 'main')
        trigger_event  (dict) Event that triggered the regression run
        user_id        (str)  For Redis job index
    """
    start = time.monotonic()
    await _update_job(redis, job_id, {"status": "running", "phase": "regression"})
    await _index_job_for_user(redis, job_id, payload.get("user_id", "anonymous"))

    repo_root: Optional[str] = None
    try:
        token         = os.environ.get("GITHUB_TOKEN", "")
        repo_url      = payload["repo_url"]
        branch        = payload.get("branch", "main")
        trigger_event = payload.get("trigger_event", {"type": "manual"})

        repo_root = _clone_repo(repo_url, branch, token)

        suite: RegressionSuite = await generate_regression_tests(
            repo_url=repo_url,
            trigger_event=trigger_event,
            repo_root=repo_root,
        )

        duration = time.monotonic() - start
        logger.info(
            "Regression suite complete job=%s incidents=%d load=%d db=%d duration=%.2fs",
            job_id,
            suite.incident_tests_count,
            suite.load_tests_count,
            suite.db_perf_tests_count,
            duration,
        )

        await _update_job(redis, job_id, {
            "status":               "completed",
            "output_file":          suite.output_file,
            "incident_tests_count": suite.incident_tests_count,
            "load_tests_count":     suite.load_tests_count,
            "db_perf_tests_count":  suite.db_perf_tests_count,
            "tokens_used":          suite.tokens_used,
            "model_used":           suite.model_used,
            "warnings":             suite.warnings,
            "completed_at":         datetime.now(timezone.utc).isoformat(),
            "duration_s":           round(duration, 2),
        })

    except Exception as exc:
        logger.exception("Regression suite failed for job %s", job_id)
        await _update_job(redis, job_id, {
            "status":       "failed",
            "error":        str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(time.monotonic() - start, 2),
        })
        raise

    finally:
        if repo_root and os.path.isdir(repo_root):
            shutil.rmtree(repo_root, ignore_errors=True)