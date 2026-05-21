"""
opsmindai/inference/cloud_llm.py

Cloud LLM client — OpenRouter (primary) or OpenAI (SRS §6.5).

Provider is selected via CLOUD_LLM_PROVIDER env var:
  - 'openrouter' → OpenRouter API (OpenAI-compatible, any model)
  - 'openai'     → gpt-4o
"""

from __future__ import annotations

import logging
from typing import Optional

from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

_OPENAI_MODEL        = "gpt-4o"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


async def generate(prompt: str, system: Optional[str] = None) -> str:
    """
    Call the configured cloud LLM and return response text.

    Args:
        prompt: User prompt.
        system: Optional system prompt.

    Returns:
        Generated text string.

    Raises:
        RuntimeError: Unknown provider or missing API key.
    """
    provider = settings.CLOUD_LLM_PROVIDER.lower()

    if provider == "openrouter":
        return await _call_openrouter(prompt, system)
    if provider == "openai":
        return await _call_openai(prompt, system)
    raise RuntimeError(f"Unknown CLOUD_LLM_PROVIDER: {provider!r}")


async def _call_openrouter(prompt: str, system: Optional[str]) -> str:
    """Call OpenRouter via OpenAI-compatible endpoint."""
    from openai import AsyncOpenAI  # type: ignore

    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=_OPENROUTER_BASE_URL,
    )

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    model = settings.OPENROUTER_MODEL
    logger.debug("cloud_llm openrouter model=%s", model)

    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=4096,
        extra_headers={
            "HTTP-Referer": "https://opsmindai.com",
            "X-Title": "OpsMind AI",
        },
    )
    return resp.choices[0].message.content or ""


async def _call_openai(prompt: str, system: Optional[str]) -> str:
    """Call OpenAI Chat Completions API."""
    from openai import AsyncOpenAI  # type: ignore

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client   = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    logger.debug("cloud_llm openai model=%s", _OPENAI_MODEL)
    resp = await client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=messages,
        max_tokens=4096,
    )
    return resp.choices[0].message.content or ""


async def is_available() -> bool:
    """
    Send a minimal probe to verify cloud API reachability.

    Returns:
        True if the cloud API responds successfully.
    """
    try:
        await generate("ping")
        return True
    except Exception:
        return False


def get_model_name() -> str:
    """Return 'provider/model' string for the active cloud backend."""
    provider = settings.CLOUD_LLM_PROVIDER.lower()
    if provider == "openrouter":
        return f"openrouter/{settings.OPENROUTER_MODEL}"
    if provider == "openai":
        return f"openai/{_OPENAI_MODEL}"
    return f"{provider}/unknown"
