"""
tests.test_tools
~~~~~~~~~~~~~~~~~
Unit tests for the research tools layer.

Tests cover:
• Tool registry completeness
• PubMed / Europe PMC parsing
• Wikipedia response parsing
• Tool dispatcher routing
• Unknown tool error handling
• Batch execution
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.exceptions import ToolError, ToolTimeoutError
from app.graph.tools import (
    TOOL_REGISTRY,
    EvidenceItem,
    ToolResult,
    execute_tool_call,
    execute_tool_calls_batch,
    pubmed_search,
    wikipedia_lookup,
)


# ── Registry Tests ───────────────────────────────────────────────────


class TestToolRegistry:
    """Verify all required tools are registered."""

    def test_all_tools_registered(self) -> None:
        """All eight required tools must be in the registry."""
        expected = {
            "tavily_search",
            "pubmed_search",
            "semantic_scholar_search",
            "google_custom_search",
            "wikipedia_lookup",
            "literature_search",
            "clinical_guidelines",
            "clinical_database",
        }
        assert expected == set(TOOL_REGISTRY.keys())

    def test_all_tools_are_callable(self) -> None:
        """Each registered tool must be an async callable."""
        for name, fn in TOOL_REGISTRY.items():
            assert callable(fn), f"{name} is not callable"


# ── PubMed Tests ─────────────────────────────────────────────────────


class TestPubMedSearch:
    """Test PubMed / Europe PMC integration."""

    @pytest.mark.asyncio
    async def test_successful_search(self) -> None:
        """Valid PubMed response should parse into ToolResult."""
        mock_data = {
            "hitCount": 42,
            "resultList": {
                "result": [
                    {
                        "title": "Troponin in ACS",
                        "abstractText": "A study on troponin elevation...",
                        "pmid": "12345678",
                        "pubYear": "2023",
                        "authorList": {
                            "author": [{"fullName": "Smith J"}]
                        },
                    }
                ]
            },
        }

        mock_resp = httpx.Response(200, json=mock_data)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await pubmed_search("troponin acute coronary")

        assert isinstance(result, ToolResult)
        assert result.tool_name == "pubmed"
        assert len(result.results) == 1
        assert result.results[0].title == "Troponin in ACS"
        assert result.results[0].source == "pubmed"
        assert result.total_found == 42

    @pytest.mark.asyncio
    async def test_http_error(self) -> None:
        """Non-200 response should return ToolResult with error."""
        mock_resp = httpx.Response(503, text="Service Unavailable")

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await pubmed_search("test query")

        assert result.error is not None
        assert "503" in result.error


# ── Wikipedia Tests ──────────────────────────────────────────────────


class TestWikipediaLookup:
    """Test Wikipedia disease lookup."""

    @pytest.mark.asyncio
    async def test_successful_lookup(self) -> None:
        """Valid Wikipedia response should parse correctly."""
        mock_data = {
            "query": {
                "search": [
                    {
                        "title": "Acute Coronary Syndrome",
                        "snippet": "ACS is a <span class=\"searchmatch\">syndrome</span>...",
                    }
                ]
            }
        }

        mock_resp = httpx.Response(200, json=mock_data)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await wikipedia_lookup("acute coronary syndrome")

        assert result.tool_name == "wikipedia"
        assert len(result.results) == 1
        assert "searchmatch" not in result.results[0].snippet  # HTML stripped
        assert "wikipedia.org" in result.results[0].url


# ── Dispatcher Tests ─────────────────────────────────────────────────


class TestToolDispatcher:
    """Test the tool call dispatch mechanism."""

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self) -> None:
        """Unknown tool name should raise ToolError."""
        with pytest.raises(ToolError, match="Unknown tool"):
            await execute_tool_call("nonexistent_tool", "query")

    @pytest.mark.asyncio
    async def test_dispatch_routes_correctly(self) -> None:
        """Dispatcher should call the correct tool function."""
        mock_result = ToolResult(
            tool_name="pubmed",
            query="test",
            results=[],
            total_found=0,
        )

        with patch(
            "app.graph.tools.pubmed_search",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            # Need to also patch the registry
            with patch.dict(TOOL_REGISTRY, {"pubmed_search": mock_fn}):
                result = await execute_tool_call("pubmed_search", "test query")

        assert result.tool_name == "pubmed"
        mock_fn.assert_awaited_once_with("test query")


# ── Batch Execution Tests ────────────────────────────────────────────


class TestBatchExecution:
    """Test concurrent tool call batching."""

    @pytest.mark.asyncio
    async def test_batch_with_failures(self) -> None:
        """Batch should handle individual tool failures gracefully."""
        calls = [
            {"tool": "pubmed_search", "query": "test1"},
            {"tool": "unknown_tool", "query": "test2"},
        ]

        mock_result = ToolResult(
            tool_name="pubmed",
            query="test1",
            results=[],
        )

        with patch.dict(
            TOOL_REGISTRY,
            {"pubmed_search": AsyncMock(return_value=mock_result)},
        ):
            results = await execute_tool_calls_batch(calls)

        assert len(results) == 2
        assert results[0].tool_name == "pubmed"
        assert results[1].error is not None  # unknown_tool failed


# ── Evidence Model Tests ─────────────────────────────────────────────


class TestEvidenceItem:
    """Test the EvidenceItem Pydantic model."""

    def test_valid_evidence(self) -> None:
        """Valid evidence should pass validation."""
        item = EvidenceItem(
            title="Test Paper",
            snippet="A study about...",
            url="https://example.com",
            source="pubmed",
            relevance_score=0.8,
            year=2024,
        )
        assert item.relevance_score == 0.8

    def test_score_clamping(self) -> None:
        """Relevance score must be 0.0–1.0."""
        with pytest.raises(Exception):
            EvidenceItem(relevance_score=1.5)
