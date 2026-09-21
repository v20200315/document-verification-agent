from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from sandbox.src.errors import DocumentLoadError
from sandbox.src.schemas import (
    CccCertificateFields,
    DocumentCategory,
    DocumentResult,
    ProcessedDocument,
)

MD5_DIGEST = "0123456789abcdef0123456789abcdef"
CQC_URL = "https://www.cqc.com.cn/www/english/"


def _jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def _processed_document() -> ProcessedDocument:
    return ProcessedDocument(
        file_md5=MD5_DIGEST,
        qr_payloads=[CQC_URL],
        certificate=CccCertificateFields(
            manufacturer=(
                "浙江德富新能源技术有限公司\n乐清市乐清湾港区乐商创业园创新路7号"
            ),
            product_name="低环境温度变频式空气源热泵（冷水）机组",
            models_and_specifications="DF-CTS064 I /04 220V～ 50Hz R410A",
            applicable_standards=(
                "GB 17625.1–2022；GB 4343.1–2018；GB 4706.1–2005 ；GB 4706.32–2012"
            ),
            issuing_certification_body="中国质量认证中心",
            issue_date="2024 年 07 月 19 日",
            valid_until="2029 年 07 月 18 日",
        ),
        document=DocumentResult(
            file_name="certificate.jpg",
            file_type="image",
            doc_category=DocumentCategory.CCC_CERTIFICATION,
            full_content="Certificate content",
        ),
    )


def test_start_shows_json_qr_and_md5_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    processed = _processed_document()

    with patch(
        "sandbox.app.pipeline_service.process_uploaded_document",
        return_value=processed,
    ) as process_mock:
        page_path = (
            Path(__file__).parents[1] / "app" / "app_pages" / "ccc_verification.py"
        )
        app = AppTest.from_file(page_path).run(timeout=10)
        app.file_uploader[0].upload(
            "certificate.jpg",
            _jpeg_bytes(),
            "image/jpeg",
        ).run(timeout=10)

        assert process_mock.call_count == 0
        next(
            button for button in app.button if button.label.startswith("Start")
        ).click().run(timeout=10)

        assert not app.exception
        assert process_mock.call_count == 1
        markdown_values = [item.value for item in app.markdown]
        assert any("Certificate JSON" in value for value in markdown_values)
        assert any("CQC QR URL" in value for value in markdown_values)
        assert any("File MD5" in value for value in markdown_values)
        json_payloads = [json.loads(item.value) for item in app.json]
        assert any(
            payload.get("product_name") == "低环境温度变频式空气源热泵（冷水）机组"
            for payload in json_payloads
        )
        assert any(code.value == MD5_DIGEST for code in app.code)
        link_labels = [button.label for button in app.get("link_button")]
        assert CQC_URL in link_labels
        assert not any(
            button.label.startswith("Analyze tampering") for button in app.button
        )
        assert not any(button.label.startswith("Check info") for button in app.button)
        assert not any(
            heading.value == "Authenticity checks / 真伪核验检查"
            for heading in app.subheader
        )


def test_qr_and_md5_sections_remain_when_extraction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    processed = ProcessedDocument(
        file_md5=MD5_DIGEST,
        qr_payloads=[CQC_URL],
        processing_error="Qwen extraction failed",
    )

    with patch(
        "sandbox.app.pipeline_service.process_uploaded_document",
        return_value=processed,
    ):
        page_path = (
            Path(__file__).parents[1] / "app" / "app_pages" / "ccc_verification.py"
        )
        app = AppTest.from_file(page_path).run(timeout=10)
        app.file_uploader[0].upload(
            "certificate.jpg",
            _jpeg_bytes(),
            "image/jpeg",
        ).run(timeout=10)
        next(
            button for button in app.button if button.label.startswith("Start")
        ).click().run(timeout=10)

        assert not app.exception
        assert any(code.value == MD5_DIGEST for code in app.code)
        assert CQC_URL in [button.label for button in app.get("link_button")]
        assert not any(
            button.label.startswith("Analyze tampering") for button in app.button
        )
        assert app.warning


def test_empty_upload_still_shows_processing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    with patch(
        "sandbox.app.pipeline_service.process_uploaded_document",
        side_effect=DocumentLoadError("The uploaded file is empty."),
    ):
        page_path = (
            Path(__file__).parents[1] / "app" / "app_pages" / "ccc_verification.py"
        )
        app = AppTest.from_file(page_path).run(timeout=10)
        app.file_uploader[0].upload(
            "certificate.jpg",
            _jpeg_bytes(),
            "image/jpeg",
        ).run(timeout=10)
        next(
            button for button in app.button if button.label.startswith("Start")
        ).click().run(timeout=10)

        assert not app.exception
        assert app.error
        assert "empty" in app.error[0].value
