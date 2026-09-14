from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.app.simple_rag.backend import RAGError
from sandbox.app.simple_rag.service import (
    is_api_configured,
    load_uploaded_rag,
)

# Upload identity and chat history are isolated to this application/session.
st.session_state.setdefault("simple_rag_uploader_generation", 0)
st.session_state.setdefault("simple_rag_active_fingerprint", None)
st.session_state.setdefault("simple_rag_initialized_fingerprint", None)
st.session_state.setdefault("simple_rag_messages", [])
st.session_state.setdefault("simple_rag_error", None)


def clear_conversation() -> None:
    st.session_state.simple_rag_messages = []


def reset_rag() -> None:
    current_key = f"simple_rag_upload_{st.session_state.simple_rag_uploader_generation}"
    st.session_state.pop(current_key, None)
    st.session_state.simple_rag_uploader_generation += 1
    st.session_state.simple_rag_active_fingerprint = None
    st.session_state.simple_rag_initialized_fingerprint = None
    st.session_state.simple_rag_messages = []
    st.session_state.simple_rag_error = None


st.title("Simple RAG / PDF 问答")
st.caption(
    "Upload one text-based PDF, build its index, and ask grounded questions. / "
    "上传一个文本型 PDF，建立索引后即可进行问答。"
)

api_ready = is_api_configured()
if not api_ready:
    st.error(
        "DASHSCOPE_API_KEY is not configured. Indexing and questions are "
        "disabled. / 未配置 DASHSCOPE_API_KEY。"
    )

uploader_key = f"simple_rag_upload_{st.session_state.simple_rag_uploader_generation}"
uploaded_file = st.file_uploader(
    "Text-based PDF / 文本型 PDF",
    type=["pdf"],
    accept_multiple_files=False,
    help="Upload one searchable PDF, up to 50 MB.",
    key=uploader_key,
)

rag_runtime: tuple[Any, Any] | None = None
if uploaded_file is None:
    if st.session_state.simple_rag_active_fingerprint is not None:
        st.session_state.simple_rag_active_fingerprint = None
        st.session_state.simple_rag_initialized_fingerprint = None
        st.session_state.simple_rag_messages = []
        st.session_state.simple_rag_error = None
    st.info(
        "Choose a PDF containing selectable text. Image-only PDFs should first "
        "be converted on the Image PDF to Text PDF page. / "
        "请选择含可选择文字的 PDF；图片型 PDF 请先进行转换。"
    )
else:
    pdf_data = uploaded_file.getvalue()
    upload_fingerprint = hashlib.sha256(
        uploaded_file.name.encode("utf-8") + b"\0" + pdf_data
    ).hexdigest()
    if upload_fingerprint != st.session_state.simple_rag_active_fingerprint:
        st.session_state.simple_rag_active_fingerprint = upload_fingerprint
        st.session_state.simple_rag_initialized_fingerprint = None
        st.session_state.simple_rag_messages = []
        st.session_state.simple_rag_error = None

    with st.container(border=True):
        name_column, size_column = st.columns([3, 1])
        name_column.caption(":material/picture_as_pdf: PDF knowledge source")
        name_column.markdown(f"**{uploaded_file.name}**")
        size_column.caption(":material/data_usage: Size / 大小")
        size_column.markdown(f"**{len(pdf_data) / (1024 * 1024):.2f} MB**")

    initialized = (
        st.session_state.simple_rag_initialized_fingerprint == upload_fingerprint
    )
    with st.container(horizontal=True):
        initialize_clicked = st.button(
            "Initialize knowledge base / 建立知识库",
            type="primary",
            icon=":material/database:",
            disabled=not api_ready,
            key=f"initialize_simple_rag_{upload_fingerprint}",
        )
        st.button(
            "New PDF / 新文件",
            icon=":material/refresh:",
            on_click=reset_rag,
            key="reset_simple_rag",
        )

    if initialize_clicked or initialized:
        try:
            with st.spinner(
                "Reading and indexing PDF… / 正在读取并建立索引…",
                show_time=True,
            ):
                rag_runtime = load_uploaded_rag(
                    uploaded_file.name,
                    pdf_data,
                    upload_fingerprint,
                )
            st.session_state.simple_rag_initialized_fingerprint = upload_fingerprint
            st.session_state.simple_rag_error = None
        except Exception as exc:  # noqa: BLE001
            st.session_state.simple_rag_initialized_fingerprint = None
            st.session_state.simple_rag_error = f"{exc.__class__.__name__}: {exc}"

if st.session_state.simple_rag_error:
    st.error(f"Knowledge base error / 知识库错误: {st.session_state.simple_rag_error}")

if rag_runtime is not None:
    rag, rag_index = rag_runtime
    metrics = st.columns(2)
    metrics[0].metric("Text pages / 文本页", rag_index.page_count)
    metrics[1].metric("Chunks / 文本块", rag_index.chunk_count)

    if st.session_state.simple_rag_messages:
        st.button(
            "Clear conversation / 清空对话",
            icon=":material/delete_sweep:",
            on_click=clear_conversation,
            key="clear_simple_rag_conversation",
        )

for message in st.session_state.simple_rag_messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        sources = message.get("sources", [])
        if sources:
            with st.expander("Sources / 来源", expanded=False):
                for source in sources:
                    st.markdown(
                        f"**Page {source['page_number']} / "
                        f"第 {source['page_number']} 页**"
                    )
                    st.write(source["excerpt"])

question = st.chat_input(
    "Ask a question about the PDF / 询问 PDF 内容",
    disabled=rag_runtime is None,
    submit_mode="disable",
    key="simple_rag_question",
)

if question and rag_runtime is not None:
    rag, rag_index = rag_runtime
    st.session_state.simple_rag_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching the PDF… / 正在检索 PDF…"):
                answer = rag.answer(rag_index, question)
            st.write(answer.answer)
            source_payload = [
                source.model_dump(mode="json") for source in answer.sources
            ]
            if source_payload:
                with st.expander("Sources / 来源", expanded=False):
                    for source in source_payload:
                        st.markdown(
                            f"**Page {source['page_number']} / "
                            f"第 {source['page_number']} 页**"
                        )
                        st.write(source["excerpt"])
            st.session_state.simple_rag_messages.append(
                {
                    "role": "assistant",
                    "content": answer.answer,
                    "sources": source_payload,
                }
            )
        except RAGError as exc:
            st.error(f"Question failed / 问答失败: {exc}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Question failed / 问答失败: {exc.__class__.__name__}: {exc}")
