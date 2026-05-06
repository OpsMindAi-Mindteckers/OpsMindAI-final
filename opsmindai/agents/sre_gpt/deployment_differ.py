"""
opsmindai/agents/sre_gpt/deployment_differ.py

Phase P5 — SRS §9.3.

Retrieves the last 5 `kubectl rollout history` revisions for a deployment,
diffs the most recent two, and surfaces image / env / replica changes
to feed into the RCA engine.

All kubectl calls are wrapped in asyncio subprocess with strict timeouts
and arg-list invocation (never shell=True) to avoid command injection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from datetime import datetime, timezone
from typing import Any, Optional

from opsmindai.schemas.incidents import DeploymentDiff

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_KUBECTL_TIMEOUT_S = 20
_MAX_REVISIONS     = 5

# Allowed characters in k8s names — guards against injection via `service` param
_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9\-\.]{0,252}[a-z0-9]$")


def _validate_k8s_name(name: str, kind: str) -> None:
    if not _SAFE_NAME.match(name):
        raise ValueError(f"Invalid kubernetes {kind} name: {name!r}")


# ── Subprocess helper ────────────────────────────────────────────────────────

async def _run_kubectl(args: list[str]) -> tuple[int, str, str]:
    """
    Execute `kubectl <args>` with timeout. Returns (returncode, stdout, stderr).
    Never uses shell=True. Never raises on non-zero exit.
    """
    if not shutil.which("kubectl"):
        return 127, "", "kubectl binary not found in PATH"

    proc = await asyncio.create_subprocess_exec(
        "kubectl", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_KUBECTL_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", f"kubectl timed out after {_KUBECTL_TIMEOUT_S}s"

    return proc.returncode or 0, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_rollout_history(text: str) -> list[int]:
    """
    Parse `kubectl rollout history` plain-text output:

        deployment.apps/api
        REVISION  CHANGE-CAUSE
        1         <none>
        2         kubectl set image ...

    Returns sorted list of revision integers.
    """
    revisions: list[int] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("revision") or "deployment" in line.lower():
            continue
        first_token = line.split()[0]
        try:
            revisions.append(int(first_token))
        except ValueError:
            continue
    return sorted(revisions)


def _extract_image(deployment_json: dict) -> Optional[str]:
    """
    Pull the first container image from a deployment manifest.

    Path: spec.template.spec.containers[0].image
    """
    try:
        containers = (
            deployment_json["spec"]["template"]["spec"]["containers"]
        )
        if containers:
            return containers[0].get("image")
    except (KeyError, TypeError, IndexError):
        return None
    return None


def _extract_env_vars(deployment_json: dict) -> dict[str, str]:
    """Flatten container env vars into {name: value}. Ignores valueFrom refs."""
    out: dict[str, str] = {}
    try:
        containers = deployment_json["spec"]["template"]["spec"]["containers"]
        for c in containers:
            for e in c.get("env", []) or []:
                if "value" in e:
                    out[e["name"]] = str(e["value"])
    except (KeyError, TypeError):
        pass
    return out


def _extract_replicas(deployment_json: dict) -> Optional[int]:
    return deployment_json.get("spec", {}).get("replicas")


def _extract_last_deploy_time(deployment_json: dict) -> Optional[datetime]:
    """
    Find the latest 'lastUpdateTime' across all conditions.
    Falls back to metadata.creationTimestamp.
    """
    try:
        conditions = deployment_json.get("status", {}).get("conditions", [])
        timestamps = [c.get("lastUpdateTime") for c in conditions if c.get("lastUpdateTime")]
        if timestamps:
            timestamps.sort(reverse=True)
            return datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass

    creation = deployment_json.get("metadata", {}).get("creationTimestamp")
    if creation:
        try:
            return datetime.fromisoformat(creation.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


# ── Public API ────────────────────────────────────────────────────────────────

async def get_deployment_diff(
    service:   str,
    namespace: str = "default",
) -> DeploymentDiff:
    """
    Return a DeploymentDiff containing image / env / replica changes
    between the most recent two revisions of `service`.

    On any kubectl failure, returns an empty DeploymentDiff with
    `revisions_inspected=0` rather than raising. RCA can proceed.

    Args:
        service:   Deployment name (must match k8s naming rules).
        namespace: Kubernetes namespace.
    """
    try:
        _validate_k8s_name(service, "deployment")
        _validate_k8s_name(namespace, "namespace")
    except ValueError as exc:
        logger.warning("Skipping deployment diff: %s", exc)
        return DeploymentDiff(service=service, namespace=namespace)

    # 1. Get current deployment manifest as JSON
    rc, stdout, stderr = await _run_kubectl([
        "get", "deployment", service,
        "-n", namespace,
        "-o", "json",
    ])
    if rc != 0:
        logger.warning(
            "kubectl get deployment failed (svc=%s ns=%s): %s",
            service, namespace, stderr.strip(),
        )
        return DeploymentDiff(service=service, namespace=namespace)

    try:
        current_manifest = json.loads(stdout)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse kubectl JSON: %s", exc)
        return DeploymentDiff(service=service, namespace=namespace)

    current_image    = _extract_image(current_manifest)
    current_env      = _extract_env_vars(current_manifest)
    current_replicas = _extract_replicas(current_manifest)
    last_deploy_time = _extract_last_deploy_time(current_manifest)

    # 2. Get rollout history → list of revisions
    rc, stdout, stderr = await _run_kubectl([
        "rollout", "history", f"deployment/{service}",
        "-n", namespace,
    ])
    if rc != 0:
        logger.warning("kubectl rollout history failed: %s", stderr.strip())
        return DeploymentDiff(
            service=service,
            namespace=namespace,
            current_image=current_image,
            last_deploy_time=last_deploy_time,
            revisions_inspected=1,
        )

    revisions = _parse_rollout_history(stdout)[-_MAX_REVISIONS:]
    if len(revisions) < 2:
        return DeploymentDiff(
            service=service,
            namespace=namespace,
            current_image=current_image,
            last_deploy_time=last_deploy_time,
            revisions_inspected=len(revisions),
        )

    # 3. Get the previous revision detail
    previous_rev = revisions[-2]
    rc, stdout, stderr = await _run_kubectl([
        "rollout", "history", f"deployment/{service}",
        "-n", namespace,
        "--revision", str(previous_rev),
        "-o", "json",
    ])

    previous_image    = None
    previous_env: dict[str, str] = {}
    previous_replicas: Optional[int] = None

    if rc == 0 and stdout.strip():
        try:
            prev = json.loads(stdout)
            previous_image    = _extract_image(prev)
            previous_env      = _extract_env_vars(prev)
            previous_replicas = _extract_replicas(prev)
        except json.JSONDecodeError:
            logger.warning("Could not parse previous revision JSON")

    # 4. Diff
    changed_fields: list[str] = []
    if current_image and previous_image and current_image != previous_image:
        changed_fields.append(f"image: {previous_image} → {current_image}")

    if current_replicas is not None and previous_replicas is not None \
            and current_replicas != previous_replicas:
        changed_fields.append(
            f"replicas: {previous_replicas} → {current_replicas}"
        )

    env_changes: list[str] = []
    for k, v in current_env.items():
        if previous_env.get(k) != v:
            env_changes.append(f"env.{k}")
    for k in previous_env.keys() - current_env.keys():
        env_changes.append(f"env.{k} (removed)")
    if env_changes:
        changed_fields.append("env_vars: " + ", ".join(env_changes[:10]))

    return DeploymentDiff(
        service=service,
        namespace=namespace,
        current_image=current_image,
        previous_image=previous_image,
        changed_fields=changed_fields,
        last_deploy_time=last_deploy_time,
        revisions_inspected=len(revisions),
    )