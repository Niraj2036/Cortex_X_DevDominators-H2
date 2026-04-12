"""
app.api.websocket
~~~~~~~~~~~~~~~~~~
WebSocket endpoint for streaming diagnostic events as a live group chat.

Each agent (Triage, Advocates, Skeptic, Inquisitor, Cortex, Scribe)
emits human-readable ``chat_message`` events that the frontend renders
as a WhatsApp-style conversation.

Protocol:
  1) Client connects
  2) Client sends JSON: {"patient_text": "...", "max_rounds": 3}
  3) Server streams chat_message events + structured events
  4) Server sends {"type": "complete"} and closes
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.logging import generate_request_id, get_logger, request_id_ctx
from app.graph.state import OmniState, WorkflowPhase, state_to_dict
from app.graph.workflow import compile_workflow
from app.services.structuring_service import structure_patient_data

logger = get_logger(__name__)

router = APIRouter(tags=["websocket"])


# ── Agent display info ───────────────────────────────────────────────

_AGENT_DISPLAY = {
    "triage": {"name": "Triage Engine", "emoji": "🔬", "color": "#06b6d4"},
    "advocate": {"name": "Advocate", "emoji": "🛡️", "color": "#60a5fa"},
    "skeptic": {"name": "Skeptic", "emoji": "⚡", "color": "#f59e0b"},
    "inquisitor": {"name": "Inquisitor", "emoji": "🔍", "color": "#a78bfa"},
    "cortex": {"name": "Cortex Engine", "emoji": "🧠", "color": "#c084fc"},
    "scribe": {"name": "Medical Scribe", "emoji": "📋", "color": "#34d399"},
    "system": {"name": "System", "emoji": "⚙️", "color": "#64748b"},
    "gemini": {"name": "Gemini Structuring", "emoji": "💎", "color": "#38bdf8"},
    "peer_rating": {"name": "Peer Rating", "emoji": "📊", "color": "#818cf8"},
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Transcript → Chat Message converters ─────────────────────────────


def _parse_content(raw: str) -> dict[str, Any]:
    """Parse JSON content from a debate entry, fallback to raw text."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"raw": raw}


def _advocate_chat(entry: dict, session_id: str) -> dict[str, Any]:
    """Convert an advocate debate entry to a chat message."""
    agent_id = entry.get("agent_id", "")
    content = _parse_content(entry.get("content", "{}"))

    # Extract diagnosis from agent_id (format: advocate_0_Acute MI)
    parts = agent_id.split("_", 2)
    diagnosis = parts[2] if len(parts) > 2 else "Unknown"

    defense = content.get("defense", "")
    evidence = content.get("evidence", [])
    attacks = content.get("attacks_on_competitors", [])
    confidence = content.get("confidence")

    lines = []
    if defense:
        lines.append(defense)
    if evidence:
        lines.append("\n📋 Evidence:")
        for ev in evidence[:5]:
            lines.append(f"  • {ev}")
    if attacks:
        lines.append("\n⚔️ Against competitors:")
        for atk in attacks[:3]:
            if isinstance(atk, dict):
                lines.append(
                    f"  • vs {atk.get('target', '?')}: {atk.get('weakness', '')}"
                )
            else:
                lines.append(f"  • {atk}")
    if confidence is not None:
        lines.append(f"\n📊 Confidence: {int(float(confidence) * 100)}%")

    return {
        "type": "chat_message",
        "agent_role": "advocate",
        "agent_id": agent_id,
        "agent_name": f"{diagnosis} Advocate",
        "agent_emoji": "🛡️",
        "agent_color": "#60a5fa",
        "content": "\n".join(lines) if lines else str(content),
        "timestamp": _ts(),
        "session_id": session_id,
    }


