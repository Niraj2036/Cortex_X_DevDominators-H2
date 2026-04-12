"""
app.services.structuring_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Gemini-powered patient data structuring service.

Takes raw merged patient data (from OCR + user text) and sends it
to Gemini to produce a clean, structured JSON with demographics,
medical history, and interpreted test results.

This structured output is what gets fed to the triage swarm,
replacing the raw messy dict.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.llm_client import gemini_text_json
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Structuring prompt ───────────────────────────────────────────────

_STRUCTURING_PROMPT = """\
You are a clinical data structuring engine. You receive raw, unstructured or \
semi-structured patient data extracted from medical reports, images, and clinician notes.

Your job is to produce a SINGLE, CLEAN, COMPREHENSIVE JSON object that organises \
ALL the clinical information into a flat structure.

Use exactly the schema shape provided below:

{
  "normal details": "<demographics, chief complaint, medical history, current medications, allergies, symptoms, vital signs - combine it all here in detail in text format>",
  "<test 1 name string>": "<measured value, flag, and brief inference>",
  "<test 2 name string>": "<measured value, flag, and brief inference>",
  "<imaging finding 1>": "<finding and inference>",
  "data_quality_notes": "<any concerns about data completeness or reliability>"
}

RULES:
1. Extract EVERY piece of clinical information from the input.
2. The "normal details" field should contain the qualitative text. ALL tests/results must dynamically become their own keys in the JSON matching the test name exactly!
3. For each test result, provide a clinical INFERENCE in its string value — what does the value mean?
   Example key-value: "Troponin": "2.45 ng/mL (High) -> Markedly elevated (>10x upper limit), strongly suggestive of myocardial injury"
4. If data is missing entirely, output an empty JSON object. Do not fabricate fields.
5. Return ONLY valid JSON — no markdown fences, no commentary.
"""


async def structure_patient_data(
    raw_patient_data: dict[str, Any],
    ocr_extractions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Send raw patient data to Gemini for clean structuring.

    Takes the messy merged dict from OCR + user text and returns
    a clean, inference-rich JSON suitable for the triage swarm.

    Parameters
    ----------
    raw_patient_data : dict
        The raw merged patient data dict.
    ocr_extractions : list[dict] | None
        Raw OCR extraction results (if any) for additional context.

    Returns
    -------
    dict[str, Any]
        Structured patient data with demographics, test inferences, etc.
    """
    # Build the input text for Gemini
    input_parts = []

    # Include raw patient data
    input_parts.append("=== PATIENT DATA ===")
    input_parts.append(json.dumps(raw_patient_data, indent=2, default=str))

    # Include raw OCR extractions for additional context
    if ocr_extractions:
        input_parts.append("\n=== RAW OCR EXTRACTIONS ===")
        for i, extraction in enumerate(ocr_extractions):
            input_parts.append(f"\n--- Document {i + 1} ---")
            input_parts.append(json.dumps(extraction, indent=2, default=str))

    combined_text = "\n".join(input_parts)

    logger.info(
        "structuring_start",
        input_chars=len(combined_text),
        has_ocr=bool(ocr_extractions),
        ocr_count=len(ocr_extractions) if ocr_extractions else 0,
    )

    try:
        structured = await gemini_text_json(
            system_prompt=_STRUCTURING_PROMPT,
            user_text=combined_text,
        )
    except Exception as exc:
        logger.error("structuring_failed", error=str(exc))
        # Fallback to raw data — don't crash the pipeline
        return raw_patient_data

    # Validate it has the expected structure
    if isinstance(structured, dict) and "normal details" in structured:
        logger.info(
            "structuring_complete",
            has_normal_details=True,
            total_extracted_keys=len(structured.keys()),
        )
        # Preserve the original raw data as a reference
        structured["_raw_input"] = raw_patient_data
        return structured

    # If Gemini returned something unexpected, still use it
    logger.warning(
        "structuring_unexpected_format",
        keys=list(structured.keys()) if isinstance(structured, dict) else "not_dict",
    )

    if isinstance(structured, dict):
        structured["_raw_input"] = raw_patient_data
        return structured

    print("structured", structured)

    return raw_patient_data
