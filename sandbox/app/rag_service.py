from __future__ import annotations

from pathlib import Path

import streamlit as st
from sandbox.src.errors import RAGError
from sandbox.src.rag import RAGIndex, SimplePDFRAG

SANDBOX_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_PDF_PATH = SANDBOX_DIR / "knowledge" / "source.pdf"


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
    # Metadata arguments intentionally participate in Streamlit's cache key.
    del modified_time_ns, file_size
    rag = SimplePDFRAG.from_env()
    return rag, rag.build_index(Path(path_string))
