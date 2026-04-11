"""
app.api.websocket
~~~~~~~~~~~~~~~~~~
WebSocket endpoint for streaming diagnostic events in real time.

Streams:
• triage_complete       — initial hypotheses
• advocate_argument     — each advocate's defense
• skeptic_objection     — penalties and contradictions
• inquisitor_halt/clear — halt decision
• consensus_event       — consensus reached or continue
• final_report          — complete diagnosis

The WebSocket accepts an initial JSON message with patient data,
then streams events as the workflow progresses.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.logging import generate_request_id, get_logger, request_id_ctx
from app.graph.state import OmniState, WorkflowPhase, dict_to_state, state_to_dict
from app.graph.workflow import compile_workflow
from app.schemas.requests import PatientDataInput

logger = get_logger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/diagnose")
async def websocket_diagnosis(ws: WebSocket) -> None:
    """
    WebSocket endpoint for streaming diagnostic workflow.

    Protocol:
    1. Client connects
    2. Client sends JSON: {"patient_data": {...}, "max_rounds": 5}
    3. Server streams events as JSON lines
    4. Server sends {"type": "complete", ...} and closes

    Each event is a JSON object with at least:
    {"type": "<event_type>", "data": {...}, "timestamp": "..."}
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

        # Parse patient data
        patient_input = PatientDataInput.model_validate(
            payload.get("patient_data", payload)
        )
        max_rounds = payload.get("max_rounds", get_settings().max_debate_rounds)

        await ws.send_json({
            "type": "session_start",
            "session_id": session_id,
            "request_id": rid,
        })

        # ── 2. Build initial state ───────────────────────────────
        initial_state = state_to_dict(
            OmniState(
                session_id=session_id,
                request_id=rid,
                phase=WorkflowPhase.INTAKE,
                patient_data=patient_input.model_dump(),
                max_rounds=max_rounds,
            )
        )

        # ── 3. Run workflow with streaming ───────────────────────
        workflow = compile_workflow()

        # Use astream for step-by-step event emission
        async for chunk in workflow.astream(initial_state):
            # Each chunk is a dict with the node name as key
            for node_name, node_state in chunk.items():
                # Extract and forward pending events
                events = node_state.get("pending_events", [])

                # Only send events from this step (new ones)
                # We track by comparing with what we've already sent
                for event in events:
                    event["session_id"] = session_id
                    try:
                        await ws.send_json(event)
                    except Exception:
                        logger.warning(
                            "ws_send_failed",
                            event_type=event.get("type"),
                        )

                # Send phase update
                phase = node_state.get("phase", "")
                await _safe_send(ws, {
                    "type": "phase_update",
                    "phase": phase,
                    "node": node_name,
                    "round": node_state.get("current_round", 0),
                    "session_id": session_id,
                })

            # Clear pending events to avoid re-sending
            if isinstance(chunk, dict):
                for node_state in chunk.values():
                    if isinstance(node_state, dict):
                        node_state["pending_events"] = []

        # ── 4. Send completion ───────────────────────────────────
        await ws.send_json({
            "type": "complete",
            "session_id": session_id,
        })

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
