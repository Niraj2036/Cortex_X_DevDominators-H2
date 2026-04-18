"""
app.api.routes_diagnosis
~~~~~~~~~~~~~~~~~~~~~~~~~
REST API endpoints for the Omni_CortexX diagnostic system.

Endpoints:
• POST /api/v1/upload              — upload PDF/image for OCR extraction
• POST /api/v1/diagnose            — run full diagnostic workflow (JSON body)
• POST /api/v1/diagnose-with-files — upload files + run diagnosis in one shot
• GET  /api/v1/health              — health check
• GET  /api/v1/ready               — readiness probe

No business logic here — everything delegates to services.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.params import Body

from app.core.config import get_settings
from app.core.exceptions import (
    FileUploadError,
    OmniCortexError,
    WorkflowError,
)
from app.core.logging import generate_request_id, get_logger, request_id_ctx
from app.graph.state import OmniState, WorkflowPhase, dict_to_state, state_to_dict
from app.graph.workflow import compile_workflow
from app.schemas.requests import DiagnosisRequest, FileUploadMetadata
from app.schemas.responses import (
    DiagnosisResponse,
    ErrorResponse,
    HealthResponse,
    OCRExtractionResponse,
    ReadinessResponse,
)
from app.services.ocr_service import extract_from_file, merge_ocr_into_patient_data
from app.services.report_service import build_diagnosis_response, build_halted_response
from app.services.structuring_service import structure_patient_data
from app.db.mongodb import get_db
from app.services.memory_service import save_session, save_diagnosis
import asyncio

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["diagnosis"])


# ── Health & Readiness ───────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness probe — always returns 200 if the process is alive."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version="1.0.0",
        environment=settings.app_env,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check() -> ReadinessResponse:
    """
    Readiness probe — verifies critical dependencies.

    Checks:
    • API keys are configured
    • Workflow graph can compile
    """
    settings = get_settings()
    checks: dict[str, bool] = {}

    checks["gemini_key"] = bool(settings.gemini_api_key)
    checks["featherless_keys"] = len(settings.featherless_api_keys) > 0

    try:
        compile_workflow()
        checks["workflow_compile"] = True
    except Exception:
        checks["workflow_compile"] = False

    all_ready = all(checks.values())

    return ReadinessResponse(ready=all_ready, checks=checks)

# ── Recent Sessions ─────────────────────────────────────────────────

@router.get("/sessions/recent")
async def get_recent_sessions(limit: int = 10):
    """Retrieve recent sessions from the database."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not ready")
        
    try:
        cursor = db["sessions"].find({}, {"messages": 0}).sort("created_at", -1).limit(limit)
        sessions = await cursor.to_list(length=limit)
        
        # We optionally format this for the UI display
        formatted = []
        for s in sessions:
            # check if there's a diagnosis
            diag = await db["diagnoses"].find_one({"session_id": s["session_id"]})
            formatted.append({
                "id": s["session_id"],
                "diagnosis": diag["verdict"] if diag else "Pending...",
                "confidence": 0, # not fully extracted at root, fallback to 0
                "status": "complete" if diag else "in_progress",
                "time": s.get("created_at", "Unknown")
            })
        return {"sessions": formatted}
    except Exception as e:
        logger.error(f"Failed to fetch recent sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch recent sessions")

