# """
# opsmindai/agents/refactor/refactor_engine.py

# Builds the LLM prompt from code + detected smells + RAG context,
# sends it through the hybrid inference router, and parses the
# structured response into a list of PatchFile objects.
# """

# from __future__ import annotations

# import asyncio
# import json
# import logging
# import re
# import textwrap
# from typing import Optional

# from opsmindai.schemas.refactor import PatchFile, SmellItem, SmellSeverity
# from opsmindai.core.config import settings

# logger = logging.getLogger(__name__)

# _OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# # Fallback models tried in order when the primary model is rate-limited.
# # These use different upstream providers to avoid the same rate-limit bucket.
# _FALLBACK_MODELS = [
#     "deepseek/deepseek-v4-flash:free",
#     "meta-llama/llama-3.3-70b-instruct:free",
#     "google/gemma-4-31b-it:free",
#     "nvidia/nemotron-3-super-120b-a12b:free",
#     "openai/gpt-oss-120b:free",
# ]


# async def _call_openrouter_refactor(
#     system_prompt: str,
#     user_prompt: str,
#     model: Optional[str] = None,
# ) -> tuple[str, int]:
#     """Call OpenRouter, falling back through free models if rate-limited.

#     Args:
#         model: OpenRouter model ID selected by the user. Falls back to settings.REFACTOR_MODEL.
#     Returns:
#         Tuple of (response_text, tokens_used).
#     """
#     from openai import AsyncOpenAI  # type: ignore

#     if not settings.OPENROUTER_API_KEY:
#         raise RuntimeError(
#             "OPENROUTER_API_KEY is not set. Add it to your .env file."
#         )

#     # Emergency free-tier models — appended last so they are tried only when every
#     # configured model fails with 402/429/503 (zero-credit account safety net).
#     _FREE_EMERGENCY_FALLBACKS = [
#         "openai/gpt-oss-20b",
#         "minimax/minimax-m2.5",
#         "nousresearch/hermes-3-llama-3.1-405b",
#         "meta-llama/llama-3.2-3b-instruct",
#         "meta-llama/llama-3.3-70b-instruct",
#         "nvidia/nemotron-3-super-120b-a12b",
#         "openai/gpt-oss-120b",
#         "minimax/minimax-m2.5:free",
#         "minimax/minimax-m2.5",
#         "nvidia/nemotron-3-nano-30b-a3b:free",
#         "nvidia/nemotron-3-nano-30b-a3b"
#     ]

#     primary = model or settings.REFACTOR_MODEL
#     # Build candidate list: primary first, then unique configured fallbacks,
#     # then emergency free-tier models that never require purchased credits.
#     seen: set[str] = set()
#     candidates: list[str] = []
#     for m in [primary] + _FALLBACK_MODELS + _FREE_EMERGENCY_FALLBACKS:
#         if m not in seen:
#             seen.add(m)
#             candidates.append(m)

#     client = AsyncOpenAI(
#         base_url=_OPENROUTER_BASE_URL,
#         api_key=settings.OPENROUTER_API_KEY,
#     )
#     messages = [
#         {"role": "system", "content": system_prompt},
#         {"role": "user",   "content": user_prompt},
#     ]

#     last_exc: Exception = RuntimeError("No models available")
#     for i, candidate in enumerate(candidates):
#         logger.info("refactor_engine → OpenRouter model=%s (attempt %d/%d)", candidate, i + 1, len(candidates))
#         try:
#             resp = await client.chat.completions.create(
#                 model=candidate,
#                 messages=messages,
#                 max_tokens=4096,
#             )
#             text        = resp.choices[0].message.content or ""
#             tokens_used = resp.usage.total_tokens if resp.usage else 0
#             if i > 0:
#                 logger.info("Succeeded with fallback model %s", candidate)
#             return text, tokens_used
#         except Exception as exc:
#             status = getattr(getattr(exc, "response", None), "status_code", None) or getattr(exc, "status_code", None)
#             # 404=model not found, 429=rate-limited, 402=insufficient credits, 503=unavailable — try next model
#             if status in (404, 429, 402, 503) and i < len(candidates) - 1:
#                 logger.warning(
#                     "Model %s unavailable (%s), trying next candidate [%d/%d]: %s",
#                     candidate, status, i + 2, len(candidates), candidates[i + 1],
#                 )
#                 await asyncio.sleep(1)
#                 last_exc = exc
#             else:
#                 raise
#     raise last_exc


# def _get_rag_pipeline():
#     """Lazy load RAGPipeline to avoid circular imports."""
#     from opsmindai.memory.rag_pipeline import RAGPipeline
#     return RAGPipeline()


