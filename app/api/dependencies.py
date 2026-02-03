"""FastAPI dependencies for request-scoped and app state access."""

from fastapi import Request


def get_vectorstore(request: Request):
    """Return the LangChain Qdrant vectorstore from app state."""
    return request.app.state.vectorstore


def get_job_status_store(request: Request) -> dict:
    """Return the shared job status store (job_id -> status info)."""
    return request.app.state.job_status
