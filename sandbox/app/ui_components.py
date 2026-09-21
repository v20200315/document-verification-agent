from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
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
        st.markdown("**:material/data_object: Certificate JSON / 证书 JSON**")
        if processed.processing_error:
            st.warning(
                f"Extraction failed / 解析失败: {processed.processing_error}",
                icon=":material/warning:",
            )
        certificate = processed.certificate or CccCertificateFields()
        st.json(certificate.model_dump())

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


def _is_http_url(payload: str) -> bool:
    lowered = payload.strip().lower()
    return lowered.startswith(("http://", "https://"))