# # ── Prompt templates ──────────────────────────────────────────────────────────

# _SYSTEM_PROMPT = textwrap.dedent("""
# You are an expert code reviewer and refactoring assistant.
# Your job is to find ALL issues in the provided code — including bugs, logic errors,
# bad practices, missing error handling, code smells, and anything that would cause
# failures or poor behaviour — and produce a fixed version.

# RULES:
# 1. Fix every bug, logic error, and code quality issue you can find.
# 2. Preserve all function signatures, return types, and public API contracts.
# 3. Do NOT add new dependencies or change import structure unless fixing a dead import.
# 4. Output ONLY a valid JSON object matching the schema below. No markdown, no explanation.
# 5. If you find nothing to fix, still return the JSON with the original source and an explanation saying the code is clean.

# COMMON BUG PATTERNS TO LOOK FOR:
# - Commented-out class or function declarations (e.g. `//class Foo {`) that break the file structure
# - Incorrect spread operators (e.g. `{ obj, ...updates }` instead of `{ ...obj, ...updates }`)
# - Logic inversions in filter/comparison operators (e.g. `===` where `!==` is needed)
# - Commented-out logic inside methods (e.g. a filter callback that is fully commented out)
# - Overly complex methods that can be dramatically simplified
# - Unused variables that are set but never read

# OUTPUT SCHEMA:
# {
#   "files": [
#     {
#       "file": "<relative file path>",
#       "refactored_source": "<complete refactored file content as a single string>",
#       "explanation": "<one sentence describing what was changed and why>"
#     }
#   ],
#   "summary": "<overall summary of all issues found and fixes applied>"
# }
# """).strip()

# _FULL_REVIEW_SYSTEM_PROMPT = textwrap.dedent("""
# You are an expert code reviewer. Perform a thorough review of the provided code.
# Find and fix ALL of the following:
# - Bugs and logic errors (especially commented-out declarations, logic inversions, wrong operators)
# - Commented-out class/function declarations that break file structure (e.g. `//class Foo {`)
# - Incorrect object spreads (e.g. `{ obj, ...updates }` should be `{ ...obj, ...updates }`)
# - Inverted filter logic (e.g. `=== tag` in a "remove tag" filter that should be `!== tag`)
# - Commented-out callback bodies inside methods that make them always return empty results
# - Missing or incorrect error handling
# - Security vulnerabilities
# - Performance issues
# - Dead code or unused variables/imports
# - Poor naming or readability issues
# - Anything that would cause test failures or runtime errors

# Output ONLY a valid JSON object — no markdown, no explanation outside the JSON.

# OUTPUT SCHEMA:
# {
#   "files": [
#     {
#       "file": "<relative file path>",
#       "refactored_source": "<complete refactored file content as a single string>",
#       "explanation": "<description of all issues found and fixes applied>"
#     }
#   ],
#   "summary": "<overall summary of all issues found and fixed>"
# }
# """).strip()


# def _build_user_prompt(
#     file_contents: dict[str, str],
#     smells:        list[SmellItem],
#     rag_context:   list[str],
# ) -> str:
#     """Assemble the user-turn prompt from file sources, smell report, and RAG context.
    
#     Args:
#         file_contents: Dictionary mapping file paths to source code content.
#         smells: List of detected code smells to address.
#         rag_context: Retrieved past refactor patterns for context.
    
#     Returns:
#         Formatted prompt string for the LLM.
#     """
#     parts: list[str] = []

#     # 1. RAG context (most relevant past patterns)
#     if rag_context:
#         parts.append("=== PAST REFACTOR PATTERNS (for reference) ===")
#         for i, ctx in enumerate(rag_context[:3], 1):  # cap at 3
#             parts.append(f"[Pattern {i}]\n{ctx}")
#         parts.append("")

#     # 2. Detected smells
#     parts.append("=== DETECTED CODE SMELLS ===")
#     for smell in smells:
#         parts.append(
#             f"- [{smell.severity.upper()}] {smell.file}:{smell.line} "
#             f"({smell.smell_type}) — {smell.message}"
#         )
#     parts.append("")

#     # 3. Source files (cap each file at 8000 chars to stay within context)
#     parts.append("=== SOURCE CODE TO REFACTOR ===")
#     for file_path, source in file_contents.items():
#         parts.append(f"--- {file_path} ---")
#         if len(source) > 8000:
#             parts.append(source[:8000])
#             parts.append(f"... [truncated {len(source) - 8000} chars]")
#         else:
#             parts.append(source)
#         parts.append("")

