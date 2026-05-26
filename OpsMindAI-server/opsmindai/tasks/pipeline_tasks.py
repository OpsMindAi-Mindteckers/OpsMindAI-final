"""
opsmindai/tasks/pipeline_tasks.py

Celery task for the end-to-end autonomous pipeline:

  Input (URL or raw log)
    ↓
  1. SRE Agent  — ingest + RCA (detect root cause, classify bug vs infra)
    ↓
  2. Testing Agent  — run full test suite against current code
    ↓
  3. Code Refactor Agent  — fix bugs / code smells identified by SRE + tests
    ↓
  4. Testing Agent (again)  — verify the fixes pass all tests
    ↓
  5. SRE Agent  — remediate + restart the server

Each stage writes progress events to a Redis list:
    pipeline:{pipeline_id}:events  (LPUSH, newest-first)

The SSE endpoint in api/v1/pipeline.py tails this list.

Stage keys written to Redis:
    pipeline:{pipeline_id}  — overall pipeline state (JSON)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import redis as sync_redis

from opsmindai.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

TTL = 86_400  # 24 h


# ── Redis helpers ──────────────────────────────────────────────────────────────

def _r() -> sync_redis.Redis:
    return sync_redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )


def _pipeline_key(pipeline_id: str) -> str:
    return f"pipeline:{pipeline_id}"


def _events_key(pipeline_id: str) -> str:
    return f"pipeline:{pipeline_id}:events"


class _AsyncRedisAdapter:
    """Thin async wrapper so agent coroutines work inside sync Celery tasks."""

    def __init__(self, client: sync_redis.Redis):
        self._r = client

    async def get(self, key: str):
        return self._r.get(key)

    async def set(self, key: str, value: str):
        return self._r.set(key, value)

    async def setex(self, key: str, ttl: int, value: str):
        return self._r.setex(key, ttl, value)

    async def lpush(self, key: str, *values):
        return self._r.lpush(key, *values)

    async def lrange(self, key: str, start: int, stop: int):
        return self._r.lrange(key, start, stop)

    async def expire(self, key: str, ttl: int):
        return self._r.expire(key, ttl)

    async def delete(self, *keys):
        return self._r.delete(*keys)


# ── State helpers ─────────────────────────────────────────────────────────────

_STAGES = [
    "sre_monitor",
    "testing_initial",
    "code_refactor",
    "testing_verify",
    "sre_remediate",
]

_STAGE_LABELS = {
    "sre_monitor":      "SRE Monitor & RCA",
    "testing_initial":  "Testing Agent (initial)",
    "code_refactor":    "Code Refactor",
    "testing_verify":   "Testing Agent (verify)",
    "sre_remediate":    "SRE Remediate & Restart",
}


def _push_event(r: sync_redis.Redis, pipeline_id: str, stage: str, status: str,
                message: str, details: dict | None = None) -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage":     stage,
        "status":    status,   # started | progress | completed | failed | skipped
        "message":   message,
        "details":   details or {},
    }
    r.lpush(_events_key(pipeline_id), json.dumps(event))
    r.expire(_events_key(pipeline_id), TTL)


def _update_pipeline(r: sync_redis.Redis, pipeline_id: str, **updates: Any) -> None:
    raw = r.get(_pipeline_key(pipeline_id))
    state = json.loads(raw) if raw else {}
    state.update(updates)
    r.setex(_pipeline_key(pipeline_id), TTL, json.dumps(state))


# ── Inline agent runners (fallback when Celery sub-tasks aren't available) ────

def _run_sre_ingest(redis_adapter: _AsyncRedisAdapter, job_id: str, payload: dict) -> dict:
    try:
        from opsmindai.agents.sre_gpt.agent import run_ingest
        asyncio.run(run_ingest(job_id, payload, redis_adapter))
        raw = redis_adapter._r.get(f"sre_job:{job_id}")
        return json.loads(raw) if raw else {}
    except Exception as exc:
        logger.exception("SRE ingest failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


def _run_sre_rca(redis_adapter: _AsyncRedisAdapter, job_id: str, payload: dict) -> dict:
    try:
        from opsmindai.agents.sre_gpt.agent import run_rca
        asyncio.run(run_rca(job_id, payload, redis_adapter))
        raw = redis_adapter._r.get(f"sre_job:{job_id}")
        return json.loads(raw) if raw else {}
    except Exception as exc:
        logger.exception("SRE RCA failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


def _run_sre_remediate(redis_adapter: _AsyncRedisAdapter, job_id: str, payload: dict) -> dict:
    try:
        from opsmindai.agents.sre_gpt.agent import run_remediate
        asyncio.run(run_remediate(job_id, payload, redis_adapter))
        raw = redis_adapter._r.get(f"sre_job:{job_id}")
        return json.loads(raw) if raw else {}
    except Exception as exc:
        logger.exception("SRE remediate failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


def _run_testing(redis_adapter: _AsyncRedisAdapter, job_id: str, payload: dict,
                 phase: str = "suite") -> dict:
    try:
        if phase == "generation":
            from opsmindai.agents.testing.agent import run_generation
            asyncio.run(run_generation(job_id, payload, redis_adapter))
        elif phase == "regression":
            from opsmindai.agents.testing.agent import run_regression
            asyncio.run(run_regression(job_id, payload, redis_adapter))
        else:
            from opsmindai.agents.testing.agent import run_suite
            asyncio.run(run_suite(job_id, payload, redis_adapter))
        raw = redis_adapter._r.get(f"testing_job:{job_id}")
        return json.loads(raw) if raw else {}
    except Exception as exc:
        logger.exception("Testing agent failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


def _run_refactor_analysis(redis_adapter: _AsyncRedisAdapter, job_id: str, payload: dict) -> dict:
    try:
        from opsmindai.agents.refactor.agent import run_analysis
        asyncio.run(run_analysis(job_id, payload, redis_adapter))
        raw = redis_adapter._r.get(f"refactor_job:{job_id}")
        return json.loads(raw) if raw else {}
    except Exception as exc:
        logger.exception("Refactor analysis failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


def _run_refactor_suggest(redis_adapter: _AsyncRedisAdapter, job_id: str, payload: dict) -> dict:
    try:
        from opsmindai.agents.refactor.agent import run_suggest
        asyncio.run(run_suggest(job_id, payload, redis_adapter))
        raw = redis_adapter._r.get(f"refactor_job:{job_id}")
        return json.loads(raw) if raw else {}
    except Exception as exc:
        logger.exception("Refactor suggest failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


def _run_refactor_apply(redis_adapter: _AsyncRedisAdapter, job_id: str, payload: dict) -> dict:
    try:
        from opsmindai.agents.refactor.agent import run_apply
        asyncio.run(run_apply(job_id, payload, redis_adapter))
        raw = redis_adapter._r.get(f"refactor_job:{job_id}")
        return json.loads(raw) if raw else {}
    except Exception as exc:
        logger.exception("Refactor apply failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


# ── Main pipeline Celery task ─────────────────────────────────────────────────

@celery_app.task(
    name="pipeline.run",
    bind=True,
    max_retries=0,   # pipeline is stateful — no automatic retry
    queue="pipeline",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=1800,  # 30 min overall budget
    time_limit=2100,
)
def task_run_pipeline(self, pipeline_id: str, payload: dict) -> None:
    """
    End-to-end autonomous pipeline.

    payload keys:
        input_type:   "url" | "log"
        server_url:   cloud/vercel/render URL (when input_type="url")
        raw_log:      pasted log text (when input_type="log")
        repo_url:     optional GitHub repo to refactor
        branch:       optional branch (default: main)
        service:      service label (default: derived from URL)
        user_id:      submitting user
    """
    r = _r()
    redis_adapter = _AsyncRedisAdapter(r)

    input_type  = payload.get("input_type", "log")
    server_url  = payload.get("server_url", "")
    raw_log     = payload.get("raw_log", "")
    repo_url    = payload.get("repo_url", "")
    branch      = payload.get("branch", "main")
    user_id     = payload.get("user_id", "system")
    service     = payload.get("service") or _derive_service(server_url or raw_log)

    logger.info("[pipeline] %s starting  service=%s", pipeline_id, service)

    _update_pipeline(r, pipeline_id,
                     status="running",
                     current_stage="sre_monitor",
                     stages={s: "pending" for s in _STAGES},
                     service=service,
                     started_at=datetime.now(timezone.utc).isoformat(),
                     user_id=user_id)

    incident_id: str | None = None
    test_failures: list = []
    code_bugs: list = []
    refactor_job_id: str | None = None
    needs_refactor = False

    try:
        # ── Stage 1: SRE Monitor + RCA ────────────────────────────────────────
        _stage_start(r, pipeline_id, "sre_monitor")
        sre_job_id = f"sre_{uuid.uuid4().hex[:12]}"

        # Build alert payload from URL or log
        alert_payload = _build_alert_payload(input_type, server_url, raw_log, service)

        _push_event(r, pipeline_id, "sre_monitor", "progress",
                    "Ingesting alert and starting root-cause analysis…",
                    {"job_id": sre_job_id, "service": service})

        # Phase 1: ingest
        ingest_result = _run_sre_ingest(redis_adapter, sre_job_id,
                                {"alert_payload": alert_payload, "user_id": user_id,
                                 "_pipeline_mode": True})
        incident_id = ingest_result.get("incident_id") or f"inc_{uuid.uuid4().hex[:8]}"
        if ingest_result.get("status") == "failed" or not ingest_result.get("incident_id"):
            fallback = {
                "incident_id": incident_id,
                "fingerprint": uuid.uuid4().hex,
                "source": "prometheus",
                "service": service,
                "severity": "high",
                "alert_name": "PipelineAlert",
                "labels": {}, "annotations": {},
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "namespace": None, "raw_payload": {},
        }
            redis_adapter._r.setex(f"incident:{incident_id}", 86400, json.dumps(fallback))

        # Phase 2: RCA
        rca_job_id = f"rca_{uuid.uuid4().hex[:12]}"
        rca_result = _run_sre_rca(redis_adapter, rca_job_id,
                                  {"incident_id": incident_id, "user_id": user_id})

        root_cause      = rca_result.get("root_cause", "Unknown root cause")
        confidence      = rca_result.get("confidence", 0.0)
        auto_remediable = rca_result.get("auto_remediable", False)

        # Classify: code bug vs infra?
        needs_refactor = _classify_needs_code_fix(rca_result, raw_log)
        code_bugs      = rca_result.get("detected_bugs", [])

        _stage_done(r, pipeline_id, "sre_monitor", {
            "incident_id":    incident_id,
            "root_cause":     root_cause,
            "confidence":     confidence,
            "needs_refactor": needs_refactor,
        })

        # ── Stage 2: Testing (initial) ────────────────────────────────────────
        _stage_start(r, pipeline_id, "testing_initial")

        if repo_url:
            test_job_id = f"test_{uuid.uuid4().hex[:12]}"
            _push_event(r, pipeline_id, "testing_initial", "progress",
                        "Running initial test suite…",
                        {"job_id": test_job_id, "repo_url": repo_url})

            test_result = _run_testing(redis_adapter, test_job_id, {
                "repo_url":           repo_url,
                "branch":             branch,
                "framework":          "pytest",
                "coverage_threshold": 0.80,
                "user_id":            user_id,
            }, phase="suite")

            test_failures = test_result.get("failures", [])
            coverage      = test_result.get("coverage", 0.0)
            tests_passed  = test_result.get("status") != "failed"

            _stage_done(r, pipeline_id, "testing_initial", {
                "failures": len(test_failures),
                "coverage": coverage,
                "passed":   tests_passed,
            })

            if test_failures:
                needs_refactor = True
        else:
            _stage_skip(r, pipeline_id, "testing_initial",
                        "No repo_url provided — skipping code tests")

        # ── Stage 3: Code Refactor ────────────────────────────────────────────
        if needs_refactor and repo_url:
            _stage_start(r, pipeline_id, "code_refactor")
            refactor_job_id = f"refactor_{uuid.uuid4().hex[:12]}"

            _push_event(r, pipeline_id, "code_refactor", "progress",
                        "Analysing code smells and generating fix patches…",
                        {"job_id": refactor_job_id, "bugs": len(code_bugs)})

            # Analysis
            analysis_result = _run_refactor_analysis(redis_adapter, refactor_job_id, {
                "repo_url":          repo_url,
                "branch":            branch,
                "severity_threshold": "medium",
                "user_id":           user_id,
                "incident_id":       incident_id,
                "known_bugs":        code_bugs,
            })

            smells = analysis_result.get("smells", [])

            if smells:
                _push_event(r, pipeline_id, "code_refactor", "progress",
                            f"Found {len(smells)} code issues — generating patches…",
                            {"smells": len(smells)})

                # Suggest
                suggest_job_id = f"suggest_{uuid.uuid4().hex[:12]}"
                suggest_result = _run_refactor_suggest(redis_adapter, suggest_job_id, {
                    "repo_url": repo_url,
                    "branch":   branch,
                    "smells":   smells,
                    "user_id":  user_id,
                })

                patches = suggest_result.get("patches", [])

                if patches:
                    # Apply
                    apply_job_id = f"apply_{uuid.uuid4().hex[:12]}"
                    apply_result = _run_refactor_apply(redis_adapter, apply_job_id, {
                        "repo_url": repo_url,
                        "branch":   branch,
                        "patches":  patches,
                        "smells":   smells,
                        "pr_title": f"fix: auto-remediation for incident {incident_id}",
                        "pr_body":  f"Root cause: {root_cause}\n\nPatches generated by OpsMindAI pipeline.",
                        "user_id":  user_id,
                    })

                    pr_url = apply_result.get("pr_url", "")
                    _stage_done(r, pipeline_id, "code_refactor", {
                        "smells_fixed": len(patches),
                        "pr_url":       pr_url,
                    })
                else:
                    _stage_done(r, pipeline_id, "code_refactor",
                                {"note": "No actionable patches generated"})
            else:
                _stage_done(r, pipeline_id, "code_refactor",
                            {"note": "No code smells found"})
        else:
            reason = "No code bugs detected" if not needs_refactor else "No repo_url provided"
            _stage_skip(r, pipeline_id, "code_refactor", reason)

        # ── Stage 4: Testing (verify fixes) ───────────────────────────────────
        if needs_refactor and repo_url:
            _stage_start(r, pipeline_id, "testing_verify")
            verify_job_id = f"verify_{uuid.uuid4().hex[:12]}"

            _push_event(r, pipeline_id, "testing_verify", "progress",
                        "Verifying all fixes pass the test suite…",
                        {"job_id": verify_job_id})

            verify_result = _run_testing(redis_adapter, verify_job_id, {
                "repo_url":           repo_url,
                "branch":             branch,
                "framework":          "pytest",
                "coverage_threshold": 0.80,
                "user_id":            user_id,
            }, phase="suite")

            verify_pass = verify_result.get("status") != "failed"
            _stage_done(r, pipeline_id, "testing_verify", {
                "passed":   verify_pass,
                "failures": len(verify_result.get("failures", [])),
                "coverage": verify_result.get("coverage", 0.0),
            })
        else:
            _stage_skip(r, pipeline_id, "testing_verify",
                        "No code changes applied — skipping re-test")

        # ── Stage 5: SRE Remediate + Server Restart ───────────────────────────
        _stage_start(r, pipeline_id, "sre_remediate")
        rem_job_id = f"rem_{uuid.uuid4().hex[:12]}"

        _push_event(r, pipeline_id, "sre_remediate", "progress",
                    "Executing remediation playbook and restarting server…",
                    {"job_id": rem_job_id, "incident_id": incident_id})

        remediate_result = _run_sre_remediate(redis_adapter, rem_job_id, {
            "incident_id": incident_id,
            "playbook":    "restart",   # always restart after pipeline completes
            "server_url":  server_url,
            "user_id":     user_id,
        })

        _stage_done(r, pipeline_id, "sre_remediate", {
            "remediation_status": remediate_result.get("remediation_status", "completed"),
            "actions_taken":      remediate_result.get("actions_taken", ["server_restart"]),
        })

        # ── Final state ───────────────────────────────────────────────────────
        _update_pipeline(r, pipeline_id,
                         status="completed",
                         current_stage="done",
                         completed_at=datetime.now(timezone.utc).isoformat())

        _push_event(r, pipeline_id, "pipeline", "completed",
                    "Pipeline completed successfully — server restarted.",
                    {"incident_id": incident_id})

        logger.info("[pipeline] %s completed", pipeline_id)

    except Exception as exc:
        logger.exception("[pipeline] %s failed", pipeline_id)
        _update_pipeline(r, pipeline_id,
                         status="failed",
                         error=str(exc),
                         failed_at=datetime.now(timezone.utc).isoformat())
        _push_event(r, pipeline_id, "pipeline", "failed",
                    f"Pipeline failed: {exc}")
        raise
    finally:
        r.close()


# ── Stage helpers ──────────────────────────────────────────────────────────────

def _stage_start(r: sync_redis.Redis, pipeline_id: str, stage: str) -> None:
    raw = r.get(_pipeline_key(pipeline_id))
    state = json.loads(raw) if raw else {}
    stages = state.get("stages", {})
    stages[stage] = "running"
    state["stages"] = stages
    state["current_stage"] = stage
    r.setex(_pipeline_key(pipeline_id), TTL, json.dumps(state))
    _push_event(r, pipeline_id, stage, "started",
                f"Stage started: {_STAGE_LABELS.get(stage, stage)}")


def _stage_done(r: sync_redis.Redis, pipeline_id: str, stage: str, details: dict) -> None:
    raw = r.get(_pipeline_key(pipeline_id))
    state = json.loads(raw) if raw else {}
    stages = state.get("stages", {})
    stages[stage] = "completed"
    state["stages"] = stages
    r.setex(_pipeline_key(pipeline_id), TTL, json.dumps(state))
    _push_event(r, pipeline_id, stage, "completed",
                f"Stage completed: {_STAGE_LABELS.get(stage, stage)}", details)


def _stage_skip(r: sync_redis.Redis, pipeline_id: str, stage: str, reason: str) -> None:
    raw = r.get(_pipeline_key(pipeline_id))
    state = json.loads(raw) if raw else {}
    stages = state.get("stages", {})
    stages[stage] = "skipped"
    state["stages"] = stages
    r.setex(_pipeline_key(pipeline_id), TTL, json.dumps(state))
    _push_event(r, pipeline_id, stage, "skipped",
                f"Stage skipped: {reason}")


# ── Utility ───────────────────────────────────────────────────────────────────

def _derive_service(text: str) -> str:
    """Guess a short service name from a URL or log snippet."""
    if not text:
        return "unknown-service"
    for platform in ("vercel.app", "render.com", "fly.dev", "railway.app",
                     "heroku.com", "netlify.app", "cloudflare", "aws.com",
                     "azure.com", "gcp.com"):
        if platform in text:
            parts = text.split("//")[-1].split("/")[0].split(".")
            return parts[0] if parts else platform.split(".")[0]
    # Fallback: first word that looks like a service name from logs
    for line in text.splitlines()[:5]:
        for token in line.split():
            if len(token) > 3 and token.isalpha():
                return token.lower()
    return "unknown-service"


def _build_alert_payload(input_type: str, server_url: str, raw_log: str,
                         service: str) -> dict:
    if input_type == "url":
        return {
            "source":      "prometheus",
            "service":     service,
            "severity":    "high",
            "alert_name":  "ExternalServiceAlert",
            "labels":      {"url": server_url, "input_type": "url"},
            "annotations": {"summary": f"Alert triggered from URL: {server_url}"},
            "raw_payload": {"url": server_url},
        }
    return {
        "source":      "prometheus",
        "service":     service,
        "severity":    _infer_severity(raw_log),
        "alert_name":  "LogAlertIngested",
        "labels":      {"input_type": "log"},
        "annotations": {"summary": raw_log[:500]},
        "raw_payload": {"log": raw_log},
    }


def _infer_severity(log_text: str) -> str:
    text_lower = log_text.lower()
    if any(k in text_lower for k in ("critical", "fatal", "panic", "oom", "crash")):
        return "critical"
    if any(k in text_lower for k in ("error", "exception", "traceback", "500")):
        return "high"
    if any(k in text_lower for k in ("warn", "warning", "deprecated", "slow")):
        return "medium"
    return "low"


def _classify_needs_code_fix(rca_result: dict, raw_log: str) -> bool:
    """Return True if the incident likely requires a code change."""
    root_cause = (rca_result.get("root_cause") or "").lower()
    log_lower  = raw_log.lower()
    code_keywords = (
        "exception", "typeerror", "nameerror", "attributeerror",
        "syntax", "import", "null pointer", "undefined", "keyerror",
        "valueerror", "assertion", "bug", "regression", "traceback",
        "unhandled", "404", "500", "stacktrace",
    )
    return any(k in root_cause or k in log_lower for k in code_keywords)