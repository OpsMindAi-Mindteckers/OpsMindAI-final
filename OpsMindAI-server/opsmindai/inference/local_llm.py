"""
opsmindai/inference/local_llm.py

Ollama / vLLM local LLM client wrapper (SRS §6.5).

Targets the model configured via LOCAL_MODEL_NAME (default: qwen2.5-coder:32b)
running at OLLAMA_BASE_URL.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)


async def generate(prompt: str, system: Optional[str] = None) -> str:
    """
    POST to Ollama /api/generate and return the response text.

    Args:
        prompt: User prompt.
        system: Optional system prompt.

    Returns:
        Generated text string.

    Raises:
        httpx.HTTPStatusError: On non-2xx Ollama response.
        httpx.TimeoutException: If Ollama does not respond within timeout.
    """
    payload: dict = {
        "model":  settings.LOCAL_MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    logger.debug("local_llm → %s model=%s", url, settings.LOCAL_MODEL_NAME)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "")


async def is_available() -> bool:
    """
    Check Ollama reachability via GET /api/tags (SRS §6.5).

    Returns:
        True if Ollama responds HTTP 200, False otherwise.
    """
    try:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except Exception:
        return False


def get_model_name() -> str:
    """Return the configured local model name."""
    return settings.LOCAL_MODEL_NAME
