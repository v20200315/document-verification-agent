from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from sandbox.src.schemas import (
    CertificateFieldName,
    DocumentCategory,
    DocumentResult,
    InfoCheckStatus,
    InfoComparisonItem,
    InfoComparisonOutcome,
    InfoComparisonReport,
    TamperingReport,
    TamperingRisk,
    TamperingStatus,
)


def _image_bytes(image_format: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format=image_format)
    return buffer.getvalue()


def test_info_check_requires_evidence_and_explicit_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    document_result = DocumentResult(
        file_name="certificate.jpg",
        file_type="image",
        doc_category=DocumentCategory.CCC_CERTIFICATION,
        full_content="证书编号：2025010703748148",
    )
    comparison_report = InfoComparisonReport(
        status=InfoCheckStatus.ALL_MATCHED,
        comparisons=[
            InfoComparisonItem(
                field_name=CertificateFieldName.CERTIFICATE_NUMBER,
                source_value="2025010703748148",
                cnca_value="2025010703748148",
                outcome=InfoComparisonOutcome.MATCH,
                explanation="证书编号一致。",
            )
        ],
        summary="已完成信息比对。",
        limitations="仅比较用户上传的截图。",
        evidence_image_count=2,
    )
    tampering_report = TamperingReport(
        status=TamperingStatus.NO_OBVIOUS_INDICATORS,
        risk_level=TamperingRisk.LOW,
        suspected_tampering=False,
        summary="未发现明显篡改迹象。",
        limitations="不能作为真实性证明。",
        pages_analyzed=1,
    )

    with (
        patch(
            "sandbox.app.pipeline_service.process_uploaded_document",
            return_value=document_result,
        ),
        patch(
            "sandbox.app.pipeline_service.analyze_uploaded_document",
            return_value=tampering_report,
        ) as tampering_mock,
        patch(
            "sandbox.app.pipeline_service.check_uploaded_information",
            return_value=comparison_report,
        ) as check_mock,
    ):
        page_path = (
            Path(__file__).parents[1] / "app" / "app_pages" / "ccc_verification.py"
        )
        app = AppTest.from_file(page_path).run(timeout=10)
        app.file_uploader[0].upload(
            "certificate.jpg",
            _image_bytes("JPEG"),
            "image/jpeg",
        ).run(timeout=10)
        next(
            button for button in app.button if button.label.startswith("Start")
        ).click().run(timeout=10)

        assert len(app.file_uploader) == 1
        assert check_mock.call_count == 0
        assert not any(button.label.startswith("Check info") for button in app.button)
        next(
            button
            for button in app.button
            if button.label.startswith("Analyze tampering")
        ).click().run(timeout=10)

        assert tampering_mock.call_count == 1
        next(
            button for button in app.button if button.label.startswith("Check info")
        ).click().run(timeout=10)

        assert any(code.value == "2025010703748148" for code in app.code)
        assert app.get("link_button")
        evidence_uploader = next(
            uploader
            for uploader in app.file_uploader
            if uploader.label == "CNCA 查询结果截图"
        )
        evidence_uploader.set_value(
            [
                ("result-1.png", _image_bytes(), "image/png"),
                ("result-2.png", _image_bytes(), "image/png"),
            ]
        ).run(timeout=10)

        assert check_mock.call_count == 0
        next(
            button for button in app.button if button.label == "Analyze / 开始比对"
        ).click().run(timeout=10)

        assert not app.exception
        assert check_mock.call_count == 1
        assert any(heading.value == "CNCA 信息比对报告" for heading in app.subheader)
