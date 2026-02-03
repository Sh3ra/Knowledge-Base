"""PDF extraction, chunking, and document logic (LangChain Document + splitter)."""

import logging
from pathlib import Path

import fitz
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import CHUNK_OVERLAP, CHUNK_SIZE, INGEST_DATA_PATH

logger = logging.getLogger(__name__)

_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def extract_text_from_pdf(content: bytes, filename: str) -> str:
    """
    Extract text from PDF bytes.
    Falls back to UTF-8 decode if PDF parsing fails (handles plain-text files with .pdf extension).
    """
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts).strip()
    except Exception as e:
        logger.warning("PDF parse failed for %s: %s. Trying plain text fallback.", filename, e)
        try:
            return content.decode("utf-8", errors="replace").strip()
        except Exception:
            raise ValueError(f"Could not extract text from {filename}") from e


def process_pdf_to_documents(content: bytes, filename: str) -> list[Document]:
    """
    Extract text from PDF and split into LangChain Documents (with metadata).
    Used for vectorstore.add_documents(); embedding is done by the vectorstore.
    """
    text = extract_text_from_pdf(content, filename)
    if not text or not text.strip():
        return []
    doc = Document(page_content=text, metadata={"source": filename})
    return _text_splitter.split_documents([doc])


def get_pdf_files_from_directory(dir_path: str) -> list[tuple[str, bytes]]:
    """
    Get all PDF files from a directory path.
    Returns list of (filename, content) tuples.
    Path must be under INGEST_DATA_PATH to prevent path traversal.
    """
    base = Path(INGEST_DATA_PATH).resolve()
    path = dir_path.strip()
    if not path or path in (".", "/"):
        resolved = base
    elif path.startswith("/"):
        resolved = Path(path).resolve()
    else:
        resolved = (base / path).resolve()

    if not str(resolved).startswith(str(base)):
        raise ValueError("Invalid directory path: path traversal not allowed")
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError(f"Directory not found: {dir_path}")

    results = []
    for f in resolved.glob("**/*.pdf"):
        if f.is_file():
            try:
                content = f.read_bytes()
                results.append((f.name, content))
            except Exception as e:
                logger.warning("Could not read %s: %s", f.name, e)
    return results
