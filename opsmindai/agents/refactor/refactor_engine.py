"""
opsmindai/agents/refactor/refactor_engine.py

Builds the LLM prompt from code + detected smells + RAG context,
sends it through the hybrid inference router, and parses the
structured response into a list of PatchFile objects.
"""

from __future__ import annotations

import json
import logging
import re
import textwrap
from typing import Optional

from opsmindai.schemas.refactor import PatchFile, SmellItem, SmellSeverity

logger = logging.getLogger(__name__)

def _get_hybrid_router():
    """Lazy load HybridRouter to avoid circular imports.
    
    Returns:
        HybridRouter instance.
        
    Raises:
        ImportError: If hybrid_router module is unavailable.
    """
    from opsmindai.inference.hybrid_router import HybridRouter
    return HybridRouter()

def _get_rag_pipeline():
    """Lazy load RAGPipeline to avoid circular imports.
    
    Returns:
        RAGPipeline instance.
        
    Raises:
        ImportError: If rag_pipeline module is unavailable.
    """
    from opsmindai.memory.rag_pipeline import RAGPipeline
    return RAGPipeline()


# ── Prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = textwrap.dedent("""
You are an expert code refactoring assistant embedded in an automated DevOps platform.
Your task is to refactor code to eliminate detected code smells while preserving
exact functional behaviour.

RULES:
1. Only modify lines that directly relate to the reported smells.
2. Preserve all function signatures, return types, and public API contracts.
3. Do NOT add new dependencies or change import structure unless fixing a dead import.
4. Output ONLY a valid JSON object matching the schema below. No markdown, no explanation.

OUTPUT SCHEMA:
{
  "files": [
    {
      "file": "<relative file path>",
      "refactored_source": "<complete refactored file content as a single string>",
      "explanation": "<one sentence describing what was changed and why>"
    }
  ],
  "summary": "<overall refactoring summary in one paragraph>"
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

    # 3. Source files
    parts.append("=== SOURCE CODE TO REFACTOR ===")
    for file_path, source in file_contents.items():
        parts.append(f"--- {file_path} ---")
        parts.append(source)
        parts.append("")

    parts.append("=== INSTRUCTIONS ===")
    parts.append(
        "Produce the refactored version of every file listed above. "
        "Address ALL smells listed. Return ONLY the JSON object."
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
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_response).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Attempt to extract JSON object with regex
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(f"LLM returned non-JSON response: {raw_response[:300]}")
        data = json.loads(match.group())

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
    skip_low_severity:  bool = True,
) -> tuple[list[PatchFile], int, str]:
    """
    Generate refactor patches for detected smells using the hybrid LLM router.

    Args:
        file_contents:     { file_path: raw_source } for all files to refactor.
        smells:            Detected smell list from smell_detector.py.
        language:          Primary language (for context).
        skip_low_severity: If True, omit LOW severity smells from LLM prompt.

    Returns:
        (patches, tokens_used, model_name)
    """
    # Filter smells for prompt (don't waste tokens on LOW unless requested)
    prompt_smells = smells
    if skip_low_severity:
        prompt_smells = [s for s in smells
                         if s.severity != SmellSeverity.LOW]

    if not prompt_smells:
        logger.info("No significant smells to refactor — skipping LLM call")
        return [], 0, "none"

    # ── RAG context retrieval ────────────────────────────────────
    rag = _get_rag_pipeline()
    smell_summary = "; ".join(
        f"{s.smell_type} in {s.file}:{s.line}" for s in prompt_smells[:5]
    )
    rag_contexts: list[str] = []
    try:
        rag_results = await rag.retrieve(
            query=f"refactor {smell_summary}",
            filter_type="refactor_pattern",
            top_k=3,
        )
        rag_contexts = [r.content for r in rag_results]
        logger.info("RAG retrieved %d refactor patterns", len(rag_contexts))
    except Exception as exc:
        logger.warning("RAG retrieval failed (continuing without context): %s", exc)

    # ── Build prompt ─────────────────────────────────────────────
    user_prompt = _build_user_prompt(file_contents, prompt_smells, rag_contexts)

    # ── Hybrid router call ───────────────────────────────────────
    router = _get_hybrid_router()
    total_tokens = sum(len(s.split()) for s in file_contents.values()) + len(user_prompt.split())

    try:
        response = await router.infer(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            task_type="refactor",
            estimated_tokens=total_tokens,
        )
    except Exception as exc:
        logger.exception("LLM inference failed in refactor_engine")
        raise RuntimeError(f"LLM inference failed: {exc}") from exc

    raw_text    = response["text"]
    tokens_used = response.get("tokens_used", 0)
    model_used  = response.get("model", "unknown")

    logger.info(
        "Refactor LLM call complete: model=%s tokens=%d",
        model_used, tokens_used
    )

    # ── Parse response → patches ─────────────────────────────────
    patches = _parse_llm_response(raw_text, file_contents)
    if not patches:
        logger.warning("LLM returned 0 patches for %d smells", len(prompt_smells))

    return patches, tokens_used, model_used