from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import streamlit as st
from sandbox.src.schemas import DocumentResult, TamperingReport

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def render_dashboard() -> None:
    st.title("Welcome / 欢迎")
    st.caption(
        "Document extraction and CCC classification workspace / "
        "文档提取与 CCC 分类工作台"
    )

    st.subheader("What you can do / 功能")
    capabilities = st.columns(3)
    with capabilities[0].container(border=True, height="stretch"):
        st.markdown("**Upload / 上传**")
        st.write("PDF, JPG, JPEG, and PNG documents.")
    with capabilities[1].container(border=True, height="stretch"):
        st.markdown("**Extract / 提取**")
        st.write("Preserve page text, tables, and key fields.")
    with capabilities[2].container(border=True, height="stretch"):
        st.markdown("**Classify / 分类**")
        st.write("Authorization, CCC certification, or other.")

    st.subheader("Getting started / 开始使用")
    st.markdown(
        "1. Select **CCC verification / CCC 核验** from the menu.\n"
        "2. Upload one PDF or image.\n"
        "3. Click **Start / 开始解析** to run the pipeline.\n"
        "4. Review or download the extracted content."
    )


def render_upload_preview(uploaded_file: Any) -> None:
    suffix = Path(uploaded_file.name).suffix.lower()
    st.subheader("Selected document / 已选文档")
    # Bound the viewport so tall source files scroll instead of growing the page.
    with st.container(border=True, height=520):
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
    category = str(result.doc_category)
    category_color = {
        "Authorization Document": "blue",
        "CCC Certification Document": "green",
        "Other": "gray",
    }.get(category, "gray")

    with st.container(border=True):
        st.caption("DOCUMENT METADATA / 文件元数据")
        name_column, type_column, category_column = st.columns([2, 1, 2])
        with name_column:
            st.caption(":material/description: File name / 文件名")
            st.markdown(f"**{result.file_name}**")
        with type_column:
            st.caption(":material/draft: File type / 文件类型")
            st.badge(result.file_type.upper(), color="gray")
        with category_column:
            st.caption(":material/category: Category / 文档类别")
            st.badge(
                category,
                icon=":material/verified:",
                color=category_color,
            )

    if result.category_reasoning:
        with st.container(border=True):
            st.markdown("**:material/fact_check: Classification reasoning / 分类依据**")
            st.write(result.category_reasoning)

    content_key = hashlib.sha256(result.full_content.encode("utf-8")).hexdigest()[:12]
    with st.expander("Full content / 完整内容", expanded=False):
        st.caption(
            "The fixed-height viewer scrolls vertically. / 固定高度区域支持垂直滚动。"
        )
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


def render_tampering_report(report: TamperingReport) -> None:
    st.subheader("Tampering-risk checkpoint / 篡改风险检查")
    status_color = {
        "No Obvious Indicators": "green",
        "Review Required": "orange",
        "Inconclusive": "gray",
    }.get(str(report.status), "gray")
    risk_color = {
        "Low": "green",
        "Medium": "orange",
        "High": "red",
        "Inconclusive": "gray",
    }.get(str(report.risk_level), "gray")

    with st.container(border=True):
        columns = st.columns([2, 1, 1])
        with columns[0]:
            st.caption(":material/checklist: Check / 检查项")
            st.markdown(f"**{report.check_type}**")
        with columns[1]:
            st.caption(":material/task_alt: Status / 状态")
            st.badge(str(report.status), color=status_color)
        with columns[2]:
            st.caption(":material/warning: Risk / 风险")
            st.badge(str(report.risk_level), color=risk_color)

        st.markdown("**Summary / 摘要**")
        st.write(report.summary)

    st.markdown("**Findings / 发现**")
    if report.findings:
        for index, finding in enumerate(report.findings, start=1):
            with st.container(border=True):
                heading, severity = st.columns([4, 1])
                heading.markdown(
                    f"**{index}. Page {finding.page_number} — {finding.location}**"
                )
                severity.badge(
                    str(finding.severity),
                    color={
                        "Low": "gray",
                        "Medium": "orange",
                        "High": "red",
                    }.get(str(finding.severity), "gray"),
                )
                st.write(finding.observation)
    else:
        st.caption(
            "No specific visual tampering indicators were reported. / "
            "未报告具体的视觉篡改迹象。"
        )

    st.warning(
        f"Limitations / 局限性: {report.limitations}",
        icon=":material/info:",
    )
