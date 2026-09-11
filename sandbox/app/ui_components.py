from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import streamlit as st
from sandbox.src.info_checker import extract_certificate_number
from sandbox.src.schemas import (
    DocumentResult,
    InfoComparisonReport,
    TamperingReport,
)

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
    st.subheader("篡改风险检查报告")
    status_color = {
        "No Obvious Indicators": "green",
        "Review Required": "orange",
        "Inconclusive": "gray",
    }.get(str(report.status), "gray")
    status_text = {
        "No Obvious Indicators": "未发现明显篡改迹象",
        "Review Required": "需要人工复核",
        "Inconclusive": "无法确定",
    }.get(str(report.status), "无法确定")
    risk_color = {
        "Low": "green",
        "Medium": "orange",
        "High": "red",
        "Inconclusive": "gray",
    }.get(str(report.risk_level), "gray")
    risk_text = {
        "Low": "低",
        "Medium": "中",
        "High": "高",
        "Inconclusive": "无法确定",
    }.get(str(report.risk_level), "无法确定")

    with st.container(border=True):
        columns = st.columns([2, 1, 1])
        with columns[0]:
            st.caption(":material/checklist: 检查项")
            st.markdown("**视觉篡改分析**")
        with columns[1]:
            st.caption(":material/task_alt: 状态")
            st.badge(status_text, color=status_color)
        with columns[2]:
            st.caption(":material/warning: 风险等级")
            st.badge(risk_text, color=risk_color)

        st.markdown("**分析摘要**")
        st.write(report.summary)

    st.markdown("**风险发现**")
    if report.findings:
        for index, finding in enumerate(report.findings, start=1):
            with st.container(border=True):
                heading, severity = st.columns([4, 1])
                heading.markdown(
                    f"**{index}. 第 {finding.page_number} 页 — {finding.location}**"
                )
                severity.badge(
                    {
                        "Low": "低",
                        "Medium": "中",
                        "High": "高",
                    }.get(str(finding.severity), "未知"),
                    color={
                        "Low": "gray",
                        "Medium": "orange",
                        "High": "red",
                    }.get(str(finding.severity), "gray"),
                )
                st.write(finding.observation)
    else:
        st.caption("未报告具体的视觉篡改迹象。")

    st.warning(
        f"局限性：{report.limitations}",
        icon=":material/info:",
    )


def render_info_comparison_report(report: InfoComparisonReport) -> None:
    st.subheader("CNCA 信息比对报告")
    status = str(report.status)
    status_text = {
        "All Matched": "全部一致",
        "Mismatch Found": "发现不一致",
        "Inconclusive": "无法完整判断",
    }.get(status, "无法完整判断")
    status_color = {
        "All Matched": "green",
        "Mismatch Found": "red",
        "Inconclusive": "orange",
    }.get(status, "gray")

    with st.container(border=True):
        summary_column, status_column, image_column = st.columns([3, 1, 1])
        with summary_column:
            st.caption(":material/summarize: 比对摘要")
            st.write(report.summary)
        with status_column:
            st.caption(":material/fact_check: 总体结果")
            st.badge(status_text, color=status_color)
        with image_column:
            st.caption(":material/imagesmode: 证据截图")
            st.markdown(f"**{report.evidence_image_count} 张**")

    field_labels = {
        "Certificate number": "证书编号",
        "Certificate status": "证书状态",
        "Certificate holder": "证书持有人",
        "Manufacturer": "制造商",
        "Production factory": "生产厂",
        "Product name": "产品名称",
        "Models and specifications": "型号与规格",
        "Applicable standards": "适用标准",
        "Issuing certification body": "发证机构",
        "Issue date": "发证日期",
        "Valid until": "有效期至",
    }
    outcome_labels = {
        "Match": "一致",
        "Mismatch": "不一致",
        "Missing from certificate": "证书中缺失",
        "Missing from CNCA evidence": "CNCA 截图中缺失",
        "Inconclusive": "无法判断",
    }
    outcome_colors = {
        "Match": "green",
        "Mismatch": "red",
        "Missing from certificate": "orange",
        "Missing from CNCA evidence": "orange",
        "Inconclusive": "gray",
    }

    st.markdown("**逐项比对**")
    for item in report.comparisons:
        outcome = str(item.outcome)
        with st.container(border=True):
            field_column, outcome_column = st.columns([4, 1])
            field_column.markdown(
                f"**{field_labels.get(str(item.field_name), str(item.field_name))}**"
            )
            outcome_column.badge(
                outcome_labels.get(outcome, "无法判断"),
                color=outcome_colors.get(outcome, "gray"),
            )
            source_column, cnca_column = st.columns(2)
            source_column.caption("CCC 文件内容")
            source_column.write(item.source_value or "未提取到")
            cnca_column.caption("CNCA 截图内容")
            cnca_column.write(item.cnca_value or "未提取到")
            st.caption(f"说明：{item.explanation}")

    st.warning(
        f"局限性：{report.limitations}",
        icon=":material/info:",
    )


def render_certificate_number(result: DocumentResult) -> None:
    certificate_number = extract_certificate_number(result.full_content)
    with st.container(border=True):
        st.caption(":material/badge: Certificate Number / 证书编号")
        if certificate_number:
            st.code(certificate_number, language=None)
        else:
            st.warning(
                "未能从 CCC 文件中识别证书编号，请查看完整提取内容并手动核对。",
                icon=":material/warning:",
            )
