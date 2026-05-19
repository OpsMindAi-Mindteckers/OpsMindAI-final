"""
tests/unit/test_hybrid_router.py

Unit tests for the Hybrid LLM Router:
  - score_task() values across task types and prompt lengths
  - route() decisions: token > 2000 → cloud; low score → cloud
  - FR-15 auto-fallback when Ollama is unreachable
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from opsmindai.inference.hybrid_router import route, score_task


# ── score_task ────────────────────────────────────────────────────────────────

class TestScoreTask:

    def test_empty_prompt_uses_type_score(self):
        # token_score ≈ 0 for empty prompt; result ≈ 0.4 * type_score
        score = score_task("", "rca")
        assert score == pytest.approx(0.4 * 0.90, abs=0.001)

    def test_very_long_prompt_caps_token_score(self):
        long_prompt = "x" * 20000   # chars / 4 = 5000 tokens → capped at 1.0
        score = score_task(long_prompt, "default")
        # 0.6 * 1.0 + 0.4 * 0.50 = 0.80
        assert score == pytest.approx(0.80, abs=0.01)

    def test_rca_type_score_is_0_90(self):
        score = score_task("", "rca")
        # 0.6*0 + 0.4*0.90 = 0.36
        assert score == pytest.approx(0.36, abs=0.001)

    def test_refactor_type_score_is_0_70(self):
        score = score_task("", "refactor")
        assert score == pytest.approx(0.28, abs=0.001)

    def test_test_type_score_is_0_60(self):
        score = score_task("", "test")
        assert score == pytest.approx(0.24, abs=0.001)

    def test_default_type_score_is_0_50(self):
        score = score_task("", "unknown_task")
        assert score == pytest.approx(0.20, abs=0.001)

    def test_score_bounded_0_to_1(self):
        for task_type in ("rca", "refactor", "test", "default"):
            score = score_task("a" * 50000, task_type)
            assert 0.0 <= score <= 1.0

    def test_case_insensitive_task_type(self):
        score_lower = score_task("", "RCA")
        score_upper = score_task("", "rca")
        assert score_lower == score_upper


# ── route ─────────────────────────────────────────────────────────────────────

class TestRoute:

    def test_long_prompt_always_routes_to_cloud(self):
        # > 2000 tokens = > 8000 chars
        long_prompt = "w " * 5000
        result = route(long_prompt, "default")
        assert result == "cloud"

    def test_short_prompt_low_confidence_routes_to_cloud(self, monkeypatch):
        # With CONFIDENCE_THRESHOLD=0.80 and short prompt + 'default' task:
        # score ≈ 0.20 < 0.80 → cloud
        monkeypatch.setattr(
            "opsmindai.inference.hybrid_router.settings.CONFIDENCE_THRESHOLD",
            0.80,
        )
        short_prompt = "Fix this."
        result = route(short_prompt, "default")
        assert result == "cloud"

    def test_high_score_task_routes_to_local(self, monkeypatch):
        # Set a very low threshold so local can win
        monkeypatch.setattr(
            "opsmindai.inference.hybrid_router.settings.CONFIDENCE_THRESHOLD",
            0.05,
        )
        result = route("short prompt", "rca")
        assert result == "local"

    def test_exactly_2000_token_prompt_does_not_force_cloud(self, monkeypatch):
        monkeypatch.setattr(
            "opsmindai.inference.hybrid_router.settings.CONFIDENCE_THRESHOLD",
            0.05,
        )
        # Exactly 2000 tokens = 8000 chars; condition is > 2000 so this stays in scoring
        exact_prompt = "x" * 8000
        # score = 0.6*(8000/4/4000) + 0.4*0.50 = 0.6*0.5 + 0.2 = 0.5
        # with threshold 0.05 this should route local
        result = route(exact_prompt, "default")
        assert result == "local"

    def test_just_over_2000_tokens_forces_cloud(self, monkeypatch):
        monkeypatch.setattr(
            "opsmindai.inference.hybrid_router.settings.CONFIDENCE_THRESHOLD",
            0.05,
        )
        over_prompt = "x" * 8005   # 8005/4 = 2001.25 tokens
        result = route(over_prompt, "default")
        assert result == "cloud"


# ── call_llm (integration with fallback) ──────────────────────────────────────

@pytest.mark.asyncio
class TestCallLlm:

    async def test_routes_to_cloud_when_ollama_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "opsmindai.inference.hybrid_router.settings.CONFIDENCE_THRESHOLD",
            0.05,
        )

        with (
            patch("opsmindai.inference.local_llm.is_available", new_callable=AsyncMock, return_value=False),
            patch("opsmindai.inference.cloud_llm.generate", new_callable=AsyncMock, return_value="cloud response") as mock_cloud,
        ):
            from opsmindai.inference.hybrid_router import call_llm
            result = await call_llm("short prompt", task_type="rca")

        mock_cloud.assert_called_once()
        assert result == "cloud response"

    async def test_uses_local_when_available_and_threshold_met(self, monkeypatch):
        monkeypatch.setattr(
            "opsmindai.inference.hybrid_router.settings.CONFIDENCE_THRESHOLD",
            0.01,
        )

        with (
            patch("opsmindai.inference.local_llm.is_available", new_callable=AsyncMock, return_value=True),
            patch("opsmindai.inference.local_llm.generate", new_callable=AsyncMock, return_value="local response") as mock_local,
            patch("opsmindai.inference.local_llm.get_model_name", return_value="ollama-model"),
            patch("opsmindai.inference.cloud_llm.generate", new_callable=AsyncMock, return_value="cloud response"),
        ):
            from opsmindai.inference.hybrid_router import call_llm
            result = await call_llm("x", task_type="default")

        mock_local.assert_called_once()
        assert result == "local response"

    async def test_fallback_to_cloud_on_local_error(self, monkeypatch):
        monkeypatch.setattr(
            "opsmindai.inference.hybrid_router.settings.CONFIDENCE_THRESHOLD",
            0.01,
        )

        with (
            patch("opsmindai.inference.local_llm.is_available", new_callable=AsyncMock, return_value=True),
            patch("opsmindai.inference.local_llm.generate", new_callable=AsyncMock, side_effect=RuntimeError("ollama down")),
            patch("opsmindai.inference.local_llm.get_model_name", return_value="model"),
            patch("opsmindai.inference.cloud_llm.generate", new_callable=AsyncMock, return_value="fallback") as mock_cloud,
        ):
            from opsmindai.inference.hybrid_router import call_llm
            result = await call_llm("short", task_type="default")

        mock_cloud.assert_called_once()
        assert result == "fallback"
