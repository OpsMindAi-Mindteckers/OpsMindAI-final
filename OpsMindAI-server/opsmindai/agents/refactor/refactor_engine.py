"""
opsmindai/agents/refactor/refactor_engine.py

Builds the LLM prompt from code + detected smells + RAG context,
sends it through the hybrid inference router, and parses the
structured response into a list of PatchFile objects.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import textwrap
from typing import Optional

from opsmindai.schemas.refactor import PatchFile, SmellItem, SmellSeverity
from opsmindai.core.config import settings

logger = logging.getLogger(__name__)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Fallback models tried in order when the primary model is rate-limited.
# These use different upstream providers to avoid the same rate-limit bucket.
_FALLBACK_MODELS = [
    "minimax/minimax-m2-her",
    "deepseek/deepseek-v3.2",
    "anthropic/claude-3.5-haiku",
    "meta-llama/llama-3.2-3b-instruct",
    "openai/gpt-oss-20b",
]


async def _call_openrouter_refactor(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
) -> tuple[str, int]:
    """Call OpenRouter, falling back through free models if rate-limited.

    Args:
        model: OpenRouter model ID selected by the user. Falls back to settings.REFACTOR_MODEL.
    Returns:
        Tuple of (response_text, tokens_used).
    """
    from openai import AsyncOpenAI  # type: ignore

    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file."
        )

    primary = model or settings.REFACTOR_MODEL
    # Build candidate list: primary first, then unique fallbacks
    candidates = [primary] + [m for m in _FALLBACK_MODELS if m != primary]

    client = AsyncOpenAI(
        base_url=_OPENROUTER_BASE_URL,
        api_key=settings.OPENROUTER_API_KEY,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    last_exc: Exception = RuntimeError("No models available")
    for i, candidate in enumerate(candidates):
        logger.info("refactor_engine → OpenRouter model=%s (attempt %d/%d)", candidate, i + 1, len(candidates))
        try:
            resp = await client.chat.completions.create(
                model=candidate,
                messages=messages,
                max_tokens=16384,
            )
            text        = resp.choices[0].message.content or ""
            tokens_used = resp.usage.total_tokens if resp.usage else 0
            if i > 0:
                logger.info("Succeeded with fallback model %s", candidate)
            return text, tokens_used
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None) or getattr(exc, "status_code", None)
            if status in (429, 503) and i < len(candidates) - 1:
                logger.warning(
                    "Model %s rate-limited (%s), trying next fallback: %s",
                    candidate, status, candidates[i + 1],
                )
                await asyncio.sleep(3)   # short pause before trying next model
                last_exc = exc
            else:
                raise
    raise last_exc


def _get_rag_pipeline():
    """Lazy load RAGPipeline to avoid circular imports."""
    from opsmindai.memory.rag_pipeline import RAGPipeline
    return RAGPipeline()


# ── Prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = textwrap.dedent("""
You are an expert code reviewer and refactoring assistant.
Your job is to find ALL issues in the provided code — including bugs, logic errors,
bad practices, missing error handling, code smells, and anything that would cause
failures or poor behaviour — and produce a fixed version.

RULES:
1. Fix every bug, logic error, and code quality issue you can find.
2. Preserve all function signatures, return types, and public API contracts.
3. Do NOT add new dependencies or change import structure unless fixing a dead import.
4. Output ONLY a valid JSON object matching the schema below. No markdown, no explanation.
5. If you find nothing to fix, still return the JSON with the original source and an explanation saying the code is clean.

OUTPUT SCHEMA:
{
  "files": [
    {
      "file": "<relative file path>",
      "refactored_source": "<complete refactored file content as a single string>",
      "explanation": "<one sentence describing what was changed and why>"
    }
  ],
  "summary": "<overall summary of all issues found and fixes applied>"
}
""").strip()

_FULL_REVIEW_SYSTEM_PROMPT = textwrap.dedent("""
You are an expert code reviewer. Perform a thorough review of the provided code.
Find and fix ALL of the following:
- Bugs and logic errors
- Missing or incorrect error handling
- Security vulnerabilities
- Performance issues
- Dead code or unused variables/imports
- Poor naming or readability issues
- Anything that would cause test failures or runtime errors

