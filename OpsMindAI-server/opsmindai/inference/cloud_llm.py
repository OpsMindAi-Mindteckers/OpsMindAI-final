"""
opsmindai/inference/cloud_llm.py

Cloud LLM client — Anthropic (Claude) or OpenAI (GPT-4o) (SRS §6.5).

Provider is selected via CLOUD_LLM_PROVIDER env var:
  - 'anthropic'  → claude-sonnet-4-6
  - 'openai'     → gpt-4o
"""

from __future__ import annotations

import logging
from typing import Optional

from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

_ANTHROPIC_MODEL = "claude-sonnet-4-6"
_OPENAI_MODEL    = "gpt-4o"


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

    if provider == "anthropic":
        return await _call_anthropic(prompt, system)
    if provider == "openai":
        return await _call_openai(prompt, system)
    raise RuntimeError(f"Unknown CLOUD_LLM_PROVIDER: {provider!r}")


async def _call_anthropic(prompt: str, system: Optional[str]) -> str:
    """Call Anthropic Messages API with prompt caching support."""
    import anthropic  # type: ignore

    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    kwargs: dict = {
        "model":      _ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "messages":   [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    logger.debug("cloud_llm anthropic model=%s", _ANTHROPIC_MODEL)
    msg = await client.messages.create(**kwargs)
    return msg.content[0].text


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
    if provider == "anthropic":
        return f"anthropic/{_ANTHROPIC_MODEL}"
    if provider == "openai":
        return f"openai/{_OPENAI_MODEL}"
    return f"{provider}/unknown"
