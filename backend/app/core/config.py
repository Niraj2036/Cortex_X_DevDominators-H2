"""
app.core.config
~~~~~~~~~~~~~~~~
Centralised, type-safe configuration via pydantic-settings.
Every setting is validated at startup; missing keys crash early.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # ── Gemini (OCR only) ────────────────────────────────────────────
    gemini_api_key: str = Field(..., description="Google Gemini API key for OCR")
    gemini_model: str = Field(
        "gemini-2.5-flash",
        description="Gemini model identifier for OCR calls",
    )

    # ── Featherless AI (all agent reasoning) ─────────────────────────
    # Comma-separated API keys for round-robin load balancing
    featherless_api_keys_raw: str = Field(
        ...,
        alias="FEATHERLESS_API_KEY",
        description="Comma-separated Featherless API keys",
    )
    featherless_base_url: str = Field(
        "https://api.featherless.ai/v1/chat/completions",
        description="Featherless chat completions endpoint",
    )
    featherless_budget_per_key: int = Field(
        4,
        ge=1,
        le=16,
        description="Max concurrency budget per API key",
    )

    @property
    def featherless_api_keys(self) -> list[str]:
        """Parse comma-separated API keys into a list."""
        keys = [k.strip() for k in self.featherless_api_keys_raw.split(",") if k.strip()]
        if not keys:
            raise ValueError("At least one Featherless API key is required")
        return keys

    # ── Model concurrency costs ──────────────────────────────────────
    # Heavy models cost 4 units per request; light models cost 2 units.
    # Default cost for unlisted models is 4 (conservative).
    heavy_models: list[str] = Field(
        default_factory=lambda: [
            "deepseek-ai/DeepSeek-V3.2",
            "Qwen/Qwen2.5-72B-Instruct",
            "moonshotai/Kimi-K2-Instruct-0905",
        ],
        description="Models that cost 4 concurrency units per request",
    )
    light_models: list[str] = Field(
        default_factory=lambda: [
            "google/gemma-4-31B-it",
            "Qwen/Qwen3-32B",
            "google/gemma-4-26B-A4B",
        ],
        description="Models that cost 2 concurrency units per request",
    )

    def model_cost(self, model_id: str) -> int:
        """Return the concurrency cost for a given model."""
        if model_id in self.light_models:
            return 2
        return 4  # heavy or unknown models default to 4

    # ── Research tool keys ───────────────────────────────────────────
    tavily_api_key: str = Field("", description="Tavily search API key")
    google_cse_api_key: str = Field("", description="Google Custom Search API key")
    google_cse_cx: str = Field("", description="Google Custom Search engine ID")

    # ── Application ──────────────────────────────────────────────────
    app_env: str = Field("development", description="Environment name")
    app_debug: bool = Field(False, description="Enable debug mode")
    log_level: str = Field("INFO", description="Structured log level")
    max_debate_rounds: int = Field(5, ge=1, le=20, description="Max debate iterations")
    consensus_threshold: float = Field(
        0.85,
        ge=0.0,
        le=1.0,
        description="Adjusted confidence needed to reach consensus",
    )

    # ── CORS ─────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"],
    )

    # ── Optional Redis ───────────────────────────────────────────────
    redis_url: str = Field("redis://localhost:6379/0", description="Redis DSN")
    redis_enabled: bool = Field(False, description="Enable Redis caching layer")

    # ── Triage model roster ──────────────────────────────────────────
    triage_models: list[str] = Field(
        default_factory=lambda: [
            "moonshotai/Kimi-K2.5",
            "google/gemma-4-31B-it",
            "Qwen/Qwen2.5-72B-Instruct",
            "moonshotai/Kimi-K2-Instruct-0905",
            "Qwen/Qwen3-32B",
            "google/gemma-4-26B-A4B",
        ],
    )
    triage_passes_per_model: int = Field(
        2,
        ge=1,
        le=5,
        description="Number of passes each triage model runs",
    )

    # ── Forbidden models ─────────────────────────────────────────────
    advocate_forbidden_models: list[str] = Field(
        default_factory=lambda: ["Qwen/Qwen3-32B"],
    )

    # ── Default agent model ──────────────────────────────────────────
    default_agent_model: str = Field(
        "Qwen/Qwen2.5-72B-Instruct",
        description="Default Featherless model for advocate/skeptic/inquisitor/cortex/scribe",
    )

    # ── HTTP timeouts (seconds) ──────────────────────────────────────
    llm_timeout: float = Field(120.0, description="Timeout for LLM API calls")
    tool_timeout: float = Field(30.0, description="Timeout for research tool calls")

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, v: str) -> str:
        return v.upper()


# ── Singleton accessor ───────────────────────────────────────────────
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached Settings singleton (lazy-initialised)."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
