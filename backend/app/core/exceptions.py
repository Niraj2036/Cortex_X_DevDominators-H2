"""
app.core.exceptions
~~~~~~~~~~~~~~~~~~~~
Clean exception hierarchy for the Omni_CortexX system.
Every exception carries structured context for logging.
"""

from __future__ import annotations

from typing import Any


class OmniCortexError(Exception):
    """Base exception for the entire Omni_CortexX system."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


# ── LLM Provider Errors ─────────────────────────────────────────────


class LLMProviderError(OmniCortexError):
    """Base for all LLM provider failures."""


class FeatherlessError(LLMProviderError):
    """Featherless API call failed after retries."""


class FeatherlessRateLimitError(FeatherlessError):
    """Featherless returned 429 — rate limit hit."""


class GeminiOCRError(LLMProviderError):
    """Gemini OCR call failed."""


# ── Tool Errors ──────────────────────────────────────────────────────


class ToolError(OmniCortexError):
    """A research tool call failed."""


class ToolTimeoutError(ToolError):
    """Research tool call timed out."""


# ── Workflow Errors ──────────────────────────────────────────────────


class WorkflowError(OmniCortexError):
    """LangGraph workflow error."""


class ConsensusDeadlockError(WorkflowError):
    """Max rounds exhausted without consensus."""


class MissingEvidenceHaltError(WorkflowError):
    """Inquisitor halted the graph — critical data missing."""

    def __init__(
        self,
        message: str,
        *,
        required_tests: list[str] | None = None,
        urgency: str = "medium",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.required_tests = required_tests or []
        self.urgency = urgency


# ── Validation Errors ────────────────────────────────────────────────


class ModelPolicyViolation(OmniCortexError):
    """A forbidden model was requested for a restricted role."""


class OCRParsingError(OmniCortexError):
    """OCR output could not be parsed into structured data."""


# ── API Errors ───────────────────────────────────────────────────────


class FileUploadError(OmniCortexError):
    """Uploaded file is invalid or unsupported."""