#     parts.append("=== INSTRUCTIONS ===")
#     parts.append(
#         "Produce the refactored version of every file listed above. "
#         "Address ALL smells listed. Return ONLY the JSON object."
#     )

#     return "\n".join(parts)


# def _build_full_review_prompt(file_contents: dict[str, str]) -> str:
#     """Build a full code-review prompt when no AST smells were detected."""
#     parts: list[str] = ["=== SOURCE CODE TO REVIEW AND FIX ==="]
#     for file_path, source in file_contents.items():
#         parts.append(f"--- {file_path} ---")
#         if len(source) > 8000:
#             parts.append(source[:8000])
#             parts.append(f"... [truncated {len(source) - 8000} chars]")
#         else:
#             parts.append(source)
#         parts.append("")
#     parts.append("=== INSTRUCTIONS ===")
#     parts.append(
#         "Perform a thorough review. Find and fix every bug, logic error, "
#         "missing error handling, unused import, poor naming, and any other issue. "
#         "Return ONLY the JSON object."
#     )
#     return "\n".join(parts)


# # ── Patch generation ──────────────────────────────────────────────────────────

# def _unified_diff(original: str, refactored: str, file_path: str) -> tuple[str, int, int]:
#     """Produce a unified diff string between original and refactored source.
    
#     Args:
#         original: Original source code.
#         refactored: Refactored source code.
#         file_path: Path to the file (used in diff headers).
    
#     Returns:
#         Tuple of (diff_string, additions_count, deletions_count).
#     """
#     import difflib
#     orig_lines = original.splitlines(keepends=True)
#     new_lines  = refactored.splitlines(keepends=True)
#     diff = list(difflib.unified_diff(
#         orig_lines, new_lines,
#         fromfile=f"a/{file_path}",
#         tofile=f"b/{file_path}",
#         lineterm="",
#     ))
#     additions = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
#     deletions = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
#     return "\n".join(diff), additions, deletions


# def _parse_llm_response(
#     raw_response: str,
#     original_sources: dict[str, str],
# ) -> list[PatchFile]:
#     """Parse LLM JSON response into PatchFile objects with unified diffs.
    
#     Handles markdown code fences and partial JSON gracefully.
    
#     Args:
#         raw_response: Raw text response from LLM.
#         original_sources: Dictionary mapping file paths to original source code.
    
#     Returns:
#         List of PatchFile objects ready to apply.
        
#     Raises:
#         ValueError: If response cannot be parsed as valid JSON.
#     """
#     if not raw_response or not raw_response.strip():
#         raise ValueError("LLM returned an empty response")

#     # Strip markdown code fences if present
#     cleaned = re.sub(r"```(?:json)?\s*", "", raw_response).strip()

#     # Detect plain-text "code is clean" responses from models that ignored JSON instructions
#     _NO_ISSUES_PHRASES = (
#         "no refactoring is required",
#         "no refactoring required",
#         "no changes are needed",
#         "no changes needed",
#         "code is already clean",
#         "code looks clean",
#         "already clean",
#         "already maintainable",
#         "nothing to fix",
#         "no issues found",
#         "no bugs found",
#         "code is clean",
#         "looks good",
#     )
#     lowered = cleaned.lower()
#     if not cleaned.startswith("{") and any(p in lowered for p in _NO_ISSUES_PHRASES):
#         logger.info("LLM indicated no refactoring needed (plain-text response) — returning 0 patches")
#         return []

#     data = None
#     try:
#         data = json.loads(cleaned)
#     except json.JSONDecodeError:
#         # Try to extract a JSON object with regex (handles surrounding text)
#         match = re.search(r"\{.*\}", cleaned, re.DOTALL)
#         if match:
#             try:
#                 data = json.loads(match.group())
#             except json.JSONDecodeError:
#                 pass

#     if data is None:
#         # Response was likely truncated mid-JSON — try to salvage any complete
#         # "files" entries already present before the cut-off point
#         partial_files: list[dict] = []
#         for m in re.finditer(
#             r'\{\s*"file"\s*:\s*"([^"]+)".*?"refactored_source"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}',
#             cleaned, re.DOTALL,
#         ):
#             try:
#                 partial_files.append(json.loads(m.group()))
#             except json.JSONDecodeError:
#                 pass
#         if partial_files:
#             logger.warning("LLM response was truncated — salvaged %d partial file(s)", len(partial_files))
#             data = {"files": partial_files}
#         else:
#             # Last resort: if response mentions no issues, return clean rather than crash
#             if any(p in lowered for p in _NO_ISSUES_PHRASES):
#                 logger.info("Unparseable response but indicates clean code — returning 0 patches")
#                 return []
#             raise ValueError(f"LLM returned unparseable response (likely truncated): {raw_response[:300]}")

