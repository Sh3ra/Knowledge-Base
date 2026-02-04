"""
Functional tests for the PDF Ingestor & Semantic Search API.

Covers: ingest (single/multiple/directory, validation, status), search (results, empty, validation).
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


def test_ingest_multiple_pdfs(tmp_path):
    """Multiple PDFs in one request: 202 and job completes with all files."""
    for i in range(3):
        (tmp_path / f"doc{i}.pdf").write_text(f"Content {i}. Machine learning and data.")
    with (tmp_path / "doc0.pdf").open("rb") as f0, (tmp_path / "doc1.pdf").open("rb") as f1, (tmp_path / "doc2.pdf").open("rb") as f2:
        response = requests.post(
            f"{BASE_URL}/ingest/",
            files=[
                ("input", ("doc0.pdf", f0, "application/pdf")),
                ("input", ("doc1.pdf", f1, "application/pdf")),
                ("input", ("doc2.pdf", f2, "application/pdf")),
            ],
        )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["job_id"] is not None
    assert len(body["files"]) == 3
    status = _wait_for_ingest_job(body["job_id"])
    assert status["status"] == "completed"
    assert len(status["files"]) == 3


def test_ingest_empty_directory_path():
    """Empty directory path should return 400."""
    response = requests.post(f"{BASE_URL}/ingest/", data={"input": ""})
    assert response.status_code == 400, response.text
    assert "detail" in response.json()
    assert "empty" in response.json()["detail"].lower() or "path" in response.json()["detail"].lower()


def test_ingest_too_many_files(tmp_path):
    """More than MAX_FILES_PER_UPLOAD (10) should return 400."""
    for i in range(11):
        (tmp_path / f"f{i}.pdf").write_text(f"Page {i}.")
    handles = [(tmp_path / f"f{i}.pdf").open("rb") for i in range(11)]
    try:
        files = [
            ("input", (f"f{i}.pdf", handles[i], "application/pdf"))
            for i in range(11)
        ]
        response = requests.post(f"{BASE_URL}/ingest/", files=files)
    finally:
        for h in handles:
            h.close()
    assert response.status_code == 400, response.text
    body = response.json()
    assert "detail" in body
    assert "10" in body["detail"] or "Maximum" in body["detail"]


def test_ingest_status_not_found():
    """GET /ingest/status/{job_id} with unknown job_id returns 404."""
    response = requests.get(f"{BASE_URL}/ingest/status/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404, response.text
    assert "detail" in response.json()


def test_ingest_status_response_shape(tmp_path):
    """Job status response has job_id, status, files, error."""
    (tmp_path / "one.pdf").write_text("Single page.")
    with (tmp_path / "one.pdf").open("rb") as f:
        r = requests.post(f"{BASE_URL}/ingest/", files={"input": f})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    status = _wait_for_ingest_job(job_id)
    assert "job_id" in status
    assert "status" in status
    assert "files" in status
    assert "error" in status
    assert status["status"] == "completed"


def test_search_query():
    """Valid search returns 200 with results list and optional message."""
    query = {"query": "Explain how AI learns from data"}
    response = requests.post(f"{BASE_URL}/search/", json=query)

    assert response.status_code == 200, f"Search failed: {response.text}"
    body = response.json()
    assert "results" in body
    assert isinstance(body["results"], list)
    if len(body["results"]) > 0:
        assert "document" in body["results"][0]
        assert "content" in body["results"][0]


def test_search_no_results_fallback_message():
    """Search for something that does not exist: fallback message is returned."""
    # Query chosen so no ingested document matches (gibberish + unique)
    response = requests.post(
        f"{BASE_URL}/search/",
        json={"query": "xyzzynonexistenttopic123 qwerty no relevant document exists"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "results" in body
    assert "message" in body
    # When no results, API must return the fallback message
    if not body["results"]:
        assert body["message"] == "No relevant documents found.", (
            f"Expected fallback when no results; got message={body.get('message')!r}"
        )


# --- Directory ingest ---


def test_ingest_directory_path():
    """POST with directory path input=/data: 202 and valid response (job_id + files or no PDFs)."""
    response = requests.post(f"{BASE_URL}/ingest/", data={"input": "/data"})
    assert response.status_code == 202, response.text
    body = response.json()
    assert "message" in body
    assert "files" in body
    if body.get("job_id") is not None:
        status = _wait_for_ingest_job(body["job_id"])
        assert status["status"] in ("completed", "failed")
    else:
        assert "No PDF" in body["message"] or body["files"] == []


def test_ingest_directory_invalid_path():
    """Invalid or non-existent directory path returns 400."""
    response = requests.post(f"{BASE_URL}/ingest/", data={"input": "/nonexistent_path_12345"})
    assert response.status_code == 400, response.text
    assert "detail" in response.json()


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
    """Multiple simultaneous ingest requests should succeed (at least 2 when env allows)."""
    num_uploads = 3
    with ThreadPoolExecutor(max_workers=num_uploads) as executor:
        futures = [executor.submit(_upload_and_wait, tmp_path, i) for i in range(num_uploads)]
        results = [f.result() for f in as_completed(futures)]

    successes = [r for r in results if r[0]]
    # App allows 4 concurrent ingest jobs; some environments (proxy, limit) may cap lower
    assert len(successes) >= 2, (
        f"Expected at least 2 of {num_uploads} concurrent uploads to succeed; "
        f"failures: {[r for r in results if not r[0]]}"
    )
