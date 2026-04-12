from typing import Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.services.atlas_service import store_case, search_similar_cases

router = APIRouter(prefix="/atlas", tags=["MongoDB Atlas Search"])

class StoreCaseRequest(BaseModel):
    session_id: str = Field(..., description="Unique diagnostic session ID")
    request_id: str = Field(..., description="Unique system request ID")
    final_diagnosis: str = Field(..., description="The definitive outcome")
    confidence: float = Field(..., description="Calculated final confidence")
    audit_trail: dict[str, Any] = Field(..., description="The complete JSON schema of the workflow")

class SearchCasesRequest(BaseModel):
    query: str = Field(..., description="Natural language search query")
    limit: int = Field(5, ge=1, le=50, description="Max results to return")

@router.post("/store-case")
async def api_store_case(req: StoreCaseRequest):
    """
    Store a finalised diagnostic case and its transcript into MongoDB.
    This also automatically computes dense vector embeddings to enable similarity search.
    """
    try:
        inserted_id = await store_case(
            session_id=req.session_id,
            request_id=req.request_id,
            final_diagnosis=req.final_diagnosis,
            confidence=req.confidence,
            audit_trail=req.audit_trail
        )
        return {"status": "success", "id": inserted_id}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store case: {e}")


@router.post("/search-similar")
async def api_search_similar(req: SearchCasesRequest):
    """
    Query historical clinical cases using natural language processing
    powered by MongoDB Atlas Vector Search ($vectorSearch).
    """
    try:
        results = await search_similar_cases(req.query, req.limit)
        return {"status": "success", "data": results}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute search: {e}")
