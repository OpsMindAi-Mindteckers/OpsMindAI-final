"""
opsmindai/agents/refactor/patch_writer.py

Takes PatchFile objects and:
1. Clones the target repo into a temp directory
2. Applies each unified diff patch
3. Commits and pushes to a new branch
4. Opens a draft GitHub PR via REST API
5. Sends a Slack notification (optional)
6. Cleans up temp directory
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import textwrap
from datetime import datetime, timezone
from typing import Optional

import httpx

from opsmindai.schemas.refactor import PatchFile, SmellItem, SmellSeverity

logger = logging.getLogger(__name__)


# ── Config (loaded from environment) ─────────────────────────────────────────
def _cfg() -> dict:
    return {
        "github_token":    os.environ.get("GITHUB_TOKEN", ""),
        "slack_webhook":   os.environ.get("SLACK_WEBHOOK_URL", ""),
        "bot_branch_prefix": os.environ.get("REFACTOR_BRANCH_PREFIX", "opsmind/refactor"),
    }


# ── Git helpers ───────────────────────────────────────────────────────────────

def _run(cmd: list[str], cwd: Optional[str] = None, check: bool = True) -> str:
    """Execute a shell command and return stdout, raising on non-zero exit if check=True."""
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, check=check
    )
    if result.returncode != 0 and check:
        raise RuntimeError(
            f"Command {' '.join(cmd)} failed:\n{result.stderr}"
        )
    return result.stdout.strip()


def _clone_repo(repo_url: str, branch: str, target_dir: str, token: str) -> None:
    """Clone a GitHub repo using the token for authentication."""
    # Inject token into URL: https://TOKEN@github.com/org/repo
    auth_url = repo_url.replace("https://", f"https://{token}@")
    _run(["git", "clone", "--depth=1", "--branch", branch, auth_url, target_dir])
    _run(["git", "config", "user.email", "opsmind-bot@opsmindai.internal"], cwd=target_dir)
    _run(["git", "config", "user.name",  "OpsMind AI Bot"],                  cwd=target_dir)


def _apply_patch(patch: PatchFile, repo_dir: str) -> bool:
    """
    Apply a unified diff patch using `git apply`.
    Returns True on success.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".patch", delete=False
    ) as pf:
        pf.write(patch.diff)
        patch_path = pf.name

    try:
        _run(["git", "apply", "--check", patch_path], cwd=repo_dir)   # dry-run first
        _run(["git", "apply",            patch_path], cwd=repo_dir)   # apply for real
        logger.info("Patch applied successfully: %s", patch.file)
        return True
    except RuntimeError as exc:
        logger.error("Patch failed for %s: %s", patch.file, exc)
        return False
    finally:
        os.unlink(patch_path)


# ── GitHub PR creation ────────────────────────────────────────────────────────