@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Retrieve a complete session including its chat history."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not ready")
        
    try:
        session = await db["sessions"].find_one({"session_id": session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        session["_id"] = str(session["_id"])
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch session")


# ── File Upload (OCR) ───────────────────────────────────────────────


@router.post("/upload", response_model=OCRExtractionResponse)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = "auto",
    patient_context: str = "{}",
) -> OCRExtractionResponse:
    """
    Upload a PDF or image for Gemini OCR extraction.

    Returns structured extraction results and merged patient data.
    """
    rid = generate_request_id()
    request_id_ctx.set(rid)
    session_id = uuid.uuid4().hex[:16]

    logger.info(
        "upload_received",
        filename=file.filename,
        content_type=file.content_type,
        doc_type=document_type,
    )

    try:
        content = await file.read()

        if len(content) == 0:
            raise FileUploadError("Empty file uploaded")

        if len(content) > 20 * 1024 * 1024:  # 20MB limit
            raise FileUploadError(
                "File too large",
                details={"size_mb": len(content) / (1024 * 1024)},
            )

        extractions = await extract_from_file(
            file_bytes=content,
            filename=file.filename or "unknown",
            document_type=document_type,
        )

        # Parse patient context
        try:
            ctx = json.loads(patient_context) if patient_context else {}
        except json.JSONDecodeError:
            ctx = {}

        merged = merge_ocr_into_patient_data(ctx, extractions)

        return OCRExtractionResponse(
            session_id=session_id,
            document_type=document_type,
            extractions=extractions,
            patient_data_merged=merged,
        )

    except FileUploadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OmniCortexError as e:
        logger.error("upload_failed", error=str(e), details=e.details)
        raise HTTPException(status_code=500, detail=str(e))


# ── Diagnosis Endpoint ───────────────────────────────────────────────


@router.post(
    "/diagnose",
    response_model=DiagnosisResponse,
    responses={
        200: {"model": DiagnosisResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def run_diagnosis(
    request: DiagnosisRequest = Body(...),
) -> DiagnosisResponse:
    """
    Run the full multi-agent diagnostic debate.

    Executes the LangGraph workflow:
    triage → advocate rounds → skeptic → inquisitor → cortex → scribe

    Returns the complete diagnosis result or a halted state
    if critical data is missing.
    """
    rid = generate_request_id()
    request_id_ctx.set(rid)
    session_id = uuid.uuid4().hex[:16]

    logger.info(
        "diagnosis_start",
        session_id=session_id,
        max_rounds=request.max_rounds,
    )

    try:
        # Build initial state
        patient_dict = request.patient_data.model_dump()

        # Structure the patient data via Gemini
        structured_patient_data = await structure_patient_data(patient_dict)

        initial_state = state_to_dict(
            OmniState(
                session_id=session_id,
                request_id=rid,
                phase=WorkflowPhase.INTAKE,
                patient_data=structured_patient_data,
                max_rounds=request.max_rounds,
            )
        )

        # Compile and run workflow
        workflow = compile_workflow()
        final_state_dict = await workflow.ainvoke(initial_state)

        # Parse final state
        final_state = dict_to_state(final_state_dict)

        # Build response
        response = build_diagnosis_response(final_state, session_id, rid)

        logger.info(
            "diagnosis_complete",
            session_id=session_id,
            status=response.status,
            rounds=response.debate_rounds,
        )

        asyncio.create_task(save_session(
            session_id, 
            structured_patient_data, 
            [e.model_dump() if hasattr(e, "model_dump") else e for e in final_state.debate_transcript]
        ))
        asyncio.create_task(save_diagnosis(
            session_id, 
            structured_patient_data, 
            response.primary_diagnosis if response.status != "halted" else f"Halted: {response.halt_reason}"
        ))

        return response

    except WorkflowError as e:
        logger.error("workflow_error", error=str(e), details=e.details)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
    except OmniCortexError as e:
        logger.error("diagnosis_error", error=str(e), details=e.details)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("unexpected_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post(
    "/extract-files",
    responses={
        200: {"description": "Returns structured patient data extracted from files and text"},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def extract_files(
    files: list[UploadFile] = File(
        [], # Optional
        description="Upload PDFs and/or images",
    ),
    patient_text: str = Form(
        "",
        description="Paste all patient info here",
    ),
    file_labels: str = Form(
        "",
        description="Comma-separated label for each file",
    ),
):
    """Extracts and structures patient data from files and text without running the debate."""
    rid = generate_request_id()
    request_id_ctx.set(rid)
    session_id = uuid.uuid4().hex[:16]

    logger.info(
        "extract_files_start",
        session_id=session_id,
        file_count=len(files) if files else 0,
        has_text=bool(patient_text),
    )

    try:
        labels = [l.strip() for l in file_labels.split(",") if l.strip()] if file_labels else []
        base_patient_data: dict[str, Any] = {}
        if patient_text.strip():
            base_patient_data["patient_description"] = patient_text.strip()

        all_extractions: list[dict[str, Any]] = []

        if files:
            for i, file in enumerate(files):
                content = await file.read()
                if len(content) == 0:
                    continue
                if len(content) > 20 * 1024 * 1024:
                    raise FileUploadError(f"File '{file.filename}' exceeds 20MB limit")
                
                label = labels[i] if i < len(labels) else ""
                doc_type = _label_to_doc_type(label) if label else _guess_doc_type(file.filename or "")

                extractions = await extract_from_file(
                    file_bytes=content,
                    filename=file.filename or "unknown",
                    document_type=doc_type,
                )
                for ext in extractions:
                    ext["_source_file"] = file.filename
                    ext["_source_label"] = label or file.filename
                all_extractions.extend(extractions)

        merged_patient_data = merge_ocr_into_patient_data(
            base_patient_data, all_extractions
        )

        if files:
            merged_patient_data["uploaded_documents"] = [
                {
                    "filename": files[i].filename,
                    "label": labels[i] if i < len(labels) else files[i].filename,
                }
                for i in range(len(files))
            ]

        # Skip Gemini here - WebSockets will handle it step-by-step
        return {
            "patient_data": merged_patient_data, 
            "ocr_extractions": all_extractions,
            "session_id": session_id
        }

    except FileUploadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("extract_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ── Diagnose with Files (combined upload + diagnosis) ────────────────


@router.post(
    "/diagnose-with-files",
    response_model=DiagnosisResponse,
    responses={
        200: {"model": DiagnosisResponse},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def diagnose_with_files(
    files: list[UploadFile] = File(
        ...,
        description="Upload PDFs and/or images (add multiple 'files' rows in Postman)",
    ),
    patient_text: str = Form(
        "",
        description="Paste all patient info here — symptoms, history, vitals, complaints, anything you know",
    ),
    file_labels: str = Form(
        "",
        description="Comma-separated label for each file in order, e.g. 'CBC Blood Report,Chest X-Ray,ECG Report'",
    ),
    max_rounds: int = Form(3, description="Maximum debate rounds"),
) -> DiagnosisResponse:
    """
    Upload files + paste patient text → get full AI diagnosis.

    **Postman setup (Body → form-data):**

    | Key           | Type | Value                                              |
    |---------------|------|----------------------------------------------------|
    | patient_text  | Text | 58 yr male, chest pain radiating to left arm...    |
    | files         | File | (select lab_report.pdf)                            |
    | files         | File | (select xray.png)                                  |
    | file_labels   | Text | CBC Blood Report,Chest X-Ray                       |
    | max_rounds    | Text | 3                                                  |

    For multiple files: add multiple rows with key **files** and type **File**.
    """
    rid = generate_request_id()
    request_id_ctx.set(rid)
    session_id = uuid.uuid4().hex[:16]

    logger.info(
        "diagnose_with_files_start",
        session_id=session_id,
        file_count=len(files),
        has_text=bool(patient_text),
        max_rounds=max_rounds,
    )

    try:
        # ── 1. Parse file labels ────────────────────────────────
        labels = [
            l.strip() for l in file_labels.split(",") if l.strip()
        ] if file_labels else []

        # ── 2. Build base patient data from plain text ──────────
        base_patient_data: dict[str, Any] = {}
        if patient_text.strip():
            base_patient_data["patient_description"] = patient_text.strip()

        # ── 3. OCR each file ────────────────────────────────────
        all_extractions: list[dict[str, Any]] = []

        for i, file in enumerate(files):
            content = await file.read()

            if len(content) == 0:
                logger.warning("empty_file_skipped", filename=file.filename)
                continue

            if len(content) > 20 * 1024 * 1024:
                raise FileUploadError(
                    f"File '{file.filename}' exceeds 20MB limit",
                    details={"filename": file.filename},
                )

            # Use label if provided, else guess from filename
            label = labels[i] if i < len(labels) else ""
            doc_type = _label_to_doc_type(label) if label else _guess_doc_type(file.filename or "")

            logger.info(
                "ocr_file",
                filename=file.filename,
                label=label or "(auto)",
                doc_type=doc_type,
                size_kb=len(content) // 1024,
            )

            extractions = await extract_from_file(
                file_bytes=content,
                filename=file.filename or "unknown",
                document_type=doc_type,
            )

            # Tag each extraction with its label
            for ext in extractions:
                ext["_source_file"] = file.filename
                ext["_source_label"] = label or file.filename

            all_extractions.extend(extractions)

        # ── 4. Merge everything ─────────────────────────────────
        merged_patient_data = merge_ocr_into_patient_data(
            base_patient_data, all_extractions
        )

        # Add file metadata summary
        merged_patient_data["uploaded_documents"] = [
            {
                "filename": files[i].filename,
                "label": labels[i] if i < len(labels) else files[i].filename,
            }
            for i in range(len(files))
        ]

        logger.info(
            "ocr_merge_complete",
            session_id=session_id,
            files_processed=len(files),
            extractions=len(all_extractions),
        )

        # ── 5. Gemini structuring — clean JSON with inferences ──
        structured_patient_data = await structure_patient_data(
            merged_patient_data,
            ocr_extractions=all_extractions,
        )

        logger.info(
            "patient_data_structured",
            session_id=session_id,
            has_demographics="demographics" in structured_patient_data,
            test_count=len(structured_patient_data.get("test_results", {})),
        )

        # ── 6. Run diagnostic workflow ──────────────────────────
        initial_state = state_to_dict(
            OmniState(
                session_id=session_id,
                request_id=rid,
                phase=WorkflowPhase.INTAKE,
                patient_data=structured_patient_data,
                ocr_extractions=all_extractions,
                max_rounds=max_rounds,
            )
        )

        workflow = compile_workflow()
        final_state_dict = await workflow.ainvoke(initial_state)
        final_state = dict_to_state(final_state_dict)

        response = build_diagnosis_response(final_state, session_id, rid)

        logger.info(
            "diagnose_with_files_complete",
            session_id=session_id,
            status=response.status,
            rounds=response.debate_rounds,
        )

        asyncio.create_task(save_session(
            session_id, 
            structured_patient_data, 
            [e.model_dump() if hasattr(e, "model_dump") else e for e in final_state.debate_transcript]
        ))
        asyncio.create_task(save_diagnosis(
            session_id, 
            structured_patient_data, 
            response.primary_diagnosis if response.status != "halted" else f"Halted: {response.halt_reason}"
        ))

        return response

    except FileUploadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except WorkflowError as e:
        logger.error("workflow_error", error=str(e), details=e.details)
        raise HTTPException(status_code=500, detail=str(e))
    except OmniCortexError as e:
        logger.error("diagnosis_error", error=str(e), details=e.details)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("unexpected_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ── Helpers ──────────────────────────────────────────────────────────


def _guess_doc_type(filename: str) -> str:
    """Guess document type from filename."""
    name = filename.lower()
    if any(kw in name for kw in ("lab", "blood", "cbc", "cmp", "lipid", "thyroid")):
        return "lab_report"
    if any(kw in name for kw in ("rx", "prescription", "med")):
        return "prescription"
    if any(kw in name for kw in ("xray", "x-ray", "ct", "mri", "scan", "echo", "ecg", "ekg")):
        return "imaging"
    if any(kw in name for kw in ("note", "clinical", "discharge", "summary")):
        return "clinical_notes"
    return "auto"


def _label_to_doc_type(label: str) -> str:
    """Convert a user-provided file label to a document type."""
    lbl = label.lower()
    if any(kw in lbl for kw in ("lab", "blood", "cbc", "cmp", "lipid", "thyroid", "test", "report")):
        return "lab_report"
    if any(kw in lbl for kw in ("rx", "prescription", "medicine", "medication")):
        return "prescription"
    if any(kw in lbl for kw in ("xray", "x-ray", "ct", "mri", "scan", "echo", "ecg", "ekg", "ultrasound", "imaging")):
        return "imaging"
    if any(kw in lbl for kw in ("note", "clinical", "discharge", "summary", "history")):
        return "clinical_notes"
    return "auto"