Output ONLY a valid JSON object — no markdown, no explanation outside the JSON.

OUTPUT SCHEMA:
{
  "files": [
    {
      "file": "<relative file path>",
      "refactored_source": "<complete refactored file content as a single string>",
      "explanation": "<description of all issues found and fixes applied>"
    }
  ],
  "summary": "<overall summary of all issues found and fixed>"
}
""").strip()


def _build_user_prompt(
    file_contents: dict[str, str],
    smells:        list[SmellItem],
    rag_context:   list[str],
) -> str:
    """Assemble the user-turn prompt from file sources, smell report, and RAG context.
    
    Args:
        file_contents: Dictionary mapping file paths to source code content.
        smells: List of detected code smells to address.
        rag_context: Retrieved past refactor patterns for context.
    
    Returns:
        Formatted prompt string for the LLM.
    """
    parts: list[str] = []

    # 1. RAG context (most relevant past patterns)
    if rag_context:
        parts.append("=== PAST REFACTOR PATTERNS (for reference) ===")
        for i, ctx in enumerate(rag_context[:3], 1):  # cap at 3
            parts.append(f"[Pattern {i}]\n{ctx}")
        parts.append("")

    # 2. Detected smells
    parts.append("=== DETECTED CODE SMELLS ===")
    for smell in smells:
        parts.append(
            f"- [{smell.severity.upper()}] {smell.file}:{smell.line} "
            f"({smell.smell_type}) — {smell.message}"
        )
    parts.append("")

    # 3. Source files (cap each file at 8000 chars to stay within context)
    parts.append("=== SOURCE CODE TO REFACTOR ===")
    for file_path, source in file_contents.items():
        parts.append(f"--- {file_path} ---")
        if len(source) > 8000:
            parts.append(source[:8000])
            parts.append(f"... [truncated {len(source) - 8000} chars]")
        else:
            parts.append(source)
        parts.append("")

    parts.append("=== INSTRUCTIONS ===")
    parts.append(
        "Produce the refactored version of every file listed above. "
        "Address ALL smells listed. Return ONLY the JSON object."
    )

    return "\n".join(parts)


def _build_full_review_prompt(file_contents: dict[str, str]) -> str:
    """Build a full code-review prompt when no AST smells were detected."""
    parts: list[str] = ["=== SOURCE CODE TO REVIEW AND FIX ==="]
    for file_path, source in file_contents.items():
        parts.append(f"--- {file_path} ---")
        if len(source) > 8000:
            parts.append(source[:8000])
            parts.append(f"... [truncated {len(source) - 8000} chars]")
        else:
            parts.append(source)
        parts.append("")
    parts.append("=== INSTRUCTIONS ===")
    parts.append(
        "Perform a thorough review. Find and fix every bug, logic error, "
        "missing error handling, unused import, poor naming, and any other issue. "
        "Return ONLY the JSON object."
    )
    return "\n".join(parts)


# ── Patch generation ──────────────────────────────────────────────────────────

def _unified_diff(original: str, refactored: str, file_path: str) -> tuple[str, int, int]:
    """Produce a unified diff string between original and refactored source.
    
    Args:
        original: Original source code.
        refactored: Refactored source code.
        file_path: Path to the file (used in diff headers).
    
    Returns:
        Tuple of (diff_string, additions_count, deletions_count).
    """
    import difflib
    orig_lines = original.splitlines(keepends=True)
    new_lines  = refactored.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        orig_lines, new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    ))
    additions = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    deletions = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    return "\n".join(diff), additions, deletions


def _parse_llm_response(
    raw_response: str,
    original_sources: dict[str, str],
) -> list[PatchFile]:
    """Parse LLM JSON response into PatchFile objects with unified diffs.
    
    Handles markdown code fences and partial JSON gracefully.
    
    Args:
        raw_response: Raw text response from LLM.
        original_sources: Dictionary mapping file paths to original source code.
    
    Returns:
        List of PatchFile objects ready to apply.
        
    Raises:
        ValueError: If response cannot be parsed as valid JSON.
    """
    if not raw_response or not raw_response.strip():
        raise ValueError("LLM returned an empty response")

    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_response).strip()

    data = None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract a JSON object with regex (handles surrounding text)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    if data is None:
        # Response was likely truncated mid-JSON — try to salvage any complete
        # "files" entries already present before the cut-off point
        partial_files: list[dict] = []
        for m in re.finditer(
            r'\{\s*"file"\s*:\s*"([^"]+)".*?"refactored_source"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}',
            cleaned, re.DOTALL,
        ):
            try:
                partial_files.append(json.loads(m.group()))
            except json.JSONDecodeError:
                pass
        if partial_files:
            logger.warning("LLM response was truncated — salvaged %d partial file(s)", len(partial_files))
            data = {"files": partial_files}
        else:
            raise ValueError(f"LLM returned unparseable response (likely truncated): {raw_response[:300]}")

    patches: list[PatchFile] = []
    for file_data in data.get("files", []):
        file_path  = file_data.get("file", "")
        refactored = file_data.get("refactored_source", "")
        original   = original_sources.get(file_path, "")

        if not refactored or not file_path:
            continue

        diff, additions, deletions = _unified_diff(original, refactored, file_path)
        patches.append(PatchFile(
            file=file_path,
            diff=diff,
            additions=additions,
            deletions=deletions,
        ))
        logger.info(
            "Patch generated for %s: +%d -%d lines",
            file_path, additions, deletions
        )

    return patches


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_refactor(
    file_contents:      dict[str, str],
    smells:             list[SmellItem],
    language:           str = "python",
    skip_low_severity:  bool = False,
    model:              Optional[str] = None,
) -> tuple[list[PatchFile], int, str]:
    """
    Generate refactor patches via OpenRouter.

    When smells are detected, sends them alongside the source for targeted fixes.
    When no smells are detected, performs a full code review and bug-fix pass.

    Returns:
        (patches, tokens_used, model_name)
    """
    prompt_smells = smells
    if skip_low_severity:
        prompt_smells = [s for s in smells if s.severity != SmellSeverity.LOW]

    # ── Choose prompt mode ────────────────────────────────────────
    if prompt_smells:
        # Smell-driven mode: include RAG context + smell report
        rag = _get_rag_pipeline()
        smell_summary = "; ".join(
            f"{s.smell_type} in {s.file}:{s.line}" for s in prompt_smells[:5]
        )
        rag_contexts: list[str] = []
        try:
            rag_results = await rag.retrieve(
                query=f"refactor {smell_summary}",
                doc_type="refactor_pattern",
                top_k=3,
            )
            rag_contexts = [r["content"] for r in rag_results]
            logger.info("RAG retrieved %d refactor patterns", len(rag_contexts))
        except Exception as exc:
            logger.warning("RAG retrieval failed (continuing without context): %s", exc)

        user_prompt  = _build_user_prompt(file_contents, prompt_smells, rag_contexts)
        system_prompt = _SYSTEM_PROMPT
        logger.info("refactor_engine: smell-driven mode (%d smells)", len(prompt_smells))
    else:
        # Full-review mode: no AST smells found — let the LLM find everything
        user_prompt  = _build_full_review_prompt(file_contents)
        system_prompt = _FULL_REVIEW_SYSTEM_PROMPT
        logger.info("refactor_engine: full-review mode (no AST smells detected)")

    # ── OpenRouter inference call ────────────────────────────────
    try:
        raw_text, tokens_used = await _call_openrouter_refactor(system_prompt, user_prompt, model)
    except Exception as exc:
        logger.exception("OpenRouter inference failed in refactor_engine")
        raise RuntimeError(f"OpenRouter inference failed: {exc}") from exc

    model_used = model or settings.REFACTOR_MODEL

    logger.info(
        "Refactor LLM call complete: model=%s tokens=%d",
        model_used, tokens_used
    )

    # ── Parse response → patches ─────────────────────────────────
    patches = _parse_llm_response(raw_text, file_contents)
    if not patches:
        logger.warning("LLM returned 0 patches for %d smells", len(prompt_smells))

    return patches, tokens_used, model_used