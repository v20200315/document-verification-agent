from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

import streamlit as st
from sandbox.app.simple_rag.backend import RAGError, RAGIndex, SimplePDFRAG

SANDBOX_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = SANDBOX_DIR.parent
KNOWLEDGE_PDF_PATH = SANDBOX_DIR / "knowledge" / "source.pdf"


def is_api_configured() -> bool:
    """Simple RAG owns its environment loading instead of importing CCC code."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return bool(os.getenv("DASHSCOPE_API_KEY", "").strip())


def knowledge_source_signature(
    pdf_path: Path = KNOWLEDGE_PDF_PATH,
) -> tuple[str, int, int]:
    """File metadata changes invalidate both the index and page chat state."""
    path = pdf_path.expanduser().resolve()
    if not path.is_file():
        raise RAGError(
            f"Knowledge PDF not found: {path}. "
            "Place the file at sandbox/knowledge/source.pdf."
        )
    if path.suffix.lower() != ".pdf":
        raise RAGError(f"Knowledge source must be a PDF: {path}")
    stat = path.stat()
    if stat.st_size == 0:
        raise RAGError(f"Knowledge PDF is empty: {path}")
    return str(path), stat.st_mtime_ns, stat.st_size


@st.cache_resource(max_entries=2, show_spinner=False)
def load_cached_rag(
    path_string: str,
    modified_time_ns: int,
    file_size: int,
) -> tuple[SimplePDFRAG, RAGIndex]:
    """Cache expensive embeddings and scanned-page OCR by file version."""
    del modified_time_ns, file_size
    rag = SimplePDFRAG.from_env()
    return rag, rag.build_index(Path(path_string))