def _skeptic_chat(entry: dict, session_id: str) -> dict[str, Any]:
    """Convert a skeptic debate entry to a chat message."""
    content = _parse_content(entry.get("content", "{}"))
    agent_id_raw = entry.get("agent_id", "skeptic_main")
    
    # Extract diagnosis from skeptic_0_DiagnosisName
    diag_name = agent_id_raw.split("_", 2)[2] if "_" in agent_id_raw and len(agent_id_raw.split("_")) > 2 else "Unknown Diagnosis"

    assessment = content.get("overall_assessment", "")
    contradictions = content.get("contradictions", [])
    hallucinations = content.get("hallucination_flags", [])
    penalty = float(content.get("uncertainty_penalty", 0.0))
    missing = content.get("missing_tests", [])

    lines = []
    if assessment:
        lines.append(f"**Critique for {diag_name}:**")
        lines.append(assessment)
    if contradictions:
        lines.append("\n🔴 Contradictions:")
        for c in contradictions[:5]:
            if isinstance(c, dict):
                lines.append(f"  • {c.get('issue', '')}")
            else:
                lines.append(f"  • {c}")
    if hallucinations:
        lines.append("\n⚠️ Hallucination flags:")
        for h in hallucinations[:3]:
            if isinstance(h, dict):
                lines.append(
                    f"  • {h.get('claim', '')} — {h.get('reason', '')}"
                )
    if penalty > 0:
        lines.append(f"\n📉 Applied Uncertainty Penalty: -{penalty}")
    if missing:
        lines.append("\n❓ Missing tests required: " + ", ".join(str(m) for m in missing))

    info = _AGENT_DISPLAY["skeptic"]
    return {
        "type": "chat_message",
        "agent_role": "skeptic",
        "agent_id": agent_id_raw,
        "agent_name": f"{info['name']} ({diag_name})",
        "agent_emoji": info["emoji"],
        "agent_color": info["color"],
        "content": "\n".join(lines) if lines else str(content),
        "timestamp": _ts(),
        "session_id": session_id,
    }


def _inquisitor_chat(entry: dict, session_id: str) -> dict[str, Any]:
    """Convert an inquisitor debate entry to a chat message."""
    content = _parse_content(entry.get("content", "{}"))

    should_halt = content.get("should_halt", False)
    assessment = content.get("assessment", "")
    missing_data = content.get("missing_data", [])
    follow_up = content.get("follow_up_questions", [])

    lines = []
    if should_halt:
        lines.append("🛑 HALT RECOMMENDED — Critical data missing.")
    if assessment:
        lines.append(assessment)
    if missing_data:
        lines.append("\n📋 Missing data:")
        for item in missing_data:
            if isinstance(item, dict):
                lines.append(
                    f"  • {item.get('test_name', '?')}: {item.get('reason', '')} "
                    f"(urgency: {item.get('urgency', 'medium')})"
                )
            else:
                lines.append(f"  • {item}")
    if follow_up:
        lines.append("\n❓ Follow-up questions:")
        for q in follow_up[:3]:
            lines.append(f"  • {q}")

    info = _AGENT_DISPLAY["inquisitor"]
    return {
        "type": "chat_message",
        "agent_role": "inquisitor",
        "agent_id": "inquisitor",
        "agent_name": info["name"],
        "agent_emoji": info["emoji"],
        "agent_color": info["color"],
        "content": "\n".join(lines) if lines else str(content),
        "timestamp": _ts(),
        "session_id": session_id,
    }


def _transcript_entry_to_chat(
    entry: dict, session_id: str
) -> dict[str, Any] | None:
    """Route a transcript entry to the correct chat converter."""
    role = entry.get("agent_role", "")
    if role == "advocate":
        return _advocate_chat(entry, session_id)
    elif role == "skeptic":
        return _skeptic_chat(entry, session_id)
    elif role == "inquisitor":
        return _inquisitor_chat(entry, session_id)
    return None


