"""Vector search via LangChain Qdrant vectorstore."""

import logging
from typing import Any

from app.config import TOP_K
from app.models import SearchResult

logger = logging.getLogger(__name__)


def search_vectorstore(
    vectorstore: Any,
    query: str,
    k: int = TOP_K,
) -> list[SearchResult]:
    """
    Perform semantic search using the LangChain vectorstore (embeds query and searches).
    Returns list of SearchResult with document (source), score, and content.
    """
    hits = vectorstore.similarity_search_with_score(query, k=k)
    results = []
    for doc, score in hits:
        results.append(
            SearchResult(
                document=doc.metadata.get("source", "unknown"),
                score=round(float(score), 2),
                content=doc.page_content,
            )
        )
    return results
