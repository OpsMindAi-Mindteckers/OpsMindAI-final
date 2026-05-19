"""
tests/unit/test_rag_pipeline.py

Unit tests for the RAG pipeline:
  - build_rag_prompt() context injection
  - store_result() calls upsert correctly
  - retrieve_context() returns SearchResults from vector store
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from opsmindai.memory.rag_pipeline import (
    RAGPipeline,
    SearchResult,
    build_rag_prompt,
    retrieve_context,
    store_result,
)


# ── build_rag_prompt ──────────────────────────────────────────────────────────

class TestBuildRagPrompt:

    def test_empty_context_returns_base_prompt_unchanged(self):
        result = build_rag_prompt("Fix the bug.", [])
        assert result == "Fix the bug."

    def test_single_result_prepends_context_block(self):
        ctx = [
            SearchResult(
                entry_id="e1",
                score=0.92,
                content="Connection pool exhaustion caused by missing close().",
                type="incident",
                metadata={},
            )
        ]
        result = build_rag_prompt("Analyze this alert.", ctx)
        assert "Relevant past context:" in result
        assert "Connection pool exhaustion" in result
        assert "Analyze this alert." in result

    def test_context_appears_before_base_prompt(self):
        ctx = [SearchResult(entry_id="e1", score=0.8, content="past info", type="pattern", metadata={})]
        result = build_rag_prompt("My prompt.", ctx)
        ctx_pos   = result.index("past info")
        prompt_pos = result.index("My prompt.")
        assert ctx_pos < prompt_pos

    def test_multiple_results_numbered(self):
        ctx = [
            SearchResult(entry_id=f"e{i}", score=0.9 - i * 0.1, content=f"content {i}", type="incident", metadata={})
            for i in range(3)
        ]
        result = build_rag_prompt("base", ctx)
        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result

    def test_score_and_type_included_in_output(self):
        ctx = [SearchResult(entry_id="e1", score=0.753, content="data", type="test_result", metadata={})]
        result = build_rag_prompt("prompt", ctx)
        assert "0.753" in result
        assert "test_result" in result


# ── store_result ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestStoreResult:

    async def test_calls_embed_and_upsert(self):
        fake_vector = [0.1] * 384

        with (
            patch("opsmindai.memory.embedder.embed", return_value=fake_vector) as mock_embed,
            patch("opsmindai.memory.vector_store.upsert") as mock_upsert,
        ):
            entry_id = await store_result(
                content="Alert: high CPU on api-service",
                type="incident",
                metadata={"service": "api-service"},
            )

        mock_embed.assert_called_once_with("Alert: high CPU on api-service")
        mock_upsert.assert_called_once()
        call_kwargs = mock_upsert.call_args[1]
        assert call_kwargs["vector"] == fake_vector
        assert "incident" in call_kwargs["metadata"]["type"]
        assert entry_id.startswith("incident_")

    async def test_returns_entry_id_with_type_prefix(self):
        with (
            patch("opsmindai.memory.embedder.embed", return_value=[0.0] * 384),
            patch("opsmindai.memory.vector_store.upsert"),
        ):
            entry_id = await store_result("data", "pattern", {})

        assert entry_id.startswith("pattern_")
        assert len(entry_id) > len("pattern_")

    async def test_metadata_includes_type_field(self):
        captured = {}

        def capture_upsert(**kwargs):
            captured.update(kwargs)

        with (
            patch("opsmindai.memory.embedder.embed", return_value=[0.0] * 384),
            patch("opsmindai.memory.vector_store.upsert", side_effect=capture_upsert),
        ):
            await store_result("content", "test_result", {"repo": "my-repo"})

        assert captured["metadata"]["type"] == "test_result"
        assert captured["metadata"]["repo"] == "my-repo"


# ── retrieve_context ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRetrieveContext:

    async def test_returns_search_results(self):
        fake_vector = [0.5] * 384
        fake_hits = [
            {
                "entry_id": "incident_001",
                "score": 0.95,
                "content": "Previous incident with same fingerprint",
                "type": "incident",
                "metadata": {"service": "api"},
            }
        ]

        with (
            patch("opsmindai.memory.embedder.embed", return_value=fake_vector),
            patch("opsmindai.memory.vector_store.search", return_value=fake_hits),
        ):
            results = await retrieve_context("high CPU on api", top_k=5)

        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].entry_id == "incident_001"
        assert results[0].score == pytest.approx(0.95)

    async def test_empty_on_search_failure(self):
        with (
            patch("opsmindai.memory.embedder.embed", side_effect=RuntimeError("embed fail")),
        ):
            results = await retrieve_context("anything")

        assert results == []

    async def test_passes_filter_type_to_search(self):
        with (
            patch("opsmindai.memory.embedder.embed", return_value=[0.0] * 384),
            patch("opsmindai.memory.vector_store.search", return_value=[]) as mock_search,
        ):
            await retrieve_context("query", top_k=3, filter_type="incident")

        mock_search.assert_called_once_with([0.0] * 384, top_k=3, filter_type="incident")


# ── RAGPipeline shim ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRAGPipelineShim:

    async def test_retrieve_delegates_to_module_function(self):
        fake_results = [
            SearchResult(entry_id="e1", score=0.90, content="ctx", type="incident", metadata={})
        ]

        with patch("opsmindai.memory.rag_pipeline.retrieve_context") as mock_retrieve:
            mock_retrieve.return_value = fake_results

            rag = RAGPipeline()
            results = await rag.retrieve("query", top_k=3)

        mock_retrieve.assert_called_once_with("query", 3, None)
        assert len(results) == 1

    async def test_retrieve_filters_by_threshold(self):
        fake_results = [
            SearchResult(entry_id="e1", score=0.90, content="high", type="incident", metadata={}),
            SearchResult(entry_id="e2", score=0.30, content="low",  type="incident", metadata={}),
        ]

        with patch("opsmindai.memory.rag_pipeline.retrieve_context", return_value=fake_results):
            rag = RAGPipeline()
            results = await rag.retrieve("q", threshold=0.50)

        assert len(results) == 1
        assert results[0].entry_id == "e1"

    async def test_add_results_calls_store_result(self):
        with patch("opsmindai.memory.rag_pipeline.store_result") as mock_store:
            mock_store.return_value = "pattern_abc"

            rag = RAGPipeline()
            await rag.add_results("content", {"type": "pattern", "service": "svc"})

        mock_store.assert_called_once_with("content", "pattern", {"type": "pattern", "service": "svc"})
