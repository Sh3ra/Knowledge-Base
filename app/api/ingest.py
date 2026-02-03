"""Ingest routes: POST /ingest/, GET /ingest/status/{job_id}."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.api.dependencies import get_job_status_store
from app.config import MAX_UPLOAD_SIZE
from app.core.ingest import get_pdf_files_from_directory
from app.models import IngestResponse, JobStatus, JobStatusResponse
from app.services.ingest_service import run_background_ingest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/", response_model=IngestResponse, status_code=202)
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
    input_fields = []
    for name, value in form.multi_items():
        if name == "input":
            input_fields.append(value)

    if not input_fields:
        raise HTTPException(status_code=400, detail="Missing 'input' field")

    files_to_process: list[tuple[str, bytes]] = []
    filenames: list[str] = []

    first = input_fields[0]
    if isinstance(first, str):
        path = first.strip()
        if not path:
            raise HTTPException(status_code=400, detail="Directory path cannot be empty")
        try:
            pdf_files = get_pdf_files_from_directory(path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not pdf_files:
            logger.info("POST /ingest/ directory path=%s: no PDFs found", path)
            return IngestResponse(
                job_id=None,
                message="No PDF files found in directory.",
                files=[],
            )
        for filename, content in pdf_files:
            files_to_process.append((filename, content))
            filenames.append(filename)
    else:
        for file in input_fields:
            if not (hasattr(file, "read") and hasattr(file, "filename")):
                continue
            if not file.filename or not file.filename.lower().endswith(".pdf"):
                raise HTTPException(
                    status_code=400, detail="Only PDF files are accepted."
                )
            content = await file.read()
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)} MB.",
                )
            files_to_process.append((file.filename, content))
            filenames.append(file.filename)
        if not files_to_process:
            raise HTTPException(
                status_code=400, detail="No valid PDF files provided."
            )

    job_id = str(uuid.uuid4())
    job_status[job_id] = {"status": JobStatus.PENDING, "files": [], "error": None}

    background_tasks.add_task(
        run_background_ingest,
        job_id,
        files_to_process,
        request.app.state,
    )

    count = len(filenames)
    logger.info("POST /ingest/ accepted job_id=%s files=%s count=%d", job_id, filenames, count)
    return IngestResponse(
        job_id=job_id,
        message=f"Ingestion started. {count} PDF document{'s' if count != 1 else ''} queued for processing.",
        files=filenames,
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
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
