"""
app.services.ocr_service
~~~~~~~~~~~~~~~~~~~~~~~~~~
OCR extraction service using Gemini REST API.

Handles:
• PDF parsing
• Medical image OCR
• Prescription extraction
• Lab report extraction
• Scan text normalisation

All calls go through ``llm_client.gemini_ocr`` — NO LangChain wrappers.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

try:
    import magic
except ImportError:
    magic = None

from app.core.exceptions import FileUploadError, OCRParsingError
from app.core.llm_client import gemini_ocr, gemini_ocr_image
from app.core.logging import get_logger

logger = get_logger(__name__)

# Supported MIME types
_SUPPORTED_MIMES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/tiff",
}

# Document-type-specific prompts
_DOC_PROMPTS: dict[str, str] = {
    "lab_report": (
        "Extract all lab test results from this clinical laboratory report. "
        "For each test, provide: test_name, value, unit, reference_range, flag (normal/high/low). "
        "Return as JSON array."
    ),
    "prescription": (
        "Extract all medication prescriptions from this document. "
        "For each: drug_name, dosage, frequency, route, duration, prescriber. "
        "Return as JSON array."
    ),
    "imaging": (
        "Extract all findings from this medical imaging report or scan. "
        "Include: modality, body_region, findings, impression, measurements. "
        "Return as JSON object."
    ),
    "clinical_notes": (
        "Extract structured clinical information from these notes. "
        "Include: chief_complaint, history_of_present_illness, review_of_systems, "
        "physical_exam, assessment, plan. Return as JSON object."
    ),
    "auto": (
        "Analyse this medical document. Extract ALL clinical information including: "
        "patient demographics, symptoms, lab values, imaging findings, diagnoses, "
        "medications, vital signs, and any other relevant medical data. "
        "Return structured JSON."
    ),
}


def _detect_mime(filename: str, content: bytes) -> str:
    """Detect MIME type broadly, falling back to python-magic if mimetypes fails."""
    # 1. Broadly try python-magic if it exists
    if magic:
        try:
            mime = magic.from_buffer(content, mime=True)
            if mime and mime in _SUPPORTED_MIMES:
                return mime
        except Exception:
            pass

    # 2. Try standard mimetypes
    mime, _ = mimetypes.guess_type(filename)
    if mime and mime in _SUPPORTED_MIMES:
        return mime

    # Simple magic-byte sniffing
    if content[:4] == b"%PDF":
        return "application/pdf"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:2] == b"\xff\xd8":
        return "image/jpeg"

    return "application/pdf"  # default assumption


async def extract_from_file(
    *,
    file_bytes: bytes,
    filename: str,
    document_type: str = "auto",
) -> list[dict[str, Any]]:
    """
    Run Gemini OCR on an uploaded file.

    Parameters
    ----------
    file_bytes : bytes
        Raw file content.
    filename : str
        Original filename (for MIME detection).
    document_type : str
        One of: auto, lab_report, prescription, imaging, clinical_notes.

    Returns
    -------
    list[dict[str, Any]]
        Structured extraction results.

    Raises
    ------
    FileUploadError
        If the file type is unsupported.
    OCRParsingError
        If Gemini output cannot be parsed.
    """
    mime = _detect_mime(filename, file_bytes)

    if mime not in _SUPPORTED_MIMES:
        raise FileUploadError(
            f"Unsupported file type: {mime}",
            details={"filename": filename, "detected_mime": mime},
        )

    prompt = _DOC_PROMPTS.get(document_type, _DOC_PROMPTS["auto"])

    logger.info(
        "ocr_extraction_start",
        filename=filename,
        mime=mime,
        doc_type=document_type,
        size_kb=len(file_bytes) // 1024,
    )

    if mime.startswith("image/"):
        results = await gemini_ocr_image(
            image_bytes=file_bytes,
            mime_type=mime,
            prompt=prompt,
        )
    else:
        results = await gemini_ocr(
            file_bytes=file_bytes,
            mime_type=mime,
            prompt=prompt,
        )

    if not results:
        logger.warning(
            "gemini_returned_empty_extraction",
            filename=filename,
            reason="Gemini found no extractable clinical content."
        )
        return [{"content": "No extractable clinical data found by Gemini.", "status": "empty_extraction"}]

    logger.info(
        "ocr_extraction_complete",
        filename=filename,
        result_count=len(results),
    )

    return results


def merge_ocr_into_patient_data(
    existing: dict[str, Any],
    extractions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Merge OCR extractions into existing patient data dict.

    Non-destructive: existing values are preserved; new data is appended.
    """
    merged = dict(existing)

    for extraction in extractions:
        # Merge lab results
        if "lab_results" in extraction:
            merged.setdefault("lab_results", {})
            if isinstance(extraction["lab_results"], dict):
                merged["lab_results"].update(extraction["lab_results"])
            elif isinstance(extraction["lab_results"], list):
                for item in extraction["lab_results"]:
                    if isinstance(item, dict) and "test_name" in item:
                        merged["lab_results"][item["test_name"]] = item

        # Merge medications
        if "medications" in extraction:
            merged.setdefault("medications", [])
            meds = extraction["medications"]
            if isinstance(meds, list):
                merged["medications"].extend(meds)

        # Merge imaging
        if "imaging" in extraction or "findings" in extraction:
            merged.setdefault("imaging", [])
            img_data = extraction.get("imaging") or extraction.get("findings")
            if isinstance(img_data, list):
                merged["imaging"].extend(img_data)
            elif isinstance(img_data, dict):
                merged["imaging"].append(img_data)

        # Merge symptoms
        if "symptoms" in extraction:
            merged.setdefault("symptoms", [])
            if isinstance(extraction["symptoms"], list):
                merged["symptoms"].extend(extraction["symptoms"])

        # Merge demographics
        if "demographics" in extraction:
            merged.setdefault("demographics", {})
            if isinstance(extraction["demographics"], dict):
                merged["demographics"].update(extraction["demographics"])

        # Merge vital signs
        if "vital_signs" in extraction:
            merged.setdefault("vital_signs", {})
            if isinstance(extraction["vital_signs"], dict):
                merged["vital_signs"].update(extraction["vital_signs"])

        # Store raw content as fallback
        if "content" in extraction:
            merged.setdefault("raw_extractions", [])
            merged["raw_extractions"].append(extraction["content"])

    # Deduplicate lists
    for key in ("symptoms", "medications"):
        if key in merged and isinstance(merged[key], list):
            seen: set[str] = set()
            deduped: list[Any] = []
            for item in merged[key]:
                s = str(item)
                if s not in seen:
                    seen.add(s)
                    deduped.append(item)
            merged[key] = deduped

    return merged
