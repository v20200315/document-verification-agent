from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.app.image_pdf_to_text.backend import ImagePDFConversionError
from sandbox.app.image_pdf_to_text.service import (
    convert_uploaded_pdf,
    is_api_configured,
)

# The uploader generation replaces the widget after an explicit reset.
st.session_state.setdefault("image_pdf_uploader_generation", 0)
# Result state belongs to exactly one upload fingerprint.
st.session_state.setdefault("image_pdf_active_fingerprint", None)
st.session_state.setdefault("image_pdf_conversion_result", None)
st.session_state.setdefault("image_pdf_conversion_error", None)


def reset_conversion() -> None:
    current_key = f"image_pdf_upload_{st.session_state.image_pdf_uploader_generation}"
    st.session_state.pop(current_key, None)
    st.session_state.image_pdf_uploader_generation += 1
    st.session_state.image_pdf_active_fingerprint = None
    st.session_state.image_pdf_conversion_result = None
    st.session_state.image_pdf_conversion_error = None


st.title("Image PDF to Text PDF")
st.caption(
    "Use Qwen-VL to transcribe every image page and create a selectable, "
    "searchable text PDF. / 将图片型 PDF 转换为可选择、可搜索的文本 PDF。"
)

api_ready = is_api_configured()
if not api_ready:
    st.error(
        "DASHSCOPE_API_KEY is not configured. Conversion is disabled. / "
        "未配置 DASHSCOPE_API_KEY，暂时无法转换。"
    )

uploader_key = f"image_pdf_upload_{st.session_state.image_pdf_uploader_generation}"
uploaded_file = st.file_uploader(
    "Image-based PDF / 图片型 PDF",
    type=["pdf"],
    accept_multiple_files=False,
    help="Maximum application upload size: 50 MB.",
    key=uploader_key,
)

if uploaded_file is None:
    if st.session_state.image_pdf_active_fingerprint is not None:
        st.session_state.image_pdf_active_fingerprint = None
        st.session_state.image_pdf_conversion_result = None
        st.session_state.image_pdf_conversion_error = None
    st.info(
        "Choose one image-based PDF. OCR starts only after you click Convert. / "
        "请选择一个图片型 PDF，点击转换后才会调用 OCR。"
    )
else:
    uploaded_bytes = uploaded_file.getvalue()
    fingerprint = hashlib.sha256(
        uploaded_file.name.encode("utf-8") + b"\0" + uploaded_bytes
    ).hexdigest()
    if fingerprint != st.session_state.image_pdf_active_fingerprint:
        st.session_state.image_pdf_active_fingerprint = fingerprint
        st.session_state.image_pdf_conversion_result = None
        st.session_state.image_pdf_conversion_error = None

    with st.container(border=True):
        name_column, size_column = st.columns([3, 1])
        name_column.caption(":material/picture_as_pdf: Source file / 原始文件")
        name_column.markdown(f"**{uploaded_file.name}**")
        size_column.caption(":material/data_usage: Size / 大小")
        size_column.markdown(f"**{len(uploaded_bytes) / (1024 * 1024):.2f} MB**")

    with st.container(horizontal=True):
        convert_clicked = st.button(
            "Convert / 开始转换",
            type="primary",
            icon=":material/document_scanner:",
            disabled=not api_ready,
            key=f"convert_image_pdf_{fingerprint}",
        )
        st.button(
            "New PDF / 新文件",
            icon=":material/refresh:",
            on_click=reset_conversion,
            key="reset_image_pdf_conversion",
        )

    if convert_clicked:
        st.session_state.image_pdf_conversion_result = None
        st.session_state.image_pdf_conversion_error = None
        try:
            with st.spinner(
                "Rendering pages, running OCR, and generating PDF… / "
                "正在渲染页面、识别文字并生成 PDF…",
                show_time=True,
            ):
                st.session_state.image_pdf_conversion_result = convert_uploaded_pdf(
                    uploaded_file.name,
                    uploaded_bytes,
                )
        except ImagePDFConversionError as exc:
            st.session_state.image_pdf_conversion_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            st.session_state.image_pdf_conversion_error = (
                f"{exc.__class__.__name__}: {exc}"
            )

    if st.session_state.image_pdf_conversion_error:
        st.error(
            "Conversion failed / 转换失败: "
            f"{st.session_state.image_pdf_conversion_error}"
        )

    result = st.session_state.image_pdf_conversion_result
    if result is not None:
        st.subheader("Conversion result / 转换结果")
        result_columns = st.columns(2)
        result_columns[0].metric("Source pages / 原始页数", result.page_count)
        result_columns[1].metric(
            "Output / 输出文件",
            result.output_file_name,
        )

        with st.expander("OCR text / 识别文本", expanded=False):
            st.caption(
                "The fixed-height viewer scrolls vertically. / "
                "固定高度区域支持垂直滚动。"
            )
            st.text_area(
                "Extracted text / 提取文本",
                value=result.full_text,
                height=420,
                disabled=True,
                key=f"image_pdf_text_{fingerprint}",
            )

        st.download_button(
            "Download text PDF / 下载文本 PDF",
            data=result.pdf_data,
            file_name=result.output_file_name,
            mime="application/pdf",
            icon=":material/download:",
            type="primary",
            key=f"download_text_pdf_{fingerprint}",
        )
