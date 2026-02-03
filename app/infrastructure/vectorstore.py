"""Qdrant client, collection creation, and LangChain Qdrant vectorstore."""

import logging
import time
from typing import Any

from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.config import (
    COLLECTION_NAME,
    EMBEDDING_DIMENSION,
    QDRANT_HOST,
    QDRANT_PORT,
)
from app.core.embeddings import get_jina_embeddings

logger = logging.getLogger(__name__)


def get_qdrant_client() -> QdrantClient:
    """Connect to Qdrant with retries. Raises after 10 failed attempts."""
    logger.info("Connecting to Qdrant at %s:%s", QDRANT_HOST, QDRANT_PORT)
    for attempt in range(10):
        try:
            client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
            return client
        except Exception as e:
            if attempt < 9:
                logger.warning("Qdrant not ready, retrying in 2s: %s", e)
                time.sleep(2)
            else:
                raise
    raise RuntimeError("Qdrant connection failed")  # unreachable if loop raises


def ensure_collection(client: QdrantClient) -> None:
    """Create the vector collection if it does not exist."""
    collections = client.get_collections().collections
    if not any(c.name == COLLECTION_NAME for c in collections):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE),
        )
        logger.info("Created collection: %s", COLLECTION_NAME)


def create_vectorstore(client: QdrantClient) -> Qdrant:
    """Build LangChain Qdrant vectorstore with Jina embeddings."""
    embeddings = get_jina_embeddings()
    vectorstore = Qdrant(
        client=client,
        collection_name=COLLECTION_NAME,
        embeddings=embeddings,
    )
    logger.info("LangChain Qdrant vectorstore ready")
    return vectorstore
