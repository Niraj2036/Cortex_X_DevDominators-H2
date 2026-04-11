"""
app.services.report_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Transforms the final OmniState into presentation-ready responses.

No business logic — purely mapping + formatting.
"""

from __future__ import annotations

from typing import Any

from app.graph.state import DiagnosisResult, OmniState
from app.schemas.responses import DiagnosisResponse, HaltedResponse


def build_diagnosis_response(
    state: OmniState,
    session_id: str,
    request_id: str,
) -> DiagnosisResponse:
    """Build the API response from a completed workflow state."""
    status = "complete"
    if state.halt_reason:
        status = "halted"
    elif state.errors:
        status = "error"

    return DiagnosisResponse(
        session_id=session_id,
        request_id=request_id,
        status=status,
        diagnosis=state.final_diagnosis,
        debate_rounds=state.current_round,
        hypotheses_considered=len(state.active_hypotheses),
        missing_data=[
            m.model_dump() if hasattr(m, "model_dump") else m
            for m in state.missing_data
        ],
        halt_reason=state.halt_reason,
        errors=state.errors,
    )


def build_halted_response(
    state: OmniState,
    session_id: str,
) -> HaltedResponse:
    """Build response when the inquisitor halted the workflow."""
    return HaltedResponse(
        session_id=session_id,
        halt_reason=state.halt_reason or "Unknown halt reason",
        required_tests=[
            m.model_dump() if hasattr(m, "model_dump") else m
            for m in state.missing_data
        ],
        partial_hypotheses=[
            h.model_dump() if hasattr(h, "model_dump") else h
            for h in state.active_hypotheses
        ],
    )