def _parse_owner_repo(repo_url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub HTTPS URL."""
    parts = repo_url.rstrip("/").split("/")
    return parts[-2], parts[-1].replace(".git", "")


def _build_pr_body(
    smells: list[SmellItem],
    patches: list[PatchFile],
    job_id: str,
) -> str:
    """Build a structured PR description from smell + patch data."""
    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for s in smells:
        severity_counts[s.severity] += 1

    files_changed = "\n".join(
        f"- `{p.file}` (+{p.additions} / -{p.deletions})" for p in patches
    )
    smell_summary = "\n".join(
        f"- [{s.severity.upper()}] `{s.file}:{s.line}` — {s.message}"
        for s in smells[:15]   # cap at 15 to keep PR readable
    )
    return textwrap.dedent(f"""
        ## OpsMind AI — Automated Code Refactor

        **Job ID:** `{job_id}`
        **Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

        ### Severity Summary
        | Severity | Count |
        |----------|-------|
        | 🔴 Critical | {severity_counts['critical']} |
        | 🟠 High     | {severity_counts['high']} |
        | 🟡 Medium   | {severity_counts['medium']} |
        | 🔵 Low      | {severity_counts['low']} |

        ### Files Changed
        {files_changed}

        ### Detected Smells Addressed
        {smell_summary}

        ---
        *This PR was opened automatically by [OpsMind AI](https://opsmindai.internal).*
        *Review the changes carefully before merging.*
    """).strip()


async def _create_github_pr(
    repo_url:   str,
    head_branch:str,
    base_branch:str,
    title:      str,
    body:       str,
    draft:      bool,
    token:      str,
) -> dict:
    """Call GitHub REST API to open a PR. Returns PR JSON response."""
    owner, repo = _parse_owner_repo(repo_url)
    url  = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "title": title,
        "body":  body,
        "head":  head_branch,
        "base":  base_branch,
        "draft": draft,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


# ── Slack notification ────────────────────────────────────────────────────────

async def _notify_slack(
    pr_url:    str,
    pr_number: int,
    repo_url:  str,
    smells:    list[SmellItem],
    webhook:   str,
) -> None:
    if not webhook:
        return
    critical = sum(1 for s in smells if s.severity == SmellSeverity.CRITICAL)
    high     = sum(1 for s in smells if s.severity == SmellSeverity.HIGH)
    _, repo  = _parse_owner_repo(repo_url)
    message  = {
        "text": (
            f":robot_face: *OpsMind AI — Code Refactor PR Opened*\n"
            f"*Repo:* `{repo}`\n"
            f"*PR:* <{pr_url}|#{pr_number}>\n"
            f"*Smells fixed:* {len(smells)} total "
            f"({critical} critical, {high} high)"
        )
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(webhook, json=message)
        if resp.status_code != 200:
            logger.warning("Slack notify failed: %s %s", resp.status_code, resp.text)


# ── Public entry point ────────────────────────────────────────────────────────

async def write_and_open_pr(
    repo_url:    str,
    base_branch: str,
    patches:     list[PatchFile],
    smells:      list[SmellItem],
    job_id:      str,
    pr_title:    Optional[str] = None,
    pr_body:     Optional[str] = None,
    draft:       bool = True,
    notify_slack:bool = True,
) -> dict:
    """
    Apply patches, push branch, open GitHub PR.

    Args:
        repo_url:      HTTPS GitHub repo URL.
        base_branch:   Branch to base the PR on (e.g. 'main').
        patches:       PatchFile list from refactor_engine.py.
        smells:        Detected smells (used in PR description).
        job_id:        Refactor job ID (included in branch name + PR body).
        pr_title:      Custom title (auto-generated if None).
        pr_body:       Custom body (auto-generated if None).
        draft:         Open as draft PR.
        notify_slack:  Send Slack notification after PR created.

    Returns:
        dict with: pr_url, pr_number, pr_title, branch, files_changed
    """
    cfg         = _cfg()
    token       = cfg["github_token"]
    head_branch = f"{cfg['bot_branch_prefix']}/{job_id[:8]}"

    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set — cannot open PR.")

    if not patches:
        raise ValueError("No patches to apply.")

    work_dir = tempfile.mkdtemp(prefix="opsmind_refactor_")
    try:
        # 1. Clone
        logger.info("Cloning %s@%s into %s", repo_url, base_branch, work_dir)
        _clone_repo(repo_url, base_branch, work_dir, token)

        # 2. Create new branch
        _run(["git", "checkout", "-b", head_branch], cwd=work_dir)

        # 3. Apply patches
        applied = 0
        for patch in patches:
            if _apply_patch(patch, work_dir):
                applied += 1

        if applied == 0:
            raise RuntimeError("All patches failed to apply — no changes to commit.")

        # 4. Commit
        _run(["git", "add", "--all"],  cwd=work_dir)
        commit_msg = (
            f"refactor: OpsMind AI automated refactor [{job_id[:8]}]\n\n"
            f"Fixed {len(smells)} code smell(s) across {applied} file(s).\n"
            f"Job: {job_id}"
        )
        _run(["git", "commit", "-m", commit_msg], cwd=work_dir)

        # 5. Push
        _run(["git", "push", "origin", head_branch], cwd=work_dir)
        logger.info("Pushed branch %s", head_branch)

        # 6. Open PR
        title = pr_title or (
            f"refactor: OpsMind AI — {applied} file(s) refactored [{job_id[:8]}]"
        )
        body  = pr_body or _build_pr_body(smells, patches, job_id)
        pr    = await _create_github_pr(
            repo_url=repo_url,
            head_branch=head_branch,
            base_branch=base_branch,
            title=title,
            body=body,
            draft=draft,
            token=token,
        )
        pr_url    = pr["html_url"]
        pr_number = pr["number"]
        logger.info("PR opened: %s", pr_url)

        # 7. Slack
        if notify_slack and cfg["slack_webhook"]:
            await _notify_slack(pr_url, pr_number, repo_url, smells, cfg["slack_webhook"])

        return {
            "pr_url":       pr_url,
            "pr_number":    pr_number,
            "pr_title":     title,
            "branch":       head_branch,
            "files_changed":applied,
        }

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        logger.debug("Temp dir cleaned up: %s", work_dir)