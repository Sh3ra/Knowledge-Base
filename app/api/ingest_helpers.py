"""Helpers for ingest route: parse form, resolve files from directory or uploads, validate limits."""

from fastapi import HTTPException

from app.config import MAX_FILES_PER_UPLOAD, MAX_UPLOAD_SIZE
from app.core.ingest import get_pdf_files_from_directory


def parse_input_fields(form) -> list:
    """Extract all 'input' values from multipart form. Raises 400 if none."""
    fields = [v for name, v in form.multi_items() if name == "input"]
    if not fields:
        raise HTTPException(status_code=400, detail="Missing 'input' field")
    return fields


def files_from_directory(path: str) -> tuple[list[tuple[str, bytes]], list[str]] | None:
    """
    Case 1: resolve PDFs from directory path. Returns (files, filenames) or None if no PDFs.
    Raises HTTPException on invalid path.
    """
    path = path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="Directory path cannot be empty")
    try:
        pdf_files = get_pdf_files_from_directory(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not pdf_files:
        return None
    files = [(name, content) for name, content in pdf_files]
    names = [f[0] for f in files]
    return files, names


async def files_from_uploads(fields: list) -> tuple[list[tuple[str, bytes]], list[str]]:
    """
    Case 2: resolve PDFs from multipart file uploads. Returns (files, filenames).
    Raises HTTPException on invalid or oversized file.
    """
    files_to_process: list[tuple[str, bytes]] = []
    for file in fields:
        if not (hasattr(file, "read") and hasattr(file, "filename")):
            continue
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB.",
            )
        files_to_process.append((file.filename, content))
    if not files_to_process:
        raise HTTPException(status_code=400, detail="No valid PDF files provided.")
    return files_to_process, [f[0] for f in files_to_process]


def check_max_files(files: list) -> None:
    """Raises 400 if more than MAX_FILES_PER_UPLOAD."""
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum is {MAX_FILES_PER_UPLOAD} per request (got {len(files)}).",
        )