def _event_to_chat(event: dict, session_id: str) -> dict[str, Any] | None:
    """Convert a pending workflow event to a chat message."""
    etype = event.get("type", "")

    if etype == "triage_complete":
        hypotheses = event.get("hypotheses", [])
        model_count = event.get("model_count", "multiple")
        lines = [
            f"Multi-model triage complete — analyzed across {model_count} AI models.\n"
        ]
        for i, h in enumerate(hypotheses):
            conf = int(h.get("confidence", 0) * 100)
            lines.append(f"{i + 1}. {h.get('diagnosis', '?')} — {conf}%")
            for ev in h.get("supporting_evidence", [])[:3]:
                lines.append(f"   • {ev}")
            lines.append("")

        info = _AGENT_DISPLAY["triage"]
        return {
            "type": "chat_message",
            "agent_role": "triage",
            "agent_id": "triage",
            "agent_name": info["name"],
            "agent_emoji": info["emoji"],
            "agent_color": info["color"],
            "content": "\n".join(lines).strip(),
            "timestamp": _ts(),
            "session_id": session_id,
        }

    if etype == "peer_rating_complete":
        scores = event.get("advocate_scores", {})
        lines = ["Peer evaluation complete.\n"]
        for aid, score in scores.items():
            # Prettify advocate_id
            parts = aid.split("_", 2)
            name = parts[2] if len(parts) > 2 else aid
            lines.append(f"  • {name}: {score}/10")

        info = _AGENT_DISPLAY["peer_rating"]
        return {
            "type": "chat_message",
            "agent_role": "peer_rating",
            "agent_id": "peer_rating",
            "agent_name": info["name"],
            "agent_emoji": info["emoji"],
            "agent_color": info["color"],
            "content": "\n".join(lines),
            "timestamp": _ts(),
            "session_id": session_id,
        }

    if etype == "consensus_event":
        leading = event.get("leading_diagnosis", "")
        reached = event.get("consensus_reached", False)
        rnd = event.get("round", 0)

        if reached:
            text = f"✅ Consensus reached on: {leading} (round {rnd})"
        else:
            text = f"Debate continues — leading: {leading} (round {rnd})"

        info = _AGENT_DISPLAY["cortex"]
        return {
            "type": "chat_message",
            "agent_role": "cortex",
            "agent_id": "cortex",
            "agent_name": info["name"],
            "agent_emoji": info["emoji"],
            "agent_color": info["color"],
            "content": text,
            "timestamp": _ts(),
            "session_id": session_id,
        }

    if etype == "final_report":
        report = event.get("report", event)
        primary = report.get("primary_diagnosis", event.get("primary_diagnosis", ""))
        conf = report.get("confidence_pct", event.get("confidence_pct", 0))
        summary = report.get("summary", event.get("summary", ""))
        emergency = report.get("emergency_escalation", event.get("emergency_escalation", False))

        lines = []
        if emergency:
            lines.append("🚨 EMERGENCY ESCALATION RECOMMENDED\n")
        lines.append(f"Primary Diagnosis: {primary}")
        lines.append(f"Confidence: {conf}%")
        if summary:
            lines.append(f"\n{summary}")

        info = _AGENT_DISPLAY["scribe"]
        return {
            "type": "chat_message",
            "agent_role": "scribe",
            "agent_id": "scribe",
            "agent_name": info["name"],
            "agent_emoji": info["emoji"],
            "agent_color": info["color"],
            "content": "\n".join(lines),
            "timestamp": _ts(),
            "session_id": session_id,
        }

    return None


# ── Chat helper ──────────────────────────────────────────────────────


def _system_chat(text: str, session_id: str) -> dict[str, Any]:
    info = _AGENT_DISPLAY["system"]
    return {
        "type": "chat_message",
        "agent_role": "system",
        "agent_id": "system",
        "agent_name": info["name"],
        "agent_emoji": info["emoji"],
        "agent_color": info["color"],
        "content": text,
        "timestamp": _ts(),
        "session_id": session_id,
    }


def _typing_indicator(
    agent_role: str, agent_name: str, is_typing: bool, session_id: str
) -> dict[str, Any]:
    return {
        "type": "typing_indicator",
        "agent_role": agent_role,
        "agent_name": agent_name,
        "is_typing": is_typing,
        "session_id": session_id,
    }


# ── Main WebSocket handler ──────────────────────────────────────────


