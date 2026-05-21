"""
tests/unit/test_refactor_agent.py

Unit tests for the Code Refactor Agent:
  - smell_detector.detect_smells()
  - _cyclomatic_complexity()
  - _is_poor_name()
  - severity_score()
  - count_by_severity()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pytest

from opsmindai.agents.refactor.smell_detector import (
    DEFAULT_THRESHOLDS,
    SmellThresholds,
    _cyclomatic_complexity,
    _is_poor_name,
    _line_hashes,
    count_by_severity,
    detect_smells,
    severity_score,
)
from opsmindai.agents.refactor.ast_analyzer import FileAST, FunctionNode, ClassNode
from opsmindai.schemas.refactor import SmellItem, SmellSeverity, SmellType


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_function(
    name: str = "my_func",
    body_lines: int = 10,
    params: int = 2,
    nesting: int = 1,
    source: str = "def my_func(): pass",
    file: str = "src/mod.py",
    start_line: int = 1,
) -> FunctionNode:
    return FunctionNode(
        name=name,
        file=file,
        start_line=start_line,
        end_line=start_line + body_lines,
        parameters=[f"p{i}" for i in range(params)],
        body_lines=body_lines,
        nesting_depth=nesting,
        raw_source=source,
    )


def _make_file_ast(
    functions: list[FunctionNode] | None = None,
    classes: list[ClassNode] | None = None,
    source: str = "",
    language: str = "python",
    file_path: str = "src/mod.py",
) -> FileAST:
    return FileAST(
        file_path=file_path,
        language=language,
        source=source,
        functions=functions or [],
        classes=classes or [],
    )


# ── _cyclomatic_complexity ────────────────────────────────────────────────────

class TestCyclomaticComplexity:

    def test_simple_function_scores_1(self):
        src = "def foo(): return 42"
        assert _cyclomatic_complexity(src, "python") == 1

    def test_if_increments_score(self):
        src = "def foo(x):\n    if x:\n        return x\n    return 0"
        assert _cyclomatic_complexity(src, "python") == 2

    def test_multiple_branches(self):
        src = (
            "def foo(a, b):\n"
            "    if a:\n"
            "        for i in b:\n"
            "            if i:\n"
            "                while True:\n"
            "                    pass\n"
        )
        # 1 + if + for + if + while = 5
        result = _cyclomatic_complexity(src, "python")
        assert result == 5

    def test_javascript_uses_different_pattern(self):
        src = "function foo(x) { if (x) { return x; } return 0; }"
        assert _cyclomatic_complexity(src, "javascript") == 2

    def test_empty_source(self):
        assert _cyclomatic_complexity("", "python") == 1


# ── _is_poor_name ─────────────────────────────────────────────────────────────

class TestIsPoorName:

    def test_single_char_is_poor(self):
        assert _is_poor_name("x", 3) is True

    def test_two_char_is_poor_by_length(self):
        assert _is_poor_name("ab", 3) is True

    def test_three_char_minimum_met(self):
        assert _is_poor_name("foo", 3) is True   # 'foo' is in banned list

    def test_banned_names(self):
        for name in ("tmp", "data", "val", "helper", "util", "misc"):
            assert _is_poor_name(name, 3) is True, f"Expected '{name}' to be poor"

    def test_descriptive_name_passes(self):
        assert _is_poor_name("process_payment", 3) is False

    def test_camel_case_descriptive_passes(self):
        assert _is_poor_name("calculateTotal", 3) is False


# ── detect_smells ─────────────────────────────────────────────────────────────

class TestDetectSmells:

    def test_empty_ast_list_returns_empty(self):
        result = detect_smells([])
        assert result == []

    def test_detects_high_complexity(self):
        # Create a function with complexity > max_complexity (10)
        # We need 10+ keywords in the source
        src = "\n".join(
            ["def complex_func():"]
            + [f"    if True: pass  # branch {i}" for i in range(12)]
        )
        fn = _make_function(name="complex_func", source=src)
        ast = _make_file_ast(functions=[fn])

        smells = detect_smells([ast])
        complexity_smells = [s for s in smells if s.smell_type == SmellType.HIGH_COMPLEXITY]
        assert len(complexity_smells) >= 1
        assert complexity_smells[0].file == "src/mod.py"

    def test_detects_long_method(self):
        fn = _make_function(name="long_func", body_lines=55)
        ast = _make_file_ast(functions=[fn], source="")

        smells = detect_smells([ast])
        long_method_smells = [s for s in smells if s.smell_type == SmellType.LONG_METHOD]
        assert len(long_method_smells) == 1
        assert "long_func" in long_method_smells[0].message

    def test_long_method_double_threshold_is_high_severity(self):
        fn = _make_function(name="huge_func", body_lines=110)  # > 50*2=100
        ast = _make_file_ast(functions=[fn])

        smells = detect_smells([ast])
        long = [s for s in smells if s.smell_type == SmellType.LONG_METHOD]
        assert len(long) == 1
        assert long[0].severity == SmellSeverity.HIGH

    def test_detects_too_many_params(self):
        fn = _make_function(name="over_params", params=7)  # threshold=5
        ast = _make_file_ast(functions=[fn])

        smells = detect_smells([ast])
        param_smells = [s for s in smells if s.smell_type == SmellType.TOO_MANY_PARAMS]
        assert len(param_smells) == 1
        assert "7 parameters" in param_smells[0].message

    def test_detects_deep_nesting(self):
        fn = _make_function(name="deep_fn", nesting=5)  # threshold=4
        ast = _make_file_ast(functions=[fn])

        smells = detect_smells([ast])
        nesting_smells = [s for s in smells if s.smell_type == SmellType.DEEP_NESTING]
        assert len(nesting_smells) == 1

    def test_detects_poor_naming(self):
        fn = _make_function(name="x")  # single char
        ast = _make_file_ast(functions=[fn])

        smells = detect_smells([ast], severity_threshold=SmellSeverity.LOW)
        naming_smells = [s for s in smells if s.smell_type == SmellType.POOR_NAMING]
        assert len(naming_smells) == 1

    def test_detects_god_class(self):
        methods = [
            _make_function(name=f"method_{i}", file="src/god.py")
            for i in range(25)   # threshold=20
        ]
        cls = ClassNode(
            name="GodClass",
            file="src/god.py",
            start_line=1,
            end_line=500,
            methods=methods,
        )
        ast = _make_file_ast(classes=[cls], file_path="src/god.py")

        smells = detect_smells([ast])
        god_smells = [s for s in smells if s.smell_type == SmellType.GOD_CLASS]
        assert len(god_smells) == 1
        assert "GodClass" in god_smells[0].message

    def test_detects_dead_unused_import(self):
        source = "import os\nimport sys\n\nx = sys.argv[0]\n"
        ast = _make_file_ast(source=source)

        smells = detect_smells([ast], severity_threshold=SmellSeverity.LOW)
        dead = [s for s in smells if s.smell_type == SmellType.DEAD_CODE]
        # 'os' is imported but never used after import line
        dead_names = [s.message for s in dead]
        assert any("os" in m for m in dead_names)

    def test_no_smell_below_threshold_excluded(self):
        fn = _make_function(name="x")  # LOW severity
        ast = _make_file_ast(functions=[fn])

        smells = detect_smells([ast], severity_threshold=SmellSeverity.MEDIUM)
        naming_smells = [s for s in smells if s.smell_type == SmellType.POOR_NAMING]
        assert len(naming_smells) == 0

    def test_result_sorted_critical_first(self):
        fn_complex = _make_function(
            name="critical_fn",
            source="\n".join(["def critical_fn():"] + [f"    if True: pass" for _ in range(35)]),
        )
        fn_long = _make_function(name="long_fn", body_lines=55)
        ast = _make_file_ast(functions=[fn_long, fn_complex])

        smells = detect_smells([ast])
        severities = [s.severity for s in smells]
        # Critical should come first in severity ordering
        severity_order = {
            SmellSeverity.CRITICAL: 0, SmellSeverity.HIGH: 1,
            SmellSeverity.MEDIUM: 2, SmellSeverity.LOW: 3,
        }
        for i in range(len(severities) - 1):
            assert severity_order[severities[i]] <= severity_order[severities[i + 1]]

    def test_skips_file_with_only_parse_error(self):
        ast = FileAST(
            file_path="broken.py",
            language="python",
            source="",
            parse_error="SyntaxError on line 1",
        )
        smells = detect_smells([ast])
        assert smells == []

    def test_detects_duplication_across_files(self):
        block = "\n".join([f"result = value_{i}" for i in range(8)])
        source1 = block + "\n# file 1 unique code"
        source2 = block + "\n# file 2 unique code"

        ast1 = _make_file_ast(source=source1, file_path="src/a.py")
        ast2 = _make_file_ast(source=source2, file_path="src/b.py")

        smells = detect_smells([ast1, ast2])
        dup_smells = [s for s in smells if s.smell_type == SmellType.DUPLICATION]
        assert len(dup_smells) >= 1


# ── severity_score ────────────────────────────────────────────────────────────

class TestSeverityScore:

    def test_empty_list_returns_zero(self):
        assert severity_score([]) == 0.0

    def test_all_critical_high_score(self, sample_smell_list):
        # sample_smell_list has critical, high, low
        score = severity_score(sample_smell_list)
        assert 0.0 < score <= 1.0

    def test_score_capped_at_1(self):
        smells = [
            SmellItem(
                file="f.py", line=1,
                smell_type=SmellType.HIGH_COMPLEXITY,
                severity=SmellSeverity.CRITICAL,
                message="x", score=1.0,
            )
            for _ in range(10)
        ]
        assert severity_score(smells) == 1.0

    def test_low_only_gives_low_score(self):
        smells = [
            SmellItem(
                file="f.py", line=i,
                smell_type=SmellType.POOR_NAMING,
                severity=SmellSeverity.LOW,
                message="short name", score=0.1,
            )
            for i in range(3)
        ]
        score = severity_score(smells)
        assert score < 0.3


# ── count_by_severity ─────────────────────────────────────────────────────────

class TestCountBySeverity:

    def test_empty_returns_zeros(self):
        counts = count_by_severity([])
        assert counts == {"critical": 0, "high": 0, "medium": 0, "low": 0}

    def test_counts_match_sample_list(self, sample_smell_list):
        counts = count_by_severity(sample_smell_list)
        assert counts["critical"] == 1
        assert counts["high"] == 1
        assert counts["low"] == 1
        assert counts["medium"] == 0

    def test_all_keys_present(self):
        counts = count_by_severity([])
        assert set(counts.keys()) == {"critical", "high", "medium", "low"}
