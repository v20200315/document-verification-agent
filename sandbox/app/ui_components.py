from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import streamlit as st
from sandbox.src.schemas import DocumentResult

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def render_upload_preview(uploaded_file: Any) -> None:
    suffix = Path(uploaded_file.name).suffix.lower()
    with st.container(border=True):
        st.subheader("Selected document / 已选文档")
        if suffix in IMAGE_SUFFIXES:
            st.image(
                uploaded_file.getvalue(),
                caption=uploaded_file.name,
                width="stretch",
            )
        else:
            st.markdown(f"**PDF:** `{uploaded_file.name}`")
            st.caption(
                "The page count will appear after extraction. / 解析完成后将显示页数。"
            )


def render_result(result: DocumentResult) -> None:
    st.subheader("Extraction result / 解析结果")
    metrics = st.columns(4)
    metrics[0].metric("File type / 文件类型", result.file_type)
    metrics[1].metric("Category / 文档类别", str(result.doc_category))
    metrics[2].metric(
        "Confidence / 置信度",
        (
            f"{result.category_confidence:.0%}"
            if result.category_confidence is not None
            else "N/A"
        ),
    )
    metrics[3].metric(
        "Pages / 页数",
        str(result.page_count) if result.page_count is not None else "N/A",
    )

    if result.category_reasoning:
        st.info(f"Classification reasoning / 分类依据: {result.category_reasoning}")

    content_key = hashlib.sha256(result.full_content.encode("utf-8")).hexdigest()[:12]
    with st.expander("Full content / 完整内容", expanded=False):
        st.text_area(
            "Extracted text / 提取文本",
            value=result.full_content,
            height=420,
            disabled=True,
            key=f"full_content_{content_key}",
        )
        st.download_button(
            "Download text / 下载文本",
            data=result.full_content.encode("utf-8"),
            file_name=f"{Path(result.file_name).stem}_extracted.txt",
            mime="text/plain",
            icon=":material/download:",
            key=f"download_{content_key}",
        )
