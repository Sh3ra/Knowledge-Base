# PDF Ingestor & Semantic Search API

A fully containerized API that ingests PDF documents, chunks them with LangChain, generates embeddings via Jina AI, stores them in Qdrant, and exposes semantic search. Built with FastAPI and LangChain.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Data Flow](#data-flow)
- [Configuration](#configuration)
- [Logging](#logging)
- [API Reference](#api-reference)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)
- [Limitations](#limitations)

---

## Features

| Feature | Description |
|--------|-------------|
| **PDF ingestion** | Accept single/multiple PDF uploads or a directory path. Only PDFs are accepted. |
| **Async ingest** | Returns 202 Accepted immediately; chunking and embedding run in background. Poll job status to know when done. |
| **Directory ingest** | Send path `input=/data` to ingest all PDFs from the project `data/` folder (mounted at `/data` in the container). |
| **Semantic search** | POST a query; returns top-k chunks ranked by cosine similarity (embeddings). |
| **LangChain integration** | Document loading (PDF → `Document`), `RecursiveCharacterTextSplitter` for chunking, LangChain Qdrant vectorstore and Jina embeddings. |
| **Chunking** | Configurable chunk size and overlap (env). Splits on paragraph/sentence boundaries when possible. |
| **Embeddings** | Jina AI `jina-embeddings-v3` (1024-dim) via API; no local model. |
| **Vector store** | Qdrant with cosine similarity; single collection `pdf_chunks`. |
| **OpenAPI docs** | Interactive docs at `/docs`. |
| **Config via env** | Jina key, chunking, TOP_K, Qdrant host/port from `.env`.|
| **Tests in container** | Functional test suite runs inside the app container.|

---

## Prerequisites

- **Docker** and **Docker Compose**
- **Jina AI API key** (e.g. from [Jina API dashboard](https://jina.ai/api-dashboard/key-manager))

---

## Quick Start

```bash
# 1. Environment
cp .env.example .env
# Edit .env and set JINA_API_KEY=your_key

# 2. Start stack (API + Qdrant)
./orchestrate.sh --action start

# Add your PDF files to the data/ directory (mounted as /data in the container) to ingest them in step 4.

# 3. Ingest one file
curl -X POST "http://localhost:8000/ingest/" -F "input=@data/sample.pdf"

# 3b. Ingest multiple files
curl -X POST "http://localhost:8000/ingest/" \
  -F "input=@data/sample.pdf" \
  -F "input=@data/sample2.pdf"

# 4. Ingest entire data directory (/data is the project's data/ folder)
curl -X POST "http://localhost:8000/ingest/" -F "input=/data"

# 5. Check job status (use job_id from step 3 or 4)
curl "http://localhost:8000/ingest/status/{job_id}"

# 6. Search
curl -X POST "http://localhost:8000/search/" \
  -H "Content-Type: application/json" \
  -d '{"query": "How does semantic search work?"}'

# 7. Stop and remove containers/volumes
./orchestrate.sh --action terminate
```

- **API:** http://localhost:8000
- **Docs:** http://localhost:8000/docs

---

## Architecture

### High-level

```
┌─────────────┐     HTTP      ┌──────────────────────────────────────────────────┐
│   Client    │ ◄──────────► │  FastAPI (port 8000)                               │
│ (curl, UI)  │              │  ├── POST /ingest/        (validate → background)  │
└─────────────┘              │  ├── GET  /ingest/status/{job_id}                  │
                             │  └── POST /search/        (embed query → search)   │
                             └─────────────────┬────────────────────────────────┘
                                                │
              ┌─────────────────────────────────┼─────────────────────────────────┐
              │                                 │                                 │
              ▼                                 ▼                                 ▼
     ┌────────────────┐              ┌──────────────────┐              ┌─────────────────┐
     │  PyMuPDF       │              │  LangChain        │              │  Qdrant         │
     │  (extract text)│              │  JinaEmbeddings   │              │  (vector store) │
     └────────────────┘              │  + Qdrant store  │              │  port 6333      │
                                     └────────┬─────────┘              └────────┬────────┘
                                              │                                 │
                                              │  Jina AI API (HTTPS)            │
                                              └─────────────────────────────────┘
```

### Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI, Uvicorn |
| PDF extraction | PyMuPDF (fitz) |
| Chunking | LangChain `RecursiveCharacterTextSplitter` |
| Documents | LangChain `Document` (metadata: `source` = filename) |
| Embeddings | LangChain `JinaEmbeddings` → Jina AI API (jina-embeddings-v3, 1024 dim) |
| Vector store | LangChain `Qdrant` (wraps qdrant-client), cosine similarity |
| Vector DB | Qdrant v1.12.1 (Docker), persistent volume |

### Concurrency and resources

- **Ingest:** Request validated synchronously; then a background task is scheduled. Up to **4** concurrent background ingest jobs (semaphore). Each job runs PDF processing in a **thread pool (4 workers)** so the event loop is not blocked.
- **Search:** Synchronous embed + vector search in the main process; no background queue.

---

## Data Flow

### Ingest flow

1. **Request**
   Client sends `POST /ingest/` with either:
   - One or more PDF files (multipart `input`), or
   - A single string `input=/data` (directory path).

2. **Validation (sync)**
   - Files: check PDF extension, size ≤ 50 MB, read body.
   - Directory: resolve path under `INGEST_DATA_PATH`, list PDFs, read bytes.

3. **Response**
   Return **202 Accepted** with `job_id`, `message`, and `files` list.

4. **Background (async)**
   For each file (respecting semaphore and thread pool):
   - **Extract:** PyMuPDF → raw text (fallback: UTF-8 decode if PDF parse fails).
   - **Document:** Build LangChain `Document(page_content=text, metadata={"source": filename})`.
   - **Split:** `RecursiveCharacterTextSplitter` → list of `Document` (chunk size/overlap from config).
   - **Store:** `vectorstore.add_documents(documents)` → Jina embed (sync) + Qdrant upsert.
   - **Status:** Update `job_status[job_id]` to `completed` or `failed`.

5. **Status**
   Client polls `GET /ingest/status/{job_id}` until `status` is `completed` or `failed`.

### Search flow

1. **Request**
   Client sends `POST /search/` with JSON `{"query": "..."}`.

2. **Validation**
   Reject empty or whitespace-only query (400).

3. **Embed**
   LangChain vectorstore embeds the query (Jina API, query task).

4. **Search**
   `vectorstore.similarity_search_with_score(query, k=TOP_K)` (default TOP_K=5).

5. **Response**
   JSON list of `{document, score, content}` (document = source filename, content = chunk text).

---

## Configuration

Variables are read from `.env` (and from `docker-compose` env_file for the app). See `.env.example`.

| Variable | Default | Description |
|----------|---------|-------------|
| `JINA_API_KEY` | (required) | Jina AI API key. |
| `JINA_EMBEDDING_MODEL` | `jina-embeddings-v3` | Jina model name. |
| `JINA_API_URL` | `https://api.jina.ai/v1/embeddings` | Jina embeddings endpoint. |
| `EMBEDDING_DIM` | `1024` | Vector dimension (must match model). |
| `CHUNK_SIZE` | `500` | Chunk size in characters. |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks. |
| `TOP_K` | `5` | Number of search results per query (capped at 20). |
| `QDRANT_HOST` | `qdrant` | Qdrant host (use `qdrant` in Docker). |
| `QDRANT_PORT` | `6333` | Qdrant port. |

---

## Logging

- **Default log file:** Logs are written to **`logs/app.log`** (under the project root). The `logs/` directory is created automatically if it doesn’t exist. Logs also go to stdout/stderr.
- **Where to see logs:** When running with Docker Compose, `./logs` is mounted into the container at `/app/logs`, so the log file appears on the host at **`./logs/app.log`**. You can also use `docker compose logs app` for stdout.
---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ingest/` | Submit PDF file(s) or directory path. Body: multipart form, field `input` = file(s) or string path. Returns 202 + `job_id`. |
| GET | `/ingest/status/{job_id}` | Get ingest job status: `pending` → `processing` → `completed` or `failed`. |
| POST | `/search/` | Semantic search. Body: JSON `{"query": "..."}`. Returns `{ "results": [ { "document", "score", "content" }, ... ] }`. |

- **Errors:** 400 (validation), 404 (job not found), 500 (server error).
- Interactive API docs (Swagger UI) are available at http://localhost:8000/docs when the app is running.

---

## Running Tests

With the stack running (`./orchestrate.sh --action start`):

**Inside the app container (recommended):**

```bash
docker compose exec app pytest tests/suite.py -v
```

Tests hit `http://localhost:8000` (from inside the container that is the same process as the API). They cover: single ingest, search, reject non-PDF, reject missing input, reject empty/whitespace query, and concurrent uploads (3 at a time for stability).

---

## Project Structure

```
Knowledge-Base/
├── orchestrate.sh           # start | terminate (docker compose up/down)
├── docker-compose.yml       # app + qdrant, .env, volumes ./data → /data, ./logs → /app/logs
├── Dockerfile               # Python 3.11, deps, app + tests
├── requirements.txt
├── .env                     # secrets and overrides (copy from .env.example)
├── .env.example
├── app/
│   ├── main.py              # FastAPI app, lifespan (wire infrastructure + api routers)
│   ├── config.py            # Env and constants (chunk, search, Qdrant, Jina)
│   ├── models.py            # Pydantic: SearchRequest, SearchResult, IngestResponse, JobStatusResponse
│   ├── core/                # Domain logic (no HTTP)
│   │   ├── ingest.py        # PDF → text, Document, split_documents, get_pdf_files_from_directory
│   │   ├── search.py        # search_vectorstore(vectorstore, query, k)
│   │   └── embeddings.py   # get_jina_embeddings() (LangChain JinaEmbeddings)
│   ├── infrastructure/      # Qdrant client, collection, vectorstore
│   │   └── vectorstore.py  # get_qdrant_client, ensure_collection, create_vectorstore
│   ├── services/
│   │   └── ingest_service.py  # run_background_ingest (semaphore, executor, vectorstore.add_documents)
│   └── api/                 # HTTP layer (routes + dependencies)
│       ├── dependencies.py   # get_vectorstore, get_job_status_store
│       ├── ingest.py         # POST /ingest/, GET /ingest/status/{job_id}
│       └── search.py         # POST /search/
├── data/                    # Mounted as /data in container; put PDFs here for directory ingest
├── logs/                    # Mounted as /app/logs in container; app.log written here (created on first run)
├── tests/
│   ├── suite.py             # Functional tests (ingest, search, errors, concurrent)
```

---

## Limitations

| Limitation | Details |
|------------|---------|
| **PDF only** | Non-PDF files (e.g. `.txt` with PDF extension) may fall back to plain-text decode; binary non-PDF is rejected. |
| **Single collection** | All ingested PDFs go into one Qdrant collection; no per-document or per-folder collections. |
| **No auth** | API has no authentication or rate limiting. |
| **In-memory job status** | Ingest job status is stored in process memory; lost on restart. No persistence of job history. |
| **No deletion API** | No endpoint to delete documents or clear the collection; use a fresh Qdrant volume or re-deploy. |
| **Upload size** | Max 50 MB per file (configurable via `MAX_UPLOAD_SIZE` in code). |
| **Directory path** | Directory ingest only allows paths under `INGEST_DATA_PATH` (default `/data`) to prevent path traversal. |
| **Concurrency** | At most 4 background ingest jobs at a time (semaphore). Thread pool of 4 for CPU-bound PDF work. |
| **Jina dependency** | Requires valid Jina API key and network access to Jina; no offline embedding option. |
| **No observability** | LangSmith is not available; no tracing or observability for LangChain (chunking, embeddings, vector store) calls. |
| **Single process** | One uvicorn process; under heavy concurrent load (e.g. many simultaneous ingest + search) connections may reset (mitigated by semaphore and moderate test concurrency). |

---

## Summary

- **Features:** Async PDF ingest (file or directory), LangChain chunking + Jina embeddings + Qdrant, semantic search, config via env, tests in container.
- **Limitations:** PDF-focused, single collection, no auth, in-memory job status, no delete API, Jina and network required, single process.
- **Architecture:** FastAPI + LangChain (splitter, Document, JinaEmbeddings, Qdrant) + PyMuPDF + Qdrant; background ingest with semaphore and thread pool.
- **Flow:** Ingest = validate → 202 + job_id → background: extract → Document → split → embed → upsert; Search = embed query → similarity_search_with_score → return top-k.
