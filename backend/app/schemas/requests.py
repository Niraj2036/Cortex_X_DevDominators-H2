"""
app.schemas.requests
~~~~~~~~~~~~~~~~~~~~~
Pydantic v2 request models for the diagnostic API.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PatientDataInput(BaseModel):
    """Direct patient data input (no file upload)."""

    demographics: dict[str, Any] = Field(
        default_factory=dict,
        description="Age, sex, weight, height, ethnicity etc.",
        examples=[{"age": 58, "sex": "male", "weight_kg": 82}],
    )
    symptoms: list[str] = Field(
        default_factory=list,
        description="List of presenting symptoms",
        examples=[["chest pain", "shortness of breath", "diaphoresis"]],
    )
    vital_signs: dict[str, Any] = Field(
        default_factory=dict,
        description="BP, HR, SpO2, temperature, RR",
        examples=[{"bp": "150/90", "hr": 110, "spo2": 94, "temp_c": 37.2}],
    )
    lab_results: dict[str, Any] = Field(
        default_factory=dict,
        description="Lab values keyed by test name",
        examples=[{"troponin_ng_ml": 0.45, "bnp_pg_ml": 890, "creatinine_mg_dl": 1.4}],
    )
    imaging: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Imaging study results",
        examples=[[{"type": "chest_xray", "findings": "bilateral infiltrates"}]],
    )
    medical_history: list[str] = Field(
        default_factory=list,
        description="Past medical history",
        examples=[["hypertension", "type 2 diabetes", "previous MI"]],
    )
    medications: list[str] = Field(
        default_factory=list,
        description="Current medications",
        examples=[["metformin 500mg", "lisinopril 10mg", "aspirin 81mg"]],
    )
    allergies: list[str] = Field(default_factory=list)
    chief_complaint: str = Field("", description="Primary reason for visit")
    additional_notes: str = Field("", description="Free-text clinician notes")


class DiagnosisRequest(BaseModel):
    """Top-level request body for the /diagnose endpoint."""

    patient_data: PatientDataInput
    max_rounds: int = Field(5, ge=1, le=20, description="Maximum debate rounds")
    consensus_threshold: float = Field(
        0.85, ge=0.0, le=1.0, description="Adjusted confidence needed"
    )


class FileUploadMetadata(BaseModel):
    """Metadata sent alongside a file upload."""

    document_type: str = Field(
        "auto",
        description="Type of document: auto, lab_report, prescription, imaging, clinical_notes",
    )
    patient_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional additional patient context",
    )
