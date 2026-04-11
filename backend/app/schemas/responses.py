"""
app.schemas.responses
~~~~~~~~~~~~~~~~~~~~~~
Pydantic v2 response models for the diagnostic API.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.graph.state import DiagnosisResult, Urgency


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "1.0.0"
    environment: str = "development"


class ReadinessResponse(BaseModel):
    """Readiness probe response."""

    ready: bool = True
    checks: dict[str, bool] = Field(default_factory=dict)


class OCRExtractionResponse(BaseModel):
    """Response from the file upload / OCR endpoint."""

    session_id: str
    document_type: str
    extractions: list[dict[str, Any]]
    patient_data_merged: dict[str, Any] = Field(default_factory=dict)


class DiagnosisResponse(BaseModel):
    """Full diagnostic result response."""

    session_id: str
    request_id: str
    status: str = Field(description="complete | halted | error")
    diagnosis: DiagnosisResult | None = None
    debate_rounds: int = 0
    hypotheses_considered: int = 0
    missing_data: list[dict[str, Any]] = Field(default_factory=list)
    halt_reason: str | None = None
    errors: list[str] = Field(default_factory=list)


class HaltedResponse(BaseModel):
    """Returned when the inquisitor halts the workflow."""

    session_id: str
    status: str = "halted"
    halt_reason: str
    required_tests: list[dict[str, Any]] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    urgency: Urgency = Urgency.MEDIUM
    partial_hypotheses: list[dict[str, Any]] = Field(default_factory=list)


class StreamEvent(BaseModel):
    """A single event pushed over WebSocket / SSE."""

    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""
    session_id: str = ""


class ErrorResponse(BaseModel):
    """Standard error response body."""

    error: str
    detail: str = ""
    request_id: str = ""
