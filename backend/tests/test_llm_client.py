"""
tests.test_llm_client
~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the centralised LLM client module.

Tests cover:
• Cost-aware multi-key scheduling
• Model policy validation
• Gemini OCR request construction
• Error handling (format retries vs no-retry)
• JSON parsing edge cases
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import (
    FeatherlessError,
    FeatherlessRateLimitError,
    GeminiOCRError,
    ModelPolicyViolation,
)
from app.core.llm_client import (
    featherless_chat,
    featherless_chat_content,
    featherless_chat_json,
    gemini_ocr,
    validate_advocate_model,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_settings() -> Settings:
    """Create a test Settings instance with 2 keys."""
    return Settings(
        gemini_api_key="test-gemini-key",
        FEATHERLESS_API_KEY="key-aaa,key-bbb",
        featherless_budget_per_key=4,
        llm_timeout=10.0,
        _env_file=None,
    )


# ── Model Policy Tests ──────────────────────────────────────────────


class TestModelPolicy:
    """Test advocate model validation."""

    def test_allowed_model_passes(self, mock_settings: Settings) -> None:
        validate_advocate_model(
            "Qwen/Qwen2.5-72B-Instruct", settings=mock_settings
        )

    def test_forbidden_model_raises(self, mock_settings: Settings) -> None:
        with pytest.raises(ModelPolicyViolation, match="forbidden"):
            validate_advocate_model("Qwen/Qwen3-32B", settings=mock_settings)

    def test_empty_model_passes(self, mock_settings: Settings) -> None:
        validate_advocate_model("", settings=mock_settings)


# ── Model Cost Tests ────────────────────────────────────────────────


class TestModelCost:
    """Test model concurrency cost classification."""

    def test_heavy_model_cost(self, mock_settings: Settings) -> None:
        """Heavy models should cost 4."""
        assert mock_settings.model_cost("moonshotai/Kimi-K2.5") == 4
        assert mock_settings.model_cost("Qwen/Qwen2.5-72B-Instruct") == 4
        assert mock_settings.model_cost("moonshotai/Kimi-K2-Instruct-0905") == 4

    def test_light_model_cost(self, mock_settings: Settings) -> None:
        """Light models should cost 2."""
        assert mock_settings.model_cost("google/gemma-4-31B-it") == 2
        assert mock_settings.model_cost("Qwen/Qwen3-32B") == 2
        assert mock_settings.model_cost("google/gemma-4-26B-A4B") == 2

    def test_unknown_model_defaults_heavy(self, mock_settings: Settings) -> None:
        """Unknown models should default to cost 4 (conservative)."""
        assert mock_settings.model_cost("some-unknown-model") == 4

    def test_multi_key_parsing(self, mock_settings: Settings) -> None:
        """Comma-separated keys should parse correctly."""
        assert len(mock_settings.featherless_api_keys) == 2
        assert mock_settings.featherless_api_keys == ["key-aaa", "key-bbb"]


# ── Featherless Chat Tests ───────────────────────────────────────────


class TestFeatherlessChat:
    """Test Featherless API caller with cost-aware multi-key worker."""

    @pytest.mark.asyncio
    async def test_successful_call(self, mock_settings: Settings) -> None:
        mock_response = httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "test response",
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

        with patch("app.core.llm_client.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                result = await featherless_chat(
                    messages=[{"role": "user", "content": "hello"}],
                    settings=mock_settings,
                )

        assert result["content"] == "test response"

    @pytest.mark.asyncio
    async def test_rate_limit_raises(self, mock_settings: Settings) -> None:
        mock_response = httpx.Response(429, text="rate limited")

        with patch("app.core.llm_client.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                with pytest.raises(FeatherlessRateLimitError):
                    await featherless_chat(
                        messages=[{"role": "user", "content": "hello"}],
                        settings=mock_settings,
                    )

    @pytest.mark.asyncio
    async def test_server_error_not_retried(self, mock_settings: Settings) -> None:
        mock_response = httpx.Response(500, text="internal error")

        with patch("app.core.llm_client.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                with pytest.raises(FeatherlessError):
                    await featherless_chat(
                        messages=[{"role": "user", "content": "hello"}],
                        settings=mock_settings,
                    )

    @pytest.mark.asyncio
    async def test_network_error_not_retried(self, mock_settings: Settings) -> None:
        with patch("app.core.llm_client.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.ConnectError("refused")):
                with pytest.raises(FeatherlessError):
                    await featherless_chat(
                        messages=[{"role": "user", "content": "hello"}],
                        settings=mock_settings,
                    )


class TestFeatherlessJsonParsing:
    """Test JSON parsing from Featherless responses."""

    @pytest.mark.asyncio
    async def test_json_content_parsed(self, mock_settings: Settings) -> None:
        json_content = json.dumps({"hypotheses": [{"diagnosis": "flu"}]})
        mock_response = httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": json_content},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

        with patch("app.core.llm_client.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                result = await featherless_chat_json(
                    messages=[{"role": "user", "content": "test"}],
                    settings=mock_settings,
                )

        assert isinstance(result, dict)
        assert "hypotheses" in result

    @pytest.mark.asyncio
    async def test_markdown_fenced_json(self, mock_settings: Settings) -> None:
        content = '```json\n{"key": "value"}\n```'
        mock_response = httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

        with patch("app.core.llm_client.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                result = await featherless_chat_json(
                    messages=[{"role": "user", "content": "test"}],
                    settings=mock_settings,
                )

        assert isinstance(result, dict)
        assert result.get("key") == "value"


# ── Gemini OCR Tests ─────────────────────────────────────────────────


class TestGeminiOCR:
    """Test Gemini OCR caller."""

    @pytest.mark.asyncio
    async def test_requires_file_input(self, mock_settings: Settings) -> None:
        with pytest.raises(GeminiOCRError, match="required"):
            await gemini_ocr(settings=mock_settings)

    @pytest.mark.asyncio
    async def test_successful_extraction(self, mock_settings: Settings) -> None:
        gemini_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    [{"test": "troponin", "value": "0.45"}]
                                )
                            }
                        ]
                    }
                }
            ]
        }
        mock_resp = httpx.Response(200, json=gemini_response)

        with patch("app.core.llm_client.get_settings", return_value=mock_settings):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
                result = await gemini_ocr(
                    file_bytes=b"%PDF-fake-pdf-content",
                    settings=mock_settings,
                )

        assert isinstance(result, list)
        assert len(result) >= 1
        assert "test" in result[0] or "content" in result[0]
