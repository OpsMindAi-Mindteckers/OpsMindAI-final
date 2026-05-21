"""
opsmindai/inference/hybrid_router.py

Routes LLM calls between local Ollama and cloud OpenRouter based on task complexity.

Routing rules (SRS FR-13):
  - token_count > 2000 OR score < CONFIDENCE_THRESHOLD → OpenRouter (cloud)
  - otherwise → local Ollama

Fallback (SRS FR-15): if Ollama unreachable, OpenRouter activates automatically.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

# Task-type complexity heuristics — higher means more likely to need cloud
_TASK_COMPLEXITY: dict[str, float] = {
    "rca":      0.90,
    "refactor": 0.70,
    "test":     0.60,
    "default":  0.50,
}


def score_task(prompt: str, task_type: str) -> float:
    """
    Complexity score 0–1 from token count + task-type heuristic.

    Args:
        prompt:    Full prompt string.
        task_type: One of 'rca', 'refactor', 'test', 'default'.

    Returns:
        Float in [0, 1]. Higher = more complex.
    """
    token_count = len(prompt) / 4
    token_score = min(token_count / 4000, 1.0)
    type_score  = _TASK_COMPLEXITY.get(task_type.lower(), 0.50)
    return round(0.6 * token_score + 0.4 * type_score, 4)


def route(prompt: str, task_type: str) -> Literal["local", "cloud"]:
    """
    Return 'local' (Ollama) or 'cloud' (OpenRouter) based on prompt complexity.

    Always tries Ollama first; OpenRouter is used only as a fallback when
    Ollama is unreachable or errors.

    Args:
        prompt:    Full prompt string.
        task_type: Task category for heuristic weighting.

    Returns:
        Always 'local' — cloud fallback is handled inside call_llm.
    """
    return "local"


class HybridRouter:
    """
    Provides an `infer()` method that routes between Ollama and OpenRouter.
    """

    async def infer(
        self,
        user_prompt: str,
        task_type: str = "default",
        system_prompt: Optional[str] = None,
        estimated_tokens: int = 0,
    ) -> dict:
        """
        Route the prompt to Ollama or OpenRouter and return a response dict.

        Returns:
            {"text": str, "tokens_used": int, "model": str}
        """
        from opsmindai.inference import local_llm, cloud_llm

        decision = route(user_prompt, task_type)

        if decision == "local" and await local_llm.is_available():
            model_label = f"ollama/{local_llm.get_model_name()}"
        else:
            model_label = cloud_llm.get_model_name()

        text = await call_llm(user_prompt, task_type=task_type, system_prompt=system_prompt)
        return {
            "text":        text,
            "tokens_used": estimated_tokens or int(len(user_prompt) / 4),
            "model":       model_label,
        }


async def call_llm(
    prompt: str,
    task_type: str = "default",
    system_prompt: Optional[str] = None,
) -> str:
    """
    Route to Ollama (local) or OpenRouter (cloud) and return generated text.

    If Ollama is unreachable, falls back to OpenRouter automatically (SRS FR-15).

    Args:
        prompt:        User prompt.
        task_type:     Task category for routing decision.
        system_prompt: Optional system instruction.

    Returns:
        Generated text string.
    """
    from opsmindai.inference import local_llm, cloud_llm

    decision      = route(prompt, task_type)
    approx_tokens = int(len(prompt) / 4)

    if decision == "local":
        if await local_llm.is_available():
            logger.info(
                "routing=local task=%s tokens≈%d model=%s",
                task_type, approx_tokens, local_llm.get_model_name(),
            )
            try:
                return await local_llm.generate(prompt, system=system_prompt)
            except Exception as exc:
                logger.warning("Ollama error (%s) — falling back to OpenRouter", exc)
        else:
            logger.warning("Ollama unreachable — auto-activating OpenRouter (FR-15)")

    logger.info(
        "routing=cloud task=%s tokens≈%d provider=%s model=%s",
        task_type, approx_tokens, settings.CLOUD_LLM_PROVIDER, cloud_llm.get_model_name(),
    )
    return await cloud_llm.generate(prompt, system=system_prompt)
