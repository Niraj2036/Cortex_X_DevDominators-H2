"""
tests.test_workflow
~~~~~~~~~~~~~~~~~~~~
Integration tests for the LangGraph diagnostic workflow.

Tests cover:
• State model validation
• Workflow graph compilation
• Hypothesis deduplication
• State serialisation round-trip
• Phase transitions
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.graph.state import (
    DebateEntry,
    DiagnosisResult,
    Hypothesis,
    MissingDataItem,
    OmniState,
    OmniStateDict,
    Urgency,
    WorkflowPhase,
    dict_to_state,
    state_to_dict,
)


# ── State Model Tests ────────────────────────────────────────────────


class TestOmniState:
    """Test the core OmniState Pydantic model."""

    def test_default_state(self) -> None:
        """Default state should have sane defaults."""
        state = OmniState()
        assert state.phase == WorkflowPhase.INTAKE
        assert state.current_round == 0
        assert state.consensus_reached is False
        assert state.final_diagnosis is None
        assert state.errors == []

    def test_state_with_patient_data(self) -> None:
        """State should accept nested patient data."""
        state = OmniState(
            session_id="test-123",
            patient_data={
                "demographics": {"age": 58, "sex": "male"},
                "symptoms": ["chest pain"],
                "lab_results": {"troponin": 0.45},
            },
        )
        assert state.patient_data["demographics"]["age"] == 58
        assert "chest pain" in state.patient_data["symptoms"]

    def test_immutable_safe_update(self) -> None:
        """State updates via model_copy should not mutate the original."""
        original = OmniState(current_round=1)
        updated = original.model_copy(update={"current_round": 2})
        assert original.current_round == 1
        assert updated.current_round == 2


class TestHypothesis:
    """Test the Hypothesis sub-model."""

    def test_valid_hypothesis(self) -> None:
        hyp = Hypothesis(
            diagnosis="Acute MI",
            confidence=0.85,
            supporting_evidence=["elevated troponin", "ST elevation"],
            source_model="test-model",
        )
        assert hyp.confidence == 0.85
        assert len(hyp.supporting_evidence) == 2

    def test_confidence_bounds(self) -> None:
        """Confidence must be 0.0–1.0."""
        with pytest.raises(Exception):
            Hypothesis(diagnosis="test", confidence=1.5)

        with pytest.raises(Exception):
            Hypothesis(diagnosis="test", confidence=-0.1)


class TestDebateEntry:
    """Test the DebateEntry model."""

    def test_entry_creation(self) -> None:
        entry = DebateEntry(
            agent_role="advocate",
            agent_id="adv_0",
            content="defense text",
            round_number=1,
        )
        assert entry.agent_role == "advocate"
        assert entry.timestamp  # auto-generated


class TestMissingDataItem:
    """Test the MissingDataItem model."""

    def test_with_urgency(self) -> None:
        item = MissingDataItem(
            test_name="ECG",
            reason="Rule out STEMI",
            urgency=Urgency.CRITICAL,
        )
        assert item.urgency == Urgency.CRITICAL


class TestDiagnosisResult:
    """Test the DiagnosisResult model."""

    def test_full_result(self) -> None:
        result = DiagnosisResult(
            primary_diagnosis="Acute Coronary Syndrome",
            confidence_pct=87.5,
            differential_list=[
                {"diagnosis": "Pulmonary Embolism", "confidence_pct": 12.0}
            ],
            supporting_evidence=["Elevated troponin"],
            emergency_escalation=True,
        )
        assert result.emergency_escalation is True
        assert result.confidence_pct == 87.5


# ── Serialisation Tests ──────────────────────────────────────────────


class TestStateSerialization:
    """Test dict ↔ OmniState serialisation."""

    def test_round_trip(self) -> None:
        """state → dict → state should be identity."""
        original = OmniState(
            session_id="s1",
            phase=WorkflowPhase.DEBATE,
            current_round=3,
            patient_data={"age": 42},
            active_hypotheses=[
                Hypothesis(diagnosis="Flu", confidence=0.6)
            ],
            confidence_scores={"Flu": 0.6},
        )

        d = state_to_dict(original)
        restored = dict_to_state(d)

        assert restored.session_id == "s1"
        assert restored.phase == WorkflowPhase.DEBATE
        assert restored.current_round == 3
        assert len(restored.active_hypotheses) == 1

    def test_partial_dict(self) -> None:
        """dict_to_state should handle partial dicts via defaults."""
        d: dict[str, Any] = {"session_id": "partial", "current_round": 2}
        state = dict_to_state(d)
        assert state.session_id == "partial"
        assert state.phase == WorkflowPhase.INTAKE  # default


# ── Workflow Compilation Test ────────────────────────────────────────


class TestWorkflowCompilation:
    """Test that the LangGraph workflow compiles without error."""

    def test_compile_succeeds(self) -> None:
        """The workflow graph should compile."""
        from app.graph.workflow import compile_workflow

        graph = compile_workflow()
        assert graph is not None


# ── Hypothesis Deduplication Test ────────────────────────────────────


class TestDeduplication:
    """Test hypothesis deduplication logic."""

    def test_dedup_merges_same_diagnosis(self) -> None:
        """Same diagnosis from multiple models should merge."""
        from app.graph.agents import _deduplicate_hypotheses

        hyps = [
            Hypothesis(diagnosis="Flu", confidence=0.7, source_model="m1"),
            Hypothesis(diagnosis="flu", confidence=0.8, source_model="m2"),
            Hypothesis(diagnosis="Pneumonia", confidence=0.5, source_model="m1"),
        ]

        deduped = _deduplicate_hypotheses(hyps)
        assert len(deduped) == 2

        # Flu should have averaged confidence
        flu = next(h for h in deduped if h.diagnosis.lower() == "flu")
        assert flu.confidence == 0.75  # (0.7 + 0.8) / 2

    def test_dedup_caps_at_eight(self) -> None:
        """Should cap at 8 hypotheses max."""
        from app.graph.agents import _deduplicate_hypotheses

        hyps = [
            Hypothesis(diagnosis=f"Disease {i}", confidence=0.5)
            for i in range(15)
        ]
        deduped = _deduplicate_hypotheses(hyps)
        assert len(deduped) <= 8
