from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.app.pipeline_service import (
    is_api_configured,
    process_uploaded_document,
)
from sandbox.app.ui_components import (
    render_result,
    render_upload_preview,
)
from sandbox.src.errors import DocumentPipelineError

st.set_page_config(
    page_title="Document extraction and classification",
    page_icon=":material/document_search:",
    layout="wide",
)

# Changing this generation gives the uploader a fresh identity after reset.
st.session_state.setdefault("document_uploader_generation", 0)
# The fingerprint identifies when a new upload invalidates previous output.
st.session_state.setdefault("active_upload_fingerprint", None)
# Result and error survive ordinary reruns but reset for each new document.
st.session_state.setdefault("latest_document_result", None)
st.session_state.setdefault("latest_processing_error", None)


def reset_document() -> None:
    current_key = f"document_upload_{st.session_state.document_uploader_generation}"
    st.session_state.pop(current_key, None)
    st.session_state.document_uploader_generation += 1
    st.session_state.active_upload_fingerprint = None
    st.session_state.latest_document_result = None
    st.session_state.latest_processing_error = None


st.title("Document extraction and classification")
st.caption(
    "Upload one PDF or image, then explicitly start Qwen extraction. / "
    "上传一个 PDF 或图片，然后手动开始通义千问解析。"
)

api_ready = is_api_configured()
if not api_ready:
    st.error(
        "DASHSCOPE_API_KEY is not configured. Set it in the environment "
        "or project-root .env before processing. / "
        "未配置 DASHSCOPE_API_KEY，请先设置环境变量或项目根目录 .env。"
    )

uploader_key = f"document_upload_{st.session_state.document_uploader_generation}"
uploaded_file = st.file_uploader(
    "Document / 文档",
    type=["pdf", "jpg", "jpeg", "png"],
    accept_multiple_files=False,
    help="Accepted formats: PDF, JPG, JPEG, PNG.",
    key=uploader_key,
)

if uploaded_file is None:
    if st.session_state.active_upload_fingerprint is not None:
        st.session_state.active_upload_fingerprint = None
        st.session_state.latest_document_result = None
        st.session_state.latest_processing_error = None
    st.info(
        "Choose a document to begin. Processing will not start "
        "automatically. / 请选择文档；上传后不会自动调用模型。"
    )
else:
    uploaded_bytes = uploaded_file.getvalue()
    upload_fingerprint = hashlib.sha256(
        uploaded_file.name.encode("utf-8") + b"\0" + uploaded_bytes
    ).hexdigest()

    if upload_fingerprint != st.session_state.active_upload_fingerprint:
        st.session_state.active_upload_fingerprint = upload_fingerprint
        st.session_state.latest_document_result = None
        st.session_state.latest_processing_error = None

    render_upload_preview(uploaded_file)

    with st.container(horizontal=True):
        start_clicked = st.button(
            "Start / 开始解析",
            type="primary",
            icon=":material/play_arrow:",
            disabled=not api_ready,
            key=f"start_processing_{upload_fingerprint}",
        )
        st.button(
            "New document / 新文档",
            icon=":material/refresh:",
            on_click=reset_document,
            key="reset_document",
        )

    if start_clicked:
        st.session_state.latest_document_result = None
        st.session_state.latest_processing_error = None
        try:
            with st.spinner(
                "Extracting and classifying… / 正在提取并分类…",
                show_time=True,
            ):
                st.session_state.latest_document_result = process_uploaded_document(
                    uploaded_file.name,
                    uploaded_bytes,
                )
        except DocumentPipelineError as exc:
            st.session_state.latest_processing_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            st.session_state.latest_processing_error = (
                f"{exc.__class__.__name__}: {exc}"
            )

    if st.session_state.latest_processing_error:
        st.error(
            f"Processing failed / 处理失败: {st.session_state.latest_processing_error}"
        )

    if st.session_state.latest_document_result is not None:
        render_result(st.session_state.latest_document_result)
