"""Pydantic models for API request/response."""

from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    """Ingest job status values."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SearchRequest(BaseModel):
    """Search endpoint request body."""

    query: str = Field(..., description="Search query")


class SearchResult(BaseModel):
    """Single search result item."""

    document: str
    score: float
    content: str


class SearchResponse(BaseModel):
    """Search endpoint response."""

    results: list[SearchResult]


class IngestResponse(BaseModel):
    """Ingest endpoint response (202 Accepted when processing in background)."""

    job_id: str | None = None
    message: str
    files: list[str]


class JobStatusResponse(BaseModel):
    """Job status response."""

    job_id: str
    status: JobStatus
    files: list[str] = []
    error: str | None = None
