import json
import logging
import random
from datetime import datetime
from typing import Any

from app.db.mongodb import get_db

logger = logging.getLogger(__name__)

async def get_embedding(text: str) -> list[float]:
    """
    Placeholder embedding function.
    In a real scenario, call an LLM (e.g., OpenAI or Gemini) to generate
    1536-dimensional embeddings. Here we return random floats to simulate.
    """
    # Use a fixed seed based on text length to provide consistent pseudo-embeddings
    # for testing purposes.
    random.seed(len(text) + sum(ord(c) for c in text[:10]))
    return [random.uniform(-1.0, 1.0) for _ in range(1536)]


async def store_case(
    session_id: str,
    request_id: str,
    final_diagnosis: str,
    confidence: float,
    audit_trail: dict[str, Any]
) -> str:
    """Store the full case result in MongoDB Atlas along with its vector embedding."""
    db = get_db()
    if db is None:
        logger.error("MongoDB Atlas connection not available. Cannot store case.")
        raise RuntimeError("Database connection not ready")

    # Construct the text to be embedded
    # Summarize key findings to capture the essence of the case
    text_to_embed = f"Diagnosis: {final_diagnosis}\n"
    
    # You might summarize the audit trail context here.
    # For now, we serialize the entire audit trail and embed it (or part of it).
    json_trail = json.dumps(audit_trail, default=str)
    text_to_embed += f"Audit Trail Summary: {json_trail[:1500]}" # cap length for embedding

    embedding_vector = await get_embedding(text_to_embed)

    document = {
        "session_id": session_id,
        "request_id": request_id,
        "created_at": datetime.utcnow().isoformat(),
        "final_diagnosis": final_diagnosis,
        "confidence": confidence,
        "audit_trail": audit_trail,
        "embedding": embedding_vector,
    }

    try:
        result = await db["cases"].insert_one(document)
        logger.info(f"Successfully stored case {session_id} in MongoDB (id: {result.inserted_id})")
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"Failed to store case in MongoDB Atlas: {e}")
        raise


async def search_similar_cases(query_text: str, limit: int = 5) -> list[dict[str, Any]]:
    """Query MongoDB Atlas using Vector Search for similar past cases."""
    db = get_db()
    if db is None:
        logger.error("MongoDB Atlas connection not available.")
        raise RuntimeError("Database connection not ready")

    query_embedding = await get_embedding(query_text)

    # Use MongoDB Atlas $vectorSearch aggregation
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": limit * 10,
                "limit": limit,
            }
        },
        {
            "$project": {
                "_id": 1,
                "session_id": 1,
                "final_diagnosis": 1,
                "confidence": 1,
                "created_at": 1,
                "score": {"$meta": "vectorSearchScore"},
                # Do not return the massive embedding vector directly to clients
            }
        }
    ]

    try:
        cursor = db["cases"].aggregate(pipeline)
        results = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string for JSON serialization
        for r in results:
            r["_id"] = str(r["_id"])
            
        logger.info(f"Found {len(results)} similar cases for query.")
        return results
    except Exception as e:
        logger.error(f"Failed to execute vector search in MongoDB Atlas: {e}")
        raise
