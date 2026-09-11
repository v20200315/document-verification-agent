from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.app.pipeline_service import (
    analyze_uploaded_document,
    check_uploaded_information,
    is_api_configured,
    process_uploaded_document,
)
from sandbox.app.ui_components import (
    render_certificate_number,
    render_info_comparison_report,
    render_result,
    render_tampering_report,
    render_upload_preview,
)
from sandbox.src.errors import DocumentPipelineError

# The generation gives the uploader a fresh identity after a reset.
st.session_state.setdefault("document_uploader_generation", 0)
# The fingerprint invalidates stale output when the selected file changes.
st.session_state.setdefault("active_upload_fingerprint", None)
# Result and error persist while navigating, but reset for each new document.
st.session_state.setdefault("latest_document_result", None)
st.session_state.setdefault("latest_processing_error", None)
# Tampering is an optional second call tied to the active upload fingerprint.
st.session_state.setdefault("latest_tampering_report", None)
st.session_state.setdefault("latest_tampering_error", None)
# CNCA screenshot evidence and its report live only for the active CCC file.
st.session_state.setdefault("show_info_check", False)
st.session_state.setdefault("evidence_uploader_generation", 0)
st.session_state.setdefault("active_evidence_fingerprint", None)
st.session_state.setdefault("latest_info_check_report", None)
st.session_state.setdefault("latest_info_check_error", None)


def clear_info_check() -> None:
    st.session_state.show_info_check = False
    st.session_state.evidence_uploader_generation += 1
    st.session_state.active_evidence_fingerprint = None
    st.session_state.latest_info_check_report = None
    st.session_state.latest_info_check_error = None


def reset_document() -> None:
    current_key = f"document_upload_{st.session_state.document_uploader_generation}"
    st.session_state.pop(current_key, None)
    st.session_state.document_uploader_generation += 1
    st.session_state.active_upload_fingerprint = None
    st.session_state.latest_document_result = None
    st.session_state.latest_processing_error = None
    st.session_state.latest_tampering_report = None
    st.session_state.latest_tampering_error = None
    clear_info_check()


st.title("CCC document verification / CCC 文档核验")
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
        st.session_state.latest_tampering_report = None
        st.session_state.latest_tampering_error = None
        clear_info_check()
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
        st.session_state.latest_tampering_report = None
        st.session_state.latest_tampering_error = None
        clear_info_check()

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
        st.session_state.latest_tampering_report = None
        st.session_state.latest_tampering_error = None
        clear_info_check()
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
        st.subheader("Authenticity checks / 真伪核验检查")
        st.caption(
            "Visual tampering analysis is one independent checkpoint; "
            "it does not confirm authenticity. / "
            "视觉篡改分析只是独立检查项之一，并不能确认文件真伪。"
        )
        analyze_clicked = st.button(
            "Analyze tampering risk / 检测篡改风险",
            icon=":material/image_search:",
            type="primary",
            key=f"analyze_tampering_{upload_fingerprint}",
        )

        if analyze_clicked:
            st.session_state.latest_tampering_report = None
            st.session_state.latest_tampering_error = None
            clear_info_check()
            try:
                with st.spinner(
                    "Analyzing original document pixels… / 正在分析原始文档像素…",
                    show_time=True,
                ):
                    st.session_state.latest_tampering_report = (
                        analyze_uploaded_document(
                            uploaded_file.name,
                            uploaded_bytes,
                        )
                    )
            except DocumentPipelineError as exc:
                st.session_state.latest_tampering_error = str(exc)
            except Exception as exc:  # noqa: BLE001
                st.session_state.latest_tampering_error = (
                    f"{exc.__class__.__name__}: {exc}"
                )

        if st.session_state.latest_tampering_error:
            st.error(
                "Tampering analysis failed / 篡改分析失败: "
                f"{st.session_state.latest_tampering_error}"
            )

        if st.session_state.latest_tampering_report is not None:
            render_tampering_report(st.session_state.latest_tampering_report)
            info_check_clicked = st.button(
                "Check info / 信息比对",
                icon=":material/compare:",
                key=f"show_info_check_{upload_fingerprint}",
            )

            if info_check_clicked:
                st.session_state.show_info_check = True

            if st.session_state.show_info_check:
                st.subheader("上传 CNCA 查询结果截图")
                render_certificate_number(st.session_state.latest_document_result)
                st.caption(
                    "可上传 1–10 张 JPG 或 PNG 截图；系统不会在上传后自动调用模型。"
                )
                st.link_button(
                    "打开 CNCA 证书查询网站",
                    "https://cx.cnca.cn/CertECloud/result/skipResultList",
                    icon=":material/open_in_new:",
                )
                evidence_key = (
                    f"cnca_evidence_{upload_fingerprint}_"
                    f"{st.session_state.evidence_uploader_generation}"
                )
                evidence_files = st.file_uploader(
                    "CNCA 查询结果截图",
                    type=["jpg", "jpeg", "png"],
                    accept_multiple_files=True,
                    key=evidence_key,
                )
                evidence_uploads = [
                    (file.name, file.getvalue()) for file in evidence_files
                ]

                if evidence_uploads:
                    evidence_digest = hashlib.sha256()
                    for file_name, data in evidence_uploads:
                        evidence_digest.update(file_name.encode("utf-8"))
                        evidence_digest.update(b"\0")
                        evidence_digest.update(data)
                    evidence_fingerprint = evidence_digest.hexdigest()
                    if (
                        evidence_fingerprint
                        != st.session_state.active_evidence_fingerprint
                    ):
                        st.session_state.active_evidence_fingerprint = (
                            evidence_fingerprint
                        )
                        st.session_state.latest_info_check_report = None
                        st.session_state.latest_info_check_error = None
                    st.caption(f"已选择 {len(evidence_uploads)} 张截图。")
                    if len(evidence_uploads) > 10:
                        st.error("最多只能上传 10 张 CNCA 截图。")
                else:
                    st.session_state.active_evidence_fingerprint = None
                    st.session_state.latest_info_check_report = None
                    st.session_state.latest_info_check_error = None
                    evidence_fingerprint = "empty"

                evidence_count_valid = 1 <= len(evidence_uploads) <= 10
                run_info_check = st.button(
                    "Analyze / 开始比对",
                    type="primary",
                    icon=":material/manage_search:",
                    disabled=not evidence_count_valid or not api_ready,
                    key=(f"run_info_check_{upload_fingerprint}_{evidence_fingerprint}"),
                )

                if run_info_check:
                    st.session_state.latest_info_check_report = None
                    st.session_state.latest_info_check_error = None
                    try:
                        with st.spinner(
                            "正在提取 CNCA 截图信息并与 CCC 文件比对…",
                            show_time=True,
                        ):
                            st.session_state.latest_info_check_report = (
                                check_uploaded_information(
                                    st.session_state.latest_document_result,
                                    evidence_uploads,
                                )
                            )
                    except DocumentPipelineError as exc:
                        st.session_state.latest_info_check_error = str(exc)
                    except Exception as exc:  # noqa: BLE001
                        st.session_state.latest_info_check_error = (
                            f"{exc.__class__.__name__}: {exc}"
                        )

                if st.session_state.latest_info_check_error:
                    st.error(
                        f"信息比对失败：{st.session_state.latest_info_check_error}"
                    )

                if st.session_state.latest_info_check_report is not None:
                    render_info_comparison_report(
                        st.session_state.latest_info_check_report
                    )
