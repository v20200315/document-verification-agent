from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.app.simple_rag.backend import RAGError
from sandbox.app.simple_rag.service import (
    KNOWLEDGE_PDF_PATH,
    is_api_configured,
    knowledge_source_signature,
    load_cached_rag,
)

# Chat is session-local; the expensive PDF index is shared through cache_resource.
st.session_state.setdefault("simple_rag_messages", [])
st.session_state.setdefault("simple_rag_source_signature", None)
st.session_state.setdefault("simple_rag_initialized_signature", None)
st.session_state.setdefault("simple_rag_error", None)


def clear_conversation() -> None:
    st.session_state.simple_rag_messages = []


st.title("Simple RAG / PDF 问答")
st.caption(
    "Answers are grounded only in sandbox/knowledge/source.pdf. / "
    "回答仅基于固定 PDF 知识库。"
)

api_ready = is_api_configured()
try:
    source_signature = knowledge_source_signature()
    source_error = None
except RAGError as exc:
    source_signature = None
    source_error = str(exc)

if source_signature != st.session_state.simple_rag_source_signature:
    st.session_state.simple_rag_source_signature = source_signature
    st.session_state.simple_rag_initialized_signature = None
    st.session_state.simple_rag_messages = []
    st.session_state.simple_rag_error = None

with st.container(border=True):
    st.caption(":material/picture_as_pdf: Knowledge source / 知识库文件")
    st.markdown(f"**`{KNOWLEDGE_PDF_PATH.name}`**")
    st.caption(str(KNOWLEDGE_PDF_PATH))

if source_error:
    st.error(source_error)
    st.info(
        "Place one PDF at `sandbox/knowledge/source.pdf`, then rerun the page. / "
        "请将一个 PDF 放到该路径后重新运行页面。"
    )

if not api_ready:
    st.error(
        "DASHSCOPE_API_KEY is not configured. PDF indexing and questions are "
        "disabled. / 未配置 DASHSCOPE_API_KEY。"
    )

rag_runtime: tuple[Any, Any] | None = None
if source_signature is not None and api_ready:
    initialized = st.session_state.simple_rag_initialized_signature == source_signature
    if not initialized:
        st.info(
            "First-time indexing may call Qwen-VL for scanned pages and create "
            "embeddings. It will be cached for this PDF version. / "
            "首次建立索引时，扫描页会调用 Qwen-VL，并生成向量索引。"
        )
        initialize_clicked = st.button(
            "Initialize knowledge base / 建立知识库",
            type="primary",
            icon=":material/database:",
            key="initialize_simple_rag",
        )
    else:
        initialize_clicked = False

    if initialize_clicked or initialized:
        try:
            with st.spinner(
                "Indexing PDF… / 正在建立 PDF 索引…",
                show_time=True,
            ):
                rag_runtime = load_cached_rag(*source_signature)
            st.session_state.simple_rag_initialized_signature = source_signature
            st.session_state.simple_rag_error = None
        except Exception as exc:  # noqa: BLE001
            st.session_state.simple_rag_initialized_signature = None
            st.session_state.simple_rag_error = f"{exc.__class__.__name__}: {exc}"

if st.session_state.simple_rag_error:
    st.error(f"Knowledge base error / 知识库错误: {st.session_state.simple_rag_error}")

if rag_runtime is not None:
    rag, rag_index = rag_runtime
    metrics = st.columns(3)
    metrics[0].metric("Pages / 页数", rag_index.page_count)
    metrics[1].metric("Scanned pages / 扫描页", rag_index.scanned_page_count)
    metrics[2].metric("Chunks / 文本块", rag_index.chunk_count)

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
                        f"**Page {source['page_number']} / 第 {source['page_number']} 页**"
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
