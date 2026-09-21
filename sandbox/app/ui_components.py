from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
from sandbox.src.certificate_fields import format_certificate_fields_plain_text
from sandbox.src.cqc_web import format_cqc_page_plain_text
from sandbox.src.schemas import CccCertificateFields, ProcessedDocument

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


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


def render_processed_document(processed: ProcessedDocument) -> None:
    st.subheader("Extraction result / 解析结果")

    with st.container(border=True):
        st.markdown("**:material/description: Certificate text / 证书文本**")
        if processed.processing_error:
            st.warning(
                f"Extraction failed / 解析失败: {processed.processing_error}",
                icon=":material/warning:",
            )
        certificate = processed.certificate or CccCertificateFields()
        st.code(
            format_certificate_fields_plain_text(certificate),
            language=None,
        )

    with st.container(border=True):
        st.markdown("**:material/qr_code: CQC QR URL / 二维码链接**")
        if not processed.qr_payloads:
            st.info("No QR code was found. / 未识别到二维码。")
        else:
            for index, payload in enumerate(processed.qr_payloads):
                if _is_http_url(payload):
                    st.link_button(
                        payload,
                        payload,
                        icon=":material/open_in_new:",
                        key=f"cqc_qr_{processed.file_md5}_{index}",
                    )
                else:
                    st.code(payload, language=None)

    with st.container(border=True):
        st.markdown("**:material/fingerprint: File MD5 / 文件 MD5**")
        st.code(processed.file_md5, language=None)

    with st.container(border=True):
        st.markdown("**:material/language: CQC website data / 官网数据**")
        if not _has_cqc_url(processed.qr_payloads):
            st.info(
                "No CQC website URL was found in the QR code. / "
                "二维码中未识别到 CQC 官网链接。"
            )
        elif processed.cqc_source_url:
            st.caption(f"Fetched from / 抓取来源: `{processed.cqc_source_url}`")
        if processed.cqc_fetch_error:
            st.warning(
                f"CQC website fetch failed / 官网抓取失败: {processed.cqc_fetch_error}",
                icon=":material/warning:",
            )
        st.markdown("**Old version info / 旧版信息**")
        st.caption(
            "Full content captured from the CQC HTML page. / "
            "官网 HTML 抓取全文。"
        )
        st.code(
            format_cqc_page_plain_text(processed.cqc_page_fields),
            language=None,
        )
        st.markdown("**Current version info / 现行版信息**")
        st.caption(
            "Normalized certificate fields mapped from the page. / "
            "官网页面映射后的结构化证书字段。"
        )
        certificate = processed.cqc_certificate or CccCertificateFields()
        st.code(
            format_certificate_fields_plain_text(certificate),
            language=None,
        )


def _is_http_url(payload: str) -> bool:
    lowered = payload.strip().lower()
    return lowered.startswith(("http://", "https://"))


def _has_cqc_url(qr_payloads: list[str]) -> bool:
    for payload in qr_payloads:
        lowered = payload.strip().lower()
        if _is_http_url(payload) and (
            "cqc.com.cn" in lowered or "cqccms.com.cn" in lowered
        ):
            return True
    return False

