from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv

import streamlit as st
from sandbox.app.simple_rag.backend import RAGError, RAGIndex, SimplePDFRAG

SANDBOX_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = SANDBOX_DIR.parent
UPLOAD_TEMP_ROOT = SANDBOX_DIR / "uploads" / ".tmp"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def is_api_configured() -> bool:
    """Simple RAG owns its environment loading and readiness check."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return bool(os.getenv("DASHSCOPE_API_KEY", "").strip())


@st.cache_resource(max_entries=4, show_spinner=False)
def load_uploaded_rag(
    file_name: str,
    pdf_data: bytes,
    upload_fingerprint: str,
) -> tuple[SimplePDFRAG, RAGIndex]:
    """Cache an index by immutable upload content while removing its temp file."""
    del upload_fingerprint
    safe_name = _safe_pdf_name(file_name)
    if not pdf_data:
        raise RAGError("The uploaded PDF is empty.")
    if len(pdf_data) > MAX_UPLOAD_BYTES:
        raise RAGError("The uploaded PDF exceeds the 50 MB limit.")

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    UPLOAD_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix="simple-rag-", dir=UPLOAD_TEMP_ROOT))
    temporary_path = temporary_dir / safe_name
    try:
        temporary_path.write_bytes(pdf_data)
        rag = SimplePDFRAG.from_env()
        return rag, rag.build_index(temporary_path)
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def _safe_pdf_name(file_name: str) -> str:
    base_name = Path(file_name).name
    if Path(base_name).suffix.lower() != ".pdf":
        raise RAGError("Only files with a .pdf extension are supported.")
    stem = re.sub(r"[^\w.-]+", "_", Path(base_name).stem).strip("._")[:100]
    return f"{stem or 'knowledge'}.pdf"
