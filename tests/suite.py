"""
Simple functional test for the PDF Ingestor & Semantic Search API.

Validates that:
1. The service starts correctly and accepts PDF ingestion.
2. The search endpoint returns meaningful results.
3. Invalid files, empty queries, and concurrent uploads are handled properly.
"""

import pytest
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="session", autouse=True)
def wait_for_service():
    """Wait for service to be ready before tests start."""
    for _ in range(20):
        try:
            r = requests.get(f"{BASE_URL}/docs")
            if r.status_code == 200:
                return
        except Exception:
            time.sleep(1)
    pytest.fail("Service did not start within expected time.")


def _wait_for_ingest_job(job_id, timeout=60):
    """Poll ingest status until job completes or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{BASE_URL}/ingest/status/{job_id}")
        assert r.status_code == 200, f"Status check failed: {r.text}"
        data = r.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.5)
    pytest.fail(f"Job {job_id} did not complete within {timeout}s")


def test_ingest_single_pdf(tmp_path):
    """Test single PDF ingestion (async: 202 + status polling)."""
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("Artificial intelligence enables systems to learn from data.")

    with open(pdf_path, "rb") as f:
        response = requests.post(f"{BASE_URL}/ingest/", files={"input": f})

    assert response.status_code == 202, f"Ingest failed: {response.text}"
    body = response.json()
    assert "message" in body
    assert "files" in body
    assert "job_id" in body
    assert pdf_path.name in body["files"]

    # Wait for background processing to complete
    status = _wait_for_ingest_job(body["job_id"])
    assert status["status"] == "completed", f"Job failed: {status.get('error')}"


def test_search_query():
    """Test semantic search query."""
    query = {"query": "Explain how AI learns from data"}
    response = requests.post(f"{BASE_URL}/search/", json=query)

    assert response.status_code == 200, f"Search failed: {response.text}"
    body = response.json()
    assert "results" in body
    assert isinstance(body["results"], list)
    if len(body["results"]) > 0:
        assert "document" in body["results"][0]
        assert "content" in body["results"][0]


# --- Invalid files ---


def test_ingest_rejects_non_pdf_file(tmp_path):
    """Uploading a non-PDF file (e.g. .txt) should return 400."""
    txt_path = tmp_path / "document.txt"
    txt_path.write_text("Some text content.")

    with open(txt_path, "rb") as f:
        response = requests.post(f"{BASE_URL}/ingest/", files={"input": (txt_path.name, f, "text/plain")})

    assert response.status_code == 400, f"Expected 400 for non-PDF: {response.text}"
    body = response.json()
    assert "detail" in body
    assert "PDF" in body["detail"] or "pdf" in body["detail"].lower()


def test_ingest_rejects_missing_input():
    """POST /ingest/ without input field should return 400."""
    response = requests.post(f"{BASE_URL}/ingest/", data={})
    assert response.status_code == 400, f"Expected 400 for missing input: {response.text}"
    body = response.json()
    assert "detail" in body


# --- Empty / invalid queries ---


def test_search_rejects_empty_query():
    """Search with empty string query should return 400."""
    response = requests.post(f"{BASE_URL}/search/", json={"query": ""})
    assert response.status_code == 400, f"Expected 400 for empty query: {response.text}"
    body = response.json()
    assert "detail" in body
    assert "empty" in body["detail"].lower() or "query" in body["detail"].lower()


def test_search_rejects_whitespace_only_query():
    """Search with whitespace-only query should return 400."""
    response = requests.post(f"{BASE_URL}/search/", json={"query": "   \n\t  "})
    assert response.status_code == 400, f"Expected 400 for whitespace query: {response.text}"
    body = response.json()
    assert "detail" in body


# --- Concurrent uploads ---


def _upload_and_wait(tmp_path, i):
    """Upload one PDF and wait for job to complete. Returns (success, job_id or error)."""
    pdf_path = tmp_path / f"doc_{i}.pdf"
    pdf_path.write_text(f"Content for document {i}. AI and machine learning.")
    with open(pdf_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/ingest/", files={"input": (pdf_path.name, f, "application/pdf")})
    if r.status_code != 202:
        return False, r.text
    body = r.json()
    job_id = body["job_id"]
    start = time.time()
    while time.time() - start < 60:
        sr = requests.get(f"{BASE_URL}/ingest/status/{job_id}")
        if sr.status_code != 200:
            return False, sr.text
        data = sr.json()
        if data["status"] == "completed":
            return True, job_id
        if data["status"] == "failed":
            return False, data.get("error", "failed")
        time.sleep(0.3)
    return False, "timeout"


def test_concurrent_uploads(tmp_path):
    """Multiple simultaneous ingest requests should all succeed."""
    num_uploads = 3  # keep moderate to avoid connection resets in-container
    with ThreadPoolExecutor(max_workers=num_uploads) as executor:
        futures = [executor.submit(_upload_and_wait, tmp_path, i) for i in range(num_uploads)]
        results = [f.result() for f in as_completed(futures)]

    successes = [r for r in results if r[0]]
    failures = [r for r in results if not r[0]]
    assert len(successes) == num_uploads, (
        f"Expected all {num_uploads} concurrent uploads to succeed; "
        f"{len(failures)} failed: {failures}"
    )
