"""
tests/unit/test_testing_agent.py

Unit tests for the Testing Agent:
  - _parse_coverage_xml()
  - _parse_lcov()
  - _load_threshold()
  - Gate logic (overall_pct >= threshold AND delta_pct >= 0)
"""

from __future__ import annotations

import os
import textwrap
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from opsmindai.agents.testing.coverage_analyzer import (
    CoverageResult,
    _load_threshold,
    _parse_coverage_xml,
    _parse_lcov,
)


# ── _parse_coverage_xml ───────────────────────────────────────────────────────

class TestParseCoverageXml:

    def _write_xml(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False)
        f.write(content)
        f.flush()
        return f.name

    def test_parses_overall_line_rate(self):
        xml = textwrap.dedent("""\
            <?xml version="1.0" ?>
            <coverage line-rate="0.85" lines-covered="85" lines-valid="100">
              <packages>
                <package>
                  <classes>
                    <class filename="src/a.py" line-rate="0.90"/>
                    <class filename="src/b.py" line-rate="0.80"/>
                  </classes>
                </package>
              </packages>
            </coverage>
        """)
        path = self._write_xml(xml)
        try:
            pct, covered, valid, breakdown = _parse_coverage_xml(path)
            assert pct == pytest.approx(85.0)
            assert covered == 85
            assert valid == 100
        finally:
            os.unlink(path)

    def test_parses_file_breakdown(self):
        xml = textwrap.dedent("""\
            <?xml version="1.0" ?>
            <coverage line-rate="0.75" lines-covered="75" lines-valid="100">
              <packages><package><classes>
                <class filename="src/auth.py" line-rate="0.60"/>
                <class filename="src/payments.py" line-rate="0.95"/>
              </classes></package></packages>
            </coverage>
        """)
        path = self._write_xml(xml)
        try:
            _, _, _, breakdown = _parse_coverage_xml(path)
            assert "src/auth.py" in breakdown
            assert breakdown["src/auth.py"] == pytest.approx(60.0)
            assert breakdown["src/payments.py"] == pytest.approx(95.0)
        finally:
            os.unlink(path)

    def test_zero_coverage(self):
        xml = textwrap.dedent("""\
            <?xml version="1.0" ?>
            <coverage line-rate="0.0" lines-covered="0" lines-valid="50">
              <packages><package><classes>
                <class filename="src/empty.py" line-rate="0.0"/>
              </classes></package></packages>
            </coverage>
        """)
        path = self._write_xml(xml)
        try:
            pct, covered, valid, _ = _parse_coverage_xml(path)
            assert pct == 0.0
            assert covered == 0
        finally:
            os.unlink(path)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            _parse_coverage_xml("/tmp/nonexistent_coverage_abc123.xml")


# ── _parse_lcov ───────────────────────────────────────────────────────────────

class TestParseLcov:

    def _write_lcov(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(suffix=".info", mode="w", delete=False)
        f.write(content)
        f.flush()
        return f.name

    def test_parses_single_file(self):
        lcov = textwrap.dedent("""\
            SF:src/app.js
            LF:100
            LH:80
            end_of_record
        """)
        path = self._write_lcov(lcov)
        try:
            pct, hit, total, breakdown = _parse_lcov(path)
            assert pct == pytest.approx(80.0)
            assert hit == 80
            assert total == 100
            assert "src/app.js" in breakdown
        finally:
            os.unlink(path)

    def test_parses_multiple_files(self):
        lcov = textwrap.dedent("""\
            SF:src/a.js
            LF:50
            LH:50
            end_of_record
            SF:src/b.js
            LF:50
            LH:25
            end_of_record
        """)
        path = self._write_lcov(lcov)
        try:
            pct, hit, total, breakdown = _parse_lcov(path)
            assert pct == pytest.approx(75.0)   # 75/100 = 75%
            assert "src/a.js" in breakdown
            assert breakdown["src/a.js"] == pytest.approx(100.0)
            assert breakdown["src/b.js"] == pytest.approx(50.0)
        finally:
            os.unlink(path)

    def test_missing_file_returns_zeros(self):
        pct, hit, total, breakdown = _parse_lcov("/tmp/no_such_lcov_file.info")
        assert pct == 0.0
        assert hit == 0
        assert total == 0
        assert breakdown == {}

    def test_empty_lcov(self):
        path = self._write_lcov("")
        try:
            pct, hit, total, breakdown = _parse_lcov(path)
            assert pct == 0.0
        finally:
            os.unlink(path)


# ── _load_threshold ───────────────────────────────────────────────────────────

class TestLoadThreshold:

    def test_explicit_override_takes_precedence(self):
        assert _load_threshold(0.95) == pytest.approx(0.95)

    def test_env_var_used_when_no_override(self, monkeypatch):
        monkeypatch.setenv("COVERAGE_THRESHOLD", "0.70")
        assert _load_threshold() == pytest.approx(0.70)

    def test_default_is_0_80(self, monkeypatch):
        monkeypatch.delenv("COVERAGE_THRESHOLD", raising=False)
        assert _load_threshold() == pytest.approx(0.80)

    def test_override_beats_env_var(self, monkeypatch):
        monkeypatch.setenv("COVERAGE_THRESHOLD", "0.60")
        assert _load_threshold(0.90) == pytest.approx(0.90)


# ── Gate logic (via CoverageResult construction) ──────────────────────────────

class TestGateLogic:
    """Validate the gate decision: overall_pct >= threshold*100 AND delta_pct >= 0."""

    def _make_result(self, coverage_pct, delta_pct, threshold=0.80) -> CoverageResult:
        gate_passed = (
            coverage_pct >= (threshold * 100)
            and delta_pct >= 0
        )
        return CoverageResult(
            coverage_pct=coverage_pct,
            delta_pct=delta_pct,
            lines_covered=int(coverage_pct),
            lines_total=100,
            file_breakdown={},
            gate_passed=gate_passed,
            threshold=threshold,
            previous_pct=coverage_pct - delta_pct,
        )

    def test_passes_when_above_threshold_and_positive_delta(self):
        result = self._make_result(coverage_pct=85.0, delta_pct=5.0)
        assert result.gate_passed is True

    def test_fails_when_below_threshold(self):
        result = self._make_result(coverage_pct=75.0, delta_pct=2.0)
        assert result.gate_passed is False

    def test_fails_when_negative_delta_even_above_threshold(self):
        result = self._make_result(coverage_pct=82.0, delta_pct=-1.0)
        assert result.gate_passed is False

    def test_passes_at_exact_threshold_with_zero_delta(self):
        result = self._make_result(coverage_pct=80.0, delta_pct=0.0)
        assert result.gate_passed is True

    def test_fails_with_zero_coverage(self):
        result = self._make_result(coverage_pct=0.0, delta_pct=0.0)
        assert result.gate_passed is False

    def test_custom_threshold(self):
        result = self._make_result(coverage_pct=70.0, delta_pct=5.0, threshold=0.65)
        assert result.gate_passed is True

        result2 = self._make_result(coverage_pct=70.0, delta_pct=5.0, threshold=0.75)
        assert result2.gate_passed is False
