"""Application configuration."""

import os
from pathlib import Path

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

# Jina embedding API
JINA_API_KEY = os.getenv("JINA_API_KEY", "")
JINA_EMBEDDING_MODEL = os.getenv("JINA_EMBEDDING_MODEL", "jina-embeddings-v3")
JINA_API_URL = os.getenv("JINA_API_URL", "https://api.jina.ai/v1/embeddings")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIM", "1024"))  # jina-embeddings-v3

# Chunking
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

# Search (number of results returned per query; capped at TOP_K_MAX)
TOP_K_MAX = 20
_top_k_raw = int(os.getenv("TOP_K", "5"))
TOP_K = max(1, min(_top_k_raw, TOP_K_MAX))

# Minimum quality: only return results with score (distance) <= this; cosine range [0, 2], lower = better, 2.0 = no filter
SEARCH_SCORE_THRESHOLD = float(os.getenv("SEARCH_SCORE_THRESHOLD", "1.5"))

# Vector DB
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = "pdf_chunks"

# Directory path for ingest (must be inside container)
INGEST_DATA_PATH = "/data"

# Max upload size (50 MB)
MAX_UPLOAD_SIZE = 50 * 1024 * 1024

# Log file
LOG_FILE = str(Path(__file__).resolve().parent.parent / "logs" / "app.log")