#     patches: list[PatchFile] = []
#     for file_data in data.get("files", []):
#         file_path  = file_data.get("file", "")
#         refactored = file_data.get("refactored_source", "")
#         original   = original_sources.get(file_path, "")

#         if not refactored or not file_path:
#             continue

#         diff, additions, deletions = _unified_diff(original, refactored, file_path)
#         patches.append(PatchFile(
#             file=file_path,
#             diff=diff,
#             additions=additions,
#             deletions=deletions,
#         ))
#         logger.info(
#             "Patch generated for %s: +%d -%d lines",
#             file_path, additions, deletions
#         )

#     return patches


# # ── Public API ────────────────────────────────────────────────────────────────

# async def generate_refactor(
#     file_contents:      dict[str, str],
#     smells:             list[SmellItem],
#     language:           str = "python",
#     skip_low_severity:  bool = False,
#     model:              Optional[str] = None,
# ) -> tuple[list[PatchFile], int, str]:
#     """
#     Generate refactor patches via OpenRouter.

#     When smells are detected, sends them alongside the source for targeted fixes.
#     When no smells are detected, performs a full code review and bug-fix pass.

#     Returns:
#         (patches, tokens_used, model_name)
#     """
#     prompt_smells = smells
#     if skip_low_severity:
#         prompt_smells = [s for s in smells if s.severity != SmellSeverity.LOW]

#     # ── Choose prompt mode ────────────────────────────────────────
#     if prompt_smells:
#         # Smell-driven mode: include RAG context + smell report
#         rag = _get_rag_pipeline()
#         smell_summary = "; ".join(
#             f"{s.smell_type} in {s.file}:{s.line}" for s in prompt_smells[:5]
#         )
#         rag_contexts: list[str] = []
#         try:
#             rag_results = await rag.retrieve(
#                 query=f"refactor {smell_summary}",
#                 top_k=3,
#             )
#             rag_contexts = [r.content if hasattr(r, "content") else r.get("content", "") for r in rag_results]
#             logger.info("RAG retrieved %d refactor patterns", len(rag_contexts))
#         except Exception as exc:
#             logger.warning("RAG retrieval failed (continuing without context): %s", exc)

#         user_prompt  = _build_user_prompt(file_contents, prompt_smells, rag_contexts)
#         system_prompt = _SYSTEM_PROMPT
#         logger.info("refactor_engine: smell-driven mode (%d smells)", len(prompt_smells))
#     else:
#         # Full-review mode: no AST smells found — let the LLM find everything
#         user_prompt  = _build_full_review_prompt(file_contents)
#         system_prompt = _FULL_REVIEW_SYSTEM_PROMPT
#         logger.info("refactor_engine: full-review mode (no AST smells detected)")

#     # ── OpenRouter inference call ────────────────────────────────
#     try:
#         raw_text, tokens_used = await _call_openrouter_refactor(system_prompt, user_prompt, model)
#     except Exception as exc:
#         logger.exception("OpenRouter inference failed in refactor_engine")
#         raise RuntimeError(f"OpenRouter inference failed: {exc}") from exc

#     model_used = model or settings.REFACTOR_MODEL

#     logger.info(
#         "Refactor LLM call complete: model=%s tokens=%d",
#         model_used, tokens_used
#     )

#     # ── Parse response → patches ─────────────────────────────────
#     patches = _parse_llm_response(raw_text, file_contents)
#     if not patches:
#         logger.warning("LLM returned 0 patches for %d smells", len(prompt_smells))

#     return patches, tokens_used, model_used















