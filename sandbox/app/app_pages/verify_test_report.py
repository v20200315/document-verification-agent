from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.app.verify_test_report.backend import ProductCategory, TestReportError
from sandbox.app.verify_test_report.service import (
    classify_uploaded_pdf,
    is_api_configured,
)

CATEGORY_BADGE_COLORS = {
    ProductCategory.HEAT_FAN: "blue",
    ProductCategory.HEAT_PUMP_CHILLER: "green",
    ProductCategory.STORAGE_HEATER: "orange",
    ProductCategory.GAS_BOILER: "red",
    ProductCategory.OTHER: "gray",
}

# The uploader generation replaces the widget after an explicit reset.
st.session_state.setdefault("test_report_uploader_generation", 0)
# Result state belongs to exactly one upload fingerprint.
st.session_state.setdefault("test_report_active_fingerprint", None)
st.session_state.setdefault("test_report_result", None)
st.session_state.setdefault("test_report_error", None)


def reset_classification() -> None:
    current_key = (
        f"test_report_upload_{st.session_state.test_report_uploader_generation}"
    )
    st.session_state.pop(current_key, None)
    st.session_state.test_report_uploader_generation += 1
    st.session_state.test_report_active_fingerprint = None
    st.session_state.test_report_result = None
    st.session_state.test_report_error = None


st.title("Verify Test Report")
st.caption(
    "Upload one text-based test-report PDF and classify its product category. / "
    "上传一份文本型检测报告 PDF，识别产品类别。"
)

api_ready = is_api_configured()
if not api_ready:
    st.error(
        "DASHSCOPE_API_KEY is not configured. Classification is disabled. / "
        "未配置 DASHSCOPE_API_KEY，暂时无法分类。"
    )

uploader_key = f"test_report_upload_{st.session_state.test_report_uploader_generation}"
uploaded_file = st.file_uploader(
    "Text-based test report PDF / 文本型检测报告 PDF",
    type=["pdf"],
    accept_multiple_files=False,
    help="Maximum application upload size: 50 MB.",
    key=uploader_key,
)

if uploaded_file is None:
    if st.session_state.test_report_active_fingerprint is not None:
        st.session_state.test_report_active_fingerprint = None
        st.session_state.test_report_result = None
        st.session_state.test_report_error = None
    st.info(
        "Choose one searchable PDF. Classification starts only after you click "
        "Classify. Image-only files should first be converted on Image PDF to "
        "Text PDF. / 请选择一个可选择文字的 PDF，点击开始分类后才会调用模型。"
        "图片型 PDF 请先转换为文本 PDF。"
    )
else:
    uploaded_bytes = uploaded_file.getvalue()
    fingerprint = hashlib.sha256(
        uploaded_file.name.encode("utf-8") + b"\0" + uploaded_bytes
    ).hexdigest()
    if fingerprint != st.session_state.test_report_active_fingerprint:
        st.session_state.test_report_active_fingerprint = fingerprint
        st.session_state.test_report_result = None
        st.session_state.test_report_error = None

    with st.container(border=True):
        name_column, size_column = st.columns([3, 1])
        name_column.caption(":material/picture_as_pdf: Source file / 原始文件")
        name_column.markdown(f"**{uploaded_file.name}**")
        size_column.caption(":material/data_usage: Size / 大小")
        size_column.markdown(f"**{len(uploaded_bytes) / (1024 * 1024):.2f} MB**")

    with st.container(horizontal=True):
        classify_clicked = st.button(
            "Classify / 开始分类",
            type="primary",
            icon=":material/category:",
            disabled=not api_ready,
            key=f"classify_test_report_{fingerprint}",
        )
        st.button(
            "New PDF / 新文件",
            icon=":material/refresh:",
            on_click=reset_classification,
            key="reset_test_report_classification",
        )

    if classify_clicked:
        st.session_state.test_report_result = None
        st.session_state.test_report_error = None
        try:
            with st.spinner(
                "Extracting selectable text and classifying the product… / "
                "正在提取文本并识别产品类别…",
                show_time=True,
            ):
                st.session_state.test_report_result = classify_uploaded_pdf(
                    uploaded_file.name,
                    uploaded_bytes,
                )
        except TestReportError as exc:
            st.session_state.test_report_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            st.session_state.test_report_error = f"{exc.__class__.__name__}: {exc}"

    if st.session_state.test_report_error:
        st.error(
            f"Classification failed / 分类失败: {st.session_state.test_report_error}"
        )

    result = st.session_state.test_report_result
    if result is not None:
        st.subheader("Classification result / 分类结果")
        with st.container(border=True):
            name_column, pages_column, category_column = st.columns([2, 1, 2])
            with name_column:
                st.caption(":material/description: File name / 文件名")
                st.markdown(f"**{result.file_name}**")
            with pages_column:
                st.caption(":material/layers: Pages / 页数")
                st.markdown(f"**{result.page_count}**")
            with category_column:
                st.caption(":material/category: Product category / 产品类别")
                st.badge(
                    result.product_category.value,
                    icon=":material/verified:",
                    color=CATEGORY_BADGE_COLORS.get(
                        result.product_category,
                        "gray",
                    ),
                )
            if result.category_confidence is not None:
                st.metric(
                    "Confidence / 置信度",
                    f"{result.category_confidence:.0%}",
                )

        with st.container(border=True):
            st.markdown("**:material/fact_check: Classification reasoning / 分类依据**")
            st.write(result.category_reasoning)

        with st.expander("Extracted text / 提取文本", expanded=False):
            st.caption(
                "The fixed-height viewer scrolls vertically. / "
                "固定高度区域支持垂直滚动。"
            )
            st.text_area(
                "Extracted text / 提取文本",
                value=result.full_content,
                height=420,
                disabled=True,
                key=f"test_report_text_{fingerprint}",
            )
