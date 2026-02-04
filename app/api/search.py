"""Search route: POST /search/."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_vectorstore
from app.core.search import search_vectorstore
from app.models import SearchRequest, SearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/", response_model=SearchResponse)
async def search(
    req: SearchRequest,
    vectorstore=Depends(get_vectorstore),
):
    """Perform semantic search over ingested content (LangChain vectorstore)."""
    query = (req.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        results = search_vectorstore(vectorstore, query)
    except Exception as e:
        logger.exception("Search failed")
        raise HTTPException(
            status_code=500, detail="Search processing failed."
        ) from e

    q_preview = query[:80] + "..." if len(query) > 80 else query
    logger.info("POST /search/ query=%r results=%d", q_preview, len(results))
    message = "No relevant documents found." if not results else None
    return SearchResponse(results=results, message=message)