"""
opsmindai/agents/refactor/refactor_engine.py

Builds the LLM prompt from code + detected smells + RAG context,
sends it through the hybrid inference router, and parses the
structured response into a list of PatchFile objects.

Fixes applied:
  1. max_tokens raised from 4096 → 16000 (prevents JSON truncation on real codebases)
  2. _is_likely_truncated() — detects truncated responses BEFORE they hit the parser,
     causing the router to try the next model instead of accepting bad output.
  3. _salvage_truncated_json() rewritten with 3 robust strategies:
       - Strategy 1: char-by-char JSON depth tracking to find last complete file object
       - Strategy 2: per-block split scan with lenient regex (handles escaped strings)
       - Strategy 3: file-path-only extraction (graceful degradation, never crashes)
  4. _parse_llm_response() updated with 4-pass parse pipeline using the new salvage fn.
  5. generate_refactor() batches large repos (>40k chars) into groups of 4 files to
     prevent hitting output token limits entirely on large repos.
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
    "deepseek/deepseek-v4-flash:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openai/gpt-oss-120b:free",
]

# How many source chars to allow in a single LLM call before batching.
# 40k chars ~ 10k tokens of input, leaving room for a 16k token output.
_CHAR_LIMIT_PER_BATCH = 40_000

# How many files per batch when the repo exceeds _CHAR_LIMIT_PER_BATCH.
_FILES_PER_BATCH = 4


# ── OpenRouter inference ───────────────────────────────────────────────────────

def _is_likely_truncated(text: str) -> bool:
    """
    Heuristic: a valid JSON response must end with '}' after whitespace.
    If the text starts with '{' but does not close, it was truncated mid-generation.
    Called immediately after each model response so we can try the next model
    instead of accepting output we know will fail the parser.
    """
    stripped = text.strip()
    if not stripped.startswith("{"):
        # Not a JSON object at all — let _parse_llm_response decide
        return False
    return not stripped.endswith("}")


async def _call_openrouter_refactor(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
) -> tuple[str, int]:
    """
    Call OpenRouter, falling back through free models if rate-limited or truncated.

    Args:
        system_prompt: System-turn content for the LLM.
        user_prompt:   User-turn content (source + smells).
        model:         OpenRouter model ID selected by the user.
                       Falls back to settings.REFACTOR_MODEL if not provided.

    Returns:
        Tuple of (response_text, tokens_used).

    Raises:
        RuntimeError: If OPENROUTER_API_KEY is not configured.
        Exception:    If all candidates are exhausted without a valid response.
    """
    from openai import AsyncOpenAI  # type: ignore

    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file."
        )

    # Emergency free-tier models — appended last so they are tried only when every
    # configured model fails with 402/429/503 (zero-credit account safety net).
    _FREE_EMERGENCY_FALLBACKS = [
        "openai/gpt-oss-20b",
        "minimax/minimax-m2.5",
        "nousresearch/hermes-3-llama-3.1-405b",
        "meta-llama/llama-3.2-3b-instruct",
        "meta-llama/llama-3.3-70b-instruct",
        "nvidia/nemotron-3-super-120b-a12b",
        "openai/gpt-oss-120b",
        "minimax/minimax-m2.5:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "nvidia/nemotron-3-nano-30b-a3b",
    ]

    primary = model or settings.REFACTOR_MODEL

    # Build candidate list: primary first, then unique configured fallbacks,
    # then emergency free-tier models that never require purchased credits.
    seen: set[str] = set()
    candidates: list[str] = []
    for m in [primary] + _FALLBACK_MODELS + _FREE_EMERGENCY_FALLBACKS:
        if m not in seen:
            seen.add(m)
            candidates.append(m)

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
        logger.info(
            "refactor_engine → OpenRouter model=%s (attempt %d/%d)",
            candidate, i + 1, len(candidates)
        )
        try:
            resp = await client.chat.completions.create(
                model=candidate,
                messages=messages,
                # FIX: was 4096 — 12 files need 15k–25k output tokens.
                # 16000 is safe for models that support it; models with lower
                # hard limits will return what they can and we salvage below.
                max_tokens=16000,
            )
            text        = resp.choices[0].message.content or ""
            tokens_used = resp.usage.total_tokens if resp.usage else 0

            # FIX: detect truncation BEFORE returning to the caller.
            # If this model cut off mid-JSON, try the next candidate rather
            # than accepting output we know will fail _parse_llm_response.
            if _is_likely_truncated(text):
                logger.warning(
                    "Model %s response appears truncated (%d chars, no closing '}') "
                    "— trying next candidate",
                    candidate, len(text),
                )
                last_exc = ValueError(f"Truncated response from {candidate}")
                await asyncio.sleep(1)
                continue

            if i > 0:
                logger.info("Succeeded with fallback model %s", candidate)
            return text, tokens_used

        except Exception as exc:
            status = (
                getattr(getattr(exc, "response", None), "status_code", None)
                or getattr(exc, "status_code", None)
            )
            # 404=model not found, 429=rate-limited, 402=insufficient credits,
            # 503=unavailable — try next model
            if status in (404, 429, 402, 503) and i < len(candidates) - 1:
                logger.warning(
                    "Model %s unavailable (%s), trying next candidate [%d/%d]: %s",
                    candidate, status, i + 2, len(candidates), candidates[i + 1],
                )
                await asyncio.sleep(1)
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

COMMON BUG PATTERNS TO LOOK FOR:
- Commented-out class or function declarations (e.g. `//class Foo {`) that break the file structure
- Incorrect spread operators (e.g. `{ obj, ...updates }` instead of `{ ...obj, ...updates }`)
- Logic inversions in filter/comparison operators (e.g. `===` where `!==` is needed)
- Commented-out logic inside methods (e.g. a filter callback that is fully commented out)
- Overly complex methods that can be dramatically simplified
- Unused variables that are set but never read

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
- Bugs and logic errors (especially commented-out declarations, logic inversions, wrong operators)
- Commented-out class/function declarations that break file structure (e.g. `//class Foo {`)
- Incorrect object spreads (e.g. `{ obj, ...updates }` should be `{ ...obj, ...updates }`)
- Inverted filter logic (e.g. `=== tag` in a "remove tag" filter that should be `!== tag`)
- Commented-out callback bodies inside methods that make them always return empty results
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
    """
    Assemble the user-turn prompt from file sources, smell report, and RAG context.

    Args:
        file_contents: Dictionary mapping file paths to source code content.
        smells:        List of detected code smells to address.
        rag_context:   Retrieved past refactor patterns for context.

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
    """
    Produce a unified diff string between original and refactored source.

    Args:
        original:   Original source code.
        refactored: Refactored source code.
        file_path:  Path to the file (used in diff headers).

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
    additions = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
    return "\n".join(diff), additions, deletions


def _salvage_truncated_json(cleaned: str, lowered: str) -> Optional[dict]:
    """
    Three-strategy salvage for truncated LLM JSON responses.

    Called by _parse_llm_response when json.loads() and the substring regex both fail,
    meaning the response was cut off before the JSON was complete.

    Strategy 1 — char-by-char JSON depth tracking:
        Walks the "files" array character by character, tracking brace depth and
        string boundaries (including escape sequences). Finds the byte offset of
        the last fully-closed file object, then reconstructs valid JSON by
        appending minimal closing tokens. Most reliable for real-world truncation
        that happens between file objects.

    Strategy 2 — per-block split scan:
        Splits the text on file-object boundaries and applies a lenient regex to
        each block. Handles cases where the closing brace of a file object is
        missing but the refactored_source string itself is complete.

    Strategy 3 — file-path-only extraction:
        Extracts file paths with no source code. Returns empty-source entries so
        the caller gets a structured result and never crashes, even if the model
        produced almost nothing useful.

    Args:
        cleaned: Cleaned response text (markdown fences already stripped).
        lowered: Lower-cased version of cleaned (for phrase checks).

    Returns:
        dict with a "files" key on success, None if all strategies fail.
    """

    # ── Strategy 1: char-by-char depth tracking ───────────────────────────────
    files_key_pos = cleaned.find('"files"')
    if files_key_pos != -1:
        bracket_start = cleaned.find("[", files_key_pos)
        if bracket_start != -1:
            depth       = 0
            in_string   = False
            escape_next = False
            last_obj_end = -1
            i = bracket_start

            while i < len(cleaned):
                ch = cleaned[i]

                if escape_next:
                    escape_next = False
                elif ch == "\\" and in_string:
                    escape_next = True
                elif ch == '"':
                    in_string = not in_string
                elif not in_string:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            last_obj_end = i
                i += 1

            if last_obj_end != -1:
                salvaged = cleaned[:last_obj_end + 1] + "]}"
                try:
                    parsed = json.loads(salvaged)
                    if parsed.get("files"):
                        logger.warning(
                            "Salvage strategy 1: recovered %d complete file(s) "
                            "from truncated JSON via depth tracking",
                            len(parsed["files"]),
                        )
                        return parsed
                except json.JSONDecodeError:
                    pass  # fall through to strategy 2

    # ── Strategy 2: per-block split scan ──────────────────────────────────────
    # Split on the start of each file object so each block contains at most one file entry.
    file_blocks: list[dict] = []
    splits = re.split(r'(?=\{\s*"file"\s*:\s*")', cleaned)

    for block in splits:
        if '"file"' not in block:
            continue

        file_match   = re.search(r'"file"\s*:\s*"([^"]+)"', block)
        # Use a lenient pattern that matches the source string even if the
        # surrounding object is not closed. The inner group captures any
        # sequence of non-quote chars or escape sequences.
        source_match = re.search(
            r'"refactored_source"\s*:\s*"((?:[^"\\]|\\.)+)"',
            block,
            re.DOTALL,
        )

        if file_match and source_match:
            try:
                file_path = file_match.group(1)
                # Wrap in double-quotes and json.loads to correctly unescape
                # all \n, \t, \" sequences the LLM emitted.
                source = json.loads(f'"{source_match.group(1)}"')
                file_blocks.append({"file": file_path, "refactored_source": source})
            except (json.JSONDecodeError, ValueError):
                continue  # skip this block, keep any already-collected ones

    if file_blocks:
        logger.warning(
            "Salvage strategy 2: extracted %d file block(s) via split scan",
            len(file_blocks),
        )
        return {"files": file_blocks}

    # ── Strategy 3: file paths only ───────────────────────────────────────────
    # Last resort — we can at least tell the caller which files were mentioned.
    # Returning empty refactored_source means _parse_llm_response will skip the
    # patch (the `if not refactored` guard), producing 0 patches rather than crashing.
    file_paths = re.findall(r'"file"\s*:\s*"([^"]+)"', cleaned)
    if file_paths:
        logger.warning(
            "Salvage strategy 3: found %d file path(s) but no parseable source "
            "— returning empty patches (graceful degradation)",
            len(file_paths),
        )
        return {"files": [{"file": p, "refactored_source": ""} for p in file_paths]}

    return None  # all strategies exhausted


def _parse_llm_response(
    raw_response: str,
    original_sources: dict[str, str],
) -> list[PatchFile]:
    """
    Parse LLM JSON response into PatchFile objects with unified diffs.

    Four-pass parse pipeline:
      Pass 1 — direct json.loads() on cleaned text.
      Pass 2 — extract largest JSON substring (handles surrounding prose).
      Pass 3 — _salvage_truncated_json() for responses cut off mid-generation.
      Pass 4 — plain-text "code is clean" fallback (return 0 patches, no crash).

    Args:
        raw_response:     Raw text response from LLM.
        original_sources: Dictionary mapping file paths to original source code.

    Returns:
        List of PatchFile objects ready to apply. Empty list means no changes needed.

    Raises:
        ValueError: If all four passes fail to produce parseable output.
    """
    if not raw_response or not raw_response.strip():
        raise ValueError("LLM returned an empty response")

    # Strip markdown code fences (both opening and closing)
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_response).strip()
    cleaned = re.sub(r"\s*```\s*$", "", cleaned).strip()

    _NO_ISSUES_PHRASES = (
        "no refactoring is required",
        "no refactoring required",
        "no changes are needed",
        "no changes needed",
        "code is already clean",
        "code looks clean",
        "already clean",
        "already maintainable",
        "nothing to fix",
        "no issues found",
        "no bugs found",
        "code is clean",
        "looks good",
    )
    lowered = cleaned.lower()

    # Early exit: plain-text "nothing to do" from a model that ignored JSON instructions
    if not cleaned.startswith("{") and any(p in lowered for p in _NO_ISSUES_PHRASES):
        logger.info(
            "LLM indicated no refactoring needed (plain-text response) — returning 0 patches"
        )
        return []

    data: Optional[dict] = None

    # ── Pass 1: direct parse ───────────────────────────────────────────────────
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # ── Pass 2: extract JSON substring ────────────────────────────────────────
    # Handles models that emit prose before/after the JSON object.
    if data is None:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    # ── Pass 3: truncation salvage ─────────────────────────────────────────────
    # _is_likely_truncated() in _call_openrouter_refactor already filtered the
    # worst cases, but a model may return a response that closes the outer object
    # without closing inner arrays — handle that here.
    if data is None:
        data = _salvage_truncated_json(cleaned, lowered)

    # ── Pass 4: plain-text clean-code fallback ─────────────────────────────────
    if data is None:
        if any(p in lowered for p in _NO_ISSUES_PHRASES):
            logger.info(
                "Unparseable response but content indicates clean code — returning 0 patches"
            )
            return []
        raise ValueError(
            f"LLM returned unparseable response (likely truncated): {raw_response[:300]}"
        )

    # ── Build PatchFile objects from parsed data ───────────────────────────────
    patches: list[PatchFile] = []
    for file_data in data.get("files", []):
        file_path  = file_data.get("file", "")
        refactored = file_data.get("refactored_source", "")
        original   = original_sources.get(file_path, "")

        # Skip entries where the salvage produced no source (strategy 3 entries)
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
            file_path, additions, deletions,
        )

    return patches


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_refactor(
    file_contents:     dict[str, str],
    smells:            list[SmellItem],
    language:          str = "python",
    skip_low_severity: bool = False,
    model:             Optional[str] = None,
) -> tuple[list[PatchFile], int, str]:
    """
    Generate refactor patches via OpenRouter.

    When smells are detected, sends them alongside the source for targeted fixes.
    When no smells are detected, performs a full code review and bug-fix pass.

    For large repos (total source > _CHAR_LIMIT_PER_BATCH chars), the file set is
    split into batches of _FILES_PER_BATCH to stay within the model's output token
    budget. Results are merged and returned as a single flat list of patches.

    Args:
        file_contents:     Dict mapping relative file path → source code.
        smells:            List of SmellItem objects from the AST analyser.
        language:          Primary language of the repo (informational, not used in routing).
        skip_low_severity: If True, LOW-severity smells are excluded from the prompt.
        model:             OpenRouter model ID override. Falls back to settings.REFACTOR_MODEL.

    Returns:
        Tuple of (patches, total_tokens_used, model_name_used).
    """
    prompt_smells = smells
    if skip_low_severity:
        prompt_smells = [s for s in smells if s.severity != SmellSeverity.LOW]

    # ── Resolve RAG context once (shared across all batches) ──────────────────
    rag_contexts: list[str] = []
    if prompt_smells:
        rag = _get_rag_pipeline()
        smell_summary = "; ".join(
            f"{s.smell_type} in {s.file}:{s.line}" for s in prompt_smells[:5]
        )
        try:
            rag_results = await rag.retrieve(
                query=f"refactor {smell_summary}",
                top_k=3,
            )
            rag_contexts = [
                r.content if hasattr(r, "content") else r.get("content", "")
                for r in rag_results
            ]
            logger.info("RAG retrieved %d refactor patterns", len(rag_contexts))
        except Exception as exc:
            logger.warning("RAG retrieval failed (continuing without context): %s", exc)

    model_used = model or settings.REFACTOR_MODEL

    # ── Helper: run one batch through the LLM ─────────────────────────────────
    async def _run_batch(batch_files: dict[str, str]) -> tuple[list[PatchFile], int]:
        if prompt_smells:
            batch_smells  = [s for s in prompt_smells if s.file in batch_files]
            system_prompt = _SYSTEM_PROMPT
            user_prompt   = _build_user_prompt(batch_files, batch_smells, rag_contexts)
            logger.info(
                "refactor_engine: smell-driven mode (%d smells, %d files in batch)",
                len(batch_smells), len(batch_files),
            )
        else:
            system_prompt = _FULL_REVIEW_SYSTEM_PROMPT
            user_prompt   = _build_full_review_prompt(batch_files)
            logger.info(
                "refactor_engine: full-review mode (%d files in batch)",
                len(batch_files),
            )

        try:
            raw_text, tokens = await _call_openrouter_refactor(
                system_prompt, user_prompt, model
            )
        except Exception as exc:
            logger.exception("OpenRouter inference failed in refactor_engine")
            raise RuntimeError(f"OpenRouter inference failed: {exc}") from exc

        logger.info(
            "Refactor LLM call complete: model=%s tokens=%d", model_used, tokens
        )

        patches = _parse_llm_response(raw_text, batch_files)
        if not patches:
            logger.warning(
                "LLM returned 0 patches for batch of %d file(s)", len(batch_files)
            )
        return patches, tokens

    # ── Decide: single call vs. batched ───────────────────────────────────────
    total_chars = sum(len(v) for v in file_contents.values())

    if total_chars <= _CHAR_LIMIT_PER_BATCH:
        # Happy path: entire repo fits in one call
        all_patches, total_tokens = await _run_batch(file_contents)
    else:
        # Large repo: split into batches of _FILES_PER_BATCH files each
        logger.info(
            "Large repo (%d chars across %d files) — batching into groups of %d",
            total_chars, len(file_contents), _FILES_PER_BATCH,
        )
        all_patches: list[PatchFile] = []
        total_tokens = 0
        file_items = list(file_contents.items())

        for batch_start in range(0, len(file_items), _FILES_PER_BATCH):
            batch = dict(file_items[batch_start : batch_start + _FILES_PER_BATCH])
            logger.info(
                "Processing batch %d/%d: %s",
                batch_start // _FILES_PER_BATCH + 1,
                -(-len(file_items) // _FILES_PER_BATCH),  # ceil division
                list(batch.keys()),
            )
            batch_patches, batch_tokens = await _run_batch(batch)
            all_patches.extend(batch_patches)
            total_tokens += batch_tokens

    return all_patches, total_tokens, model_used