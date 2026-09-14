from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

st.set_page_config(
    page_title="Document verification",
    page_icon=":material/document_search:",
    layout="wide",
)

page = st.navigation(
    [
        st.Page(
            "app_pages/dashboard.py",
            title="Dashboard",
            icon=":material/dashboard:",
            url_path="dashboard",
            default=True,
        ),
        st.Page(
            "app_pages/ccc_verification.py",
            title="CCC verification",
            icon=":material/fact_check:",
            url_path="ccc-verification",
        ),
        st.Page(
            "app_pages/simple_rag.py",
            title="Simple RAG",
            icon=":material/chat:",
            url_path="simple-rag",
        ),
        st.Page(
            "app_pages/image_pdf_to_text.py",
            title="Image PDF to Text PDF",
            icon=":material/document_scanner:",
            url_path="image-pdf-to-text",
        ),
    ],
    position="sidebar",
    expanded=True,
)

page.run()
