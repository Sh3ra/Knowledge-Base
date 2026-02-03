"""FastAPI application for PDF ingestion and semantic search."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import ingest, search
from app.config import JINA_API_KEY
from app.infrastructure.vectorstore import (
    create_vectorstore,
    ensure_collection,
    get_qdrant_client,
)
from app.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate config, init Qdrant client + LangChain vectorstore and collection."""
    if not JINA_API_KEY:
        raise RuntimeError(
            "JINA_API_KEY is not set. Add it to your .env file or environment."
        )

    logger.info("Using Jina AI embedding API (LangChain)")

    client = get_qdrant_client()
    app.state.qdrant = client
    app.state.job_status = {}
    app.state.executor = ThreadPoolExecutor(max_workers=4)
    app.state.ingest_semaphore = asyncio.Semaphore(4)

    ensure_collection(client)
    app.state.vectorstore = create_vectorstore(client)

    yield
    app.state.executor.shutdown(wait=False)


app = FastAPI(
    title="PDF Ingestor & Semantic Search API",
    version="1.0.0",
    description="Ingests PDF documents, generates embeddings, and enables semantic search.",
    lifespan=lifespan,
)

app.include_router(ingest.router)
app.include_router(search.router)
