"""
opsmindai/inference/hybrid_router.py

Routes LLM calls to local (Ollama) or cloud LLM based on task complexity.

Routing rules (SRS FR-13):
  - token_count > 2000 OR score < CONFIDENCE_THRESHOLD → cloud
  - otherwise → local Ollama

Fallback (SRS FR-15): if Ollama unreachable, cloud activates automatically.
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
    Return 'local' or 'cloud' based on prompt complexity (SRS FR-13).

    Args:
        prompt:    Full prompt string.
        task_type: Task category for heuristic weighting.

    Returns:
        'local' or 'cloud'.
    """
    token_count = len(prompt) / 4
    if token_count > 2000:
        return "cloud"
    score = score_task(prompt, task_type)
    if score < settings.CONFIDENCE_THRESHOLD:
        return "cloud"
    return "local"


async def call_llm(
    prompt: str,
    task_type: str = "default",
    system_prompt: Optional[str] = None,
) -> str:
    """
    Route to local_llm or cloud_llm and return generated text.

    If Ollama is unreachable, falls back to cloud automatically (SRS FR-15).

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
                logger.warning("local LLM error (%s) — falling back to cloud", exc)
        else:
            logger.warning("Ollama unreachable — auto-activating cloud LLM (FR-15)")

    logger.info(
        "routing=cloud task=%s tokens≈%d provider=%s",
        task_type, approx_tokens, settings.CLOUD_LLM_PROVIDER,
    )
    return await cloud_llm.generate(prompt, system=system_prompt)
