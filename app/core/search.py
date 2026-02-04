"""Vector search via LangChain Qdrant vectorstore and SimilarityScoreThresholdRetriever."""

import logging
from typing import Any

from app.config import MIN_SIMILARITY_SCORE, TOP_K
from app.models import SearchResult

logger = logging.getLogger(__name__)


def search_vectorstore(
    vectorstore: Any,
    query: str,
    k: int = TOP_K,
) -> list[SearchResult]:
    """
    Perform semantic search using the LangChain SimilarityScoreThresholdRetriever.
    Returns list of SearchResult with document (source) and content.
    """
    retriever = vectorstore.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={
            "k": k,
            "score_threshold": MIN_SIMILARITY_SCORE,
        },
    )
    docs = retriever.invoke(query)
    return [
        SearchResult(
            document=doc.metadata.get("source", "unknown"),
            content=doc.page_content,
        )
        for doc in docs
    ]
