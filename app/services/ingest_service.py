"""Ingest service: background PDF processing and LangChain Qdrant vectorstore."""

import asyncio
import logging
from typing import Any

from app.core.ingest import process_pdf_to_documents
from app.models import JobStatus

logger = logging.getLogger(__name__)


def _process_and_store_pdf(
    content: bytes,
    filename: str,
    vectorstore: Any,
) -> list[str]:
    """Process a single PDF and add chunks to the LangChain Qdrant vectorstore (runs in thread pool)."""
    documents = process_pdf_to_documents(content, filename)
    if not documents:
        return [filename]
    vectorstore.add_documents(documents)
    return [filename]


async def process_and_store_pdf_async(
    content: bytes,
    filename: str,
    executor: Any,
    vectorstore: Any,
) -> list[str]:
    """Process PDF in thread pool and add to vectorstore."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor,
        _process_and_store_pdf,
        content,
        filename,
        vectorstore,
    )


async def run_background_ingest(
    job_id: str,
    files_to_process: list[tuple[str, bytes]],
    state: Any,
) -> None:
    """Background task: chunk, embed (via vectorstore), and store. Updates state.job_status."""
    job_status = state.job_status
    executor = state.executor
    vectorstore = state.vectorstore
    semaphore = state.ingest_semaphore

    ingested: list[str] = []
    job_status[job_id] = {"status": JobStatus.PROCESSING, "files": [], "error": None}
    try:
        async with semaphore:
            for filename, content in files_to_process:
                try:
                    await process_and_store_pdf_async(
                        content, filename, executor, vectorstore
                    )
                    ingested.append(filename)
                    logger.info("Ingest job_id=%s processed file=%s", job_id, filename)
                except Exception as e:
                    logger.exception("Background ingest failed for %s", filename)
                    job_status[job_id] = {
                        "status": JobStatus.FAILED,
                        "files": ingested,
                        "error": str(e),
                    }
                    return
        job_status[job_id] = {
            "status": JobStatus.COMPLETED,
            "files": ingested,
            "error": None,
        }
        logger.info("Ingest job_id=%s completed files=%s", job_id, ingested)
    except Exception as e:
        logger.exception("Background ingest failed for job %s", job_id)
        job_status[job_id] = {
            "status": JobStatus.FAILED,
            "files": ingested,
            "error": str(e),
        }
