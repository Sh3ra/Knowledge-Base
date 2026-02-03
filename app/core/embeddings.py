"""LangChain Jina embeddings (used by the Qdrant vectorstore for ingest and search)."""

from langchain_community.embeddings import JinaEmbeddings

from app.config import JINA_API_KEY, JINA_EMBEDDING_MODEL


def get_jina_embeddings() -> JinaEmbeddings:
    """Return a LangChain JinaEmbeddings instance for the vectorstore."""
    if not JINA_API_KEY:
        raise ValueError(
            "JINA_API_KEY is not set. Add it to your .env file or environment."
        )
    return JinaEmbeddings(
        jina_api_key=JINA_API_KEY,
        model_name=JINA_EMBEDDING_MODEL,
    )
