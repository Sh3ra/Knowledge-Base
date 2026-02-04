"""Ingest routes: POST /ingest/, GET /ingest/status/{job_id}."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.api.dependencies import get_job_status_store
from app.api.ingest_helpers import (
    check_max_files,
    files_from_directory,
    files_from_uploads,
    parse_input_fields,
)
from app.models import IngestResponse, JobStatus, JobStatusResponse
from app.services.ingest_service import run_background_ingest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post(
    "/",
    response_model=IngestResponse,
    status_code=202,
    responses={
        202: {"description": "Accepted. Ingestion started; poll GET /ingest/status/{job_id}."},
        400: {"description": "Bad Request. Missing input, invalid path, non-PDF, too many files, or file too large."},
    },
)
async def ingest(
    request: Request,
    background_tasks: BackgroundTasks,
    job_status: dict = Depends(get_job_status_store),
):
    """
    Ingest PDFs into the system (async).
    Validates and accepts files immediately; chunking and embedding run in background.
    Returns 202 Accepted with job_id. Poll GET /ingest/status/{job_id} for completion.
    """
    form = await request.form()
    input_fields = parse_input_fields(form)
    first = input_fields[0]

    # Case 1: directory path (e.g. input=/data)
    if isinstance(first, str):
        result = files_from_directory(first)
        if result is None:
            logger.info("POST /ingest/ directory path=%s: no PDFs found", first.strip())
            return IngestResponse(job_id=None, message="No PDF files found in directory.", files=[])
        files_to_process, filenames = result
    # Case 2: file upload(s)
    else:
        files_to_process, filenames = await files_from_uploads(input_fields)

    check_max_files(files_to_process)

    job_id = str(uuid.uuid4())
    job_status[job_id] = {"status": JobStatus.PENDING, "files": [], "error": None}
    background_tasks.add_task(run_background_ingest, job_id, files_to_process, request.app.state)

    count = len(filenames)
    logger.info("POST /ingest/ accepted job_id=%s files=%s count=%d", job_id, filenames, count)
    return IngestResponse(
        job_id=job_id,
        message=f"Ingestion started. {count} PDF document{'s' if count != 1 else ''} queued for processing.",
        files=filenames,
    )


@router.get(
    "/status/{job_id}",
    response_model=JobStatusResponse,
    responses={
        200: {"description": "Job status (pending, processing, completed, failed)."},
        404: {"description": "Job not found."},
    },
)
async def ingest_status(
    job_id: str,
    job_status: dict = Depends(get_job_status_store),
):
    """Get status of an ingest job."""
    if job_id not in job_status:
        raise HTTPException(status_code=404, detail="Job not found")
    info = job_status[job_id]
    logger.info("GET /ingest/status/%s status=%s", job_id, info["status"])
    return JobStatusResponse(
        job_id=job_id,
        status=info["status"],
        files=info.get("files", []),
        error=info.get("error"),
    )
