"""
app.graph.workflow
~~~~~~~~~~~~~~~~~~~
LangGraph StateGraph wiring with conditional edges.

FLOW
────
intake → triage → debate_loop:
    advocate_round → skeptic → peer_rating → inquisitor → cortex
        ├── consensus → scribe → END
        ├── halted → END
        └── continue (with eliminated advocates) → advocate_round
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, StateGraph

from app.core.config import get_settings
from app.core.logging import get_logger
from app.graph.agents import (
    advocate_round_node,
    cortex_node,
    inquisitor_node,
    peer_rating_node,
    scribe_node,
    skeptic_node,
    triage_node,
)
from app.graph.state import OmniStateDict, WorkflowPhase

logger = get_logger(__name__)


# ── Conditional edge functions ───────────────────────────────────────


def _after_inquisitor(state: dict[str, Any]) -> Literal["cortex", "__end__"]:
    """Route after inquisitor: halt → end, otherwise → cortex."""
    phase = state.get("phase", "")
    if phase == WorkflowPhase.HALTED.value:
        logger.info("workflow_halted", reason=state.get("halt_reason"))
        return END  # type: ignore[return-value]
    return "cortex"


def _after_cortex(
    state: dict[str, Any],
) -> Literal["scribe", "advocate_round", "__end__"]:
    """
    Route after cortex consensus check.

    • consensus_reached → scribe (final report)
    • max rounds hit → scribe (forced completion)
    • else → advocate_round (continue debate with eliminated advocates removed)
    """
    settings = get_settings()
    consensus = state.get("consensus_reached", False)
    current_round = state.get("current_round", 0)
    phase = state.get("phase", "")

    if consensus or phase == WorkflowPhase.CONSENSUS.value:
        return "scribe"

    if current_round >= settings.max_debate_rounds:
        logger.info("workflow_max_rounds", round=current_round)
        return "scribe"

    return "advocate_round"


# ── Graph builder ────────────────────────────────────────────────────


def build_workflow() -> StateGraph:
    """
    Construct and compile the diagnostic debate StateGraph.

    Returns the compiled graph ready for ``.invoke()`` or ``.astream()``.
    """
    graph = StateGraph(OmniStateDict)

    # ── Register nodes ───────────────────────────────────────────
    graph.add_node("triage", triage_node)
    graph.add_node("advocate_round", advocate_round_node)
    graph.add_node("skeptic", skeptic_node)
    graph.add_node("peer_rating", peer_rating_node)
    graph.add_node("inquisitor", inquisitor_node)
    graph.add_node("cortex", cortex_node)
    graph.add_node("scribe", scribe_node)

    # ── Edges ────────────────────────────────────────────────────
    graph.set_entry_point("triage")

    # Triage → first advocate round
    graph.add_edge("triage", "advocate_round")

    # Advocate → Skeptic → Peer Rating → Inquisitor (debate chain)
    graph.add_edge("advocate_round", "skeptic")
    graph.add_edge("skeptic", "peer_rating")
    graph.add_edge("peer_rating", "inquisitor")

    # Inquisitor → conditional: cortex or halt
    graph.add_conditional_edges(
        "inquisitor",
        _after_inquisitor,
        {"cortex": "cortex", END: END},
    )

    # Cortex → conditional: scribe (consensus), advocate_round (continue), or end
    graph.add_conditional_edges(
        "cortex",
        _after_cortex,
        {
            "scribe": "scribe",
            "advocate_round": "advocate_round",
        },
    )

    # Scribe → END
    graph.add_edge("scribe", END)

    return graph


def compile_workflow():
    """Build and compile the workflow graph."""
    graph = build_workflow()
    return graph.compile()