@router.websocket("/ws/diagnose")
async def websocket_diagnosis(ws: WebSocket) -> None:
    """
    WebSocket endpoint for the group-chat diagnostic experience.

    Protocol:
      1. Client connects
      2. Client sends JSON: {"patient_text": "...", "max_rounds": 3}
         — OR legacy format: {"patient_data": {...}, "max_rounds": 5}
      3. Server streams chat_message events (+ structured events)
      4. Server sends {"type": "complete"} and closes
    """
    await ws.accept()
    rid = generate_request_id()
    request_id_ctx.set(rid)
    session_id = uuid.uuid4().hex[:16]

    logger.info("ws_connected", session_id=session_id)

    try:
        # ── 1. Receive initial payload ───────────────────────────
        raw = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
        payload = json.loads(raw)

        # Support simple text mode OR structured patient_data
        patient_text = payload.get("patient_text", "")
        patient_data_raw = payload.get("patient_data", None)
        ocr_extractions = payload.get("ocr_extractions", None)
        max_rounds = payload.get("max_rounds", get_settings().max_debate_rounds)

        if patient_data_raw and isinstance(patient_data_raw, dict):
            # Legacy structured mode / passed from extract-ocr
            raw_patient_dict = patient_data_raw
        else:
            # Simple text mode — wrap in a dict
            raw_patient_dict = {
                "patient_description": patient_text,
                "additional_notes": patient_text,
            }

        await ws.send_json({
            "type": "session_start",
            "session_id": session_id,
            "request_id": rid,
        })

        # ── 2. Structure via Gemini ──────────────────────────────
        await _safe_send(
            ws,
            _typing_indicator("gemini", "Gemini Structuring", True, session_id),
        )

        gemini_info = _AGENT_DISPLAY["gemini"]
        await _safe_send(
            ws,
            {
                "type": "chat_message",
                "agent_role": "gemini",
                "agent_id": "gemini",
                "agent_name": gemini_info["name"],
                "agent_emoji": gemini_info["emoji"],
                "agent_color": gemini_info["color"],
                "content": "Analyzing and structuring the patient data...",
                "timestamp": _ts(),
                "session_id": session_id,
            },
        )

        structured_patient_data = await structure_patient_data(raw_patient_dict, ocr_extractions)

        # Build a readable summary from the structured data (Flat Structure as requested)
        struct_lines = ["✅ **Data Structured Successfully**\n"]
        for key, value in structured_patient_data.items():
            if key == "_raw_input" or not value: 
                continue
            struct_lines.append(f"**{key}**:\n{value}\n")

        await _safe_send(
            ws,
            _typing_indicator("gemini", "Gemini Structuring", False, session_id),
        )
        await _safe_send(
            ws,
            {
                "type": "chat_message",
                "agent_role": "gemini",
                "agent_id": "gemini",
                "agent_name": gemini_info["name"],
                "agent_emoji": gemini_info["emoji"],
                "agent_color": gemini_info["color"],
                "content": "\n".join(struct_lines),
                "timestamp": _ts(),
                "session_id": session_id,
            },
        )

        # ── 3. Build initial state ───────────────────────────────
        initial_state = state_to_dict(
            OmniState(
                session_id=session_id,
                request_id=rid,
                phase=WorkflowPhase.INTAKE,
                patient_data=structured_patient_data,
                max_rounds=max_rounds,
            )
        )

        # ── 4. Run workflow with streaming ───────────────────────
        workflow = compile_workflow()
        sent_transcript_count = 0
        sent_events_count = 0

        # Map node names to agent roles for typing indicators
        _NODE_TO_AGENT = {
            "triage": ("triage", "Triage Engine"),
            "advocate_round": ("advocate", "Advocates"),
            "skeptic": ("skeptic", "Skeptic"),
            "peer_rating": ("peer_rating", "Peer Rating"),
            "inquisitor": ("inquisitor", "Inquisitor"),
            "cortex": ("cortex", "Cortex Engine"),
            "scribe": ("scribe", "Medical Scribe"),
        }

        transcript_buffer = []

        async for chunk in workflow.astream(initial_state):
            for node_name, node_state in chunk.items():
                # Send typing indicator OFF for this node
                if node_name in _NODE_TO_AGENT:
                    role, name = _NODE_TO_AGENT[node_name]
                    await _safe_send(
                        ws, _typing_indicator(role, name, False, session_id)
                    )

                # ── A) Convert new transcript entries to chat ────
                transcript = node_state.get("debate_transcript", [])
                new_entries = transcript[sent_transcript_count:]
                
                parsed_entries = []
                for entry_obj in new_entries:
                    parsed_entries.append(
                        entry_obj if isinstance(entry_obj, dict)
                        else entry_obj.model_dump() if hasattr(entry_obj, "model_dump")
                        else {}
                    )

                if node_name == "advocate_round":
                    # Buffer advocates and wait for skeptics to pair them
                    transcript_buffer.extend(parsed_entries)
                    sent_transcript_count = len(transcript)
                elif node_name == "skeptic":
                    # Intertwine advocates and skeptics
                    interleaved = []
                    for i in range(max(len(transcript_buffer), len(parsed_entries))):
                        if i < len(transcript_buffer): interleaved.append(transcript_buffer[i])
                        if i < len(parsed_entries): interleaved.append(parsed_entries[i])
                    
                    for entry in interleaved:
                        chat_msg = _transcript_entry_to_chat(entry, session_id)
                        if chat_msg:
                            await _safe_send(ws, chat_msg)
                            
                    transcript_buffer = []
                    sent_transcript_count = len(transcript)
                else:
                    # Normal processing
                    for entry in parsed_entries:
                        chat_msg = _transcript_entry_to_chat(entry, session_id)
                        if chat_msg:
                            await _safe_send(ws, chat_msg)
                    sent_transcript_count = len(transcript)

                # ── B) Convert pending events to chat ────────────
                events = node_state.get("pending_events", [])
                new_events = events[sent_events_count:]
                for event in new_events:
                    event["session_id"] = session_id
                    # Send the raw event (for structured data consumers)
                    await _safe_send(ws, event)
                    # Also send a chat-friendly version
                    chat_msg = _event_to_chat(event, session_id)
                    if chat_msg:
                        await _safe_send(ws, chat_msg)
                sent_events_count = len(events)

                # ── C) Send typing indicator for NEXT node ───────
                # Peek at what comes next based on current phase
                phase = node_state.get("phase", "")
                next_nodes = {
                    "debate": ("advocate", "Advocates"),
                    "consensus": ("scribe", "Medical Scribe"),
                }
                if phase in next_nodes:
                    nrole, nname = next_nodes[phase]
                    await _safe_send(
                        ws, _typing_indicator(nrole, nname, True, session_id)
                    )

            # Clear pending events
            if isinstance(chunk, dict):
                for ns in chunk.values():
                    if isinstance(ns, dict):
                        ns["pending_events"] = []

        # ── 5. Send completion ───────────────────────────────────
        await _safe_send(ws, _system_chat("Diagnostic session complete.", session_id))
        await _safe_send(ws, {"type": "complete", "session_id": session_id})

        logger.info("ws_workflow_complete", session_id=session_id)

    except WebSocketDisconnect:
        logger.info("ws_disconnected", session_id=session_id)
    except asyncio.TimeoutError:
        await _safe_send(ws, {
            "type": "error",
            "error": "Timeout waiting for patient data",
            "session_id": session_id,
        })
    except json.JSONDecodeError as e:
        await _safe_send(ws, {
            "type": "error",
            "error": f"Invalid JSON: {str(e)}",
            "session_id": session_id,
        })
    except Exception as e:
        logger.exception("ws_error", error=str(e))
        await _safe_send(ws, {
            "type": "error",
            "error": str(e),
            "session_id": session_id,
        })
    finally:
        try:
            await ws.close()
        except Exception:
            pass


async def _safe_send(ws: WebSocket, data: dict[str, Any]) -> None:
    """Send JSON over WebSocket, swallowing send errors."""
    try:
        await ws.send_json(data)
    except Exception:
        pass
