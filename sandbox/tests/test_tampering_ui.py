from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from sandbox.src.schemas import (
    DocumentCategory,
    DocumentResult,
    TamperingReport,
    TamperingRisk,
    TamperingStatus,
)


def _jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_tampering_checkpoint_requires_explicit_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    document_result = DocumentResult(
        file_name="certificate.jpg",
        file_type="image",
        doc_category=DocumentCategory.CCC_CERTIFICATION,
        full_content="Certificate content",
    )
    tampering_report = TamperingReport(
        status=TamperingStatus.NO_OBVIOUS_INDICATORS,
        risk_level=TamperingRisk.LOW,
        suspected_tampering=False,
        summary="No visible indicators were identified.",
        limitations="This is not proof of authenticity.",
        pages_analyzed=1,
    )

    with (
        patch(
            "sandbox.app.pipeline_service.process_uploaded_document",
            return_value=document_result,
        ) as process_mock,
        patch(
            "sandbox.app.pipeline_service.analyze_uploaded_document",
            return_value=tampering_report,
        ) as tampering_mock,
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

        assert tampering_mock.call_count == 0
        next(
            button for button in app.button if button.label.startswith("Start")
        ).click().run(timeout=10)

        assert process_mock.call_count == 1
        assert tampering_mock.call_count == 0
        next(
            button
            for button in app.button
            if button.label.startswith("Analyze tampering")
        ).click().run(timeout=10)

        assert not app.exception
        assert tampering_mock.call_count == 1
        assert any(
            heading.value == "Tampering-risk checkpoint / 篡改风险检查"
            for heading in app.subheader
        )
