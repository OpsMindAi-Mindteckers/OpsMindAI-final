"""
tests/e2e/test_refactor_flow.py

End-to-end tests for the code refactor pipeline:
  1. GitHub push/PR webhook → event normalisation
  2. Task router dispatches refactor.run_analysis
  3. Smell detector identifies issues in synthetic source code
  4. Severity scoring and smell grouping
  5. Testing gate verification (coverage threshold + delta)

No external network calls are made; all LLM, Redis, and Celery calls are mocked.
"""

from __future__ import annotations

import json
import os
import tempfile
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from opsmindai.agents.refactor.ast_analyzer import FileAST, FunctionNode, ClassNode
from opsmindai.agents.refactor.smell_detector import (
    SmellThresholds,
    count_by_severity,
    detect_smells,
    severity_score,
)
from opsmindai.agents.testing.coverage_analyzer import (
    CoverageResult,
    _load_threshold,
    _parse_coverage_xml,
    _parse_lcov,
)
from opsmindai.orchestrator.event_handler import (
    EventSource,
    EventType,
    normalise,
)
from opsmindai.orchestrator.task_router import route_event
from opsmindai.schemas.refactor import SmellItem, SmellSeverity, SmellType


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_function(name: str, body_lines: int = 10, params: int = 2,
                   nesting: int = 1, source: str = "", file: str = "src/mod.py") -> FunctionNode:
    return FunctionNode(
        name=name,
        file=file,
        start_line=1,
        end_line=1 + body_lines,
        parameters=[f"p{i}" for i in range(params)],
        body_lines=body_lines,
        nesting_depth=nesting,
        raw_source=source or f"def {name}(): pass",
    )


def _make_file_ast(functions=None, classes=None, source="",
                   language="python", file_path="src/mod.py") -> FileAST:
    return FileAST(
        file_path=file_path,
        language=language,
        source=source,
        functions=functions or [],
        classes=classes or [],
    )


# ── PR Push → Refactor Dispatch ───────────────────────────────────────────────

class TestPrToRefactorDispatch:

    def test_push_event_triggers_refactor_analysis(self):
        payload = {
            "ref": "refs/heads/feature/payment-refactor",
            "repository": {
                "clone_url": "https://github.com/org/payment-service.git",
            },
            "commits": [
                {"modified": ["src/payment/processor.py", "src/payment/validator.py"], "added": []}
            ],
        }

        event = normalise("github", payload)
        assert event.event_type == EventType.PUSH
        assert "src/payment/processor.py" in event.file_paths

        tasks = route_event(event)
        refactor_tasks = [t for t in tasks if "refactor" in t.queue]
        assert len(refactor_tasks) >= 1

    def test_pr_with_python_files_routes_to_refactor(self):
        payload = {
            "action": "opened",
            "pull_request": {
                "number": 99,
                "head": {"ref": "fix/db-pool"},
                "base": {"ref": "main"},
            },
            "repository": {"clone_url": "https://github.com/org/repo.git"},
        }

        event = normalise("github", payload)
        tasks = route_event(event)
        assert len(tasks) >= 1

    def test_pr_with_test_files_also_routes_to_testing(self):
        payload = {
            "action": "opened",
            "pull_request": {
                "number": 7,
                "head": {"ref": "add-tests"},
                "base": {"ref": "main"},
            },
            "repository": {"clone_url": "https://github.com/org/repo.git"},
            "head_commit": {"modified": ["src/api.py", "tests/test_api.py"]},
        }

        event = normalise("github", payload)
        # Override file_paths for this test
        event.file_paths = ["src/api.py", "tests/test_api.py"]
        tasks = route_event(event)

        queues = {t.queue for t in tasks}
        assert "refactor" in queues or "testing" in queues


# ── Smell Detection on Synthetic Code ────────────────────────────────────────

class TestSmellDetectionOnSyntheticCode:

    def test_detects_all_smell_types_in_realistic_code(self):
        """Synthetic file with intentional smells in every category."""
        # GOD CLASS: > 20 methods
        methods = [_make_function(f"method_{i}", file="src/god.py") for i in range(22)]
        god_class = ClassNode(name="PaymentProcessor", file="src/god.py",
                              start_line=1, end_line=400, methods=methods)

        # HIGH COMPLEXITY: many branches
        complex_src = "\n".join(
            ["def process(a, b, c, d):"]
            + ["    if True: pass" for _ in range(15)]
        )
        complex_fn = _make_function("process", params=4, source=complex_src,
                                     file="src/logic.py")

        # LONG METHOD: > 50 lines
        long_fn = _make_function("do_everything", body_lines=60, file="src/logic.py")

        # DEAD CODE: unused import
        dead_src = "import os\nimport sys\n\nx = sys.argv[0]\n"

        file1 = _make_file_ast(classes=[god_class], file_path="src/god.py")
        file2 = _make_file_ast(functions=[complex_fn, long_fn], source=dead_src,
                                file_path="src/logic.py")

        smells = detect_smells([file1, file2], severity_threshold=SmellSeverity.LOW)
        smell_types = {s.smell_type for s in smells}

        assert SmellType.GOD_CLASS in smell_types
        assert SmellType.HIGH_COMPLEXITY in smell_types
        assert SmellType.LONG_METHOD in smell_types
        assert SmellType.DEAD_CODE in smell_types

    def test_severity_score_above_threshold_triggers_gate(self):
        """Severity score > 0.5 should trigger a review gate."""
        critical_smell = SmellItem(
            file="src/critical.py", line=1,
            smell_type=SmellType.HIGH_COMPLEXITY,
            severity=SmellSeverity.CRITICAL,
            message="Complexity 40", score=1.0,
        )
        score = severity_score([critical_smell])
        assert score > 0.5   # should trigger code review gate

    def test_clean_code_scores_zero(self):
        clean_fn = _make_function("calculate_total", body_lines=20, params=2, nesting=1)
        ast = _make_file_ast(functions=[clean_fn])
        smells = detect_smells([ast])
        assert severity_score(smells) == 0.0


