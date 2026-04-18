import logging
import httpx
from datetime import datetime
from typing import Any, List, Dict

from app.core.config import get_settings
from app.db.mongodb import get_db

logger = logging.getLogger(__name__)

GEMINI_EMBED_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"

def _clean_patient_data_for_embedding(data: dict) -> str:
    """Strips arbitrary keys and formats the dictionary into a clear descriptive text string."""
    clean_parts = []
    # Explicit keys to exclude entirely from embedding context
    exclude_keys = {"_raw_input", "uploaded_documents", "session_id"}
    
    for key, value in data.items():
        if key in exclude_keys:
            continue
        if not value:
            continue
        
        # Flatten simple lists or dicts
        val_str = ""
        if isinstance(value, list):
            val_str = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            val_str = ", ".join(f"{k}: {v}" for k, v in value.items())
        else:
            val_str = str(value)
            
        clean_parts.append(f"{key}: {val_str}")
        
    return "\n".join(clean_parts) if clean_parts else "No patient data provided."

async def get_gemini_embedding(text: str) -> List[float]:
    """Uses httpx to call the Gemini API for vector embeddings."""
    settings = get_settings()
    if not settings.gemini_api_key:
        logger.warning("No gemini_api_key configured, cannot generate embeddings.")
        return []

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.gemini_api_key
    }
    payload = {
        "content": {
            "parts": [
                {
                    "text": text
                }
            ]
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(GEMINI_EMBED_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json()
            embedding_vals = data.get("embedding", {}).get("values", [])
            return embedding_vals
    except Exception as e:
        logger.error(f"Failed to generate Gemini embedding: {e}")
        return []

async def save_session(session_id: str, patient_data: dict, messages: List[dict]):
    """Inserts the complete record into the sessions collection."""
    db = get_db()
    if db is None:
        logger.error("Database connection not ready. Cannot save session.")
        return

    document = {
        "session_id": session_id,
        "patient_data": patient_data,
        "messages": messages,
        "created_at": datetime.utcnow().isoformat()
    }
    
    try:
        await db["sessions"].insert_one(document)
        logger.info(f"Successfully saved session {session_id} to MongoDB.")
    except Exception as e:
        logger.error(f"Failed to save session to MongoDB: {e}")

async def save_diagnosis(session_id: str, patient_data: dict, verdict: str):
    """Generates the embedding and saves the record into the diagnoses collection."""
    db = get_db()
    if db is None:
        logger.error("Database connection not ready. Cannot save diagnosis.")
        return

    clean_text = _clean_patient_data_for_embedding(patient_data)
    embedding = await get_gemini_embedding(clean_text)

    document = {
        "session_id": session_id,
        "verdict": verdict,
        "embedding": embedding,
        "created_at": datetime.utcnow().isoformat()
    }
    
    try:
        await db["diagnoses"].insert_one(document)
        logger.info(f"Successfully saved diagnosis {session_id} with embeddings to MongoDB.")
    except Exception as e:
        logger.error(f"Failed to save diagnosis to MongoDB: {e}")
