"""
app.graph.state
~~~~~~~~~~~~~~~~
Immutable-safe Pydantic v2 state models for the LangGraph StateGraph.

LangGraph requires TypedDict or dataclass-style state for its channels.
We define Pydantic models for validation, then expose a TypedDict view
that LangGraph consumes natively.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field

# LangGraph expects TypedDict for state channels — we bridge via a helper.
from typing_extensions import TypedDict


# ── Enumerations ─────────────────────────────────────────────────────


class WorkflowPhase(str, Enum):
    """Tracks which phase the graph is currently in."""

    INTAKE = "intake"
    TRIAGE = "triage"
    DEBATE = "debate"
    CONSENSUS = "consensus"
    HALTED = "halted"
    COMPLETE = "complete"


class Urgency(str, Enum):
    """Clinical urgency classification."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ── Sub-models ───────────────────────────────────────────────────────


class Hypothesis(BaseModel):
    """A diagnostic hypothesis generated during triage."""

    diagnosis: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)
    source_model: str = ""
    source_pass: int = 0


class DebateEntry(BaseModel):
    """One entry in the debate transcript."""

    agent_role: str
    agent_id: str
    content: str
    round_number: int
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class MissingDataItem(BaseModel):
    """A clinical test / datum the inquisitor requests."""

    test_name: str
    reason: str
    urgency: Urgency = Urgency.MEDIUM
    impact_on_diagnosis: str = ""


class PeerRating(BaseModel):
    """One advocate's rating of another advocate."""

    rater_id: str           # who is rating
    ratee_id: str           # who is being rated
    ratee_diagnosis: str    # diagnosis being rated
    score: float = Field(ge=0.0, le=10.0)     # score out of 10
    remark: str = ""        # free-form remark on the case strength
    round_number: int = 0


class SourceCredibility(BaseModel):
    """Skeptic's assessment of a cited source's credibility."""

    source_url: str = ""
    source_title: str = ""
    cited_by_advocate: str = ""     # advocate agent_id
    credibility_score: float = Field(default=0.5, ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    verified: bool = False


class DiagnosisResult(BaseModel):
    """Final structured diagnosis output."""

    primary_diagnosis: str
    confidence_pct: float = Field(ge=0.0, le=100.0)
    differential_list: list[dict[str, Any]] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradictory_evidence: list[str] = Field(default_factory=list)
    missing_investigations: list[str] = Field(default_factory=list)
    recommended_next_tests: list[str] = Field(default_factory=list)
    emergency_escalation: bool = False
    scribe_summary: str = ""


# ── Core Pydantic State ─────────────────────────────────────────────


class OmniState(BaseModel):
    """
    Complete graph state.

    All fields have defaults so partial updates work cleanly.
    LangGraph channels merge dicts — we rely on ``model_copy(update=...)``
    for immutable-safe transitions.
    """

    # ─ Identifiers
    session_id: str = ""
    request_id: str = ""

    # ─ Phase tracking
    phase: WorkflowPhase = WorkflowPhase.INTAKE
    current_round: int = 0
    max_rounds: int = 5

    # ─ Patient data (from OCR + user input)
    patient_data: dict[str, Any] = Field(default_factory=dict)
    ocr_extractions: list[dict[str, Any]] = Field(default_factory=list)

    # ─ Triage outputs
    raw_triage_outputs: list[dict[str, Any]] = Field(default_factory=list)
    active_hypotheses: list[Hypothesis] = Field(default_factory=list)

    # ─ Debate
    debate_transcript: list[DebateEntry] = Field(default_factory=list)
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    uncertainty_penalties: dict[str, float] = Field(default_factory=dict)

    # ─ Peer ratings & elimination
    peer_ratings: list[PeerRating] = Field(default_factory=list)
    advocate_scores: dict[str, float] = Field(default_factory=dict)
    eliminated_advocates: list[str] = Field(default_factory=list)

    # ─ Source credibility (from skeptic)
    source_credibility: list[SourceCredibility] = Field(default_factory=list)

    # ─ Missing data
    missing_data: list[MissingDataItem] = Field(default_factory=list)
    halt_reason: str | None = None

    # ─ Consensus
    consensus_reached: bool = False
    final_diagnosis: DiagnosisResult | None = None

    # ─ Comprehensive audit trail (built by scribe)
    audit_trail: dict[str, Any] = Field(default_factory=dict)

    # ─ Streaming events (consumed by WebSocket)
    pending_events: list[dict[str, Any]] = Field(default_factory=list)

    # ─ Error tracking
    errors: list[str] = Field(default_factory=list)


# ── LangGraph TypedDict bridge ──────────────────────────────────────
# LangGraph's StateGraph channels work with TypedDict.
# We serialize OmniState ↔ dict at the graph boundary.


class OmniStateDict(TypedDict, total=False):
    """TypedDict mirror of OmniState for LangGraph channel compatibility."""

    session_id: str
    request_id: str
    phase: str
    current_round: int
    max_rounds: int
    patient_data: dict[str, Any]
    ocr_extractions: list[dict[str, Any]]
    raw_triage_outputs: list[dict[str, Any]]
    active_hypotheses: list[dict[str, Any]]
    debate_transcript: list[dict[str, Any]]
    confidence_scores: dict[str, float]
    uncertainty_penalties: dict[str, float]
    peer_ratings: list[dict[str, Any]]
    advocate_scores: dict[str, float]
    eliminated_advocates: list[str]
    source_credibility: list[dict[str, Any]]
    missing_data: list[dict[str, Any]]
    halt_reason: str | None
    consensus_reached: bool
    final_diagnosis: dict[str, Any] | None
    audit_trail: dict[str, Any]
    pending_events: list[dict[str, Any]]
    errors: list[str]


def state_to_dict(state: OmniState) -> dict[str, Any]:
    """Convert OmniState → plain dict for LangGraph."""
    return state.model_dump(mode="python")


def dict_to_state(d: dict[str, Any]) -> OmniState:
    """Reconstruct OmniState from a LangGraph state dict."""
    return OmniState.model_validate(d)
