"""
opsmindai/agents/refactor/agent.py

Code Refactor Agent — main entry point.
Orchestrates the full refactor pipeline:
    1. Clone & read source files
    2. AST analysis (ast_analyzer)
    3. Smell detection (smell_detector)
    4. LLM refactor generation (refactor_engine)
    5. Patch writing + PR creation (patch_writer)
    6. RAG embedding of result (rag_pipeline)
    7. Job state update in Redis
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
from typing import Optional

from opsmindai.agents.refactor.ast_analyzer   import analyze_file, FileAST
from opsmindai.agents.refactor.smell_detector import (
    detect_smells, severity_score, count_by_severity, SmellThresholds
)
from opsmindai.agents.refactor.refactor_engine import generate_refactor
from opsmindai.agents.refactor.patch_writer    import write_and_open_pr
from opsmindai.schemas.refactor import (
    JobStatus, SmellItem, SmellSeverity, PatchFile
)

logger = logging.getLogger(__name__)

# ── Supported file extensions ─────────────────────────────────────────────────
_SUPPORTED_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx"}


# ── Redis helpers ─────────────────────────────────────────────────────────────

def _job_key(job_id: str) -> str:
    """Generate Redis key for a refactor job.
    
    Args:
        job_id: Unique job identifier.
    
    Returns:
        Redis key string.
    """
    return f"refactor:job:{job_id}"


async def _update_job(redis, job_id: str, updates: dict) -> None:
    """Merge updates into existing job state in Redis.
    
    Args:
        redis: Redis async client.
        job_id: Unique job identifier.
        updates: Dictionary of fields to update/merge into job state.
    """
    raw = await redis.get(_job_key(job_id))
    if not raw:
        logger.warning("Job %s not found in Redis — cannot update", job_id)
        return
    state = json.loads(raw)
    state.update(updates)
    await redis.setex(_job_key(job_id), 86400, json.dumps(state, default=str))


async def _index_job_for_user(redis, job_id: str, user_id: str) -> None:
    """Add job_id to user's history index in Redis.
    
    Args:
        redis: Redis async client.
        job_id: Unique job identifier.
        user_id: User identifier (email or UUID).
    """
    index_key = f"refactor:user:{user_id}:jobs"
    await redis.lpush(index_key, job_id)
    await redis.expire(index_key, 86400 * 30)   # 30-day rolling index


# ── Source file reading ───────────────────────────────────────────────────────

def _read_files_from_repo(
    repo_url:   str,
    branch:     str,
    file_paths: list[str],
    token:      str,
) -> dict[str, str]:
    """Clone the repo (shallow) and read requested source files.
    
    Supports scanning full repository for supported file types if file_paths is empty.
    
    Args:
        repo_url: HTTPS GitHub repository URL.
        branch: Branch name (e.g., 'main', 'develop').
        file_paths: List of file paths to read. If empty, scans all supported files.
        token: GitHub personal access token for authentication.
    
    Returns:
        Dictionary mapping relative file paths to their source content.
    """
    work_dir = tempfile.mkdtemp(prefix="opsmind_ast_")
    try:
        auth_url = repo_url.replace("https://", f"https://{token}@") if token else repo_url
        subprocess.run(
            ["git", "clone", "--depth=1", "--branch", branch, auth_url, work_dir],
            check=True, capture_output=True,
        )
        result: dict[str, str] = {}

        if file_paths:
            targets = file_paths
        else:
            # Full repo scan — collect all supported files
            targets = []
            for root, _, files in os.walk(work_dir):
                # Skip hidden dirs and common non-source dirs
                rel_root = os.path.relpath(root, work_dir)
                if any(p.startswith(".") or p in ("node_modules", "__pycache__", ".git", "venv", ".venv")
                       for p in rel_root.split(os.sep)):
                    continue
                for fname in files:
                    if any(fname.endswith(ext) for ext in _SUPPORTED_EXTS):
                        targets.append(os.path.relpath(os.path.join(root, fname), work_dir))

        for rel_path in targets:
            abs_path = os.path.join(work_dir, rel_path)
            if os.path.isfile(abs_path):
                try:
                    with open(abs_path, encoding="utf-8", errors="replace") as f:
                        result[rel_path] = f.read()
                except Exception as exc:
                    logger.warning("Could not read %s: %s", rel_path, exc)

        logger.info("Read %d source file(s) from %s@%s", len(result), repo_url, branch)
        return result
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ── Main agent entry points ───────────────────────────────────────────────────

async def run_analysis(job_id: str, payload: dict, redis) -> None:
    """
    PHASE 1 — Analyse repository for code smells.
    Called by the Celery task run_refactor_analysis.
    """
    start = time.monotonic()
    await _update_job(redis, job_id, {"status": JobStatus.RUNNING})
    await _index_job_for_user(redis, job_id, payload.get("user_id", "anonymous"))

    try:
        token      = os.environ.get("GITHUB_TOKEN", "")
        repo_url   = payload["repo_url"]
        branch     = payload.get("branch", "main")
        file_paths = payload.get("file_paths", [])
        sev_str    = payload.get("severity_threshold", "medium")
        severity   = SmellSeverity(sev_str)

        # 1. Read source files
        file_contents = _read_files_from_repo(repo_url, branch, file_paths, token)
        if not file_contents:
            raise ValueError("No supported source files found in repository.")

        # 2. AST parse each file
        ast_results: list[FileAST] = []
        for fp, source in file_contents.items():
            ast_result = analyze_file(fp, source)
            ast_results.append(ast_result)
            if ast_result.parse_error:
                logger.warning("Parse warning for %s: %s", fp, ast_result.parse_error)

        # 3. Detect smells
        thresholds = SmellThresholds()   # use defaults; could load from config/models.yaml
        smells     = detect_smells(ast_results, thresholds, severity)

        counts   = count_by_severity(smells)
        sev_score= severity_score(smells)
        duration = time.monotonic() - start

        logger.info(
            "Analysis complete job=%s smells=%d critical=%d high=%d duration=%.2fs",
            job_id, len(smells), counts["critical"], counts["high"], duration,
        )

        await _update_job(redis, job_id, {
            "status":        JobStatus.COMPLETED,
            "smells":        [s.model_dump() for s in smells],
            "severity_score":sev_score,
            "total_smells":  len(smells),
            "critical_count":counts["critical"],
            "high_count":    counts["high"],
            "file_paths":    list(file_contents.keys()),
            "completed_at":  datetime.now(timezone.utc).isoformat(),
            "duration_s":    round(duration, 2),
        })

    except Exception as exc:
        logger.exception("Analysis failed for job %s", job_id)
        await _update_job(redis, job_id, {
            "status":    JobStatus.FAILED,
            "error":     str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(time.monotonic() - start, 2),
        })
        raise


async def run_suggest(job_id: str, payload: dict, redis) -> None:
    """
    PHASE 2 — Generate LLM refactor suggestions.
    Called by the Celery task run_refactor_suggest.
    """
    start = time.monotonic()
    await _update_job(redis, job_id, {"status": JobStatus.RUNNING})

    try:
        token      = os.environ.get("GITHUB_TOKEN", "")
        repo_url   = payload["repo_url"]
        branch     = payload.get("branch", "main")
        smells_raw = payload.get("smells", [])
        smells     = [SmellItem(**s) for s in smells_raw]
        model      = payload.get("model") or None

        # Determine which files to read:
        # - Always start with every file path recorded by the analyze job.
        # - When smells exist, put smell files first so they get priority context.
        # - Files that had AST parse errors (e.g. commented-out class declarations)
        #   are represented by a DEAD_CODE smell and are therefore already in
        #   the smell set; including all file_paths ensures nothing is silently
        #   excluded regardless of smell coverage.
        all_file_paths: list[str] = payload.get("file_paths", [])
        if smells:
            smell_file_set = {s.file for s in smells}
            # Smell files first (they're the priority for the LLM), then the rest
            smell_files = list(smell_file_set) + [
                f for f in all_file_paths if f not in smell_file_set
            ]
        else:
            smell_files = all_file_paths

        if not smell_files:
            raise ValueError("No files to review — provide file_paths in the analyze request.")

        file_contents = _read_files_from_repo(repo_url, branch, smell_files, token)

        # LLM refactor generation
        patches, tokens_used, model_used = await generate_refactor(
            file_contents=file_contents,
            smells=smells,
            model=model,
        )

        duration = time.monotonic() - start
        logger.info(
            "Suggest complete job=%s patches=%d tokens=%d model=%s duration=%.2fs",
            job_id, len(patches), tokens_used, model_used, duration,
        )

        # ── Embed result in RAG ───────────────────────────────────────────────
        try:
            from opsmindai.memory.rag_pipeline import RAGPipeline
            rag = RAGPipeline()
            patch_summary = "; ".join(f"{p.file}: +{p.additions} -{p.deletions}" for p in patches)
            smell_summary = "; ".join(f"{s.smell_type}@{s.file}:{s.line}" for s in smells[:5])
            await rag.add_results(
                content=f"Refactor job {job_id}. Smells: {smell_summary}. Patches: {patch_summary}",
                metadata={"type": "refactor_pattern", "job_id": job_id, "repo": repo_url, "files": smell_files},
            )
        except Exception as exc:
            logger.warning("RAG embed failed (non-fatal): %s", exc)

        await _update_job(redis, job_id, {
            "status":       JobStatus.COMPLETED,
            "patches":      [p.model_dump() for p in patches],
            "tokens_used":  tokens_used,
            "model_used":   model_used,
            "repo_url":     repo_url,
            "branch":       branch,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(duration, 2),
        })

    except Exception as exc:
        logger.exception("Suggest failed for job %s", job_id)
        await _update_job(redis, job_id, {
            "status":       JobStatus.FAILED,
            "error":        str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(time.monotonic() - start, 2),
        })
        raise


async def run_apply(job_id: str, payload: dict, redis) -> None:
    """
    PHASE 3 — Apply patch and open GitHub PR.
    Called by the Celery task apply_refactor_patch.
    """
    start = time.monotonic()
    await _update_job(redis, job_id, {"status": JobStatus.RUNNING})

    try:
        repo_url     = payload["repo_url"]
        branch       = payload.get("branch", "main")
        patches_raw  = payload.get("patches", [])
        smells_raw   = payload.get("smells", [])
        patches      = [PatchFile(**p) for p in patches_raw]
        smells       = [SmellItem(**s) for s in smells_raw]
        source_job_id= payload.get("source_job_id", job_id)

        # Fetch smells from source analyze job if not in payload
        if not smells and payload.get("source_job_id"):
            raw = await redis.get(_job_key(payload["source_job_id"]))
            if raw:
                src = json.loads(raw)
                smells = [SmellItem(**s) for s in src.get("smells", [])]

        result = await write_and_open_pr(
            repo_url=repo_url,
            base_branch=branch,
            patches=patches,
            smells=smells,
            job_id=source_job_id,
            pr_title=payload.get("pr_title"),
            pr_body=payload.get("pr_body"),
            draft=payload.get("draft", True),
            notify_slack=payload.get("notify_slack", True),
        )

        duration = time.monotonic() - start
        logger.info(
            "Apply complete job=%s pr=%s duration=%.2fs",
            job_id, result["pr_url"], duration,
        )

        await _update_job(redis, job_id, {
            "status":       JobStatus.COMPLETED,
            "pr_url":       result["pr_url"],
            "pr_number":    result["pr_number"],
            "pr_title":     result["pr_title"],
            "branch":       result["branch"],
            "files_changed":result["files_changed"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(duration, 2),
        })

    except Exception as exc:
        logger.exception("Apply failed for job %s", job_id)
        await _update_job(redis, job_id, {
            "status":       JobStatus.FAILED,
            "error":        str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s":   round(time.monotonic() - start, 2),
        })
        raise