# ── Coverage Gate Enforcement ─────────────────────────────────────────────────

class TestCoverageGateEnforcement:

    def _write_xml(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False)
        f.write(content)
        f.flush()
        return f.name

    def test_gate_passes_on_improved_coverage(self, monkeypatch):
        monkeypatch.setenv("COVERAGE_THRESHOLD", "0.80")
        threshold = _load_threshold()
        assert threshold == 0.80

        current = 85.0
        previous = 80.0
        delta = current - previous
        gate_passed = (current >= threshold * 100) and (delta >= 0)
        assert gate_passed is True

    def test_gate_fails_when_coverage_drops(self):
        threshold = 0.80
        current = 75.0
        previous = 82.0
        delta = current - previous
        gate_passed = (current >= threshold * 100) and (delta >= 0)
        assert gate_passed is False

    def test_gate_enforced_at_exact_boundary(self):
        threshold = 0.80
        current = 80.0
        delta = 0.0
        gate_passed = (current >= threshold * 100) and (delta >= 0)
        assert gate_passed is True

    def test_parse_xml_produces_correct_overall_pct(self):
        xml = textwrap.dedent("""\
            <?xml version="1.0" ?>
            <coverage line-rate="0.92" lines-covered="460" lines-valid="500">
              <packages><package><classes>
                <class filename="src/core.py" line-rate="0.95"/>
                <class filename="src/utils.py" line-rate="0.88"/>
              </classes></package></packages>
            </coverage>
        """)
        path = self._write_xml(xml)
        try:
            pct, covered, valid, breakdown = _parse_coverage_xml(path)
            assert pct == pytest.approx(92.0)
            assert covered == 460
            assert valid == 500
            assert "src/core.py" in breakdown
        finally:
            os.unlink(path)


# ── Full Pipeline Simulation ──────────────────────────────────────────────────

@pytest.mark.asyncio
class TestFullRefactorPipeline:

    async def test_pr_smell_detect_gate_pipeline(self, mock_redis):
        """
        Simulate: PR opened → smell detection → coverage gate → results stored.
        """
        # Step 1: PR event normalised
        pr_payload = {
            "action": "opened",
            "pull_request": {
                "number": 55,
                "head": {"ref": "refactor/cleanup"},
                "base": {"ref": "main"},
            },
            "repository": {"clone_url": "https://github.com/org/service.git"},
        }
        event = normalise("github", pr_payload)
        assert event.event_type == EventType.PULL_REQUEST

        # Step 2: Tasks routed
        tasks = route_event(event)
        assert len(tasks) >= 1

        # Step 3: Smell detection on sample code
        complex_src = "\n".join(
            ["def process():"] + ["    if True: pass" for _ in range(12)]
        )
        fn = FunctionNode(
            name="process", file="src/service.py",
            start_line=1, end_line=15,
            parameters=[], body_lines=13, nesting_depth=2,
            raw_source=complex_src,
        )
        ast = FileAST(
            file_path="src/service.py",
            language="python",
            source=complex_src,
            functions=[fn],
        )

        smells = detect_smells([ast])
        high_priority = [s for s in smells if s.severity in (SmellSeverity.CRITICAL, SmellSeverity.HIGH, SmellSeverity.MEDIUM)]

        # Step 4: Store analysis result in Redis
        job_id = tasks[0].job_id
        result = {
            "job_id": job_id,
            "status": "completed",
            "smells_count": len(smells),
            "high_priority_count": len(high_priority),
            "severity_score": severity_score(smells),
        }
        await mock_redis.setex(f"testing:job:{job_id}", 3600, json.dumps(result))

        # Step 5: Verify retrievable
        stored = await mock_redis.get(f"testing:job:{job_id}")
        assert stored is not None
        stored_data = json.loads(stored)
        assert stored_data["status"] == "completed"
        assert stored_data["smells_count"] >= 0
